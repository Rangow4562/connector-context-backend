"""GitHub entity schemas.

Based on the GitHub REST API (read-only scope), we define entity schemas for:
  • Repository
  • Repository Contents
  • Pull Requests (merged only)
  • Pull Request Review Comments

References:
  • https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28 (Repositories)
  • https://docs.github.com/en/rest/repos/contents?apiVersion=2022-11-28 (Repository contents)
  • https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28 (Pull requests)
  • https://docs.github.com/en/rest/pulls/comments?apiVersion=2022-11-28 (PR review comments)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import computed_field

from connector_context.platform.entities._connector_context_field import ConnectorContextField
from connector_context.platform.entities._base import BaseEntity, Breadcrumb, CodeFileEntity, DeletionEntity


def _parse_gh_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse GitHub ISO8601 timestamps to timezone-aware datetimes."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class GitHubRepositoryEntity(BaseEntity):
    """Schema for GitHub repository entity."""

    repo_id: int = ConnectorContextField(
        ...,
        description="Unique GitHub repository ID",
        is_entity_id=True,
    )
    name: str = ConnectorContextField(
        ...,
        description="Repository short name",
        is_name=True,
        embeddable=True,
    )
    created_at: datetime = ConnectorContextField(
        ...,
        description="Timestamp when the repository was created",
        is_created_at=True,
    )
    updated_at: datetime = ConnectorContextField(
        ...,
        description="Timestamp when the repository was last updated",
        is_updated_at=True,
    )
    full_name: str = ConnectorContextField(
        ..., description="Full repository name including owner", embeddable=True
    )
    description: Optional[str] = ConnectorContextField(
        None, description="Repository description", embeddable=True
    )
    default_branch: str = ConnectorContextField(
        ..., description="Default branch of the repository", embeddable=True
    )
    language: Optional[str] = ConnectorContextField(
        None, description="Primary language of the repository", embeddable=True
    )
    fork: bool = ConnectorContextField(
        ..., description="Whether the repository is a fork", embeddable=False
    )
    size: int = ConnectorContextField(..., description="Size of the repository in KB", embeddable=False)
    stars_count: Optional[int] = ConnectorContextField(
        None, description="Number of stars", embeddable=False
    )
    watchers_count: Optional[int] = ConnectorContextField(
        None, description="Number of watchers", embeddable=False
    )
    forks_count: Optional[int] = ConnectorContextField(
        None, description="Number of forks", embeddable=False
    )
    open_issues_count: Optional[int] = ConnectorContextField(
        None, description="Number of open issues", embeddable=False
    )

    @computed_field(return_type=str)
    def web_url(self) -> str:
        """Clickable GitHub page for the repository."""
        return f"https://github.com/{self.full_name}"

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> GitHubRepositoryEntity:
        """Build from a GitHub API repository object."""
        return cls(
            breadcrumbs=[],
            repo_id=data["id"],
            name=data["name"],
            created_at=_parse_gh_datetime(data["created_at"]),
            updated_at=_parse_gh_datetime(data["updated_at"]),
            full_name=data["full_name"],
            description=data.get("description"),
            default_branch=data["default_branch"],
            language=data.get("language"),
            fork=data["fork"],
            size=data["size"],
            stars_count=data.get("stargazers_count"),
            watchers_count=data.get("watchers_count"),
            forks_count=data.get("forks_count"),
            open_issues_count=data.get("open_issues_count"),
        )


class GitHubDirectoryEntity(BaseEntity):
    """Schema for GitHub directory entity."""

    full_path: str = ConnectorContextField(
        ...,
        description="Repository-qualified directory path (owner/repo/path)",
        is_entity_id=True,
    )
    name: str = ConnectorContextField(
        ...,
        description="Directory name",
        is_name=True,
        embeddable=True,
    )
    path: str = ConnectorContextField(
        ..., description="Path of the directory within the repository", embeddable=True
    )
    repo_name: str = ConnectorContextField(
        ..., description="Name of the repository containing this directory", embeddable=True
    )
    repo_owner: str = ConnectorContextField(..., description="Owner of the repository", embeddable=True)
    branch: str = ConnectorContextField(
        ..., description="Branch that was traversed for this directory", embeddable=True
    )

    @computed_field(return_type=str)
    def web_url(self) -> str:
        """Clickable URL for the directory."""
        if not self.path:
            return f"https://github.com/{self.repo_owner}/{self.repo_name}"
        return (
            f"https://github.com/{self.repo_owner}/{self.repo_name}/tree/{self.branch}/{self.path}"
        )


class GitHubCodeFileEntity(CodeFileEntity):
    """Schema for GitHub code file entity."""

    full_path: str = ConnectorContextField(
        ...,
        description="Repository-qualified file path (owner/repo/path)",
        is_entity_id=True,
    )
    name: str = ConnectorContextField(
        ...,
        description="Filename",
        is_name=True,
        embeddable=True,
    )
    branch: str = ConnectorContextField(
        ..., description="Branch that was traversed for this file", embeddable=True
    )
    sha: str = ConnectorContextField(..., description="SHA hash of the file content", embeddable=False)
    line_count: Optional[int] = ConnectorContextField(
        None, description="Number of lines in the file", embeddable=False
    )
    is_binary: bool = ConnectorContextField(
        False, description="Flag indicating if file is binary", embeddable=False
    )
    html_url: Optional[str] = ConnectorContextField(
        None,
        description="HTML URL for viewing this content on GitHub.",
        embeddable=False,
        unhashable=True,
    )

    @computed_field(return_type=str)
    def web_url(self) -> str:
        """Clickable URL for viewing the file on GitHub."""
        if self.html_url:
            return self.html_url
        return f"https://github.com/{self.repo_owner}/{self.repo_name}/blob/{self.branch}/{self.path_in_repo}"


class GitHubPullRequestEntity(BaseEntity):
    """Schema for a merged GitHub pull request.

    Reference:
        https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28
    """

    pr_id: str = ConnectorContextField(
        ...,
        description="Repository-qualified PR identifier (owner/repo#number)",
        is_entity_id=True,
    )
    title: str = ConnectorContextField(
        ...,
        description="Pull request title",
        is_name=True,
        embeddable=True,
    )
    body: Optional[str] = ConnectorContextField(
        None, description="Pull request description (markdown)", embeddable=True
    )
    number: int = ConnectorContextField(
        ..., description="PR number within the repository", embeddable=False
    )
    state: str = ConnectorContextField(..., description="PR state (closed for merged PRs)", embeddable=True)
    author: Optional[str] = ConnectorContextField(
        None, description="Login of the PR author", embeddable=True
    )
    labels: Optional[List[str]] = ConnectorContextField(
        None, description="Labels applied to the PR", embeddable=True
    )
    assignees: Optional[List[str]] = ConnectorContextField(
        None, description="Assignee logins", embeddable=True
    )
    reviewers: Optional[List[str]] = ConnectorContextField(
        None, description="Requested reviewer logins", embeddable=True
    )
    base_branch: Optional[str] = ConnectorContextField(
        None, description="Base branch the PR was merged into", embeddable=True
    )
    head_branch: Optional[str] = ConnectorContextField(
        None, description="Source branch of the PR", embeddable=True
    )
    additions: Optional[int] = ConnectorContextField(
        None, description="Number of lines added", embeddable=False
    )
    deletions: Optional[int] = ConnectorContextField(
        None, description="Number of lines deleted", embeddable=False
    )
    changed_files: Optional[int] = ConnectorContextField(
        None, description="Number of files changed", embeddable=False
    )
    changed_files_list: Optional[List[str]] = ConnectorContextField(
        None, description="Paths of files changed in this PR", embeddable=True
    )
    merge_commit_sha: Optional[str] = ConnectorContextField(
        None, description="SHA of the merge commit", embeddable=False
    )
    created_time: datetime = ConnectorContextField(
        ..., description="When the PR was created", is_created_at=True
    )
    updated_time: datetime = ConnectorContextField(
        ..., description="When the PR was last updated", is_updated_at=True
    )
    merged_at: Optional[datetime] = ConnectorContextField(
        None, description="When the PR was merged", embeddable=False
    )
    repo_name: str = ConnectorContextField(..., description="Repository short name", embeddable=True)
    repo_owner: str = ConnectorContextField(..., description="Repository owner", embeddable=True)
    web_url_value: Optional[str] = ConnectorContextField(
        None, description="Link to the PR on GitHub", embeddable=False, unhashable=True
    )

    @computed_field(return_type=str)
    def web_url(self) -> str:
        """Clickable URL for the pull request."""
        return self.web_url_value or ""

    @classmethod
    def from_api(
        cls,
        data: Dict[str, Any],
        *,
        repo_name: str,
        repo_owner: str,
        changed_files_list: Optional[List[str]] = None,
        breadcrumbs: List[Breadcrumb],
    ) -> GitHubPullRequestEntity:
        """Build from a GitHub API pull request object."""
        pr_number = data["number"]
        full_repo = f"{repo_owner}/{repo_name}"

        labels = [lbl["name"] for lbl in data.get("labels", []) if lbl.get("name")]
        assignees = [a["login"] for a in data.get("assignees", []) if a.get("login")]
        reviewers = [r["login"] for r in data.get("requested_reviewers", []) if r.get("login")]

        return cls(
            breadcrumbs=breadcrumbs,
            pr_id=f"{full_repo}#{pr_number}",
            title=data["title"],
            body=data.get("body"),
            number=pr_number,
            state=data["state"],
            author=data.get("user", {}).get("login"),
            labels=labels or None,
            assignees=assignees or None,
            reviewers=reviewers or None,
            base_branch=data.get("base", {}).get("ref"),
            head_branch=data.get("head", {}).get("ref"),
            additions=data.get("additions"),
            deletions=data.get("deletions"),
            changed_files=data.get("changed_files"),
            changed_files_list=changed_files_list,
            merge_commit_sha=data.get("merge_commit_sha"),
            created_time=_parse_gh_datetime(data["created_at"]),
            updated_time=_parse_gh_datetime(data["updated_at"]),
            merged_at=_parse_gh_datetime(data.get("merged_at")),
            repo_name=repo_name,
            repo_owner=repo_owner,
            web_url_value=data.get("html_url"),
        )


class GitHubPRCommentEntity(BaseEntity):
    """Schema for a review comment on a GitHub pull request.

    Review comments are anchored to specific lines in the diff.

    Reference:
        https://docs.github.com/en/rest/pulls/comments?apiVersion=2022-11-28
    """

    comment_id: str = ConnectorContextField(
        ...,
        description="Repository-qualified comment identifier (owner/repo#number/comment/id)",
        is_entity_id=True,
    )
    comment_label: str = ConnectorContextField(
        ...,
        description="Short label for the comment",
        is_name=True,
        embeddable=True,
    )
    body: Optional[str] = ConnectorContextField(
        None, description="Comment body (markdown)", embeddable=True
    )
    path: Optional[str] = ConnectorContextField(
        None, description="File path the comment is anchored to", embeddable=True
    )
    diff_hunk: Optional[str] = ConnectorContextField(
        None, description="Diff context surrounding the comment", embeddable=True
    )
    author: Optional[str] = ConnectorContextField(
        None, description="Login of the comment author", embeddable=True
    )
    pr_number: int = ConnectorContextField(
        ..., description="PR number this comment belongs to", embeddable=False
    )
    created_time: datetime = ConnectorContextField(
        ..., description="When the comment was created", is_created_at=True
    )
    updated_time: datetime = ConnectorContextField(
        ..., description="When the comment was last updated", is_updated_at=True
    )
    repo_name: str = ConnectorContextField(..., description="Repository short name", embeddable=True)
    repo_owner: str = ConnectorContextField(..., description="Repository owner", embeddable=True)
    web_url_value: Optional[str] = ConnectorContextField(
        None, description="Link to the comment on GitHub", embeddable=False, unhashable=True
    )

    @computed_field(return_type=str)
    def web_url(self) -> str:
        """Clickable URL for the review comment."""
        return self.web_url_value or ""

    @classmethod
    def from_api(
        cls,
        data: Dict[str, Any],
        *,
        repo_name: str,
        repo_owner: str,
        pr_number: int,
        breadcrumbs: List[Breadcrumb],
    ) -> GitHubPRCommentEntity:
        """Build from a GitHub API review comment object."""
        comment_id = data["id"]
        author = data.get("user", {}).get("login", "unknown")
        path = data.get("path", "")

        label_parts = []
        if author:
            label_parts.append(author)
        if path:
            label_parts.append(path)
        label = f"Comment by {' on '.join(label_parts)}" if label_parts else f"Comment {comment_id}"

        full_repo = f"{repo_owner}/{repo_name}"
        return cls(
            breadcrumbs=breadcrumbs,
            comment_id=f"{full_repo}#{pr_number}/comment/{comment_id}",
            comment_label=label,
            body=data.get("body"),
            path=path,
            diff_hunk=data.get("diff_hunk"),
            author=author,
            pr_number=pr_number,
            created_time=_parse_gh_datetime(data["created_at"]),
            updated_time=_parse_gh_datetime(data["updated_at"]),
            repo_name=repo_name,
            repo_owner=repo_owner,
            web_url_value=data.get("html_url"),
        )


class GithubRepoEntity(BaseEntity):
    """Schema for a GitHub repository (alternative schema).

    References:
      https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28

    Note: This is an alternative repository entity schema. Consider using GitHubRepositoryEntity.
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the repository ID)
    # - breadcrumbs (empty - repositories are top-level)
    # - name (from repository name)
    # - created_at (from created_at timestamp)
    # - updated_at (from updated_at timestamp)

    # API fields
    full_name: Optional[str] = ConnectorContextField(
        None, description="Full name (including owner) of the repo.", embeddable=True
    )
    owner_login: Optional[str] = ConnectorContextField(
        None, description="Login/username of the repository owner.", embeddable=True
    )
    private: bool = ConnectorContextField(
        False, description="Whether the repository is private.", embeddable=False
    )
    description: Optional[str] = ConnectorContextField(
        None, description="Short description of the repository.", embeddable=True
    )
    fork: bool = ConnectorContextField(
        False, description="Whether this repository is a fork.", embeddable=False
    )
    pushed_at: Optional[datetime] = ConnectorContextField(
        None, description="When the repository was last pushed.", embeddable=False
    )
    homepage: Optional[str] = ConnectorContextField(
        None, description="Homepage URL for the repository.", embeddable=False
    )
    size: Optional[int] = ConnectorContextField(
        None, description="Size of the repository (in kilobytes).", embeddable=False
    )
    stargazers_count: int = ConnectorContextField(
        0, description="Number of stars on this repository.", embeddable=False
    )
    watchers_count: int = ConnectorContextField(
        0, description="Number of people watching this repository.", embeddable=False
    )
    language: Optional[str] = ConnectorContextField(
        None, description="Primary language of the repository.", embeddable=True
    )
    forks_count: int = ConnectorContextField(
        0, description="Number of forks for this repository.", embeddable=False
    )
    open_issues_count: int = ConnectorContextField(
        0, description="Number of open issues on this repository.", embeddable=False
    )
    topics: List[str] = ConnectorContextField(
        default_factory=list, description="Topics/tags applied to this repo.", embeddable=True
    )
    default_branch: Optional[str] = ConnectorContextField(
        None, description="Default branch name of the repository.", embeddable=True
    )
    archived: bool = ConnectorContextField(
        False, description="Whether the repository is archived.", embeddable=False
    )
    disabled: bool = ConnectorContextField(
        False, description="Whether the repository is disabled in GitHub.", embeddable=False
    )


