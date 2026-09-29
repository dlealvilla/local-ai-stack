# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-V0.4-GATEWAY-HARDENING-AND-CAMPAIGN-CONTINUE-001`
Status: `AUTHORIZED_CORRECTION_AND_CONTINUATION`

Starting implementation source:
`459d34b34f2238b5af108c0fe822c4637603b754`

Current evidence tip:
`ff92569a7ce4d644aef9ae2011d8735014c04778`

Branch:
`rukan/user-access-gateway-v0.4`

Canonical:
`machi@16084a5b21a0cca25bfe60070ad862832c80fb51`

The previous v0.4 run made substantial progress and correctly returned:

`RUKAN_V0_4_USER_ACCESS_NOT_READY`

It implemented:
- Rukan User Gateway;
- OIDC identity binding;
- Rukan API credentials;
- OpenAI-compatible models/chat API;
- user usage;
- Admin per-user analytics;
- MCP broker/catalog policy;
- LibreChat replaceable adapter;
- physical Gateway tests on A40;
- one server-discovered streaming request-shape fix.

However Lead review found four unresolved pilot-level defects and one missing physical compatibility proof.

Do not begin the first-party Rukan Workspace yet.

First harden the Gateway as a stable substrate.

---

# 1. TRUE END-TO-END STREAMING

Current defect:

`StoreChat.complete(..., stream=True)` opens the vLLM request and then calls:

`response.read()`

before parsing SSE.

This means:
- upstream finishes;
- Rukan buffers the entire response;
- only then does downstream receive chunks.

That is not genuine chat streaming.

## Required architecture

Introduce a real upstream streaming path.

Conceptually:

```text
vLLM SSE socket
   ↓
incremental parser
   ↓
Gateway streaming iterator
   ↓
downstream SSE client
```

Do not buffer the full completion.

Use a bounded incremental parser.

Requirements:
- process upstream SSE line/event incrementally;
- forward content deltas as they arrive;
- extract final upstream usage when reported;
- emit downstream usage exactly once;
- emit final `[DONE]`;
- close upstream response/socket on downstream generator close;
- no response text persisted;
- no full-response buffering for accounting.

## Accounting under streaming

Streaming usage event is recorded once.

Cases:
- normal completion;
- upstream sends final usage;
- upstream closes without usage;
- client disconnects;
- upstream disconnects;
- timeout;
- malformed event;
- error event.

If token usage is unavailable:
- record `not_recorded`;
- do not estimate from buffered content.

If upstream completed execution but client disconnected:
- record actual executed usage if known;
- otherwise record unresolved counts.

## Backpressure

Do not pre-read the entire response faster than downstream can consume.

A bounded read buffer is acceptable.

## Measurements

Add:
- Gateway time-to-first-chunk;
- total request duration where current contracts permit;
- do not overload existing latency semantics silently.

If introducing TTFC/TTFB into product metrics is too large for v0.4, use it in acceptance evidence only.

## Tests

Deterministic fake SSE upstream:
- chunk 1;
- deliberate pause;
- chunk 2;
- final usage;
- done.

Assert downstream receives chunk 1 before fake upstream emits chunk 2/final usage.

Also test:
- client generator close after first chunk;
- upstream error;
- malformed SSE;
- final usage absent;
- concurrency counters released after all paths.

Physical server:
- prove visible incremental output timing.

---

# 2. ENTERPRISE OIDC DISCOVERY / JWKS ROTATION

Current production class uses a static injected JWKS.

Keep static JWKS for deterministic tests.

Add a production verifier/provider.

Suggested architecture:

```text
IdentityAssertionVerifier
   |
   +-- StaticJwksVerifier      (tests)
   |
   +-- OidcDiscoveryVerifier  (production)
```

Use mature libraries.

Do not implement JWT cryptography manually.

## Configuration

Required:
- issuer;
- audience;
- discovery URL derived from issuer or explicit override;
- supported algorithms allow-list;
- clock skew;
- connect/read timeout;
- cache TTL;
- optional CA/trust configuration through normal platform/TLS mechanisms.

Production defaults:
- HTTPS discovery;
- HTTPS JWKS;
- issuer match required.

Local test issuer may explicitly use HTTP.

## Discovery

Fetch:
`/.well-known/openid-configuration`

Validate:
- issuer in discovery equals configured issuer;
- `jwks_uri` valid and allowed;
- signing algorithms intersection is acceptable where exposed.

## JWKS

Cache keys.

