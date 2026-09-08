# Stage 1.6J — Plan-Driven Acquisition + Resource Admission

**Milestone 1 — Walking skeleton.**

Status: **CLOSED — L1.** Checkpoint:
`checkpoints/STAGE-1.6J-deployment-prepare.json`.

This stage migrates already-built executable acquisition and
ResourceManager admission onto the CURRENT `DeploymentPlan`. It does
not reopen Stages 1.6B–1.6I. It does not create InferenceInstance or
launch a runtime.

STORE_ONLY warehouse acquisition remains independent of the plan.

```text
CURRENT STAGE                Plan-driven acquisition and resource
                             admission. CURRENT DeploymentPlan is
                             execution intent. Stop before
                             InferenceInstance.
PREDECESSOR OUTPUTS          Stage 1.6I CLOSED L1
                             (`dd45e7eca54a630a2d2048c2b17dd64cca1958af`).
THIS STAGE'S REQUIRED OUTPUT Plan-driven acquire/reuse of the exact
                             selected ModelArtifact; ResourceRequest
                             from DeploymentPlan.resource_request plus
                             artifact_id; ResourceManager admission;
                             ResourceReservation; STORE_ONLY preserved.
CORE CONTRACTS AFFECTED      None new. Existing ResourceRequest,
                             ModelArtifact, ResourceReservation.
ADAPTERS AFFECTED            None.
PERSISTED STATE              Existing artifacts and reservations.
                             PreparedDeployment is not persisted.
MUTATION / FAILURE BOUNDARY  POST acquire/admit/prepare. STALE and
                             UNAVAILABLE refuse. Admission refusal
                             does not mutate the plan.
CANCELLATION / CLEANUP       Existing acquisition and reservation
                             release. Duplicate ACTIVE reuse by
                             request_id.
ACCEPTANCE LEVEL             L1 CLOSED. T0/T1 plus T2 clean-wheel
                             fixture chain. T3 not required.
ADMIN SURFACE                POST /v1/deployments/plan/acquire|admit|prepare;
                             kultrun deployments acquire|admit|prepare;
                             Console Prepare deployment.
DEBT ENTRIES                 K-66, K-77 remain OPEN.
                             plan_from non-authoritative.
                             plan_for_entry residual on artifact-id
                             reserve until InferenceInstance remap.
```

## Flow

```text
Verified Runtime
        ↓
Eligible Models
        ↓
ModelRequirement
        ↓
Capacity
        ↓
ModelSelection
        ↓
DeploymentPlan
        ↓
ModelArtifact
        ↓
ResourceRequest
        ↓
ResourceManager
        ↓
ResourceReservation
        ↓
[STOP 1.6J]
```

Future, **not implemented here**:

```text
CURRENT DeploymentPlan
        +
exact ModelArtifact
        +
matching ResourceReservation
        ↓
InferenceInstance
        ↓
real serving
```

## Authority

`DeploymentPreparationService` consumes a CURRENT plan. It does not
rank models, estimate requirements, or calculate capacity. Exact
inventory match is reused. Resource amounts come from the plan, not
`plan_for_entry`. ResourceManager is the live physical decision.

## Surfaces

- `POST /v1/deployments/plan/acquire`
- `POST /v1/deployments/plan/admit`
- `POST /v1/deployments/plan/prepare`
- `kultrun deployments acquire|admit|prepare`
- Console **Prepare deployment**

GET `/v1/deployments/plan` remains read-only. STORE_ONLY remains
`POST /v1/models/acquire?candidate=` and `kultrun models acquire <id>`.
`kultrun models acquire --recommended` consumes the CURRENT plan.

## Residual

`plan_from` remains a non-authoritative recommendation projection.
`plan_for_entry` remains on the artifact-id reservation path used by
the residual `POST /resources/reservations?artifact_id=` API. That
path is not InferenceInstance authority after Stage 1.6K.
