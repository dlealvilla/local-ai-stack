# Stage 1.3 — Runtime / executor exoskeleton

**Milestone 1 — Walking skeleton.**

Status: **LOCAL ACCEPTANCE COMPLETE; L2 T3 PENDING.**

The stage establishes two domains and does not run an LLM.

- **Runtime** answers: what executable configuration should be launched?
- **Execution** answers: how is an already-defined workload started,
  observed, stopped, and cleaned up?

Composition (`kultrun.platform.launch` and `kultrun.main`) copies a
`RuntimeLaunchSpec` into an `ExecutorSpec`. The two packages do not import
each other. Runtime does not import Capacity; that is now an enforced
non-edge.

---

## CURRENT STAGE

`NativeProcessExecutor` plus a reference `InferenceRuntime` adapter that
launches a deterministic acceptance harness
(`kultrun.adapters.runtime.reference_workload`). Native process execution
is first-class. Docker, OCI and Kubernetes are not required.

## PREDECESSOR OUTPUTS

| Consumed | From |
|---|---|
| Host discovery + fixture replay | Stage 1.1 / 1.2A |
| Capacity envelope (unchanged) | Stage 1.2 |
| Prototype Console | Stage 1.2A |
| Store, startup, health, Platform API | Stage 0.3 |
| Model-lifecycle sequence (1.4A after 1.3) | `WORKFLOW-model-lifecycle-roadmap` |

## THIS STAGE'S REQUIRED OUTPUT

`ExecutorSpec` + `ExecutorHandle` + `DeviceRequest` + `RuntimeProfile` +
`RuntimeLaunchSpec` + `NativeProcessExecutor` + `InferenceRuntime` port +
unimplemented `ContainerEngine` seam.

## Platform API

| Method | Path | Effect |
|---|---|---|
| GET | `/v1/runtime` | Profiles, executor identity, `executions[]`, process vs host evidence |
| POST | `/v1/runtime/execution` | Start the reference workload only. Arbitrary argv refused |
| POST | `/v1/runtime/execution/stop` | Stop one owned execution, or every owned running execution |
| GET | `/v1/mode` | Adds `process_evidence_kind` and `host_evidence_kind` |

GET never starts a process.

## Reconciliation

Persisted `ExecutorHandle` records are observed at startup. A PID that
exists without a live `Popen` in this control plane is `UNVERIFIED` and
is never signalled (`docs/DEBT.md` K-31). Desired, observed and health
remain separate fields; health is `UNKNOWN` (K-32).

## Cancellation / cleanup

SIGTERM to the process group, then SIGKILL after the spec's grace period.
Stdout and stderr are each truncated at `output_limit_bytes`. Capture
threads are non-daemon and joined after exit.

## Acceptance

| Layer | Result |
|---|---|
| T0 focused | `tests/test_runtime_execution.py` |
| T1 regressions | Host, Capacity, Sonar, Console, architecture |
| T2 | Clean installed wheel, `kultrun runtime start --once`, console `/v1/runtime` |
| T3 | **Pending.** Gate is L2 on a generic Linux host. No GPU required. Previous RunPod must not be reused. |

## Debt

K-31, K-32, K-33, K-34.

## Not begun

Stage 1.4A. No `ModelSource`, model download, model selection, inventory,
or inference runtime (vLLM / llama.cpp / Ollama / MLX / TensorRT-LLM).
No Docker executor.