On token with unknown `kid`:
- refresh JWKS once;
- retry verification;
- unknown after refresh => fail.

Avoid refetch for every bad token.

Bound cache and refresh frequency to prevent attacker-driven request storms.

## Failure

If discovery/JWKS unavailable:
- fail authentication closed;
- do not use stale keys beyond a deliberately documented stale-if-error policy, if any.

Simplest acceptable v0.4 policy:
- cached valid keys usable until cache TTL;
- after TTL and refresh failure, auth unavailable.

Document.

## Tests

Use local fake OIDC server:
1. discovery + key A;
2. token A succeeds;
3. rotate server to key B;
4. first token B causes bounded refresh and succeeds;
5. token signed by removed/unknown key fails;
6. wrong issuer;
7. wrong audience;
8. expired;
9. future nbf;
10. unsupported alg;
11. malformed discovery;
12. JWKS timeout.

Physical diagnostic:
- run standards-compatible test issuer;
- Gateway uses discovery path, not injected static JWKS.

---

# 3. API CREDENTIAL SCOPE ENFORCEMENT

API credentials are explicit scoped credentials.

Scopes must be enforced by route.

## Required matrix

For `api_credential` principals:

### `GET /v1/models`
Require:
`models`

### `POST /v1/chat/completions`
Require:
`inference`

### `GET /v1/me/usage`
Require:
`self_usage`

### `GET /v1/me`
Authenticated identity is sufficient.

It may show current policy/capabilities, but never secrets.

### MCP

Choose and document one v0.4 policy.

Preferred minimal policy:

Add credential scope:
`mcp`

Then:
- MCP route requires `mcp`;
- user must also have effective `mcp_use=allow`;
- server must be approved.

If adding scope creates unnecessary migration complexity, alternative:
- MCP rejects all `api_credential` principals;
- MCP requires OIDC in v0.4.

Cursor should choose the cleaner implementation and explain why.

Do not let an `inference`-only key call MCP.

## Scope/Access intersection

Credential scope never grants capability.

Effective permission is:

```text
credential scope
AND
current user AccessContext
AND
resource/model/MCP policy
```

Suspension/revocation overrides.

## Tests

Create credentials with each individual scope and combinations.

Test every route.

Test revoked and expired.

Test suspended user.

Test user policy denied despite scope.

---

# 4. CRASH-CONSISTENT USER/DEPLOYMENT ACCOUNTING

Current implementation writes one inference request into two stores separately:

```text
TelemetryStore.record_usage(InferenceUsage)
        ↓
GatewayLedger.record(PrincipalUsage)
```

A crash between writes can permanently break:

`SUM(user usage) == employee deployment usage`.

This must be corrected before confidence.

## Required invariant

Each executed employee Gateway request has one canonical durable usage fact.

That fact contains:
- one usage id;
- request id;
- Rukan user id;
- one accounting team;
- client id;
- auth method;
- instance/model/runtime;
- input/output tokens;
- latency/outcome;
- occurred_at;
- no prompt/response.

From this single fact derive:
- per-user analytics;
- employee deployment usage;
- telemetry/report aggregation.

## Preferred design

Create a canonical customer-local:

`GatewayUsageEvent`

or equivalent.

Persist it transactionally in one durable store.

Then use idempotent projections:

```text
GatewayUsageEvent
    |
    +--> Principal/User analytics projection
    |
    +--> InferenceUsage / telemetry projection
```

Track projection state/cursors.

Because `usage_id` is stable and destination writes are idempotent, retries converge.

## Alternative

A transactional outbox spanning existing stores is acceptable if it proves equivalent behavior.

Do not attempt fragile cross-database "best effort" ordering.

## Required failure behavior

If canonical append succeeds but projection fails:
- request result may still be returned if product policy allows;
- accounting status becomes degraded/pending;
- background/on-next-operation reconcile retries;
- Admin shows projection_pending/degraded;
- no loss.

If canonical append fails:
- do not claim the request is fully accounted;
- record local degraded accounting state where possible.

Inference must not be repeated merely to repair accounting.

## Tests

Inject failure:
1. canonical append succeeds;
2. deployment projection fails;
3. process restart;
4. reconciliation;
5. exactly one deployment record and one principal projection.

Also inverse destination failure.

Repeated reconcile:
- idempotent.

Crash before canonical commit:
- no event.

Crash after canonical commit:
- event recovered.

Duplicate usage id:
- not double counted.

## Admin reconciliation

