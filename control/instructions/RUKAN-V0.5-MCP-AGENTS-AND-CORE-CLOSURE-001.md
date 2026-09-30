# RUKAN v0.5 — MCP, AGENTS, PHYSICAL ACCEPTANCE, AND CORE PRODUCT CLOSURE

Instruction ID: `RUKAN-V0.5-MCP-AGENTS-AND-CORE-CLOSURE-001`
Status: `QUEUED_PHASE_3_AFTER_NATIVE_WORKSPACE_LOCAL_PASS`

This phase completes the first-party employee product and closes the validated
core Rukan infrastructure product.

No Docker is required.

LibreChat remains optional fallback only.

The first-party Rukan Workspace is the default employee product.

---

# 1. ADOPT OFFICIAL MCP SDK

Replace the hand-rolled partial MCP protocol path with an adapter built on the
official Model Context Protocol SDK.

Preferred:
- current stable official Python MCP SDK;
- bounded compatible dependency;
- Streamable HTTP for remote enterprise MCP;
- stdio only for local/developer/test integrations where explicitly used.

Do not make the browser an MCP client.

Architecture:

```text
Rukan Workspace
      |
      v
Workspace API
      |
      v
Rukan MCP Policy + McpClientProvider
      |
      v
Official MCP SDK
      |
      v
Approved MCP Server
```

Rukan remains authority for:
- which servers exist;
- which users/teams may see/use them;
- which tools may be bound to an agent;
- credential references;
- audit.

Official SDK owns:
- protocol negotiation;
- Streamable HTTP;
- session semantics;
- capability discovery;
- tools/resources/prompts protocol details.

Do not duplicate the entire protocol.

---

# 2. MCP CLIENT PROVIDER CONTRACT

Introduce a first-class abstraction such as:

`McpClientProvider`

Required operations:
- discover server;
- list capabilities;
- list tools;
- list resources;
- list prompts;
- call tool;
- read resource where allowed;
- get prompt where allowed;
- close/session cleanup.

Return normalized Rukan-owned DTOs.

Do not leak SDK object types through product layers.

Track:
- server id;
- protocol version;
- server identity/version;
- capabilities;
- last successful discovery;
- last error.

---

# 3. MCP SERVER CATALOG

Complete canonical server definition.

Minimum:
- server_id;
- display_name;
- description;
- transport;
- endpoint;
- enabled;
- auth mode;
- sensitivity;
- allowed capability types;
- created/updated;
- last discovery status;
- last success;
- last failure category.

Enterprise default:
- admin-approved servers only.

User-created arbitrary endpoints remain disabled unless explicitly granted later.

---

# 4. MCP AUTH / CREDENTIALS

Do not blindly reuse Rukan's OIDC access token for unrelated MCP resource servers.

Introduce a Rukan-owned credential-provider seam.

Supported v0.5 modes:

## none
For public/internal server requiring no auth.

## static/admin secret reference
Optional if current secure secret store exists cleanly.
Secret not in DB plaintext.

## test bearer
Acceptance fixture only.

Architect for future:
- OAuth Authorization Code + PKCE;
- on-behalf-of / token exchange;
- client credentials;
- per-user connection OAuth.

Do not overbuild those future modes now.

If no secure persistent secret store exists yet:
- ship `none` as production-supported v0.5;
- keep other modes experimental/test;
- do not invent weak secret storage.

---

# 5. MCP NETWORK SECURITY

Use the chosen SDK/HTTP client's normal TLS hostname validation.

Do not rewrite HTTPS hostnames to raw IP addresses in a way that breaks SNI.

Default product trust rule:
- only administrator-approved endpoints can be used;
- user arbitrary URL entry is off.

At approval and connection time:
- scheme must be http/https according to policy;
- production remote default = https;
- DNS resolution checked;
- metadata/link-local/multicast/unspecified/reserved dangerous targets rejected;
- redirects disabled or constrained to the same approved origin;
- private/internal endpoints permitted only because an admin explicitly approved
  that endpoint;
