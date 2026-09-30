# RUKAN v0.5 — LEAD CLOSURE CORRECTION

Instruction ID: `RUKAN-V0.5-LEAD-CLOSURE-CORRECTION-001`
Status: `AUTHORIZED_CORRECT_PRELIMINARY_CLOSURE_AND_RE-EARN_PASS`

Repository truth at Lead review:

- canonical: `machi@124a1424ab20e6fd3e2ca96ee7fedb0cef539198`
- preliminary closure PR: #6
- tested source: `8c68bdedb71f0faeec957bc14eb8b5062f9807fb`
- evidence tree: `4f42c170ea624f10e0f07e56710376b8cae9b2e9`
- wheel SHA256: `29bef59fa62bccb536b5eeaf1a3ec4a195ce2dc4537bfb40ed87ac80522ec204`
- historical checkpoint:
  `checkpoint/rukan-core-product-closed-nvidia-vllm-124a142`

The preliminary closure implementation is substantial and remains canonical.
Do NOT revert it wholesale.

Independent Lead review WITHHOLDS final product-closure acceptance because the
merged implementation does not fully satisfy the requested Workspace/MCP/Agent
product contract and the physical campaign skipped several acceptance gates.

The authoritative interim status is:

`RUKAN_V0_5_PRELIMINARY_CORE_MERGED_LEAD_CORRECTION_REQUIRED`

Create correction branch:

`rukan/v0.5-lead-closure-correction`

from current canonical `machi`.

Do not delete or move the historical tag. It will be superseded by a corrected
checkpoint after PASS.

---

# 1. DO NOT REDESIGN THE WORKING CORE

Preserve:
- Install/Discover/Capacity/Foundation/Model/Plan/Admit/Serve;
- ResourceManager authority;
- first-party Rukan Workspace;
- customer-local conversation store;
- Rukan User Gateway;
- per-user canonical usage accounting;
- provider registry;
- OIDC discovery/JWKS rotation;
- credential scope model;
- Admin/Command Center separation;
- LibreChat fallback adapter;
- no-Docker default product.

This is a targeted closure correction.

---

# 2. WORKSPACE MODEL SELECTOR — MUST BE REAL

Current issue:
- backend model route exists;
- conversation has `model_id`;
- UI does not fetch/select models;
- new chat posts no model selection.

Implement the full simple path.

## UI

Chat must:
- fetch allowed models after login;
- render a model selector;
- select default allowed model;
- create conversation with selected `model_id`;
- display current conversation model;
- allow changing model for subsequent turns if current access allows;
- gracefully handle model disappearing/unavailable.

If one model:
- selector may be visually compact;
- it must still represent actual model identity.

## Backend

Add/update conversation model route or PATCH semantics.

Revalidate on every generation:
- model is still in current user-visible model list;
- model is currently READY/authorized.

Employee model change does NOT deploy/start another model.

## Tests

- one allowed model;
- two allowed-model fixture;
- denied model absent;
- direct forged model id denied;
- model changed mid-conversation;
- model unavailable after selection;
- UI test proves selected model is sent.

---

# 3. AGENT BUILDER — COMPLETE THE MINIMUM REAL PRODUCT

Current issue:
- create + archive only;
- no real edit;
- no model selector;
- no tool selector;
- no direct start-chat-with-agent path.

Required v0.5 Agent Builder:

## Agent fields

- name;
- description;
- instructions;
- selected allowed model or "current/default";
- selected approved MCP tool references;
- bounded max tokens;
- optional temperature only if current runtime supports it cleanly;
- active/archived;
- revision.

## UI

Agents screen:
- list;
- create;
- open/view;
- edit;
- save revision/update;
- archive;
- duplicate only if trivial;
- "Chat with agent" action.

Builder must show:
- model selector from user-allowed models;
- approved MCP servers/tools user may use;
- unavailable tool/model reason when previously configured item is no longer allowed.

## Execution

Creating a conversation from an agent must persist:
- agent id;
- selected model;
- agent revision/snapshot reference sufficient to explain historical chat.

A later agent edit must not silently rewrite the meaning of an old conversation.
Simplest acceptable:
- conversation stores agent revision number and/or immutable instruction snapshot.

## Permissions

