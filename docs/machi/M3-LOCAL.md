# M3 Steward — local acceptance

**Work token:** `MACHI-3-STEWARD`  
**Implementation commit:** `785a7658ba73b25e4bafb33686fb0ec4761df244`  
**Artifact:** `machi-0.1.0-py3-none-any.whl`  
**SHA256:** `a9234b697ef659ebcebdcab446ac36b30b1408d55f9b259e5a6231ef35f681e9`  
**Build ID:** `0.1.0+785a7658ba73`  
**Size:** 143293 bytes  
**Clean source:** true  
**Result:** local isolated-wheel reconstruction **PASS**; physical follows

This exact archived wheel is the Steward Tier-2 candidate.

## Archived candidate

`dist/machi/candidates/785a7658ba73b25e4bafb33686fb0ec4761df244/machi-0.1.0-py3-none-any.whl`

Strategy docs commit on this branch: `dedf801628bee6479b815a6e058e948721b8aa53`.
It sets `VllmExecutionMacropath` as PRIMARY and `OllamaExecutionMacropath`
as COMPATIBILITY / FALLBACK. Dynamo stays deferred. Untracked
`docs/machi/proposals/` were not committed.

Predecessor 2.4 remains `b131041` / wheel `3fbf6c83…`. Canonical `machi`
remains `1db7646`.

## What was proven locally

- Fresh throwaway venv; wheel-only install; Kultrun absent
- `machi steward assess` verifies a root whose marker and registry agree
- `destructive_authorization` is false
- no `safe_storage_bytes`
- events are `operational` and do not carry the state-root path
- prior `discover.mounts.observed` is not rewritten
- `tests/machi` passed, including ownership, lifecycle, symlink, and
  hard-link cases

## Lab

| Record | ID |
|---|---|
| Campaign | `camp_611b40f4f3d82d84` |
| Policy snapshot | `pol_ae03b9617c14468e` |
| Candidate | `cand_a29dd524251ae6c7` |
| Local run | `erun_643b802c73632c5a` |
| Checkpoint | `chk_22e9eec9041d5317` |

Isolated `tools/verify_machi.py` → `verify_ok`.
