# Stage 1.6D — Runtime Verification

**Milestone 1 — Walking skeleton.**

Status: **OPEN.** Checkpoint:
`checkpoints/STAGE-1.6D-runtime-verification.json`.

This stage answers whether an exact installed runtime operates correctly
on the current host and executor. It does not choose a runtime, rank
runtimes, select a model, or perform inference.

`INSTALLED` is never `VERIFIED`. `VERIFIED` is never model-compatible.

```text
CURRENT STAGE                Runtime verification. Exact installation
                             → host/executor probe → capability profile.
PREDECESSOR OUTPUTS          Stage 1.6C CLOSED L2
                             (`0f39753d9d2b2c9e2942ca852983efa2e6203ad3`).
THIS STAGE'S REQUIRED OUTPUT RuntimeVerifier;
                             RuntimeCapabilityProfile;
                             RuntimeVerificationBasis;
                             vLLM native verifier;
                             fixture verifier;
                             persistence; idempotency; staleness;
                             API/CLI/Console; T0/T1/T2; real T3 for L2.
CORE CONTRACTS AFFECTED      runtime.capability_profile@1 (new);
                             runtime.verification_basis@1 (new);
                             runtime.verification_check@1 (new);
                             runtime.verification_probe@1 (new).
ADAPTERS AFFECTED            adapters/verification/fixture (T0/T1/T2);
                             adapters/verification/vllm_native (product).
PERSISTED STATE              One current RuntimeCapabilityProfile per
                             RuntimeInstallation. Installations unchanged.
MUTATION / FAILURE BOUNDARY  POST verify only. GET may present STALE.
                             GET never executes a probe.
CANCELLATION / CLEANUP       Bounded probe; timeout becomes FAILED;
                             no daemon left behind. Failed verify does
                             not delete the installation.
ACCEPTANCE LEVEL             L2 required to close. T2 is L1 control-plane
                             evidence. Fixture verify is not real vLLM.
ADMIN SURFACE                POST /v1/runtimes/verify;
                             GET /v1/runtimes/capability-profiles;
                             GET /v1/runtimes/capability-profile;
                             kultrun runtimes verify|capabilities;
                             Console Verify. No ranking or model UI.
DEBT ENTRIES                 K-88…K-93. K-56…K-87 preserved.
                             K-66 and K-77 remain OPEN / not implemented.
DEFERRED ITEMS               Stage 1.6E Runtime Evaluation / Selection.
                             Do not begin it from this stage.
```

## Flow

```text
RuntimeInstallation
        +
current HostCapabilities
        +
current ExecutorCapabilityProfile
        ↓
RuntimeVerifier
        ↓
RuntimeCapabilityProfile
        ↓
[STOP 1.6D]
```

Future, **not implemented here**:

```text
RuntimeCapabilityProfile[]
        ↓
Stage 1.6E RuntimeEvaluator / RuntimeSelector
        ↓
recommended + selectable + blocked
        ↓
AUTO | bounded MANUAL
```

## Verification definition

A `VERIFIED` profile means the installed runtime passed its
host/runtime/backend checks against the current material verification
basis. It does not mean every model, architecture, quantization, context
length, or concurrency value works, and it does not mean the model fits.

No model identifiers belong on `RuntimeCapabilityProfile`.

## Profile lifecycle

| Status | Meaning |
|---|---|
| `UNVERIFIED` | Installation exists; no current profile. |
| `VERIFIED` | Required checks passed against the current material basis. |
| `FAILED` | A verification attempt ran and required checks failed. |
| `STALE` | A previously `VERIFIED` profile was created against a materially different basis. |

`RuntimeInstallation.status` stays `INSTALLED` through `FAILED` and
`STALE`. Verification never deletes the install, never marks the
installation failed, never remediates Python (K-66) or drivers (K-77),
and never kills a future running inference instance.

## Verification basis

Material facts only: installation identity and root, runtime family and
version, Python executable and version, executor identity and
availability, OS family, architecture, accelerator vendor/model/count,
and driver version.

Excluded: free RAM, free VRAM, disk free, CPU/GPU utilization,
reservations, port occupancy, and `HostCapabilities.fingerprint` (that
fingerprint is a host-sameness key, not a runtime-capability key, and it
does not include driver version).

A read may report `STALE`. Re-verification is always an explicit POST.
Startup reconciles stored `VERIFIED` against the current basis and does
not run a probe.

## Executor boundary

Runtime owns what to check and how to interpret evidence. Executor owns
how the probe process is executed. Orchestration does not call
`subprocess`. The product path copies a `RuntimeVerificationProbe` into
an `ExecutorSpec` and runs it through `NativeProcessExecutor`
(`shell=False`, structured argv, timeout, bounded stdout/stderr).

## vLLM native probe

`VllmNativeVerifier` targets the exact `vLLM 0.28.0` native-process
installation. It proves installation integrity, isolated Python
execution, package metadata `vllm==0.28.0`, `import vllm`, backend
import, CUDA availability, NVIDIA device visibility, and a tiny CUDA
tensor operation. It does not download a model, start `vllm serve`, or
generate tokens.

## Non-goals

RuntimeEvaluator, RuntimeSelector, AUTO/MANUAL runtime override, model
eligibility, model selection, model capacity, resource override,
production `DeploymentPlan` remap, benchmarks, Gateway, analytics,
managed Python (K-66), driver remediation (K-77).

## Testing

- **T0** — schema, states, basis fingerprint, staleness inclusions and
  exclusions, success/failure/retry/idempotency, no model fields.
- **T1** — fixture scenarios A–O, including restart and FAILED→retry.
- **T2** — clean wheel, fixture chain through `VERIFIED`, API/CLI/Console,
  persistence, restart, staleness, failure, retry, idempotency.
- **T3** — real NVIDIA host, rediscovered (not reused 1.6C host facts),
  exact installation (reuse 1.6C if present, else recreate through
  Kultrun), actual import/backend/GPU probe. Not real model inference.

## STOP

After this stage, stop. Do not begin Stage 1.6E. Present Daniel with
minimum / minimum + a little depth / rabbit hole before writing 1.6E
implementation instructions.
