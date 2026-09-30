# Open Decisions

## v0.4 physical Workspace acceptance topology — do not couple LibreChat to the GPU host

The D3 hardened Gateway run proved that forcing LibreChat onto the disposable GPU host is an unnecessary infrastructure coupling. The A40 image had no Docker and rootless Podman was prohibited, even though Rukan/Gateway itself worked.

Binding direction:

- Rukan/inference may run on the disposable NVIDIA host.
- LibreChat/Mongo/test IdP/test MCP services may run on a separate container-capable operator/CPU environment.
- Prefer the existing operator/development machine if it has a supported container engine; this is cheaper and more representative than installing a container stack into the GPU test image.
- A second cloud host is optional, not required, and must only be used if existing authorized tooling supports it safely and economically.
- Product acceptance is about the real network/auth/application path, not co-location.

Preferred economical topology:

```text
OPERATOR / CPU ENVIRONMENT
  - exact pinned LibreChat container
  - pinned Mongo dependency
  - test OIDC issuer
  - test MCP server
  - browser/session automation where available
           |
           | secure SSH forwards/reverse-forwards or equally bounded test networking
           v
GPU SERVER
  - Rukan control plane
  - Rukan User Gateway
  - ResourceManager
  - Serve / vLLM
  - model
```

The test must still use:
- real HTTP/TLS;
- real OIDC discovery/JWKS;
- live bearer forwarding from LibreChat to Rukan Gateway;
- no direct vLLM endpoint in LibreChat;
- real MCP through the Rukan-governed path;
- no database shortcut.

An SSH tunnel is transport only; it does not replace Rukan authentication/authorization.

If the operator machine hosts the test OIDC/MCP services, reverse tunnels may expose those services only to the remote campaign host so that the same issuer/endpoint identity can be reached by both sides. Use campaign-local CA certificates and explicit trust rather than disabling TLS verification.

Physical LibreChat availability must no longer block development of the remaining v0.4 Employee Access product closure. If the exact container cannot be run in the current environment:
- continue all local/product implementation, migrations, failure/recovery, Admin UX, MCP governance, usage/accounting, observability, and documentation work;
- preserve physical LibreChat as an explicit acceptance debt;
- return to physical testing once a container-capable environment is available;
- final product PASS still requires real LibreChat compatibility evidence.

## Rukan v0.4 Lead review — Gateway hardening before first-party Workspace

Independent Lead review of source `459d34b34f2238b5af108c0fe822c4637603b754` accepts the overall v0.4 architecture but finds four unresolved PILOT_BLOCKER-level correctness/security/UX issues before the User Access Gateway can be treated as a stable foundation for the first-party Rukan Workspace.

### 1. Streaming must be truly end-to-end

Current `StoreChat.complete(..., stream=True)` performs `response.read()` before parsing SSE. This buffers the entire vLLM response before Rukan yields any chunk to the client.

That is not acceptable as production chat streaming.

Required:
- open upstream request;
- parse SSE incrementally;
- forward content chunks to the downstream client as they arrive;
- preserve final upstream usage event;
- record accounting exactly once;
- release concurrency on completion, upstream failure, client disconnect, timeout, or generator close;
- do not persist response content;
- do not buffer full completion solely for token accounting.

Measure:
- time-to-first-byte/chunk at Gateway boundary;
- total duration separately if available.

The first downstream chunk should be observable before upstream completion in a deterministic streaming integration test.

### 2. Enterprise OIDC must support discovery and signing-key rotation

Current verifier accepts a static in-memory JWKS only.

That is useful for deterministic tests but not sufficient as the primary enterprise adapter.

Add a production OIDC configuration/provider seam using a mature OIDC/JWT library:
- configured issuer;
- OpenID discovery document;
- `jwks_uri`;
- HTTPS by default;
- bounded fetch/connect/read timeouts;
- issuer consistency check;
- cache keys;
- refresh on unknown `kid`;
- bounded cache lifetime;
- safe failure when discovery/JWKS unavailable;
- signature/issuer/audience/exp/nbf/sub validation;
- supported algorithms allow-list;
- no bearer token logging.

Keep injected static JWKS as a deterministic test adapter/fixture, not the production-only story.

Physically or locally prove key rotation:
- token signed with key A succeeds;
- provider rotates to key B;
- first B request causes bounded refresh and succeeds;
- removed/unknown invalid key fails.

### 3. API credential scopes must be enforced at every route

Current behavior:
- chat checks `inference`;
- self usage checks `self_usage`;
- model listing does not require `models`;
- MCP may be called using a Rukan API credential based only on user policy even though current credential scopes do not include MCP.

This violates least privilege.

Required route authorization:
- `GET /v1/models` -> `models` scope for API credentials;
- `POST /v1/chat/completions` -> `inference`;
- `GET /v1/me/usage` -> `self_usage`;
- MCP:
  - either add an explicit `mcp` scope and require it;
  - or explicitly deny Rukan API-credential authentication on MCP in v0.4 and require OIDC.
Choose the simpler truthful policy after design review.

`GET /v1/me` may be identity/self-profile if authenticated, but must not leak capabilities beyond the principal.

Tests must cover every route × scope combination.

### 4. User/deployment accounting must be crash-consistent

Current Gateway accounting writes:
1. `InferenceUsage` into TelemetryStore;
2. `PrincipalUsage` into GatewayLedger.

These are separate commits/databases.

A process crash, disk error, or lock failure between writes can produce:
- deployment usage without user usage;
- user usage without deployment usage if ordering changes later;
- permanent reconciliation mismatch.

The product requirement is stronger than a happy-path equality assertion.

Introduce one durable Gateway usage source-of-truth / delivery state.

Preferred pattern:
- append one canonical customer-local `GatewayUsageEvent` containing both deployment and principal attribution facts;
- assign stable usage id;
- transactionally persist it once;
- derive/project:
  - principal/user analytics;
  - deployment employee usage / telemetry input
  through idempotent projections/cursors;
- projection failure remains retryable and visible;
- no prompt/response content;
- existing operational `InferenceUsage` for user_request may become an idempotent projection from the canonical Gateway usage event.

An alternative transactional/outbox design is acceptable if it provides equivalent crash consistency and exact reconciliation.

Required failure injection:
- crash after canonical append before deployment projection;
- crash after deployment projection before principal projection;
- restart/reconcile;
- final result contains exactly one deployment usage and exactly one principal usage with same usage id;
- no double counting.

Admin reconciliation must distinguish:
- match;
- projection_pending/degraded;
- true mismatch/corruption.

### 5. LibreChat physical proof remains pending

The adapter pin is currently:
- LibreChat `v0.8.8-rc4`;
- commit `361553f3322d7b9bb547d0a9c2c5aaefc2934901`;
- manifest digest `sha256:929f4491cb9a87d6beb02e9e9ce9a54d4ee05bc56b65b1debe5b1f28a327a4fb`.

This pin is a current pre-release, while `v0.8.7` is the latest stable tag. The chosen rc4 is acceptable only because the required live OpenID token/header behavior is being intentionally validated. Record this as a deliberate compatibility choice, not "stable LibreChat".

The physical server diagnostics used RunPod images without Docker, so LibreChat itself was not run.

Before v0.4 confidence:
- obtain a Docker/container-capable host or otherwise run the exact pinned LibreChat release through a supported isolated process/container path;
- prove actual OIDC login/token reuse;
- prove the custom endpoint forwards the live OpenID bearer to Rukan Gateway;
- prove model list/chat/streaming;
- prove MCP configuration against the Rukan broker;
- prove suspended/unprovisioned user is denied by Rukan;
- do not inspect/write LibreChat DB to make the test pass.

The adapter remains replaceable. This physical proof is compatibility evidence, not a reason to make LibreChat core.

### 6. Confidence readiness

The corrected D2 server run is valuable but it is only one clean diagnostic.

Before confidence:
- close items 1–4 locally;
- run local architecture/security/failure tests;
- run LibreChat physical compatibility at least once;
- obtain two consecutive clean v0.4 full-stack diagnostics on the same behavioral candidate;
- then freeze exact Rukan wheel + LibreChat digest + deployment manifest;
- run C1/C2/C3 fresh confidence hosts.

All confidence runs must re-prove the underlying v0.3 deployment lifecycle.

## v0.3 physical-confidence stock deferral / v0.4 forward-development gate — binding

The v0.3 frozen candidate:
- source `77923d0587a7ca4519a1a90dd5097a89ca4844e2`
- wheel SHA256 `6c5482508806facf0d1b19d13325387ccdc2fd1bbc8ca24bba36ac89e27aeb33`

