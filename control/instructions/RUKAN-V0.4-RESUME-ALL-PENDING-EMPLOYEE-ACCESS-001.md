# RUKAN v0.4 — RESUME ALL PENDING EMPLOYEE ACCESS WORK

Instruction ID: `RUKAN-V0.4-RESUME-ALL-PENDING-EMPLOYEE-ACCESS-001`
Status: `AUTHORIZED_CONTINUE_ALL_PENDING_PRODUCT_AND_PHYSICAL_WORK`

This instruction resumes from:

- implementation branch: `rukan/user-access-gateway-v0.4`
- current evidence tip: `b2cc72610a081c92558201e67889bd220a5216c2`
- hardened product source: `cae6a352717b8717ec96d840eb45ab17fd080bca`
- canonical `machi`: `16084a5b21a0cca25bfe60070ad862832c80fb51`

Previous result:

`RUKAN_V0_4_EMPLOYEE_ACCESS_PRODUCT_NOT_READY`

because:
- the four Lead Gateway blockers were implemented;
- D3 physically proved the hardened Gateway path on A40;
- but the selected GPU host could not run the pinned LibreChat container;
- therefore no full-stack clean diagnostic existed;
- Phase 2 product closure was not started.

This instruction changes the sequencing rule.

The container-host limitation may block final physical acceptance, but it MUST NOT
block the remaining v0.4 product engineering.

The required execution order is now:

```text
A. Re-verify hardened Gateway
        ↓
B. Solve/test split LibreChat topology if possible now
        ↓
C. Implement ALL remaining Employee Access product closure
        ↓
D. Complete local/failure/load/migration QA
        ↓
E. Run full physical diagnostics using split topology
        ↓
F. iterate/fix/retest
        ↓
G. two consecutive clean diagnostics
        ↓
H. C1 → C2 → C3 fresh confidence
        ↓
RUKAN_V0_4_EMPLOYEE_ACCESS_PRODUCT_CLOSED
```

Do not begin the first-party Rukan Workspace in this instruction.

The next product increment remains the native Rukan Workspace after this backend is
closed.

---

# 0. READ ALL PREDECESSOR INSTRUCTIONS

Before coding, read:

- `control/CURRENT-INSTRUCTION.md`
- `control/STATE.json`
- `control/LATEST-PASTEBACK.md`
- `control/instructions/RUKAN-V0.4-GATEWAY-HARDENING-AND-CAMPAIGN-CONTINUE-001.md`
- `control/instructions/RUKAN-V0.4-EMPLOYEE-ACCESS-PRODUCT-CLOSURE-001.md`
- `control/OPEN-DECISIONS.md`

Repository truth overrides summaries.

Do not discard the already-correct hardening work.

---

# 1. RE-VERIFY HARDENED GATEWAY SOURCE

Inspect source `cae6a352717b8717ec96d840eb45ab17fd080bca`.

Verify that all four Lead blockers are genuinely implemented:

## 1.1 True streaming

- upstream SSE is consumed incrementally;
- first downstream content can be observed before upstream completion;
- generator close closes upstream;
- accounting executes exactly once;
- missing usage remains `not_recorded`;
- no response content persistence.

## 1.2 Production OIDC

- production discovery verifier exists;
- issuer/audience/signature/exp/nbf/sub enforced;
- discovery issuer match;
- JWKS caching;
- unknown `kid` refresh;
- bounded timeouts;
- static JWKS remains test-only path;
- no token logs.

## 1.3 Credential scopes

- models -> `models`;
- chat -> `inference`;
- self usage -> `self_usage`;
- MCP -> explicit `mcp` scope;
- current Rukan AccessContext still required.

## 1.4 Canonical Gateway usage

- one canonical Gateway usage fact;
- idempotent projections;
- telemetry projection can retry;
- principal/deployment reconciliation state is explicit;
- restart recovers pending projection;
- no double counting.

Run focused tests.

