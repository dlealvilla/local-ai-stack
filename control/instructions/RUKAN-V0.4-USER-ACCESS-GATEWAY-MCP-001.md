# RUKAN v0.4 — USER ACCESS GATEWAY, WORKSPACE ADAPTERS, LIBRECHAT, MCP, AGENTS

Instruction ID: `RUKAN-V0.4-USER-ACCESS-GATEWAY-MCP-001`
Status: `QUEUED_AFTER_V0.3_SERVER_CAMPAIGN_CLOSURE`

This is the next major productisation stage after Rukan v0.3 server-campaign closure.

The objective is to turn Rukan from:

> an administrator-operated local AI deployment platform

into:

> a governed organisational AI service that administrators can provision to employees and applications.

This phase must establish Rukan-owned identity/access/routing/usage/tool-governance contracts while using LibreChat as the first replaceable employee workspace.

LibreChat MUST sit behind a Rukan-owned adapter.

Rukan must remain capable of replacing LibreChat later with a first-party Rukan Workspace without redesigning the Gateway, People, routing, usage, model, telemetry, or policy layers.

The intended system is:

```text
ADMIN PLANE

Rukan Admin
   |
   +--> People / Teams
   +--> provision access
   +--> model policy
   +--> MCP policy/catalog
   +--> agent/workspace capability policy
   +--> user API credentials
   +--> usage analytics


EMPLOYEE / APPLICATION PLANE

Enterprise Identity
        |
        +-------------------------------+
        |                               |
        v                               v
LibreChatAdapter                   Generic API Client
        |                               |
     LibreChat                     OpenAI-compatible
        |                               |
        +---------------+---------------+
                        |
                        v
                RUKAN USER GATEWAY
                 authenticate
                 bind identity
                 authorize
                 resolve teams
                 filter models
                 route
                 account usage
                        |
                        v
              authorized READY deployment


TOOL / DATA PLANE

Workspace / Agent MCP Host
        |
        v
Rukan-approved MCP policy/catalog
        |
        +--> approved MCP server
        +--> approved MCP server
        +--> future Rukan Git Brain MCP server
```

The user-facing Workspace is NOT an authority for:
- user identity;
- model access;
- deployment truth;
- token accounting;
- team policy;
- ResourceManager;
- Serve.

---

# GATE 0 — CLOSE RUKAN v0.3 PHYSICAL CONFIDENCE FIRST

Do not begin v0.4 implementation from an unaccepted v0.3 campaign branch.

Current frozen v0.3 confidence candidate:

- source: `77923d0587a7ca4519a1a90dd5097a89ca4844e2`
- wheel SHA256: `6c5482508806facf0d1b19d13325387ccdc2fd1bbc8ca24bba36ac89e27aeb33`
- build: `0.1.0+77923d0587a7`
- campaign branch: `rukan/v0.3-server-campaign`
- current evidence tip: `7c47dd95862e25ba64ad1c9c07e76d9223b1cd0e`

Evidence:
- D4 clean;
- D5 clean;
- corrected confidence C1 clean;
- C1 included telemetry outage/recovery;
- C2 could not be allocated after three L40S stock refusals;
- C3 not started;
- there is no known open product defect on the frozen artifact.

## Gate 0.1 — obtain C2 and C3

Resume the existing v0.3 campaign.

Use the exact frozen source/wheel.

No code changes merely to obtain server stock.

L40S remains preferred.

If L40S is unavailable, Cursor MAY use another NVIDIA server shape if:
- current Rukan Discover/Capacity/Foundation evaluates it as feasible;
- same native/vLLM path works without source-code changes;
- tiny acceptance model fits safely;
- hourly price stays within existing RunPod NVIDIA limit;
- it remains inside the current NVIDIA pilot support envelope.

A different already-compatible NVIDIA host is valuable confidence evidence.

C2 and C3 must each prove:
- clean wheel install;
- packaged Admin;
- packaged Command Center;
- clean HUB model acquisition;
- real Deploy workflow;
- ResourceManager reservation;
- Serve READY;
- Admin restart/re-entry;
- >=3 inference requests;
- token accounting;
- 120-second Development telemetry;
- >=3 periodic reports;
- material lifecycle reports;
- STOP;
- RELEASE;
- People smoke;
- privacy canaries;
- evidence export;
- teardown.

## Gate 0.2 — failure during C2/C3

If a PRODUCT_DEFECT appears:
- preserve evidence;
- write regression;
- design robust fix;
- commit;
- full affected QA;
- build new immutable wheel;
- obtain two clean diagnostics;
- restart confidence at C1/C2/C3 on the new frozen candidate.

The old D5 maximum no longer prevents fixing a newly discovered blocker. This instruction explicitly authorizes continued corrective iteration subject to:
- one Pod at a time;
- existing RunPod hard limits;
- no hang/safety override;
- campaign cost remains reasonable.

## Gate 0.3 — promote accepted v0.3

Only after:
`RUKAN_V0_3_SERVER_CAMPAIGN_PASS`

then:
1. verify all owned Pods terminated;
2. verify exact final source and wheel SHA;
3. finish campaign result doc;
4. open PR into canonical `machi`;
5. independently review the merge diff;
6. merge;
7. verify clean canonical;
8. create checkpoint tag;
9. update control state.

Then create v0.4 branch from that canonical tip.

---

# 1. CREATE V0.4 BRANCH

Create:

`rukan/user-access-gateway-v0.4`

from newly accepted canonical `machi`.

Do not reuse or rewrite the v0.3 campaign branch.

---

# 2. REQUIRED PRODUCT + TECHNICAL DESIGN REVIEW

Before implementation, create:

`docs/machi/RUKAN-USER-ACCESS-GATEWAY-V0.4.md`

The document must be detailed enough to become the technical architecture for implementation.

