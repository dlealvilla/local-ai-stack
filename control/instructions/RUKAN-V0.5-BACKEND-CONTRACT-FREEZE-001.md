# RUKAN v0.5 — BACKEND CONTRACT FREEZE BEFORE NATIVE WORKSPACE

Instruction ID: `RUKAN-V0.5-BACKEND-CONTRACT-FREEZE-001`
Status: `QUEUED_PHASE_1`

Starting branch tip / evidence:
`rukan/user-access-gateway-v0.4@7a0e6180a1e0d40e1d26271d590502d447d761a1`

Product-closure implementation source:
`7115852c984d8d5860bf29cdd49e2b42f61b12f7`

Canonical remains:
`machi@16084a5b21a0cca25bfe60070ad862832c80fb51`

This phase closes backend loose ends before the first-party Rukan Workspace is
allowed to treat the Employee Access APIs as stable product contracts.

No Docker/container runtime is part of the default product.

LibreChat is optional fallback and is NOT a blocker in this instruction.

Create working branch:

`rukan/native-workspace-v0.5`

from the current v0.4 branch tip so all v0.4 product and evidence history remains
reachable.

Do not rewrite v0.4 evidence commits.

---

# 1. ARCHITECTURE REVIEW

Before code, review:
- Product Vision;
- Architecture;
- Roadmap;
- current v0.4 Employee Access docs;
- Gateway;
- People/Directory;
- OIDC;
- credentials;
- canonical usage/projections;
- MCP;
- Admin;
- UI packaging;
- backup/migration;
- telemetry/privacy.

Create:

`docs/machi/RUKAN-V0.5-BACKEND-CONTRACT-FREEZE.md`

For each issue below specify:
- current repository truth;
- product expectation;
- authority;
- chosen correction;
- migration impact;
- failure behavior;
- test evidence.

Do not stop after the document.

---

# 2. IDENTITY PROVIDER CONFIGURATION MUST BECOME AUTHORITATIVE

Current defect:
Admin can persist identity-provider rows, while `gateway serve` still primarily
constructs the verifier from independent CLI issuer/audience arguments.

This creates two truths.

Fix the architecture.

## 2.1 Provider registry

Define one Rukan-owned provider registry.

Minimum provider contract:
- provider_id;
- label;
- issuer;
- audience;
- discovery URL / derived discovery;
- enabled;
- allowed algorithms;
- clock skew;
- CA/trust configuration reference;
- created/updated;
- last successful discovery;
- last JWKS refresh;
- last error category;
- config revision.

Persist in customer-local authoritative state.

Several providers may exist.
One default provider may be selected in v0.5 if multi-provider login UX is deferred.

## 2.2 Gateway / Workspace startup

Production startup should support:

`--provider-id <id>`

and load the authoritative stored provider.

Advanced explicit CLI issuer/audience/JWKS options may remain for:
- tests;
- recovery;
- expert/debug mode.

If override mode is used:
- clearly label it override;
- do not pretend Admin provider configuration is active;
- Admin/support projection shows configuration source.

Default product path:
Admin configuration -> stored provider -> Gateway/Workspace verifier.

## 2.3 Revision / live changes

Do not silently mutate a verifier in the middle of a request.

Simplest v0.5:
- provider config changes require Workspace/Gateway restart;
- Admin shows "restart required".

If safe live reload is easy, it may be implemented.

Do not build complex dynamic config watchers merely to avoid restart.

## 2.4 Tests

- saved provider drives production verifier;
- disabled provider refuses startup/login;
- unknown provider id;
- config update then restart;
- CLI explicit override;
- no secret/bearer logging;
- migration from current identity_providers table.

---

# 3. OIDC BROWSER AUTH FOUNDATION

The native Workspace needs a secure browser login.

Use OIDC Authorization Code + PKCE.

Do NOT implement OAuth cryptography/protocol manually.

Evaluate a mature Python OIDC/OAuth library and choose a bounded dependency.

Requirements:
- discovery from authoritative provider;
- authorization endpoint;
- token endpoint;
- PKCE S256;
- state;
- nonce where appropriate;
- issuer validation;
- ID/access token validation;
- audience/client validation;
- expiry/not-before;
- JWKS rotation through the existing production verifier/provider;
- bounded timeouts;
- explicit redirect URI.

## 3.1 Session architecture

Preferred:
- Workspace backend is BFF;
- access/refresh tokens do not go into browser localStorage;
- browser receives high-entropy opaque session cookie;
- HttpOnly;
- SameSite=Lax or stricter with documented login implications;
- Secure whenever TLS is active;
- path/domain scoped;
- session rotation after login;
- expiry bounded by identity/token lifetime.

For simplicity:
- OIDC tokens may remain memory-only in the Workspace server;
- a server restart may log users out;
- this is acceptable v0.5 behavior if documented.

Do not persist raw access/refresh tokens to SQLite merely to preserve sessions.

