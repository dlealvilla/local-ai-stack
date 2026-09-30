# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-V0.5-NATIVE-WORKSPACE-AND-CORE-CLOSURE-001`
Status: `AUTHORIZED_AUTONOMOUS_BUILD_TEST_FIX_AND_CLOSE`

This instruction is directly authorized by Daniel.

The product direction has changed:

- first-party Rukan Workspace is now the DEFAULT employee frontend;
- LibreChat is OPTIONAL FALLBACK only;
- Docker/container runtime is NOT required for the default product;
- final closure no longer depends on physically running LibreChat;
- Rukan Workspace must be functional, simple, packaged, and product-owned;
- MCP and Agent Builder are first-party Rukan capabilities behind Rukan-owned
  identity/policy/usage contracts.

The priority is:

> functional and coherent over feature-heavy.

Do not add gadgets merely because Open WebUI has them.

Use Open WebUI only as product inspiration for useful core workflows:
- chat;
- conversation history;
- model selection;
- tools;
- reusable agents/presets;
- basic prompts/connections.

Do NOT copy its arbitrary Python plugin/function execution model.

---

# STARTING REPOSITORY TRUTH

Current implementation/evidence branch:

`rukan/user-access-gateway-v0.4@7a0e6180a1e0d40e1d26271d590502d447d761a1`

Current v0.4 product-closure source:

`7115852c984d8d5860bf29cdd49e2b42f61b12f7`

Canonical remains:

`machi@16084a5b21a0cca25bfe60070ad862832c80fb51`

The v0.4 backend has already proven:
- deployment lifecycle;
- User Gateway;
- OIDC discovery/JWKS rotation;
- credential scopes;
- true streaming;
- crash-safe canonical user usage;
- generic API;
- basic MCP policy;
- per-user token reconciliation.

Do not throw that away.

Create:

`rukan/native-workspace-v0.5`

from the current v0.4 branch tip.

---

# EXECUTION PLAN

Execute THREE phases in strict order.

## PHASE 1

Read and execute completely:

`control/instructions/RUKAN-V0.5-BACKEND-CONTRACT-FREEZE-001.md`

Required internal PASS:

`RUKAN_V0_5_BACKEND_CONTRACT_FREEZE_PASS`

Do not stop after PASS.

Continue directly to Phase 2.

## PHASE 2

Read and execute completely:

`control/instructions/RUKAN-V0.5-NATIVE-WORKSPACE-001.md`

Required internal PASS:

`RUKAN_V0_5_NATIVE_WORKSPACE_LOCAL_PASS`

Do not stop after PASS.

Continue directly to Phase 3.

## PHASE 3

Read and execute completely:

`control/instructions/RUKAN-V0.5-MCP-AGENTS-AND-CORE-CLOSURE-001.md`

This phase includes:
- official MCP SDK integration;
- open-source MCP interoperability fixture;
- Rukan Agent Builder;
- physical server diagnostics;
- iterative correction;
- confidence C1/C2/C3;
- final integration/merge/tag if all gates pass.

---

# FIRST-PARTY WORKSPACE — PRODUCT STANDARD

The default employee experience must look conceptually like:

```text
Employee
   |
   v
Rukan Workspace
   |
   +--> Chat / conversations
   +--> Model selector
   +--> My Usage
   +--> Tools / MCP
   +--> Agents
   +--> Connections
   |
   v
Rukan Workspace API / BFF
   |
   v
Rukan User Gateway
   |
   v
authorized READY ServingInstance
```

No browser direct access to vLLM/Ollama/Serve.

No Docker.

No Node runtime in production.

No LibreChat requirement.

---

# MINIMUM WORKSPACE FEATURE SET

Must work:

## Authentication
- enterprise OIDC login;
- logout;
- session expiry;
- suspended user denial.

## Chat
- new chat;
- persisted conversation history;
- rename/delete;
- real streaming;
- stop generation;
- regenerate;
- edit/truncate-and-continue if cleanly implemented;
- copy response;
- Markdown/code rendering;
- plain-language errors.

## Models
- allowed models only;
- model switch for subsequent turns.