has:
- D4 CLEAN;
- D5 CLEAN;
- corrected C1 CLEAN;
- no known open SERVER_ACCEPTANCE_BLOCKER or PILOT_BLOCKER;
- C2/C3 unexecuted only because supported secure NVIDIA inventory was unavailable after bounded placement attempts.

Provider inventory is NOT a software architecture dependency.

Therefore:

### Development-continuation status

v0.3 may be accepted as:

`RUKAN_V0_3_IMPLEMENTATION_ACCEPTED_PHYSICAL_CONFIDENCE_PENDING`

This status means:
- implementation may be merged to canonical for downstream development;
- the exact frozen v0.3 artifact does NOT receive the stronger historical claim `RUKAN_V0_3_SERVER_CAMPAIGN_PASS`;
- C2/C3 remain deferred physical-confidence evidence debt;
- docs/state must preserve that only one confidence run passed.

### Canonical merge

The frozen v0.3 candidate may be merged to canonical `machi` after:
- repository diff review;
- full local QA confirmation;
- D4/D5/C1 evidence review;
- branch clean/pushed;
- no known open product blocker.

Create a checkpoint tag that says implementation accepted / physical confidence pending. Do NOT use a tag or release name implying full three-run server campaign PASS.

### v0.4 progression

After that bounded acceptance:
- create v0.4 branch from canonical;
- execute the User Access Gateway / Workspace Adapter / LibreChat / MCP buildout immediately;
- do not block local v0.4 architecture/implementation/testing on v0.3 C2/C3 stock.

### Physical confidence supersession

The future v0.4 physical server campaign must re-exercise the complete underlying v0.3 product path:
- install;
- model acquisition;
- deploy;
- Plan;
- ResourceManager;
- Serve;
- inference;
- STOP;
- RELEASE;
- telemetry;
- People;
- Command Center.

If v0.4 obtains its required two clean diagnostics plus three fresh confidence runs on one frozen v0.4 candidate with no regression in v0.3 functionality, that evidence supersedes the need to block product progression on the historical v0.3 C2/C3 runs.

The v0.3 historical record still remains truthful:
- C1 passed;
- C2/C3 were stock-blocked;
- full v0.3 three-confidence campaign was not completed.

If supported v0.3 stock later becomes available before v0.4 confidence begins, Cursor may opportunistically run C2/C3 on the exact frozen v0.3 artifact within existing cost rules, but this is no longer a prerequisite for v0.4 development.

## Rukan v0.4 User Access Gateway / LibreChat / MCP — binding direction

This phase begins only after Rukan v0.3 server campaign closure. The v0.3 confidence candidate is currently source `77923d0587a7ca4519a1a90dd5097a89ca4844e2`, wheel SHA256 `6c5482508806facf0d1b19d13325387ccdc2fd1bbc8ca24bba36ac89e27aeb33`; C1 passed and C2/C3 remain pending only because L40S placement was unavailable.

### 1. Product architecture: LibreChat is a client, Rukan Gateway is the authority

The employee-facing inference path becomes:

```text
Employee / application
        |
        | enterprise identity or Rukan API credential
        v
LibreChat / other OpenAI-compatible client
        |
        v
Rukan User Gateway
  - authenticate principal
  - resolve Rukan User/Team AccessContext
  - authorize inference/model selection
  - route only to an authorized READY ServingInstance
  - record principal-attributed non-content usage
        |
        v
Serve / vLLM / provider path
```

- LibreChat remains replaceable and must not become Rukan's identity, policy, routing, or usage authority.
- Users never receive a direct vLLM/Ollama/Serve endpoint.
- Rukan Gateway exposes a standards-oriented OpenAI-compatible API so future clients can connect without a LibreChat dependency.
- Direct Serve ports remain private to the host/control plane.
- Rukan Admin remains the customer administrator control plane; employee inference uses a separate network/API surface.

### 2. Approved email is provisioning identity, not long-term authentication identity

Rukan Admin provisions a local User with:
- stable Rukan user id;
- approved normalized email;
- status;
- team memberships;
- access intent/policy.

For federated access:
- prefer enterprise OIDC access tokens;
- validate token signature, issuer, audience, expiry/not-before, and configured claims;
- first successful authenticated request may bind a provisioned Rukan user by approved email to the stable external identity `issuer + subject`;
- after binding, stable external subject is authoritative; email remains profile/reconciliation data;
- a different subject presenting the same email does not silently take over the user;
- suspended/deactivated Rukan user denies access even when the enterprise IdP token is valid.

Email/header values supplied by LibreChat are metadata only and must never be sufficient authorization by themselves.

### 3. Enterprise security layering, not a proprietary security stack

Rukan is not a replacement for customer cybersecurity infrastructure.

Design every user-facing surface so normal enterprise controls can sit around it:

```text
Corporate LAN / private cloud / VPN / ZTNA
        |
Firewall / load balancer / reverse proxy / WAF (customer choice)
        |
Enterprise IdP (Entra / Okta / Keycloak / equivalent)
        |
LibreChat + Rukan Gateway
```

Rukan should provide:
- TLS-capable HTTP APIs;
- OIDC/JWT validation seam;
- configurable trusted reverse-proxy boundaries;
- private/loopback bind defaults where sensible;
- standard Authorization headers;
- secure secret storage adapters;
- clear audit/accountability;
- no assumption that the product must be directly Internet exposed.

Do not build a proprietary VPN, firewall, WAF, endpoint-security, SIEM, PKI, or identity provider.

LibreChat may use OIDC, SAML, or LDAP for its own login, but the preferred Rukan Gateway production path is a bearer identity that Rukan can independently validate, especially OIDC. SAML/LDAP-only environments can later use a standard identity-aware proxy/bridge; preserve an IdentityAssertionVerifier port rather than hard-coding one vendor.

### 4. Rukan user API credentials for generic clients

To let a provisioned user connect Rukan inference to other OpenAI-compatible applications:

- optionally allow administrator-approved per-user Rukan API credentials / personal access tokens;
- token is bound to one Rukan user, scopes, issue time, expiry, status, and optional client label;
- token secret shown once and stored only as a verifier/hash;
- revocable;
- disabled if user/platform/inference access is disabled;
- never grants more capability than the user's resolved AccessContext;
- no token ever points directly to Serve.

Enterprise OIDC remains preferred for browser/SSO scenarios. Rukan credentials are a product API-access mechanism, not a replacement for corporate SSO.

### 5A. LibreChat must sit behind a replaceable User Workspace / Client Adapter boundary

LibreChat is an accelerator, not a foundation dependency.

Rukan must define its own employee-workspace contracts independently from LibreChat. The integration should look conceptually like:

```text
                    RUKAN PRODUCT CONTRACTS

Rukan User Gateway
OpenAI-compatible inference API
Identity / AccessContext
Usage API
Approved MCP catalog/policy
Agent/Workspace policy seams
        |
        +------------------------------+
        |                              |
        v                              v
LibreChatAdapter                Future RukanWorkspaceAdapter
        |                              |
    LibreChat                   first-party Rukan UI
```

The adapter must own LibreChat-specific:
- configuration files/environment;
- container lifecycle/health;
- custom endpoint projection;
- OIDC/client identity forwarding configuration;
- supported role/group/config projection where used;
- MCP server projection;
- future agent/template projection if used;
- version/capability detection.

Rukan core must not:
- import LibreChat internal code;
- depend on LibreChat MongoDB schema;
- treat LibreChat user ids as Rukan User ids;
- treat LibreChat agents as Rukan's canonical agent ontology;
- treat LibreChat MCP configuration as Rukan's canonical MCP policy;
- require LibreChat for direct OpenAI-compatible API access;
- require LibreChat for future first-party Workspace.

Pin one supported LibreChat version/container digest behind the adapter. Detect incompatible versions and fail clearly instead of depending on undocumented internals.

### 5B. First-party Rukan Workspace is a planned product path, not a prerequisite for v0.4

Rukan should preserve the option to own its employee experience.

A future first-party Rukan Workspace can reasonably include:
- chat/conversation UI;
- streaming inference;
- model selector constrained by Gateway policy;
- own usage display;
- file/context attachment surfaces;
- MCP connection/tool picker;
- agent builder;
- saved agents/workspaces;
- prompt/templates;
- conversation search/history;
- Team Brain/Git Brain integration.

Do not build the full first-party Workspace in v0.4 if that delays proving the access/gateway infrastructure.

