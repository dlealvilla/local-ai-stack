# Stage 1.5C — Runtime / Executor boundary reconciliation

**Milestone 1 — Walking skeleton.**

Status: **OPEN** until checkpoint close.

This stage answers whether the already-proven InferenceInstance lifecycle
consumes a clean Runtime / Executor seam. It does not load a real model.

```text
CURRENT STAGE                Runtime / Executor contract reconciliation.
                             No vLLM, no provisioning, no verification,
                             no model-selection remap.
PREDECESSOR OUTPUTS          Stage 1.5B CLOSED L1
                             (`620a78be94433a0e8a6624d36147b0e870fafd61`).
THIS STAGE'S REQUIRED OUTPUT ExecutorCapabilityProfile;
                             RuntimeSupportDescriptor (reference TEST_ONLY);
                             executor-neutral RuntimeLaunchSpec (KEEP/ADJUST);
                             executor-neutral ExecutorHandle (KEEP/ADJUST);
                             RecordingExecutor fixture;
                             readiness owned by runtime;
                             1.5B lifecycle + resource + model regressions.
CORE CONTRACTS AFFECTED      execution.capability_profile (new);
                             runtime.support_descriptor (new);
                             runtime.readiness (new);
                             runtime.launch_spec / execution.spec /
                             execution.handle additive generic fields.
ADAPTERS AFFECTED            NativeProcessExecutor.capabilities;
                             reference-serving / reference-process descriptors
                             + readiness; adapters/execution/recording (fixture).
PERSISTED STATE              InferenceInstance + ExecutorHandle as in 1.5B.
                             Additive handle fields decode with defaults.
                             Reconciliation still uses ExecutionId + ownership.
MUTATION / FAILURE BOUNDARY  No new mutating workflows. Existing start/stop
                             fail closed as in 1.5B.
CANCELLATION / CLEANUP       Unchanged: executor stop, explicit reservation
                             release after STOPPED.
ACCEPTANCE LEVEL             L1. T3 not required (1.3 + 1.5B already proved
                             physical process composition).
ADMIN SURFACE                Existing instance / runtime / resource / model
                             surfaces. No Runtime Setup. No new CLI family.
DEBT ENTRIES                 ContainerExecutor (K-33, 1.6A);
                             verified RuntimeCapabilityProfile;
                             runtime-first selection remap; vLLM.
DEFERRED ITEMS               1.6A minimal ContainerExecutor and the rest of
                             the runtime-first chain.
```
