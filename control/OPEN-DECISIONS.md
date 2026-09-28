# Open Decisions

There are **no blocking Lead Developer decisions** for the first local Admin UI design review.

## Binding post-Stage-1 product direction

- Stage 1 remains closed as `STAGE1_DEPLOYMENT_SPINE_IMPLEMENTATION_CLOSED_PHYSICAL_BREADTH_PENDING` at closure tip `4cb89622a4cd3a1a37bf6ab44c4414e4287e8934`.
- The **next product-track direction is a simple local operator/admin frontend** so a system administrator can see and interact with the Stage-1 deployment spine without driving pytest or internal developer tooling.
- The first frontend is **same-machine / loopback only**. It must not create a LAN, remote-admin, or vendor-control promise.
- The local Admin UI and the future central business/vendor command center are **separate planes**. They may later share explicit APIs/contracts, but they are not one application and do not share authority.
- The UI must render and invoke Machi-owned contracts/services. It must **not** become a second source of truth for host facts, SAFE capacity, Foundation, model qualification, Plan, ResourceManager, ServingInstance, lifecycle, or Witness.
- The first UI must include an **embedded inference tester** for the current READY local instance. This requires a narrow local interaction seam if one does not already exist. Prompt and response content remain local and must not be added to operational telemetry, Witness, or vendor export.
- The first UI should start with only core functions supported by repository truth. **Do not invent dashboards, KPIs, settings, model-marketplace behaviour, analytics, fleet controls, or lifecycle actions merely to make the UI look complete.**
- The first design target is five pages:
  - Overview;
  - Inference;
  - Models;
  - Deployment;
  - System.
- Future product areas may be mocked for information architecture but are not v0 functionality unless repository truth already supports them.
- Native/vLLM remains the primary macropath where supported. Ollama remains the compatibility/fallback macropath. The UI must present them as execution paths under one Machi product, not as two products.
- One ResourceManager remains the sole admission authority. UI actions may call it only through existing services/control seams.
- Physical qualification breadth remains separate and pending: AMD native/vLLM, macOS/Ollama, NVIDIA Ampere/N1 breadth, and other recorded physical coverage.

## v0 design intent

The Lead's current preferred v0 shape is:

1. **Overview** — Witness status, active macropath, running model identity, ServingInstance health/state, SAFE capacity summary, and only safe lifecycle actions that already exist.
2. **Inference** — an embedded local prompt/response tester bound to the current READY instance; surface request/proof metadata that Machi actually records.
3. **Models** — expose the current model operations honestly: inspect, local import, explicit hub acquire, stored/provider identity, and qualification/unsupported state. Do not call this a full marketplace until a real catalog/discovery API exists.
4. **Deployment** — show the existing Foundation → Model → Plan → Reservation → Instance → Witness chain and allow only existing valid lifecycle actions such as stop and release-after-stop. A future guided deploy flow may be added only if it maps cleanly to the current services.
5. **System** — observed host information, SAFE capacity evidence, execution-path status, and physical qualification state. Technical identifiers belong behind progressive disclosure.

## Future mock areas — not v0 implementation

- usage analytics/KPI dashboard until a real Machi UsageEvent/analytics product surface exists;
- central command center / fleet inventory;
- LAN or remote Admin;
- Knowledge/RAG administration;
- Users/Teams/Permissions;
- Licensing/entitlements;
- software update UI;
- Dynamo controls;
- multi-host placement;
- live request-failure failover;
- broad model marketplace semantics not yet implemented.

## Previously decided and still valid

- Existing accepted physical evidence remains sufficient for Stage-1 capability closure at its bounded scope.
- AMD managed native prefix/userspace is Machi-owned; host kernel/driver/device prerequisites remain host-owned.
- Verified existing/provider ROCm userspace may be verified/reused when it matches the approved recipe.
- OCI runtime image: preserve the seam, build later unless a future decision opens it.
- ContainerExecutor: deferred.
- Qualification evidence must not be reused across materially different GPU environments merely by compute capability.

## Decisions intentionally left open for the design review

- The exact frontend technology/framework. Cursor must inspect repository/tooling reality and run the Industry Solution Selection Gate if more than one materially credible option remains.
- The exact local control/API shape between browser UI and Machi services. Prefer the thinnest replaceable loopback seam that preserves domain authority.
- Whether the first runnable UI should be read-mostly plus inference/stop/release, or also include a bounded guided deployment action in the same increment. This must be decided from actual service composition, not visual ambition.
- Whether `machi` should be fast-forwarded to the Stage-1 closure tip before the first frontend implementation branch. The design review should recommend the clean sequence; do not promote during the review.

## Later decision gates

- Runtime Artifact Registry scope and sequence relative to frontend v0.2 / installer work.
- Authentication/authorisation before any non-loopback control surface.
- Central command center identity, tenancy, consent, and telemetry/export contract.
- Whether/when to run Dynamo or other runtime/fabric comparisons in the Stage-2 lab.
- Whether/when to execute the pending AMD, macOS/Ollama, and NVIDIA breadth physical campaigns.
