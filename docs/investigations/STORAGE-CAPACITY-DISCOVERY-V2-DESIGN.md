# Storage Capacity Discovery V2 — design from repository truth

**Status:** investigation and design only. No production behavior change.

**Code under audit:** storage implementation
`caa9e03225cd9fa8b7d12707b144406a69902ae6`
(`stage/1.6L-storage-capacity-truth`).

**Physical predecessor:** acceptance integration
`efba9d92ecf995f13d4d888d2c516104594f48aa` on RunPod `/workspace` FUSE
MooseFS (`stage-1.6L-storage-r4-20260910T212743Z`). That run is evidence of
current behavior, not a specification.

**This branch:** `investigation/storage-capacity-discovery-v2`, created
from `caa9e03`. It does not modify frozen Stream A, Stream B, storage
implementation, or acceptance HEADs.

**Predecessor investigation:** `investigation/1.6L-storage-capacity-truth`
at `a5ebd41` is the *pre-implementation* CLASS B report. It is frozen. This
document audits the *implemented* repair against a new target algorithm.

Non-goals: no Sonar patch, no threshold change in code, no runtime adapters,
no llama.cpp, no deploy, no further GPU rental, no Stage 1.6M.

---

## 1. Current executable flow

Traced from `src/kultrun/main.py`, `storage/characterize.py`,
`storage/evidence.py`, `storage/sonar.py`, `platform/foundation_realize.py`,
`resource/manager.py`, `capacity/envelope.py`.

Every `kultrun` CLI command calls `build()`.

```text
1. Host discovery (hwloc / nvidia / native-linux)
   native-linux: os.statvfs → MountFacts.free_bytes / total_bytes
   (reported figures; authorizes nothing by themselves)

2. OwnershipService.ensure_platform_roots
   dual markers .kultrun-owner.json + registry

3. Cheap characterization  (ALWAYS, at startup)
   StorageCharacterizationService.characterize(
       run_cleanup=True,
       run_empirical=False,          # GET /host never Sonars
       probe_workspace=state_root,
   )
   → StorageEvidenceIndex.put_many(...)   # OVERWRITES per-pool key

4. CapacityService.compute(host, sanity, stored_storage)
   REPORTED / EFFECTIVE / SAFE
   FUSE: EFFECTIVE = min(reported, 64 GiB) display/belief
         SAFE = UNRESOLVED unless authorizing_available_bytes is set

5. Foundation / Available Models / planning read the envelope
   (cheap path: /workspace SAFE unresolved)

6. Mutation path: kultrun runtimes realize
   FoundationRealizeService._realize_once:
     characterize(run_cleanup=True, run_empirical=True)
       Step 0 disposable cleanup
       pools_from_host + bind_path (longest prefix, no first-pool)
       native_available_bytes (live statvfs on linux/darwin)
       ProbeRegistry.run — every compatible specialist
       arbitrate native vs probe
       needs_empirical_fallback? → EmpiricalStorageProbe
       re-arbitrate with empirical
     if low_space (< 5 GiB operational): stop, admin guidance
     foundation.view(..., require_storage=True)
       _storage_feasible: requirement.peak <= operational_available
     ResourceManager.admit(RUNTIME_PROVISIONING, incremental=peak)
       compares against envelope SAFE (not operational)
     then FoundationSelectionService.realize_selected → pip

7. On capacity/footprint failure: StorageReplanService
   100% → 90% → 81% → 72.9% (max 3), real smaller candidates only

8. After successful install: index.invalidate + cheap rediscover
   (run_empirical=False again)
```

**Exact capacity authorization point:**
`CapacityService._pool` via `_authorizing_storage(StorageCapacityEvidence)`
then `_withhold` → `LayeredBytes.safe_bytes`. ResourceManager spends SAFE.

**Exact runtime-feasibility point:**
`FoundationSelectionService._storage_feasible` /
`storage.feasibility.requirement_fits` against **operational** bytes
(not SAFE). Then RM admits against **SAFE**. These two numbers differ.

**Exact mutation point:**
`ProvisioningService.provision` → `VllmNativeProvisioner.install`
(`pip install --no-cache-dir`). Must not start before RM ADMITTED.

GET `/host` / `kultrun host` never calls empirical Sonar. That is
intentional and must remain. The defect is that the cheap snapshot
**replaces** the stronger stored characterization (see §15).

---

## 2. Current native / programmatic storage