## Usage
- per-response usage when reported;
- 24h/7d/30d/all totals;
- token coverage.

## Connections
- generic OpenAI-compatible API information;
- API credential metadata/revoke.

## MCP
- approved server list;
- tool discovery;
- tool enablement;
- tool invocation;
- resources/prompts discovery where easy/useful.

## Agents
- create/edit/archive;
- system instructions;
- model;
- approved tools;
- use in chat;
- bounded tool loop where selected model supports tool calling.

---

# EXPLICITLY DEFERRED UNLESS TRIVIAL

Do not delay closure for:
- RAG/document knowledge;
- image generation;
- audio;
- voice;
- collaborative channels;
- rich notes editor;
- full plugin marketplace;
- arbitrary server-side Python;
- arbitrary JS plugins;
- SCIM;
- general RBAC rewrite;
- mobile apps;
- learned memory;
- autonomous long-running agents;
- complex multi-agent orchestration.

These belong after the core product is closed.

---

# MCP DIRECTION

Use the OFFICIAL current stable MCP SDK.

Rukan Workspace is the MCP host/client product.

Rukan policy remains authoritative.

Use official open-source reference servers only for interoperability testing.

Preferred broad test fixture:
- official **Everything** reference server from `modelcontextprotocol/servers`
  when development Node/npx is already available.

Also build a tiny deterministic acceptance MCP server using the official SDK for:
- CI;
- server campaign;
- no-Node environments.

Do not call reference MCP servers production-hardened.

Do not create a proprietary MCP protocol fork.

---

# LIBRECHAT

Keep:
- LibreChatAdapter;
- compatibility metadata;
- fallback configuration path.

Change:
- not default;
- not product authority;
- no Docker validation required for core closure;
- no further effort unless it breaks the adapter contract or is trivial to maintain.

The first-party Rukan Workspace is the tested default.

---

# SECURITY BOUNDARY

Rukan is not a cybersecurity suite.

But the product must provide sane application security and remain compatible with:
- enterprise IdP;
- reverse proxy;
- private network;
- VPN/ZTNA;
- WAF/load balancer;
- enterprise PKI;
- SIEM/log collection.

Required in product:
- OIDC;
- Authorization Code + PKCE;
- secure browser session;
- HttpOnly cookie;
- CSRF protection;
- TLS support;
- trusted proxy boundary;
- no direct model port;
- no bearer in localStorage;
- no arbitrary code plugins;
- content isolation by user;
- MCP allow-list/policy;
- local customer content;
- privacy-safe vendor telemetry.

Do not build:
- VPN;
- firewall;
- WAF;
- SIEM;
- endpoint security;
- proprietary IdP.

---

# CONTENT OWNERSHIP / PRIVACY

Rukan Workspace DOES persist conversation content locally.

That is intentional.

The previous operational rule "Rukan does not persist prompts/responses" applies to
operational analytics/vendor telemetry, not to the customer-facing conversation
product.

Customer owns and controls:
- conversations;
- agent instructions;
- MCP tool content;
- saved prompts.

They remain customer-local.

Vendor Command Center receives none of that content.

---

# AUTONOMOUS DEFECT CORRECTION

The user explicitly authorizes iterative correction.

For any normal product defect:

```text
evidence
  -> classify
  -> violated invariant
  -> regression test
  -> robust design
  -> implement
  -> commit
  -> QA
  -> immutable artifact
  -> retest
```

Do NOT stop on:
- ordinary code bugs;
- UI bugs;
- migration bugs;
- test failures;
- one unavailable GPU SKU;
- one server image limitation;
- lack of Docker.

Use another already-supported NVIDIA host if needed and Rukan itself evaluates it
as feasible.

Stop only for:
- safety/hang rule;
- provider authentication impossible;
- budget boundary;
- genuinely unresolved product decision outside these instructions.

---

# PHYSICAL TESTING

No Docker.

Default physical topology:

```text
NVIDIA server
  |
  +-- Rukan Admin
  +-- Rukan Workspace
  +-- Rukan User Gateway
  +-- vLLM / model
  +-- Python synthetic OIDC issuer
  +-- Python official-SDK MCP acceptance server
```

