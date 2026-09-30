# Rukan v0.4 employee access product closure

The employee plane is the User Gateway. LibreChat is a replaceable workspace
adapter and a pre-release compatibility target, not a Rukan dependency.

## Identity

Several identity providers may be stored. One may be enabled. Users do not
carry a hardcoded issuer. Approved email provisions the user. After binding,
issuer and subject are the external identity. An email change does not retarget
the subject. Admin reset allows a new subject to bind. A different subject
cannot take over a bound email.

## Gateway

Supported subset: `GET /v1/models`, `POST /v1/chat/completions`, `GET /v1/me`,
`GET /v1/me/usage`, and `GET /v1/version`. Streaming forwards deltas as they
arrive. `GET /v1/version` names the subset and does not require a bearer.

Bind and TLS are startup configuration. Invalid TLS material fails startup.
Untrusted peers cannot supply `X-Forwarded-For`, `X-Real-IP`, or `Forwarded`.
Those headers are never identity.

Employees cannot acquire, deploy, stop, or release. Model listing and chat
both require inference and model-selection permission.

## Credentials

Secrets are shown once and stored as scrypt hashes. Lifetime is at least 60
seconds and at most 365 days. There is no non-expiring credential. Scopes are
`models`, `inference`, `self_usage`, and `mcp`. A scope cannot exceed People
access. The user may revoke their own credential. Suspend and deactivate make
every credential fail immediately.

Client analytics names are `librechat`, `generic_api`, and
`rukan_future_workspace`. Any other label becomes `generic_api`.

## Usage

One `gateway_events` row is canonical. Telemetry is an idempotent projection.
Reconciliation states are `match`, `projection_pending`,
`partial_token_coverage`, `degraded`, and `mismatch`. Unknown token counts do
not become estimates. The accounting team is the earliest active membership,
or `unassigned`. That rule is provisional and does not double-count.

## Workspace and MCP

Managed mode renders a digest-pinned LibreChat compose file. External mode is
the same config without Rukan owning the process. Supported LibreChat target
is only `v0.8.8-rc4`. A different version fails the adapter check. There is no
automatic upgrade.

MCP catalog entries can be approved. User-created servers stay off unless
`mcp_connect` is allowed. The broker does not forward the employee's OIDC
token to an arbitrary tool server. Redirects are refused. The connection uses
the address that was classified. Metadata and link-local targets are refused.
A down tool server does not stop ordinary inference.

## Operations

Preflight is read-only. Backup copies the people, gateway, and telemetry
ledgers and not the machine telemetry secret. Restore copies those files back.
A corrupt directory fails access closed because the gateway cannot resolve a
user. A missed telemetry projection is retried from the canonical event.

## Native workspace

Do not build it in this closure. The first increment, after physical
confidence, should be a thin client of the gateway subset above: chat,
streaming, My Usage, model list, and connections.
