"""API endpoints for entity definitions and relations."""

from connector_context.api.deps import Inject
from connector_context.api.router import TrailingSlashRouter
from connector_context.domains.entities.protocols import EntityDefinitionRegistryProtocol
from connector_context.domains.entities.types import EntityDefinitionMetadata

router = TrailingSlashRouter()


@router.get("/definitions/by-source/", response_model=list[EntityDefinitionMetadata])
async def get_entity_definitions_by_source_short_name(
    source_short_name: str,
    registry: EntityDefinitionRegistryProtocol = Inject(EntityDefinitionRegistryProtocol),
) -> list[EntityDefinitionMetadata]:
    """Get all entity definitions for a given source."""
    entries = registry.list_for_source(source_short_name)
    return [
        EntityDefinitionMetadata(
            short_name=entry.short_name,
            name=entry.name,
            description=entry.description,
            class_name=entry.class_name,
            module_name=entry.module_name,
            entity_type=entry.entity_type,
            entity_schema=entry.entity_schema,
        )
        for entry in entries
    ]
