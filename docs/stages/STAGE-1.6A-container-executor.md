# Stage 1.6A — Minimal ContainerExecutor + Executor Portability

**Milestone 1 — Walking skeleton.**

Status: **OPEN / READY_FOR_T3.** `L1`. Checkpoint:
`checkpoints/STAGE-1.6A-container-executor.json`.

T0/T1/T2 passed on committed source `d244200`. Real Docker Engine T3 is
required to close at L2 and has not run: the development host is Darwin
and Docker Desktop is not an architectural dependency.

This stage proves that Runtime owns WHAT and Executor owns HOW across two
real execution mechanisms. It does not load a real model and it does not
implement vLLM.

```text
CURRENT STAGE                Minimal ContainerExecutor + portability proof.
                             No vLLM, no RuntimeResolver, no provisioning.
PREDECESSOR OUTPUTS          Stage 1.5C CLOSED L1
                             (`8e78dea7a56dcd9cd23faef0a4a45fb08a1141a3`).
THIS STAGE'S REQUIRED OUTPUT ContainerExecutor; Docker CLI ContainerEngine;
                             truthful container capability profile;
                             executor-owned ContainerExecutionConfig;
                             same reference-serving Runtime through
                             NativeProcessExecutor and ContainerExecutor.
CORE CONTRACTS AFFECTED      execution.container_config (new);
                             execution.engine_probe (new);
                             generic seams unchanged (no docker_* fields).
ADAPTERS AFFECTED            adapters/execution/container;
                             adapters/container/docker;
                             adapters/container/recording (fake engine);
                             native/reference logical `python` resolution.
PERSISTED STATE              ExecutorHandle as in 1.5C. Container identity
                             is external_identity. PID optional.
MUTATION / FAILURE BOUNDARY  Normalized engine/image/lifecycle failures.
                             No raw Docker exceptions in core domains.
CANCELLATION / CLEANUP       Stop then optional remove, constrained to
                             Kultrun-managed identity. No unrelated
                             container deletion.
ACCEPTANCE LEVEL             L2 after real Docker Engine T3. T0/T1/T2
                             alone leave the stage OPEN / READY_FOR_T3.
ADMIN SURFACE                Diagnostic executor identity and capability.
                             No docker CLI family. No container UI.
DEBT ENTRIES                 GPU container exposure; richer networking;
                             multiple engines; image management; Kubernetes.
DEFERRED ITEMS               Stage 1.6B Runtime Resolution and later 1.6
                             letters.
```

## Architecture

```text
RuntimeAdapter
      ↓
RuntimeLaunchSpec          (executor-neutral; no Docker fields)
      ↓
Executor
     ↙                      ↘
NativeProcessExecutor    ContainerExecutor
      ↓                      ↓
                     ContainerEngine
                             ↓
                      Docker CLI adapter
      ↓                      ↓
ExecutorHandle            ExecutorHandle
      ↘                      ↙
       runtime-owned readiness
               ↓
             READY
```

Docker Engine is the first `ContainerEngine` implementation. Docker is
not in generic contracts. Image, pull policy, network mode and naming
belong to `ContainerExecutionConfig`, owned by Executor/composition.

## Network v0

Reference serving still binds loopback and reports its endpoint. The
container executor realizes that with **Linux host networking** so the
Runtime adapter does not grow Docker or bind-address branches.

Limitations (debt): host networking is a Linux-only v0 choice;
bridge/publish mapping, extra networks, and GPU device attachment are
deferred.

## T2

Wheel `kultrun-0.1.0-py3-none-any.whl` SHA256
`8cd70b4c244b4c8cdb52217c10b947e2f6c92149ce048ea87f8b4eecfa2b0c11`
from `d2442003888bc6ed12e5287d74a9c70e203c75db`. Native reference
serving, fake-engine ContainerExecutor, Small→Large→Small, API/CLI/Console
all passed in a clean install.

## T3

Not run. Needs Linux Docker Engine, this exact wheel, and the reference
image fixture. Do not close from fake-engine tests.

## Executable resolution

Runtime names the `python` component. Each executor resolves that name
inside its environment: native uses the interpreter running Kultrun;
container uses the image `PATH`. Runtime does not branch on executor.