| Source | File | Function | Platform | Semantics | Trusted? | Authorizing? | Consumer |
|---|---|---|---|---|---|---|---|
| Live statvfs | `host/adapters/native_linux.py` | mount inventory | Linux | `f_bavail * f_frsize` caller-available | family allow-list | no | `MountFacts.free_bytes` |
| Live statvfs | `storage/native.py` `native_available_bytes` | linux/darwin | same | yes if `is_credible_family` | only if trusted | characterize |
| Fixture mount | `adapters/host/fixtures` | replay | any | captured free | as family | no until characterize | fixture tests / GET |
| POSIX probe class | `adapters/storage/posix_stat.py` | `PosixStatvfsProbe` | linux/darwin | same as native | n/a | **not in default registry** | unused on live path |
| Windows | `adapters/storage/windows.py` | Win32 | deferred | no | no | K-100 |
| macOS extra | `adapters/storage/macos.py` | APFS/quota | deferred; native is still statvfs | darwin statvfs may authorize if `apfs` in allow-list | K-101 |
| Provider/orchestrator | none | — | — | — | no | K-108 |
| Quota fields on MountFacts | none | — | — | — | no | — |

**StoragePool / quota_identity:**
`storage/topology.py` `quota_identity_for` =
`{family}:{device}:{mount_point}`. Example physical:
`fuse:mfs#us-ks-2.runpod.net:9421:/workspace`.

**Credibility (`is_credible_family` / `FAMILIES_WITH_CREDIBLE_SIZE`):**
local block FS + overlay. **Not** FUSE, NFS, Ceph, SMB, object, unknown.

**REPORTED:** mount free (statvfs).
**EFFECTIVE:** trusted family = reported; else `min(reported, 64 GiB)`
belief bound (`UNVERIFIED_POOL_CEILING_BYTES`).
**SAFE:** `_withhold(effective, 0.10, 5 GiB)` **only if** authorizing
evidence exists **or** family is SUFFICIENT. Otherwise UNRESOLVED.

**500 GiB anomaly:** **not implemented**. The related constant is
`SANITY_TRIGGER_BYTES = 1 TiB` in `capacity/policy.py`, used only to *flag*
that operator 1.2A sanity *could* be run. It does not trigger specialist
probes or Sonar. Specialist probes run whenever `supports()` is true.

**Trusted local path (ext4 180 GiB, no quota bytes):**
YES — already works: native AUTHORITATIVE, SAFE withheld 10%/5 GiB,
no Sonar (`needs_empirical_fallback` is false for credible families unless
CONTRADICTED).

**FUSE path:** native not trusted → UNRESOLVED → Sonar on mutation.

---

## 3. Technology-specific probe inventory

`default_probe_registry()` registers, in order:
`LinuxQuotaProbe`, `FuseIdentifyProbe`, `MooseFSQuotaProbe`,
`NFSQuotaProbe`, `WindowsCapacityProbe`, `MacosCapacityProbe`.

`PosixStatvfsProbe` exists but is **not registered**. Native uses
`storage/native.py` instead.

Registry rule: every compatible probe **must** run. Identification without
bytes is not settlement (`needs_empirical_fallback`).

### Linux quota — `linux-quota` / `LinuxQuotaProbe`

| Field | Truth |
|---|---|
| detection | `os_name==linux` and fstype in ext2/3/4, xfs, btrfs, f2fs |
| `supports()` | yes |
| executed | only if `quota` on PATH |
| external binary | `quota` (optional, not bundled) |
| Python package | no |
| returns bytes | **NO** — `available_bytes=NOT_PROVIDED` even when executed |
| parsing | not implemented |
| tested | `test_storage_probes.py` (supports/run, not parse) |
| physical | not on RunPod image |
| fallback | Sonar only if family not credible (ext4 does **not** Sonar) |
| debt | K-102 |

**Status:** PARTIAL / PLACEHOLDER (seam + optional invoke, no bytes).

### XFS / Btrfs / ZFS

No dedicated adapters. XFS/Btrfs ride `linux-quota` (unparsed).
ZFS is in the credible-size allow-list so **statvfs may authorize** even
with dataset quotas. **Status:** MISSING (K-102). Risk: ZFS trusted
native can be wrong.

### FUSE — `fuse-identify` / `FuseIdentifyProbe`

| Field | Truth |
|---|---|
| detection | fstype in fuse/fuseblk/fuse.sshfs or "fuse" in device |
| executed | always when compatible |
| bytes | **NO** — identification only |
| tested | `test_fuse_and_moosefs_match_fuse_mfs` |
| physical | YES — executed on RunPod |
| status | WORKING_AS_DESIRED for identification |

### MooseFS — `moosefs-quota` / `MooseFSQuotaProbe`

See §4. **Status:** PARTIAL seam (K-105).

### NFS — `nfs-quota` / `NFSQuotaProbe`

`supports` nfs/nfs4. If `quota` or `nfsstat` present: `executed=True` with
detail "numeric NFS rquota deferred" and **no bytes**. K-103.
**Status:** PLACEHOLDER.

### SMB/CIFS

No probe class. Family is in `FAMILIES_REQUIRING_EVIDENCE` so native does
not authorize; Sonar would run. K-104. **Status:** MISSING.