States:
- `match`;
- `projection_pending`;
- `degraded`;
- `mismatch`.

Do not render a pending projection as corruption.

---

# 5. GATEWAY SECURITY / PRODUCT COHERENCE AUDIT

After corrections, re-audit:

- no Serve/vLLM endpoint exposed;
- exact READY instance only;
- model filtering;
- suspended/deactivated user;
- binding conflict;
- credential scopes;
- concurrency limits;
- body/message bounds;
- TLS configuration;
- trusted reverse-proxy handling;
- errors do not leak internals;
- bearer tokens absent from logs/stores;
- user cannot query another user's usage;
- vendor telemetry has no user id/name/email;
- Command Center contains no prompt.

Test thread/process restart.

---

# 6. LIBRECHAT PIN — RECORD TRUTHFULLY

Current adapter intentionally pins:

- LibreChat `v0.8.8-rc4`;
- commit `361553f3322d7b9bb547d0a9c2c5aaefc2934901`;
- container manifest digest
  `sha256:929f4491cb9a87d6beb02e9e9ce9a54d4ee05bc56b65b1debe5b1f28a327a4fb`.

As of Lead verification, GitHub/LibreChat still identifies rc4 as a pre-release,
while v0.8.7 is the latest stable tagged image.

The rc4 choice is allowed because its OpenID/MCP header behavior is the capability
being intentionally tested.

Docs/UI must state:
- adapter release = pinned pre-release compatibility target;
- not Rukan core dependency.

Do not call it a stable LibreChat release.

Before confidence:
- verify the digest again;
- do not silently follow a newer rc.

---

# 7. PHYSICALLY RUN LIBRECHAT

The A40 diagnostic images did not contain Docker, so LibreChat was never actually
started.

That evidence is insufficient for adapter acceptance.

## Test environment requirement

Use a host/test topology capable of running the pinned LibreChat artifact.

Preferred options in order:

1. supported server with Docker/container engine already available;
2. Rukan's existing container-execution capability if it can run the container
   honestly without weakening product architecture;
3. a separate inexpensive CPU/container-capable test host for LibreChat while
   Gateway/model remain on the GPU host, if the existing provider/tooling supports
   this safely within cost policy.

Do NOT:
- install Docker through unsafe privileged host mutation if not allowed;
- change the adapter to a source checkout just because Docker is absent;
- mark config-render tests as physical LibreChat proof.

## LibreChat physical proof

Use the exact pinned image/digest.

Run required supporting services.

Use a real test OIDC issuer through discovery.

Prove:
- LibreChat starts;
- browser/login flow or equivalent real session flow;
- OIDC token reuse enabled/configured as needed;
- custom Rukan endpoint;
- live OpenID bearer forwarded to Gateway;
- `GET /v1/models`;
- non-streaming chat;
- true streaming chat;
- Rukan usage fields;
- Rukan authorization denies suspended/unprovisioned user;
- no direct Serve endpoint;
- MCP broker endpoint with live identity;
- allowed user tool call;
- denied user tool call;
- ordinary chat still works after MCP denial.

Do not inspect or edit LibreChat database to enforce Rukan policy.

Capture:
- LibreChat version;
- image digest;
- adapter generated config;
- health;
- evidence.

---

# 8. AGENT CLAIMS

LibreChat Agent Builder was not physically tested.

Until it is:
- keep Agents capability as client-local / unqualified;
- do not claim Rukan agent governance is physically proven.

For v0.4 confidence, Agent Builder is OPTIONAL unless it can be tested without
broadening scope.

The hard product gate is:
- Gateway;
- users;
- usage;
- LibreChat chat;
- MCP.

Agent Builder may remain next-stage functionality for the native Rukan Workspace.

---

# 9. LOCAL QA BEFORE SERVER RETEST

Run:

- focused streaming tests;
- OIDC discovery/JWKS rotation tests;
- route×scope matrix;
- canonical usage/projection failure injection;
- reconciliation/restart tests;
- MCP security tests;
- full `tests/machi`;
- `tests/acceptance_lab`;
- ruff;
- mypy strict;
- Admin Vitest/typecheck/build;
- Command Center Vitest/typecheck/build;
- wheel build/isolated verify.

Update:
`docs/machi/RUKAN-USER-ACCESS-GATEWAY-V0.4.md`

and debt/audit docs.

---

# 10. RESUME V0.4 SERVER DIAGNOSTICS

Existing diagnostics:

- D1: found `stream_options` non-streaming defect;
- fix commit: `459d34b34f2238b5af108c0fe822c4637603b754`;
- D2: Gateway path clean;
- D2 did NOT run LibreChat;
- D2 predates Lead hardening fixes in this instruction.

Therefore clean-streak resets after these changes.

Run new diagnostics as:
- D3;
- D4;
- etc.

Maximum total diagnostic iterations before mandatory Lead review remains 8.

## Full-stack clean diagnostic

Must prove:

Underlying v0.3:
- clean install;
- model acquire;
- Deploy;
- Plan;
- ResourceManager;
- Serve READY;
- inference;
- STOP;
- RELEASE;
- telemetry.

v0.4:
- production OIDC discovery verifier;
- two allowed users;
- unprovisioned;
- suspended;
- Rukan API credentials and scope matrix;
- generic client;
- true streaming;
- per-user usage;
- exact eventual reconciliation;
- MCP allowed/denied;
- actual pinned LibreChat running;
- live OIDC forwarding;
- LibreChat chat through Gateway;
- privacy.

Two consecutive full-stack clean diagnostics required.

A config-only LibreChat test does not count as full-stack clean.

---

# 11. CONFIDENCE PHASE

After two consecutive full-stack diagnostics:

Freeze:
- Rukan source SHA;
- wheel SHA;
- LibreChat version/image digest;
- deployment manifest;
- identity test provider config/artifact;
- MCP fixture artifact.

Run C1/C2/C3 on fresh environments.

No Rukan code changes.

Each confidence run:
- full v0.3 deployment path;
- Gateway;
- OIDC;
- at least two users;
- generic client;
- LibreChat physical;
- true streaming;
- per-user accounting;
- exact reconciliation;
- MCP smoke;
- restart;
- privacy;
- teardown.

At least one:
- JWKS rotation;
- API credential revoke;
- Gateway restart;
- MCP denial;
- LibreChat restart.

Product defect:
- confidence resets;
- robust fix;
- diagnostics again.

---

# 12. SERVER/COST RULES

Use one GPU Pod at a time.

Prefer cheap supported NVIDIA.

For LibreChat container proof, an inexpensive separate host is allowed only if:
- tooling supports it;
- one-Pod limit is preserved if RunPod is used;
- no unrelated cloud infrastructure is introduced;
- cost stays within campaign target.

v0.4 campaign target remains <= $20.

Existing RunPod hard limits remain.

Hang:
- STOP owned Pod;
- preserve evidence;
- ask Daniel before termination.

---

# 13. DO NOT START NATIVE WORKSPACE YET

The next planned product increment is first-party Rukan Workspace.

Do not begin it in this instruction.

The purpose of this instruction is to make the Gateway contracts stable enough that
the first-party UI can be built on them without immediately redesigning:
- identity;
- streaming;
- usage;
- MCP;
- credentials.

---

# 14. TERMINAL STATUS

PASS:

`RUKAN_V0_4_USER_ACCESS_GATEWAY_SERVER_CAMPAIGN_PASS`

Only if:
- four Lead blockers closed;
- true streaming;
- enterprise OIDC discovery/rotation;
- scope enforcement;
- crash-consistent accounting;
- physical LibreChat proof;
- two consecutive clean full-stack diagnostics;
- C1/C2/C3 clean;
- no server/pilot blocker.

Otherwise:

`RUKAN_V0_4_USER_ACCESS_NOT_READY`

Do not merge v0.4 canonical.

---

# 15. PASTE BACK

Return:

A. terminal status
B. starting/final source SHA
C. streaming architecture
D. first-chunk evidence
E. streaming disconnect/error accounting
F. OIDC discovery architecture
G. JWKS rotation evidence
H. route/scope matrix
I. MCP credential-scope policy
J. canonical Gateway usage design
K. projection/reconciliation state machine
L. crash/failure-injection evidence
M. Admin reconciliation behavior
N. security audit
O. LibreChat pin truth/status
P. LibreChat physical environment
Q. real LibreChat OIDC login
R. live token forwarding
S. LibreChat chat/streaming
T. MCP through LibreChat
U. user/token reconciliation
V. diagnostic D3
W. later diagnostics
X. clean streak
Y. confidence C1
Z. confidence C2
AA. confidence C3
AB. final wheel SHA
AC. LibreChat digest
AD. usage totals
AE. privacy evidence
AF. cost
AG. remaining GA blockers
AH. git state
AI. cleanup
AJ. recommended native Workspace next step
AK. STOP

# END INSTRUCTION
