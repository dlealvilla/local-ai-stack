# Stage 1.6L — First Real vLLM Inference Vertical

**Milestone 1 — Walking skeleton.**

Status: **OPEN — Stream A capture-lifetime fix integrated with frozen
Phase 0 telemetry. K-96 still requires this integration wheel on a new
GPU host. Stage 1.6M not started.**
Checkpoint: `checkpoints/STAGE-1.6L-real-vllm-inference.json`.

This stage extends the authoritative preparation chain into real serving.
It does not reopen Stages 1.6B–1.6K. It does not implement container GPU,
llama.cpp, MLX, streaming, cancellation, routing, or a chat frontend.

```text
CURRENT STAGE                First real native vLLM serving. CURRENT
                             DeploymentPlan + local ModelArtifact +
                             ACTIVE reservation launch one vLLM process
                             through NativeProcessExecutor. Bounded
                             Kultrun inference returns generated text.
PREDECESSOR OUTPUTS          Stage 1.6K CLOSED L1
                             (`1e51f13ec2a7c2e1fa34b6a3ec0c92f712d4b43e`).
THIS STAGE'S REQUIRED OUTPUT Exact RuntimeInstallation; local artifact;
                             loopback RuntimeLaunchSpec; readiness;
                             InferenceRequest/Response; API + CLI infer.
                             Staged Available Models funnel before
                             ModelSelector. Estimated-feasible is not
                             Available; vLLM members require resolved
                             highest-pressure runtime-memory calibration.
CORE CONTRACTS AFFECTED      runtime.launch_request optional serving
                             fields; runtime.memory_profile@1;
                             inference.request@1;
                             inference.response@1. No VllmRuntimeV2.
ADAPTERS AFFECTED            existing vLLM runtime adapter.
PERSISTED STATE              InferenceInstance endpoint/ready/lifecycle.
                             Prompts and responses are not persisted.
MUTATION / FAILURE BOUNDARY  START launches native vLLM. Infer requires
                             RUNNING + ready + ACTIVE reservation.
                             STOP terminates the process.
CANCELLATION / CLEANUP       Readiness timeout stops the process.
                             Reservation remains until explicit release.
                             Artifact retained.
ACCEPTANCE LEVEL             L3 required. T0/T1/T2 local is not closure.
ADMIN SURFACE                GET /v1/models/available; POST /v1/models/available/refresh;
                             kultrun models available; Console Available Models
                             before Model selection; POST /v1/inference/instances/start|stop|infer;
                             kultrun instances start|inspect|infer|stop.
DEBT ENTRIES                 K-66, K-77 remain OPEN. K-95 deferred depth.
                             K-96 llmfit plan is not native vLLM serving;
                             measured runtime-memory calibration is the
                             Available gate, still OPEN until T3.
                             K-97 Hub ingest deferred. K-98 live Accelerate
                             remains optional/structural-only; default
                             product path stays offline. K-99 native
                             process capture files are not rotated.
```

## Flow

```text
MODEL UNIVERSE
        ↓
source discovery (hints)
        ↓
Kultrun compatibility prefilter
        ↓
cheap factual weight bound
        ↓
deep ModelRequirement
        ↓
ESTIMATED-FEASIBLE (not Available)
        ↓
highest-pressure runtime-memory calibration
        ↓
CALIBRATED ModelRequirement
        ↓
one CurrentCapacitySnapshot
        ↓
AvailableModelView
        ↓
PRINT / API / Admin
        ↓
ModelSelector
        ↓
DeploymentPlan
        ↓
ModelArtifact
        ↓
ResourceReservation
        ↓
InferenceInstance
        ↓
vLLM RuntimeAdapter
        ↓
RuntimeLaunchSpec
        ↓
NativeProcessExecutor
        ↓
REAL vLLM
        ↓
Readiness
        ↓
Inference
```