Everything should be runnable from the Rukan artifact + Python/runtime dependencies.

The Workspace static frontend is served from the built wheel.

---

# SERVER CAMPAIGN STANDARD

Before final PASS:

- two consecutive clean full-stack diagnostics;
- then C1/C2/C3 fresh confidence on one frozen candidate.

A code change resets the clean diagnostic streak.

A confidence defect:
- resets confidence;
- fix;
- diagnostics;
- new confidence sequence.

Use small models and lowest-cost supported NVIDIA hosts.

This is product confidence, not performance benchmarking.

---

# PHYSICAL PRODUCT PROOF

The physical campaign must prove:

- install;
- model acquire;
- Plan;
- ResourceManager;
- Serve;
- Workspace;
- OIDC login;
- User Gateway;
- real chat;
- real streaming;
- stop;
- regenerate;
- conversation persistence after restart;
- My Usage;
- generic API client;
- credential revoke;
- MCP tools;
- Agent Builder;
- agent chat;
- suspension;
- backup/restore in at least one run;
- bounded concurrency in at least one run;
- STOP/RELEASE;
- telemetry privacy;
- no content in Command Center.

If the physical model cannot call tools:
- automatic agent tool loop must pass locally using deterministic tool-capable
  fixture;
- physical server must still prove MCP discovery/manual invocation and
  instruction-only agent chat;
- capability shown truthfully.

Do not use brittle prompt-based fake tool calling.

---

# FINAL CORE PRODUCT CLOSURE

The product is closed only for the validated current product path.

Validated closure target:
- NVIDIA;
- native/vLLM;
- first-party Rukan Workspace;
- enterprise OIDC;
- Rukan User Gateway;
- local conversations;
- per-user usage;
- MCP;
- Agents.

Do NOT claim:
- AMD production validation;
- macOS production validation;
- every runtime/hardware family.

Keep those as explicit coverage debt.

---

# FINAL MERGE AUTHORIZATION

If all required diagnostics/confidence and closure audit pass, Cursor is authorized
to:

1. open final PR to `machi`;
2. inspect exact diff;
3. verify no secrets/test junk;
4. merge;
5. fetch canonical;
6. run post-merge smoke;
7. tag truthfully, suggested:

`checkpoint/rukan-core-product-closed-nvidia-vllm-<shortsha>`

8. update control state.

Do NOT merge on NOT READY.

---

# TERMINAL STATUS

Success:

`RUKAN_V0_5_NATIVE_WORKSPACE_AND_CORE_PRODUCT_CLOSED`

Failure/incomplete:

`RUKAN_V0_5_NATIVE_WORKSPACE_PRODUCT_NOT_READY`

---

# FINAL PASTE BACK

Return one complete report containing:

A. terminal status  
B. starting branch/source  
C. Phase 1 result  
D. provider config authority  
E. browser OIDC/session design  
F. preflight  
G. backup/restore  
H. MCP TLS/network correction  
I. Phase 2 result  
J. Workspace architecture  
K. conversation schema  
L. login/logout  
M. chat features  
N. streaming/stop/regenerate  
O. model selector  
P. conversation history/search/export  
Q. My Usage  
R. Connections/API credentials  
S. Markdown/security  
T. Phase 3 result  
U. official MCP SDK/version  
V. official/reference MCP interoperability  
W. deterministic MCP acceptance server  
X. MCP catalog/policy  
Y. AgentDefinition  
Z. Agent Builder  
AA. agent execution/tool loop  
AB. tool-capability handling  
AC. Admin product controls  
AD. migrations  
AE. privacy  
AF. local QA  
AG. diagnostics  
AH. defects/fixes  
AI. clean streak  
AJ. C1  
AK. C2  
AL. C3  
AM. physical Workspace evidence  
AN. usage/token reconciliation  
AO. backup/restore evidence  
AP. concurrency evidence  
AQ. campaign spend  
AR. final wheel/build identities  
AS. remaining platform breadth debt  
AT. PR/merge SHA  
AU. checkpoint tag  
AV. recommended next phase  
AW. cleanup  
AX. STOP

# END MASTER INSTRUCTION