However, v0.4 MUST establish contracts that make a later first-party client straightforward:
- standard Rukan Gateway API;
- self-service `My Usage` API;
- user connection/credential API;
- Rukan-owned MCP catalog/policy contracts;
- Rukan-owned agent/workspace metadata interfaces if agent projection into LibreChat is implemented;
- no LibreChat-specific identity in core records.

### 5C. Build-vs-reuse decision

The design review must assess a staged path:

**Phase 1 — reuse LibreChat behind adapter**
- fastest path to usable employee chat;
- validates Gateway, identity, user accounting, MCP, access policy;
- avoids spending the current infrastructure milestone on commodity chat UX.

**Phase 2 — thin first-party Rukan Workspace**
- native chat;
- model/access-aware experience;
- My Usage;
- Connections;
- MCP tool chooser;
- Rukan-native visual language.

**Phase 3 — Rukan Agent Builder**
- Rukan-owned AgentDefinition/AgentRevision contracts;
- model policy;
- system/instruction template;
- allowed MCP tools/connections;
- knowledge/resource bindings later;
- execution policy;
- sharing/team ownership;
- audit/versioning;
- export/projection adapters to clients such as LibreChat where useful.

Cursor must recommend exact boundaries after architecture review. It should not blindly preserve LibreChat as the permanent UI if a thin first-party client becomes cheaper/cleaner once the Gateway exists.

The core architectural requirement is that replacing LibreChat later must NOT require redesigning:
- identity;
- access policy;
- routing;
- usage accounting;
- MCP governance;
- deployment/Serve;
- customer/vendor privacy boundaries.

### 5. LibreChat integration

Use LibreChat as the first employee chat/workspace client because it:
- supports OpenAI-compatible custom endpoints;
- supports OIDC/SAML/LDAP authentication;
- supports dynamic user/OpenID headers on configured endpoints;
- supports token/context display;
- supports Agents and MCP.

Pin one exact tested LibreChat release/container digest for the Rukan adapter. Do not follow latest implicitly.

Preferred inference configuration:
- LibreChat custom OpenAI-compatible endpoint points to Rukan Gateway, not vLLM;
- where the pinned LibreChat release supports it, pass the signed-in user's live OIDC access token in `Authorization: Bearer ...` to Rukan Gateway;
- optional LibreChat user id/email/conversation headers are correlation metadata only, not authorization;
- if direct OIDC token forwarding is not available in the selected stable LibreChat release, Cursor must design a standards-based trusted-client assertion/token-exchange alternative; it may not fall back to trusting an unsigned email header from any network caller.

Do not fork LibreChat unless there is no viable standard/config/API integration. Prefer config/admin APIs/adapters.

### 6. User usage accounting

Extend active inference usage so employee traffic has a stable principal attribution:

- Rukan `user_id`;
- optional effective team context;
- client/application id;
- request purpose/class;
- model/runtime;
- input tokens when reported;
- output tokens when reported;
- latency;
- outcome/failure.

No prompt/response content.

Accounting invariants:

```text
EmployeeDeploymentInputTokens  = SUM(UserInputTokens)
EmployeeDeploymentOutputTokens = SUM(UserOutputTokens)
EmployeeDeploymentTotalTokens  = SUM(UserInputTokens + UserOutputTokens)
```

for all employee/user traffic in the same time window.

Operational traffic remains separate:

```text
AllInference =
  EmployeeTraffic
  + OperatorTests
  + AcceptanceProbes
  + Other explicitly classified system traffic
```

This separation prevents qualification/Admin tests from inflating employee adoption.

Every employee inference request must resolve exactly one Rukan user before model execution.

Multiple team membership must not double-count usage. If team analytics are implemented, each request needs one explicit accounting team context or must be classified `unassigned`; do not duplicate one user's tokens into every team membership.

### 7. Token display

Users should see token usage.

For LibreChat:
- enable/use its native token/context usage display with the standard usage fields returned by Rukan Gateway;
- keep Rukan's usage ledger authoritative;
- verify the pinned LibreChat version renders Rukan-reported input/output usage correctly for streaming and non-streaming responses.

Also provide a Rukan user-safe self-usage query/surface:
- own requests/tokens by 24h/7d/30d/all retained;
- input/output/total;
- model breakdown;
- no access to other users.

Avoid forking LibreChat merely to add a lifetime-usage widget. If LibreChat cannot display Rukan-authoritative cumulative totals through supported extension/config surfaces, provide a small Rukan "My Usage / Connections" user page or API and link to it rather than coupling Rukan to a LibreChat fork.

Admin local Analytics should show per-user usage and prove that the user rows sum exactly to the deployment employee total.

Vendor Command Center continues to exclude names/emails/user lists. It may receive deployment-level employee request/token aggregates only if explicitly added to the non-content telemetry allow-list.

### 8. MCP: role and boundary

MCP is NOT the inference transport.

Two distinct paths:

```text
MODEL PATH
LibreChat / client
  -> Rukan Gateway
  -> model inference

TOOL / DATA PATH
LibreChat Agent (MCP Host)
  -> MCP client connection
  -> approved MCP server
  -> enterprise tool/data source
```

MCP gives the model/application standardized:
- tools;
- resources;
- prompts.

Initial product direction:
- leverage LibreChat's MCP host/client support instead of rebuilding an MCP host inside Rukan;
- Rukan Admin owns a governed connection/catalog policy seam describing which MCP servers are approved and which users/teams may use them;
- prefer remote Streamable HTTP MCP for multi-user enterprise deployments;
- local stdio MCP is primarily for single-user/local developer use and should not become the default multi-user server path;
- use OAuth/OIDC per-user authorization to MCP servers when available;
- do not pass user OAuth credentials into model prompts;
- external MCP credentials belong in the client/secret/auth layer, not the model or inference usage record.

Rukan should not build a full MCP proxy/broker in this phase unless architecture review proves it is necessary for enforceable policy. Prefer a thin Rukan policy/catalog + LibreChat execution model first.

If users are allowed to add their own MCP connections, make that an explicit administrator-controlled capability. Enterprise default should be admin-approved connections only.

Future Git Brain / Company Brain services should be designed so they can themselves expose MCP servers/resources/tools, making them usable from LibreChat, Cursor, VS Code, and other MCP hosts without client-specific integrations.

### 9. MCP access model

Extend current access intent only as needed, with bounded capabilities such as:
- MCP use;
- MCP connection creation/configuration;
- Agent use;
- Agent creation.

Do not invent a general RBAC framework.

If projecting Rukan policies into LibreChat, use documented LibreChat admin/config/access APIs where stable. Rukan's gateway inference authorization remains authoritative regardless of LibreChat UI permissions.

### 10. Rukan Gateway data/content boundary

Gateway necessarily handles prompt/response transiently to perform inference, but:
- prompts/responses remain unpersisted by Rukan operational analytics by default;
- usage/audit stores only non-content facts;
- no customer messages go to vendor Command Center;
- per-user usage stays customer-local;
- vendor telemetry remains deployment-level aggregate only unless a future explicit opt-in decision changes that.

### 11. Network surfaces

Keep planes distinct:

- Rukan Admin: administrator surface, private/loopback/admin network;
- Rukan User Gateway: employee/application inference API, designed for private network or customer-controlled reverse proxy exposure;
- LibreChat: employee UI, customer network exposure according to enterprise policy;
- direct Serve/vLLM/Ollama ports: never employee/public API;
- Command Center: vendor/business plane remains separate from customer inference.

### 12. Server campaign expectations for v0.4

After local architecture/implementation:
- run iterative server diagnostics until two consecutive clean product runs;
- then three fresh confidence runs on one exact frozen artifact;
- server topology should include:
  - Rukan Admin/control plane;
  - Rukan User Gateway;
  - LibreChat pinned version;
  - standards-compliant test OIDC/JWT issuer or enterprise-compatible test IdP;
  - Command Center;
  - real NVIDIA model deployment/inference;
- test at least two allowed users plus denied/suspended users;
- prove identity binding, user policy, token attribution, exact aggregate conservation, LibreChat inference, direct OpenAI-compatible API access, optional Rukan user API credential, and at least one MCP connection;
- iterate/fix product defects under version control before confidence.

## Rukan v0.3 product deployment closure after server D1 — binding

Server diagnostic D1 proved the packaged product shell, telemetry, People, Command Center, and verified vLLM foundation on a real NVIDIA L40S host, but exposed two product blockers before a real inference deployment chain could be completed:

1. the clean Machi/Rukan wheel uses the Hugging Face model-source adapter but does not declare the required `huggingface_hub` runtime dependency;
2. the Stage-1 Plan, ResourceManager, and Serve capabilities exist internally, but the shipped Rukan Admin/CLI/API does not yet expose one complete administrator product action that takes an exact stored model through recomputation, planning, admission, serving, readiness, inference, STOP, and RELEASE.

These are now SERVER_ACCEPTANCE_BLOCKERS.

### Model acquisition packaging

- The release artifact must declare every Python dependency required by a supported product path.
- Rukan must not depend on a transitive dependency that happens to exist inside a managed vLLM environment.
- The Hugging Face adapter may remain optional at architecture level, but if the shipped Admin exposes HUB acquisition as a supported action, the normal Rukan artifact must install the adapter dependency required to execute that action.
- Pin or bound the dependency using the project's existing dependency policy after verifying a tested compatible version; do not leave an accidental unbounded latest dependency if avoidable.
- A clean isolated wheel installation must acquire the small public acceptance model without a manual `pip install`.

### Deployment orchestration product seam

Introduce one Rukan-owned customer-local deployment orchestration service/control API that composes existing domain owners without replacing them.

Conceptually:

```text
Admin / local product API
        |
        | select exact model + bounded desired settings
        v
Rukan Deployment Orchestrator
        |
        +--> reconstruct trusted local state
        +--> recompute current Capacity/Foundation/Model feasibility
        +--> compose DeploymentPlan
        +--> ResourceManager.admit()
        +--> Serve.start()
        +--> wait for READY
        +--> expose resulting ServingInstance
```

Authority remains:

- Model domain owns artifact/eligibility facts;
- Plan owns deployment configuration;
- ResourceManager remains sole physical admission authority;
- Serve owns process lifecycle;
- telemetry only observes;
- browser never submits arbitrary pid/port/runtime/provider/reservation/fingerprint.

The orchestrator owns workflow coordination, idempotency, error mapping, and product-facing operation state only.

### Product workflow

For the current bounded v0.3 pilot, Admin must support a truthful path equivalent to:

```text
Browse/inspect exact model
        ↓
Acquire/store exact artifact
        ↓
Deploy
        ↓
Preparing
  ✓ host/capacity recomputed
  ✓ foundation/runtime verified
  ✓ model compatible
  ✓ plan created
  ✓ resources admitted
  ✓ runtime started
        ↓
READY
        ↓
Admin inference tester
        ↓
STOP
        ↓
RELEASE
```

Do not expose "Deploy" until this backing operation is real.

The exact artifact/digest remains authoritative even when the UI groups models by family/generation/variant.

### Recompute-before-execute

A Deploy request must not trust stale UI projections.

At invocation:
- resolve current Install/state root;
- reconstruct current verified foundation/generation;
- load and verify the exact stored model artifact;
- recompute current capacity;
- validate model/runtime/capacity compatibility;
- create a fresh DeploymentConfiguration/Plan;
- request ResourceManager admission;
- start Serve only with the exact admitted plan/reservation;
- fail closed if any dependency is stale/unresolved/incompatible.

No reuse of a prior reservation or plan after model/runtime/resource changes unless the architecture explicitly proves it remains current.

### Idempotency / failure compensation

The Deploy operation must be safe under retries and partial failure.

At minimum:
- a repeated request for the exact already-READY deployment converges to that instance rather than duplicating it;
- plan failure creates no reservation/process;
- admission rejection creates no process;
- Serve start failure leaves the reservation in a truthful state and exposes a deliberate release/recovery path;
- if the orchestrator can safely release a reservation created by the same failed operation after confirmed no-process state, do so explicitly and record evidence; otherwise retain the hold and show the required administrator recovery action rather than guessing;
- API/network retry after the backend has already started the operation must not create duplicate reservations/instances;
- STOP remains distinct from RELEASE.

### Operation persistence

Use an explicit customer-local operation/workflow record if necessary to make deploy status/retry/restart truthful.

It should contain non-secret references such as:
- operation id;
- selected artifact id;
- requested bounded configuration;
- plan id;
- reservation id;
- serving instance id;
- state/outcome;
- timestamps;
- typed failure;
- actor origin.

Do not duplicate the authoritative full Plan/Reservation/Serve records.

### UI

Admin Models/Deployment should provide a coherent business-admin experience:
- selected model card/detail;
- Deploy action;
- bounded settings only where backend feasibility supports them;
- clear preparation/progress states;
- READY state;
- current model/runtime/context/resource facts;
- Test inference;
- STOP;
- RELEASE after STOP;
- technical details via progressive disclosure.

Do not put advanced knobs on Overview.

### Campaign continuation

After local product closure:
- build a new immutable artifact;
- perform a clean artifact-only local acceptance of acquire → deploy → READY → >=3 inference requests → STOP → RELEASE;
- then resume the existing `rukan/v0.3-server-campaign` as the next diagnostic iteration, D2;
- D1 remains evidence and counts as diagnostic iteration 1;
- diagnostic maximum remains D5;
- the clean-run streak is currently zero because D1 found product blockers;
- two consecutive clean diagnostics are still required before confidence;
- confidence still requires C1/C2/C3 fresh servers on one identical final artifact.

## Rukan v0.3 autonomous server campaign — binding

The post-audit accountability correction is followed by one autonomous bounded server campaign. This campaign is authorized only after the correction reaches:

`RUKAN_V0_3_PRODUCTION_CANDIDATE_READY_FOR_SERVER_ACCEPTANCE`

and Lead-review blockers from `RUKAN-V0.3-PRODUCTION-READINESS-FIX-001` are closed.

### Campaign purpose

The campaign exists to discover server-only integration defects, not merely to repeat local tests.

It must exercise the frozen release artifact on real disposable servers, collect real operational evidence, repair server/pilot blockers through normal version-controlled development, and iterate without requiring additional user instructions unless a safety/authentication/hang gate requires intervention.

The desired end state is:
- bounded Rukan v0.3 works reproducibly from its release artifact on fresh supported server hosts;
- automatic 2-minute Development telemetry works during acceptance;
- deployment/inference/usage/People/Admin/Command Center workflows are exercised;
- failures discovered on servers become local regression tests before fixes are accepted;
- campaign telemetry/support evidence is preserved after disposable servers are destroyed;
- three final fresh-server confidence runs pass on a frozen candidate without code changes between those three runs.

### Iteration model

Use two phases.

#### Phase A — diagnostic/corrective campaign

Maximum **5 server diagnostic iterations**.

An iteration is:
1. freeze exact source commit and wheel SHA;
2. provision or reuse one authorized disposable server;
3. install artifact-only;
4. execute the campaign acceptance slice;
5. collect evidence;
6. classify every deviation;
7. if a product defect exists:
   - reproduce locally where feasible;
   - write a failing regression test;
   - design the smallest robust architectural correction;
   - fix on the campaign branch;
   - run local QA;
   - commit and push;
   - build one new immutable RC artifact;
   - continue to the next server iteration;
8. never hot-patch source code on the server as the accepted fix.

Diagnostic phase may end before iteration 5 only after **two consecutive clean server iterations** on the same source candidate/behavioral design with no SERVER_ACCEPTANCE_BLOCKER or PILOT_BLOCKER and no unexplained data mismatch.

If iteration 5 still exposes a server/pilot blocker, stop and return NOT_READY with evidence rather than continue spending.

#### Phase B — confidence campaign

Once diagnostic robustness is established, run **3 additional fresh-server confidence tries**.

Requirements:
- each starts from a newly provisioned disposable server or demonstrably fresh host image/state;
- install only the exact frozen wheel selected after Phase A;
- no source checkout;
- no code changes between the three runs;
- if any of the three finds a product defect, confidence phase fails:
  - fix via version control;
  - candidate is no longer frozen;
  - return to diagnostic mode, counting against the maximum diagnostic budget if still available;
  - after robustness is re-established, confidence run count resets to 0;
- terminal PASS requires three consecutive clean fresh-server confidence runs on one identical source commit and wheel SHA.

### Server minimization

- One disposable server at a time.
- NVIDIA only for this campaign unless a test requirement proves otherwise.
- Prefer the cheapest available previously supported/qualified NVIDIA shape that safely runs the tiny acceptance model and the complete Rukan control plane.
- Prefer A40/L40S or another already-supported NVIDIA family over introducing hardware breadth during a software robustness campaign.
- Do not use AMD in this campaign solely for breadth.
- Diagnostic iterations may reuse the same pod when the next test does not require a fresh host, but must use:
  - fresh virtual environment;
  - fresh Rukan state root;
  - fresh Command Center data root;
  - fresh telemetry credential;
  - fresh InstallId;
  - exact new RC artifact where code changed.
