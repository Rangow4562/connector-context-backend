"""URL scope parser — converts user-provided URLs/paths into connector-specific scope config."""

from typing import Any, Optional
from urllib.parse import urlparse, unquote

from pydantic import BaseModel, Field


class ScopeResolution(BaseModel):
    """Result of parsing a scope URL."""

    resolved: bool
    scope_type: str  # "site", "folder", "library", "space", "page", "channel", "repo", "project", "path"
    description: str  # Human-readable: "ather library in Aventia site"
    config: dict[str, Any] = Field(default_factory=dict)  # Connector-specific config overrides
    error: Optional[str] = None


class ScopeParser:
    """Parse scope URLs/paths into connector-specific config for all source types."""

    _PARSERS: dict = {}

    @classmethod
    def register(cls, *short_names: str):
        """Decorator to register a parser for one or more source short_names."""
        def wrapper(func):
            for name in short_names:
                cls._PARSERS[name] = func
            return func
        return wrapper

    @classmethod
    def parse(cls, short_name: str, url: str) -> ScopeResolution:
        """Parse a URL for any source type."""
        if not url or not url.strip():
            return ScopeResolution(
                resolved=False,
                scope_type="all",
                description="Will sync all content",
                config={},
            )

        parser = cls._PARSERS.get(short_name)
        if parser:
            try:
                return parser(url.strip())
            except Exception as e:
                return ScopeResolution(
                    resolved=False,
                    scope_type="unknown",
                    description="",
                    config={},
                    error=str(e),
                )

        # Fallback: treat as raw path filter for any unregistered connector
        return ScopeResolution(
            resolved=True,
            scope_type="path",
            description=f"Will filter content matching: {url.strip()}",
            config={"scope_url": url.strip()},
        )

    @classmethod
    def get_supported_sources(cls) -> list[str]:
        """Return list of short_names with custom parsers."""
        return list(cls._PARSERS.keys())

    @classmethod
    def get_placeholder(cls, short_name: str) -> str:
        """Return source-aware placeholder text for the scope input."""
        placeholders = {
            "sharepoint": "https://company.sharepoint.com/sites/Team/Library",
            "sharepoint_online": "https://company.sharepoint.com/sites/Team/Library",
            "sharepoint_online_app": "https://company.sharepoint.com/sites/Team/Library",
            "google_drive": "https://drive.google.com/drive/folders/abc123",
            "google_docs": "https://drive.google.com/drive/folders/abc123",
            "google_slides": "https://drive.google.com/drive/folders/abc123",
            "onedrive": "/Documents/Projects or OneDrive URL",
            "dropbox": "/team/projects or Dropbox folder URL",
            "box": "https://app.box.com/folder/123 or folder ID",
            "confluence": "https://company.atlassian.net/wiki/spaces/ENG or space key",
            "notion": "https://notion.so/workspace/page-title-id",
            "slack": "general, engineering or Slack channel URL",
            "github": "https://github.com/owner/repo",
            "gitlab": "https://gitlab.com/owner/repo",
            "jira": "PROJ, PROJ2 or Jira project URL",
            "salesforce": "Account, Contact, Opportunity",
            "airtable": "https://airtable.com/appXXXX",
            "teams": "general, team-name or Teams channel URL",
        }
        return placeholders.get(short_name, "Paste a URL or path to limit sync scope")


# ── SharePoint ──────────────────────────────────────────────────────────────