This is the first real serving vertical. ContainerExecutor GPU,
multi-runtime, multi-GPU, and production chat UX are not complete.

## Authority

The DeploymentPlan remains authoritative for model, revision,
quantization, runtime, version, executor, GPU, and context.
`InstanceService` owns lifecycle and must not import `planning` or
`platform`. The vLLM adapter owns argv, readiness, and HTTP
translation. NativeProcessExecutor owns process mechanics.

Reference-serving remains isolated test infrastructure and cannot
substitute for product vLLM.

## Surfaces

- `GET /v1/models/available` (no persist, no recommendation)
- `POST /v1/models/available/refresh` (persist; does not select)
- `kultrun models available` (funnel + Available Models; no recommend)
- `kultrun models recommend|select` print Available Models first
- Console Available Models panel before Model selection
- `POST /v1/inference/instances/start`
- `POST /v1/inference/instances/infer`
- `POST /v1/inference/instances/stop`
- `kultrun instances start|inspect|infer|stop`
- Console modest Infer probe on RUNNING cards

## Residual

Streaming, cancellation, automatic crash recovery, request queues,
harder-than-runtime GPU memory enforcement, and richer observability
remain K-95. Admitted VRAM is translated into vLLM
`--gpu-memory-utilization` on the native serving path; that is a runtime
budget control, not a kernel-enforced VRAM cgroup.

Available Models is produced before ModelSelector. Recommendation does
not define availability. Cheap weight evidence is a lower bound, not a
serving total. Accelerate is optional and is not vLLM authority. AUTO
refines successful llmfit vLLM plan components rather than shopping
estimators. Feasibility compares a runtime-specific `ModelRequirement`
to one `CurrentCapacitySnapshot` (SAFE minus ACTIVE) for the whole
pass. Hypothetical candidates do not consume capacity. Stored artifacts
consume storage via live free space; they do not consume VRAM.
ResourceManager remains final admission. Provider-enabled T2 is the
same wheel in two isolated installs: T2-A core-only offline catalog
and Kultrun fallback; T2-B extras `acquisition,estimators,analysis`
with `KULTRUN_MODEL_SOURCE_MODE=live`. A first fresh-host T3 proved calibrated admission and a healthy vLLM
process, but `instances start` did not return: readiness polling
persisted growing execution logs through FileStore fsync, and a
concurrent inspect could write UNKNOWN over STARTING. Local Stream A
bounded that loop and refuses to treat inspect-during-STARTING as a
control-plane restart. A second physical T3 then reached RUNNING/READY
and printed success, but the launching CLI stayed alive: non-daemon
`kultrun-exec-capture` threads blocked on stdout/stderr pipes of a child
that never EOF'd. NativeProcessExecutor now captures a bounded prefix from
anonymous files so the launching interpreter can exit while the serving
child keeps writing. K-31 remains OPEN: a later CLI still does not own
Popen and must not signal the child; `instances infer` uses the
persisted endpoint and does not require that ownership. Capture files
are not rotated (K-99). Stream B later warehouse phases are K-100 in
this integration ledger. K-96 stays OPEN until this integration wheel on
a **new** GPU host observes READY, a returned start CLI, and T5
inference. Do not reuse `216.81.151.62`. Do not begin Stage 1.6M from
this freeze.

## Physical T3/T5 order

Mandatory Stage 1.6L physical sequence:

```text
start instance
→ start CLI returns
→ DO NOT inspect/list/reconcile
→ instances infer
→ prove generated text
→ capture non-destructive evidence
```

`instances inspect`, `instances list`, and `instances reconcile` from a
second process persist UNKNOWN (K-31). That must not run before T5.

Cross-process stop/restart is **not** a Stage 1.6L gate. K-31 refuses
to signal a process this control plane did not start. In-process stop
in a safely owning context remains optional.

Acceptance host setup uses `tools/acceptance/sandbox/` on the
acceptance branch only. Those scripts are not product code and are not
in the wheel.
