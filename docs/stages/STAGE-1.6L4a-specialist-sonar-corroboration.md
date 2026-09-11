# Stage 1.6L4a — Specialist / Sonar corroboration

**Milestone 1 — Walking skeleton (storage correction, not 1.6L close).**

Status: **implementation on `stage/1.6L4a-specialist-sonar-corroboration`.**
Does not close Stage 1.6L. Does not start 1.6M. Does not add runtimes.

Predecessor: 1.6L4 Storage Sonar V2
`5773a8d7746d032340fbf6299d3655167c97e26e`.

Sequence:
`docs/investigations/STORAGE-RUNTIME-BREADTH-SEQUENCE.md` (S3.1).

```text
CURRENT STAGE                Specialist is capacity authority unless
                             Sonar contradicts it with a capacity
                             failure strictly below the candidate.
PREDECESSOR OUTPUTS           1.6L4 Sonar V2 engine 5773a8d.
THIS STAGE'S REQUIRED OUTPUT Corroboration policy; specialist value
                             retained when confirmed / inconclusive /
                             lower-only; empirical after contradiction.
CORE CONTRACTS AFFECTED      optional EmpiricalProbeEvidence.corroboration
                             and specialist_candidate_bytes;
                             policy_version 1.6L4.1-corroboration.
ADAPTERS AFFECTED            none. Sonar engine reused, not rewritten.
PERSISTED STATE              see_* during probes; sce_* after cleanup.
MUTATION / FAILURE BOUNDARY  Only EDQUOT/ENOSPC below S contradict.
CANCELLATION / CLEANUP       Unchanged reserve / probe cleanup.
ACCEPTANCE LEVEL             L1 scaled FakeVolume. Not L2. Not T3.
MUST NOT                     G-REPL; manual CLI; llama.cpp; MLX;
                             weaken SAFE; merge to kultrun; new Sonar
                             tiers; write production GiB in pytest.
DEBT                         K-102/K-103/K-105/K-106 remain OPEN.
                             K-111 remainder after 1.6L5: physical
                             Sonar L2. 256 GiB ceiling is not a
                             reason to distrust S > 256.
```

## Authority (pseudocode)

```text
candidate = specialist.available_bytes
if smaller_hard_bound exists:
    candidate = min(candidate, smaller_hard_bound)

if no usable specialist:
    run full Sonar V2
    authorizing = sonar.lower_bound or unresolved
else:
    L = greatest official tier <= candidate
    U = smallest official tier > candidate
    if L is missing:          # S < 16
        corroboration = limited
        authorizing = candidate
    else:
        if test(L) is CAPACITY and L_bytes < candidate:
            specialist contradicted
            authorizing = full_sonar_v2()
        else if test(L) is OTHER:
            corroboration = inconclusive
            authorizing = candidate
        else if U is missing:  # S >= 256
            r256 = test(256)
            if r256 is SUCCESS:
                corroboration = lower_only if S > 256 else confirmed
                authorizing = candidate
            else if r256 is CAPACITY and 256 < candidate:
                contradicted; authorizing = full_sonar_v2()
            else:
                inconclusive; authorizing = candidate
        else:
            ru = test(U)
            if ru is CAPACITY:
                confirmed_bracketed; authorizing = candidate
            else if ru is SUCCESS:
                not_contradicted; authorizing = candidate
            else:
                inconclusive; authorizing = candidate
```

```text
specialist >256 GiB
+ Sonar proves 256 GiB
+ no smaller hard contradiction
→ retain specialist capacity
```

Cheap GET (`run_empirical=False`) never enters this path.