@ScopeParser.register("sharepoint", "sharepoint_online", "sharepoint_online_app")
def _parse_sharepoint(url: str) -> ScopeResolution:
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]

    # Remove trailing Forms/AllItems.aspx suffix
    while path_parts and path_parts[-1].lower() in ("forms", "allitems.aspx"):
        path_parts.pop()

    site_url = ""
    drive_name = ""
    folder_path = ""
    if "sites" in path_parts:
        idx = path_parts.index("sites")
        if idx + 1 < len(path_parts):
            site_name = path_parts[idx + 1]
            site_url = f"{parsed.scheme}://{parsed.netloc}/sites/{site_name}"
            remaining = path_parts[idx + 2:]
            if remaining:
                # First component = document library (drive) name
                # Remaining components = subfolder path within the library
                drive_name = remaining[0]
                if len(remaining) > 1:
                    folder_path = "/".join(remaining[1:])

    if site_url and drive_name and folder_path:
        return ScopeResolution(
            resolved=True,
            scope_type="folder",
            description=f"{folder_path} in {drive_name} library ({site_url.split('/')[-1]} site)",
            config={"site_url": site_url, "drive_name": drive_name, "folder_path": folder_path},
        )
    elif site_url and drive_name:
        return ScopeResolution(
            resolved=True,
            scope_type="library",
            description=f"{drive_name} library in {site_url.split('/')[-1]} site",
            config={"site_url": site_url, "drive_name": drive_name},
        )
    elif site_url:
        return ScopeResolution(
            resolved=True,
            scope_type="site",
            description=f"All content in {site_url.split('/')[-1]} site",
            config={"site_url": site_url},
        )

    return ScopeResolution(
        resolved=False,
        scope_type="unknown",
        description="",
        config={},
        error="Could not parse SharePoint URL. Expected: https://company.sharepoint.com/sites/SiteName/...",
    )


# ── Google Drive / Docs / Slides ────────────────────────────────────────────


@ScopeParser.register("google_drive", "google_docs", "google_slides")
def _parse_google_drive(url: str) -> ScopeResolution:
    parsed = urlparse(url)
    path = parsed.path

    if "/folders/" in path:
        folder_id = path.split("/folders/")[-1].strip("/")
        return ScopeResolution(
            resolved=True,
            scope_type="folder",
            description=f"Google Drive folder: {folder_id[:12]}...",
            config={"folder_id": folder_id},
        )

    if "/document/d/" in path or "/spreadsheets/d/" in path or "/presentation/d/" in path:
        doc_id = path.split("/d/")[-1].split("/")[0]
        return ScopeResolution(
            resolved=True,
            scope_type="file",
            description=f"Single document: {doc_id[:12]}...",
            config={"document_id": doc_id},
        )

    return ScopeResolution(
        resolved=False,
        scope_type="unknown",
        description="",
        config={},
        error="Paste a Google Drive folder URL (e.g., https://drive.google.com/drive/folders/...)",
    )


# ── OneDrive ────────────────────────────────────────────────────────────────


@ScopeParser.register("onedrive")
def _parse_onedrive(url: str) -> ScopeResolution:
    if url.startswith("/") or not url.startswith("http"):
        return ScopeResolution(
            resolved=True,
            scope_type="folder",
            description=f"Folder path: {url}",
            config={"folder_path": url.strip("/")},
        )
    parsed = urlparse(url)
    path = unquote(parsed.path)
    return ScopeResolution(
        resolved=True,
        scope_type="path",
        description=f"OneDrive path: {path}",
        config={"folder_path": path.strip("/")},
    )


# ── Dropbox ─────────────────────────────────────────────────────────────────


@ScopeParser.register("dropbox")
def _parse_dropbox(url: str) -> ScopeResolution:
    if url.startswith("/") or not url.startswith("http"):
        return ScopeResolution(
            resolved=True,
            scope_type="folder",
            description=f"Dropbox folder: {url}",
            config={"include_path": url},
        )
    parsed = urlparse(url)
    path = unquote(parsed.path).replace("/home", "")
    return ScopeResolution(
        resolved=True,
        scope_type="folder",
        description=f"Dropbox path: {path}",
        config={"include_path": path},
    )


# ── Box ─────────────────────────────────────────────────────────────────────