If any regression/fault is found:
- fix before proceeding;
- add regression;
- commit.

Do not repeat already-proven architecture merely for activity.

---

# 2. SOLVE LIBRECHAT PHYSICAL TEST TOPOLOGY

The previous A40 host could not run Docker or rootless Podman.

Do not retry the same assumption.

## Preferred topology

```text
OPERATOR / CPU ENVIRONMENT
  exact pinned LibreChat container
  Mongo
  test OIDC provider
  test MCP server
  browser/test client
            |
            | secure bounded test networking
            v
GPU SERVER
  Rukan
  Gateway
  vLLM
  model
```

The GPU host does not need Docker.

## 2.1 First choice: operator/development machine

Check whether the operator machine has a supported container engine:
- Docker Desktop / Docker Engine;
- OrbStack;
- Colima;
- Podman where actually functional.

Use the existing engine.

Do NOT install a large/untrusted system dependency automatically if it requires
administrator privilege or disrupts the machine.

If a safe already-installed engine exists, use it.

## 2.2 LibreChat container

Use exactly:

- version `v0.8.8-rc4`;
- commit `361553f3322d7b9bb547d0a9c2c5aaefc2934901`;
- image digest
  `sha256:929f4491cb9a87d6beb02e9e9ce9a54d4ee05bc56b65b1debe5b1f28a327a4fb`.

Do not follow latest.

Pin Mongo exact version/image digest if practical.

Record actual pulled digests.

## 2.3 Secure networking

The real product path must remain:

```text
LibreChat
   ↓
Rukan Gateway
   ↓
Serve/vLLM
```

Never:
`LibreChat -> vLLM`.

Preferred test transport:
- SSH local forward from operator host to remote Gateway;
- and reverse forwards if local test IdP/MCP must be reachable by remote Gateway.

Tunnels are transport only.

Rukan auth remains required.

## 2.4 TLS

Use campaign-local CA.

Generate certs for:
- Gateway test endpoint;
- OIDC issuer;
- MCP endpoint if using HTTPS.

Use explicit trust.

Do NOT:
- disable certificate verification;
- set global insecure flags;
- modify production code to trust all certs.

If container trust needs a mounted CA or supported Node trust variable, configure it
through adapter/test deployment, not application code hacks.

## 2.5 OIDC issuer topology

The same issuer identifier must be coherent for:
- LibreChat login/session;
- Gateway discovery.

If the issuer runs on operator machine:
- expose it to remote Gateway through a bounded reverse tunnel;
- use one stable issuer URL reachable on both sides through the test topology;
- preserve discovery issuer equality;
- do not rewrite `iss` claims between hops.

Choose a topology that works without weakening OIDC semantics.

## 2.6 MCP topology

The test MCP server may run on operator/CPU environment.

If Gateway broker needs to reach it:
- use reverse tunnel or approved private network path;
- exact endpoint must be approved in Rukan MCP catalog;
- do not bypass MCP target policy.

## 2.7 If operator container runtime is unavailable

Try one of these only if existing authorized tooling supports it:
- inexpensive CPU/container host;
- supported provider VM;
- a container-capable GPU image at the next physical diagnostic.

Do not invent permanent infrastructure.

Do not install Docker into an incompatible RunPod container merely to satisfy a test.

## 2.8 Crucial sequencing rule

If no container-capable environment can be obtained now:

DO NOT STOP THE ENTIRE RUN.

Record:
`LIBRECHAT_PHYSICAL_PENDING_ENVIRONMENT`.

Continue immediately into Sections 3–27 below.

Return to physical LibreChat validation after the remaining product work is complete.

Final PASS still requires LibreChat physical evidence.

---

# 3. EXECUTE THE COMPLETE EMPLOYEE ACCESS PRODUCT CLOSURE

Read and implement every applicable requirement in:

`control/instructions/RUKAN-V0.4-EMPLOYEE-ACCESS-PRODUCT-CLOSURE-001.md`

