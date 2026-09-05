"""Adaptation, and the provenance that makes it governable.

One rule shapes both contracts here. `docs/PRODUCT_VISION.md` §76:
**permission to retrieve knowledge does not imply permission to train on
it.** A dataset snapshot therefore records training authorization
explicitly, as its own fact, rather than letting it be inferred from the
fact that someone could read the material.

That is why `training_authorized` is a plain boolean while almost
everything else in these contracts is optional or unknown. An unknown
authorization is not an authorization, and making the field unresolvable
would invite exactly that reading.

`DerivedModel` exists so that a LoRA adapter can be represented as what it
is — a modification of a parent at a revision — rather than as an
independent base model. §75 asks for lineage; without a parent reference
and a derivation type, a promoted adapter becomes indistinguishable from a
model that arrived from a source, and rollback stops being possible.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.identity.contracts import SubjectId, TeamId
from kultrun.kernel.ids import EntityId
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe
from kultrun.model.contracts import DerivationType, ModelId


class DatasetSnapshotId(EntityId):
    """Identifies one immutable set of training material."""

    prefix = "dset"


class DerivedModelId(EntityId):
    """Identifies one model produced from another."""

    prefix = "deriv"


class PromotionState(StrEnum):
    """How far a derived model has progressed toward serving traffic."""

    DRAFT = "draft"
    EVALUATING = "evaluating"
    APPROVED = "approved"
    PRODUCTION = "production"
    DEPRECATED = "deprecated"


@contract(kind="training.dataset_snapshot", version=1)
@dataclass(frozen=True, slots=True)
class DatasetSnapshot(Contract):
    """An immutable, explicitly authorized set of training material."""

    snapshot_id: DatasetSnapshotId = meaning("platform-minted identity of this set")
    created_at: dt.datetime = meaning("when it was captured, UTC")
    training_authorized: bool = meaning(
        "explicit permission to train on this material; never inferred from "
        "permission to read it"
    )
    authorized_by: SubjectId | None = meaning(
        "who granted that permission", default=None
    )
    scope_team_id: TeamId | None = meaning(
        "the team whose material this is, which bounds what may be derived "
        "from it",
        default=None,
    )
    provenance_refs: tuple[str, ...] = meaning(
        "where the material came from, by identifier, so a derived model's "
        "sources remain traceable",
        default=(),
    )
    retention_days: Maybe[int] = meaning(
        "how long the material may be kept", default=NOT_PROVIDED
    )


@contract(kind="training.derived_model", version=1)
@dataclass(frozen=True, slots=True)
class DerivedModel(Contract):
    """A model produced from a parent, with its lineage intact."""

    derived_id: DerivedModelId = meaning("platform-minted identity of this derivative")
    parent_model_id: ModelId = meaning("the model it was derived from")
    derivation_type: DerivationType = meaning(
        "how it was derived; an adapter is not a base model"
    )
    promotion_state: PromotionState = meaning("how far it has progressed")
    created_at: dt.datetime = meaning("when it was produced, UTC")
    parent_revision: Maybe[str] = meaning(
        "the parent revision it was derived from; without this the "
        "derivation is not reproducible",
        default=NOT_PROVIDED,
    )
    snapshot_id: DatasetSnapshotId | None = meaning(
        "the training material used, for derivations that used any",
        default=None,
    )
    owner_team_id: TeamId | None = meaning(
        "the team it belongs to", default=None
    )