- Recreate the pod whenever:
  - installation/bootstrap/fresh-host behavior is under test;
  - host contamination could mask the defect;
  - the current pod is unstable;
  - confidence phase begins.
- Confidence runs use fresh servers.

### RunPod policy

All existing RunPod safety limits remain binding:
- Cursor may manage only disposable RunPod Pods it creates for this campaign;
- never modify/stop/terminate a pre-existing or ambiguously owned Pod;
- official RunPod agent skill/MCP/runpodctl only; no custom cloud client;
- max concurrent Pods: 1;
- NVIDIA max hourly price: $1.50/hour;
- no network volume;
- max Pod lifetime: 90 minutes;
- max provisioning retries: 3;
- session max: $40;
- daily max: $80;
- remaining account balance floor: $0.50;
- live account balance must be established before creation;
- projected test must preserve the $0.50 floor;
- on success or terminal product failure: capture evidence then terminate the owned Pod;
- on hang: STOP the owned Pod and ask Daniel before termination, per binding policy.

Additional campaign target:
- target total campaign infrastructure spend <= $15 when availability permits;
- if projected campaign spend will exceed $15, stop before creating another Pod and report why;
- this additional cap is a campaign economy guard, not permission to violate any stricter existing limit.

### Server topology

The default low-cost test topology may co-locate the two product planes on one disposable server while keeping them logically separate:

```text
Disposable server

Customer Rukan plane
  - separate state root
  - Admin on 127.0.0.1
  - Serve/runtime/model
  - telemetry sender

Business plane
  - separate Command Center data root
  - Command Center UI on 127.0.0.1
  - telemetry intake
  - separate credential database
```

The planes must communicate through the real telemetry HTTP/TLS/machine-auth path, not by writing each other's databases.

For TLS on a single host:
- use a campaign-local CA/server certificate with SAN matching the test endpoint;
- run telemetry client with normal certificate/hostname verification;
- do not use `local_test=true` to bypass TLS verification for the acceptance result;
- do not weaken production client code solely for the campaign.

If a real owned external HTTPS endpoint is already available and can be used safely without new product architecture, one confidence run may exercise it. It is not required to create unrelated infrastructure solely to satisfy this campaign.

### Real-user behavior exercised

Each server run should exercise the current bounded product like a customer administrator would:
- install/start from wheel;
- open packaged Admin through loopback/SSH tunnel semantics;
- inspect Overview/System;
- inspect Models;
- deploy/start the accepted small model/runtime path;
- perform multiple inference requests;
- record input/output tokens and latency;
- inspect Admin Analytics/Activity;
- create/edit/suspend/reactivate/deactivate test users where appropriate;
- create/edit/archive/reactivate teams;
- add/remove membership;
- set access intent and inspect effective access;
- configure automatic reporting with Development 120-second cadence;
- receive periodic and material-event reports;
- trigger a permitted monitoring/configuration change;
- stop serving;
- release reservation;
- verify corresponding reports;
- restart Admin and Command Center/intake;
- simulate a brief telemetry outage;
- verify queued resend/recovery;
- verify no content/People PII crosses the telemetry boundary.

Use synthetic acceptance identities/emails only.

### Data collection and preservation

Every run must have a durable campaign run id.

Collect at least:
- source commit;
- wheel name/SHA/build id;
- RunPod Pod id owned by campaign;
- provider GPU shape;
- hourly rate;
- OS/arch;
- driver/runtime versions;
- CPU/RAM/VRAM/storage observations;
- InstallId;
- telemetry stream id(s);
- model/artifact/runtime/macropath;
- deployment/plan/reservation/ServingInstance/Witness identifiers where appropriate;
- report ids/sequences/triggers/timestamps;
- generated_at/received_at/ACK timing;
- heartbeat intervals;
- inference request count;
- input/output tokens when reported;
- latency;
- failure counts/types;
- usage-accounting degradation state;
- People workflow outcomes using synthetic PII;
- restart/outage behavior;
- retention/stream-reset behavior when exercised;
- test PASS/FAIL;
- defects discovered;
- code commit that fixes each defect;
- approximate server spend.

Do not commit:
- real credentials;
- private keys;
- bearer secrets;
- customer content;
- raw prompts/responses;
- proprietary files.

Before terminating a Pod, copy sanitized evidence back to the campaign evidence root on the operator machine.

Also export the existing privacy-safe support snapshot / analytics bundle from the server run and import it into a persistent local campaign Command Center inbox where possible, so the final local Command Center accumulates a list of campaign deployments and historical analytics after the Pods are gone.

Automatic telemetry itself is still tested on the server topology; manual bundle import is used only for durable cross-run aggregation after teardown.

### Version control discipline

Use one campaign branch after the accountability fix, suggested:

`rukan/v0.3-server-campaign`

Never rewrite accepted history.

For each iteration record:
- run manifest;
- tested source SHA;
- tested wheel SHA;
- result;
- defect IDs;
- evidence path.

If code changes:
- add regression test first where feasible;
- code fix commit;
- QA;
- build artifact;
- separate sanitized evidence/update commit when useful.

Commit messages should identify the campaign iteration, for example:
- `server-campaign(i2): reproduce telemetry reset defect`
- `server-campaign(i2): preserve stream currentness across reset`
- `server-campaign(i2): record acceptance evidence`

Do not commit generated secrets or raw sensitive logs.

### Defect handling

Every server deviation gets one classification:
- PRODUCT_DEFECT;
- TEST_HARNESS_DEFECT;
- PROVIDER_ENVIRONMENT_DEFECT;
- UNSUPPORTED_HOST;
- EXPECTED_LIMITATION;
- OPERATOR_ERROR.

For PRODUCT_DEFECT:
1. write minimal causal hypothesis;
2. identify violated invariant;
3. design robust solution before patching;
4. prefer domain-owner fix over UI workaround;
5. add local regression;
6. fix;
7. run targeted QA;
8. run full bounded regression appropriate to changed domain;
9. freeze new artifact;
10. retest server.

Never:
- disable safety checks just to pass;
- hardcode one RunPod machine;
- suppress an error instead of fixing state semantics;
- change expected output to match a bug;
- mark provider failures as product PASS without evidence.

### Robustness criteria before confidence phase

Must have two consecutive clean diagnostic runs with:
- artifact-only install;
- Admin packaged UI works;
- Command Center packaged UI works;
- model deploy/start/inference/stop/release works;
- usage/token accounting reconciles exactly;
- 2-minute periodic telemetry observed for at least three slots;
- one event-trigger report between slots;
- telemetry outage/retry works;
- restart works;
- no duplicate/lost report or usage;
- People workflow works;
- privacy canaries absent from Command Center;
- no unexplained SQLite lock/migration errors;
- no stale stream/current-state errors;
- no hidden manual repair;
- no source checkout/Node runtime;
- all SERVER_ACCEPTANCE_BLOCKER and PILOT_BLOCKER findings closed.

### Confidence run minimum

Each of the 3 final fresh tries should remain economical but must include enough time to prove:
- clean install;
- one deployment;
- at least 3 real inference requests;
- at least 3 periodic 120-second reports;
- at least 1 material event report;
- one restart of a product service;
- stop/release;
- evidence export;
- clean teardown.

If prior diagnostic evidence proves a long outage/retry path repeatedly, confidence runs do not need to repeat every expensive destructive scenario; at least one confidence run must still exercise a brief intake outage/recovery.

### Final campaign result

PASS only if:
- post-audit accountability fix passed before campaign;
- no unresolved SERVER_ACCEPTANCE_BLOCKER;
- no unresolved PILOT_BLOCKER in the declared POSIX/NVIDIA pilot envelope;
- three consecutive fresh confidence runs pass on the exact same source SHA + wheel SHA;
- final wheel hash is recorded;
- final branch is clean/pushed;
- campaign evidence and aggregate summary exist locally;
- persistent local Command Center contains/imports the campaign deployment/support/analytics evidence where existing product import paths permit;
- all owned Pods are terminated.

Terminal PASS:

`RUKAN_V0_3_SERVER_CAMPAIGN_PASS`

Failure terminal:

`RUKAN_V0_3_SERVER_CAMPAIGN_NOT_READY`

