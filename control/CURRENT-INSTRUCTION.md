# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-V0.4-HARDEN-THEN-CLOSE-EMPLOYEE-ACCESS-001`
Status: `AUTHORIZED_TWO_PHASE_AUTONOMOUS_PRODUCT_CLOSURE`

This instruction is directly authorized by Daniel.

The objective is to finish the current v0.4 Employee Access backend as a stable,
supportable product foundation before the next planned increment:

> first-party Rukan Workspace / native chat frontend.

Do NOT build that native frontend in this instruction.

Execute two phases in strict order.

---

# PHASE 1 — GATEWAY HARDENING

Read and execute completely:

`control/instructions/RUKAN-V0.4-GATEWAY-HARDENING-AND-CAMPAIGN-CONTINUE-001.md`

Starting implementation source at Lead review:

`459d34b34f2238b5af108c0fe822c4637603b754`

Branch:

`rukan/user-access-gateway-v0.4`

Phase 1 must close, at minimum:

1. true end-to-end live streaming;
2. production OIDC discovery + JWKS rotation;
3. complete API credential route/scope enforcement;
4. crash-consistent user/deployment usage accounting;
5. actual pinned LibreChat physical execution/compatibility proof.

It also requires:
- local tests;
- security/privacy review;
- failure injection;
- physical diagnostics;
- two clean full-stack diagnostics;
- confidence evidence as defined in that instruction.

## Phase 1 iteration

Do not stop on a normal fixable product defect.

Use:

```text
evidence
 -> classify
 -> violated invariant
 -> regression
 -> robust design
 -> fix
 -> commit
 -> QA
 -> immutable artifact
 -> retest
```

Continue autonomously inside the authorized safety/cost/provider rules.

## Phase 1 PASS

The successful Phase 1 status is:

`RUKAN_V0_4_USER_ACCESS_GATEWAY_SERVER_CAMPAIGN_PASS`

If Phase 1 reaches that state:
- record exact source SHA;
- wheel SHA;
- LibreChat version/digest;
- QA;
- physical evidence;
- remaining non-blocking debt;
- push clean branch.

Do NOT stop for Lead review.

Continue immediately to Phase 2.

## Phase 1 NOT READY

If Phase 1 correctly terminates:

`RUKAN_V0_4_USER_ACCESS_NOT_READY`

because of:
- unresolved product blocker;
- safety;
- cost;
- provider authentication;
- architectural ambiguity requiring Daniel;

then:
- publish precise blocker/evidence;
- do NOT pretend Phase 2 can close the product;
- final master status is:
  `RUKAN_V0_4_EMPLOYEE_ACCESS_PRODUCT_NOT_READY`;
- STOP.

Provider stock alone should not prevent local/product engineering, but required
physical acceptance cannot be fabricated.

---

# PHASE 2 — COMPLETE EMPLOYEE ACCESS PRODUCT CLOSURE

After Phase 1 PASS, read and execute completely:

`control/instructions/RUKAN-V0.4-EMPLOYEE-ACCESS-PRODUCT-CLOSURE-001.md`

This is intentionally broader than the technical hardening phase.

It must turn the Employee Access subsystem into a coherent product covering:

- user lifecycle;
- user provisioning;
- identity-binding recovery;
- enterprise identity provider configuration;
- Gateway network deployment;
- trusted proxy semantics;
- TLS modes;
- API credential lifecycle;
- credential limits/scopes;
- client identity;
- model access;
- Workspace adapter product contract;
- LibreChat managed/external modes;
- LibreChat upgrade compatibility;
- user self-service;
- usage retention;
- token coverage/reconciliation;
- team accounting;
- vendor privacy boundary;
- MCP catalog lifecycle;
- MCP authentication;
- future OAuth/token-exchange seam;
- MCP SSRF/DNS rebinding safety;
- MCP audit/failure isolation;
- agent semantics;
- Admin employee-access UX;
- readiness/preflight;
- service lifecycle;
- observability/logging;
- migrations;
- backup/restore;
- corruption/degraded recovery;
- concurrency/queueing;
- request limits;
- stable errors;
- OpenAI-compatible subset definition;
- API versioning;
- LibreChat failure isolation;
- generic-client proof;
- LibreChat-independent user access;
- documentation;
- support evidence;
- local failure injection;
- bounded load/concurrency;
- iterative server diagnostics;
- three fresh confidence runs.

This phase is the product-standard closure.

Do not narrow it to only code required for the next happy-path demo.

---

# PRODUCT STANDARD

The completed v0.4 backend should support this stable product model:

```text
RUKAN ADMIN PLANE

Admin
  |
  +-- People
  +-- Teams
  +-- Access policy
  +-- Identity
  +-- Gateway
  +-- Workspace adapter
  +-- API connections
  +-- MCP
  +-- Analytics
  +-- Readiness/support


EMPLOYEE / APPLICATION PLANE

Enterprise IdP / Rukan API credential
                |
                v
        Rukan User Gateway
                |
       +--------+--------+
       |                 |
  LibreChat          generic client
  via adapter        OpenAI-compatible
       |                 |
       +--------+--------+
                |
        authorized READY model


TOOL / DATA PLANE

Workspace / future Rukan Workspace
                |
                v
        Rukan MCP governance
                |
                v
       approved MCP servers
```