@ScopeParser.register("box")
def _parse_box(url: str) -> ScopeResolution:
    if url.isdigit():
        return ScopeResolution(
            resolved=True,
            scope_type="folder",
            description=f"Box folder ID: {url}",
            config={"folder_id": url},
        )
    parsed = urlparse(url)
    if "/folder/" in parsed.path:
        folder_id = parsed.path.split("/folder/")[-1].strip("/")
        return ScopeResolution(
            resolved=True,
            scope_type="folder",
            description=f"Box folder: {folder_id}",
            config={"folder_id": folder_id},
        )
    return ScopeResolution(
        resolved=True,
        scope_type="path",
        description=f"Box: {url}",
        config={"scope_url": url},
    )


# ── Confluence ──────────────────────────────────────────────────────────────


@ScopeParser.register("confluence")
def _parse_confluence(url: str) -> ScopeResolution:
    parsed = urlparse(url)
    path = parsed.path

    if "/spaces/" in path:
        parts = path.split("/spaces/")[-1].split("/")
        space_key = parts[0]
        page_path = "/".join(parts[1:]) if len(parts) > 1 else ""

        if "pages/" in page_path:
            page_id = page_path.split("pages/")[-1].split("/")[0]
            return ScopeResolution(
                resolved=True,
                scope_type="page",
                description=f"Confluence page {page_id} in space {space_key}",
                config={"space_key": space_key, "page_id": page_id},
            )
        return ScopeResolution(
            resolved=True,
            scope_type="space",
            description=f"Confluence space: {space_key}",
            config={"space_key": space_key},
        )

    if url.isalpha() and url.isupper():
        return ScopeResolution(
            resolved=True,
            scope_type="space",
            description=f"Confluence space: {url}",
            config={"space_key": url},
        )

    return ScopeResolution(
        resolved=False,
        scope_type="unknown",
        description="",
        config={},
        error="Paste a Confluence space or page URL",
    )


# ── Notion ──────────────────────────────────────────────────────────────────


@ScopeParser.register("notion")
def _parse_notion(url: str) -> ScopeResolution:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    parts = path.split("-")
    page_id = parts[-1] if parts else path

    if len(page_id) == 32:
        formatted = f"{page_id[:8]}-{page_id[8:12]}-{page_id[12:16]}-{page_id[16:20]}-{page_id[20:]}"
        return ScopeResolution(
            resolved=True,
            scope_type="page",
            description=f"Notion page and its children: {formatted[:18]}...",
            config={"root_page_id": formatted},
        )

    return ScopeResolution(
        resolved=True,
        scope_type="path",
        description=f"Notion: {url}",
        config={"scope_url": url},
    )


# ── Slack ────────────────────────────────────────────────────────────────────


@ScopeParser.register("slack")
def _parse_slack(url: str) -> ScopeResolution:
    parsed = urlparse(url)

    if "/archives/" in parsed.path:
        channel_id = parsed.path.split("/archives/")[-1].strip("/")
        return ScopeResolution(
            resolved=True,
            scope_type="channel",
            description=f"Slack channel: {channel_id}",
            config={"channel_ids": [channel_id]},
        )

    if not url.startswith("http"):
        channels = [c.strip().lstrip("#") for c in url.split(",") if c.strip()]
        return ScopeResolution(
            resolved=True,
            scope_type="channel",
            description=f"Slack channels: {', '.join(channels)}",
            config={"channel_names": channels},
        )

    return ScopeResolution(
        resolved=True,
        scope_type="path",
        description=f"Slack: {url}",
        config={"scope_url": url},
    )


# ── GitHub ───────────────────────────────────────────────────────────────────


@ScopeParser.register("github")
def _parse_github(url: str) -> ScopeResolution:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]

    if len(parts) >= 2:
        owner, repo = parts[0], parts[1]
        if len(parts) > 3 and parts[2] == "tree":
            branch = parts[3]
            path = "/".join(parts[4:]) if len(parts) > 4 else ""
            return ScopeResolution(
                resolved=True,
                scope_type="folder",
                description=f"GitHub: {owner}/{repo}/{path} (branch: {branch})",
                config={"repo_name": f"{owner}/{repo}", "branch": branch, "path_filter": path},
            )
        return ScopeResolution(
            resolved=True,
            scope_type="repo",
            description=f"GitHub repo: {owner}/{repo}",
            config={"repo_name": f"{owner}/{repo}"},
        )

    return ScopeResolution(
        resolved=False,
        scope_type="unknown",
        description="",
        config={},
        error="Paste a GitHub repository URL",
    )


