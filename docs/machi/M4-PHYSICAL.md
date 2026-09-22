# M4 Capacity — physical acceptance

**Work token:** `MACHI-4-CAPACITY`  
**Implementation commit:** `68a503e8b6acb7ace18ca128d12f5bc5d0c1a8f7`  
**SHA256:** `56d6a5d7691f950f9e52c416f0a22f30b16e4fda4407115f8ee4792a5f16a8a2`  
**Build ID:** `0.1.0+68a503e8b6ac`  
**Lab campaign:** `camp_91bc6fbe5ff82172`  
**Lab candidate:** `cand_2e678022388cd01d`  
**Lab checkpoint:** `chk_7f1c4a86323e4893`  
**Result:** `CAPACITY_TIER2_CLOSED`

No GPU pod. No production-size Sonar write. Fixtures were disposable
and removed. The frozen wheel was installed into a throwaway venv.

## Case A — this host, ordinary storage, no Sonar write

`machi capacity evaluate` on an owned state root.

- physical RAM `8589934592`
- execution limit `unsupported` (not read as a fake ceiling)
- reserve `536870912`
- SAFE memory `8053063680` (physical minus reserve)
- 11 storage domains, 9 usable, 2 excluded
- one usable domain reported `8448126976`, SAFE `7374385152`
- `sonar.writes` `disabled`; sonar status `not_attempted`

`CASE_A=PASS`

## Case B — overlay / container

Not run. Docker was not required to close the behavior that this host
and the Sonar writer already covered. Overlay classification remains a
Discover fact. A container Sonar run is residual, not a reason to
provision a pod.

`CASE_B=RESIDUAL`

## Case C — bounded real write, not a quota exhaustion

The frozen wheel's Sonar writer committed 64 then 128 real bytes on a
disposable directory, corroborated a reported ceiling of 200, and
removed the probe file. No EDQUOT environment was available. The
contradiction rule is proven in local tests, not by filling a disk.

`CASE_C=PASS` for allocation, extension, and cleanup.  
`EDQUOT` physical contradiction is residual.

## Case D — accelerator

This host's accelerator row was `unified`. `safe_bytes` stayed
Unresolved. Discrete NVIDIA/AMD headroom was not re-proven on a GPU
pod; per-device arithmetic is covered by local tests.

`CASE_D=PASS` for unified-not-a-pool. Discrete physical headroom is residual.

## Coverage

```text
TARGET_POPULATION = MACHI_RELEVANT_CAPACITY_BEHAVIOR
WEIGHTS: memory/execution 0.25, ordinary storage SAFE 0.20,
         excluded read-only 0.10, unified accelerator 0.15,
         sonar allocate/cleanup 0.15,
         quota contradiction 0.10 residual,
         discrete GPU pod 0.05 residual
SELECTED: A, C, D
ESTIMATED_COVERAGE = 0.85
TARGET_MET = YES
RESIDUAL: live quota specialist, EDQUOT on a real volume, overlay Sonar, discrete GPU pod
```

## Product defects

None requiring a candidate rebuild.
