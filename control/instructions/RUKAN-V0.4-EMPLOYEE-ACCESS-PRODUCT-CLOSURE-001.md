# RUKAN v0.4 — EMPLOYEE ACCESS PRODUCT CLOSURE

Instruction ID: `RUKAN-V0.4-EMPLOYEE-ACCESS-PRODUCT-CLOSURE-001`
Status: `QUEUED_AFTER_GATEWAY_HARDENING_PASS`

This instruction begins ONLY after:

`RUKAN-V0.4-GATEWAY-HARDENING-AND-CAMPAIGN-CONTINUE-001`

has genuinely passed its required local and physical gates.

The purpose of this phase is broader than closing a few defects.

It must turn the current v0.4 employee-access implementation into a coherent,
supportable, enterprise-compatible product subsystem that can become the stable
backend contract for the next planned product increment:

> first-party Rukan Workspace / chat frontend.

This phase MUST NOT build the full first-party Workspace yet.

It MUST make the employee-access backend sufficiently complete that the next
frontend can be implemented primarily as a client of stable Rukan-owned APIs,
without forcing another redesign of identity, usage, policy, MCP, model routing,
credentials, or Workspace adapters.

---

# 0. PRODUCT OUTCOME

At the end of this phase, an organisation administrator should be able to:

1. install/start Rukan;
2. deploy one or more supported models;
3. create/provision users and teams;
4. configure enterprise OIDC;
5. grant/deny user capabilities;
6. expose a Rukan User Gateway through the customer’s chosen enterprise network;
7. connect LibreChat through the adapter OR connect another OpenAI-compatible client;
8. issue/revoke Rukan API credentials where policy permits;
9. allow/deny MCP servers and MCP use;
10. see exact per-user requests and token usage;
11. reconcile those totals to deployment employee usage;
12. suspend a user and have all access stop immediately;
13. rotate IdP signing keys without product intervention;
14. restart services without losing identity/accounting/policy truth;
15. upgrade from accepted v0.3/v0.4 schemas without destructive reset;
16. diagnose common failures through Admin;
17. use the product behind ordinary enterprise security controls;
18. replace LibreChat later without changing the backend architecture.

The product should NOT require the administrator to understand:
- vLLM ports;
- reservation ids;
- SQLite;
- JWKS internals;
- MCP JSON-RPC;
- LibreChat database internals.

The technical system may expose those details under advanced/support views, but
the primary product experience is business-admin oriented.

---

# 1. PRODUCT PRINCIPLES

The following principles are binding.

## 1.1 Rukan owns product meaning

Rukan owns:
- User identity binding state;
- Teams;
- effective access;
- Gateway authorization;
- model-access policy;
- usage accounting;
- API credentials;
- MCP catalog/policy;
- Workspace adapter selection/capability profile;
- employee-access audit;
- support/readiness state.

Adapters own:
- OIDC implementation mechanics;
- LibreChat configuration;
- MCP transport mechanics;
- runtime/provider-specific execution.

## 1.2 LibreChat is replaceable

LibreChat must remain:
- one Workspace adapter;
- not identity authority;
- not usage authority;
- not access authority;
- not MCP policy authority;
- not canonical Agent authority.

Replacing LibreChat with a future first-party Rukan Workspace must not require
schema or policy migration for:
- Users;
- Teams;
- identity bindings;
- Gateway;
- API credentials;
- principal usage;
- MCP definitions;
- employee model access.

## 1.3 Enterprise-compatible, not enterprise-security replacement

Rukan is designed to sit behind:
- private networks;
- VLANs;
- VPN;
- ZTNA;
- reverse proxies;
- customer load balancers;
- WAF;
- enterprise PKI;
- Entra/Okta/Keycloak/etc.;
- SIEM/logging.

Rukan does NOT attempt to replace those systems.

## 1.4 Content privacy by architecture

Rukan operational/accounting systems do not persist:
- prompt text;
- response text;
- MCP tool payloads;
- OAuth access tokens;
- chat histories.

Workspace clients may have their own content stores; that is a separate customer
data boundary and must be documented truthfully.

## 1.5 Stable IDs over display attributes

Authorization and usage are bound to:
- Rukan user id;
- issuer + subject external identity;
- stable team ids.

Never authorize based on:
- display name;
- raw email header alone;
- LibreChat internal user id;
- client-supplied team name.

---

# 2. REQUIRED ARCHITECTURE DOCUMENT

Create/update:

`docs/machi/RUKAN-EMPLOYEE-ACCESS-PRODUCT-CLOSURE-V0.4.md`

This document must become the authoritative technical product architecture for
employee access.

For every major component include:
- purpose;
- authority;
- trusted inputs;
- untrusted inputs;
- outputs;
- persistence;
- network surface;
- secret handling;
- PII handling;
- restart/recovery;
- migrations;
- failure modes;
- audit;
- UI projection;
- test evidence;
- deferred work.

