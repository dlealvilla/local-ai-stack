"""What the organisation knows, normalized away from where it is kept.

`docs/PRODUCT_VISION.md` §39 asks that all knowledge sources normalize to
one representation and, importantly, that the platform not assume content
must be copied locally. ``content_location`` is therefore a reference: some
sources are indexed in place and read at retrieval time, and a contract
that assumed a local copy would make those sources unsupportable.

**Connectors advertise capabilities rather than pretending to be alike.**
§37 is explicit about this. A share that cannot report per-item permissions
is a different thing from one that can, and the difference has to be
visible to the retrieval path rather than discovered when it returns
something it should not have.

``permission_ref`` points at the source's own authorization rather than
copying it. Copied permissions go stale, and §41 allows revalidation
against the source at retrieval time for sensitive systems — which is only
possible if the platform keeps the pointer.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.kernel.ids import EntityId, Name
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe


class KnowledgeSourceId(EntityId):
    """Identifies one connected source of organisational knowledge."""

    prefix = "ksrc"


class KnowledgeItemId(EntityId):
    """Identifies one item within a source."""

    prefix = "kitem"


class IndexingState(StrEnum):
    """Whether the platform can currently retrieve from this.

    ``STALE`` is distinct from ``INDEXED``: an index built before the source
    changed can still answer, but an administrator needs to know it is
    answering from an old view.
    """

    NOT_INDEXED = "not_indexed"
    INDEXING = "indexing"
    INDEXED = "indexed"
    STALE = "stale"
    FAILED = "failed"


@contract(kind="knowledge.source", version=1)
@dataclass(frozen=True, slots=True)
class KnowledgeSource(Contract):
    """One connected repository of organisational information."""

    source_id: KnowledgeSourceId = meaning("platform-minted identity of this source")
    display_name: str = meaning("name shown to an administrator")
    connector: Name = meaning("the connector adapter that reaches it")
    indexing_state: IndexingState = meaning(
        "whether it can currently be retrieved from"
    )
    capabilities: tuple[Name, ...] = meaning(
        "what this connector can actually do, so the retrieval path never "
        "assumes a capability the source lacks",
        default=(),
    )
    permission_model: Name | None = meaning(
        "how authorization for this source is determined", default=None
    )
    last_indexed_at: dt.datetime | None = meaning(
        "when the index was last rebuilt", default=None
    )


@contract(kind="knowledge.item", version=1)
@dataclass(frozen=True, slots=True)
class KnowledgeItem(Contract):
    """One piece of organisational information, as the platform sees it."""

    item_id: KnowledgeItemId = meaning("platform-minted identity of this item")
    source_id: KnowledgeSourceId = meaning("the source it came from")
    external_id: str = meaning("its identity in the source, kept verbatim")
    indexing_state: IndexingState = meaning("whether this item is retrievable")
    path: str | None = meaning(
        "location within the source, where the source has paths", default=None
    )
    media_type: Maybe[str] = meaning(
        "content type; unknown means unclassified, not plain text",
        default=NOT_PROVIDED,
    )
    version: Maybe[str] = meaning("source version identifier", default=NOT_PROVIDED)
    checksum: Maybe[str] = meaning(
        "content digest, where obtainable", default=NOT_PROVIDED
    )
    modified_at: Maybe[dt.datetime] = meaning(
        "when the source last changed it", default=NOT_PROVIDED
    )
    owner_ref: str | None = meaning(
        "who owns it in the source, by the source's own reference", default=None
    )
    permission_ref: str | None = meaning(
        "pointer to the source's authorization for this item, so permissions "
        "are revalidated rather than copied and left to go stale",
        default=None,
    )
    content_location: str | None = meaning(
        "where the content lives; a reference, because content need not be "
        "copied into the platform to be indexed",
        default=None,
    )