### CephFS

No probe class. Family `ceph` requires evidence. K-106. **Status:** MISSING.

### Windows — `windows-capacity`

`supports` windows/win32. Probe always `executed=False`, no bytes. K-100.
**Status:** PLACEHOLDER / fixture contract.

### macOS/APFS — `macos-capacity`

Same: executed=False. Native darwin `statvfs` still used; `apfs` is in
the credible allow-list so macOS local disks may authorize from native.
Physical APFS quota / `F_PREALLOCATE` is K-101 / K-28.
**Status:** PLACEHOLDER extra; native path PARTIAL.

### Container overlay

No probe. `overlay`/`overlayfs` are **credible**. Physical overlay `/`
~30 GiB was AUTHORITATIVE ~32 GiB operational, SAFE ~24.9 GiB.
**Status:** WORKING_AS_DESIRED for container-local writable layer.
CSI/PVC is K-107 MISSING.

### Kubernetes/CSI, cloud/provider

No adapters. K-107, K-108. **Status:** MISSING.

### Unknown / proprietary

Unrecognised family → not credible → SAFE unresolved → Sonar on mutation
if empirical allowed. **Status:** fail-closed WORKING_AS_DESIRED.

---

## 4. Physical MooseFS answer

**How detected:** `MountFacts.filesystem_type = fuse`,
`device = mfs#us-ks-2.runpod.net:9421`. Topology family = `fuse` (network,
not credible). `MooseFSQuotaProbe.supports` is true because `"mfs" in device`.
`FuseIdentifyProbe.supports` is also true.

**Which probes ran:** both fuse-identify and moosefs-quota (plus any other
compatible). Cheap evidence named `moosefs-quota` because characterize
walks reports and keeps the **last compatible name** unless a report has
executed **and** `available_bytes`. Fuse-identify executed without bytes;
MooseFS was last compatible → name `moosefs-quota` even when
`mfsgetquota` was absent.

**Was `mfsgetquota` the intended capacity source?** YES.

**Invoked?** NO. `shutil.which("mfsgetquota")` was None. Probe returned
`executed=False`, `available=False`,
detail `"mfsgetquota is not installed; optional MooseFS tooling"`.

**Bytes?** Unresolved.

**Other MooseFS mechanism?** None. No mfsmount ioctl, no HTTP, no
`getfattr`. Adapter is a seam.

**Parsing:** `_parse_mfs` **discards output** and returns
`(NOT_PROVIDED, NOT_PROVIDED, "mfsgetquota output not numerically parsed in v1")`.
Even if the binary existed, v1 would not produce bytes. **K-105.**

**Did Kultrun perform a technology-specific MooseFS *capacity* probe?**

```text
technology identified:     YES (fuse + mfs in device)
capacity successfully measured: NO
```

Fallback: algorithmic Sonar (`empirical-fallback`).

---

## 5. Current 10% evidence arbitration

`storage/evidence.py` `disagreement_ratio` and `arbitrate`:

```text
ratio = abs(native - probe) / max(native, probe)

if both present and ratio ≤ 0.10:
    selected = native if native_trusted else probe
    status = CORROBORATED
elif both present and ratio > 0.10:
    selected = probe (capped by hard)
    status = CONTRADICTED
elif probe only:
    selected = probe
elif native only and trusted:
    AUTHORITATIVE
elif native only and not trusted:
    UNRESOLVED   # FUSE 179 TiB does not authorize
```

Empirical lower bound is injected as `probe` when specialist bytes are
missing (`probe_name = empirical-fallback`).

**On quota-sensitive (native_trusted=False):** if specialist bytes exist,
the specialist **already always wins**. The 10% rule only changes the
status label (CORROBORATED vs CONTRADICTED).

**On trusted local:** ≤10% disagreement keeps **native**; >10% uses probe.
A future parsed project-quota of 50 GiB vs statvfs 180 GiB would already
select 50 GiB. A 9% quota lie would keep native — that is the remaining
hole.

**Recommendation (do not implement here):**

```text
trusted ordinary local + no specialist bytes
  → native remains authority

quota-sensitive / shared / network
  → native never authority (already)

specialist probe returns caller-entitlement bytes
  → specialist is operational authority
     10% comparison is corroboration/diagnostic only
     smaller hard bound still caps
```

This is **Policy: specialist-wins-when-byte-producing**, not “always native
if close.” Aligns with the new target. The 10% *deployment* replan
(K-110) is a **different** 10% and must stay separate.

---

## 6. Current Sonar algorithm

**Module:** `src/kultrun/storage/sonar.py` `EmpiricalStorageProbe`
writes via `adapters/storage/empirical_write.py` `RealWritePort`.

**Trigger (`needs_empirical_fallback`):**
- evidence CONTRADICTED, or
- UNRESOLVED and family not credible, or
- family not credible and no specialist executed **with bytes**.