Components:
1. People;
2. Teams;
3. Memberships;
4. AccessIntent;
5. EffectiveAccess;
6. IdentityBinding;
7. OIDC verifier/provider;
8. API credentials;
9. User Gateway;
10. Gateway usage source-of-truth;
11. per-user analytics;
12. employee deployment totals;
13. WorkspaceAdapter;
14. LibreChatAdapter;
15. MCP catalog;
16. MCP broker/policy;
17. Admin employee-access surfaces;
18. user self-service/My Usage;
19. Gateway service lifecycle;
20. reverse-proxy/TLS boundary;
21. migrations/upgrade;
22. support evidence;
23. telemetry/vendor boundary.

Include a dependency/authority graph.

---

# 3. USER LIFECYCLE — COMPLETE PRODUCT MODEL

Audit and close the complete lifecycle.

States:
- active;
- suspended;
- deactivated.

Required semantics:

## Active
May authenticate if external identity valid and Rukan policy allows.

## Suspended
- all Gateway inference denied;
- API credentials denied immediately;
- MCP denied;
- Workspace capability considered denied by Rukan;
- existing identity binding retained;
- usage/history retained;
- reactivation permitted.

## Deactivated
- all access denied;
- API credentials disabled/revoked;
- identity binding retained for audit but unusable;
- no silent reactivation if existing product rule makes deactivation terminal;
- historical usage retained.

If current deactivation semantics are terminal, preserve them.

Admin UI must clearly distinguish suspended vs deactivated.

---

# 4. USER PROVISIONING

Admin must be able to:

- create user;
- edit display name;
- change approved email through safe workflow;
- suspend;
- reactivate;
- deactivate;
- inspect stable Rukan ID;
- inspect teams;
- inspect effective access;
- inspect identity binding;
- reset identity binding;
- inspect API credentials;
- issue/revoke credentials;
- inspect recent usage.

Changing approved email after an OIDC subject is already bound must NOT silently
change the external subject.

Define:
- whether binding remains valid;
- mismatch state;
- administrator reconciliation action.

Document and test.

---

# 5. IDENTITY BINDING RECOVERY

Identity binding requires operational recovery controls.

Admin actions:
- inspect issuer;
- inspect subject fingerprint;
- last bound/used time;
- mismatch status;
- reset binding.

Reset:
- does not delete user;
- does not delete usage;
- invalidates old issuer+subject binding;
- next valid approved login may bind again.

Security:
- reset is local-admin operation;
- audit it;
- no raw subject exposed if not necessary;
- no bearer token stored.

Test:
- employee changes identity provider subject;
- old binding refuses;
- admin resets;
- new binding works;
- another subject cannot steal the account.

---

# 6. MULTIPLE IDENTITY PROVIDERS

Architect now for multiple configured issuers.

v0.4 may support one active provider in UI if implementation cost is bounded, but
schema/contracts must not assume one global issuer forever.

Define provider config:
- provider id;
- display name;
- issuer;
- audience;
- discovery URL;
- enabled;
- trust settings;
- claim mapping;
- created/updated.

IdentityBinding already contains issuer.

Do NOT bind only on email.

If implementing multiple providers is low-risk after the discovery verifier work,
support multiple providers now.

If not:
- create a provider registry seam;
- clearly document one-active-provider limitation.

---

# 7. OIDC PRODUCT READINESS

After Step 1 hardening, add product-level controls.

Admin should see:
- configured/not configured;
- provider name;
- issuer;
- discovery status;
- JWKS last refresh;
- key count;
- last auth success;
- last auth error category;
- clock skew setting;
- audience;
- TLS validation mode.

Never show signing keys as editable secrets.

Health states:
- ready;
- degraded;
- unavailable;
- misconfigured.

Do not call the IdP itself "healthy" based solely on one successful login.

---

# 8. GATEWAY NETWORK DEPLOYMENT MODES

Define supported modes.

## Loopback/private host mode
Gateway binds loopback, reverse proxy forwards locally.

## Private network mode
Gateway binds explicit private interface/address where administrator config permits.

## External edge mode
Rukan itself does NOT become an Internet perimeter product.
Document:
- customer must put normal reverse proxy/WAF/identity/network policy around it;
- TLS required;
- trusted proxy list explicit.

Gateway should never default to `0.0.0.0` with no authentication/TLS warning.

Admin must display:
- bind;
- port;
- TLS status;
- trusted proxy status;
- external-access warning if applicable.

---

# 9. TRUSTED PROXY SEMANTICS

Complete and test trusted-proxy behavior.

Only explicitly trusted proxy addresses may influence:
- forwarded client IP;
- forwarded scheme;
- host where needed.

Never trust:
- X-Forwarded-For;
- Forwarded;
- X-Real-IP

