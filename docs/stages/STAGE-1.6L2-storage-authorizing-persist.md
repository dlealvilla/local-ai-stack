# Stage 1.6L2 — Storage authorizing persist

**Milestone 1 — Walking skeleton (storage correction, not 1.6L close).**

Status: **implementation on `stage/1.6L2-storage-authorizing-persist`.**
Does not close Stage 1.6L. Does not start 1.6M. Does not add runtimes.

Predecessor: storage implementation
`caa9e03225cd9fa8b7d12707b144406a69902ae6`.

Sequence:
`docs/investigations/STORAGE-RUNTIME-BREADTH-SEQUENCE.md` (S0+S1).

```text
CURRENT STAGE                Cheap observation vs authorizing
                             characterization; EmpiricalProbeEvidence
                             persist; foundation fit uses SAFE.
PREDECESSOR OUTPUTS          1.6L storage-capacity-truth caa9e03.
THIS STAGE'S REQUIRED OUTPUT Split store keys; GET /host cannot erase
                             Sonar; requirement_fits vs SAFE.
CORE CONTRACTS AFFECTED      none new; same storage.capacity_evidence@1
                             and storage.empirical_evidence@1.
ADAPTERS AFFECTED            none.
PERSISTED STATE              sco_* observation, sce_* authorizing,
                             see_* empirical.
MUTATION / FAILURE BOUNDARY  Cheap characterize never writes authorizing
                             of a matching identity.
CANCELLATION / CLEANUP       Unchanged.
ACCEPTANCE LEVEL             L1. T0/T1. Not L2. Not T3.
MUST NOT                     Sonar algorithm change; llama.cpp; MLX;
                             weaken SAFE; merge to kultrun.
DEBT                         K-111 remainder of Track S (1.6L3–L5).
```
