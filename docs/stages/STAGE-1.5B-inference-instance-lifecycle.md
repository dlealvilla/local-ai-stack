# Stage 1.5B — InferenceInstance lifecycle

**Milestone 1 — Walking skeleton.**

Status: **CLOSED.** `L1`. Plural instance lifecycle over a reference
serving process. Stop does not release. Checkpoint:
`checkpoints/STAGE-1.5B-inference-instance-lifecycle.json`.

This stage answers whether a STORED `ModelArtifact` and an ACTIVE
`ResourceReservation` can become a create / start / observe / stop
serving process. It does not load a real model or generate tokens.

## CURRENT STAGE

`InferenceInstance`, `InstanceId`, desired vs observed state, reference
serving runtime, Executor composition, persistence, restart
reconciliation, reservation-in-use composition, dynamic active-capacity
mobility, API / CLI / Console.

## PREDECESSOR OUTPUTS

| Consumed | From |
|---|---|
| ACTIVE `ResourceReservation` | Stage 1.5A |
| STORED `ModelArtifact` | Stage 1.4C |
| Runtime / Executor | Stage 1.3 |

## THIS STAGE'S REQUIRED OUTPUT

```text
STORED ModelArtifact + ACTIVE ResourceReservation
  → InferenceInstance CREATED
  → RuntimeLaunchSpec + Executor start
  → RUNNING + readiness + loopback endpoint
  → STOP → STOPPED
  → reservation remains ACTIVE until explicit release
```

`ModelArtifact ≠ ResourceReservation ≠ InferenceInstance`.

Stored / reserved / running are lifecycle labels, not capacity
partitions. Disk, RAM, VRAM and unified memory stay separate.

## Contracts

| Kind | Role |
|---|---|
| `inference.instance@1` | Additive desired/observed, artifact, execution, endpoint, failure |
| `runtime.launch_request@1` | What inference asks a runtime to translate |

## Lifecycle

`CREATED → STARTING → RUNNING → STOPPING → STOPPED`

Failed startup: `STARTING → FAILED`. Unexpected exit: `RUNNING → FAILED`.
Control-plane restart: persisted RUNNING is not trusted; UNVERIFIED
process identity becomes `UNKNOWN`. Reservation stays ACTIVE.

## Not in this stage

Real LLM load, vLLM / llama.cpp / MLX, prompt or chat API, scheduler,
automatic model switching, production port allocator, process supervisor
deepening, execution cache, Gateway.