from untrusted peers.

Identity remains bearer-token based, not proxy-header identity, unless a future
signed assertion adapter is explicitly implemented.

Test spoofing.

---

# 10. GATEWAY TLS

Support:
- direct TLS cert/key;
- reverse-proxy TLS termination.

Direct TLS:
- cert/key file validation;
- restrictive key permissions;
- load failure is explicit;
- no plaintext fallback.

Reverse-proxy mode:
- Rukan may run HTTP on loopback/private backend;
- Admin shows that TLS is terminated externally and cannot independently verify
  external edge configuration.

Do not falsely claim "secure" solely because the backend is loopback.

---

# 11. API CREDENTIAL PRODUCT MODEL

Complete credential lifecycle.

Credential:
- key id;
- owner user;
- label;
- scopes;
- issued;
- expiry;
- revoked;
- last used;
- created by actor;
- optional description.

Policies:
- minimum/maximum TTL;
- configurable default TTL;
- no permanent token by default unless explicit admin choice;
- user must have API credential permission;
- credential cannot outlive deactivated user in effective access.

Admin:
- issue;
- copy once;
- revoke;
- inspect metadata.

Self-service:
- if allowed, user may view credential metadata;
- self-revoke;
- optionally issue own credential only if admin policy permits.

Do not expose stored secret.

---

# 12. API CREDENTIAL RATE / ABUSE BOUNDS

No billing/quota engine yet.

Add simple policy seams:
- per-user concurrent requests;
- global concurrent requests;
- optional per-user requests/minute;
- optional API credential rate bound.

If implementing requests/minute materially complicates v0.4, preserve an explicit
RatePolicy port and enforce concurrency now.

Admin should understand rejection:
- overloaded;
- rate_limited;
- policy_denied.

---

# 13. CLIENT APPLICATION IDENTITY

Client id should not be arbitrary analytics pollution.

Define bounded client identity rules.

Known clients:
- librechat;
- rukan_workspace_future;
- generic_api;
- admin_operator_test;
- named credential label where appropriate.

Untrusted X-Rukan-Client must not create unbounded cardinality.

Prefer:
- sanitize;
- map unknown to generic;
- derive client identity from credential or Workspace adapter when possible.

Test malicious long/high-cardinality values.

---

# 14. MODEL ACCESS POLICY

Current user policy has model-selection permission, but product should distinguish:

- may use currently assigned/default model;
- may list/select among allowed models.

Define Rukan model access now.

At minimum:
- deployment-wide allowed employee model set;
- optional team/user allowed-model restriction seam.

Do not build complex per-model RBAC if not needed.

But:
- `GET /v1/models` must not expose models that user cannot invoke;
- chat request must enforce same policy independently.

If only one READY model exists in v0.4, still create an adapter/policy seam rather
than hardcoding "all users see current model forever."

---

# 15. NO EMPLOYEE DEPLOYMENT AUTHORITY

Employee Gateway users may select only among models the administrator has already
made available.

They do NOT:
- acquire models;
- create Plan;
- admit resources;
- start Serve;
- unload models;
- release reservations.

Those remain administrator actions.

Future self-service deployment is separate product work.

---

# 16. WORKSPACE ADAPTER PRODUCT CONTRACT

Formalize the adapter interface.

Required capabilities:
- adapter id;
- adapter version;
- artifact/image digest;
- managed/external mode;
- health/readiness;
- inference API base projection;
- identity-forwarding capability;
- models capability;
- streaming capability;
- usage-display capability;
- MCP capability;
- agent capability;
- config generation version;
- upgrade compatibility.

Admin must show:
- selected Workspace;
- version;
- mode;
- capability profile;
- degraded/unsupported capabilities;
- connection status.

Do not reduce WorkspaceAdapter to helper functions only if lifecycle management is
now a product requirement.

---

# 17. LIBRECHAT MANAGED MODE

If Rukan supports managed LibreChat:
- exact image digest pinned;
- dependency services pinned;
- Rukan-owned config directory;
- secrets in protected env/secret file;
- start/stop/status through adapter/executor;
- no direct DB mutation;
- logs bounded;
- restart policy explicit.

Do not make LibreChat lifecycle affect Rukan Gateway availability.

If LibreChat fails:
- generic API access continues.

---

# 18. LIBRECHAT EXTERNAL MODE

Support or architect:
- externally managed LibreChat URL;
- Admin generates/downloads required config;
- adapter performs capability/version check where possible;
- Rukan does not manage container lifecycle.

This is important for customers that already operate application platforms.

If not implemented:
- define adapter mode seam and document future support.

---

# 19. LIBRECHAT UPGRADE POLICY

Because the current pin is pre-release, define compatibility policy.

Never auto-upgrade.

