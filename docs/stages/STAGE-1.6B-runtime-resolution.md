# Stage 1.6B — Runtime Resolution

**Milestone 1 — Walking skeleton.**

Status: **OPEN.** Target gate: `L1` (T0/T1/T2). Checkpoint:
`checkpoints/STAGE-1.6B-runtime-resolution.json`.

This stage answers which runtime/executor paths are **technically
plausible** on the current host. It does not install, verify, benchmark,
select models, or run vLLM.

```text
CURRENT STAGE                Runtime resolution. Declared support × host
                             × executor capability → RuntimeCandidate[].
PREDECESSOR OUTPUTS          Stage 1.6A CLOSED L2
                             (`f3d4baf3d255ca944ffd626aaf1f3505f3b20b27`).
THIS STAGE'S REQUIRED OUTPUT RuntimePolicy; RuntimeCandidate;
                             RuntimeResolution; RuntimeResolver;
                             conservative vLLM declared-support descriptor;
                             read-only API/CLI/Console candidates surface.
CORE CONTRACTS AFFECTED      runtime.policy (new);
                             runtime.candidate (new);
                             runtime.resolution (new);
                             runtime.support_descriptor additive
                             preferred_version only.
ADAPTERS AFFECTED            adapters/runtime/vllm (declared support only;
                             does not import or execute vLLM).
PERSISTED STATE              None. Candidates are derived on each read.
MUTATION / FAILURE BOUNDARY  Read-only. No provision, install, verify,
                             or start-runtime routes.
CANCELLATION / CLEANUP       None. No runtime files or processes created.
ACCEPTANCE LEVEL             L1. T3 not required: deterministic
                             control-plane resolution over already-proven
                             Host and Executor evidence.
ADMIN SURFACE                GET /v1/runtimes/candidates;
                             kultrun runtimes candidates;
                             read-only Console panel. No Install/Verify.
DEBT ENTRIES                 K-56…K-65 (ranking, versions, fallback,
                             multi-host, marketplace, …).
DEFERRED ITEMS               Stage 1.6C Runtime Provisioning and later
                             1.6 letters. Do not begin them from this stage.
```

## Flow

```text
HostCapabilities
        +
ExecutorCapabilityProfile[]
        +
RuntimeSupportDescriptor[]
        +
RuntimePolicy
        ↓
RuntimeResolver
        ↓
RuntimeCandidate[]
```

A RuntimeCandidate is a runtime family/provider + executor path that
appears supportable enough to plan provisioning. It is not installed,
verified, healthy, benchmarked, or model-feasible.

## Compatibility

| Class | Meaning |
|---|---|
| `COMPATIBLE` | Declared support and current host/executor facts line up; no known missing prerequisite. |
| `CONDITIONAL` | Plausible, with non-fatal caveats (component not installed, GPU-in-container unverified, v0 limits). |
| `UNSUPPORTED` | Known hard mismatch (OS, arch, accelerator, executor unavailable). |
| `UNRESOLVED` | A load-bearing fact is unknown. Unknown is never Compatible. |

## AUTO and EXPLICIT

AUTO inspects current host, executor profiles, and registered descriptors,
classifies every relevant Runtime+Executor pair, omits reference/test/future
families unless policy opts in, and ranks remaining paths deterministically.

EXPLICIT evaluates only the requested runtime. It never falls back to
another family.

Preferred candidate is the first `COMPATIBLE` path (or a CONDITIONAL path
only when policy explicitly allows preferring those). It is not “best
runtime”: nothing has been installed or verified.

## Ranking (not an optimizer)

1. compatibility class
2. support tier
3. executor availability
4. RuntimePolicy preferred executor/runtime order
5. stable runtime then executor name

No tokens/sec, latency, VRAM efficiency, quality, cost, or benchmark
scores. After a later provisioning failure the system must re-resolve;
this stage does not try candidate 2 automatically. See K-56, K-59.

## vLLM descriptor

Declared support only. Linux, x86_64, NVIDIA/CUDA-oriented product path,
executors `native-process` and `container-docker`. Support tier `PRODUCT`.
Version is unset until provisioning/verification pins one. The adapter
must not import, install, or run vLLM.

## Identity

Candidate IDs are `rcand_<16 hex>` derived from schema, runtime, version
token, executor, host id, and host fingerprint. Recompute on every read;
do not persist compatibility as truth.

## Negative cases

| Case | Expected |
|---|---|
| Linux NVIDIA + native available + vLLM declared support + component present | `COMPATIBLE` native candidate; may be preferred |
| macOS Apple Silicon + NVIDIA-only vLLM descriptor | `UNSUPPORTED` (`host_os_unsupported`); no preferred candidate |
| Container-only descriptor + container executor unavailable | `UNSUPPORTED` (`executor_unavailable`) |
| GPU required + container `accelerator_exposure` unknown | `CONDITIONAL` or `UNRESOLVED`, never `COMPATIBLE` |
| EXPLICIT request for an incompatible runtime | that family's failure; no silent fallback |
| AUTO with `reference-serving` registered | excluded unless policy opts in |
| Policy `allow_test_only` / `allow_reference_runtimes` | reference/test candidates appear |
| Two `COMPATIBLE` paths | deterministic order (native-process before container-docker by default) |
| Same inputs twice | same candidate IDs and order |

## Deferred enhancements

Recorded in `docs/DEBT.md`. None of these block Stage 1.6B:

* K-56 runtime performance-aware ranking
* K-57 runtime version optimization
* K-58 native vs container performance/cost comparison
* K-59 runtime fallback policy
* K-60 multi-host runtime resolution
* K-61 rich accelerator/backend ranking
* K-62 learned runtime recommendations
* K-63 runtime marketplace/plugin discovery
* K-64 multi-container-engine resolution
* K-65 runtime benchmark evidence integration

## Non-goals

RuntimeProvisioningPlan, RuntimeProvisioner, RuntimeInstallation,
RuntimeVerifier, RuntimeCapabilityProfile, model eligibility remap,
selection/acquisition remap, vLLM install, real inference, Gateway.

## Evidence

T0/T1: `tests/test_runtime_resolution.py` plus architecture non-edges.
T2: clean wheel, recorded in the checkpoint. T3 is not required.

