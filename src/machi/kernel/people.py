"""Customer-local directory contracts. Not authentication and not vendor telemetry."""

from __future__ import annotations

from dataclasses import dataclass

from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning

USER_STATUSES = frozenset({"active", "suspended", "deactivated"})
TEAM_STATUSES = frozenset({"active", "archived"})
ACCESS = frozenset({"allow", "deny", "inherit"})
GRANTS = frozenset({"allow", "deny"})
SUBJECTS = frozenset({"user", "team"})
ENFORCEMENT = "rukan_user_gateway"
CAPABILITIES = (
    "platform_access",
    "inference_access",
    "model_selection",
    "agent_builder",
    "agent_use",
    "api_credential",
    "workspace",
    "mcp_use",
    "mcp_connect",
)
_TOKEN_MAX = 240


@contract(kind="kernel.directory_user", version=1)
@dataclass(frozen=True, slots=True)
class DirectoryUser(Contract):
    """One local person. Email stays on the customer host."""

    user_id: str = meaning("platform-minted user id")
    email_normalized: str = meaning("lowercase email used for uniqueness")
    email_display: str = meaning("email as entered")
    display_name: str = meaning("name shown in Admin")
    status: str = meaning("active, suspended, or deactivated")
    created_at: str = meaning("UTC")
    updated_at: str = meaning("UTC")
    external_ref: str = meaning("future IdP reference, or not_recorded")
    actor_origin: str = meaning("who recorded the last change")

    def __post_init__(self) -> None:
        if self.status not in USER_STATUSES:
            raise ValidationError("directory user status is unknown")
        _text("user", self.user_id)
        _text("email", self.email_normalized)
        _text("name", self.display_name)


@contract(kind="kernel.directory_team", version=1)
@dataclass(frozen=True, slots=True)
class DirectoryTeam(Contract):
    """A team id is authoritative. The name is not."""

    team_id: str = meaning("platform-minted team id")
    name: str = meaning("admin label")
    description: str = meaning("optional description, or empty")
    status: str = meaning("active or archived")
    created_at: str = meaning("UTC")
    updated_at: str = meaning("UTC")

    def __post_init__(self) -> None:
        if self.status not in TEAM_STATUSES:
            raise ValidationError("directory team status is unknown")
        _text("team", self.team_id)
        _text("team name", self.name)


@contract(kind="kernel.directory_membership", version=1)
@dataclass(frozen=True, slots=True)
class DirectoryMembership(Contract):
    """An explicit user-team link. Nothing is inferred from an email domain."""

    user_id: str = meaning("user")
    team_id: str = meaning("team")
    active: bool = meaning("whether the membership is current")
    created_at: str = meaning("UTC")
    actor_origin: str = meaning("who recorded the membership")

    def __post_init__(self) -> None:
        _text("user", self.user_id)
        _text("team", self.team_id)


@contract(kind="kernel.access_intent", version=1)
@dataclass(frozen=True, slots=True)
class AccessIntent(Contract):
    """Future gateway configuration. It does not authenticate anyone."""

    subject_kind: str = meaning("user or team")
    subject_id: str = meaning("user id or team id")
    platform_access: str = meaning("allow or deny")
    inference_access: str = meaning("allow or deny")
    model_selection: str = meaning("allow or deny")
    agent_builder: str = meaning("allow or deny")
    updated_at: str = meaning("UTC")
    agent_use: str = meaning("allow, deny, or inherit", default="inherit")
    api_credential: str = meaning("allow, deny, or inherit", default="inherit")
    workspace: str = meaning("allow, deny, or inherit", default="inherit")
    mcp_use: str = meaning("allow, deny, or inherit", default="inherit")
    mcp_connect: str = meaning("allow, deny, or inherit", default="inherit")

    def __post_init__(self) -> None:
        if self.subject_kind not in SUBJECTS:
            raise ValidationError("access intent subject is unknown")
        allowed = ACCESS if self.subject_kind == "user" else GRANTS
        for label, value in (
            ("platform", self.platform_access),
            ("inference", self.inference_access),
            ("model selection", self.model_selection),
            ("agent builder", self.agent_builder),
            ("agent use", self.agent_use),
            ("api credential", self.api_credential),
            ("workspace", self.workspace),
            ("mcp use", self.mcp_use),
            ("mcp connect", self.mcp_connect),
        ):
            if value not in allowed:
                raise ValidationError(f"access intent {label} is unknown")


@contract(kind="kernel.effective_access", version=1)
@dataclass(frozen=True, slots=True)
class EffectiveAccess(Contract):
    """Resolved future access. Enforcement is not available in this version."""

    user_id: str = meaning("user")
    status: str = meaning("directory status")
    team_ids: tuple[str, ...] = meaning("active team memberships")
    platform_access: str = meaning("effective allow or deny")
    inference_access: str = meaning("effective allow or deny")
    model_selection: str = meaning("effective allow or deny")
    agent_builder: str = meaning("effective allow or deny")
    platform_provenance: str = meaning("rule for platform access")
    inference_provenance: str = meaning("rule for inference access")
    model_selection_provenance: str = meaning("rule for model selection")
    agent_builder_provenance: str = meaning("rule for agent builder")
    configured: bool = meaning("the directory can express intent")
    enforcement: str = meaning("rukan_user_gateway enforces employee access")
    agent_use: str = meaning("effective allow or deny", default="deny")
    api_credential: str = meaning("effective allow or deny", default="deny")
    workspace: str = meaning("effective allow or deny", default="deny")
    mcp_use: str = meaning("effective allow or deny", default="deny")
    mcp_connect: str = meaning("effective allow or deny", default="deny")
    agent_use_provenance: str = meaning("rule for agent use", default="default_deny")
    api_credential_provenance: str = meaning(
        "rule for api credentials", default="default_deny"
    )
    workspace_provenance: str = meaning("rule for workspace", default="default_deny")
    mcp_use_provenance: str = meaning("rule for mcp use", default="default_deny")
    mcp_connect_provenance: str = meaning(
        "rule for mcp connections", default="default_deny"
    )

    def __post_init__(self) -> None:
        if self.enforcement != ENFORCEMENT:
            raise ValidationError("employee gateway enforcement is not available")
        _text("user", self.user_id)


def _text(label: str, value: str) -> None:
    if not value or len(value) > _TOKEN_MAX or any(char in value for char in "\n\r\x00"):  # noqa: E501
        raise ValidationError(f"directory {label} is empty or unsafe")