Upgrade requires:
1. explicit new adapter compatibility entry;
2. config rendering test;
3. OIDC token forwarding test;
4. model list;
5. streaming;
6. usage;
7. MCP;
8. no DB coupling;
9. physical smoke;
10. explicit supported-version list update.

Admin must warn if external LibreChat version is unsupported.

---

# 20. USER SELF-SERVICE SURFACE

Keep a Rukan-owned user API independent of Workspace.

Required:
- `GET /v1/me`;
- `GET /v1/me/usage`.

Add/complete:
- credential metadata/revoke endpoint where policy allows;
- current models/capabilities;
- MCP connection status where appropriate.

Do not expose:
- other users;
- team membership beyond own contextual info if unnecessary;
- admin-only system facts.

The minimal `/me` HTML page may remain provisional.

The next first-party Workspace will replace/expand it.

---

# 21. USAGE RETENTION / ACCOUNTING PRODUCT STANDARD

After crash-safe canonical Gateway usage is implemented:

Define retention for:
- canonical Gateway usage events;
- user analytics projections;
- deployment/telemetry projection;
- Gateway audit.

Requirements:
- retention cannot break reconciliation;
- canonical data needed to rebuild projections must remain long enough or be
  compacted into durable aggregates;
- compacted aggregates preserve per-user totals;
- no prompt/response.

Test retention > threshold.

---

# 22. USER TOKEN CONSERVATION — HARD INVARIANT

For every reporting period:

```text
EmployeeRequests = Σ UserRequests

EmployeeInputTokens = Σ UserInputTokens

EmployeeOutputTokens = Σ UserOutputTokens
```

If any record is `not_recorded`, coverage must be explicit.

Expose:
- token coverage percentage;
- requests with recorded tokens;
- unresolved token count requests.

Do not present exact token totals as complete when some requests have unknown counts.

Admin reconciliation states:
- match;
- projection_pending;
- partial_token_coverage;
- mismatch;
- degraded.

---

# 23. TEAM ANALYTICS

One request maps to at most one accounting team.

Make that choice inspectable.

Current rule:
earliest active membership.

Audit whether this is good product behavior.

Preferred product-friendly alternative:
- explicit primary/accounting team;
- otherwise unassigned.

Do not silently choose an arbitrary team forever if this creates misleading
department analytics.

During design review choose:
A. explicit primary team;
B. request-selected team from allowed memberships;
C. current deterministic earliest team as provisional.

The UI must disclose the rule.

No double counting.

---

# 24. USAGE EXPORT / VENDOR BOUNDARY

Vendor Command Center receives only deployment aggregate.

Allowed:
- employee requests;
- aggregate input/output tokens;
- aggregate failures;
- model/runtime;
- total active-user count only if product/privacy decision explicitly approves it.

Default disallowed:
- user id;
- email;
- name;
- team ids;
- identity issuer/subject;
- credential ids;
- MCP user identity.

Negative canary tests required.

---

# 25. MCP CATALOG LIFECYCLE

Admin must be able to:
- add approved MCP server;
- edit label;
- disable;
- re-enable;
- delete only when safe or archive;
- see transport;
- see auth method;
- see sensitivity/category;
- test connectivity;
- see last success/error;
- inspect which capability policy controls usage.

Do not permit users to invent server URLs unless `mcp_connect` explicitly allows
and the product has safe target controls.

Enterprise default:
admin-approved catalog only.

---

# 26. MCP AUTHENTICATION

Supported auth modes should be explicit.

At minimum:
- none;
- per_user_bearer where safely handled.

Architect for:
- OAuth 2.0 authorization code/PKCE;
- client credentials for service tools;
- static secret references.

Do not implement all if not required now.

If per-user bearer is accepted by Gateway:
- secret never stored in prompt;
- not logged;
- not vendor-exported;
- memory lifetime bounded;
- user separation strict.

If current broker simply forwards incoming Authorization token to MCP, verify this
is semantically correct for the test server and NOT assumed valid for arbitrary
enterprise MCP.

Document distinction between:
- Rukan OIDC token;
- MCP resource-server OAuth token.

Do not blindly reuse one bearer token across unrelated audiences in production.

This is an important architecture review point.

---

# 27. MCP OAUTH / TOKEN EXCHANGE SEAM

Create an `McpCredentialProvider` / equivalent seam if needed.

The product must support future:
- separate MCP OAuth audience;
- token exchange/on-behalf-of;
- per-user connection secret.

Do not hardcode "forward Rukan Gateway bearer to every MCP server."

For v0.4:
- test server may accept the same synthetic bearer only if explicitly documented as
  a fixture simplification;
- production design must preserve separate authorization.

---

# 28. MCP SSRF / TARGET SAFETY

Close known debt around hostname resolution.

Current implementation resolves hostname before request but connection may resolve
again.

Implement robust target policy.

Options:
- connect to validated resolved IP while preserving Host/SNI correctly;
- use a transport/client that pins validated resolution;
- revalidate on redirect/DNS change;
- disable redirects by default.