Suppressed when: `run_empirical=False` (startup/GET); no empirical port
(fixture); family credible and not contradicted; operational already
below 5 GiB low-space (skips large writes); `known_low_bytes<=0`.

**`DEFAULT_MAX_EMPIRICAL_PROBE_BYTES` = 25 GiB.**

Why 25 GiB: documented as a **probe budget**, never `available = 25 GiB`.
Chosen as a bounded exploration for v1 / CLASS B, matching the old
provisioning peak range (15–25 GiB). It is **not** adaptive.

**`_search_sizes(first, ceiling, granularity)`:** start at 1 MiB, **double**
until `< ceiling`, then append ceiling. Example for 25 GiB:
1 MiB … 16 GiB, then 25 GiB. Granularity is unused in size generation
(used only in binary-search `_refine` after a failure bracket).

**Writes:** `open("wb")` + `handle.write` of 8 MiB chunks, `flush` +
`os.fsync` every 8 chunks. **Not sparse, not truncate, not fallocate-only.**
Each rung **rewrites from zero** (`"wb"`). Incremental growth is **not**
supported by the current port.

**Stop:** capacity failure (EDQUOT/ENOSPC) → upper=failed size, refine
binary search while `upper-lower > 64 MiB`; other errors interrupt
without claiming capacity; timeout 600 s; cancel; `size >= ceiling`
→ `probe_ceiling_reached`.

**If max succeeds:** `verified_lower_bound >= ceiling`, upper UNKNOWN.
Arbitration sets operational = 25 GiB. Capacity then SAFE =
`25 GiB - max(10% of 25 GiB, 5 GiB) = 25 - 5 = 20 GiB`.

**Does 25 GiB cap planning?** **YES, in practice.** Operational 25 GiB →
SAFE 20 GiB. vLLM peak estimate 24 GiB. RM denies. The physical T3 block
is this arithmetic, not a FUSE SAFE leak.

Emergency reserve: `ceiling = min(25 GiB, native - 1 GiB)`. On 179 TiB
native this does **nothing**. It does not protect a hidden 50 GiB quota.

Owned probe path: `{probe_workspace}/.kultrun-sonar/`, dual ownership
`DISPOSABLE`, cleaned in `finally`. Physical: directory gone after realize.

Timeout: 600 s. At ~50–90 MB/s MooseFS, 25 GiB completed in ~4.5 min.
A 256 GiB tree would need a higher time/I/O budget or incremental growth.

---

## 7. Physical predecessor interpreted against code

| Observation | Code explanation | Verdict |
|---|---|---|
| 179 TiB statvfs | native-linux + `native_available_bytes` | expected |
| FUSE not authorizing | `native_trusted=False` → UNRESOLVED | CORRECT architecture |
| fuse-identify ran | registry always-run | CORRECT |
| no MooseFS bytes | no `mfsgetquota`; parse stub | expected (K-105) |
| Sonar to 25 GiB | doubling search + ceiling | WORKING algorithm, **wrong policy for V2** |
| lower ≥ 25, no upper | ceiling reached | as designed today |
| SAFE 20 GiB | withhold max(10%, 5 GiB floor) | 5 GiB floor, **not 20%** |
| vLLM 12+12=24 | `storage/footprint.py` constants | ESTIMATED |
| blocked before pip | RM 24 GiB > SAFE 20 GiB | CORRECT architecture |

**Incorrect/incomplete for V2:** stopping at a 25 GiB exploration budget
so the host cannot prove 32/48/64 GiB tiers that would admit vLLM.

Do **not** “fix” this by weakening SAFE, inflating estimates, or claiming
30 GiB without writing it.

---

## 8. Desired V2 flow (refined against repository seams)

The proposed 31-step sequence is accepted with these **deviations**
(dependencies already in the code, not new architecture):

1. **Minimal topology** already happens in host discovery (step 1).
2. **Step 0 is inside characterize**, not a separate CLI. Keep it there;
   do not add a second cleanup command.
3. Cheap GET must remain empirical-free. Split persistence (step F)
   so GET can refresh REPORTED without clobbering authorizing evidence.
4. Specialist probing already runs on **every** compatible technology,
   not only when native > 500 GiB. Keep that. Add Condition A (implausible
   size) as an *additional* trigger for **credible** families that look
   like shared backends (e.g. 12 TiB “ext4” that is actually a bind).
5. Foundation feasibility currently uses **operational**; RM uses
   **SAFE**. V2 should use one authorizing figure for both, or document
   the two-step (fit vs headroom) explicitly. Recommend: feasibility
   against SAFE (same as RM) so we do not select then immediately deny.
6. llama.cpp is **absent** as a Runtime. Do not put it on the v1 V2
   critical path (increment J is optional later).