Read:
- Product Vision;
- Architecture;
- Roadmap;
- Rukan Admin docs;
- People/Access docs;
- Telemetry/analytics docs;
- current User/Team/Membership/AccessIntent implementation;
- deployment/Serve/usage code;
- current LibreChat official documentation;
- current MCP specification + official SDK docs;
- current OIDC/JWT standards/library options.

The review must explicitly decide:
- Gateway domain/contracts;
- identity verification;
- identity binding;
- user API credentials;
- Workspace adapter contracts;
- LibreChat version/capabilities;
- first-party Rukan Workspace path;
- MCP execution/governance;
- agent ownership/projection;
- user usage model;
- team usage attribution;
- networking/trust boundaries;
- secret ownership;
- privacy;
- migrations;
- service lifecycle;
- server acceptance topology.

Cursor is encouraged to challenge implementation details.

Cursor may NOT violate the binding product boundaries below.

---

# 3. WORKSPACE ADAPTER ARCHITECTURE — NON-NEGOTIABLE

LibreChat is a replaceable client.

Define a Rukan-owned abstraction, conceptually:

`UserWorkspaceAdapter`

or another repository-consistent name.

The contract should expose only capabilities Rukan actually needs, such as:
- adapter identity/version;
- health/readiness;
- capability profile;
- inference endpoint projection/configuration;
- identity-forwarding configuration;
- user/group capability projection where supported;
- MCP connection/catalog projection where supported;
- optional agent/template projection;
- launch/config generation where Rukan manages the deployment;
- status/evidence.

LibreChat-specific configuration belongs in:

`LibreChatAdapter`

not Rukan core.

## Prohibited coupling

Rukan core MUST NOT:
- import LibreChat source internals;
- depend on LibreChat MongoDB schemas;
- query/modify LibreChat DB directly;
- use LibreChat user id as Rukan user id;
- use LibreChat's agent representation as canonical Rukan agent state;
- use LibreChat's MCP configuration as canonical Rukan MCP policy;
- expose Serve/vLLM directly because LibreChat happens to support it;
- require LibreChat for generic API access;
- require LibreChat for future first-party Rukan Workspace.

Pin one exact tested LibreChat release/container image digest.

Detect unsupported versions/capabilities and fail clearly.

Do not track `latest`.

---

# 4. FIRST-PARTY RUKAN WORKSPACE PATH

Do NOT require a full native replacement before v0.4 can ship.

But design Rukan so a native Workspace can replace LibreChat cleanly.

The design doc must define the staged path:

## Stage A — v0.4

LibreChat behind adapter.

Rukan owns:
- Gateway;
- identity;
- usage;
- People;
- policy;
- model access;
- MCP catalog/policy;
- user credentials;
- self-usage API.

## Stage B — thin Rukan Workspace

Future first-party UI:
- chat;
- model selector;
- own token usage;
- Connections;
- API credentials;
- MCP chooser;
- conversation/history;
- Rukan-native product experience.

## Stage C — Rukan Agent Builder

Future Rukan-owned:
- AgentDefinition;
- AgentRevision;
- ownership/team;
- instructions;
- model policy;
- MCP/tool bindings;
- future Knowledge/Git Brain bindings;
- execution policy;
- sharing;
- versioning;
- audit.

The architecture review must decide whether any small Rukan AgentDefinition seam should be introduced in v0.4 to prevent LibreChat agent lock-in.

Do not build a giant agent platform merely for architectural purity.

---

# 5. RUKAN USER GATEWAY — NEW AUTHORITY BOUNDARY

Create a first-class Gateway domain/service.

The User Gateway is the only supported employee/application inference edge.

Clients must never receive direct:
- vLLM endpoint;
- Ollama endpoint;
- Serve endpoint.

## Gateway responsibilities

- authenticate principal;
- bind/resolve external identity;
- resolve Rukan User;
- resolve teams;
- resolve effective access;
- authorize inference;
- authorize model selection;
- list allowed models;
- route only to authorized READY ServingInstance;
- record principal-attributed usage;
- stream responses;
- generate client-safe errors;
- audit non-content access decisions.

Gateway does NOT:
- deploy models;
- admit resources;
- own ServingInstance;
- become IdP;
- manage LibreChat accounts as identity truth;
- execute MCP tools unless an explicit later broker design is selected.

---

# 6. OPENAI-COMPATIBLE GATEWAY API

Initial required API:

- `GET /v1/models`
- `POST /v1/chat/completions`

Support:
- normal responses;
- streaming.

Use OpenAI-compatible request/response shapes where current Rukan runtime capabilities support them.

Return standard usage facts:
- prompt/input tokens;
- completion/output tokens;
- total tokens.

The Gateway may normalize provider-specific runtime responses.

Do not fake unsupported fields.

If pinned LibreChat or agent interoperability materially requires `/v1/responses`, Cursor may implement it after design review, but Chat Completions remains required.

## Model listing

`GET /v1/models` must return only models/aliases the current principal is permitted to use.

Do not expose:
- unavailable models;
- inaccessible models;
- internal process ports;
- unsupported providers.

Initially the list may be one currently READY deployment if v0.4 does not yet support employee-driven model deployment.

---

# 7. IDENTITY VERIFICATION PORT

Define:

`IdentityAssertionVerifier`

or equivalent.

Initial production adapter:

`OIDCBearerVerifier`

Use a mature OIDC/JWT library.

Do not implement cryptographic JWT verification manually.

Configure:
- issuer;
- audience;
- discovery/JWKS;
- subject claim;
- email claim;
- optional name claim;
- required scopes/claims;
- bounded clock skew.

Validate:
- signature;
- issuer;
- audience;
- expiry;
- not-before if present;
- subject;
- required claims.

Fail closed.

