# Stage 1.6 — Runtime-first architecture + real inference

**Milestone 1 — Walking skeleton.**

Status: **OPEN.** Gate A+B close at `L1` / `READY_FOR_T5`. Gate C (real
vLLM on fresh NVIDIA hardware) is required before `L3` close and before
merge into `kultrun`.

This stage changes **ordering and responsibility**, not merely “add a
runtime check.” Normal guided deployment becomes:

```text
HOST → RUNTIME → VERIFY → ELIGIBLE MODELS → CAPACITY → SELECT
  → PLAN → ACQUIRE → RESERVE → RUN
```

## CURRENT STAGE

Runtime-first contracts, host-driven runtime planning, verification,
eligibility ≠ capacity, persisted `DeploymentPlan`, explicit
`NORMAL_EXECUTION` vs `STORE_ONLY`, fixture full stack to a running
instance, and a real-vLLM seam for T5.

## PREDECESSOR OUTPUTS

| Consumed | From |
|---|---|
| Stage 1.5B CLOSED L1 | `620a78be94433a0e8a6624d36147b0e870fafd61` |
| Safety tag | `checkpoint/stage-1.5B-closed-620a78b` |
| Safety branch | `safety/pre-runtime-first-620a78b` |
| STORED artifact / reservation / instance lifecycle | 1.4C / 1.5A / 1.5B |
| SAFE capacity, 20–100% policy, llmfit AUTO | 1.2 / 1.4B |

## THIS STAGE'S REQUIRED OUTPUT

```text
RuntimeCandidate → RuntimeProvisioningPlan → RuntimeInstallation
  → VERIFIED RuntimeCapabilityProfile
  → RuntimeEligibleModelCandidate → FeasibleModelCandidate
  → SelectedDeploymentCandidate → persisted DeploymentPlan
  → NORMAL acquisition | STORE_ONLY
  → ResourceReservation → InferenceInstance
```

Gate C additionally: real isolated vLLM provision, verification **before**
recommendation, real generation, physical VRAM vs reservation.

## CORE CONTRACTS AFFECTED

`runtime.candidate`, `runtime.provisioning_plan`, `runtime.installation`,
`runtime.capability_profile`, `runtime.policy` (new).
`planning.runtime_capability_snapshot`, `planning.runtime_eligible_candidate`,
`planning.feasible_candidate`, `planning.selected_deployment` (new).
`planning.deployment_plan` additive fields.
`planning.selection_recommendation` gains `RUNTIME_NOT_VERIFIED`.
`model.acquisition_request` additive `mode` / `plan_id`.
`resource.request` additive plan/profile provenance.

## ADAPTERS AFFECTED

`adapters/runtime/fixture_vllm` — architecture/T2 path; launches the
reference serving workload. Not a production runtime.
`adapters/runtime/vllm` — replaceable production seam; isolated component
environment; pinned intended version `0.10.2`.
Reference serving remains REFERENCE / TEST_ONLY.

## PERSISTED STATE

`RuntimeInstallation`, `RuntimeCapabilityProfile`, `DeploymentPlan`.
On restart, profile status is revalidated against a verification
fingerprint (runtime/executor/accelerator/driver — not free RAM).
ModelArtifact stays runtime-independent.

## MUTATION / FAILURE BOUNDARY

NORMAL acquire without a current VERIFIED plan is refused.
STORE_ONLY never creates a reservation or instance.
Stale profile blocks new recommendation, NORMAL acquire, reservation,
and start. A running instance is not auto-killed. Launch failure does
not fall back to another runtime.

## CANCELLATION / CLEANUP

Failed provision/verify leaves a FAILED or absent profile, never VERIFIED.
Failed NORMAL acquire keeps the existing staging/cleanup rules.
Failed start: instance FAILED, reservation ACTIVE.

## ACCEPTANCE LEVEL

Gate A+B: **L1** (T0/T1/T2). Stage stays OPEN / READY_FOR_T5.
Gate C: **L3** on a fresh Linux/NVIDIA host. L1 cannot close real inference.

## ADMIN SURFACE

Runtime candidate / provision / verify APIs and CLI; selection blocked
until verified; acquire by plan or explicit store-only; Console runtime
setup panel; unambiguous Store Only vs plan-backed deploy.

## DEBT ENTRIES

K-54 fixture-vLLM is not production vLLM.
K-55 llama.cpp / MLX production adapters deferred.
K-56 catalog query push-down deferred.
K-57 isolated vLLM environment is a minimal venv, not a component manager.
K-51 remains until T5 generation evidence exists.

## DEFERRED ITEMS

Gateway, streaming, analytics, scheduler, automatic runtime switching,
multi-GPU, training, auto-kill on staleness, second production runtime.
