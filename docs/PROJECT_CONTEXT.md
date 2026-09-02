# AI Deployment Project — Project Context

Authoritative orientation for any Cursor Agent session working on this
repository. Read this together with `docs/PRODUCT_VISION.md`,
`docs/ROADMAP.md`, `docs/DEVELOPMENT_WORKFLOW.md` and
`docs/CAPACITY_ARCHITECTURE.md` before proposing substantial
architectural changes.

`docs/CAPACITY_ARCHITECTURE.md` is authoritative for host
characterization, capacity representation, storage evidence, model
requirements, feasibility and model selection, including its migration,
versioning and robustness strategy.

---

## Architectural invariants

- **Core owns concepts; adapters own implementations.**
- Exoskeleton first: complete an end-to-end modular product before
  deeply optimizing subsystems.
- Prefer a simple real implementation behind a strong replaceable
  interface.
- Runtime, executor, gateway, model source, storage provider, connector,
  telemetry provider, frontend and licensing provider remain replaceable.
- Docker is not mandatory. Native process execution is first class.
- vLLM and LiteLLM are not permanent dependencies.
- Detect capabilities and decide from capabilities. No hardware-specific
  if/else trees.
- Reuse existing platform seams before creating new abstractions or
  scripts.
- Plug-and-play installability is a product requirement, not a
  convenience.
- Security, permissions and privacy architecture is non-negotiable.
  Permission-aware retrieval is required; customer prompts, responses,
  documents and RAG content stay local by default.
- Access control lives above the inference server. Do not put user
  authorization inside vLLM, and do not put licensing logic inside
  ResourceManager or runtime adapters.
- Persisted models are a reusable warehouse. Stored does not mean
  runnable on this host; do not delete incompatible artifacts, and do not
  redownload when a compatible artifact exists.
- Raw filesystem-reported free space, such as `df` output, is **not** the
  platform storage budget. It is one input signal. The platform's own
  storage capacity resolution, Capacity Sonar evidence and commit
  admission logic decide what is usable. Network and overlay filesystems
  routinely report the underlying shared volume rather than the usable
  quota.

---

## Current phase

**Phase 9 — Resource Manager / Multi-model Lifecycle.**

Scope, exclusions, exit criteria and remaining work are defined in
`docs/ROADMAP.md`.

---

## Current verified technical state

### Git / GitHub

- Repository: `dlealvilla/ai-stack` (private).
- GitHub is the authoritative source of truth.
- `main` = last accepted stable baseline, commit `eac040e`.
- `phase9` = active Phase 9 development, workflow commit `a7b2536`.
- Never commit directly to `main` during Phase 9 development.

### ResourceManager

ResourceManager exists and owns the lifecycle:

- `preview_start`
- `start_model`
- `stop_workload`
- `workload` / `workloads`
- `snapshot`

Resource reservation semantics:

- reserve before runtime mutation
- roll back the reservation if runtime start fails
- conservative state handling on persistence errors
- stop the runtime before releasing the resource reservation

ResourceManager remains generic and runtime-agnostic.

### Existing concrete adapters

- `JsonFileReservationStore`
- `JsonFileWorkloadStateStore`
- `ProcessExecutorRuntime`
- `VllmInventoryServiceSpecProvider`
- `VllmRuntimeAwareReservationPlanningProvider`

Runtime-aware vLLM reservation planning exists and remains in an adapter
rather than in ResourceManager.

A prior accounting bug was fixed so live observed safe availability is not
double-subtracted against managed reservations.

### Demonstrated runtime behavior

Real Qwen lifecycle has previously been demonstrated on NVIDIA Blackwell:

- ResourceManager-controlled start
- vLLM serving
- `/v1/models` success
- real inference on previous acceptance
- safe denial of an unsafe second workload
- ResourceManager-owned stop
- reservation release
- clean GPU/process/port state

Managed vLLM runtime provisioning already exists through the platform
runtime-management seam and has successfully reconstructed vLLM on a new
host.

Known validated runtime stack:

- vLLM 0.10.2
- torch 2.8.0+cu128
- CUDA 12.8
- NVIDIA Blackwell

---

## Known unresolved issue

A later clean startup smoke on a different host reached:

- ResourceManager admission allowed
- runtime started
- `/v1/models` HTTP 200

but the test client timed out waiting for `/v1/chat/completions`.

ResourceManager cleanup still succeeded:

- workload count 0
- reservation count 0
- runtime stopped

Treat this as an unresolved smoke-test/runtime-response issue, **not** as
evidence of corrupted ResourceManager state.

## Known unresolved issue — foreground storage characterization cost

A clean-room acquisition attempt proved the storage machinery is sound
and correctly fails closed, but is operationally too expensive in the
foreground. Against a 6.70 GiB transaction requirement, calibration ran
about 48 minutes without converging, because it searched for the pool
ceiling rather than stopping once evidence exceeded the requirement.
Interruption also lost all empirical evidence, and the probe orphaned a
42,990 MiB temporary file because it ran in a daemon HTTP worker thread.

The integration code that exposed this is preserved as experimental
evidence only, not accepted implementation, under
`/workspace/checkpoints/step-chain/`. Remediation is designed in
`docs/CAPACITY_ARCHITECTURE.md` as decision-bounded characterization
(steps C3A to C3C).

---

## Bootstrap layering

Four distinct things are easy to confuse. Keep them separate.

**A. Development source retrieval.** Getting this repository onto a host
is a plain `git`/`gh` clone or pull from GitHub. It is a developer
workflow step, not a product feature, and it is not part of the customer
bootstrap experience.

**B. Existing platform orchestration.** The repository's `./ai`
executable and the platform components behind it already own host
inspection, planning, runtime preparation, preflight, lifecycle, status,
health and acceptance. This is the current working orchestration surface.

**C. Provisional bootstrap/resume coordinator.** An early
platform-owned layer that progressively ties the *existing* seams
together: host detection, storage capacity/sonar, inventory, model
compatibility and selection, runtime management, ResourceManager and
health. It is a coordinator over what already exists.

It must **not** become a parallel bootstrap system, and it does not
replace the `./ai` architecture or duplicate its logic. Where the
coordinator needs behavior, extend or call the existing seam.

**D. Phase 16 bootstrapper.** The polished customer-facing
installer, conversational onboarding, packaging and recovery UX. That is
a later phase and is not what C is.

## Development workflow

Mac/Cursor
→ edit
→ test where possible
→ commit
→ push `phase9`
→ GitHub
→ RunPod fetch/pull
→ GPU/integration acceptance

RunPod is an execution and acceptance-test host, not the source of truth.
Legitimate RunPod-side fixes may be committed and pushed, then pulled back
to the Mac clone. Do not leave source modifications only on RunPod.

Never commit secrets, model weights, runtime environments, logs, PID
files, workload/reservation state or caches. Keep `.gitignore`
protections intact.

See `docs/DEVELOPMENT_WORKFLOW.md` for the branch and GPU-testing rules.

---

## Immediate next actions

1. Diagnose/resolve the Qwen chat-completion smoke timeout.
2. Implement persisted workload/reservation reconciliation and recovery
   (Step 07).
3. Begin provisional host-aware bootstrap/resume orchestration using the
   existing platform seams.
4. Bind platform/runtime request concurrency to runtime-specific controls
   through adapters.
5. Prove at least two genuinely simultaneous inference-server instances
   with safe per-instance resource allocations.
6. Expose ResourceManager lifecycle through Platform API.
7. Run integrated Phase 9 acceptance.
8. Merge accepted Phase 9 into `main`.

---

## Agent working rules

- Inspect the source instead of inventing APIs from memory.
- Make the smallest change that advances the current phase contract.
- Do not pull future roadmap features into the active phase merely
  because they are interesting.
- Preserve replaceability and backward compatibility unless there is an
  explicit migration.
- Run focused tests after changes.
- For GPU/runtime behavior, distinguish local/unit evidence from real
  RunPod acceptance.
- Do not push unless explicitly asked. Show diffs before commit when
  requested.