Use NOT_READY if:
- diagnostic iteration 5 still finds blocker;
- cost/safety gate prevents adequate testing;
- provider availability prevents confidence evidence;
- a hang requires Daniel input;
- three consecutive confidence runs cannot be obtained;
- data/evidence is contradictory.

### Autonomous scope

Within these bounds, Cursor is authorized to:
- provision/stop/terminate owned disposable campaign Pods;
- install the frozen Rukan wheel;
- configure synthetic acceptance data;
- run current supported tiny models;
- inspect logs/state/evidence;
- modify repository code/tests/docs in response to discovered product defects;
- commit/push campaign work;
- build successive RC wheels;
- repeat diagnostic loops;
- perform final confidence runs.

Cursor is not authorized to:
- touch pre-existing Pods;
- use network volumes;
- exceed cost/balance limits;
- deploy unrelated cloud infrastructure;
- weaken security;
- add remote customer control;
- add employee auth/chat/RAG/Agent Builder/licensing;
- perform destructive cleanup outside campaign-owned paths;
- upload customer content.

## Rukan v0.3 bounded production-readiness gate — binding

The next gate is not a claim that the entire long-term Company Brain is GA-ready. It is a **bounded production-readiness gate for the currently implemented Rukan v0.3 pilot product**:

- customer-local Admin, loopback-only;
- deployment/model/inference/system/analytics/activity/People/settings surfaces currently implemented;
- Stage-1 Blocks 0–9 authority;
- local People/Teams/access-intent directory;
- non-content inference usage accounting;
- automatic one-way operational reporting;
- machine-authenticated TLS telemetry intake;
- business Command Center portfolio/analytics/reporting;
- no employee login/gateway/chat/RAG/agent builder;
- no remote customer control.

A production-readiness PASS must mean that this bounded product can be installed from its release artifact, operated on supported hosts, restarted/upgraded safely, and used for a controlled pilot/server acceptance without relying on source checkout, fake data, hidden manual repairs, or unverified architectural assumptions.

### Readiness classification

Cursor/Lead must distinguish:

1. **SERVER_ACCEPTANCE_BLOCKER** — likely to make the upcoming real-server campaign fail or corrupt/lose/security-misstate data. Must be fixed before server testing.
2. **PILOT_BLOCKER** — unacceptable for a controlled customer pilot, but may not prevent a narrow lab server test. Must be fixed before pilot.
3. **GA_BLOCKER** — required before general commercial production/GA but intentionally outside the current bounded pilot (for example human administrator authentication or a Windows secret-storage adapter where that platform is not yet declared supported).
4. **DEFERRED_PRODUCT** — later Company Brain capability, not a defect in this bounded scope.

Do not label something production-ready merely because tests pass. State the supported deployment envelope and unresolved GA blockers explicitly.

### Telemetry cadence

- One authoritative duration policy remains mandatory.
- Development/server-acceptance profile: **120 seconds**.
- Production profile: **21,600 seconds / 6 hours**.
- A production-mode deployment must not accidentally inherit the 2-minute development cadence merely because the binary was built during development.
- The selected profile must be explicit, inspectable and persisted.
- The upcoming server campaign will intentionally select the development profile to accelerate observation.
- Commercial/pilot documentation must identify the production profile as the normal operating setting.

### Artifact-only operation

A release candidate is not ready for server acceptance unless:
- a clean wheel/release artifact can be installed into a fresh environment without repository checkout;
- Node/npm/Vite are not required on the target host at runtime;
- production Admin and Command Center static assets are packaged or otherwise delivered by the release artifact;
- CLI/service commands can discover those packaged assets without hard-coded repository-relative paths;
- build identity and source provenance remain inspectable.

### Data-delivery correctness

Inference usage export must be audited for race- and boundary-free delivery. Timestamp windows alone are insufficient if they can double-count same-boundary records or lose a usage row inserted after a report snapshot with an earlier occurred_at. Prefer an ACK-owned stable local usage sequence/cursor or prove an alternative cannot lose/duplicate rows under concurrency.

Operational reports must remain:
- at-least-once;
- ACK-owned;
- idempotent receiver-side;
- resilient to restart;
- bounded in storage;
- explicit about stream/reset continuity.

### Persistence and retention

Production readiness requires:
- migration transactions/failure tests;
- crash/restart tests;
- sensitive-file permissions on supported platforms;
- explicit retention/compaction policies so 2-minute development reporting cannot grow customer/Command Center stores without bound;
- no deletion of unacknowledged data;
- preserved rollups/accountability when raw delivered envelopes are compacted.

### Security envelope

Until human administrator authentication exists:
- Admin remains loopback-only;
- remote administrator testing uses SSH/local forwarding;
- this is acceptable for controlled pilot/server acceptance but is a **GA limitation**, not something to hide.
- external telemetry intake is the only non-loopback product surface in this stage;
- production non-loopback intake requires verified TLS and machine authentication;
- local-test TLS/HTTP exceptions must be impossible to enable accidentally on a non-loopback bind.

### People/access semantics

Before future gateway work:
- People UI must expose the real directory capabilities;
- platform access is the parent gate for subordinate capabilities;
- per-capability access provenance must be truthful;
- user/team policy inheritance/override semantics must be explicitly coherent and tested;
- PII stays customer-local;
- current configuration must never be described as enforced employee access until gateway authentication/authorization actually exists.

## Development telemetry cadence / acceptance readiness — binding

- Telemetry cadence becomes a typed, centrally configurable policy expressed internally in **seconds**, not an hours-only field.
- Preserve the product production target of **6 hours**.
- During the current development/real-user acceptance phase, the default **development profile is 120 seconds (2 minutes)** so deployment/report behavior can be observed quickly.
- Use explicit named profiles at minimum:
  - `development`: interval 120 seconds; small deterministic phase/jitter suitable for tests;
  - `production`: interval 21600 seconds (6 hours); deterministic fleet-distribution phase up to the approved production jitter.
- A bounded custom interval may be supported through one authoritative setting/CLI/API seam. Do not scatter cadence constants across scheduler, report contracts, UI and tests.
- The periodic schedule is independent from event-triggered reports. Event/model/settings/test reports never postpone the next periodic slot.
- Jitter establishes a stable phase; it does not accumulate on each interval.
- Admin/Command Center must display the active cadence/profile truthfully.
- Before commercial release, switching the default from development to production must be one central product-policy change, not a code sweep.

### Real-user/server acceptance preparation

- Prepare, document and locally validate a repeatable server acceptance workflow, but **do not run external/server acceptance yet** unless Daniel explicitly starts that campaign.
- Acceptance should be designed for Daniel to act as the real customer administrator:
  - deploy/start Rukan;
  - access Rukan Admin safely;
  - browse/select/inspect models;
  - perform inference tests;
  - observe usage;
  - change permitted monitoring/configuration settings;
  - manage people/teams/access intent;
  - stop/release deployment;
  - observe event and 2-minute periodic reports arrive in Command Center.
- Until human authentication exists, customer Admin remains loopback-only. Remote browser testing should use an operator-controlled SSH tunnel or equivalent local forwarding rather than exposing Admin unauthenticated on the network.
- The only externally exposed surface in this stage is the bounded machine-authenticated HTTPS telemetry intake.
- Prepare an evidence checklist and exact commands for at least:
  - customer Rukan host;
  - business/operator Command Center host/PC;
  - secure telemetry pairing;
  - 2-minute reporting;
  - deployment READY/STOP/report triggers;
  - inference token/latency accounting;
  - telemetry outage/retry;
  - privacy/content-negative checks;
  - user/team directory administration.
- Do not consume RunPod or other paid server capacity during preparation.

## People / Teams / future employee access foundation — binding

Rukan now needs a first-class customer-local people directory so identity is not retrofitted after the employee gateway/chat experience.

### Product boundary

- Build the **directory, team membership, access-policy intent, administration UI/API, persistence, audit/accountability and future authorization seam now**.
- Do **not** build employee login, authentication sessions, email delivery, invite links, employee inference endpoint, chat UI, agent builder, LibreChat/Open WebUI integration, RAG/knowledge permissions or remote provisioning yet.
- Until an employee gateway actually consumes the policy, UI must not claim that a configured person can already log in or that inference access is enforced.

### Directory concepts

Use Rukan-owned typed identities. Cursor may refine exact contract names after architecture review, but the model must distinguish at least:

- **User**:
  - platform-minted stable user id;
  - normalized unique email plus display email;
  - display name;
  - lifecycle/status such as active/suspended/deactivated (do not invent "invited" if no invitation was sent);
  - created/updated timestamps;
  - optional external identity reference seam for future IdP reconciliation;
- **Team**:
  - stable team id;
  - name;
  - optional description;
  - active/archived state;
- **Membership**:
  - explicit user ↔ team relationship;
  - timestamps/provenance;
  - optional bounded membership role only if repository/product review demonstrates a current need;
- **Access intent/policy seed**:
  - whether the user is intended to have platform access;
  - whether future inference access is allowed;
  - whether future end-user model selection is allowed;
  - whether future agent-builder access is opted in/allowed;
  - explicit enforcement state showing that future employee gateway enforcement is not active yet.

Do not store passwords.

Do not build a generic enterprise RBAC engine prematurely.

### Authorization seam

Preserve the Product Vision principle that one future `AccessContext` / subject model should serve gateway, analytics, knowledge, agents and audit.

The old `src/kultrun/identity/contracts.py` may be used as design precedent, not copied blindly.

Create the smallest Rukan-owned resolver/projection needed so a future gateway can ask:

- who is this subject?;
- which teams do they belong to?;
- is the directory record active?;
- what is the current intended inference/access policy?;
- what team/user policy provenance produced that result?

Default-deny and conservative composition are preferred. If multiple-team policy composition creates a material design choice, document and challenge it rather than inventing complex RBAC.

### Privacy

- User emails, names, memberships and external identity references are **customer-local restricted PII**.
- They must never enter vendor/Command Center telemetry in this increment.
- Command Center may not receive user lists.
- If later product telemetry needs user/team counts, that requires an explicit privacy/product decision.
- Admin activity events may cite stable local user/team ids where locally appropriate, but vendor export must exclude directory PII.

### Admin product surface

Add a customer Admin surface named **People** or **Users & Teams** based on UX review.

It should support real local CRUD/state changes backed by persistence:
- list/search users;
- create/edit user;
- suspend/reactivate/deactivate;
- show stable id and email;
- list/create/edit/archive teams;
- assign/remove team membership;
- inspect effective access intent;
- configure supported access-intent toggles;
- show clearly which future capabilities are not yet enforceable;
- show recent directory/access changes in Activity.

Do not clutter the main Overview. A small truthful summary such as active users/team count may appear only if useful.

### Future capability controls

Where the backend contract is implemented, allow the administrator to configure intent such as:
- platform access enabled/disabled;
- future inference access enabled/disabled;
- future user model-selection permission;
- future agent-builder opt-in/permission.

Every future-only control must display an enforcement/readiness state such as **Configured — employee gateway not yet enabled**. Never imply that toggling it changes a non-existent employee endpoint.

### Accountability

Record actor origin and before/after-safe change evidence for:
- user created/updated/status changed;
- team created/updated/archived;
- membership added/removed;
- access intent changed.

Do not put email addresses/secrets into vendor-exportable operational events.

## Automatic monitoring / telemetry loop — binding direction

Rukan is moving from manual analytics-file transfer to a **one-way automatic operational reporting loop**. This is monitoring and accountability, not remote control.

### Semantics

- A deployment sends a versioned **Operational Report** to the vendor/business intake.
- The periodic trigger may be called a heartbeat in product language, but it does **not** prove Online/Offline or current health.
- Command Center may show **Last report received**, **report age**, report sequence, report trigger and latest reported state.
- Until an explicit liveness model is implemented, Command Center must not derive Online, Offline, Healthy, Unhealthy, Last Seen, or availability SLA from report cadence.

### Cadence and triggers

- Periodic report target: every **6 hours**.
- Add bounded jitter so future fleets do not synchronize exactly.
- Also request an immediate/coalesced report after material operational changes, including:
  - deployment/serving instance reaches READY;
  - deployment/serving instance is STOPPED and/or its reservation is released;
  - deployment start/serve failure;
  - active model selection changes;
  - Foundation/runtime/macropath selection changes, including approved fallback;
  - active DeploymentPlan materially changes or becomes stale/replaced;
  - bounded inference settings change: context length, concurrency, replica count, placement/device, resource reserve/headroom where those settings actually exist;
  - AUTO/MANUAL selection mode changes or a bounded override changes;
  - model artifact/provider model is installed/acquired/removed where active contracts support the action;
  - Rukan software/build changes;
  - SAFE capacity materially changes after rediscovery/recharacterization;
  - telemetry sharing, endpoint, cadence or machine credential changes.
- Pure presentation preferences, UI filters, theme, local Command Center aliases and other non-operational UI settings do not warrant deployment telemetry.
- Coalesce related rapid state transitions into one report once the resulting state is stable rather than uploading several redundant reports seconds apart.

### Security

- Human login/authentication and tenancy remain deferred.
- **Machine authentication is mandatory for automatic upload.** Secure telemetry cannot accept unauthenticated Internet writes.
- Initial direction: HTTPS + one high-entropy credential per deployment/key-id, with server-side credential verification and rotation/revocation seams.
- Non-loopback transport must require TLS. Plain HTTP is permitted only for explicit local test mode.
- Credentials, tokens and secrets are never journaled, exported, displayed after creation, or included in analytics bundles/reports.
- The external intake surface is write-only/minimal. It must not expose ResourceManager, Serve, settings mutation, shell, file access or remote-control APIs.
- A full human identity system is not a prerequisite for this machine-to-machine security boundary.
- Actor accountability before identity exists records **actor origin** such as local Admin UI, CLI, system/AUTO, scheduler or telemetry agent; it must not invent a human user identity.

### Delivery semantics

- Customer inference/deployment must never depend on telemetry availability.
- Use a durable local outbox and **at-least-once delivery** with server-side idempotency; do not attempt distributed exactly-once semantics.
- Failed uploads remain queued and retry with bounded exponential backoff.
- Each accepted report has a stable report id, deployment/install id, generated time, trigger reason(s), sequence/cursor metadata and schema version.
- The server acknowledges accepted report ids. Client cursor/outbox state advances only after acknowledgement.
- A periodic report should include the latest safe deployment summary plus incremental operational changes and usage since the last acknowledged cursor, with enough cumulative counters/provenance to identify gaps.

### Inference usage

Create an active Rukan-owned **non-content inference usage record** rather than treating acceptance proofs as the long-term usage model.

Initial usage facts should include, where truthfully available:
- request/usage id and occurred_at;
- request purpose/source (for example operator_test, acceptance_probe, future user_request);
- serving instance, plan and model identity;
- runtime/macropath/provider;
- outcome and typed error/failure class;
- input tokens when the runtime reports them;
- output/completion tokens when the runtime reports them;
- latency measured at the Rukan request boundary;
- protocol status where relevant.

Never store prompt/response text in usage analytics.

Acceptance probes and Admin test prompts must be distinguishable from future employee/user traffic so product usage is not overstated.

Vendor reporting may transmit bounded interval/model rollups instead of prompt-level content. Customer Admin may retain richer local non-content request records subject to local retention.

### Product surfaces

Rukan Admin is the customer's **AI operations cockpit**: readiness, active capability, models, deployments, capacity, local usage, activity and settings.

Rukan Command Center is the vendor/business **deployment portfolio and product intelligence** surface: known deployments, report freshness, versions, hardware, runtime/model state at last report, deployment/change history, usage aggregates, failures/support evidence and telemetry intake accountability.

Both surfaces must remain evidence-backed and avoid fake KPI/state.

### Model experience

The Admin Models area should evolve toward a streaming-catalog/Netflix-like experience while preserving exact model identity:
- **family/series** (for example Qwen);
- **generation/release line** (for example Qwen 2.5 or Qwen 3);
- **concrete variant/edition** (size, instruct/base, quantization, format/runtime-specific artifact).

This grouping is presentation metadata only. It must never collapse distinct artifacts/digests or imply compatibility/equivalence that Rukan has not proven.

Rows such as Running, Installed, Recommended for this host, Compatible and Available may be shown only when the corresponding active Rukan contracts support them.

## Command Center ingestion / analytics — binding