Rukan owns:
- identity binding;
- policy;
- usage;
- routing;
- MCP policy;
- API credentials;
- Workspace adapter contract.

LibreChat remains replaceable.

Direct Serve/vLLM endpoints remain non-user-facing.

---

# NATIVE WORKSPACE BOUNDARY

The next planned product increment after this master instruction is:

`Rukan first-party Workspace`

Potential scope:
- native chat;
- streaming UI;
- My Usage;
- model selector;
- Connections;
- API credentials;
- MCP tools;
- later Agent Builder;
- later Git Brain / Company Brain.

Do NOT begin that UI here.

The purpose of this master instruction is to make all backend contracts stable enough
that the first-party frontend can consume them without redesign.

At Phase 2 completion, produce a concrete recommendation for the native Workspace
API/client boundary and first build increment.

---

# TESTING / ITERATION STANDARD

Both phases follow the same evidence standard.

For every defect:

1. preserve evidence;
2. classify;
3. identify violated invariant;
4. reproduce locally where feasible;
5. add regression;
6. design robust solution before patching;
7. implement in the domain owner;
8. commit/push;
9. run targeted QA;
10. run broader QA appropriate to changed architecture;
11. build immutable artifact;
12. retest physically when required.

No accepted:
- server hot patch;
- manual DB repair;
- weakened authentication;
- disabled TLS;
- fake test data replacing product state;
- hidden error suppression;
- special case for one RunPod host.

---

# VERSION CONTROL

Continue on:

`rukan/user-access-gateway-v0.4`

unless the detailed phase instruction explicitly creates an evidence/campaign branch.

Do not rewrite existing D1/D2 evidence.

Commit meaningful corrections separately.

Keep:
- source;
- tests;
- docs;
- sanitized evidence

traceable.

Do not commit:
- bearer tokens;
- API credential secrets;
- private keys;
- real user emails;
- prompts/responses;
- MCP payloads.

Synthetic `example.invalid` identities only.

Do not merge v0.4 to canonical automatically.

Final Lead review decides promotion.

---

# RUNPOD / PHYSICAL TEST POLICY

All existing RunPod rules remain binding.

One GPU Pod at a time.

Prefer the lowest-cost supported NVIDIA host that can prove the product.

Do not insist on one GPU SKU if another already-supported/feasible NVIDIA host works
without code changes.

For LibreChat/IdP/MCP commodity services:
- use same host if container-capable;
- or use a bounded low-cost CPU/container-capable environment where authorized;
- do not create permanent infrastructure.

Existing:
- hourly caps;
- balance floor;
- lifetime limit;
- retry limit;
- no network volume;
- hang rule

remain binding.

A hung owned Pod:
- STOP;
- preserve evidence;
- ask Daniel before termination.

---

# DIAGNOSTIC / CONFIDENCE EXPECTATION

The detailed phase instructions own exact numbering.

The master requirement is:

Before final Employee Access closure:
- all Lead hardening blockers closed;
- product closure requirements closed;
- two consecutive clean full-stack diagnostics on one behavioral candidate line;
- three fresh confidence runs on one exact frozen Rukan artifact + Workspace adapter
  compatibility target;
- underlying v0.3 install/deploy/inference/STOP/RELEASE still passes;
- no SERVER_ACCEPTANCE_BLOCKER;
- no PILOT_BLOCKER.

A code change after a clean diagnostic resets the clean streak.

A product defect during confidence:
- invalidates confidence streak;
- returns to correction/diagnostic;
- new candidate must earn confidence again.

---

# FINAL MASTER STATUS

PASS:

`RUKAN_V0_4_EMPLOYEE_ACCESS_PRODUCT_CLOSED`

Only if BOTH phases pass.

NOT READY:

`RUKAN_V0_4_EMPLOYEE_ACCESS_PRODUCT_NOT_READY`

Use if either phase cannot responsibly close.

Do not call partial completion PASS.

---

# FINAL PASTE BACK

The final paste-back must include:

## Phase 1
- hardening status;
- true streaming;
- OIDC discovery/JWKS rotation;
- credential scope matrix;
- canonical/crash-safe accounting;
- physical LibreChat proof;
- diagnostics/confidence evidence;
- exact source/wheel/LibreChat digest.

## Phase 2
- full Employee Access product architecture;
- user lifecycle/provisioning;
- identity recovery/provider configuration;
- Gateway deployment/TLS/proxy;
- credentials;
- model access;
- Workspace adapter;
- LibreChat lifecycle/upgrade;
- self service;
- usage/accounting/retention;
- team analytics;
- MCP catalog/auth/security;
- Admin UX;
- lifecycle/observability;
- migrations/backup/recovery;
- concurrency/request/error contracts;
- generic client compatibility;
- LibreChat independence;
- docs/support;
- failure/load tests;
- physical diagnostic/confidence campaign;
- cost;
- remaining GA debt;
- recommended first-party Rukan Workspace increment.

Then STOP for Lead review.

# END MASTER INSTRUCTION