Requirements:
- no cloud metadata;
- no link-local;
- no multicast;
- no unspecified;
- admin-approved private/internal targets permitted;
- unapproved private targets denied;
- redirect cannot escape approval;
- DNS rebinding test.

This is a PILOT_BLOCKER for user-configurable remote MCP.

If user-created MCP remains disabled and admin-approved exact URLs only, still close
obvious redirect/rebinding escape paths before pilot.

---

# 29. MCP TOOL AUDIT

Audit only non-content metadata by default:
- user id;
- server id;
- tool name if safely non-sensitive;
- allowed/denied;
- latency;
- result category.

Do NOT store:
- tool arguments;
- tool result content;
- OAuth token.

If tool name itself can be sensitive in some environments, support configurable
redaction later.

---

# 30. MCP FAILURE ISOLATION

MCP outage must not take down model inference.

If MCP server unavailable:
- tool call fails clearly;
- ordinary chat still works;
- Gateway stays healthy.

Test:
- timeout;
- DNS failure;
- 500;
- malformed JSON-RPC;
- oversized response;
- auth failure.

Bound MCP response body size.

---

# 31. AGENT SEMANTICS

Do not overbuild native Agent Builder.

But freeze the boundary.

Rukan AgentDefinition is canonical only for future Rukan-owned agents.

LibreChat agents remain client-local unless explicitly imported/projected.

Document:
- no guarantee that deleting a LibreChat agent affects Rukan;
- Rukan access policy still constrains its model/MCP calls;
- client-local agent metadata is not vendor-exported.

The future first-party Agent Builder will use Rukan contracts.

---

# 32. ADMIN EMPLOYEE ACCESS PAGE

Turn current fragments into a coherent product area.

Suggested navigation:

`People`
- Users
- Teams
- Access

`User Access`
- Gateway
- Identity
- Workspace
- API Connections
- MCP

`Analytics`
- User Usage
- Team Usage
- Reconciliation

Exact nav may vary.

Primary questions:
1. Who can use Rukan?
2. Are they successfully bound to enterprise identity?
3. Which models can they use?
4. Can they connect other applications?
5. Which MCP tools can they use?
6. How much are they using?
7. Are any access/identity/accounting systems degraded?

No raw SQLite/config editing.

---

# 33. ADMIN READINESS SCORECARD — FACTUAL, NOT OPAQUE

Provide explicit statuses, not an unexplained "health score".

Examples:
- Gateway: ready/degraded/unavailable;
- Identity provider: configured/ready/error;
- Workspace adapter: ready/degraded/not configured;
- usage projections: caught_up/pending/degraded;
- MCP catalog: N approved / M failing connectivity;
- Users: provisioned/bound/suspended counts.

Avoid one opaque percentage.

---

# 34. EMPLOYEE ACCESS PRE-FLIGHT

Create a non-mutating preflight.

Checks:
- Gateway bind;
- TLS;
- OIDC discovery;
- audience/issuer;
- JWKS reachable;
- model READY;
- Gateway can see authorized instance;
- usage store writable;
- Workspace adapter configured;
- LibreChat compatibility;
- MCP target connectivity where configured;
- credential store permissions.

Output:
- human readable;
- JSON where practical;
- PASS/BLOCKED per subsystem.

Do not perform real inference unless explicit probe flag.

---

# 35. SERVICE LIFECYCLE

Gateway must have clear:
- start;
- stop;
- restart;
- status.

Workspace managed adapter:
- start;
- stop;
- restart;
- status.

MCP broker is part of Gateway unless architecture says otherwise.

Restart:
- no user/accounting loss;
- no duplicate projections;
- OIDC cache safely rebuilt;
- API credentials remain;
- LibreChat may reconnect.

Test SIGTERM/SIGINT.

---

# 36. GATEWAY OBSERVABILITY

Customer-local metrics:
- auth successes/failures;
- active requests;
- queued/rejected requests;
- latency;
- streaming first-chunk latency where supported;
- upstream failures;
- accounting pending/degraded;
- OIDC refresh failures;
- MCP request/failure counts.

No user email in generic operational logs.

Allow detailed user-specific audit only in restricted customer-local Admin access.

Do not vendor-export raw per-user observability.

---

# 37. LOGGING

Structured logs should:
- include stable request id;
- include safe user id only where customer-local restricted log policy permits;
- not include bearer;
- not include prompt/response;
- not include MCP payload;
- not include API credential secret.

Bound log growth.

Document rotation/retention assumption.

---

# 38. DATABASE / MIGRATION READINESS

Audit:
- directory.sqlite;
- gateway canonical usage store;
- projections;
- telemetry;
- any Workspace adapter state.

Migration:
- transactional;
- schema versioned;
- idempotent;
- failure leaves previous usable state;
- no destructive reset.

