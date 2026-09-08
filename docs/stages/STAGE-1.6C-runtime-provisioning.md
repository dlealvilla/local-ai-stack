# Stage 1.6C — Runtime Provisioning

**Milestone 1 — Walking skeleton.**

Status: **OPEN / READY_FOR_T3 — L1.** Checkpoint:
`checkpoints/STAGE-1.6C-runtime-provisioning.json`.

This stage answers whether Kultrun can create an exact reproducible
installation plan from a current `RuntimeCandidate` and safely install
that runtime into a Kultrun-owned isolated environment. It does not
verify that the runtime engine works.

`INSTALLED` is never `VERIFIED`.

```text
CURRENT STAGE                Runtime provisioning. Candidate → exact plan
                             → isolated install receipt.
PREDECESSOR OUTPUTS          Stage 1.6B CLOSED L1
                             (`cfbfc2f5d488e73cb94642c643f095355964f083`).
THIS STAGE'S REQUIRED OUTPUT RuntimeProvisioningPlan;
                             RuntimeProvisioner;
                             RuntimeInstallation;
                             exact vLLM 0.28.0 pin;
                             isolated venv + pip;
                             persistence; idempotency; explicit retry;
                             fixture T2; real T3 install for L2 close.
CORE CONTRACTS AFFECTED      runtime.provisioning_component@1 (new);
                             runtime.provisioning_plan@1 (new);
                             runtime.installation@1 (new);
                             support_descriptor preferred_version = 0.28.0.
ADAPTERS AFFECTED            adapters/provisioning/fixture (T0/T1/T2);
                             adapters/provisioning/vllm_native (product);
                             adapters/runtime/vllm (pin only; still no
                             import or launch).
PERSISTED STATE              RuntimeProvisioningPlan and
                             RuntimeInstallation. Candidates remain
                             derived. Interrupted INSTALLING → FAILED.
MUTATION / FAILURE BOUNDARY  POST plan / POST provision only.
                             GET candidates/plans/installations are
                             read-only. No system Python, driver, CUDA,
                             or package-manager mutation.
CANCELLATION / CLEANUP       Failed attempts clean staging under
                             <state_root>/runtimes/.staging/. Partial
                             installs are never promoted.
ACCEPTANCE LEVEL             L2 required to close. T2 is L1 control-plane
                             evidence. Fixture install is not real vLLM.
ADMIN SURFACE                POST /v1/runtimes/provisioning-plans;
                             POST /v1/runtimes/provision;
                             GET plans; GET installations;
                             kultrun runtimes {plan,provision,installations};
                             Console Create plan / Provision. No Verify.
DEBT ENTRIES                 K-66…K-79. K-56…K-65 preserved.
                             K-80…K-87 selection/replanning debt;
                             not blocking.
DEFERRED ITEMS               Stage 1.6D Runtime Verification and later
                             1.6 letters. Do not begin them from this stage.
```

## Flow

```text
RuntimeCandidate
        ↓
RuntimeProvisioningPlan
        ↓
RuntimeProvisioner
        ↓
RuntimeInstallation
        ↓
[STOP]
```

Future, **not implemented here**:

```text
RuntimeInstallation
        ↓
Stage 1.6D RuntimeVerifier
        ↓
RuntimeCapabilityProfile
```

| Object | Meaning |
|---|---|
| `RuntimeCandidate` | this path appears technically plausible |
| `RuntimeProvisioningPlan` | this is exactly what Kultrun intends to install |
| `RuntimeInstallation` | these components were installed |
| Stage 1.6D profile | we actually proved the runtime works |

## Product pin

| | |
|---|---|
| Runtime | vLLM |
| Executor | native-process |
| Version | `0.28.0` (exact; never latest / `>=0.28` / nightly) |
| Python | 3.12, located on the host, never installed by Kultrun |
| Isolation | stdlib `venv` + `python -m pip` |
| Source | PyPI |
| Proof | `importlib.metadata.version("vllm") == "0.28.0"` |

`import vllm`, `vllm serve`, engine init, CUDA, and model load are
Stage 1.6D.

## Provisionability