Cache discovery/JWKS safely.

Never log bearer tokens.

---

# 8. APPROVED EMAIL + STABLE EXTERNAL IDENTITY BINDING

Admin provisioning already creates Rukan User with approved email.

Email is provisioning/reconciliation data.

It is NOT the permanent identity key after federation.

Add an identity-binding concept:

- binding id;
- Rukan user id;
- provider kind;
- issuer;
- external subject;
- email seen at binding;
- created_at;
- updated_at;
- status;
- provenance.

## First binding

When:
- OIDC token is valid;
- issuer is configured;
- subject is not already bound;
- token email matches one active provisioned Rukan approved email;

Rukan may bind:
`issuer + subject -> user_id`

according to explicit policy.

## After binding

Stable external subject is authoritative.

If the same user later has a changed email at the IdP:
- do not silently create a new user;
- surface mismatch/reconciliation state as appropriate.

If a different subject presents an email already bound to another subject:
- refuse automatic takeover.

Admin must be able to inspect:
- identity binding state;
- issuer;
- safe subject fingerprint/display;
- last successful authentication;
- mismatch/rebind-required state.

Do not show or persist bearer tokens.

Admin may explicitly reset/rebind identity with audit evidence.

---

# 9. USER ACCESS POLICY

Reuse/extend current AccessIntent conservatively.

Required effective capabilities at minimum:

- platform access;
- inference access;
- model-selection permission;
- API credential permission;
- Workspace/LibreChat use;
- MCP use;
- MCP connection creation;
- agent use;
- agent creation.

Do not build a generic RBAC/ABAC system.

Preserve:
- user INHERIT/ALLOW/DENY;
- active-team grants;
- user overrides;
- default deny;
- Platform as parent gate;
- inactive/suspended/deactivated denies all.

Per-capability provenance remains required.

---

# 10. TEAM CONTEXT

Users may belong to several teams.

Identity must not duplicate usage across teams.

Define an explicit request/accounting team context.

Options:
- administrator-defined primary team;
- user-selected team from allowed memberships;
- client/workspace context;
- `unassigned`.

Choose one deterministic v0.4 rule.

The same request must count:
- once for user;
- once for deployment employee total;
- at most once for one team context.

Never copy one request into every team membership.

The selected team context may later scope Knowledge/Team Brain.

---

# 11. RUKAN USER API CREDENTIALS

Generic applications should be able to connect to Rukan without LibreChat.

Implement optional Rukan-issued per-user API credentials.

Admin controls whether a user may have API credentials.

A credential has:
- key id;
- user id;
- scopes;
- client label;
- issued_at;
- expires_at;
- revoked_at/status;
- optional last_used_at;
- verifier/hash.

Secret:
- high entropy;
- shown once;
- never stored plaintext;
- never exported;
- never logged.

Credential can never grant more than current user AccessContext.

Suspending user or disabling inference makes credential ineffective immediately.

Required scopes should remain simple:
- inference;
- models;
- self_usage
or another minimal bounded set.

Do not create a giant OAuth server.

---

# 12. LIBRECHAT ADAPTER

After design review, select one exact LibreChat release/container digest.

Implement `LibreChatAdapter`.

It may own:
- deployment/config generation;
- custom Rukan endpoint configuration;
- identity forwarding setup;
- supported role/group projection;
- MCP projection;
- agent capability projection if stable;
- health/version probe.

Do not read/write LibreChat MongoDB directly.

Prefer documented:
- YAML;
- environment;
- official admin/config surfaces;
- supported APIs.

## Employee inference path

LibreChat must call:

`Rukan User Gateway`

not vLLM.

## Identity forwarding

Preferred:
- user signs into LibreChat with enterprise OIDC;
- LibreChat passes the user's live OIDC bearer token to Rukan Gateway if the pinned release supports that safely.

LibreChat user/email headers may be sent as correlation metadata but are NEVER sufficient authorization.

If the exact pinned release cannot securely forward the user's validated bearer token:
- design a standards-based alternative, e.g. token exchange or a trusted client assertion carrying a signed user claim;
- document trust boundaries;
- Rukan must independently validate the assertion;
- do not trust a raw unsigned email header merely because request came from LibreChat.

A shared LibreChat service API key + unsigned email header is NOT an acceptable production identity design.

---

# 13. LIBRECHAT LOGIN

LibreChat may authenticate through:
- OIDC;
- SAML;
- LDAP

according to its supported configuration.

Rukan should prefer a setup where LibreChat and Rukan Gateway both rely on the same enterprise OIDC identity source or a standard bridge.

Rukan does not replace:
- Entra;
- Okta;
- Keycloak;
- customer directory;
- corporate SSO.

An employee may successfully log into LibreChat but still be denied model inference if:
- no Rukan user provisioned;
- email not approved/unbound;
- Rukan user suspended;
- Platform denied;
- inference denied.

Rukan authorization wins for Rukan inference.

---

# 14. USER PROVISIONING ADMIN EXPERIENCE

Expand Admin People into actual access provisioning.

Per user show:

- name;
- approved email;
- stable Rukan user id;
- status;
- teams;
- identity-binding status;
- Gateway access;
- Workspace/LibreChat access;
- inference access;
- model-selection permission;
- API credential permission;
- MCP use;
- MCP connection creation;
- agent use/create;
- recent usage;
- last successful access;
- current credential count.

Actions:
- enable/disable;
- suspend/reactivate;
- memberships;
- access policies;
- revoke/reset identity binding;
- issue/revoke API credential;
- inspect own-user-safe audit.

Never send invitation email in this phase unless deliberately designed later.

"Provisioned" means Rukan will recognize an authenticated external identity matching the approved record and then enforce Rukan policy.

---

# 15. USER SELF-SERVICE / MY USAGE

