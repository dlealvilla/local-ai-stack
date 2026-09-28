# Open Decisions

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