The requirements below emphasize the expected result and remove ambiguity.

---

# 4. COMPLETE USER LIFECYCLE

Ensure coherent states:

- active;
- suspended;
- deactivated.

Suspended:
- Gateway auth may identify user but access denied;
- API credentials denied;
- MCP denied;
- historical usage retained;
- reactivation works.

Deactivated:
- all access denied;
- credentials unusable;
- history retained;
- follow existing terminal/reactivation semantics.

Admin UI must clearly distinguish them.

Tests:
- active → suspended → active;
- active → deactivated;
- old API token after each transition;
- OIDC after each transition;
- MCP after each transition.

---

# 5. COMPLETE PROVISIONING / IDENTITY RECOVERY

Admin must be able to:
- create user;
- edit safe profile fields;
- update approved email;
- inspect stable Rukan user id;
- inspect identity binding;
- see issuer/subject fingerprint;
- see mismatch;
- reset binding;
- suspend/reactivate/deactivate.

Changing email may not silently change bound external subject.

Test:
- bound user email changed;
- current subject still handled according to documented policy;
- mismatch surfaced;
- reset;
- new subject binds;
- attacker/new subject cannot steal account.

Audit all actions.

---

# 6. IDENTITY PROVIDER CONFIGURATION

Introduce/complete provider configuration model.

At minimum:
- provider id;
- label;
- issuer;
- audience;
- discovery URL or derived;
- enabled;
- allowed algorithms;
- clock skew;
- trust/CA configuration metadata;
- last discovery;
- last JWKS refresh;
- last error category.

Architecture must permit multiple issuers even if UI initially enables one.

Do not encode one global issuer into User records.

Admin displays:
- configured;
- ready/degraded/error;
- issuer;
- audience;
- last key refresh;
- last auth error.

No signing key editing.

---

# 7. GATEWAY NETWORK/TLS PRODUCT MODES

Support/document:

## local/reverse-proxy mode
Gateway loopback/private backend behind customer proxy.

## private-network direct mode
explicit bind on private interface + TLS.

No default unauthenticated public bind.

Admin shows:
- bind;
- port;
- TLS on/off;
- external termination mode;
- trusted proxies.

If TLS config is invalid:
- fail startup;
- no silent plaintext fallback.

---

# 8. TRUSTED PROXY HARDENING

Only explicitly trusted proxy peers may influence forwarded address/scheme.

Test spoofed:
- X-Forwarded-For;
- X-Real-IP;
- Forwarded.

Identity is never trusted from those headers.

Document customer reverse-proxy contract.

---

# 9. API CREDENTIAL PRODUCT CLOSURE

Complete lifecycle:
- issue;
- show secret once;
- hash/verifier only;
- label;
- scopes;
- expiry;
- last used;
- revoke;
- self revoke where allowed;
- user suspend/deactivate invalidates immediately.

Define bounded TTL:
- safe default;
- minimum;
- maximum;
- explicit non-expiring only if product chooses to support it.

No plaintext secret persistence.

Tests across restart/migration.

---

# 10. CLIENT IDENTITY / CARDINALITY

Do not trust arbitrary client labels for analytics.

Derive or normalize:
- librechat;
- generic_api;
- rukan_future_workspace;
- credential label/category where bounded.

Unknown header:
- sanitize;
- cap length;
- map to generic if not approved.

Test high-cardinality attack.

---

# 11. EMPLOYEE MODEL ACCESS

Define policy seam for:
- deployment allowed employee models;
- optional team/user restrictions;
- selection permission.

Even if only one READY model exists:
- GET models uses policy;
- chat rechecks independently.

Employees cannot:
- acquire;
- deploy;
- admit;
- start/stop;
- release.

Those remain Admin authority.

Tests for list/use mismatch.

---

# 12. WORKSPACE ADAPTER CONTRACT

Formalize Rukan-owned Workspace adapter interface.

