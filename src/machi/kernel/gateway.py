"""Employee gateway contracts. LibreChat is not an authority here."""

from __future__ import annotations

from dataclasses import dataclass

from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning

NOT_RECORDED = "not_recorded"
BINDING_STATUSES = frozenset({"bound", "mismatch", "reset"})
CREDENTIAL_STATUSES = frozenset({"active", "revoked", "expired"})
SCOPES = frozenset({"inference", "models", "self_usage"})
MCP_TRANSPORTS = frozenset({"streamable_http"})
AGENT_AUTHORITY = "rukan"
_TOKEN_MAX = 500


def _token(label: str, value: str) -> None:
    if (
        not value
        or len(value) > _TOKEN_MAX
        or any(char in value for char in "\n\r\x00")
    ):
        raise ValidationError(f"gateway {label} is empty or unsafe")


@contract(kind="kernel.identity_binding", version=1)
@dataclass(frozen=True, slots=True)
class IdentityBinding(Contract):
    """Issuer and subject identify a user after the first approved bind."""

    binding_id: str = meaning("platform-minted binding id")
    user_id: str = meaning("Rukan user")
    provider_kind: str = meaning("oidc")
    issuer: str = meaning("configured issuer")
    subject_fingerprint: str = meaning("sha256 of the external subject")
    email_seen: str = meaning("approved email observed at binding")
    status: str = meaning("bound, mismatch, or reset")
    created_at: str = meaning("UTC")
    updated_at: str = meaning("UTC")

    def __post_init__(self) -> None:
        if self.provider_kind != "oidc":
            raise ValidationError("gateway identity provider is unknown")
        if self.status not in BINDING_STATUSES:
            raise ValidationError("gateway binding status is unknown")
        for label, value in (
            ("binding", self.binding_id),
            ("user", self.user_id),
            ("issuer", self.issuer),
            ("subject", self.subject_fingerprint),
            ("email", self.email_seen),
        ):
            _token(label, value)


@contract(kind="kernel.api_credential", version=1)
@dataclass(frozen=True, slots=True)
class ApiCredentialMetadata(Contract):
    """Public credential facts. The secret is not a field."""

    key_id: str = meaning("credential id")
    user_id: str = meaning("owning user")
    scopes: tuple[str, ...] = meaning("inference, models, self_usage")
    client_label: str = meaning("application label")
    issued_at: str = meaning("UTC")
    expires_at: str = meaning("UTC")
    revoked_at: str = meaning("UTC, or not_recorded")
    status: str = meaning("active, revoked, or expired")
    last_used_at: str = meaning("UTC, or not_recorded")

    def __post_init__(self) -> None:
        if self.status not in CREDENTIAL_STATUSES:
            raise ValidationError("gateway credential status is unknown")
        if not self.scopes or any(item not in SCOPES for item in self.scopes):
            raise ValidationError("gateway credential scope is unknown")
        for label, value in (
            ("key", self.key_id),
            ("user", self.user_id),
            ("label", self.client_label),
            ("issued", self.issued_at),
            ("expires", self.expires_at),
            ("revoked", self.revoked_at),
            ("used", self.last_used_at),
        ):
            _token(label, value)


@contract(kind="kernel.principal_usage", version=1)
@dataclass(frozen=True, slots=True)
class PrincipalUsage(Contract):
    """One employee request. Text is not a field."""

    usage_id: str = meaning("same id as the deployment usage row")
    request_id: str = meaning("gateway request id")
    user_id: str = meaning("exactly one Rukan user")
    accounting_team_id: str = meaning("one team context, or unassigned")
    client_id: str = meaning("workspace or generic client")
    auth_method: str = meaning("oidc or api_credential")
    model_identity: str = meaning("public model id")
    macropath: str = meaning("runtime family")
    instance_id: str = meaning("serving instance")
    input_tokens: str = meaning("reported input tokens, or not_recorded")
    output_tokens: str = meaning("reported output tokens, or not_recorded")
    latency_ms: str = meaning("boundary latency")
    outcome: str = meaning("completed or failed")
    occurred_at: str = meaning("UTC")

    def __post_init__(self) -> None:
        if self.auth_method not in {"oidc", "api_credential"}:
            raise ValidationError("gateway auth method is unknown")
        if self.outcome not in {"completed", "failed"}:
            raise ValidationError("gateway usage outcome is unknown")
        for label, value in (
            ("usage", self.usage_id),
            ("request", self.request_id),
            ("user", self.user_id),
            ("team", self.accounting_team_id),
            ("client", self.client_id),
            ("model", self.model_identity),
            ("runtime", self.macropath),
            ("instance", self.instance_id),
            ("occurred", self.occurred_at),
        ):
            _token(label, value)
        for label, value in (
            ("input tokens", self.input_tokens),
            ("output tokens", self.output_tokens),
            ("latency", self.latency_ms),
        ):
            if value != NOT_RECORDED and not value.isdigit():
                raise ValidationError(f"gateway {label} is not a count")


@contract(kind="kernel.mcp_server", version=1)
@dataclass(frozen=True, slots=True)
class McpServerDefinition(Contract):
    """Approved tool server. Credentials are not stored on this record."""

    server_id: str = meaning("stable server id")
    display_name: str = meaning("admin label")
    transport: str = meaning("streamable_http")
    endpoint: str = meaning("approved endpoint")
    approved: bool = meaning("administrator approval")
    auth_method: str = meaning("none or per_user_bearer")
    sensitivity: str = meaning("category label")
    created_at: str = meaning("UTC")
    updated_at: str = meaning("UTC")

    def __post_init__(self) -> None:
        if self.transport not in MCP_TRANSPORTS:
            raise ValidationError("mcp transport is unknown")
        if self.auth_method not in {"none", "per_user_bearer"}:
            raise ValidationError("mcp auth method is unknown")
        for label, value in (
            ("server", self.server_id),
            ("name", self.display_name),
            ("endpoint", self.endpoint),
            ("sensitivity", self.sensitivity),
            ("created", self.created_at),
            ("updated", self.updated_at),
        ):
            _token(label, value)


@contract(kind="kernel.agent_definition", version=1)
@dataclass(frozen=True, slots=True)
class AgentDefinition(Contract):
    """Rukan-owned agent seam. A workspace client is not the source of truth."""

    agent_id: str = meaning("stable agent id")
    owner_user_id: str = meaning("owning user")
    accounting_team_id: str = meaning("one team context, or unassigned")
    display_name: str = meaning("label")
    revision: int = meaning("monotonic revision")
    instruction_ref: str = meaning("reference, not instruction text")
    model_policy: str = meaning("model constraint")
    mcp_server_ids: tuple[str, ...] = meaning("approved server ids")
    status: str = meaning("active or retired")
    authority: str = meaning("rukan")
    created_at: str = meaning("UTC")
    updated_at: str = meaning("UTC")

    def __post_init__(self) -> None:
        if self.authority != AGENT_AUTHORITY:
            raise ValidationError("agent authority must stay with Rukan")
        if self.status not in {"active", "retired"}:
            raise ValidationError("agent status is unknown")
        if self.revision < 1:
            raise ValidationError("agent revision must be positive")
        for label, value in (
            ("agent", self.agent_id),
            ("owner", self.owner_user_id),
            ("team", self.accounting_team_id),
            ("name", self.display_name),
            ("instructions", self.instruction_ref),
            ("model", self.model_policy),
            ("created", self.created_at),
            ("updated", self.updated_at),
        ):
            _token(label, value)
