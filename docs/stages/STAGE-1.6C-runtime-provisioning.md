# Stage 1.6C — Runtime Provisioning

**Milestone 1 — Walking skeleton.**

Status: **CLOSED — L2.** Checkpoint:
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

**Current T3 vs commercial Python.** This stage's reference proof
requires Python 3.12 already on the host. Kultrun locates it and never
installs it. The commercial target is the opposite for Class A
prerequisites: the customer must not be expected to preinstall a
specific Python; Kultrun will provision a managed isolated interpreter
(K-66) after the first runtime path is physically proven. Those two
statements are not in conflict. A working NVIDIA driver is likewise a
current host prerequisite; privileged driver remediation is K-77.

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
non-edges. 753 tests passed after the promoted-path fix; ruff and mypy
clean.

T2 (final accepted artifact): clean wheel
`kultrun-0.1.0-py3-none-any.whl`
SHA256 `c7fe5ce723f87519c634f00bf4cd6c048b454253afb17bd21fcc474241a9c621`
from source `ed8f5099fa478f71a01424afc5e6b7cd3ad2109e` (build
`0.1.0+ed8f5099fa47`). Isolated install, no source checkout. Fixture
provisioner: plan `rplan_dfbeb2011f6e208c` → installation
`rinst_1a0940f0b60e72b4` `INSTALLED` `vllm==0.28.0`, idempotent, no
verify route. Fixture install is not real vLLM. An earlier T2 wheel
from `42117a74a3a213ec079fad83095b4030fb862ba1` was invalidated when
T3 exposed a dangling staging `python_executable` after atomic
promotion.

T3: PASS on a disposable Linux x86_64 NVIDIA host (Ubuntu 24.04.3,
kernel 6.8.0-124-generic, Intel Xeon Gold 6342, NVIDIA RTX A6000
48 GiB, driver 580.159.04, Python 3.12.3 at `/usr/bin/python3.12`,
NativeProcessExecutor available, PyPI reachable). Host
`host_09da05bd74830e63` fingerprint `d9e665f5d166dbb5449e332f84cee9b9`.
vLLM/native-process candidate `rcand_5e16a64313b76682` was
`conditional` solely for `required_component_missing`. AUTO had no
preferred COMPATIBLE candidate; provisioning consumed the explicitly
selected candidate. Plan `rplan_3b5942e3244e7b95` `vllm==0.28.0`
native-process python-venv-pip. `VllmNativeProvisioner` installed
into Kultrun state
`runtimes/vllm/0.28.0/rinst_22e540a9eeca0e8d`.
`importlib.metadata.version("vllm") == "0.28.0"`. Installer report
SHA256 `9cb70b848ea1771e7be6ac783c5356de8a7663668a4f00d0631c31d0b2093764`.
Staging emptied after atomic promotion. Receipt
`python_executable` names the promoted venv, not staging. Second
provision reused `rinst_22e540a9eeca0e8d` with `attempt_count` 1.
Global Python had no vllm before or after. No `import vllm`, no
engine, no CUDA proof through vLLM, no model.
`INSTALLED` ≠ `VERIFIED`.

Current reference proof: Python 3.12 and a working NVIDIA driver were
already on the host. Commercial target: Kultrun will provision a
managed isolated interpreter (K-66) and may later offer privileged
driver remediation with approval and rediscovery (K-77). Neither is
implemented here.

## Deferred enhancements

Recorded in `docs/DEBT.md`. None block Stage 1.6C:

* K-66 Managed Python / Interpreter Provisioning (required
  pre-commercial; not implemented here)
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
* K-77 Privileged Accelerator Driver Remediation (required
  pre-commercial behavior; not implemented here)
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