Required:
- adapter id;
- version;
- artifact/digest;
- mode;
- health;
- capabilities;
- configuration version;
- identity-forwarding support;
- streaming;
- usage display;
- MCP;
- agents;
- model-list behavior.

LibreChat implementation stays behind it.

Future Rukan Workspace must fit same high-level client boundary without migrations.

---

# 13. LIBRECHAT MODES

## managed
Rukan can generate:
- pinned compose/deployment;
- config;
- protected env;
- start/stop/status where execution adapter exists.

## external
Rukan can:
- generate configuration;
- validate supported version/capabilities where possible;
- connect without owning lifecycle.

If external mode implementation is deferred:
- contracts must support it;
- docs must describe limitation.

Do not access LibreChat DB.

---

# 14. LIBRECHAT UPGRADE POLICY

No auto upgrade.

A new supported LibreChat version requires:
- adapter capability review;
- config test;
- OIDC forwarding;
- models;
- chat;
- streaming;
- usage;
- MCP;
- physical smoke.

Supported version list explicit.

Unsupported version:
- fail or warn as documented;
- do not silently assume compatibility.

---

# 15. USER SELF-SERVICE

Complete authenticated:
- GET /v1/me;
- GET /v1/me/usage;
- own credential metadata;
- own revoke where allowed;
- allowed model/capability summary;
- connection information.

No cross-user access.

The current minimal /me page may remain provisional.

Do not build native chat UI yet.

---

# 16. USAGE RETENTION / RECONCILIATION

Canonical Gateway events must survive retention rules.

If raw events are compacted:
- preserve per-user/deployment totals;
- preserve token coverage;
- projections remain rebuildable or checkpointed.

Admin must expose:
- match;
- projection_pending;
- partial_token_coverage;
- degraded;
- mismatch.

If one request has unknown token counts:
- request count remains exact;
- token coverage indicates incompleteness;
- do not pretend totals are complete.

Tests beyond retention threshold.

---

# 17. TEAM ACCOUNTING

Revisit current "earliest active team" rule.

Prefer explicit accounting/primary team if low-risk.

If current rule remains:
- call it provisional;
- display it;
- no double counting.

Required invariant:
one request -> zero or one accounting team.

Tests with multi-team user.

---

# 18. MCP PRODUCT CLOSURE

Admin lifecycle:
- add;
- approve;
- disable;
- re-enable;
- archive/delete safely;
- connectivity test;
- last success/failure;
- auth method;
- sensitivity.

User-created MCP endpoints remain disabled unless mcp_connect explicitly allows.

---

# 19. MCP CREDENTIAL ARCHITECTURE

Do not assume the Rukan OIDC bearer is valid for every MCP server.

Define separation:

```text
User -> Rukan Gateway identity token

MCP server -> potentially different resource/audience credential
```

Create a replaceable credential provider seam for:
- none;
- test bearer;
- future OAuth code/PKCE;
- token exchange/OBO;
- service credentials.

v0.4 fixture may reuse a synthetic token only as documented test simplification.

Production architecture must not blindly forward one enterprise token to arbitrary MCP servers.

---

# 20. MCP TARGET HARDENING

Close SSRF/rebinding/redirect issues.

Requirements:
- metadata/link-local/multicast/unspecified denied;
- exact approved internal/private endpoints allowed;
- unapproved private denied;
- redirects cannot escape approval;
- DNS rebinding cannot change to forbidden destination after validation;
- bounded response body;
- bounded timeout.

Use robust transport rather than validate-then-resolve-again if possible.

Tests:
- metadata;
- redirect;
- rebinding fixture;
- private approved;
- private unapproved;
- oversized response.

---

# 21. MCP FAILURE ISOLATION / AUDIT

Tool server down:
- tool fails;
- normal inference still works.

Audit non-content only:
- user id;
- server;
- safe tool name if allowed;
- result category;
- latency.

Never:
- tool arguments;
- result body;
- OAuth token.

Test timeout/500/malformed/auth.