- `agent_use` required to run;
- `agent_builder` required to create/edit/archive;
- agent model/tools still intersect invoking user's current permissions.

## Tests

- builder denied user;
- use-only user;
- create/edit/archive;
- model selection;
- tool selection;
- launch chat;
- later edit does not mutate old conversation semantics;
- archived agent cannot start new chat;
- direct API IDOR.

---

# 4. PRODUCTION TOOL CALLING — USE STANDARD OPENAI/VLLM SEMANTICS

Current issue:
the controller expects a custom `tool_call` SSE object, but production
`StoreChat` never emits one.

Fix the actual protocol path.

## 4.1 Gateway request contract

Extend bounded Chat Completions subset to support:
- `tools`;
- `tool_choice` where appropriate;
- assistant `tool_calls`;
- `tool` role messages;
- `tool_call_id`.

Do not claim full OpenAI parity.

## 4.2 Upstream request

When an agent has enabled tools and the selected model/runtime capability says
tool calling is supported:
- include OpenAI-compatible tool schemas;
- include runtime-specific configuration only through the runtime adapter or
  verified foundation configuration.

Do not hard-code one model parser globally.

## 4.3 Streaming parser

Parse standard streaming:
- `delta.tool_calls`;
- fragmented function name/arguments;
- tool call id;
- finish_reason as applicable.

Accumulate one bounded structured tool-call request.

Do not rely on model prose.

## 4.4 Non-streaming parser

Support ordinary tool_calls if agent execution uses non-stream fallback/tests.

## 4.5 Message validation

Allow:
- system;
- user;
- assistant;
- tool

with structured fields needed by tool calling.

Keep body/message size bounds.

## 4.6 Capability truth

Introduce/complete:
`tool_calling: supported | unsupported | unresolved`

derived from:
- selected model metadata;
- verified runtime support/config;
- not from UI assumption.

For unsupported model:
- agent still works as instruction preset;
- automatic tools clearly unavailable;
- manual MCP tool use remains available.

## 4.7 Runtime configuration

Research current vLLM official documentation for the exact tested version.

If vLLM requires:
- `--enable-auto-tool-choice`;
- model-specific tool parser;
- chat template;

then represent those as verified runtime/model capability configuration, not hidden
server-test flags.

No server hot patch.

## Tests

- fragmented streamed tool call;
- two tool calls rejected or bounded according to policy;
- tool arguments invalid JSON;
- unauthorized tool;
- tool result continuation;
- maximum rounds;
- model unsupported;
- normal chat unaffected.

---

# 5. PHYSICALLY PROVE ONE REAL TOOL-CAPABLE MODEL IF PRACTICAL

The previous SmolLM model honestly lacked tool-call support.

For corrected closure, attempt one small supported tool-capable model on an existing
supported NVIDIA/vLLM path.

Cursor must research current official vLLM docs/model support and choose a small
model that:
- fits A40 comfortably;
- has documented tool-call support;
- has a compatible parser/template for the pinned runtime;
- has a stable exact revision.

Do not guess.

Examples may be considered only after documentation verification; do not treat
this instruction as pinning a specific model.

Physical proof:
- Rukan agent with one approved MCP tool;
- model emits a real structured tool call;
- Rukan executes via MCP SDK;
- tool result is returned to model;
- final natural-language answer arrives.

If no suitable small model can be made to work within campaign cost/runtime:
- preserve exact evidence;
- automatic tool loop remains LOCAL_VERIFIED_ONLY;
- final closure may still PASS only if product UI truthfully marks automatic
  tool use experimental/unsupported on the physically tested model and the Lead
  accepts that bounded product definition.
- Do not fake with prompt parsing.

Prefer to close it physically.

---

# 6. MCP PROVIDER — COMPLETE USEFUL CORE, NOT JUST PING

Current official SDK adapter is tool-only.

Expand Rukan-owned normalized provider:

Required:
- server initialize/capability discovery;
- list_tools;
- call_tool;
- list_resources;
- read_resource;
- list_prompts;
- get_prompt;
- close/session cleanup.

Normalize SDK types into Rukan DTOs.

No SDK object leakage into Workspace/domain.

## Acceptance fixture

