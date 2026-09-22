# M4 Capacity — local acceptance

**Work token:** `MACHI-4-CAPACITY`  
**Implementation commit:** `68a503e8b6acb7ace18ca128d12f5bc5d0c1a8f7`  
**Artifact:** `machi-0.1.0-py3-none-any.whl`  
**SHA256:** `56d6a5d7691f950f9e52c416f0a22f30b16e4fda4407115f8ee4792a5f16a8a2`  
**Build ID:** `0.1.0+68a503e8b6ac`  
**Size:** 161900 bytes  
**Clean source:** true  
**Result:** local isolated-wheel reconstruction **PASS**

## Archived candidate

`dist/machi/candidates/68a503e8b6acb7ace18ca128d12f5bc5d0c1a8f7/machi-0.1.0-py3-none-any.whl`

Strategy pointer commit `3410d55` is on this branch. Steward evidence
`a470857` is unchanged. Canonical `machi` remains `1db7646`.
Untracked `docs/machi/proposals/` were not committed.

## What was proven locally

- Reported, proven, and SAFE stay distinct
- A smaller specialist or EDQUOT bound beats a larger report
- A larger Sonar write does not raise the reported ceiling
- Corroboration keeps the reported value; there is no ±10% rule
- GPUs stay separate; unified memory is not a VRAM pool
- Shared backing is not summed; read-only storage is excluded
- Default `sonar.writes` is `disabled`
- Isolated `tools/verify_machi.py` → `verify_ok`

## Lab

| Record | ID |
|---|---|
| Campaign | `camp_91bc6fbe5ff82172` |
| Policy snapshot | `pol_8309a1317100786c` |
| Candidate | `cand_2e678022388cd01d` |
| Local run | `erun_0284446039677cd2` |
| Checkpoint | `chk_7f1c4a86323e4893` |