- timeouts bounded;
- response/message size bounded where SDK/client permits;
- connection count bounded.

If the HTTP client allows robust validated-IP pinning while preserving Host/SNI:
implement and test it.

If not:
- preserve TLS correctness;
- validate DNS before each new connection;
- disable redirects;
- rely on administrator-approved endpoint policy as primary SSRF boundary;
- document residual DNS-rebinding defense-in-depth debt.

Do NOT weaken TLS hostname verification.

---

# 6. MCP OPEN-SOURCE INTEROPERABILITY FIXTURES

Use official open-source MCP components for interoperability evidence.

## Required local interoperability

Use the official `modelcontextprotocol/servers` **Everything** reference server
if Node/npx is available in the development environment.

Why:
- tools;
- resources;
- prompts;
- broad protocol coverage.

Treat it as:
- reference/test fixture;
- NOT production dependency;
- NOT security-hardened enterprise server.

If npx is unavailable:
- do not install Node solely for production;
- use an official SDK example/reference server available through the chosen SDK;
- keep Everything interoperability as optional development evidence.

## Required CI-safe fixture

Build a tiny deterministic Rukan acceptance MCP server using the official SDK.

Expose:
- tool `add(a,b)`;
- tool `echo(text)`;
- resource `status://project`;
- prompt `summarize_status`.

Use Streamable HTTP.

This fixture:
- is tests/acceptance only;
- is not a product MCP server.

---

# 7. WORKSPACE MCP UX

Tools / Connections page must show:
- approved servers;
- status;
- tools;
- resource/prompt counts;
- descriptions.

For a server:
- connect/test;
- list tools;
- list resources/prompts where supported;
- admin-disabled state.

For user:
- no arbitrary endpoint textbox by default.

Conversation/agent:
- enable allowed tools.

Manual tool test:
- optional user-facing or Admin-only.
- if implemented, render JSON-schema-based input form where simple;
- raw JSON fallback is acceptable for advanced view.

---

# 8. TOOL CALL RENDERING

Conversation UI should render a compact tool event:

```text
Tool: project_status
Running...
✓ Completed
```

Expandable details may show:
- tool name;
- safe input summary;
- safe result content when it is part of the customer conversation.

Do not put tool arguments/results into operational logs/vendor telemetry.

Tool content may be stored inside the customer's conversation history because it is
part of the Workspace content product.

---

# 9. AGENT DOMAIN — RUKAN OWNS IT

Create canonical:

`AgentDefinition`
and optionally `AgentRevision`.

Minimum fields:
- agent_id;
- owner_kind user/team;
- owner_id;
- name;
- description;
- model selection/policy;
- system instructions;
- allowed MCP server/tool refs;
- bounded generation settings;
- active/archived;
- revision;
- created_at;
- updated_at.

Do not use LibreChat agent schemas.

No arbitrary code.

No uploaded plugins.

No executable scripts.

---

# 10. AGENT ACCESS

Current People capabilities:
- agent_use;
- agent_builder.

Rules:

## agent_use
User can invoke agents visible to them.

## agent_builder
User can create/edit/archive agents within allowed ownership scope.

Agent execution still intersects:
- platform access;
- inference access;
- model access;
- MCP access;
- actual server/tool policy.

An AgentDefinition cannot grant a capability the invoking user lacks.

---

# 11. AGENT OWNERSHIP / SHARING

Prioritize simple semantics.

Required:
- private user agent.

Desirable if straightforward:
- team agent owned by one team;
- users in active membership can use;
- edit requires agent_builder plus ownership/admin rule.

Do not build organization-wide marketplace/discovery.

Do not delay product for rich sharing.

If team ownership is too large:
- implement private agents now;
- schema supports team later;
- document.

---

# 12. AGENT BUILDER UI

Workspace Agents page.

Required:
- list;
- create;
- edit;
- archive/delete;
- duplicate if trivial;
- launch chat with agent.