7. Manual 20%×5 is **orthogonal** to K-110 10%×3. Policy A.
8. Runtime+minimum-model before pip is desirable but is a **platform
   composition** extension, not storage-core. Defer unless Minimum+depth.

Refined V2 sequence:

```text
host topology
→ owned roots + Step 0
→ native measurement (cheap always)
→ classify (trusted / implausible / quota-sensitive)
→ if specialist required: run compatible probes
→ if byte-producing specialist: operational = specialist (hard cap)
→ else if mutation path and fallback required: Sonar decision tree
→ persist EmpiricalProbeEvidence + authorizing characterization
→ CapacityService: SAFE = withhold(authorizing)
→ if still unresolved: administrator last resort (hard-bound)
→ derive feasible foundations (storage is one input)
→ RM admit → provision → invalidate expensive characterization
   cheap REPORTED may refresh; authorizing stays until invalidation
→ verify → Available Models → model admit → …
→ ordinary footprint failure: K-110 10% × 3
→ manual-capacity mode only: 20% × 5
```

---

## 9. Native / specialist trigger policy (proposed)

**Condition B (primary) — technology risk** (already present):

Run specialist probes if family ∈ requiring-evidence **or** any registered
probe `supports()` (linux-quota on ext4 already does).

**Condition A (additional) — generic anomaly:**

If native available ≥ **500 GiB** *and* we have not already classified the
family as requiring evidence, still attempt specialists / treat as
suspicious. Current `SANITY_TRIGGER_BYTES` is **1 TiB** and only flags
K-27 operator sanity. Recommend **500 GiB as a characterize suspicion
trigger**, not a capacity cap, and **not** the only specialist trigger.

Do **not** require native > 500 GiB before MooseFS/NFS probes.

**Ordinary local:** ext4/xfs/… with plausible native, no specialist bytes,
no contradiction → native authorizes (already).

**ZFS gap:** currently credible. Dataset quota can lie. V2 may move ZFS
to requiring-evidence until a bytes probe exists (K-102). Flag as OPEN
if that is too aggressive for developer Macs/servers.

---

## 10. Target Sonar tree

```text
TEST 64 GiB
  SUCCESS → TEST 128
              SUCCESS → TEST 256
                          SUCCESS → proven >= 256 (upper unknown)
                          FAIL    → TEST 192
                                      SUCCESS → 192
                                      FAIL    → 128
              FAIL    → TEST 96
                          SUCCESS → 96
                          FAIL    → 64
  FAIL    → TEST 32
              SUCCESS → TEST 48
                          SUCCESS → 48
                          FAIL    → 32
              FAIL    → TEST 16
                          SUCCESS → TEST 24
                                      SUCCESS → 24
                                      FAIL    → 16
                          FAIL    → <16 / UNRESOLVED
```

**Tiers:** `<16, 16, 24, 32, 48, 64, 96, 128, 192, ≥256`.

**Failed higher does not erase lower success.** (Current `_refine` already
keeps `lower` on EDQUOT; V2 tree should do the same.)

**Probe count:** typical 3; low-space branch 4; worst case **4**
(64f→32f→16s→24). Acceptable vs “3–4 meaningful probes.”

**Edge cases:**

- Timeout / permission / non-quota I/O: do **not** treat as a tier fail;
  go to manual last-resort (current interrupt semantics).
- Compression/dedupe: real writes of zeros/`bytearray` may not consume
  quota on some FS. Current filler is zeros. V2 should use **incompressible
  (random or counter) payloads**. Document as Sonar safety, not optional.
- MooseFS async quota: fsync already present; may still lag. Keep
  conservative tiers, not byte-perfect search.
- 64 GiB first write on a 20 GiB volume: one fail then 32/16 — correct.
- 256 GiB v1 cap: enough for MVP. Future >256 is debt.

**v1 ceiling 256 GiB proven** = lower bound; upper unknown. Do not climb
512/1024 in this stage.

---

## 11. Sonar I/O, incremental growth, safety

**Current:** rewrite each size from 0. Physical ~1+2+…+16+25 GiB written.

**V2:** grow one owned file (`ab` / `os.write` from current length).

```text
64 success, next 128 → write 64 more
128 success, next 256 → write 128 more
fail at 192 after 128 → keep 128 proven; truncate/remove extra if needed
```

**Safety:** still fsync; still not sparse; cleanup entire file after;
quota accounting on network FS should see growth. Failure mid-growth:
keep last successful length as lower bound, record errno.

**Current abstraction:** `write_exactly(path, size)` implies absolute
size with `"wb"`. Needs a new `extend_to(path, size)` or `append_bytes`.
Ports belong to storage; implementation in `adapters/storage`.

**Emergency reserve vs hidden quota:**

Subtracting 1 GiB from 179 TiB is useless. Recommend an **owned reserve
file** created **before** the first 64 GiB test:

- Size: **1 GiB** (same constant), Kultrun-owned, DISPOSABLE, on the
  **same quota identity** as the probe.
- If even 1 GiB reserve fails: treat as very-low / manual; do not start 64.
- On EDQUOT during a tier: delete reserve first, then probe file, so
  logs/state can persist.
- Does not invent capacity; it is recovery headroom.

This is design only.

**User-data safety (current vs target):** owned path, no unrelated delete,
bounded, cleaned, same pool as `state_root` when `probe_workspace` is set.
Physical sentinel survived. **WORKING_AS_DESIRED** except evidence of the
search (bytes/elapsed) is not persisted.

---

## 12. Manual administrator capacity

**Current:** `characterize(..., administrator_bounds={mount: int})` and
`apply_manual_bound` (manual cannot exceed smaller hard or
`empirical_upper - 1`). **No CLI, no API, no env, no persistence of a
manual fact as its own record.** Composition never passes bounds.

**V2 trigger (last resort only):** native inadequate **and** specialist
inadequate **and** Sonar cannot establish a useful tier (interrupt,
permission, timeout, disable-empirical, recovery unsafe).

**Semantics:** record source=administrator, value, timestamp, pool/quota
identity, confidence=LOW. Do **not** rewrite 100 GiB as 80/64. Reduce
**deployment footprint**, not the evidence.

Hard evidence wins: provider 50 GiB, EDQUOT at 42 GiB, etc.

---

## 13. Ordinary vs manual deployment reduction

| Mode | Attempts | Factor | Max extra tries |
|---|---|---|---|
| Ordinary auto-measured (K-110) | 100 / 90 / 81 / 72.9 | ×0.90 | 3 |
| Manual-capacity last-resort | 100 / 80 / 64 / 51.2 / 40.96 / 32.768 | ×0.80 | 5 |

Both: ceiling over **real candidates**, never `requirement *= k`, never
inflate SAFE, never convert MANUAL to AUTO.

**Recommendation: Policy A.** Manual mode is a different evidence class
(low confidence, human-stated). Coarser 20%×5 is appropriate there.
Ordinary Sonar/specialist failures should keep K-110. Policy B would
reopen a locally closed loop and change already-tested AUTO behavior
without a physical need.

If a later review wants a single policy, that is a product decision
(OPEN). Default for implementation: A.

Physical replan: runtime-only, “no smaller supported runtime” — only vLLM
exists. 20%×5 would not have helped without a second runtime.

---

## 14. vLLM storage requirement

From `storage/footprint.py` (not measured, not version-calibrated):

| Field | Value | Source |
|---|---|---|
| persistent | 12 GiB | `DEFAULT_VLLM_PERSISTENT_BYTES` |
| staging/transient | 12 GiB (= persistent) | `runtime_provisioning_requirement` |
| cache | 0 | `--no-cache-dir` |
| peak | 24 GiB | persistent + staging |
| confidence | LOW until `measured=True` | |
| reserve field | 5 GiB | **not added to peak** (SAFE already withholds) |

Ranges (sanity only): vLLM 8–15 GiB, peak 15–25 GiB.

**Not** platform-specific. Pin is `vllm==0.28.0` but the 12 GiB figure
is not derived from that pin.

**SAFE vs peak:** RM requires `peak ≤ SAFE`.
`SAFE = authorizing - max(0.10 * authorizing, 5 GiB)`.

For 25–50 GiB authorizing, **floor 5 GiB dominates**:
need `authorizing ≥ 24 + 5 = 29 GiB` to admit a 24 GiB peak.

**Not** `24 / 0.80 = 30 GiB`. That assumed 20% headroom. Actual fraction
is **10%**, floor **5 GiB**. Physical: 25 − 5 = 20. Correct.

**Standalone `VLLM_MIN_STORAGE = 30 GiB`:** **not recommended.** Keep
requirement-based comparison (`SAFE` vs `RuntimeStorageRequirement`).
A magic 30 GiB would hide estimate or headroom changes.

**End-to-end runtime+model before pip:**
`runtime peak + min viable model` is knowable only loosely (catalog
`storage_bytes` / `peak_additional_bytes` on packaged candidates).
Recommended seam: `FoundationRealizeService` / a platform preflight that
asks storage+planning “does any Available-eligible candidate fit after
runtime peak?” Avoid a new domain. If expensive, Minimum+depth only:
compare runtime peak to SAFE (already) and document that first model may
still fail later (current, acceptable for v1).

---

## 15. llama.cpp and runtime decision tree

