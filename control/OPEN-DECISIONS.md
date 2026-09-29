# Open Decisions

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
