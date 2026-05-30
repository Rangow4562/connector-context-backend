"""Slack source implementation for federated search."""

from __future__ import annotations

import re
from typing import Any, AsyncGenerator, Dict, List, Optional

from tenacity import retry, stop_after_attempt

from connector_context.core.logging import ContextualLogger
from connector_context.core.shared_models import RateLimitLevel
from connector_context.domains.browse_tree.types import NodeSelectionData
from connector_context.domains.sources.exceptions import SourceAuthError
from connector_context.domains.sources.token_providers.protocol import TokenProviderProtocol
from connector_context.domains.storage.file_service import FileService
from connector_context.domains.sync_pipeline.pipeline.text_builder import TextualRepresentationBuilder
from connector_context.domains.syncs.cursors.cursor import SyncCursor
from connector_context.platform.configs.auth import SlackAuthConfig
from connector_context.platform.configs.config import SlackConfig
from connector_context.platform.decorators import source
from connector_context.platform.entities._base import ConnectorContextSystemMetadata, BaseEntity, Breadcrumb
from connector_context.platform.entities.slack import SlackMessageEntity
from connector_context.platform.http_client.connector_context_client import ConnectorContextHttpClient
from connector_context.platform.sources._base import BaseSource
from connector_context.platform.sources.http_helpers import raise_for_status
from connector_context.platform.sources.retry_helpers import (
    retry_if_rate_limit_or_timeout,
    wait_rate_limit_with_backoff,
)
from connector_context.schemas.source_connection import AuthenticationMethod, OAuthType

# Pattern for Slack mrkdwn special sequences:
# <@U1234|display_name> → @display_name  (user mention with label)
# <@U1234>              → @U1234         (user mention without label)
# <#C1234|channel-name> → #channel-name  (channel mention with label)
# <#C1234>              → #C1234         (channel mention without label)
# <!subteam^S1234|@team> → @team         (user group mention)
# <!here>, <!channel>, <!everyone> → @here, @channel, @everyone
# <http://url|label>    → label          (link with label)
# <http://url>          → url            (link without label)
_SLACK_MRKDWN_PATTERN = re.compile(
    r"<"
    r"(?:"
    r"[@#!](?:[A-Z0-9^]+\|)?([^>|]+)"  # mentions: use label after pipe, or the ID
    r"|"
    r"(?:https?://[^|>]+)\|([^>]+)"  # links with label: use label
    r"|"
    r"(https?://[^>]+)"  # links without label: use URL
    r")"
    r">"
)


def _clean_slack_mrkdwn(text: str) -> str:
    """Strip Slack mrkdwn markup, replacing mentions and links with display text."""

    def _replace(m: re.Match[str]) -> str:
        if m.group(1):
            # Mention (user/channel/special) — use the label
            return m.group(1)
        # Link — use label or URL
        return m.group(2) or m.group(3) or ""

    cleaned = _SLACK_MRKDWN_PATTERN.sub(_replace, text)
    # Strip Slack search highlight markers (U+E000 / U+E001 wrap matched terms)
    cleaned = cleaned.replace("\ue000", "").replace("\ue001", "")
    # Collapse multiple spaces left by removed markup
    return re.sub(r"  +", " ", cleaned).strip()


