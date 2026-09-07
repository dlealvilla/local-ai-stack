# Stage 1.6 — Runtime-first migration map

Inspected against repository HEAD `620a78be94433a0e8a6624d36147b0e870fafd61`
(Stage 1.5B closed L1). This note records the **actual** 1.5B orchestration
and the target 1.6 dependency direction. It is not a claim that 1.5B used
the new architecture.

Safety anchors (do not delete):

- tag `checkpoint/stage-1.5B-closed-620a78b`
- branch `safety/pre-runtime-first-620a78b`
- feature branch `stage/1.6-runtime-first`

`kultrun` stays at the 1.5B close until Gate C passes.

---

## Actual current orchestration (1.5B)

```text
Host Discovery → SAFE Capacity
  → Model Catalog (source-neutral)
  → SelectionService.recommend(envelope, candidates, product_identities())
  → ephemeral DeploymentPlan
  → AcquisitionService.acquire(candidate)     # no plan required
  → STORED ModelArtifact
  → AdmissionService.reserve(artifact)        # re-runs plan_for_entry
  → InstanceService.create()                  # defaults to reference-serving
  → start → reference HTTP readiness
```

`RuntimeCatalogue.product_identities()` excludes `reference-process` and
`reference-serving`. With only those adapters registered, the tuple is
empty, so planning's runtime-overlap check does not run. Catalog
`supported_runtimes` values such as `vllm` are metadata only.

There is no `RuntimeCandidate`, `RuntimeProvisioningPlan`,
`RuntimeInstallation`, `RuntimeVerifier`, or `RuntimeCapabilityProfile`.
`DeploymentPlan` and `SelectionRecommendation` are not persisted.
`POST /v1/models/acquire` takes a candidate id (or `--recommended`).

---

## Target orchestration (1.6)

```text
HostCapabilities
  → RuntimeResolver → RuntimeCandidate[]
  → RuntimeProvisioningPlan → RuntimeInstallation
  → RuntimeVerifier → VERIFIED RuntimeCapabilityProfile
  → ModelMetadata (catalog remains source-neutral)
  → RuntimeEligibilityEvaluator → RuntimeEligibleModelCandidate
  → ModelRequirement (verified runtime on the estimate request)
  → CapacityAssessment / FeasibleModelCandidate
  → ModelRecommendation → SelectedDeploymentCandidate
  → persisted DeploymentPlan
  → NORMAL_EXECUTION acquisition  |  explicit STORE_ONLY warehouse
  → ResourceReservation (plan-derived)
  → InferenceInstance (runtime already chosen; no re-selection)
```

Invariant: **NORMAL execution acquisition must not download a production
model unless a VERIFIED operational runtime/executor path exists, the
candidate is runtime-eligible, and a DeploymentPlan exists.**

Exception: **STORE_ONLY** may store an artifact without a verified runtime.
`currently_runnable` is derived, not a ModelArtifact lifecycle field.

---

## Placement (tier law)

| Concept | Owner | Why |
|---|---|---|
| RuntimeCandidate, ProvisioningPlan, Installation, CapabilityProfile, Resolver | `runtime` (tier 5) | Execution-environment facts. May import `host.contracts`. Must not import `model`, `planning`, `capacity`, `execution`. |
| RuntimeProvisioner, RuntimeVerifier ports | `runtime` | Implementations in `adapters/runtime`. |
| RuntimeCapabilitySnapshot, eligibility, FeasibleModelCandidate, SelectedDeploymentCandidate | `planning` (tier 4) | Planning must not import `runtime`. Snapshot is the same pattern as `DeploymentCapacity`. |
| AcquisitionMode | `model` | Warehouse vs execution is an acquisition semantic. Preconditions for NORMAL are enforced in `platform`. |
| RuntimeSetupService, DeploymentService | `platform` (tier 8) | Maps profiles → snapshots; sequences provision/verify/select/acquire/admit. |
| ResourceRequest.plan_id / runtime_profile_id | `resource` | Provenance copies, not a second decision. |

---

## Component map

### Host discovery