| Question | Repository truth |
|---|---|
| Runtime adapter | **ABSENT** (no `adapters/runtime/llama*`) |
| Resolver | only descriptors that exist: vLLM PRODUCT, reference-serving, reference-process. Explicit `llama.cpp` → unresolved note, no candidate |
| Environment recipe / provision / verify | none |
| Executor | NativeProcessExecutor is generic; no llama.cpp launch recipe |
| GGUF eligibility | vLLM `known_formats=("safetensors",)`; tests block GGUF for vLLM. Catalog lists llama.cpp on many entries as metadata only |
| ResourceManager | generic; would admit any runtime’s storage request |
| Licensing | not evaluated in-tree; llama.cpp MIT would be fine commercially **if** implemented |
| Maturity | **absent**, not partial |

**Best current lower-footprint fallback:** **none that is production-ready.**
Reference-serving is TEST/REFERENCE, not a product LLM. Do not advertise
llama.cpp as a V2 fallback until a real adapter exists. Putting it in the
decision tree now would be a **roadmap lie**.

**Target tree (after a future runtime increment, not this V2 min):**
derive feasible set from OS/CPU/RAM/GPU/VRAM/storage/support-tier, then
rank. Never `if disk < X → llama.cpp`.

Apple MLX: also absent.

---

## 16. Evidence persistence and freshness

**Where stored:** `StorageEvidenceIndex` one record per
`(host_id, mount_point)` of kind `storage.capacity_evidence`.

**Cheap overwrite:** `build()` always `characterize(run_empirical=False)`
then `put_many`. Unresolved cheap FUSE **replaces** Sonar CONTRADICTED
25 GiB. Next mutation `needs_empirical_fallback` again → **re-Sonar**.
No history. `EmpiricalProbeEvidence` is a contract **not written** by
the index.

**Recommended model:**

```text
latest_observation     cheap native/mount snapshot (GET may update)
authorizing_characterization
  status, operational, SAFE inputs, probe_name, empirical_id
  not overwritten by cheap UNRESOLVED
empirical_run          first-class EmpiricalProbeEvidence
  sizes attempted, bytes written, lower, upper, errno,
  elapsed, cleanup, ceiling_reached, interrupted
```

Invalidation of **authorizing** (must re-Sonar / specialist):

| Event | Cheap refresh | Expensive re-characterize |
|---|---|---|
| GET /host / process restart | yes (observation) | no |
| Step 0 cleaned disposable | cheap OK | no unless bytes material |
| runtime provision / model acquire | yes | **yes** (already invalidate) |
| EDQUOT / ENOSPC | contradict + invalidate | yes |
| admin capacity change | — | yes |
| remount / quota_identity change | yes | yes (fingerprint change) |
| host reboot | observation | treat identity change as stale |
| time-based | optional later debt | not v1 |

GET must never write 64–256 GiB.

---

## 17. SAFE / headroom (do not weaken)

```text
reserve = max(floor(effective * 0.10), 5 GiB)
SAFE = effective - reserve   if remaining > 0 else NOT_MEASURED
```

Physical 25 GiB → reserve 5 GiB (floor) → SAFE 20 GiB.

**Recommendation:** keep `max(percent, absolute)`. Transparent in operator
output (“5 GiB floor applied”). Do **not** drop the floor to admit vLLM.
Better evidence (prove ≥29 GiB) or measured lower peak is the honest path.

Tier-dependent headroom is a possible later tweak; not required for V2 min.

---

## 18. Gap table (summary)

| # | Component | Current | Target | Class | Change | Depends | Test |
|---|---|---|---|---|---|---|---|
| 1 | Ordering | capacity-first on mutation | same | WORKING_AS_DESIRED | none | — | existing realize tests |
| 2 | FUSE distrust | UNRESOLVED SAFE | same | WORKING_AS_DESIRED | none | — | physical + unit |
| 3 | Specialist registry | always-run, mostly no bytes | byte-producing where possible | PARTIAL | parse K-102/105 when tools exist | A | probe bytes tests |
| 4 | 10% arbitration | native wins if trusted & ≤10% | specialist wins if entitlement bytes | WORKING_BUT_POLICY_CHANGE_REQUIRED | B | A | evidence tests |
| 5 | Sonar sizes | 1 MiB doubling to 25 GiB | 64/128/256 tree | WRONG_ALGORITHM | C | — | tree tests |
| 6 | Incremental write | rewrite `"wb"` | grow file | PARTIAL | D | C | I/O tests |
| 7 | Emergency reserve | 1 GiB vs native (useless on FUSE) | owned reserve file | WRONG_ALGORITHM for hidden quota | D | C | EDQUOT recovery |
| 8 | Cheap vs authorizing persist | cheap overwrites | split | WRONG_ORDER / persistence | F | E | host-after-realize |
| 9 | EmpiricalProbeEvidence | contract only | persist | MISSING persist | E | C | store tests |
| 10 | Manual capacity UX | function unused | last-resort CLI/API | MISSING | G | F | admin bound tests |
| 11 | Manual 20%×5 | 10%×3 only | Policy A extra mode | MISSING | H | G, K-110 | replan tests |
| 12 | Feasibility vs RM | operational vs SAFE | one figure | PARTIAL | I (small) | C | realize tests |
| 13 | llama.cpp | absent | optional later | MISSING / out of min | J | runtime stage | — |
| 14 | 500 GiB trigger | 1 TiB flag only | Condition A extra | PARTIAL | A | B | huge-native tests |
| 15 | Incompressible writes | zero `bytearray` | incompressible | PARTIAL | D | C | — |

