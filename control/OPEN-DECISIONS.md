# Open Decisions

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
