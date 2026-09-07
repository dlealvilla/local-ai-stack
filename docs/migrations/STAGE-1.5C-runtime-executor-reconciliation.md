# Stage 1.5C — Runtime / Executor boundary reconciliation

**Baseline:** `kultrun` @ `620a78be94433a0e8a6624d36147b0e870fafd61`
(Stage 1.5B CLOSED L1).

This is a current → target map, not a rebuild plan. Classifications:

| Class | Meaning |
|---|---|
| KEEP | Contract already correct |
| ADJUST | Small interface or ownership correction |
| MOVE | Logic belongs in another module |
| SPLIT | One module currently owns two responsibilities |
| DEFER | Not required before real inference |

No RuntimeResolver, provisioning, verification, `RuntimeCapabilityProfile`,
model-selection remap, acquisition gating change, vLLM, or ContainerExecutor
is in this stage.

---

## Runtime abstraction (`kultrun.runtime`, `InferenceRuntime`)

| | |
|---|---|
| **CURRENT OBJECT** | `InferenceRuntime` + `RuntimeProfile` + `RuntimeLaunchSpec` |
| **CURRENT INPUT** | `RuntimeLaunchRequest` (instance, mode, bind, artifact id) |
| **CURRENT OUTPUT** | `RuntimeLaunchSpec` (executable, argv, env, cwd, limits, grace, device indexes) |
| **CURRENT RESPONSIBILITY** | Translate a request into a structured recipe. Must not exec. |
| **TARGET RESPONSIBILITY** | Same, plus a static `RuntimeSupportDescriptor` and runtime-owned readiness. Still does not exec, signal, or talk to Docker. |
| **CLASSIFICATION** | **ADJUST** (descriptor + readiness methods). Profile KEEP. |
| **CALLERS AFFECTED** | `RuntimeCatalogue`, `InstanceService`, both reference adapters |
| **PERSISTENCE IMPACT** | None. Descriptors are declared, not stored. |
| **API/CLI/UI IMPACT** | Existing `GET /v1/runtime` may list descriptors. No new routes required. |
| **TESTS REQUIRED** | Runtime contract suite against `reference-serving` |

`RuntimeProfile` stays the launch-identity card. It is not a verified
operational profile and must not be renamed into `RuntimeCapabilityProfile`.

---

## Executor abstraction (`kultrun.execution`, `Executor`)

| | |
|---|---|
| **CURRENT OBJECT** | `Executor` port: `start` / `observe` / `stop` on `ExecutorSpec` |
| **CURRENT INPUT** | `ExecutorSpec` copied from `RuntimeLaunchSpec` by composition |
| **CURRENT OUTPUT** | `ExecutorHandle` |
| **CURRENT RESPONSIBILITY** | Realize a recipe on the host. No model or runtime semantics. |
| **TARGET RESPONSIBILITY** | Same, plus truthful `ExecutorCapabilityProfile` from current host evidence. |
| **CLASSIFICATION** | **ADJUST** (capability reporting). Start/observe/stop KEEP. |
| **CALLERS AFFECTED** | `ExecutionService`, `NativeProcessExecutor`, contract tests |
| **PERSISTENCE IMPACT** | None for the profile (computed). Handles remain persisted. |
| **API/CLI/UI IMPACT** | Optional field on existing runtime GET. No `kultrun executors` CLI. |
| **TESTS REQUIRED** | Executor contract suite on native + recording fixture |

---

## `RuntimeLaunchSpec`

| | |
|---|---|
| **CURRENT OBJECT** | `runtime.launch_spec@1` |
| **CURRENT INPUT** | Produced by a runtime adapter |
| **CURRENT OUTPUT** | Copied field-for-field into `ExecutorSpec` |
| **CURRENT RESPONSIBILITY** | Executor-neutral recipe: executable, structured argv, env, cwd, output bound, grace, device indexes. Rejects shells. |
| **TARGET RESPONSIBILITY** | Same, plus optional generic filesystem and network requirements so a second executor can consume the spec without Docker or Popen fields. |
| **CLASSIFICATION** | **KEEP** core. **ADJUST** additive generic requirement fields. No V2. |
| **CALLERS AFFECTED** | `platform.launch.executor_spec_from`, `InstanceService._spec_from` |
| **PERSISTENCE IMPACT** | Specs are not persisted. Additive defaults decode-safe. |
| **API/CLI/UI IMPACT** | None |
| **TESTS REQUIRED** | Neutrality: no `docker_*`, `popen_kwargs`, runtime-vendor fields; argv still structured |

