# Stage 1.6L3 — P0 specialist probes

**Milestone 1 — Walking skeleton (storage correction, not 1.6L close).**

Status: **frozen on `stage/1.6L2-storage-authorizing-persist` at
`da9b75e703ac15edf745c29fcdefb98178637ceb`.**
Does not close Stage 1.6L. Does not start 1.6M. Does not add runtimes.

Predecessor: 1.6L2 authorizing persist
`4153838a7faa2baf6554ed52d0f21b35993747fc`.

Sequence:
`docs/investigations/STORAGE-RUNTIME-BREADTH-SEQUENCE.md` (S2).

```text
CURRENT STAGE                Native always; compatible specialists
                             always; specialist remaining bytes win;
                             500 GiB anomaly trigger; real P0 parsers.
PREDECESSOR OUTPUTS           1.6L2 authorizing persist 4153838.
THIS STAGE'S REQUIRED OUTPUT Specialist-bytes authority; typed misses
                             when optional tools are absent.
CORE CONTRACTS AFFECTED      none new; policy_version 1.6L3.0.
ADAPTERS AFFECTED            linux-quota, moosefs, zfs, ceph,
                             windows (native-class), nfs seam.
PERSISTED STATE              unchanged keys from 1.6L2.
MUTATION / FAILURE BOUNDARY  Missing binaries never SUCCESS-with-bytes.
CANCELLATION / CLEANUP       Unchanged. Sonar algorithm unchanged.
ACCEPTANCE LEVEL             L1 fixtures. Not L2. Not T3.
MUST NOT                     Sonar tree 64–256; 20% replan; llama.cpp;
                             MLX; weaken SAFE; merge to kultrun.
DEBT                         K-105/K-102/K-106 physical remain OPEN.
                             K-111 remainder is S3–S4.
```