Test upgrade from:
- accepted v0.3 canonical;
- current pre-hardening v0.4 development schema where relevant;
- fresh.

If migration from unreleased development schema is unnecessary, state so and provide
developer reset guidance separate from customer upgrade behavior.

---

# 39. BACKUP / RESTORE

Define minimum customer-local backup scope for v0.4:
- install identity;
- People;
- access intents;
- identity bindings;
- credentials/verifiers;
- Gateway usage/accounting state;
- MCP catalog;
- Admin settings;
- deployment records where required.

Secrets must remain protected.

Provide a documented offline backup procedure or existing state-root backup rules.

Test:
- copy/restore under stopped services;
- restart;
- identity/accounting coherent.

Do not build a complex online backup engine if unnecessary.

---

# 40. CORRUPTION / DEGRADED STATE

If one non-authoritative projection DB is corrupt:
- do not delete canonical data;
- attempt rebuild from canonical source;
- mark degraded;
- inference may continue if authorization truth remains sound.

If People/identity authority DB is corrupt:
- fail access safely;
- do not allow unauthenticated inference.

Document recovery.

---

# 41. CAPACITY / CONCURRENCY

Gateway concurrency defaults must respect deployment capacity.

Do not let Gateway advertise 100 concurrent requests if runtime/ResourceManager
configuration only supports a small number.

Create a derived/default relationship:
- runtime effective max sequences/concurrency;
- platform Gateway max concurrent;
- per-user bound.

Admin may lower Gateway bound.

Increasing beyond safe runtime bound requires explicit validation/refusal.

Preserve future central configuration plane.

---

# 42. QUEUEING

Define bounded queue behavior.

If current Gateway rejects immediately when full, document.

If adding queue:
- bounded length;
- bounded wait;
- cancellation;
- FIFO or explicit policy;
- no unbounded memory.

Do not overbuild priority classes now.

Return standard overload response.

---

# 43. REQUEST LIMITS

Enforce:
- body max;
- message count;
- text size;
- max_tokens;
- model context compatibility;
- stream duration;
- HTTP idle timeout.

Do not parse full huge bodies before checking Content-Length where practical.

Chunked transfer limits need bounded handling if supported.

---

# 44. ERROR CONTRACT

Freeze a stable client-safe error vocabulary.

At minimum:
- authentication_required;
- identity_not_provisioned;
- identity_binding_conflict;
- user_suspended;
- platform_access_denied;
- inference_access_denied;
- model_not_allowed;
- no_ready_model;
- insufficient_scope;
- overloaded;
- rate_limited if implemented;
- upstream_failure;
- accounting_degraded;
- mcp_access_denied;
- mcp_target_denied;
- mcp_upstream_failed.

Map consistently to HTTP.

Document which are retryable.

Do not leak internal exception strings.

---

# 45. OPENAI-COMPATIBILITY CONTRACT

Audit actual compatibility.

Required:
- `GET /v1/models`;
- `POST /v1/chat/completions`;
- streaming SSE;
- usage fields.

Document supported subset:
- roles;
- max_tokens;
- stream;
- unsupported tools/functions if not implemented;
- unsupported multimodal.

Do not claim full OpenAI API compatibility.

Use:
`OpenAI-compatible Chat Completions subset`.

Test with:
- curl;
- official/standard OpenAI-compatible Python client if practical;
- LibreChat.

---

# 46. VERSION NEGOTIATION / API STABILITY

Before first-party Workspace, identify v0.4 Gateway API as a product contract.

Add:
- service version/build endpoint or response header;
- schema/version metadata where useful.

Do not break current routes casually.

Future frontend should be able to check compatible backend.

---

# 47. LIBRECHAT PHYSICAL PRODUCT TEST

After Step 1 physical proof, extend into product behavior:

- Admin can see adapter ready;
- employee opens LibreChat;
- OIDC session established;
- model list filtered by Rukan;
- user chats;
- true streaming;
- token usage returned;
- suspend user mid-session then next inference denied;
- revoke API credential where generic client used;
- MCP allow/deny;
- restart LibreChat;
- session reconnect behavior documented.

No DB manipulation.

---

# 48. LIBRECHAT FAILURE MODES

Test:
- container down;
- Mongo down;
- unsupported version;
- bad generated config;
- IdP unreachable;
- Gateway unreachable.

Rukan Gateway/generic API should remain available where independent.

Admin should report Workspace degraded, not whole Rukan deployment down.

---

# 49. EXTERNAL CLIENT PRODUCT TEST

Use at least:
- curl;
- Python OpenAI-compatible client;
- one additional simple generic client if inexpensive.

Prove:
- models;
- non-streaming;
- streaming;
- credential scope;
- revoke;
- self usage.

This demonstrates LibreChat replacement boundary is real.

---