| | |
|---|---|
| CURRENT IN | live inspection or fixture replay |
| CURRENT OUT | `HostCapabilities` (accelerators, `execution.native_process` / docker / podman) |
| TARGET | unchanged; becomes input to `RuntimeResolver` |
| WHY | host-driven runtime planning |
| CALLERS | `RuntimeSetupService` |
| PERSISTENCE | existing host inventory |
| API/CLI/UI | existing host surfaces |
| TESTS | existing host fixtures; new resolver tests |

### Runtime catalogue / adapters

| | |
|---|---|
| CURRENT IN | registered `InferenceRuntime` adapters |
| CURRENT OUT | `RuntimeProfile`, `RuntimeLaunchSpec` |
| TARGET | plus support tier; fixture-vLLM (T0–T2) and real vLLM seam (T5); reference-serving is REFERENCE / TEST_ONLY |
| WHY | product identities must not treat harnesses as executable production runtimes |
| CALLERS | resolver, instance start |
| PERSISTENCE | none for profiles; installations persist separately |
| TESTS | catalogue excludes REFERENCE from AUTO product selection |

### RuntimeResolver

| | |
|---|---|
| CURRENT | does not exist |
| TARGET IN | `HostCapabilities`, executor facts on the host, registered providers, `RuntimePolicy` |
| TARGET OUT | `RuntimeCandidate[]` |
| WHY | host-driven runtime planning; no model required |
| AUTO | preferred PRODUCT or FIXTURE candidate; never REFERENCE |
| EXPLICIT | evaluate that runtime only; incompatible fails clearly |
| PERSISTENCE | candidates are recomputed |
| API | `GET /v1/runtimes/candidates` |
| TESTS | NVIDIA → vLLM candidate; MLX unsupported on Linux; explicit incompatible fails |

### Runtime provisioning / verification

| | |
|---|---|
| CURRENT | none (runtimes assumed present) |
| TARGET | `RuntimeProvisioningPlan` → `RuntimeProvisioner` → `RuntimeInstallation` → `RuntimeVerifier` → `RuntimeCapabilityProfile` |
| WHY | installed ≠ operational ≠ model-compatible |
| ISOLATION | real vLLM installs into a Kultrun-managed environment under `state_root`, not the core venv |
| PIN | intended `vllm==0.10.2` (legacy validated pin); T5 records the version that actually passes |
| PERSISTENCE | `RuntimeInstallation`, `RuntimeCapabilityProfile` |
| API | `POST /v1/runtimes/provision`, `POST /v1/runtimes/verify`, `GET /v1/runtimes` |
| TESTS | broken provision; installed but unverified; upgrade → STALE |

### RuntimeCapabilityProfile

| | |
|---|---|
| CURRENT | absent |
| TARGET | platform-owned capability + verification evidence; no raw vLLM objects |
| STATUS | UNVERIFIED / VERIFIED / FAILED / STALE |
| STALE WHEN | runtime version, executor, host/accelerator identity, or driver/backend identity changes |
| NOT STALE WHEN | free RAM or current VRAM availability changes |
| ONLY VERIFIED | authorizes executable-model selection |
| PERSISTENCE | independent of `ModelArtifact` |

### Model catalog / ModelSource

| | |
|---|---|
| CURRENT IN/OUT | catalog query → `ModelMetadata[]` |
| TARGET | unchanged output; optional runtime-aware query is an optimization only |
| WHY | catalog must not claim final compatibility |
| CALLERS | eligibility evaluator; warehouse browse |
| UI | catalog remains available before verification; executable recommendation is blocked |

### RuntimeEligibilityEvaluator

| | |
|---|---|
| CURRENT | overlap of `supported_runtimes` ∩ `available_runtimes` inside `evaluate()` |
| TARGET IN | `ModelMetadata` + planning `RuntimeCapabilitySnapshot` (mapped from a VERIFIED profile) |
| TARGET OUT | `RuntimeEligibleModelCandidate` |
| WHY | eligibility ≠ capacity; planning must not import `runtime` |
| HARD FILTER | unsupported architecture / format / quantization / stale profile → no capacity estimate as an executable candidate |
| TESTS | unsupported format/arch/quant; stale profile |

### Estimator / capacity