# ── GitLab ───────────────────────────────────────────────────────────────────


@ScopeParser.register("gitlab")
def _parse_gitlab(url: str) -> ScopeResolution:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) >= 2:
        project = "/".join(parts[:2])
        return ScopeResolution(
            resolved=True,
            scope_type="repo",
            description=f"GitLab project: {project}",
            config={"project_path": project},
        )
    return ScopeResolution(
        resolved=True,
        scope_type="path",
        description=f"GitLab: {url}",
        config={"scope_url": url},
    )


# ── Jira ─────────────────────────────────────────────────────────────────────


@ScopeParser.register("jira")
def _parse_jira(url: str) -> ScopeResolution:
    parsed = urlparse(url)

    if "/projects/" in parsed.path:
        project_key = parsed.path.split("/projects/")[-1].split("/")[0]
        return ScopeResolution(
            resolved=True,
            scope_type="project",
            description=f"Jira project: {project_key}",
            config={"project_keys": [project_key]},
        )

    if not url.startswith("http"):
        keys = [k.strip().upper() for k in url.split(",") if k.strip()]
        return ScopeResolution(
            resolved=True,
            scope_type="project",
            description=f"Jira projects: {', '.join(keys)}",
            config={"project_keys": keys},
        )

    return ScopeResolution(
        resolved=True,
        scope_type="path",
        description=f"Jira: {url}",
        config={"scope_url": url},
    )


# ── HubSpot ──────────────────────────────────────────────────────────────────


@ScopeParser.register("hubspot")
def _parse_hubspot(url: str) -> ScopeResolution:
    return ScopeResolution(
        resolved=True,
        scope_type="path",
        description=f"HubSpot scope: {url}",
        config={"scope_url": url},
    )


# ── Microsoft Teams ──────────────────────────────────────────────────────────


@ScopeParser.register("teams")
def _parse_teams(url: str) -> ScopeResolution:
    if not url.startswith("http"):
        channels = [c.strip() for c in url.split(",") if c.strip()]
        return ScopeResolution(
            resolved=True,
            scope_type="channel",
            description=f"Teams channels: {', '.join(channels)}",
            config={"channel_names": channels},
        )
    return ScopeResolution(
        resolved=True,
        scope_type="path",
        description=f"Teams: {url}",
        config={"scope_url": url},
    )


# ── Salesforce ───────────────────────────────────────────────────────────────


@ScopeParser.register("salesforce")
def _parse_salesforce(url: str) -> ScopeResolution:
    if not url.startswith("http"):
        objects = [o.strip() for o in url.split(",") if o.strip()]
        return ScopeResolution(
            resolved=True,
            scope_type="object",
            description=f"Salesforce objects: {', '.join(objects)}",
            config={"object_types": objects},
        )
    return ScopeResolution(
        resolved=True,
        scope_type="path",
        description=f"Salesforce: {url}",
        config={"scope_url": url},
    )


# ── Airtable ─────────────────────────────────────────────────────────────────


@ScopeParser.register("airtable")
def _parse_airtable(url: str) -> ScopeResolution:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if parts and parts[0].startswith("app"):
        base_id = parts[0]
        table_id = parts[1] if len(parts) > 1 else None
        desc = f"Airtable base: {base_id}"
        config: dict = {"base_id": base_id}
        if table_id:
            desc += f", table: {table_id}"
            config["table_id"] = table_id
        return ScopeResolution(
            resolved=True,
            scope_type="base",
            description=desc,
            config=config,
        )
    return ScopeResolution(
        resolved=True,
        scope_type="path",
        description=f"Airtable: {url}",
        config={"scope_url": url},
    )
