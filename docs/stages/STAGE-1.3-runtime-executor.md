# Stage 1.3 — Runtime / executor exoskeleton

**Milestone 1 — Walking skeleton.**

Status: **CLOSED.** `L2` on a fresh Linux x86_64 CPU-only host, 2026-09-06.

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

Stage 1.6L replaced those pipe-pump threads with file-backed prefix
capture so a launching CLI can exit while a serving child continues
writing. Bounded handle capture is unchanged; inode growth of a
long-lived child is K-99.

## Acceptance

| Layer | Result |
|---|---|
| T0 focused | 32 tests in `tests/test_runtime_execution.py` |
| T1 regressions | architecture + full suite 493, ruff clean, mypy strict 98 files |
| T2 | Clean installed wheel locally; superseded for the gate by T3 |
| T3 | **Passed.** `L2` on a fresh Linux x86_64 CPU-only host. Previous RunPod identities were not reused. |

Accepted artifact: `kultrun-0.1.0-py3-none-any.whl`  
SHA-256: `d8f2d5b559280162e3d758b7601de8e18e4e71ca1e2a16963e419cf33f60d8a8`  
Build: `0.1.0+01a43238c790` from `01a43238c79086ef8b809c52985b134e3c04d9ae`  
Install: `/opt/kultrun`, `KULTRUN_STATE_ROOT=/var/lib/kultrun`, no source checkout.

T3 host: Docker container `698a886ede90`, Ubuntu 20.04.6, AMD EPYC 9655P
96/192, fingerprint `2c154fdc76affcc87a8a15880a361a95`. No GPU. SSH
`root@213.173.105.101:38631`.

Attempt 1 used the T2 wheel. Linux showed empty stdout on a still-running
hold workload because buffered `read(4096)` waited for a full chunk or
EOF. Fixed in `01a43238c790`; attempt 2 proved live stdout, PID, states,
stderr, non-zero exit, graceful stop, forced SIGKILL, no orphans, and
the Prototype Console on this host (`/prototype` 200, mode LIVE HOST,
process evidence `live_local_process`).

Checkpoint: `checkpoints/STAGE-1.3-runtime-executor.json`.

## Debt

K-31, K-32, K-33, K-34.

Adjacent, not blocking: Prototype Console renders unresolved `pid` /
`exit_code` as `[object Object]` (`$unresolved` vs `kind`). Live running
PIDs render correctly.

## Not begun

Stage 1.4A. No `ModelSource`, model download, model selection, inventory,
or inference runtime (vLLM / llama.cpp / Ollama / MLX / TensorRT-LLM).
No Docker executor.