Form:
- name;
- description;
- model;
- instructions;
- approved tools;
- max tokens;
- optional temperature only if reliably supported.

Show:
- tools unavailable because of current user policy;
- model unavailable;
- archived state.

Test agent before save is desirable but not required.

---

# 13. AGENT EXECUTION — SIMPLE TOOL LOOP

Build a bounded server-side agent runner.

Do not build autonomous long-running agents.

Maximum:
- configurable small number of tool rounds, default e.g. 4;
- max tools per round bounded;
- no recursive agent spawning;
- no background autonomy.

Flow:

```text
conversation
   +
Agent instructions
   +
allowed tool schemas
        ↓
model
        ↓
assistant content OR tool call
        ↓
if tool call:
  re-authorize
  call MCP
  append tool result
  repeat bounded
        ↓
final answer
```

---

# 14. MODEL TOOL-CALL CAPABILITY

Do not assume every model supports OpenAI tool calling.

Add capability truth:
- tool_calling = supported / unsupported / unresolved.

For tool-capable model:
- pass tool schemas using the runtime's supported OpenAI-compatible format;
- parse structured tool calls.

For model without tool support:
- agent still functions as instruction/system-prompt preset;
- tool-enabled agent displays tools unavailable for selected model;
- manual MCP tools remain available where product permits.

Do NOT implement brittle "please emit JSON" pseudo tool calling as the production
fallback.

---

# 15. EXTEND GATEWAY CHAT CONTRACT CAREFULLY

If needed for tool-capable models, extend Chat Completions subset to support:
- `tools`;
- `tool_choice`;
- assistant `tool_calls`;
- `tool` role messages.

Only expose fields the runtime path reliably handles.

Keep backward-compatible ordinary chat.

Add capability metadata.

Do not claim full OpenAI API parity.

---

# 16. AGENT STREAMING

For ordinary assistant content:
- stream live.

When tool call appears:
- Workspace may pause content streaming;
- render tool running;
- perform tool;
- continue next model round.

Keep implementation understandable.

Do not attempt token-by-token rendering of raw tool-call JSON if it complicates UX.

---

# 17. AGENT / MCP USAGE ACCOUNTING

Model calls:
- recorded as user_request;
- attributed to user;
- linked to conversation/agent internally;
- content excluded.

Tool calls:
- do not create model token usage;
- optional local audit event with latency/result;
- no tool payload in operational analytics.

An agent with 3 model rounds produces 3 inference usage events unless an existing
higher-level accounting model is introduced.

My Usage should still reconcile to all model requests.

Do not hide agent token cost.

---

# 18. SAVED PROMPTS

If not already implemented and simple:
- user-owned SavedPrompt;
- title;
- body;
- updated;
- insert into composer.

No complex variable system required.

Do not block closure for this.

---

# 19. WORKSPACE SETTINGS

Minimum:
- profile;
- current provider/session;
- default model if allowed;
- theme if supported;
- connection/API info;
- sign out.

Do not create dozens of preferences.

---

# 20. ADMIN AGENT/MCP VISIBILITY

Admin should see:
- MCP catalog/status;
- agent counts by owner type/status;
- not agent instructions/content unless customer admin product deliberately
  authorizes inspection later.

Default privacy:
- employee-created instructions are customer content;
- do not vendor-export.

Admin may disable agent builder globally through policy if existing access model
permits.

---

# 21. BACKUP / MIGRATION EXPANSION

Backup now includes:
- workspace.sqlite;
- agents;
- conversation content;
- saved prompts;
- MCP catalog;
- existing employee state.

Backup is customer-local sensitive content.

Do not include it in vendor support export.

Restore test:
- conversations preserved;
- agents preserved;
- tool bindings preserved;
- usage preserved;
- login/provider config preserved;
- no raw OIDC session tokens expected because sessions are ephemeral.

---

# 22. DATA RETENTION / DELETE

Conversation delete behavior must be implemented/documented.