Build a Rukan-owned authenticated user API independent of LibreChat.

Required:
- `GET /v1/me`
- `GET /v1/me/usage`
- API credential self-view/revoke where policy permits;
- connection/capability summary where useful.

A user can access only self data.

Usage periods:
- 24h;
- 7d;
- 30d;
- retained/all.

Show:
- request count;
- input tokens;
- output tokens;
- total tokens;
- success/failure;
- model breakdown.

If useful, build a very small Rukan User Access page:
- profile;
- My Usage;
- Connections/API credentials;
- Open Chat in LibreChat.

This page is allowed and desirable because it creates a Rukan-owned user experience seam without forcing the full native chat implementation now.

Do not build the full first-party chat UI unless the design review concludes it is low-risk and valuable.

---

# 16. PRINCIPAL-ATTRIBUTED INFERENCE USAGE

Extend active non-content usage.

Every employee Gateway request must resolve exactly one Rukan user before upstream model execution.

Record:

- usage id;
- gateway request id;
- user id;
- optional team context;
- client/application id;
- auth method;
- model;
- runtime/macropath;
- instance;
- input tokens;
- output tokens;
- latency;
- outcome/failure;
- occurred_at.

No prompt/response.

## Usage classes

Preserve separation:

- `user_request`;
- `operator_test`;
- `acceptance_probe`;
- explicit system categories.

User analytics only count `user_request`.

## Conservation invariants

For each time interval and deployment:

```text
EmployeeRequestCount = SUM(UserRequestCount)

EmployeeInputTokens = SUM(UserInputTokens)

EmployeeOutputTokens = SUM(UserOutputTokens)

EmployeeTotalTokens = EmployeeInputTokens + EmployeeOutputTokens
                    = SUM(UserInputTokens + UserOutputTokens)
```

No user request may be unattributed.

No request may be attributed twice.

Team totals must not double count multi-team users.

Admin Analytics must include reconciliation checks.

A mismatch is an accounting defect.

---

# 17. STREAMING ACCOUNTING

Streaming must still produce final usage.

Where upstream supports usage chunks/options:
- request required usage reporting from upstream;
- consume final usage;
- record once.

If client disconnects after upstream execution:
- record the executed request truthfully.

If upstream omits usage:
- record request with unresolved token counts;
- do not estimate tokens from raw content.

Never buffer/store full responses merely to count tokens.

Test:
- normal stream;
- client cancel;
- upstream error;
- disconnect;
- retry;
- final usage missing.

---

# 18. USER TOKEN DISPLAY

LibreChat should display per-message/context token information using standard Gateway usage fields if the pinned version supports it.

Verify physically.

Do not fork LibreChat just to add Rukan cumulative token totals.

Rukan's own `My Usage` API/page is authoritative for cumulative usage.

LibreChat adapter may:
- configure token/context display;
- expose/link the Rukan My Usage surface if supported.

Admin sees per-user usage.

Command Center continues to receive deployment-level aggregate only unless explicitly allowed.

No name/email/user list sent vendor-side.

---

# 19. ADMIN USER ANALYTICS

Customer Admin Analytics should add:

- active users;
- users with inference activity;
- requests by user;
- input/output/total tokens by user;
- failures;
- average latency;
- model usage;
- team totals using one accounting team context;
- source/client type.

Provide reconciliation row:

`Sum of user traffic = Employee deployment traffic`

Make any accounting gap visible.

Operator tests/acceptance probes remain separate.

Do not include People PII in vendor telemetry.

---

# 20. GENERIC CLIENT CONNECTION EXPERIENCE

The administrator wants users to connect Rukan inference to other applications.

Provide safe connection information:

- Gateway base URL;
- API style = OpenAI-compatible;
- allowed model names;
- authentication method;
- credential status;
- example client configuration.

Never display direct Serve port.

User may use:
- OIDC-capable client;
- Rukan user API credential if enabled.

Test at least:
- curl/OpenAI SDK-compatible client;
- another simple generic client fixture.

No client-specific logic belongs in Gateway.

---

# 21. ENTERPRISE SECURITY LAYERING

Rukan is not a cybersecurity platform.

Design for compatibility with normal enterprise controls.

Supported conceptual deployment:

```text
Private network / corporate LAN / VPN / ZTNA
        |
customer firewall / reverse proxy / load balancer / WAF
        |
enterprise identity provider
        |
LibreChat + Rukan User Gateway
```

Rukan should provide:
- TLS;
- identity verification;
- Authorization header support;
- configurable bind addresses;
- trusted-proxy configuration;
- secret adapters;
- audit;
- rate/concurrency hooks;
- standard logs/metrics.

Do NOT build:
- VPN;
- WAF;
- firewall;
- SIEM;
- PKI;
- EDR;
- proprietary IdP.

## Trusted proxy

If deployed behind reverse proxy:
- explicit trusted source addresses/CIDRs;
- only trusted peers may supply forwarded scheme/client IP;
- forwarded identity is not accepted unless cryptographically verified through the selected identity mechanism.

---

# 22. GATEWAY ABUSE / RESOURCE BOUNDS

Employee Gateway needs practical safeguards.

Implement/configure:
- max request body;
- max prompt/messages size according to current model context policy;
- max tokens bounded by deployment policy;
- request timeout;
- streaming timeout/cleanup;
- per-user concurrent request bound;
- global Gateway concurrent bound coordinated with deployment capacity;
- queue bound;
- typed overload/rejection.

Do not introduce complex quota/billing engine yet.

The administrator should be able to inspect relevant bounds.

Future rate/quota policies get a replaceable seam.

---

# 23. MCP — PRODUCT ROLE

MCP is NOT the inference protocol.

It connects an AI workspace/agent to tools and data.