# 50. USER EXPERIENCE WITHOUT LIBRECHAT

Rukan should still provide:
- connection base URL;
- API credential management where allowed;
- My Usage;
- allowed models;
- documentation.

LibreChat is optional.

This is a hard decoupling test.

Run a full user inference session with LibreChat completely stopped.

---

# 51. DOCUMENTATION

Update:
- RUKAN.md;
- ARCHITECTURE.md;
- ROADMAP.md;
- People/access docs;
- Gateway v0.4 docs;
- Admin docs;
- privacy docs;
- telemetry docs;
- server acceptance docs;
- DEBT.md.

Create:
`docs/machi/RUKAN-EMPLOYEE-ACCESS-ADMIN-GUIDE.md`

Include:
- provision user;
- configure OIDC;
- connect LibreChat;
- connect generic app;
- issue API token;
- configure MCP;
- inspect usage;
- suspend access;
- troubleshoot.

---

# 52. PRODUCT SUPPORT EVIDENCE

Add employee-access facts to customer-local support snapshot:
- Gateway version/status;
- identity provider configured/status;
- Workspace adapter/version/status;
- usage projection status;
- approved MCP server count/status;
- user counts by status only where appropriate.

Do NOT include:
- names;
- emails;
- subjects;
- tokens;
- prompts.

Vendor support export remains privacy allow-listed.

---

# 53. LOCAL TEST MATRIX

Before physical campaign, execute:

## Identity
- discovery;
- JWKS rotation;
- binding;
- mismatch;
- reset;
- suspend/deactivate;
- multiple provider seam.

## Credentials
- issue;
- scope;
- expire;
- revoke;
- user suspend;
- concurrency.

## Gateway
- model list;
- non-stream;
- true stream;
- disconnect;
- timeout;
- malformed body;
- overload;
- service restart.

## Accounting
- canonical append;
- projection fail/retry;
- retention;
- token coverage;
- per-user/deployment conservation;
- team context.

## MCP
- allow/deny;
- auth;
- SSRF;
- DNS rebinding/redirect;
- timeout;
- oversized body;
- unavailable server.

## Workspace
- config;
- version mismatch;
- managed/external mode seams;
- adapter down;
- Gateway independent.

## Migration
- v0.3 → v0.4;
- current dev → final where supported;
- fresh.

## Privacy
- synthetic email/name/subject/token/prompt/response/MCP payload canaries.

Full backend/frontends/static/build QA.

---

# 54. FAILURE INJECTION

Deliberately inject:
- disk write failure in usage canonical append;
- projection DB lock;
- OIDC discovery timeout;
- JWKS refresh timeout;
- Gateway upstream model unavailable;
- client disconnect;
- MCP upstream timeout;
- Workspace down;
- read-only config;
- credential store unwritable.

Required:
- truthful degraded state;
- no security bypass;
- no double usage;
- no process crash loop.

---

# 55. LOAD / CONCURRENCY TEST

This is not a scale benchmark.

Run practical bounded tests.

Examples:
- 10 synthetic users;
- 2 requests each;
- mixed streaming/non-streaming;
- concurrency near configured limit.

Prove:
- per-user caps;
- global cap;
- no cross-user attribution;
- accounting conservation;
- acceptable SQLite contention;
- no deadlock;
- latency reported;
- overload response bounded.

Do not use huge GPU load or expensive models.

Fixture/local for most tests; one small physical concurrency smoke later.

---

# 56. PHYSICAL DIAGNOSTIC CAMPAIGN

After local closure, continue the existing v0.4 physical campaign.

Use one Pod/host at a time.

Diagnostics continue from D3.

A full clean diagnostic now means:

## Foundation
- artifact-only install;
- model acquire;
- Deploy;
- Plan;
- ResourceManager;
- Serve;
- inference;
- STOP;
- RELEASE;
- telemetry.

## Employee access
- production OIDC discovery;
- key rotation at least one diagnostic;
- two allowed users;
- unprovisioned;
- suspended;
- API credentials;
- full scope matrix smoke;
- true streaming;
- user token conservation;
- Gateway restart;
- My Usage;
- Admin analytics;
- MCP;
- LibreChat physically running;
- generic client without LibreChat;
- privacy.

## Product operations
- suspend user after successful session;
- revoke credential;
- Workspace failure isolation;
- MCP failure isolation.

Require two consecutive clean full diagnostics.

Code change resets clean streak.

---

# 57. PHYSICAL HOST STRATEGY

Do not require GPU host to run every commodity service if that makes validation fragile.

Allowed economical topology:

```text
GPU host:
  Rukan control
  Gateway
  model runtime

CPU/container host OR same GPU host if capable:
  LibreChat
  Mongo
  test IdP
  MCP fixture
```

If two hosts:
- use real network/TLS paths;
- preserve one GPU Pod maximum;
- low-cost CPU service may use existing authorized tooling if available;
- keep total campaign within budget.

