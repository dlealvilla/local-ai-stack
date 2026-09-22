# M3 Steward — physical acceptance

**Work token:** `MACHI-3-STEWARD`  
**Implementation commit:** `785a7658ba73b25e4bafb33686fb0ec4761df244`  
**Artifact:** `machi-0.1.0-py3-none-any.whl`  
**SHA256:** `a9234b697ef659ebcebdcab446ac36b30b1408d55f9b259e5a6231ef35f681e9`  
**Build ID:** `0.1.0+785a7658ba73`  
**Lab campaign:** `camp_611b40f4f3d82d84`  
**Lab candidate:** `cand_a29dd524251ae6c7`  
**Lab checkpoint:** `chk_22e9eec9041d5317`  
**Result:** `STEWARD_TIER2_CLOSED`

Physical population: ownership and filesystem behavior. Not GPU market
coverage. No pod was created. Fixtures lived under a disposable `/tmp`
tree and were removed after the run. The wheel was installed into a
throwaway venv. No pre-existing customer files were used.

## Case A — verified owned active root

`machi install establish-record` then `machi steward assess`.

- ownership `verified_machi_owned`
- lifecycle `active`
- protection `active_protected`
- reclaimability `not_reclaimable`
- `delete False`
- payload file still present
- measured bytes reported (not unresolved)

`CASE_A=PASS`

## Case B — copied marker

The Case A marker file was copied onto a different directory.

- ownership `conflicted`
- reclaimability `not_reclaimable`
- size `unresolved(not_measured)`
- copied marker file still present

`CASE_B=PASS`

## Case C — obsolete unprotected candidate

A second established root assessed with `--generation obsolete`.

- lifecycle `obsolete`
- protection `unprotected`
- reclaimability `reclaimable`
- `delete False`
- `old.bin` still present

`CASE_C=PASS`

## Case D — symlink escape and hard link

Using the frozen wheel's measurement on two disposable trees: one with
two distinct 5-byte files, one with a hard link plus a symlink to a
4096-byte file outside the root.

- symlink escapes recorded: 1
- measured size 244 bytes, below the 4096-byte target
- outside file still present

A user-level bind mount was not created. Crossing onto another device
is covered by the measurement rule and remains a residual for a
privileged mount.

`CASE_D=PASS` for symlink and hard link. Bind-mount crossing is residual.

## Case E — legacy marker

A directory containing only `.kultrun-owner.json`.

- ownership `legacy_unverified`
- reclaimability `not_reclaimable`
- legacy file still present

`CASE_E=PASS`

## Coverage

```text
TARGET_POPULATION = OWNERSHIP + FILESYSTEM BEHAVIOR
WEIGHTS: verified active 0.25, conflict/copied 0.20, obsolete candidate 0.20,
         symlink/hardlink 0.15, legacy 0.12, bind-mount crossing 0.08 residual
SELECTED: A B C D E
ESTIMATED_COVERAGE = 0.92
TARGET_MET = YES
RESIDUAL: privileged bind-mount crossing; automatic deletion (Tier 3, S-3-01)
NEXT_HIGHEST_VALUE = not required to close Tier 2
```

## Product defects

None requiring a candidate rebuild.

## Environment

Darwin filesystem. Directory `st_size` dominates measured bytes, so a
successful measurement is not a count of customer file payloads alone.
Journal files inside a state root are part of that root's occupancy.