```text
Inference:
Workspace
   -> Rukan Gateway
   -> model

Tools/data:
Workspace / Agent MCP Host
   -> MCP connection
   -> MCP Server
   -> tool/data system
```

Use official MCP SDKs/protocol.

Prefer:
- Streamable HTTP for shared/multi-user enterprise MCP;
- stdio only for local/single-user/developer cases.

---

# 24. RUKAN MCP CATALOG / POLICY

Create Rukan-owned MCP governance contracts.

At minimum:

## McpServerDefinition

- stable id;
- display name;
- endpoint/transport type;
- admin-approved state;
- auth method metadata;
- capability metadata;
- sensitivity/category labels;
- created/updated;
- optional server identity/version facts.

Do not store arbitrary credential secrets in the canonical definition.

## McpAccessPolicy

Resolve whether user/team may:
- use MCP;
- see a server;
- attach server/tools to an agent;
- create personal connection if allowed.

## McpConnection

Where Rukan needs a user-visible connection record:
- user id;
- server id;
- connection state;
- auth status;
- secret reference, not raw secret where possible;
- last successful connection;
- error state.

Do not put OAuth access tokens into model prompts or usage analytics.

---

# 25. MCP EXECUTION DECISION GATE

During design review, decide whether v0.4 execution should be:

## Preferred A — LibreChat-native MCP host behind adapter

Rukan:
- owns approved catalog/policy;
- projects permitted servers/capabilities to LibreChat;
- LibreChat executes MCP client connections/tools.

Choose this if:
- policy can be made truthful/enforceable;
- user-created arbitrary servers can be disabled unless Rukan permits;
- approved server list can be projected safely;
- user OAuth/credentials stay isolated;
- no core Rukan policy depends on LibreChat DB internals.

## Option B — thin Rukan MCP Gateway/Broker

Build only if architecture review proves A cannot satisfy enforceable governance.

If built:
- use official MCP SDK;
- proxy Streamable HTTP MCP;
- authenticate Rukan user;
- authorize server/tool;
- keep user secret/token out of model;
- audit tool call metadata without tool payload by default;
- do not become a generic network proxy.

This is a deeper complexity path and must be justified.

Do not build a broker merely because it sounds more controlled.

---

# 26. MCP SECURITY

Default enterprise posture:

- only administrator-approved MCP servers visible;
- user-defined MCP server creation disabled unless explicit capability grants it;
- remote endpoint normally HTTPS;
- outbound target validation;
- protect against SSRF.

If arbitrary remote URL configuration exists:
- resolve/validate destination;
- reject loopback/link-local/cloud metadata endpoints;
- handle DNS rebinding;
- private RFC1918/internal destinations require explicit administrator policy because internal MCP servers are legitimate enterprise use cases.

Do not hard-code "all private IPs forbidden."

Instead:
- default deny user-defined private targets;
- explicit admin-approved internal target policy.

Per-user MCP OAuth:
- prefer standard OAuth;
- credentials user-scoped;
- no sharing between users;
- revocation;
- expiry/refresh handled by chosen host/adapter.

---

# 27. MCP SERVER TEST

Server campaign must include at least one controlled MCP server.

Prefer a small Streamable HTTP test MCP server using official SDK.

It should expose safe deterministic tools, e.g.:
- echo;
- add;
- get synthetic project status.

At least one run should exercise authenticated MCP:
- OAuth or bounded per-user API credential;
- two users must not share credentials.

Prove:
- allowed user can use tool;
- denied user cannot;
- MCP denial does not prevent ordinary inference;
- tool result flows through agent/chat;
- MCP credentials absent from prompts/telemetry/logs where prohibited.

---

# 28. AGENTS — LIBRECHAT NOW, RUKAN OWNERSHIP PATH

LibreChat's Agent Builder may be used as the first UI.

But Rukan must not make LibreChat Agent DB its future product ontology.

During architecture review, define a minimal Rukan-owned:

`AgentDefinition` / `AgentRevision`

ONLY if it can be introduced cleanly without ballooning scope.

Candidate future fields:
- stable agent id;
- owner user/team;
- display name;
- revision;
- instructions/template reference;
- model selection policy;
- MCP server/tool references;
- future Knowledge/Git Brain refs;
- sharing policy;
- status;
- created/updated.

If implemented in v0.4:
- LibreChatAdapter may project/sync supported subsets;
- unsupported client fields stay adapter-specific;
- Rukan remains source of truth for Rukan-defined agents.

If not implemented:
- explicitly classify LibreChat-created agents as client-local workspace artifacts;
- preserve the migration path;
- do not expose them as canonical Rukan agents.

---

# 29. AGENT CREATION POLICY

Current People access intent should govern:
- agent use;
- agent creation.

Where LibreChat supports role/group capability controls:
- LibreChatAdapter projects them.

This projection improves UX but does not replace Gateway inference authorization.

An agent cannot use a model the user is not authorized to invoke through Gateway.

MCP tools must also obey the selected MCP governance mechanism.

---

# 30. FUTURE GIT BRAIN COMPATIBILITY

This architecture must deliberately support the future Git Brain / Company Brain.

Future Brain modules should be able to expose:

- MCP tools;
- MCP resources;
- MCP prompts;
- Gateway-accessible model services where appropriate;
- Knowledge retrieval APIs.

The employee Workspace then uses the same standard integration:

```text
Rukan Workspace / LibreChat
        |
        +--> Rukan Gateway -> models
        |
        +--> MCP -> Git Brain / Company Brain
```

Do not bake Git Brain into v0.4.

Do ensure this phase creates no architecture that would prevent it.

---

# 31. CLIENT CAPABILITY PROFILE

Define a capability profile for Workspace adapters.

Examples:
- chat;
- streaming;
- token display;
- model selection;
- MCP;
- agents;
- user OAuth passthrough;
- group policy projection;
- API/agent management availability.