If token refresh is implemented:
- refresh token memory-only;
- refresh failure returns to login.

## 3.2 CSRF / Origin

Cookie-authenticated state-changing endpoints require:
- CSRF token or equivalent robust same-origin protection;
- Origin/Referer validation where applicable.

GET read endpoints remain side-effect free.

## 3.3 Rukan authorization

OIDC login establishes identity.

Every product operation still resolves current Rukan User/AccessContext.

A valid IdP session does not override:
- suspension;
- deactivation;
- inference denial;
- model denial;
- MCP denial;
- agent-builder denial.

Test suspend while browser session remains open:
next protected action is denied.

---

# 4. WORKSPACE SERVICE COMPOSITION

Create a first-class Rukan Workspace service.

Suggested:

`machi workspace serve`

or product-facing `rukan workspace serve` if CLI conventions support it without
namespace migration.

It should compose:
- static Rukan Workspace assets;
- browser OIDC/session endpoints;
- Workspace conversation APIs;
- Rukan User Gateway service/API;
- Workspace MCP host/client APIs;
- Agent APIs later in Phase 3.

Default employee service should be one coherent process where practical.

Do not require administrators to separately launch:
- Gateway;
- Workspace frontend backend;
- an auth helper.

Headless `gateway serve` remains available for API-only deployments.

## 4.1 Network authority

Workspace never exposes:
- vLLM port;
- Serve port;
- reservation;
- executable path.

Browser talks to Rukan Workspace only.

Generic API clients talk to Rukan Gateway `/v1`.

---

# 5. STABLE API CONTRACT / VERSIONING

Freeze an employee-facing API version.

Keep:
- `GET /v1/version`
- `GET /v1/models`
- `POST /v1/chat/completions`
- `GET /v1/me`
- `GET /v1/me/usage`

Workspace-specific routes should use a clear namespace such as:

`/api/workspace/v1/*`

Do not mix admin-only routes into employee APIs.

Add:
- API schema/version constant;
- build id;
- capability profile.

Workspace frontend checks compatible API version at startup.

---

# 6. REAL EMPLOYEE ACCESS PREFLIGHT

Replace shallow placeholder checks.

Preflight must be non-mutating.

Required checks:

## State
- install identity;
- People store readable;
- Gateway/workspace DB readable/writable;
- migration state current;
- static Workspace assets present.

## Identity
- enabled provider exists;
- issuer/audience valid;
- discovery reachable;
- discovery issuer matches;
- JWKS reachable;
- current keys parse;
- token endpoint present for browser login;
- authorization endpoint present.

## Network/TLS
- configured bind valid;
- cert/key exist when direct TLS selected;
- key permissions reasonable;
- cert parses;
- no TLS placeholder PASS;
- trusted proxy config parses.

## Inference
- current READY authorized serving instance exists;
- model list projection available;
- direct Serve endpoint remains hidden.

## MCP
- catalog readable;
- approved endpoints syntactically valid;
- optional connectivity check only when requested because preflight should not
  unexpectedly call external tools.

## Workspace
- UI manifest/assets;
- session configuration;
- API compatibility.

Output:
- overall PASS/BLOCKED;
- per-check code;
- human explanation;
- remediation;
- JSON-safe evidence;
- no secrets.

Tests for every blocked state.

---

# 7. SQLITE BACKUP / RESTORE MUST BE CONSISTENT

Current raw live file copies are insufficient as the final product contract.

Choose one simple robust approach.

Preferred:
- SQLite backup API from read connection into destination;
- one database at a time;
- manifest records schema/version/timestamp/install id;
- refuse active restore while services hold write authority unless safe orchestration
  stops them.

Alternative:
- explicitly stop affected services;
- WAL checkpoint;
- copy;
- verify.

Do not naïvely copy a live WAL-mode DB.

## 7.1 Scope

Include:
- directory/People;
- Gateway canonical usage;
- telemetry/accounting state required locally;
- Workspace content DB once added;
- agents/MCP catalog if separate;
- product settings/provider configuration.

Exclude:
- raw OIDC tokens;
- API credential plaintext secrets;
- telemetry machine bearer secret unless the existing broader backup policy
  explicitly handles it separately.

## 7.2 Restore

Restore only into:
- stopped services;
- compatible install/schema;
- explicit target root.

After restore:
- migrations/reconciliation;
- People works;
- bindings work;
- usage totals preserved;
- conversation/agents later preserved;
- projections reconcile.

Tests:
- WAL activity;
- backup during ordinary DB state;
- corrupt/incomplete backup;
- wrong manifest/install;
- restore;
- restart.

---

# 8. MCP TRANSPORT CORRECTION

Current custom URL pinning rewrites an HTTPS hostname to an IP. That risks breaking
Host/SNI/certificate hostname validation.

Do not preserve this implementation merely because it blocks DNS rebinding.

Phase 3 will adopt the official MCP SDK.

