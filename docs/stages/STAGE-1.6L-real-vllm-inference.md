# Stage 1.6L — First Real vLLM Inference Vertical

**Milestone 1 — Walking skeleton.**

Status: **CLOSED L3 — VLLM INSTALLATION-TO-INFERENCE + RESTART VERTICAL:
PHYSICALLY CLOSED.** Guided DeploymentReport observability frozen with
this stage package.

Physical reference: `ba04df2f94ae7ff9e0fdeef3ec4cf0af20186b6a`
Build: `0.1.0+ba04df2f94ae`
Wheel SHA256: `d4369a6edec0d877f78c3f2c1ad3b96643e267bfc768a1dffb801a49ad3968eb`

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
are not rotated (K-99). K-96 remains estimator/calibration debt, not the
T5 serving proof.

## Physical T5 close

On `ba04df2f94ae7ff9e0fdeef3ec4cf0af20186b6a` the product proved:

```text
installation → inference → stop → restart → second inference → stop
```

Ubuntu 24.04, NVIDIA RTX PRO 4500 Blackwell, 31.9 GiB VRAM. `/workspace`
MooseFS/FUSE Sonar 16/24/32 GiB PASS, 48 GiB EDQUOT. vLLM 0.28.0 ~7.7 GiB.
Available Models: Qwen 0.5B AWQ and Qwen 7B AWQ. AUTO selected Qwen 7B AWQ.
Inference 1 PASS ~686 ms. Stop released GPU 0. Restart PASS. Inference 2
PASS ~473 ms. Final stop PASS. Reservation held. OVERALL PASS.

Shared-volume leftover from a predecessor install was operator reclaim,
not a product deployment failure.

## Observability freeze

`DeploymentRun` (`drun_…`) is the correlation identity reused across CLI
processes via `KULTRUN_STATE_ROOT`. `OperationalFact.correlation_id`
carries it. `DeploymentReport` is the single projection for live CLI
progress, the human guided stack report, JSON/API, and future Admin UI.
`ProductTelemetryExporter` remains outbound-only, disabled by default,
and never required. Token counts stay local. No cloud backend (K-113).

## Residual report notes (not deployment defects)

- `GET runtimes foundation` may print selected `-` when live AUTO
  remaining SAFE shrinks; stored `FoundationSelection` still drove
  verify/report.
- First `instances start` may return before readiness; restart waits.
  Start-wait semantics were not changed in the observability freeze.
- `required_component_missing` on a selected verified foundation is
  suppressed in the default human report; it remains in structured JSON.

Do not begin llama.cpp, MLX, or Stage 1.6M from this freeze.