Admin should show:
- selected employee Workspace adapter;
- version;
- health;
- supported capabilities;
- unsupported/degraded capabilities.

Do not silently pretend LibreChat can enforce a feature if the pinned version cannot.

---

# 32. WORKSPACE DEPLOYMENT / PACKAGING

Do not make LibreChat a Python dependency.

Prefer isolated container/service deployment behind adapter.

Pin exact image digest.

Secrets/config:
- not committed;
- generated into Rukan-owned protected configuration directory or provided through secret adapter;
- no database password/token in browser-visible config.

Use replaceable execution seam where practical:
- current container engine adapter;
- future external/pre-existing LibreChat possible.

Rukan should support:
- `managed` LibreChat deployment for easy pilot;
- `external` LibreChat endpoint/config mode later if simple.

Do not require LibreChat for Gateway-only deployments.

---

# 33. LIBRECHAT DATA BOUNDARY

LibreChat will hold conversation/workspace data according to its own configured storage.

Rukan core operational stores:
- do not ingest full LibreChat conversations;
- do not scrape LibreChat DB;
- do not vendor-export chat content.

Document clearly:
- Rukan content persistence policy;
- LibreChat content persistence boundary;
- customer deployment responsibility.

This is important because "Rukan does not persist prompt/response" does not mean LibreChat necessarily does not.

The Admin privacy UI/docs must distinguish these planes.

---

# 34. USER WORKSPACE ADMIN SURFACE

Add Admin section under People/Settings such as:

`User Access / Workspace`

Show:
- Gateway enabled/status;
- Gateway URL/bind/TLS mode;
- identity verifier status;
- Workspace adapter = LibreChat;
- LibreChat version/health;
- provisioned user count;
- bound identity count;
- active users;
- users with API credentials;
- MCP approved connections;
- agent capabilities;
- privacy boundary.

Do not clutter Overview.

---

# 35. USER-SAFE ERRORS

Gateway responses should distinguish:
- authentication_required;
- identity_not_provisioned;
- identity_binding_conflict;
- user_suspended;
- platform_access_denied;
- inference_access_denied;
- model_not_allowed;
- no_ready_model;
- overloaded;
- upstream_failure.

Do not reveal internal paths/secrets/process information.

LibreChat should receive useful standard HTTP errors.

---

# 36. AUDIT / ACCOUNTABILITY

Customer-local audit events:

- gateway.auth_succeeded/failed (safe identifiers only);
- identity.bound/reset/conflict;
- api_credential.issued/revoked;
- user.inference_allowed/denied;
- mcp.connection_added/removed/authenticated;
- mcp.access_denied;
- workspace.adapter_changed/version_changed.

Do not journal:
- access tokens;
- prompts;
- responses;
- OAuth codes;
- MCP credential values;
- tool payloads by default.

Use stable local ids.

Vendor telemetry receives deployment aggregates only.

---

# 37. MIGRATION

People directory schema evolves transactionally.

Add:
- identity bindings;
- API credentials/verifiers;
- access intent fields;
- optional primary/accounting team;
- workspace capability state if needed.

Test migration from accepted v0.3 People schema.

No destructive reset.

Back up/recover where current migration policy requires.

---

# 38. LOCAL SECURITY / THREAT AUDIT

Before server campaign, test:

Identity:
- forged JWT;
- wrong issuer;
- wrong audience;
- expired;
- not-before;
- unknown kid;
- missing email first bind;
- duplicate email binding conflict;
- suspended/deactivated;
- binding reset.

API credentials:
- wrong secret;
- revoked;
- expired;
- disabled user;
- constant-time verifier;
- no logs.

Gateway:
- direct internal Serve endpoint not disclosed;
- unauthorized models filtered;
- body bounds;
- malformed streaming request;
- client disconnect;
- concurrency overflow;
- trusted proxy spoofing;
- CORS/Origin where applicable.

Self usage:
- user A cannot query user B.

MCP:
- unauthorized server;
- unauthorized tool;
- user connection creation denied;
- SSRF cases;
- secret leakage;
- cross-user credential isolation.

LibreChat adapter:
- unsupported version;
- config secret leakage;
- direct DB coupling test/prohibition.

---

# 39. LOCAL FUNCTIONAL ACCEPTANCE

Before spending on v0.4 server campaign:

Run complete local/fixture topology:

- Rukan Admin;
- deployed READY model seam/fixture;
- User Gateway;
- synthetic standards-compliant OIDC issuer/test verifier;
- two allowed users;
- one unprovisioned user;
- one suspended user;
- Rukan user API credential;
- LibreChatAdapter config generation;
- pinned LibreChat container where local environment supports it;
- MCP test server.

Prove:

User A:
- logs/authenticates;
- binds;
- allowed models;
- inference;
- streaming;
- tokens;
- My Usage;
- MCP allowed;
- agent capability according to policy.

User B:
- separate usage;
- separate MCP credentials.

Denied users:
- fail before model execution.

Admin:
- per-user totals.

Reconciliation:
- user A + user B = employee deployment total exactly.

Operator tests do not appear in employee total.

---

# 40. LIBRECHAT PHYSICAL LOCAL ACCEPTANCE

Where Docker/container runtime is available locally:

Use pinned exact LibreChat image.

Do not accept configuration-only evidence.

Prove:
- LibreChat starts;
- user can authenticate through test IdP;
- custom endpoint points to Rukan Gateway;
- direct vLLM endpoint is not configured;
- chat response streams;
- token usage displayed if pinned version supports it;
- model list is filtered;
- suspended user inference denied by Rukan;
- MCP tool works where allowed;
- agent builder/capability works where allowed.

If local environment cannot run LibreChat:
- do not fabricate PASS;
- carry this proof into physical server Gate.

---