Do not introduce permanent cloud infrastructure.

---

# 58. CONFIDENCE CAMPAIGN

After two clean diagnostics:

Freeze:
- Rukan source SHA;
- wheel SHA;
- Gateway API version;
- LibreChat digest;
- deployment manifest;
- IdP test artifact/config;
- MCP test artifact.

Run 3 fresh confidence environments.

Each:
- install;
- deploy;
- Gateway;
- OIDC;
- user provisioning;
- LibreChat;
- generic client;
- streaming;
- tokens;
- MCP;
- restart;
- STOP/RELEASE;
- privacy;
- cleanup.

No code changes.

At least across the 3 runs collectively prove:
- key rotation;
- Gateway restart;
- LibreChat restart;
- MCP outage;
- credential revoke;
- user suspend;
- concurrency smoke.

---

# 59. DEFECT ITERATION

Continue autonomous defect correction.

For every product defect:
- evidence;
- classification;
- invariant;
- regression;
- robust design;
- fix;
- commit;
- QA;
- new immutable artifact;
- diagnostic retest.

Do not stop on ordinary fixable defects.

Stop only on:
- safety;
- cost;
- provider authorization;
- architectural uncertainty requiring product decision;
- diagnostic iteration cap from master orchestration.

---

# 60. PRODUCT CLOSURE REVIEW

Before PASS, answer:

1. Can an admin provision a user without backend knowledge?
2. Can enterprise OIDC rotate keys?
3. Can a suspended user be cut off immediately?
4. Can a generic app use Rukan without LibreChat?
5. Can LibreChat be removed without changing identity/usage/policy?
6. Do streamed responses arrive live?
7. Can accounting recover from crashes?
8. Do user totals reconcile to deployment totals?
9. Is MCP governed and failure-isolated?
10. Can normal enterprise security products sit in front of Rukan?
11. Can Rukan upgrade without destructive resets?
12. Can support diagnose Gateway/identity/Workspace problems without content access?
13. Does Workspace failure leave Gateway available?
14. Are direct Serve ports hidden from employees?
15. Is every employee request attributable exactly once?
16. Are remaining limitations explicitly GA debt rather than hidden?

Any "no" that is a pilot blocker must be fixed.

---

# 61. TERMINAL STATUS

PASS:

`RUKAN_V0_4_EMPLOYEE_ACCESS_PRODUCT_CLOSED`

Required:
- Gateway hardening predecessor passed;
- product closure requirements complete;
- local tests complete;
- two clean diagnostics;
- C1/C2/C3 fresh confidence;
- no SERVER_ACCEPTANCE_BLOCKER;
- no PILOT_BLOCKER;
- branch clean/pushed;
- evidence preserved;
- all owned resources cleaned.

NOT READY:

`RUKAN_V0_4_EMPLOYEE_ACCESS_PRODUCT_NOT_READY`

Use if:
- unresolved blocker;
- physical evidence incomplete;
- cost/safety stop;
- architecture ambiguity requiring Lead decision.

Do NOT merge v0.4 canonical in this phase unless master instruction later authorizes it.

---

# 62. FINAL PASTE BACK

A. terminal status
B. starting/final SHA
C. product architecture summary
D. user lifecycle
E. provisioning UX
F. identity recovery
G. OIDC provider model
H. Gateway network modes
I. trusted proxy/TLS
J. API credential lifecycle
K. model access policy
L. Workspace adapter contract
M. LibreChat managed/external modes
N. LibreChat upgrade policy
O. self-service APIs
P. canonical usage retention
Q. token coverage/reconciliation
R. team accounting
S. vendor privacy boundary
T. MCP catalog lifecycle
U. MCP auth architecture
V. MCP OAuth/token-exchange seam
W. MCP SSRF/rebinding closure
X. MCP audit/failure isolation
Y. agent semantics
Z. Admin employee-access surfaces
AA. readiness/preflight
AB. service lifecycle
AC. observability/logging
AD. migrations
AE. backup/restore
AF. corruption/degraded recovery
AG. concurrency/queueing
AH. request/error contracts
AI. OpenAI compatibility
AJ. API versioning
AK. LibreChat physical UX
AL. external client proof
AM. LibreChat-independent user path
AN. docs/support evidence
AO. local tests
AP. failure injection
AQ. load/concurrency evidence
AR. diagnostic server runs
AS. defects/fixes
AT. clean diagnostic streak
AU. confidence C1
AV. confidence C2
AW. confidence C3
AX. final wheel/API/LibreChat digests
AY. usage/accounting totals
AZ. privacy evidence
BA. campaign cost
BB. remaining GA blockers
BC. recommendation for first-party Rukan Workspace
BD. git state
BE. cleanup
BF. STOP

# END PRODUCT CLOSURE