---

## `ExecutorSpec`

| | |
|---|---|
| **CURRENT OBJECT** | `execution.spec@1` — the executor's copy of the recipe |
| **CLASSIFICATION** | **KEEP** + matching **ADJUST** so composition stays field-for-field |
| **NOTES** | Remains the executor input. Runtime still does not import `execution`. |

---

## Execution handle (`ExecutorHandle`)

| | |
|---|---|
| **CURRENT OBJECT** | Already named `ExecutorHandle`. Generic `ExecutionId`. `pid` is `Maybe[int]`. Ownership / observed state / bounded stdout/stderr / exit / timestamps already exist. |
| **CURRENT RESPONSIBILITY** | Last observation of one execution |
| **TARGET RESPONSIBILITY** | Same. PID remains native evidence, never the generic identity. Add optional non-PID `external_identity` so a future container/task id has a home. |
| **CLASSIFICATION** | **KEEP** name and identity model. **ADJUST** additive `external_identity` + optional `network_bindings`. |
| **CALLERS AFFECTED** | Native adapter (defaults). Recording fixture (sets external identity, no PID). |
| **PERSISTENCE IMPACT** | Additive fields with defaults; 1.5B records still decode. |
| **API/CLI/UI IMPACT** | Console/CLI may show Execution ID in addition to PID. |
| **TESTS REQUIRED** | Handle without PID is valid; RecordingExecutor returns one |

`running_owned()` currently requires a resolved PID. That is a native-only
assumption. **ADJUST:** owned + running is sufficient.

---

## `NativeProcessExecutor`

| | |
|---|---|
| **CURRENT RESPONSIBILITY** | `Popen` argv, capture, SIGTERM/SIGKILL, PID reuse → UNVERIFIED |
| **TARGET RESPONSIBILITY** | Same implementation. Report a truthful capability profile. Do not understand `/health` or model readiness. |
| **CLASSIFICATION** | **KEEP** implementation. **ADJUST** `capabilities(host)`. |
| **NOTES** | Isolation is unsupported. Accelerator exposure is host-process inheritance, not a fabricated CDI/Docker claim. |

---

## Recording / fixture executor

| | |
|---|---|
| **CURRENT OBJECT** | Absent |
| **TARGET RESPONSIBILITY** | Consume the same `ExecutorSpec`, return a generic handle, no `Popen`, no PID requirement. Proves the contract is not native-process-specific. |
| **CLASSIFICATION** | **ADJUST** (new test-only adapter). Not a production ContainerExecutor. |
| **DEFER** | Real `ContainerExecutor` / Docker — Stage 1.6A |

---

## Readiness

| | |
|---|---|
| **CURRENT OBJECT** | `InstanceService._ready_from_stdout` + `_health_ok` (`urllib` `/health`) |
| **CURRENT RESPONSIBILITY** | Inference knows the reference marker and HTTP probe |
| **TARGET RESPONSIBILITY** | Executor: alive / exited. Runtime: workload READY. Inference: compose both into observed state. |
| **CLASSIFICATION** | **MOVE** probe + marker parse into `reference-serving`. **ADJUST** `InferenceRuntime.inspect_readiness`. |
| **CALLERS AFFECTED** | `InstanceService._wait_ready` and reconcile health |
| **PERSISTENCE IMPACT** | None |
| **TESTS REQUIRED** | Reference lifecycle still reaches READY; executor contract does not mention `/health` |

---

## Shutdown