# 41. V0.4 SERVER CAMPAIGN

After local gates pass, run a new bounded iterative server campaign.

Suggested branch:
`rukan/v0.4-user-access-server-campaign`

Use one Pod at a time.

Use cheap supported NVIDIA host and tiny model.

Reuse existing RunPod hard limits.

Additional campaign target:
- target <= $20 infrastructure spend;
- if continued testing would exceed this, stop and report.

## Diagnostic phase

No arbitrary fixed "five and quit" if a useful robust correction remains inside budget.

However do not loop indefinitely.

Use:
- maximum 8 product diagnostic server iterations before mandatory Lead review;
- or earlier stop if cost/safety requires.

Exit diagnostics after:
- two consecutive clean full user-access runs;
- no server/pilot blocker;
- exact accounting;
- no auth/privacy/MCP mismatch.

A code change resets clean streak.

## Defect loop

```text
server evidence
 -> classify
 -> violated invariant
 -> regression
 -> architecture fix
 -> commit
 -> QA
 -> new immutable artifact
 -> server retest
```

No hot patches.

---

# 42. V0.4 SERVER TOPOLOGY

One disposable NVIDIA server may co-locate test planes for economy while preserving process/data boundaries:

```text
Server
 |
 +-- Rukan Admin/control
 +-- Rukan User Gateway
 +-- deployed vLLM model
 +-- LibreChat pinned container
 +-- LibreChat backing services required by pinned deployment
 +-- test OIDC provider/issuer
 +-- MCP Streamable HTTP test server
 +-- Command Center / telemetry intake
```

Separate:
- state roots;
- DBs;
- ports;
- credentials.

No cross-DB shortcuts.

Real HTTP/TLS/auth paths.

Use SSH forwarding for admin/operator UIs where appropriate.

---

# 43. SERVER USER MATRIX

Synthetic users:

## User A
- provisioned;
- active;
- Team Alpha;
- platform allow;
- inference allow;
- model selection allow;
- Workspace allow;
- MCP allow;
- agent use/create allow;
- API credential allow.

## User B
- provisioned;
- active;
- Team Beta;
- inference allow;
- more restricted MCP/agent policy.

## User C
- authenticated at IdP;
- NOT provisioned in Rukan.

Expected:
- login to Workspace may occur depending on client config;
- Rukan inference denied.

## User D
- provisioned but suspended.

Expected:
- Gateway denial before upstream model call.

Test identity binding independently.

---

# 44. SERVER INFERENCE / ACCOUNTING TEST

Each allowed user:

- >=5 non-streaming or mixed requests;
- >=5 streaming requests if practical;
- at least two model contexts if model-selection path exists.

Record exact user usage.

Prove:

```text
A requests + B requests = employee requests

A input + B input = employee input

A output + B output = employee output

A total + B total = employee total
```

Operator test/acceptance probe remains outside employee totals.

Restart Gateway.

Repeat request.

No loss/double count.

---

# 45. LIBRECHAT SERVER TEST

Physically prove:

- exact pinned digest;
- adapter capability detection;
- OIDC login;
- Rukan Gateway endpoint;
- no direct Serve route;
- User A chat;
- User B chat;
- User C denied by Rukan;
- User D denied by Rukan;
- model selector filtered;
- streaming;
- usage returned.

If LibreChat token display cannot show cumulative Rukan totals:
- verify message/context token display where supported;
- verify My Usage API/page for cumulative totals;
- do not fork solely for cosmetic parity.

---

# 46. GENERIC API CLIENT SERVER TEST

User A receives/uses a Rukan API credential if policy allows.

Prove:
- standard OpenAI-compatible client;
- `GET /v1/models`;
- Chat Completions;
- streaming;
- revocation causes denial;
- suspended user credential denied;
- same usage ledger.

No direct model server address.

---

# 47. MCP SERVER TEST

Use official MCP SDK.

Use Streamable HTTP.

At least:
- deterministic tool;
- authenticated connection in at least one diagnostic/confidence run.

Prove:
- User A permitted;
- User B policy difference;
- denied user cannot call;
- tool can be attached/used through LibreChat/agent;
- ordinary model inference still works without MCP;
- no MCP credential in Rukan telemetry;
- no cross-user token sharing.

If user-created connections are enabled in v0.4:
- test allowed vs denied capability;
- SSRF protections;
- admin-approved internal endpoint exception.

---

# 48. AGENT SERVER TEST

If LibreChat Agent Builder is part of accepted adapter capability:

- User A creates/uses an agent if allowed;
- User B denied creation if policy says so;
- agent uses Rukan Gateway model;
- agent uses only allowed MCP tool/server;
- Rukan inference policy still applies.

Do not claim Rukan-native agent ownership unless AgentDefinition was implemented.

Document client-local vs Rukan-owned agent semantics.

---

# 49. RESTART / FAILURE TESTS

At least once:
- restart User Gateway;
- restart LibreChat;
- restart identity test provider where safe;
- restart MCP test server;
- restart Admin;
- intake outage/recovery if relevant.

Verify:
- identity binding persists;
- user API credentials persist;
- usage persists;
- no duplicate accounting;
- Workspace reconnects;
- MCP failure degrades tool use without corrupting inference.

---

# 50. CONFIDENCE PHASE

After two consecutive clean diagnostics:

Freeze:
- Rukan source SHA;
- wheel SHA;
- LibreChat exact image digest;
- test deployment manifest;
- MCP test server artifact;
- identity test configuration.

Run 3 fresh confidence servers:
- C1;
- C2;
- C3.

No product code changes.

Each:
- clean install;
- deploy model;
- Gateway;
- identity;
- 2+ allowed users;
- denied user;
- LibreChat;
- generic client;
- per-user usage;
- aggregate reconciliation;
- MCP smoke;
- restart;
- privacy;
- teardown.