Simplest:
- hard delete user-owned conversation/messages/tool events;
- durable usage records remain because accounting is separate.

Agent delete:
- archive preferred if referenced by historical conversations;
- historical conversation keeps display snapshot/reference.

Do not cascade-delete usage.

---

# 23. LOCAL SECURITY TESTS

Workspace:
- XSS in Markdown;
- javascript URL;
- HTML injection;
- CSRF;
- session fixation;
- expired session;
- logout;
- IDOR conversations;
- IDOR agents;
- B user reading A chat;
- suspend during active session.

MCP:
- unauthorized server;
- unauthorized tool;
- disabled server;
- redirect;
- dangerous address;
- oversized result;
- timeout;
- malformed response;
- protocol negotiation failure.

Agents:
- user without agent_builder cannot create;
- agent cannot use unauthorized model;
- agent cannot use unauthorized tool;
- archived agent cannot start new chat;
- bounded tool loop enforced.

---

# 24. LOCAL FUNCTIONAL ACCEPTANCE

Use:
- synthetic OIDC issuer;
- deterministic fake or reference model boundary;
- official MCP SDK test server.

Run:

## Chat
- login;
- new chat;
- 5 turns;
- streaming;
- stop;
- regenerate;
- restart;
- history.

## Usage
- per-message usage;
- My Usage;
- reconciliation.

## MCP
- discover;
- list tools;
- call add;
- read resource;
- get prompt;
- deny unauthorized user.

## Agents
- create agent;
- instructions;
- bind add/echo tools;
- chat;
- tool-call loop with deterministic tool-capable model fixture;
- agent result;
- edit agent creates revision if implemented;
- archive.

## Privacy
- prompt/response/tool/agent canaries absent from Command Center/vendor exports.

---

# 25. FULL QA BEFORE PHYSICAL

Backend:
- focused Workspace;
- MCP;
- agents;
- People;
- Gateway;
- migration;
- backup;
- security;
- full tests/machi;
- acceptance_lab;
- ruff;
- strict mypy.

Workspace:
- Vitest;
- TypeScript;
- Vite build;
- packaged-asset test.

Admin:
- Vitest;
- TypeScript;
- build.

Command Center:
- existing tests/build.

Artifact:
- wheel;
- clean venv;
- no source checkout;
- no Node runtime;
- no Docker.

---

# 26. PHYSICAL SERVER CAMPAIGN — NO DOCKER

Create a fresh physical acceptance campaign on a new branch if repository convention
benefits from it, e.g.:

`rukan/v0.5-native-workspace-server-campaign`

One supported NVIDIA GPU server at a time.

Install only the Rukan artifact and normal Python/runtime dependencies.

No Docker.

No LibreChat.

Use:
- Rukan Admin;
- Rukan Workspace;
- Rukan Gateway;
- vLLM;
- synthetic Python OIDC issuer;
- deterministic Python MCP acceptance server using official SDK.

Use real TLS where network crosses host boundaries.

For same-host test issuer, local HTTP may be allowed only as explicit acceptance
fixture; at least one confidence run should prove HTTPS identity discovery if
practical.

---

# 27. PHYSICAL DIAGNOSTIC USER MATRIX

Synthetic identities only.

## Ada
- provisioned;
- active;
- inference;
- model selection;
- Workspace;
- MCP;
- agent_use;
- agent_builder;
- API credential.

## Bob
- provisioned;
- active;
- Workspace/inference;
- MCP limited;
- agent_builder denied.

## Charlie
- valid IdP identity;
- not provisioned.

## Dana
- provisioned;
- suspended.

Use `example.invalid`.

No real employee information.

---

# 28. PHYSICAL DIAGNOSTIC WORKFLOW

A clean diagnostic must prove:

## Infrastructure
- artifact install;
- Discover/Capacity;
- model acquire;
- Plan;
- ResourceManager;
- Serve READY.