Expand deterministic official-SDK test server to include:
- tool `ping`;
- tool `add(a,b)`;
- resource `status://project`;
- prompt `summarize_status`.

## UI

Tools/Connections screen:
- server status;
- tool list;
- resource list;
- prompt list;
- tool description;
- argument schema.

Manual tool invocation:
- render a basic JSON-schema-derived form for primitive fields where easy;
- otherwise safe JSON argument input;
- do not always call first tool with empty args.

Resources:
- allow user to inspect/read if policy permits.

Prompts:
- allow user to insert/select prompt content if useful;
- no need for a complex prompt marketplace.

## Policy

All actions recheck:
- server approved/enabled;
- user `mcp_use`;
- server/tool/resource/prompt capability policy.

---

# 7. MCP NETWORK/TLS

Keep:
- original hostname/SNI;
- normal TLS hostname validation;
- redirect refusal;
- dangerous-address validation;
- admin-approved endpoint authority.

Do not reintroduce HTTPS-to-IP rewrite.

`R-04-01` may remain non-blocking if robust address pinning is not available in
the official SDK transport without weakening TLS.

Add tests for:
- HTTPS hostname preserved;
- redirect denied;
- dangerous resolved target denied;
- approved private target;
- DNS change between new connections is revalidated where hook permits.

Document residual risk precisely.

---

# 8. OIDC BROWSER FLOW — COMPLETE OIDC, NOT ONLY OAUTH+PKCE

Current flow has:
- code;
- PKCE;
- state;
- ID-token signature verification.

Missing:
- nonce.

Fix.

## Authorization request

Generate:
- state;
- PKCE verifier;
- nonce.

Store pending tuple memory-only with expiry.

Send `nonce`.

## Callback

Require:
- token response contains `id_token` for `openid` flow;
- verify signature/iss/aud/exp/nbf;
- verify returned token nonce equals pending nonce.

Do NOT fall back to `access_token` for browser identity.

Access token may be used later for APIs only under an explicit resource-server
contract.

## Library decision

Re-evaluate using Authlib or another mature OIDC client library for the browser
flow.

If a mature library can replace the hand-written authorization/token mechanics
without destabilizing the product, use it.

If not:
- document why;
- keep PyJWT verification;
- add complete protocol tests;
- do not claim a library-backed client.

## Tests

- valid nonce;
- missing nonce;
- wrong nonce;
- replayed state;
- expired state;
- token response without id_token;
- wrong issuer/audience;
- JWKS rotation.

---

# 9. SECURE COOKIE UNDER REVERSE-PROXY TLS

Current `Secure` flag depends only on direct backend TLS.

Fix external-origin semantics.

If configured `public_base` is `https://...`:
- session cookie MUST be Secure even if backend socket is HTTP behind trusted proxy.

Direct HTTP local development:
- Secure may be false.

Validate:
- public_base scheme;
- bind/TLS/proxy mode consistency.

Do not infer security from arbitrary forwarded headers.

Clear-cookie must use matching Secure/SameSite/Path attributes.

Tests:
- direct HTTPS;
- HTTPS public base + HTTP backend;
- local HTTP dev;
- invalid public base.

---

# 10. STATIC ASSET PATH CONTAINMENT

Replace string-prefix containment.

Use:
- resolved root;
- resolved target;
- `target.is_relative_to(root)` on supported Python;
- or equivalent robust component-based check.

Test:
- `../`;
- sibling directory with same path prefix;
- encoded traversal if HTTP parser exposes it;
- missing SPA path still falls back to index only when safe.

---

# 11. PER-MESSAGE USAGE MUST LINK TO CANONICAL USAGE

Current message table has `usage_id` but Workspace streaming does not receive the
canonical Gateway usage id.

Fix without duplicate accounting.

Preferred:
- Gateway stream emits a final Rukan metadata event carrying:
  - canonical `usage_id`;
  - input/output counts;
  - completion outcome;
- Workspace consumes it;
- assistant message stores same usage_id and counts.

This metadata event is Rukan extension around the OpenAI-compatible stream.

Generic `/v1` compatibility should remain standard-compatible:
- if emitting non-standard metadata would break clients, expose it only through
  Workspace-internal stream or a clearly namespaced event.