@source(
    name="Slack",
    short_name="slack",
    auth_methods=[
        AuthenticationMethod.OAUTH_BROWSER,
        AuthenticationMethod.OAUTH_TOKEN,
        AuthenticationMethod.AUTH_PROVIDER,
    ],
    oauth_type=OAuthType.ACCESS_ONLY,
    auth_config_class=SlackAuthConfig,
    config_class=SlackConfig,
    labels=["Communication", "Messaging"],
    supports_continuous=False,
    federated_search=True,
    rate_limit_level=RateLimitLevel.ORG,
)
class SlackSource(BaseSource):
    """Slack source connector using federated search.

    Instead of syncing all messages and files, this source searches Slack at query time
    using the search.all API endpoint. This is necessary because Slack's rate limits
    are too restrictive for full synchronization.
    """

    @classmethod
    async def create(
        cls,
        *,
        auth: TokenProviderProtocol,
        logger: ContextualLogger,
        http_client: ConnectorContextHttpClient,
        config: SlackConfig,
    ) -> SlackSource:
        """Create a new Slack source."""
        instance = cls(auth=auth, logger=logger, http_client=http_client)
        instance._channel_ids = list(config.channel_ids or [])
        instance._channel_names = list(config.channel_names or [])
        return instance

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(5),
        retry=retry_if_rate_limit_or_timeout,
        wait=wait_rate_limit_with_backoff,
        reraise=True,
    )
    async def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict:
        """Make authenticated GET request to Slack API with token refresh support."""
        token = await self.auth.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        response = await self.http_client.get(url, headers=headers, params=params)

        if response.status_code == 401 and self.auth.supports_refresh:
            new_token = await self.auth.force_refresh()
            headers = {"Authorization": f"Bearer {new_token}"}
            response = await self.http_client.get(url, headers=headers, params=params)

        raise_for_status(
            response,
            source_short_name=self.short_name,
            token_provider_kind=self.auth.provider_kind,
        )
        return response.json()

    # ------------------------------------------------------------------
    # Federated search
    # ------------------------------------------------------------------

    def _build_scoped_query(self, query: str) -> str:
        """Append channel scope qualifiers to the search query."""
        channel_filters = []
        for ch_id in self._channel_ids:
            channel_filters.append(f"in:<#{ch_id}>")
        for ch_name in self._channel_names:
            name = ch_name.lstrip("#")
            channel_filters.append(f"in:#{name}")
        if channel_filters:
            return f"{query} {' '.join(channel_filters)}"
        return query

    async def search(self, query: str, limit: int) -> List[BaseEntity]:
        """Search Slack for messages matching the query with pagination support.

        Uses Slack's search.messages API endpoint with pagination to retrieve
        up to the requested limit. Files are not included since processing file
        content requires the full sync pipeline (download, chunking, vectorization)
        which federated search sources skip.
        """
        scoped_query = self._build_scoped_query(query)
        self.logger.info(
            f"Searching Slack messages for query: '{scoped_query}' (limit: {limit})"
        )
        results = await self._paginate_search_results(scoped_query, limit)
        self.logger.info(f"Slack search complete: returned {len(results)} results")
        return results

    async def _paginate_search_results(self, query: str, limit: int) -> List[BaseEntity]:
        """Paginate through Slack search results."""
        page = 1
        results_fetched = 0
        max_results_per_page = 100
        all_entities: List[BaseEntity] = []

        while results_fetched < limit:
            count = min(max_results_per_page, limit - results_fetched)
            response_data = await self._fetch_search_page(query, count, page)

            if not response_data:
                break

            messages = response_data.get("messages", {})
            message_matches = messages.get("matches", [])
            paging_info = messages.get("paging", {})

            self.logger.debug(
                f"Page {page}: found {len(message_matches)} results "
                f"(total available: {paging_info.get('total', 'unknown')})"
            )

            if not message_matches:
                break

            entities = self._process_message_matches(message_matches, limit, results_fetched)
            all_entities.extend(entities)
            results_fetched += len(entities)

            if page >= paging_info.get("pages", 1):
                break

            page += 1

        return all_entities

    async def _fetch_search_page(
        self, query: str, count: int, page: int
    ) -> Optional[Dict[str, Any]]:
        """Fetch a single page of search results from Slack API."""
        params = {
            "query": query,
            "count": count,
            "page": page,
            "highlight": True,
            "sort": "score",
        }

        response_data = await self._get("https://slack.com/api/search.messages", params=params)

        if not response_data.get("ok"):
            error = response_data.get("error", "unknown_error")
            self.logger.warning(f"Slack search API error: {error}")

            if error == "missing_scope":
                raise ValueError(
                    "Slack search failed: missing 'search:read' scope. "
                    "Please ensure your Slack OAuth connection includes the 'search:read' scope "
                    "to enable message search."
                )
            elif error == "not_authed":
                raise ValueError("Slack search failed: authentication token is invalid or expired")
            elif error == "account_inactive":
                raise ValueError("Slack search failed: account is inactive")
            else:
                raise ValueError(f"Slack search failed: {error}")

        return response_data

    def _process_message_matches(
        self, message_matches: List[Dict], limit: int, results_fetched: int
    ) -> List[BaseEntity]:
        """Process message matches and return entities."""
        entities: List[BaseEntity] = []
        for message in message_matches:
            if results_fetched + len(entities) >= limit:
                break

            try:
                entity = self._create_message_entity(message)
                if entity:
                    entities.append(entity)
            except SourceAuthError:
                raise
            except Exception as e:
                self.logger.warning(f"Error creating message entity: {e}")
                continue

        return entities

    def _create_message_entity(self, message: Dict[str, Any]) -> Optional[SlackMessageEntity]:
        """Create a SlackMessageEntity from a search result."""
        channel_info = message.get("channel", {})
        channel_id = channel_info.get("id", "unknown")
        channel_name = channel_info.get("name")

        breadcrumbs = [
            Breadcrumb(
                entity_id=channel_id,
                name=f"#{channel_name}" if channel_name else channel_id,
                entity_type="SlackChannel",
            )
        ]

        entity = SlackMessageEntity.from_api(message, breadcrumbs=breadcrumbs)

        entity.connector_context_system_metadata = ConnectorContextSystemMetadata(
            source_name="slack",
            entity_type="SlackMessageEntity",
            sync_id=None,
            sync_job_id=None,
        )

        entity.textual_representation = TextualRepresentationBuilder().build_metadata_section(
            entity=entity,
            source_name="slack",
        )

        return entity

    # ------------------------------------------------------------------
    # Sync entry point (not used — Slack is federated search only)
    # ------------------------------------------------------------------

    async def generate_entities(
        self,
        *,
        cursor: SyncCursor | None = None,
        files: FileService | None = None,
        node_selections: list[NodeSelectionData] | None = None,
    ) -> AsyncGenerator[BaseEntity, None]:
        """Not used — Slack is a federated search source.

        Raises NotImplementedError; use search() instead.
        """
        self.logger.warning("generate_entities() called on federated search source")
        raise NotImplementedError(
            "Slack uses federated search. Use the search() method instead of generate_entities()."
        )
        yield  # make this a generator  # noqa: RUF027

    async def validate(self) -> None:
        """Validate credentials by calling Slack auth.test."""
        await self._get("https://slack.com/api/auth.test")
