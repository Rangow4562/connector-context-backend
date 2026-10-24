"""Repository implementations for OAuth domain, wrapping crud singletons."""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from connector_context import crud
from connector_context.api.context import ApiContext
from connector_context.core.context import BaseContext
from connector_context.crud import connection_init_session, redirect_session
from connector_context.db.unit_of_work import UnitOfWork
from connector_context.domains.oauth.protocols import (
    OAuthInitSessionRepositoryProtocol,
    OAuthRedirectSessionRepositoryProtocol,
)
from connector_context.models.connection_init_session import ConnectionInitSession
from connector_context.models.redirect_session import RedirectSession


class OAuthInitSessionRepository(OAuthInitSessionRepositoryProtocol):
    """Delegates to crud.connection_init_session."""

    async def get_by_state_no_auth(
        self, db: AsyncSession, *, state: str
    ) -> Optional[ConnectionInitSession]:
        """Look up an init session by OAuth state parameter."""
        return await connection_init_session.get_by_state_no_auth(db, state=state)

    async def get_by_oauth_token_no_auth(
        self, db: AsyncSession, *, oauth_token: str
    ) -> Optional[ConnectionInitSession]:
        """Look up an init session by OAuth token."""
        return await connection_init_session.get_by_oauth_token_no_auth(db, oauth_token=oauth_token)

    async def get(
        self,
        db: AsyncSession,
        *,
        id: UUID,
        ctx: BaseContext,
    ) -> Optional[ConnectionInitSession]:
        """Fetch an init session by ID (org-scoped)."""
        return await connection_init_session.get(db, id=id, ctx=ctx)

    async def create(
        self,
        db: AsyncSession,
        *,
        obj_in: Dict[str, Any],
        ctx: ApiContext,
        uow: UnitOfWork,
    ) -> ConnectionInitSession:
        """Create a new connection init session."""
        return await connection_init_session.create(db, obj_in=obj_in, ctx=ctx, uow=uow)

    async def mark_completed(
        self,
        db: AsyncSession,
        *,
        session_id: UUID,
        final_connection_id: Optional[UUID],
        ctx: ApiContext,
    ) -> None:
        """Mark an init session as completed with the final connection ID."""
        await connection_init_session.mark_completed(
            db, session_id=session_id, final_connection_id=final_connection_id, ctx=ctx
        )


class OAuthRedirectSessionRepository(OAuthRedirectSessionRepositoryProtocol):
    """Delegates to crud.redirect_session."""

    async def generate_unique_code(self, db: AsyncSession, *, length: int) -> str:
        """Generate a unique redirect code of the given length."""
        return await redirect_session.generate_unique_code(db, length=length)

    async def create(
        self,
        db: AsyncSession,
        *,
        code: str,
        final_url: str,
        expires_at: datetime,
        ctx: ApiContext,
        uow: Optional[UnitOfWork] = None,
    ) -> RedirectSession:
        """Create a new redirect session."""
        return await redirect_session.create(
            db, code=code, final_url=final_url, expires_at=expires_at, ctx=ctx, uow=uow
        )

    async def get_by_code(self, db: AsyncSession, code: str) -> Optional[RedirectSession]:
        """Look up a redirect session by its code."""
        return await crud.redirect_session.get_by_code(db, code)

    async def consume(
        self, db: AsyncSession, code: str, *, uow: Optional[UnitOfWork] = None
    ) -> Optional[RedirectSession]:
        """Atomically consume a redirect session (one-time use)."""
        return await redirect_session.consume(db, code, uow=uow)