---

## 19. Working already

- Capacity-first mutation order (characterize → fit → RM → pip)
- Dual ownership + Step 0 labelled-only delete
- FUSE/network native not authorizing SAFE
- Per-pool RM storage admission; no first-pool shortcut (physical: 20 GiB
  workspace, not overlay 24.9 GiB)
- Runtime blocked before pip when SAFE insufficient
- Model destination-pool admission (code; not physically reached this run)
- EDQUOT/ENOSPC classification + contradict path (unit; not physical)
- Sentinel / unlabeled data not deleted
- Real writes + fsync + owned probe cleanup
- K-110 real-candidate 10% loop (local tests; runtime physical: no smaller runtime)

---

## 20. Implementation decomposition and order

```text
C  algorithmic Sonar tree          # unblocks honest 32–256 proof
D  incremental write + reserve file + incompressible payload
E  persist EmpiricalProbeEvidence
F  cheap observation vs authorizing characterization
A  probe inventory + Condition A/B documentation in code comments/policy
B  specialist-wins-when-bytes (small evidence.py change)
G  manual last-resort wiring (CLI/API) + hard-bound
H  manual-mode 20% × 5 (separate policy, keep K-110)
I  feasibility uses SAFE (align with RM); optional runtime+min-model note
J  llama.cpp — NOT in this stage unless a later product decision
K  tests/docs throughout
L  physical acceptance on a new wheel — not this investigation
```

**Dependencies:** C → D, E; F can proceed in parallel with C once evidence
shape is known; G after F; H after G; I after C; A/B small and early;
J out of band.

---

## 21. Three depths (same V2 stage)

### Minimum viable

Replace doubling/25 GiB with the 64/128/256 tree; keep real writes; keep
FUSE distrust and RM. Prove a FUSE host can reach a **useful tier**
(32/48/64/…) or honestly `<16`. Persist enough that GET does not destroy
the result (minimum of F).

**Proves:** capacity-estimation algorithm matches the target tree.
**Defers:** incremental I/O, reserve file, manual UX, 20%×5, llama.cpp,
quota parsers.

### Minimum + a little depth (recommended)

Minimum plus: incremental growth, owned 1 GiB reserve file, incompressible
payload, first-class empirical records, split cheap/authorizing persist,
feasibility-vs-SAFE alignment, specialist-wins-when-bytes, Condition A
500 GiB suspicion on otherwise-trusted families.

**Proves:** physical RunPod can characterize beyond 25 GiB without
rewriting the tree from zero, survive EDQUOT, and not forget Sonar on
`kultrun host`.
**Defers:** mfsgetquota parser (K-105) unless the binary is present;
manual 20%×5; llama.cpp.

### Rabbit hole (same subsystem only)

K-102–K-108 parsers/adapters; ZFS credibility change; provider adapters;
adaptive timeouts; history of empirical runs; runtime+min-model
preflight; calibrated vLLM footprint. **Not** 1.6M serving features.

---

## 22. Test plan (target)

1. Trusted ext4 native authorizes; no Sonar.
2. FUSE huge native → UNRESOLVED → tree starts at 64.
3. Specialist bytes override native on FUSE (50 GiB vs 180 TiB).
4. Tree: 64s/128s/256s; 64s/128s/256f/192s; 64s/128f/96f→64; 64f/32s/48f→32; 64f/32f/16s/24s; 16f → `<16`.
5. Incremental extend; cleanup; owned reserve recovered after EDQUOT.
6. Timeout/permission → manual path, not fake tier.
7. Cheap GET does not clobber authorizing; mutation still invalidates.
8. K-110 unchanged; manual mode 20%×5 separately; no llama.cpp fake candidate.

---

## 23. Explicit non-goals

- Do not weaken SAFE or estimates to pass vLLM on 25 GiB proof.
- Do not implement llama.cpp/MLX in this V2 min.
- Do not merge into `kultrun`.
- Do not start Stage 1.6M.
- Do not rent another GPU for this investigation.
- Do not parse MooseFS in this docs task (K-105 remains OPEN).

---

## 24. Architectural risk

Not a global redesign. Bounded storage-capacity repair on existing
seams (CLASS B continues). Foundation/RM changes are small (SAFE vs
operational; optional preflight). Runtime adapters and catalog: only if
J is opened later. Persistence: yes, split observation vs authorization.
)