## Identity
- configure provider through Rukan Admin/product config;
- Workspace OIDC login;
- Ada binds;
- Charlie denied;
- Dana denied.

## Native Workspace
- assets from wheel;
- no Node/Docker;
- new chat;
- at least 5 turns;
- visible live streaming;
- stop one generation;
- regenerate;
- conversation survives Workspace restart;
- model list;
- My Usage.

## Generic API
- issue/retrieve test credential through allowed path;
- models;
- chat;
- streaming;
- revoke;
- denial after revoke.

## MCP
- official SDK acceptance server;
- discovery;
- tools;
- resource;
- prompt;
- allowed Ada;
- denied Bob according to configured policy;
- failure isolation.

## Agent
- create Rukan agent;
- use instructions;
- select model;
- tool binding;
- agent chat.

If current physical model is tool-call capable:
- prove automatic tool loop.

If not:
- prove instruction-only agent physically;
- prove automatic tool loop locally with deterministic tool-capable fixture;
- mark physical model capability accurately, not as product failure.

## Accounting
- exact per-user requests;
- token coverage;
- deployment reconciliation.

## Lifecycle
- Gateway/Workspace restart;
- user suspension after successful chat;
- next request denied;
- STOP;
- RELEASE.

## Privacy
- conversation canary not in Command Center;
- response canary not in Command Center;
- tool payload not in Command Center;
- agent instruction not in Command Center.

## Backup
At least one diagnostic:
- stopped-service backup;
- restore into test state;
- conversation/agent/usage preserved.

---

# 29. DIAGNOSTIC ITERATION

Run enough diagnostics to obtain:

**two consecutive clean full-stack diagnostics on the same behavioral candidate.**

Ordinary defects:
- evidence;
- regression;
- robust fix;
- commit;
- QA;
- new wheel;
- retest.

No arbitrary low diagnostic cap if remaining defect is straightforward and campaign
budget remains reasonable.

Mandatory Lead stop if:
- safety;
- provider auth;
- architecture decision outside this instruction;
- campaign cost would exceed the configured target.

Recommended campaign target:
<= $20 additional GPU spend.

Existing RunPod hard rules still apply.

---

# 30. CONFIDENCE C1/C2/C3

After two clean diagnostics:

Freeze exact:
- source SHA;
- wheel SHA;
- Workspace assets/build;
- API version;
- MCP SDK version;
- acceptance MCP fixture revision;
- OIDC fixture revision;
- model artifact/revision where practical.

Run 3 fresh confidence servers.

No product code changes.

Each:
- clean install;
- deploy;
- OIDC login;
- Workspace chat;
- streaming;
- history;
- usage;
- generic API;
- MCP;
- agent;
- restart;
- STOP/RELEASE;
- privacy;
- cleanup.

Across C1-C3 collectively include:
- JWKS rotation;
- suspended user;
- API credential revoke;
- Workspace restart;
- MCP outage;
- backup/restore;
- bounded concurrency smoke.

Product defect:
- confidence resets;
- fix;
- diagnostics;
- new C1-C3.

---

# 31. LOAD / CONCURRENCY PHYSICAL SMOKE

At least one diagnostic/confidence:
- >=10 synthetic users or equivalent concurrent principals if practical;
- bounded mixed streaming/non-streaming requests;
- near configured concurrency;
- no cross-user conversation leakage;
- no deadlock;
- overload bounded;
- accounting reconciles.

Keep model small.
This is robustness, not benchmark competition.

---

# 32. PRODUCT CLOSURE AUDIT

Before PASS answer YES with evidence:

1. Default employee client is first-party Rukan Workspace.
2. No Docker required.
3. LibreChat can be absent.
4. Admin config drives identity.
5. User can OIDC sign in.
6. User can chat with real model.
7. Streaming is live.
8. Conversation history persists locally.
9. User can stop/regenerate.
10. User can select allowed model.
11. User sees own usage.
12. Generic OpenAI-compatible access works.
13. Admin can provision/suspend.
14. Suspended user is denied immediately.
15. MCP official SDK interoperability works.
16. Admin-approved MCP tools are usable.
17. Unauthorized MCP is denied.
18. Agent Builder works.
19. Agent cannot exceed user permissions.
20. Usage remains crash-safe/reconciled.
21. Backup/restore works.
22. Prompt/response/tool content remains vendor-private.
23. Workspace restart recovers durable state.
24. Underlying deployment lifecycle still works.
25. No SERVER_ACCEPTANCE_BLOCKER/PILOT_BLOCKER remains on validated path.

Any NO that is a core blocker must be fixed.

---

# 33. FINAL DOCUMENTATION

Update:
- PRODUCT_VISION;
- ARCHITECTURE;
- ROADMAP;
- RUKAN;
- RUKAN-ADMIN;
- User Gateway;
- Employee Access closure;
- Native Workspace;
- MCP;
- Agent Builder;
- privacy;
- backup/recovery;
- server campaign;
- DEBT.

Create:
`docs/machi/RUKAN-WORKSPACE-USER-GUIDE.md`

Cover:
- sign in;
- chat;
- conversations;
- models;
- usage;
- MCP/tools;
- agents;
- API connection;
- troubleshooting.

Create:
`docs/machi/RUKAN-WORKSPACE-ADMIN-GUIDE.md`

Cover:
- provider;
- users;
- Workspace service;
- MCP catalog;
- agent policy;
- backup;
- support.

---

# 34. FINAL MERGE / TAG — AUTHORIZED ONLY AFTER FULL PASS

If:
- two clean diagnostics;
- C1/C2/C3;
- product closure audit passes;
- branch clean/pushed;
- no blocking defect;

then this instruction AUTHORIZES final integration.

Steps:
1. open PR from final native-workspace/product branch to `machi`;
2. inspect diff against canonical;
3. verify no secrets/evidence junk;
4. verify all required tests/status;
5. merge;
6. fetch canonical;
7. post-merge smoke;
8. tag truthfully:

Suggested:
`checkpoint/rukan-core-product-closed-nvidia-vllm-<shortsha>`

Do NOT use a tag implying:
- AMD validated;
- macOS validated;
- all hardware GA.

Update control state:
- canonical SHA;
- validated path;
- remaining platform breadth debt;
- next phase = Git Brain / Company Brain exploration OR further Workspace enhancement
  according to Lead/user direction.

---

# 35. TERMINAL STATUS

PASS:

`RUKAN_V0_5_NATIVE_WORKSPACE_AND_CORE_PRODUCT_CLOSED`

Only after final merge/tag.

NOT READY:

`RUKAN_V0_5_NATIVE_WORKSPACE_PRODUCT_NOT_READY`

Do not merge on NOT READY.

---

# 36. FINAL PASTE BACK

A. terminal status
B. starting source / final canonical SHA
C. backend contract-freeze result
D. Workspace architecture
E. OIDC browser/session design
F. conversation storage/schema
G. chat features completed
H. streaming/stop/regenerate
I. model selection
J. My Usage
K. generic API
L. MCP SDK/version
M. MCP official interoperability
N. MCP catalog/security
O. AgentDefinition
P. Agent Builder
Q. agent tool loop
R. model tool-capability handling
S. Admin employee access surfaces
T. preflight
U. backup/restore
V. migrations
W. security tests
X. privacy tests
Y. local QA
Z. diagnostic runs
AA. defects/fixes
AB. clean diagnostic streak
AC. C1
AD. C2
AE. C3
AF. physical Workspace evidence
AG. physical MCP evidence
AH. physical Agent evidence
AI. usage/token reconciliation
AJ. concurrency smoke
AK. final wheel SHA
AL. final Workspace build/assets identity
AM. campaign spend
AN. remaining platform breadth debt
AO. PR/merge SHA
AP. checkpoint tag
AQ. recommended next product phase
AR. cleanup
AS. STOP

# END PHASE 3