Tests:
- message usage_id exists;
- lookup matches canonical gateway event;
- regenerate creates a new usage id;
- interrupted request usage semantics;
- no double accounting.

UI:
- per assistant message show input/output/total when known.

---

# 12. WORKSPACE UI — CORE FUNCTIONALITY CORRECTIONS

The current UI is intentionally simple; keep that simplicity.

Add only the missing core:

## Chat
- actual model selector;
- actual agent selector / Chat with agent;
- per-message usage;
- clearer interrupted/error status.

## Markdown
Current safe text rendering is secure but very limited.

Use a small safe Markdown renderer if it can be added cleanly:
- paragraphs;
- headings;
- lists;
- tables;
- links;
- fenced code;
- inline code.

Raw HTML disabled.

If adding a dependency materially destabilizes packaging, keep the safe renderer
and improve only common cases.

## Keyboard
- Enter send;
- Shift+Enter newline.

## Agents
- proper builder fields from Section 3.

## Tools
- schema-aware tool selection/invocation;
- resources/prompts.

Do not add RAG, voice, images, themes, projects, or social features.

---

# 13. WORKSPACE SCHEMA MIGRATION

The preliminary `workspace.sqlite` schema is now canonical.

Do not rely only on CREATE TABLE IF NOT EXISTS forever.

Add migration framework/version transition for changes in this correction.

Migration must preserve:
- conversations;
- messages;
- sessions may be discarded only if explicitly acceptable;
- agents;
- existing usage references.

Test migration from preliminary schema 1 to corrected schema.

Unknown future schema fails closed.

---

# 14. ADMIN / PRODUCT TRUTH

Admin Workspace status must show:
- Rukan Workspace = default;
- API version;
- auth provider source;
- model availability;
- MCP status;
- Agent capability state.

If selected model lacks tool calling:
- show Agent chat supported;
- automatic MCP tool loop unavailable for that model.

Do not show universal "Agents with tools ready" when capability is unresolved.

---

# 15. PHYSICAL ACCEPTANCE GAPS — RE-RUN CORRECTLY

The previous physical evidence remains useful but does not satisfy the final Lead
gate.

Run a new correction campaign on the corrected artifact.

One GPU Pod at a time.

No Docker.

Use inexpensive supported NVIDIA.

## Diagnostic clean streak

MUST obtain:

D1_corrected CLEAN
then
D2_corrected CLEAN

on the same behavioral candidate line.

A code change resets to D1.

Only after two consecutive clean diagnostics:
- freeze source/wheel/assets;
- start confidence C1.

Do not count prior D2 as part of the corrected streak.

---

# 16. CORRECTED DIAGNOSTIC WORKFLOW

Each clean diagnostic must prove:

## Core deployment
- artifact-only install;
- discover/capacity;
- model acquire;
- Plan;
- ResourceManager;
- Serve READY.

## Workspace
- packaged assets;
- OIDC login with nonce;
- model selector visible/works;
- new conversation;
- >=5 turns;
- live streaming;
- stop;
- regenerate;
- restart;
- history preserved;
- per-message canonical usage linkage.

## Agents
- create;
- edit;
- model selection;
- tool selection;
- launch agent chat;
- archive.

At least one diagnostic should use the real tool-capable model if successfully
qualified.

## MCP
- list tools;
- call `add` or `ping`;
- list/read resource;
- list/get prompt;
- denied user path;
- outage isolation.

## Generic API
- credential;
- models;
- chat;
- streaming;
- revoke.

## Suspension
- successful session;
- admin suspends;
- next action denied.

## Backup/restore
At least one of the two clean diagnostics MUST:
1. stop relevant services;
2. take backup;
3. mutate/delete test Workspace state;
4. restore backup;
5. restart;
6. prove:
   - conversation;
   - agent;
   - provider config;
   - usage/accounting;
   survive.

## Command Center privacy
At least one clean diagnostic MUST:
- run a test Command Center receiver/intake through the product's permitted
  telemetry path;
- deliver an actual report;
- inspect received report/database;
- prove absent:
  - prompt canary;
  - response canary;
  - agent instruction canary;
  - MCP payload canary;
  - user email/name;
- aggregate permitted usage may be present.

Do not substitute local telemetry-file scan.

