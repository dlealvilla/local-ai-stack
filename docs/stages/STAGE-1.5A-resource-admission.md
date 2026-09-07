# Stage 1.5A — Resource admission + ResourceReservation

**Milestone 1 — Walking skeleton.**

Status: **WORKING.** `L1`. Control-plane admission and persistent
reservations. Reserved is not running.

This stage answers whether a planned stored workload may consume
resources now. It does not launch a process or create an
InferenceInstance.

## CURRENT STAGE

`ResourceRequest`, `AdmissionDecision`, `ResourceReservation`,
`ResourceManager`, SAFE-minus-ACTIVE arithmetic, atomic admit, release,
API/CLI/Console.

## PREDECESSOR OUTPUTS

| Consumed | From |
|---|---|
| `DeploymentPlan` v0 + selection | Stage 1.4B |
| STORED `ModelArtifact` + inventory | Stage 1.4C |
| SAFE `CapacityEnvelope` | Stage 1.2 |

## THIS STAGE'S REQUIRED OUTPUT

```text
STORED ModelArtifact + DeploymentPlan + current SAFE + ACTIVE reservations
  → ResourceRequest (server-derived)
  → ResourceManager.admit
  → AdmissionDecision + ResourceReservation ACTIVE
```

Planning still does not reserve. Resource still does not rank.

## Contracts

| Kind | Role |
|---|---|
| `resource.request@1` | One future workload; amounts from server evidence |
| `resource.admission_decision@1` | admitted / rejected / unresolved |
| `resource.reservation@1` | Additive provenance on the existing grant |
| `resource.summary@1` | SAFE / RESERVED / AVAILABLE, recomputed |
| `resource.device_summary@1` | Per-accelerator ledger |

Lifecycle written in v0: `ACTIVE`, `RELEASED`. No serving states.

## Arithmetic

`CURRENT RESERVABLE = CURRENT SAFE − SUM(ACTIVE)`

Per device. GPUs are never summed. Available for new work is never
negative. Unknown never authorizes. Stored artifact disk is not reserved
again.

## Not in this stage

InferenceInstance, runtime launch, model load, scheduler, leases,
quotas, physical enforcement, port allocator.
