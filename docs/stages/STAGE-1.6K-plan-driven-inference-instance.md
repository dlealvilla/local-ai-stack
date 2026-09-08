# Stage 1.6K — Plan-Driven InferenceInstance

**Milestone 1 — Walking skeleton.**

Status: **CLOSED — L1.** Checkpoint:
`checkpoints/STAGE-1.6K-plan-driven-inference-instance.json`.

This stage migrates the already-built `InferenceInstance` onto the
authoritative preparation chain. It does not reopen Stages 1.6B–1.6J.
It does not implement real vLLM serving, a production endpoint, or
prompt/response.

```text
CURRENT STAGE                Plan-driven InferenceInstance. CURRENT
                             DeploymentPlan + matching artifact +
                             matching ACTIVE reservation create one
                             instance. Stop before real vLLM serving.
PREDECESSOR OUTPUTS          Stage 1.6J CLOSED L1
                             (`92be1c7796060e3add08bc6790b77bee134b708c`).
THIS STAGE'S REQUIRED OUTPUT Plan-driven InferenceInstance create;
                             three-way match; plan provenance;
                             configuration currentness; START of a
                             vLLM plan refused; reference lifecycle
                             preserved for explicit reference runtime.
CORE CONTRACTS AFFECTED      inference.instance@1 optional provenance
                             fields. No InferenceInstanceV2.
ADAPTERS AFFECTED            None.
PERSISTED STATE              Existing InferenceInstance plus plan
                             provenance fields.
MUTATION / FAILURE BOUNDARY  POST /inference/instances. STALE and
                             UNAVAILABLE refuse create. START refuses
                             stale plan and unsupported vLLM launch.
CANCELLATION / CLEANUP       Existing stop and reservation release.
                             Release still blocked while live.
ACCEPTANCE LEVEL             L1 CLOSED. T0/T1 plus T2 clean-wheel
                             fixture chain. T3 not required.
ADMIN SURFACE                POST /v1/inference/instances;
                             kultrun instances create;
                             Console Create instance.
DEBT ENTRIES                 K-66, K-77 remain OPEN.
                             plan_from remains non-authoritative.
                             plan_for_entry residual on artifact-id
                             reservation only; not instance authority.
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
ResourceReservation
        ↓
InferenceInstance
        ↓
[STOP 1.6K]
```

Future, **not implemented here**:

```text
InferenceInstance
        ↓
real vLLM RuntimeLaunchSpec
        ↓
Executor
        ↓
model load
        ↓
readiness
        ↓
inference endpoint
        ↓
prompt / response
```

## Authority

`DeploymentInstanceService` consumes a CURRENT plan, a matching
artifact, and a matching ACTIVE reservation. It does not select a
model, estimate requirements, evaluate capacity, acquire, or admit.
`InstanceService` still owns lifecycle and must not import
`planning` or `platform`.

A product vLLM plan cannot start the reference-serving adapter.
Reference lifecycle remains isolated test infrastructure.

## Surfaces

- `POST /v1/inference/instances`
- `POST /v1/inference/instances/start`
- `POST /v1/inference/instances/stop`
- `kultrun instances create|start|stop|inspect`
- Console **Create instance**

## Residual

`plan_from` remains a non-authoritative recommendation projection.
`plan_for_entry` remains on the artifact-id reservation path only.
It is not part of normal deployment execution and is not
InferenceInstance authority.