A plan is allowed for `COMPATIBLE` native-process vLLM, or `CONDITIONAL`
native-process vLLM whose only leftover reason is
`required_component_missing` for the `vllm` package itself.

Not provisionable: `UNSUPPORTED`, `UNRESOLVED`, container-docker,
missing Python 3.12, unavailable executor, stale host fingerprint,
unknown load-bearing executor capability, driver/CUDA/OS/arch mismatch.

Plans are immutable. Material host/executor change requires re-resolution
and a new plan, not mutation of the old one.

## Layout

```text
<state_root>/runtimes/.staging/<installation-id>-<attempt>/
<state_root>/runtimes/vllm/0.28.0/<installation-id>/
    venv/
    manifest/installer-report.json
    installation-metadata.json
```

Install into staging. Promote atomically only after installer success
and metadata version match. Failed staging is deleted. The control-plane
record remains `FAILED`.

## Lifecycle

`INSTALLING` → `INSTALLED` | `FAILED`.

No `VERIFIED`, `READY`, or `RUNNING` on `RuntimeInstallation`.
A later verification failure does not un-install the package.

Idempotent: same successful plan returns the existing `INSTALLED`
record. `INSTALLING` conflicts. `FAILED` retries only with an explicit
flag; `attempt_count` increments. No background retry.

## Evidence

T0/T1: `tests/test_runtime_provisioning.py` cases A–M plus architecture
non-edges. 753 tests passed; ruff and mypy clean.

T2: clean wheel `kultrun-0.1.0-py3-none-any.whl`
SHA256 `49b385611ed61836851aae10d9881abc6e7a7ea3d64536e84a3229ae1502e875`
from source `42117a74a3a213ec079fad83095b4030fb862ba1`. Isolated install,
no source checkout. Fixture provisioner: Host → candidates → plan
`rplan_98989570ba1d5fb6` → installation `rinst_a6a737019abeb197`
`INSTALLED` `vllm==0.28.0`, idempotent second provision, API/CLI/Console,
no verify route. Fixture install is not real vLLM.

T3: required for L2 close. Not run. This workspace is Darwin arm64 with
Python 3.13 and no Linux x86_64 NVIDIA host. Required host: Linux
x86_64, NVIDIA GPU, Python 3.12, NativeProcessExecutor, network to
PyPI, sufficient disk. No `import vllm`. Stage remains OPEN /
READY_FOR_T3 at L1.

## Deferred enhancements

Recorded in `docs/DEBT.md`. None block Stage 1.6C:

* K-66 managed Python runtime acquisition
* K-67 alternative installer backend (`uv`)
* K-68 offline / air-gapped runtime bundles
* K-69 fully locked runtime dependency manifests
* K-70 runtime package cache / mirror
* K-71 runtime upgrade (see also K-57)
* K-72 runtime rollback
* K-73 runtime uninstall / garbage collection
* K-74 side-by-side version management
* K-75 containerized runtime provisioning
* K-76 CUDA/toolkit dependency management
* K-77 driver management (outside the runtime provisioner)
* K-78 concurrent/background provisioning jobs
* K-79 signed runtime artifacts

K-56…K-65 remain. Version optimization, fallback, and marketplace are
those entries, not new duplicates. Bounded-selection intelligence is
K-80…K-87 and does not block this stage.

## Selection preservation

RuntimeProvisioner provisions the **explicitly selected**
`RuntimeCandidate`. It does not independently choose the platform
recommendation or substitute another candidate.

`RuntimeInstallation` preserves candidate id, plan id, runtime, version,
executor, host fingerprint, and installer provenance so later
verification and selection can attach to this exact path.

This stage preserves the bounded-selection and downstream
dependency-recalculation seam. It does not implement recommendation,
alternatives UI, AUTO/MANUAL selection, or a generic selection
framework.

## Non-goals

RuntimeVerifier, RuntimeCapabilityProfile, `import vllm` as operational
proof, `vllm serve`, model loading, prompt inference, containerized
vLLM, CUDA toolkit install, NVIDIA driver install, system package
manager, dependency solver, runtime marketplace, automatic upgrade,
rollback framework, garbage collection, multiple runtime families.
