# Rukan v0.5 backend contract freeze

Status: `RUKAN_V0_5_BACKEND_CONTRACT_FREEZE_PASS` for the local
contract. This note does not claim a physical product closure.

## Authority

The enabled identity-provider row is what production startup loads.
`machi workspace serve --provider-id primary` and
`machi gateway serve --provider-id primary` build the verifier from
that row. Passing `--issuer` or `--audience` or `--jwks` is a CLI
override. The process prints `identity stored_provider` or
`identity cli_override`. It does not pretend an Admin edit is live.
Changing a provider requires a restart. There is no watcher.

OIDC signatures stay on PyJWT. The browser login is Authorization
Code with PKCE S256: the verifier is a random string, the challenge
is SHA-256 as in RFC 7636, and the token endpoint is a form POST.
The ID token is checked by the existing discovery verifier. Authlib
was not added. Its sync client would pull a second HTTP stack, and
the cryptographic check is already PyJWT.

## Session

`machi workspace serve` is one process. It serves the packaged
Workspace UI, `/api/workspace/v1/*`, and the headless `/v1/*` gateway.
The browser gets an opaque `rukan_session` cookie: HttpOnly,
SameSite=Lax, Secure only when TLS is configured. Access and refresh
tokens are not stored in the browser or in SQLite. The in-memory
PKCE state is dropped on restart, so an in-flight login must start
again. A session that is already open ends at its expiry or when the
user is no longer active. The next call after suspension is
`user_suspended`. Mutating cookie routes require `X-Rukan-CSRF` and
reject a foreign `Origin`.

Headless `gateway serve` remains for API credentials. It does not
admit, and it does not publish the Serve port.

## Employee API

Unauthenticated: `GET /v1/version`.

Authenticated: `GET /v1/models`, `POST /v1/chat/completions`,
`GET /v1/me`, `GET /v1/me/usage`.

Workspace routes live under `/api/workspace/v1/`: login, callback,
logout, me, conversations, messages, stop, regenerate, usage,
credentials, tools, and agents.

Customer conversation text is in `workspace.sqlite` on the customer
host. It is included in the employee backup. It is not vendor
telemetry and it is not a Command Center report.

## Preflight and backup

`employee_preflight` is non-mutating. It checks the people store, the
usage store, an enabled provider, discovery issuer match, the
authorize and token endpoints, JWKS, packaged workspace assets, and
whether the projected serving instance is READY. A missing model does
not start one. TLS material is not invented.

Backup and restore use the SQLite backup API and write
`manifest.json`. They do not copy a live WAL file with `shutil`.

## MCP

DNS is checked immediately before connect. The original hostname is
kept so HTTPS SNI still matches. Redirects are refused. That does
not close `R-04-01`: a name can still change address in the gap, and
this version does not pin the socket to the address it classified.

The official Python MCP SDK (`mcp>=1.30,<2`) is the host library for
tool listing and manual tool calls against a streamable HTTP server.
`mcp_host.serve_acceptance` is the deterministic ping server. The
automatic tool loop still uses the JSON broker when the model emits
a `tool_call` event. A prompt is not parsed into a fake tool call.
Rukan policy remains the authority for which server may be called.

## Errors

Public codes include `session_expired`, `scope_denied`,
`conversation_not_found`, `agent_not_found`, `workspace_conflict`,
`mcp_access_denied`, `mcp_target_denied`, `mcp_unavailable`, and
`mcp_upstream_failed`.

## Not in this freeze

LibreChat is an optional fallback adapter. It is not on the
acceptance path. Docker is not a product dependency. RAG, images,
audio, channels, a plugin marketplace, SCIM, and learned memory are
out of this version.