- Rukan Command Center is now intended to be a **long-running local business application/service** on the operator PC, not only a browser-local snapshot viewer.
- v0.2 should introduce a persistent local Command Center service and datastore. Use a small local SQLite database unless repository truth exposes a stronger already-authoritative fit. The browser UI must become a client of that local service rather than the authority.
- Add a local **inbox/import directory**. A Refresh action scans that directory, validates supported Rukan export artifacts, imports only new material idempotently, and updates the UI.
- There is **no deployment-to-business transport yet**. For now, files may be copied/synced into the inbox manually or by external means. Do not pretend remote delivery exists.
- Canonical machine interchange should be **versioned JSON/JSONL**, not CSV. CSV may be offered later as a human export/import adapter, but it must not define Rukan analytics contracts.
- Preserve the existing `rukan.support_snapshot` as a compact point-in-time support summary. Do not overload it to become the entire analytics feed.
- Add a separate versioned analytics/export bundle capable of carrying currently implemented non-content analytical records from a deployment, including:
  - the support snapshot;
  - exportable EventRecord envelopes/timeline;
  - inference-proof/usage facts that actually exist in active Rukan contracts;
  - other implemented non-content analytical projections only where repository truth supports them.
- Do not invent input-token, TTFT, queue-time, cost, user/team/application, utilization, or other metrics that active Rukan does not yet persist. Preserve those as future schema/domain work.
- Customer content stays local. Prompts, generated responses, documents, RAG context, secrets, credentials, filesystem paths, and other restricted/customer-content fields must not enter Command Center analytics.
- Local customer administrators should also gain access to analytics derived from their own local operational journal/state. The customer-local Admin analytics view may contain locally permitted data that is not eligible for vendor export.
- Keep the three concerns distinct:
  1. customer-local operational/usage analytics;
  2. business/vendor product telemetry and support analytics in Command Center;
  3. future licensing/entitlement data.
- Command Center aggregation is not authoritative for local host facts, Capacity, ResourceManager, Plan, Serve, or inference availability.
- Live fleet heartbeat/transport, tenant identity, authentication, consented automatic export, and remote control remain separate later workstreams.

## RunPod acceptance cost — binding

- **NVIDIA hourly ceiling remains ≤ $1.50/hour.**
- **AMD hourly ceiling remains ≤ $4.00/hour.**
- The **remaining RunPod account-balance floor is now $0.50**.
- Before creating a Pod, live balance must be established and the planned test must be able to complete while preserving at least $0.50, accounting for the selected hourly rate, expected runtime, any other observed account burn, and a reasonable safety margin.
- If balance cannot be established or safe completion above $0.50 cannot be demonstrated, do not create the Pod.
- Existing one-Pod ownership/safety rules, session/day caps, 90-minute lifetime, retry limit, no-network-volume rule, and stop-and-ask hang handling remain unchanged unless separately amended.

There are **no blocking Lead Developer decisions** for the first Rukan dual-UI implementation bundle.

## Product identity — binding

- The product is now called **Rukan**.
- Customer-facing and business-facing product copy, new UI code, new documentation, and new post-Stage-1 workstreams should use **Rukan**.
- The existing Python package/module namespace `machi`, persisted contract kinds, ids, environment variables, state-root conventions, historical evidence, checkpoints, and control branch names are **not** renamed inside this UI bundle. Renaming persisted/internal identity requires a separate compatibility/migration decision because Stage-1 evidence and schemas already depend on them.
- Historical documents that describe Machi at the time should remain historical. Current product-facing documents should explain the Rukan name and may note that `machi` remains the internal technical namespace during migration.

## Two visual products — build both now

Rukan now has two distinct visual applications. They must share Rukan-owned contracts but remain separate trust planes.

### 1. Rukan Admin UI — customer-facing / deployment-local

- Runs on the customer Rukan host.
- Same-machine / loopback only for v0.
- Shows and operates local Rukan deployment truth.
- Does not own host truth, Capacity, Foundation, model qualification, Plan, ResourceManager, ServingInstance, lifecycle, or Witness.
- Core v0 pages:
  - Overview;
  - Inference;
  - Models;
  - Deployment;
  - System.
- Must include a small embedded inference tester for the current authorised READY local instance.
- The inference tester is **Rukan-native**. It must call a narrow Rukan-owned loopback API/control seam, which then calls the current authorised serving path. The browser must not bypass Rukan and talk directly to vLLM/Ollama as the normal product architecture.
- Prompt and response content remain local and are not added to operational telemetry, Witness, or business Command Center export.
- LibreChat is **not** the Rukan Admin UI and is not required for v0.
- LibreChat/Open WebUI or another client may later be supported as a replaceable employee/end-user chat client through standard Rukan/gateway APIs. They must not define Rukan Admin semantics or lifecycle authority.

### 2. Rukan Command Center — business/vendor-facing

- Separate application and trust plane from the customer Admin UI.
- Initial v0 may run locally on the business operator's PC.
- Its purpose is to list known Rukan deployments and inspect non-content deployment/support information.
- v0 must not pretend there is already live fleet telemetry, remote control, tenancy, or always-on customer connectivity.
- The simplest truthful v0 is an **imported deployment/support snapshot workflow**:
  - a customer-host Rukan deployment can produce a bounded non-content Deployment Summary / Support Snapshot derived from persisted Rukan evidence;
  - the business operator imports that snapshot into the local Command Center;
  - the Command Center stores and renders those imported summaries locally.
- If repository truth already contains a better existing export seam, reuse it rather than creating a competing mechanism.
- Command Center v0 should show only fields supportable from real Rukan evidence, such as where available:
  - deployment/install identity;
  - first-observed/deployed timestamp with exact semantics stated;
  - Rukan build/version;
  - OS/architecture/accelerator summary;
  - selected macropath/Foundation/runtime identity;
  - model identity and qualification scope;
  - current or exported Witness verdict;
  - physical qualification state;
  - safe non-content operational event/support evidence.
- Raw customer prompts, generated responses, documents, RAG context, secrets, and customer files must not be exported.
- v0 Command Center has no remote start/stop/admit/release authority.
- It must not become authoritative for the customer's local ResourceManager, host facts, Capacity, Plan, Serve, or inference availability.
- Live connected fleet updates, tenancy, customer identity, authentication, consented telemetry, licensing and remote support are later workstreams.

## Stage-1 and macropath invariants remain binding

- Stage 1 remains closed as `STAGE1_DEPLOYMENT_SPINE_IMPLEMENTATION_CLOSED_PHYSICAL_BREADTH_PENDING` at `4cb89622a4cd3a1a37bf6ab44c4414e4287e8934`.
- Native/vLLM remains the primary macropath where supported.
- Ollama remains the compatibility/fallback macropath.
- AUTO fallback remains a control-plane recomputation, not a hidden Serve retry and not request-level live failover.
- Native and Ollama model identity/catalog semantics remain separate.
- One ResourceManager remains the sole local admission authority.
- STOP != RELEASE.
- Physical qualification remains pending where recorded: AMD native/vLLM, macOS/Ollama, NVIDIA Ampere/N1 breadth and other recorded gaps.

## v0 UI truth rule

Every visual field, KPI, action, list, badge, chart or log must be backed by real Rukan contracts/evidence or be omitted.

Do not add fake placeholder functionality merely to make either product look complete.

Mocked future navigation is acceptable only when visibly labelled future/not implemented.

## Frontend technology

- Cursor must inspect repository reality and apply the Industry Solution Selection Gate if there is a material framework choice.
- The Lead's current default preference is a small TypeScript web frontend that can be built to static assets and served locally, with React + Vite as the likely baseline if repository/tooling reality does not show a better fit.
- Avoid a heavyweight full-stack framework unless there is a demonstrated need.
- The Admin UI and Command Center may share a small Rukan design system / typed client package where that does not merge their security boundaries.

## Naming of screens

- Customer app: **Rukan Admin**.
- Business app: **Rukan Command Center**.
- Initial model page is **Models**, not Marketplace. A curated catalog/marketplace becomes a product claim only after the underlying catalog/discovery/recommendation semantics exist.

## Not in this bundle

- Dynamo implementation;
- Runtime Artifact Registry implementation, except interfaces needed by UI must not block future registry work;
- Knowledge/RAG;
- users/teams/permissions;
- licensing/entitlements;
- LAN/remote Admin;
- live central telemetry/heartbeat;
- central remote control;
- multi-host scheduling;
- live request-failure failover;
- broad model marketplace/recommendation semantics;
- physical AMD/macOS/Ampere campaigns.

## Future decision gates

- Internal/package namespace migration from `machi` to `rukan`.
- Authentication/authorisation before any non-loopback customer Admin UI.
- Fleet identity, tenant identity, consent and live export before a connected Command Center.
- Runtime Artifact Registry scope.
- LibreChat/Open WebUI or other employee-facing chat client integration.
- Dynamo and other runtime/fabric comparisons.