---

# 22. ADMIN EMPLOYEE ACCESS PRODUCT UX

Create coherent Admin sections.

At minimum surface:
- Users;
- Teams;
- effective access;
- Identity;
- Gateway;
- Workspace;
- API credentials;
- MCP;
- User Analytics;
- readiness/support.

Primary screens should answer:
- who has access?;
- who is bound?;
- who is suspended?;
- what models are usable?;
- which connections exist?;
- how much usage?;
- which subsystem is degraded?

Technical IDs under disclosure.

---

# 23. READINESS / PREFLIGHT

Implement non-mutating Employee Access preflight.

Checks:
- Gateway config/startability;
- TLS;
- OIDC discovery;
- JWKS;
- READY model;
- usage store;
- Workspace adapter;
- LibreChat version/config;
- MCP endpoints;
- state permissions.

Return:
- per-check PASS/BLOCKED;
- human text;
- JSON.

Do not mutate/deploy model unless explicit probe option.

---

# 24. SERVICE LIFECYCLE / OBSERVABILITY

Gateway:
- start;
- stop;
- restart;
- status.

Managed Workspace where supported:
- start;
- stop;
- restart;
- status.

Metrics:
- auth success/failure;
- active requests;
- overload;
- latency;
- streaming first-chunk timing if practical;
- upstream failure;
- usage projection pending;
- OIDC refresh errors;
- MCP failures.

No prompt/response/token secret logs.

Bound logging growth.

---

# 25. MIGRATIONS / BACKUP / RECOVERY

Version all customer-local state.

Test:
- accepted v0.3 -> final v0.4;
- fresh;
- current dev schema -> final if relevant.

No destructive reset.

Backup minimum:
- install identity;
- People/Teams;
- access;
- identity bindings;
- credential verifiers;
- canonical Gateway usage;
- MCP catalog;
- settings.

Test stopped-service backup/restore.

If projection DB corrupt:
- rebuild from canonical source where possible.

If identity authority DB corrupt:
- fail access closed.

---

# 26. CONCURRENCY / QUEUE / REQUEST LIMITS

Align Gateway limits with runtime safe concurrency.

Admin may lower, not silently exceed safe runtime bound.

Test:
- max global;
- max user;
- overload;
- disconnect cleanup.

If queue implemented:
- bounded length;
- bounded wait;
- cancellation.

No unbounded queue.

Request limits:
- body;
- message count;
- content size;
- max_tokens;
- duration.

---

# 27. STABLE CLIENT CONTRACT

Freeze v0.4 supported subset:

- GET /v1/models;
- POST /v1/chat/completions;
- streaming;
- usage;
- /v1/me;
- /v1/me/usage.

Document unsupported:
- full OpenAI API;
- multimodal if absent;
- tools/functions through Chat Completions if absent.

Add:
- service/build version endpoint or response metadata.

Stable error vocabulary:
- authentication_required;
- identity_not_provisioned;
- identity_binding_conflict;
- user_suspended;
- platform_access_denied;
- inference_access_denied;
- model_not_allowed;
- no_ready_model;
- scope_denied/insufficient_scope;
- overloaded;
- upstream_failure;
- accounting_degraded;
- MCP errors.

Document retryability.

---

# 28. LOCAL QA — COMPLETE BEFORE FINAL PHYSICAL CAMPAIGN

Run all predecessor local tests PLUS:

## identity
- provider config;
- discovery;
- JWKS rotation;
- mismatch/reset;
- suspend/deactivate.

## credentials
- lifecycle;
- scopes;
- TTL;
- restart;
- revoke.

## Gateway
- true streaming;
- client close;
- timeouts;
- overload;
- TLS;
- proxy spoofing.

## accounting
- projection fail/retry;
- retention;
- token coverage;
- team accounting;
- restart.

## MCP
- auth separation;
- SSRF/rebinding;
- redirect;
- failures;
- body limits.

## migration
- upgrade;
- rollback-safe failure.

