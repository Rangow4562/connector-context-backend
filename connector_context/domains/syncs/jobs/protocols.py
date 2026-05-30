"""Protocols for the sync jobs subdomain."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from connector_context.core.context import BaseContext
from connector_context.core.shared_models import SourceConnectionErrorCategory, SyncJobStatus
from connector_context.db.unit_of_work import UnitOfWork
from connector_context.domains.sync_pipeline.pipeline.entity_tracker import SyncStats
from connector_context.domains.syncs.jobs.types import LifecycleData, TransitionResult
from connector_context.models.sync_job import SyncJob
from connector_context.schemas.sync_job import SyncJobCreate, SyncJobUpdate


class SyncJobRepositoryProtocol(Protocol):
    """Data access for sync job records."""

    async def get(self, db: AsyncSession, id: UUID, ctx: BaseContext) -> Optional[SyncJob]:
        """Get a sync job by ID within org scope."""
        ...

    async def get_latest_by_sync_id(self, db: AsyncSession, sync_id: UUID) -> Optional[SyncJob]:
        """Get the most recent sync job for a sync."""
        ...

    async def get_active_for_sync(
        self, db: AsyncSession, sync_id: UUID, ctx: BaseContext
    ) -> List[SyncJob]:
        """Get all active (PENDING, RUNNING, CANCELLING) jobs for a sync."""
        ...

    async def get_all_by_sync_id(
        self,
        db: AsyncSession,
        sync_id: UUID,
        ctx: BaseContext,
        limit: Optional[int] = None,
    ) -> List[SyncJob]:
        """Get all jobs for a specific sync."""
        ...

    async def create(
        self,
        db: AsyncSession,
        obj_in: SyncJobCreate,
        ctx: BaseContext,
        uow: Optional[UnitOfWork] = None,
    ) -> SyncJob:
        """Create a new sync job."""
        ...

    async def update(
        self,
        db: AsyncSession,
        db_obj: SyncJob,
        obj_in: SyncJobUpdate,
        ctx: BaseContext,
    ) -> SyncJob:
        """Update an existing sync job."""
        ...

    async def get_stuck_jobs_by_status(
        self,
        db: AsyncSession,
        status: List[str],
        modified_before: Optional[datetime] = None,
        started_before: Optional[datetime] = None,
    ) -> List[SyncJob]:
        """Get sync jobs stuck in specific statuses based on timestamps."""
        ...


class SyncJobServiceProtocol(Protocol):
    """Sync job status management."""

    async def update_status(
        self,
        sync_job_id: UUID,
        status: SyncJobStatus,
        ctx: BaseContext,
        stats: Optional[SyncStats] = None,
        error: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        failed_at: Optional[datetime] = None,
        error_category: Optional[SourceConnectionErrorCategory] = None,
    ) -> None:
        """Update sync job status with provided details."""
        ...


class SyncJobStateMachineProtocol(Protocol):
    """Validated, idempotent sync job status transitions."""

    async def transition(
        self,
        sync_job_id: UUID,
        target: SyncJobStatus,
        ctx: BaseContext,
        *,
        lifecycle_data: Optional[LifecycleData] = None,
        error: Optional[str] = None,
        stats: Optional[SyncStats] = None,
        error_category: Optional[SourceConnectionErrorCategory] = None,
    ) -> TransitionResult:
        """Execute a validated, idempotent status transition."""
        ...