| | |
|---|---|
| **CURRENT OBJECT** | `RuntimeLaunchSpec.grace_period_seconds` → executor SIGTERM then SIGKILL |
| **CURRENT RESPONSIBILITY** | Inference calls `ExecutionService.stop`. Runtime does not kill. |
| **TARGET RESPONSIBILITY** | Unchanged. Runtime describes grace; executor signals. |
| **CLASSIFICATION** | **KEEP** |
| **TESTS REQUIRED** | Runtime adapters still must not import `subprocess` / `os.kill` |

---

## `InferenceInstance` + `InstanceService`

| | |
|---|---|
| **CURRENT INPUT** | Artifact + reservation + already-chosen runtime/executor identities |
| **CURRENT OUTPUT** | Lifecycle state, endpoint, `ExecutionId`, optional PID |
| **CURRENT RESPONSIBILITY** | Compose runtime + executor. Persist identities. Conservative restart reconciliation. |
| **TARGET RESPONSIBILITY** | Same. Ask the runtime for readiness. Do not require PID on the generic path. Do not persist provider objects. |
| **CLASSIFICATION** | **KEEP** lifecycle, persistence, reservation rules. **ADJUST** readiness call. |
| **RESOURCE** | **KEEP**. No ResourceManager change. |
| **API/CLI/UI IMPACT** | Show executor + Execution ID. No Runtime Setup. |
| **TESTS REQUIRED** | Full 1.5B lifecycle + alternate-executor composition |

Reconciliation already keys on `ExecutionId` + `ExecutionOwnership`, not
“PID exists ⇒ RUNNING”. Native UNVERIFIED stays UNKNOWN. A non-PID
executor can use the same ownership enum.

---

## `RuntimeCatalogue`

| | |
|---|---|
| **CURRENT RESPONSIBILITY** | `profiles()`, `launch()`, `product_identities()` excluding hardcoded harness names |
| **TARGET RESPONSIBILITY** | Also `descriptors()` / `inspect_readiness()`. Product identities exclude `TEST_ONLY` / non-production descriptors, not only two names. |
| **CLASSIFICATION** | **ADJUST** |

---

## ResourceManager / reservations

| | |
|---|---|
| **CLASSIFICATION** | **KEEP** |
| **NOTES** | No contract defect found. SAFE − ACTIVE, overcommit, release, per-device accounting, Small→Large→Small remain untouched. |

---

## Model selection / acquisition

| | |
|---|---|
| **CLASSIFICATION** | **DEFER** |
| **NOTES** | 19-model catalog, AUTO estimator, llmfit primary, STORE acquisition, reserve-by-artifact stay as 1.4B/1.4C/1.5A. Runtime-first remap is later. |

---

## Composition copy (`platform.launch` and inference `_spec_from`)

| | |
|---|---|
| **CLASSIFICATION** | **KEEP** the copy step. **ADJUST** new generic fields. |
| **NOTES** | Runtime ⟂ execution remains a non-edge. |

---

## Summary

| Area | Class |
|---|---|
| `RuntimeLaunchSpec` (core) | KEEP |
| `ExecutorHandle` name + `ExecutionId` | KEEP |
| Native process implementation | KEEP |
| InferenceInstance lifecycle | KEEP |
| ResourceManager | KEEP |
| Shutdown ownership | KEEP |
| Structured argv / no `shell=True` | KEEP |
| Executor capability profile | ADJUST (new contract + native report) |
| Runtime support descriptor | ADJUST (new contract + reference TEST_ONLY) |
| Launch spec generic mappings | ADJUST |
| Handle `external_identity` | ADJUST |
| `running_owned` PID assumption | ADJUST |
| Catalogue product / readiness | ADJUST |
| Reference readiness HTTP/marker | MOVE (inference → serving adapter) |
| RecordingExecutor | ADJUST (fixture only) |
| ContainerExecutor | DEFER (1.6A) |
| RuntimeResolver / provisioning / verification | DEFER |
| `RuntimeCapabilityProfile` | DEFER |
| Model eligibility / DeploymentPlan-gated acquire | DEFER |
| vLLM / real inference | DEFER |