## backup
- restore.

## privacy
canaries:
- user email;
- name;
- subject;
- API secret;
- bearer;
- prompt;
- response;
- MCP payload.

## bounded load
- >=10 synthetic users;
- mixed streaming/non-streaming;
- near concurrency limit;
- exact attribution/reconciliation;
- no deadlocks.

Full:
- tests/machi;
- acceptance_lab;
- ruff;
- mypy;
- Admin tests/typecheck/build;
- Command Center tests/typecheck/build;
- wheel build;
- clean install.

---

# 29. RETURN TO PHYSICAL LIBRECHAT

If not already solved in Section 2, try again now after all product engineering is complete.

Preferred:
operator/container environment + GPU inference host.

Do not stop before attempting the split topology thoroughly.

Required physical proof:

- exact pinned LibreChat image starts;
- Mongo dependency starts;
- real OIDC login/session;
- live access token forwarded;
- Gateway validates via discovery;
- models fetched from Rukan;
- non-streaming chat;
- true streaming;
- usage returned;
- suspended user denied on next call;
- MCP allowed user succeeds;
- MCP denied user fails;
- ordinary chat still works;
- no direct Serve route;
- no DB mutation.

If browser automation is available, use it for login/chat smoke.

Otherwise use the real LibreChat HTTP/session flow and document the limitation.

---

# 30. FULL-STACK DIAGNOSTIC CAMPAIGN

Continue diagnostic numbering from D3 evidence.

The next full-stack attempt is D4 unless repository campaign history uses another label.

A clean full-stack diagnostic requires:

## underlying v0.3
- artifact install;
- acquire;
- Deploy;
- Plan;
- ResourceManager;
- Serve;
- inference;
- STOP;
- RELEASE;
- telemetry.

## v0.4
- production OIDC discovery;
- rotation test on at least one diagnostic;
- two allowed users;
- unprovisioned;
- suspended;
- API credentials;
- scope smoke;
- generic client;
- LibreChat physical;
- true streaming;
- per-user usage;
- exact reconciliation;
- MCP allowed/denied;
- Gateway restart;
- privacy.

## product operations
- user suspend after session;
- credential revoke;
- LibreChat restart/failure isolation;
- MCP outage/failure isolation.

Two consecutive clean full-stack diagnostics required.

Any code change resets clean streak.

---

# 31. ITERATE ON EVERY DEFECT

The user explicitly authorizes continued correction.

Do not stop at the first product defect.

For each:
- evidence;
- classify;
- invariant;
- reproduce;
- test;
- design;
- fix;
- commit;
- QA;
- artifact;
- retest.

Do not use:
- hot patch;
- manual DB edit;
- insecure TLS;
- auth bypass;
- direct vLLM route;
- unpinned LibreChat latest.

Mandatory Lead review only if:
- safety;
- budget;
- missing provider authorization;
- major product decision not covered here;
- diagnostic count reaches the existing bounded campaign limit.

---

# 32. CONFIDENCE C1/C2/C3

After two clean full-stack diagnostics:

Freeze:
- Rukan source;
- wheel;
- Gateway API version;
- LibreChat version/digest;
- Mongo digest;
- test IdP artifact/config;
- MCP fixture;
- deployment manifest.

Run C1, C2, C3 fresh.

No code changes.

Each must prove:
- underlying v0.3 lifecycle;
- employee provisioning;
- OIDC;
- Gateway;
- generic client;
- LibreChat;
- streaming;
- usage;
- MCP;
- restart;
- privacy;
- cleanup.

Collectively include:
- JWKS rotation;
- API credential revoke;
- user suspend;
- Gateway restart;
- LibreChat restart;
- MCP outage;
- concurrency smoke.

Any product defect resets confidence after correction and diagnostics.

---

# 33. RESOURCE / COST POLICY

Existing RunPod policy remains.

One GPU Pod maximum.

GPU <= authorized hourly cap.