| | |
|---|---|
| CURRENT IN | `ModelEstimationRequest.runtime` from metadata's first supported runtime (often hypothetical `vllm`) |
| TARGET IN | the **verified** runtime family/profile on the estimation request |
| CAPACITY IN | SAFE envelope minus current ACTIVE reservations, as planning-owned `CapacityCommitments` (platform copies numbers; planning ⟂ resource) |
| TARGET OUT | `FeasibleModelCandidate` wrapping evaluation |
| POLICY | 20–100% preferred band unchanged; llmfit does not choose runtime |
| TESTS | eligible but insufficient current VRAM |

### ModelSelector / DeploymentPlan

| | |
|---|---|
| CURRENT IN | raw catalog + empty product identities |
| CURRENT OUT | ephemeral `DeploymentPlan` (runtime name only, no profile/version) |
| TARGET IN | already-evaluated feasible candidates + policy |
| TARGET OUT | persisted `DeploymentPlan` with profile/installation/version/executor/host/eligibility/capacity evidence and a plan fingerprint |
| FRESHNESS | reject NORMAL acquire/start if referenced profile is not current VERIFIED |
| PERSISTENCE | **new** — plans are stored so acquire/reserve resolve server-side |
| API | `GET /v1/models/selection` returns `RUNTIME_NOT_VERIFIED` when none exist |

### Acquisition

| | |
|---|---|
| CURRENT IN | `ModelAcquisitionRequest` from candidate id |
| TARGET | explicit `NORMAL_EXECUTION` (plan id) vs `STORE_ONLY` (candidate) |
| NORMAL | plan exists, profile VERIFIED/current, candidate eligible, storage admitted |
| STORE_ONLY | storage admitted; no runtime, plan, reservation, or instance |
| BYPASS | candidate-only NORMAL is rejected; missing mode is rejected on the API |
| ARTIFACT | remains runtime-independent |
| TESTS | no acquire without plan; store-only without runtime; stale plan rejected |

### Resource admission

| | |
|---|---|
| CURRENT | `reserve(artifact_id)` re-plans from catalog |
| TARGET | `reserve(plan_id)` after STORED artifact; request carries plan/profile provenance |
| STALE PROFILE | no new execution reservation |
| CALLERS | API/CLI/Console reservation actions |
| TESTS | reservation uses selected runtime plan |

### InferenceInstance

| | |
|---|---|
| CURRENT | `create` defaults `reference-serving`; does not read the plan |
| TARGET | runtime from persisted `ResourceRequest` / plan; client does not send runtime |
| START | blocked if referenced profile is STALE/FAILED |
| FALLBACK | launch failure does not invoke another runtime |
| REFERENCE | still used as the fixture-vLLM launch recipe and as a REFERENCE harness |
| TESTS | no post-plan fallback; stale profile blocks start; 1.5B lifecycle updated to name runtime on the request |

### API / CLI / Console

| Surface | Change |
|---|---|
| `GET /v1/runtimes/candidates` | new |
| `POST /v1/runtimes/provision` | new |
| `POST /v1/runtimes/verify` | new |
| `GET /v1/runtimes` | installations + profiles |
| `GET /v1/models/selection` | requires VERIFIED profile; richer chain |
| `POST /v1/models/acquire` | mandatory `mode`; NORMAL needs `plan_id` |
| `POST /v1/resources/reservations` | `plan_id` (not client RAM/VRAM) |
| CLI | `kultrun runtimes …`; acquire `--plan` / `--store-only` |
| Console | Runtime setup panel; Store Only vs plan-backed acquire; no ambiguous Acquire |

---

## Persistence

New record kinds: `runtime.installation`, `runtime.capability_profile`,
`planning.deployment_plan` (now stored). Additive optional fields on
`model.acquisition_request` and `resource.request`. Historical Stage 1.4 /
1.5A / 1.5B checkpoint files are not rewritten.

---

## Tests that prove the new connection

`tests/test_runtime_first.py` — T0 contracts and T1 full-stack / negative
traces. Existing acquisition tests become explicit STORE_ONLY.
`tests/architecture.py` — runtime does not import model/planning; planning
does not import runtime; inference does not select runtime.