In this phase, define the transport policy that the SDK adapter must satisfy.

For admin-approved MCP endpoints:
- preserve original hostname;
- TLS certificate validates original hostname;
- SNI is original hostname;
- redirects disabled by default;
- connection-time DNS resolution checked against policy;
- metadata/link-local/multicast/unspecified forbidden;
- admin-approved private addresses allowed;
- arbitrary user endpoints disabled by default.

If robust IP-pinned TLS transport is straightforward using the chosen HTTP client:
- validate DNS;
- connect to validated IP;
- preserve original Host/SNI/hostname verification.

If not:
- because only administrator-approved endpoints exist in the default product,
  use standard secure TLS hostname connection;
- validate DNS immediately before connection;
- reject dangerous resolved addresses;
- disable redirects;
- revalidate each new connection;
- document residual DNS-rebinding risk as defense-in-depth debt;
- do NOT weaken TLS to close it.

Remove any approach that breaks normal HTTPS.

---

# 9. CONCURRENCY / REQUEST LIMITS

Freeze simple product behavior.

Gateway:
- max global concurrent;
- max per-user concurrent;
- no unbounded queue;
- request body cap;
- message count/content cap;
- max_tokens cap;
- streaming timeout;
- upstream timeout.

Derive safe default global bound from current serving instance/runtime where possible.

If derivation not clean:
- conservative bounded default;
- Admin may lower;
- advanced override validated.

Tests:
- limit reached;
- stream cancel frees slot;
- upstream error frees slot;
- Workspace session disconnect frees slot.

---

# 10. ERROR CONTRACT

Normalize client-safe codes.

Required:
- authentication_required;
- session_expired;
- identity_not_provisioned;
- identity_binding_conflict;
- user_suspended;
- platform_access_denied;
- inference_access_denied;
- model_not_allowed;
- no_ready_model;
- scope_denied;
- overloaded;
- upstream_failure;
- accounting_degraded;
- mcp_access_denied;
- mcp_target_denied;
- mcp_upstream_failed;
- workspace_conflict;
- conversation_not_found;
- agent_not_found.

Document HTTP mapping and retryability.

No internal traceback/path in client response.

---

# 11. ADMIN PRODUCT SURFACE FOR EMPLOYEE ACCESS

Before Workspace launch, finish the minimum Admin controls required to operate it.

Add coherent Admin screens/sections using existing React/Vite conventions.

Required:
- Identity Provider;
- User Gateway / Workspace;
- MCP Catalog;
- User Analytics/reconciliation.

## Identity Provider
- provider rows;
- active provider;
- issuer;
- audience;
- discovery URL;
- status;
- last discovery/JWKS refresh;
- edit/save;
- restart-required notice.

## Workspace
- default client = Rukan Workspace;
- service status;
- bind/URL;
- TLS mode;
- API version;
- fallback LibreChat = optional/unconfigured by default.

## MCP
- approved servers;
- add/edit/disable;
- auth mode metadata;
- connectivity test;
- last status.

## Analytics
- users;
- requests;
- input/output/total tokens;
- token coverage;
- reconciliation state.

Do not overload Overview.

---

# 12. LIBRECHAT FALLBACK POLICY

Remove LibreChat physical execution from core closure requirements.

Keep:
- LibreChatAdapter code;
- pinned compatibility metadata;
- config generation.

Mark:
- optional fallback;
- unqualified physical compatibility until later tested;
- not default.

Do not delete it.

Do not spend Docker disk or cloud time validating it in the core closure campaign.

---

# 13. LOCAL TEST GATE

Before Phase 2:

Backend:
- provider authority;
- OIDC browser auth fixture;
- state/nonce/PKCE;
- session cookie;
- CSRF;
- user suspension during session;
- preflight failure matrix;
- backup/WAL/restore;
- API version;
- error mappings;
- concurrency cleanup;
- MCP transport TLS policy.

Admin:
- Identity page;
- Workspace page;
- MCP page;
- Analytics;
- Vitest;
- typecheck;
- build.

Full:
- tests/machi;
- acceptance_lab;
- ruff;
- strict mypy;
- existing UI suites;
- wheel build;
- clean artifact install.

Record exact source.

---

# 14. PHASE 1 PASS

Return internal gate:

`RUKAN_V0_5_BACKEND_CONTRACT_FREEZE_PASS`

Only if:
- authoritative provider config works;
- browser OIDC/session foundation works;
- real preflight;
- consistent backup;
- sane MCP HTTPS policy;
- Admin operating surfaces;
- stable API/error contract;
- all local QA passes.

Then continue automatically to:

`RUKAN-V0.5-NATIVE-WORKSPACE-001`

Do not stop for Lead review.

If not:
`RUKAN_V0_5_BACKEND_CONTRACT_FREEZE_NOT_READY`
and only stop for a real unresolved architectural/safety blocker.

# END PHASE 1