Use operator/local container runtime first for LibreChat.

If a separate CPU/container host is required:
- only use existing authorized provider/tooling;
- cheapest sufficient host;
- no permanent infrastructure;
- campaign total target remains <= $20 unless Lead later changes it.

If cost target would be exceeded:
- stop before new resource;
- report exact evidence gap.

Hang:
- STOP owned Pod;
- preserve evidence;
- ask Daniel before termination.

---

# 34. DOCUMENTATION / PRODUCT CLOSURE

Complete:
- RUKAN-EMPLOYEE-ACCESS-PRODUCT-CLOSURE-V0.4.md;
- RUKAN-USER-ACCESS-GATEWAY-V0.4.md;
- Architecture;
- Roadmap;
- Admin guide;
- privacy;
- MCP;
- migration/backup;
- server campaign;
- DEBT.

Do not mark deferred items closed without evidence.

---

# 35. FINAL PRODUCT REVIEW

Before terminal PASS verify:

- admin can provision user;
- real OIDC works and rotates;
- suspended user is cut off;
- generic client works without LibreChat;
- LibreChat works through adapter;
- LibreChat can fail without Gateway failing;
- live streaming is real;
- user accounting survives crashes;
- user totals reconcile;
- MCP governed and isolated;
- enterprise security layers can sit in front;
- migrations/backups work;
- no employee direct Serve access;
- remaining debt is non-blocking and explicit.

---

# 36. TERMINAL STATUS

PASS:

`RUKAN_V0_4_EMPLOYEE_ACCESS_PRODUCT_CLOSED`

Only with:
- all product implementation complete;
- physical LibreChat proof;
- two consecutive clean diagnostics;
- C1/C2/C3;
- no SERVER_ACCEPTANCE_BLOCKER;
- no PILOT_BLOCKER;
- all resources cleaned;
- branch clean/pushed.

NOT READY:

`RUKAN_V0_4_EMPLOYEE_ACCESS_PRODUCT_NOT_READY`

If physical container environment remains impossible after all development:
- still complete product engineering;
- report `LIBRECHAT_PHYSICAL_PENDING_ENVIRONMENT`;
- include exact remaining acceptance steps;
- do not call PASS.

Do not merge v0.4 canonical.

---

# 37. PASTE BACK

A. terminal status
B. starting/final SHA
C. re-verification of four Lead hardening fixes
D. chosen LibreChat physical topology
E. operator/container engine evidence
F. tunnel/TLS topology
G. OIDC issuer topology
H. user lifecycle closure
I. provisioning/identity recovery
J. identity provider product configuration
K. Gateway TLS/network/proxy
L. API credential lifecycle
M. client identity handling
N. employee model policy
O. Workspace adapter contract
P. LibreChat managed/external modes
Q. LibreChat upgrade policy
R. self-service APIs
S. canonical usage retention/reconciliation
T. team accounting
U. MCP catalog lifecycle
V. MCP credential/OAuth seam
W. MCP SSRF/rebinding/redirect closure
X. MCP audit/failure isolation
Y. Admin employee access UX
Z. readiness/preflight
AA. service lifecycle/observability
AB. migrations
AC. backup/restore
AD. degraded/corruption recovery
AE. concurrency/queue/request limits
AF. stable API/error contract
AG. local QA
AH. failure injection
AI. load/concurrency
AJ. actual LibreChat startup
AK. actual LibreChat OIDC/login
AL. actual LibreChat streaming
AM. actual LibreChat MCP
AN. generic client without LibreChat
AO. D4
AP. later diagnostics
AQ. clean streak
AR. C1
AS. C2
AT. C3
AU. final source/wheel/API versions
AV. LibreChat/Mongo digests
AW. usage totals/reconciliation
AX. privacy
AY. cost
AZ. remaining GA debt
BA. recommended first-party Workspace starting increment
BB. git state
BC. cleanup
BD. STOP

# END INSTRUCTION