class GithubContentEntity(BaseEntity):
    """Schema for a GitHub repository's content (file, directory, submodule, etc.).

    References:
      https://docs.github.com/en/rest/repos/contents?apiVersion=2022-11-28

    Note: This is a generic content entity. Consider using specific entities like
    GitHubCodeFileEntity or GitHubDirectoryEntity.
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (content path or SHA)
    # - breadcrumbs (repository and parent breadcrumbs)
    # - name (file/directory name)
    # - created_at (None - content items don't have creation timestamps)
    # - updated_at (None - content items don't have update timestamps)

    # API fields
    repo_full_name: Optional[str] = ConnectorContextField(
        None, description="Full name of the parent repository.", embeddable=True
    )
    path: Optional[str] = ConnectorContextField(
        None, description="Path of the file or directory within the repo.", embeddable=True
    )
    sha: Optional[str] = ConnectorContextField(
        None, description="SHA identifier for this content item.", embeddable=False
    )
    item_type: Optional[str] = ConnectorContextField(
        None,
        description="Type of content. Typically 'file', 'dir', 'submodule', or 'symlink'.",
        embeddable=False,
    )
    size: Optional[int] = ConnectorContextField(
        None, description="Size of the content (in bytes).", embeddable=False
    )
    html_url: Optional[str] = ConnectorContextField(
        None, description="HTML URL for viewing this content on GitHub.", embeddable=False
    )
    download_url: Optional[str] = ConnectorContextField(
        None, description="Direct download URL if applicable.", embeddable=False
    )
    content: Optional[str] = ConnectorContextField(
        None,
        description="File content (base64-encoded) if retrieved via 'mediaType=raw' or similar.",
        embeddable=True,
    )
    encoding: Optional[str] = ConnectorContextField(
        None,
        description="Indicates the encoding of the content (e.g., 'base64').",
        embeddable=False,
    )


class GitHubFileDeletionEntity(DeletionEntity):
    """Schema for GitHub file deletion entity.

    This entity is used to signal that a file has been removed from the repository
    and should be deleted from the destination.
    """

    deletes_entity_class = GitHubCodeFileEntity

    full_path: str = ConnectorContextField(
        ...,
        description="Repository-qualified file path (owner/repo/path)",
        is_entity_id=True,
    )
    deletion_label: str = ConnectorContextField(
        ...,
        description="Human-readable deletion label",
        is_name=True,
        embeddable=True,
    )
    file_path: str = ConnectorContextField(
        ..., description="Path of the deleted file within the repository", embeddable=False
    )
    repo_name: str = ConnectorContextField(
        ..., description="Name of the repository containing the deleted file", embeddable=False
    )
    repo_owner: str = ConnectorContextField(..., description="Owner of the repository", embeddable=False)
    branch: Optional[str] = ConnectorContextField(
        None, description="Branch context for the deleted file", embeddable=False
    )

    @computed_field(return_type=str)
    def web_url(self) -> str:
        """Fallback to repository page since deleted files have no direct URLs."""
        return f"https://github.com/{self.repo_owner}/{self.repo_name}"