## Concurrency
At least one diagnostic:
- practical overlapping user requests;
- bounded overload;
- no cross-user message leakage;
- accounting reconciles.

---

# 17. LOCAL LOAD / ISOLATION

Before physical confidence:

Run >=10 synthetic Rukan users locally against fixture/upstream.

Mix:
- streaming;
- non-streaming;
- conversations;
- agents;
- MCP calls.

Prove:
- no IDOR/cross-user conversation;
- no agent cross-user access;
- per-user concurrency;
- global concurrency;
- no SQLite deadlock;
- canonical usage reconciles;
- sessions isolated.

This is not a performance benchmark.

---

# 18. CONFIDENCE C1/C2/C3

After corrected D1 + D2 clean:

Freeze:
- exact source SHA;
- wheel SHA;
- Workspace asset identity;
- API version;
- MCP SDK version;
- acceptance MCP fixture;
- exact model(s)/revision(s);
- OIDC fixture.

Run C1, C2, C3 fresh.

No code changes.

Each proves:
- install/deploy;
- OIDC login;
- model selector;
- Workspace chat;
- streaming;
- history;
- usage linkage;
- MCP;
- Agent Builder;
- generic API;
- restart;
- STOP/RELEASE;
- privacy.

Across the 3 include:
- JWKS rotation;
- API credential revoke;
- suspension;
- Workspace restart;
- MCP outage;
- backup/restore;
- concurrency.

If a product defect occurs:
- confidence resets;
- fix;
- D1/D2 again;
- new C1-C3.

---

# 19. FINAL LEAD-CORRECTED CLOSURE

PASS status:

`RUKAN_V0_5_CORE_PRODUCT_LEAD_CORRECTED_CLOSED`

Required:
- all Lead blockers above closed or explicitly reclassified non-blocking with
  evidence;
- two corrected clean diagnostics;
- C1/C2/C3;
- no SERVER_ACCEPTANCE_BLOCKER;
- no PILOT_BLOCKER.

Then:

1. open correction PR to `machi`;
2. inspect exact diff;
3. merge;
4. post-merge smoke;
5. update docs/control state;
6. create a NEW annotated checkpoint tag, suggested:

`checkpoint/rukan-core-product-lead-corrected-nvidia-vllm-<shortsha>`

7. mark historical
   `checkpoint/rukan-core-product-closed-nvidia-vllm-124a142`
   as superseded in docs/control only. Do not delete it.

If not ready:

`RUKAN_V0_5_CORE_PRODUCT_LEAD_CORRECTION_NOT_READY`

Do not create corrected closure tag.

---

# 20. COST / SAFETY

Existing RunPod rules remain.

One GPU Pod at a time.

Prefer low-cost supported NVIDIA.

Recommended additional correction campaign target <= $15.

If a tool-capable model requires materially more costly hardware:
- first try a small documented model on A40;
- do not escalate beyond existing hourly cap.

All owned Pods terminated after use.

Hang:
- stop;
- preserve evidence;
- ask Daniel before termination.

---

# 21. FINAL PASTE BACK

A. terminal status
B. starting canonical SHA
C. correction branch
D. model selector
E. Agent Builder
F. agent edit/revision
G. agent launch-chat path
H. production tool-call request contract
I. production tool-call streaming parser
J. real tool-capability model decision
K. physical real tool-call evidence
L. MCP SDK normalized provider
M. MCP tools/resources/prompts
N. MCP fixture
O. MCP network security
P. OIDC nonce
Q. ID-token-only browser identity
R. secure-cookie proxy behavior
S. static path containment
T. per-message usage-id linkage
U. Workspace UI corrections
V. schema migration
W. Admin capability truth
X. local security tests
Y. 10-user isolation/load
Z. corrected D1
AA. corrected D2
AB. actual Command Center privacy delivery
AC. physical backup/restore
AD. clean streak
AE. C1
AF. C2
AG. C3
AH. exact source/wheel/assets
AI. usage reconciliation
AJ. remaining non-blocking debt
AK. PR
AL. corrected canonical SHA
AM. corrected checkpoint tag
AN. historical tag supersession record
AO. cost
AP. cleanup
AQ. recommended next phase
AR. STOP

# END INSTRUCTION
