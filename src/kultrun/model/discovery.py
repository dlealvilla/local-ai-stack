"""Source discovery query and result. Not compatibility and not capacity."""

from __future__ import annotations

from dataclasses import dataclass, field

from kultrun.model.contracts import ModelCatalogEntry


@dataclass(frozen=True, slots=True)
class DiscoveryQuery:
    """Cheap remote/source-native filters. Hints, not Kultrun compatibility."""

    pipeline_tag: str | None = "text-generation"
    gated: bool | None = False
    apps: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    search: str | None = None
    parameter_min: int | None = None
    parameter_max: int | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True)
class FunnelQuery:
    """Inputs for one Available Models pass. Not a recommendation."""

    discovery: DiscoveryQuery = field(default_factory=DiscoveryQuery)
    requested_context_tokens: int | None = None
    allow_commercially_restricted: bool = True


@dataclass(frozen=True, slots=True)
class RemoteDiscoveryHit:
    """One source-native listing row. Not a catalog entry and not eligible."""

    source_ref: str
    pipeline_tag: str | None = None
    gated: bool | None = None
    tags: tuple[str, ...] = ()
    apps: tuple[str, ...] = ()
    parameter_count: int | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Stage A output. Curated catalog members are never dropped here."""

    universe_count: int
    discovered_count: int
    criteria: DiscoveryQuery
    catalog_entries: tuple[ModelCatalogEntry, ...]
    remote_hits: tuple[RemoteDiscoveryHit, ...] = ()
    live: bool = False
    source_failure: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def payload(self) -> dict[str, object]:
        """API-shaped discovery counts. Not a compatibility verdict."""
        return {
            "universe_count": self.universe_count,
            "discovered_count": self.discovered_count,
            "live": self.live,
            "source_failure": self.source_failure,
            "criteria": {
                "pipeline_tag": self.criteria.pipeline_tag,
                "gated": self.criteria.gated,
                "apps": list(self.criteria.apps),
                "tags": list(self.criteria.tags),
                "search": self.criteria.search,
                "parameter_min": self.criteria.parameter_min,
                "parameter_max": self.criteria.parameter_max,
                "limit": self.criteria.limit,
            },
            "notes": list(self.notes),
            "compatibility": False,
        }