At least one confidence run:
- authenticated MCP;
- API credential revoke;
- Workspace restart.

A product defect resets confidence to zero after robust correction and clean diagnostics.

---

# 51. DATA COLLECTION

Campaign evidence must include:

- source SHA;
- wheel SHA;
- LibreChat version/digest;
- server/GPU;
- InstallId;
- model/artifact/runtime;
- users by synthetic stable ids only;
- identity binding outcomes;
- Gateway request counts;
- per-user token totals;
- deployment totals;
- reconciliation;
- auth denial counts/reasons;
- API credential outcomes;
- MCP server/tool outcomes;
- agent outcomes;
- report/telemetry;
- cost.

Never commit:
- bearer tokens;
- API token secrets;
- OAuth codes;
- TLS private keys;
- real emails;
- prompts/responses.

Use synthetic `example.invalid` identities.

---

# 52. PRIVACY / VENDOR TELEMETRY

Command Center may receive:
- employee aggregate request count;
- aggregate input/output tokens;
- model/runtime;
- failures;
- deployment facts.

Command Center must NOT receive:
- user names;
- emails;
- user ids unless explicitly pseudonymized by future decision;
- team memberships;
- identity subjects;
- API credential ids;
- MCP OAuth identities;
- prompts;
- responses;
- tool payloads.

Add negative canary tests.

---

# 53. ADMIN / USER EXPERIENCE REVIEW

Before confidence freeze, perform product coherence audit.

Admin should answer:

- who has access?;
- which teams?;
- who is bound to enterprise identity?;
- who is active/suspended?;
- who can use inference?;
- who can select models?;
- who can use Workspace?;
- who can use/create agents?;
- who can use MCP?;
- which MCP servers are approved?;
- how many requests/tokens per user/team?;
- does the user total reconcile?;
- what is the Gateway status?;
- what is the Workspace adapter/version?;

User should answer:

- can I chat?;
- which models may I use?;
- how many tokens have I used?;
- how do I connect another app?;
- what credentials/connections do I have?;
- which MCP tools can I use?;
- can I build/use an agent?;

Avoid infrastructure jargon in primary screens.

---

# 54. ROADMAP / NATIVE WORKSPACE DECISION

At the end of v0.4, make an explicit recommendation:

A. keep LibreChat as default adapter while building Git Brain;
B. build thin first-party Rukan Workspace next;
C. begin native Rukan Agent Builder next;
D. other evidence-based sequence.

Evaluate:
- adapter friction;
- LibreChat upgrade risk;
- UX differentiation;
- implementation complexity;
- Agent/MCP requirements;
- Git Brain roadmap.

Do not automatically choose "build everything ourselves" or "never build it."

---

# 55. FULL QA

Backend:
- Gateway unit/integration;
- identity;
- access;
- API credentials;
- usage/reconciliation;
- streaming;
- MCP policy/catalog;
- adapter contracts;
- migrations;
- security/privacy;
- full `tests/machi`;
- `tests/acceptance_lab`;
- ruff;
- mypy strict.

Admin:
- provisioning;
- binding;
- credentials;
- analytics;
- MCP policy;
- Workspace status;
- Vitest;
- TypeScript;
- build.

Any Rukan user page:
- auth;
- own usage;
- credentials;
- connections;
- denial isolation.

LibreChat adapter:
- pinned-version fixture/integration;
- config generation;
- capability profile;
- unsupported-version behavior.

Artifact:
- wheel;
- SHA;
- clean venv;
- packaged UI;
- no source repo runtime.

---

# 56. TERMINAL STATUS

Gate 0 failure:

`RUKAN_V0_4_BLOCKED_BY_V0_3_CONFIDENCE`

v0.4 implementation/local failure:

`RUKAN_V0_4_USER_ACCESS_NOT_READY`

Full physical PASS:

`RUKAN_V0_4_USER_ACCESS_GATEWAY_SERVER_CAMPAIGN_PASS`

PASS requires:
- v0.3 campaign promoted first;
- Rukan Gateway;
- real identity;
- admin provisioning;
- LibreChat adapter;
- generic API access;
- per-user usage;
- exact aggregate reconciliation;
- MCP governed path;
- server diagnostics clean;
- 3 fresh confidence runs;
- no server/pilot blocker.

Do not promote canonical v0.4 until final Lead review unless a later explicit instruction authorizes automatic merge.

---

# 57. PASTE BACK

Return:

A. terminal status
B. v0.3 Gate 0 C2/C3 result
C. v0.3 promoted canonical SHA
D. v0.4 starting SHA/branch
E. industry/product review
F. Workspace adapter architecture
G. LibreChat pinned version/digest
H. native Rukan Workspace future path
I. Gateway contracts
J. Gateway network surface
K. identity verifier
L. identity binding
M. user/team access changes
N. API credential design
O. Gateway auth tests
P. OpenAI-compatible API
Q. streaming
R. model filtering
S. user usage contract
T. accounting conservation evidence
U. My Usage
V. Admin per-user analytics
W. LibreChat adapter integration
X. LibreChat auth/inference
Y. MCP architecture decision
Z. MCP catalog/policy
AA. MCP security/SSRF handling
AB. MCP physical evidence
AC. agent semantics
AD. Agent Builder physical evidence if supported
AE. generic client evidence
AF. enterprise-security layering
AG. privacy/vendor boundary
AH. local QA
AI. diagnostic server runs
AJ. defects/fixes
AK. confidence C1
AL. confidence C2
AM. confidence C3
AN. final source/wheel/digests
AO. usage/token totals
AP. cost
AQ. remaining GA blockers
AR. native Workspace recommendation
AS. git state
AT. cleanup
AU. recommended next step
AV. STOP

# END INSTRUCTION
