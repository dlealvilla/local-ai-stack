# Stage 1.6L4 — Storage Sonar V2

**Milestone 1 — Walking skeleton (storage correction, not 1.6L close).**

Status: **implementation on `stage/1.6L4-storage-sonar-v2`.**
Does not close Stage 1.6L. Does not start 1.6M. Does not add runtimes.

Predecessor: 1.6L3 P0 specialist probes
`da9b75e703ac15edf745c29fcdefb98178637ceb`.

Sequence:
`docs/investigations/STORAGE-RUNTIME-BREADTH-SEQUENCE.md` (S3).

```text
CURRENT STAGE                HOST-mode Sonar V2: official tiers
                             16–256 GiB; owned 1 GiB reserve;
                             grow-to-size incompressible writes;
                             expensive path always runs Sonar.
PREDECESSOR OUTPUTS           1.6L3 specialist-bytes authority da9b75e.
THIS STAGE'S REQUIRED OUTPUT Conservative proven lower-bound tiers;
                             specialist confirmed or replaced by Sonar.
CORE CONTRACTS AFFECTED      optional EmpiricalProbeEvidence fields;
                             policy_version 1.6L4.0-sonar-v2.
ADAPTERS AFFECTED            empirical_write grow-to-size.
PERSISTED STATE              see_* progress; sce_* only after cleanup.
MUTATION / FAILURE BOUNDARY  EDQUOT/ENOSPC upper bound only;
                             other errors interrupt; reserve-first
                             recovery; identity must match to promote.
CANCELLATION / CLEANUP       Timeout keeps last completed checkpoint.
ACCEPTANCE LEVEL             L1 scaled FakeVolume. Not L2. Not T3.
MUST NOT                     G-REPL code; manual CLI; llama.cpp; MLX;
                             weaken SAFE; merge to kultrun; write
                             production GiB in pytest.
DEBT                         K-110 CLOSED (superseded, not rewritten).
                             K-111 remainder: manual + G-REPL +
                             physical Sonar L2 + >256.
```

## Logical tree (pseudocode)

```text
establish 1 GiB owned reserve or return VERY_LOW
test 64
  success → test 128
    success → test 256
      success → lower >= 256, upper UNKNOWN
      capacity → test 192 → 192 or 128
    capacity → test 96 → 96 or 64
  capacity → test 32
    success → test 48 → 48 or 32
    else → test 16
      success → test 24 → 24 or 16
      else → VERY_LOW
```

Only CAPACITY forms an upper bound. Partial file size is not a tier.
Physical I/O may checkpoint 16, 24, 32, 48 while growing to 64.

## Confirmation policy

```text
if specialist bytes and Sonar lower bound both resolved:
    if disagreement_ratio <= 0.10:
        operational = specialist   # confirmed
    else:
        operational = Sonar
elif Sonar resolved:
    operational = Sonar
elif specialist resolved:
    operational = specialist     # Sonar could not characterize
```

Cheap GET never enters this path (`run_empirical=False`).
