# Storage capacity truth — Stage 1.6L investigation

**Status:** INVESTIGATION ONLY. Not a stage brief. Not mergeable into Stream A,
Stream B, acceptance, or `kultrun`.

**Base:** acceptance freeze `34b068c01969d6f16ae1aa526a3ca4e9a88a57f4`
(`0.1.0+34b068c01969`).

**Physical contradiction:**

```text
Kultrun /workspace:
  reported 185.8 TiB free
  effective 64.0 GiB
  SAFE 57.6 GiB

Actual remaining writable on /workspace:
  ≈ 6.25 GiB then EDQUOT (errno 122)

vLLM 0.28.0 native realize:
  installer_failed / Disk quota exceeded
```

No production code was changed for this document.

---

# CURSOR PROPOSED INVESTIGATION PLAN

Written before any product edits (none were made).

## Initial hypotheses

1. **Measurement:** the 64 / 57.6 GiB figures are Stage 1.2 *policy
   disbelief bounds* for FUSE `statvfs`, not Storage Sonar and not project
   quota.
2. **Authorization leak:** `EMPIRICAL_EVIDENCE_NEEDED` still produces a
   numeric SAFE that later code treats as writable budget.
3. **Admission gap:** `kultrun runtimes realize` mutates storage without a
   storage requirement or reservation.
4. **Path/domain:** Kultrun-owned paths under `KULTRUN_STATE_ROOT` share one
   `/workspace` quota, while planning/acquisition may consult a *different*
   pool (`/` overlay) because they take the first resolved SAFE.
5. **Sizing:** final vLLM install size is not the peak extra bytes (pip
   cache + staging + unpack). Model `storage_bytes` is steady-state artifact
   size, not runtime+model+cache.
6. **Invalidation:** pip `EDQUOT` is stored as `installer_failed` and does
   not contradict the envelope.
7. **Sandbox distortion:** isolating `PIP_CACHE_DIR` onto `/workspace`
   increased peak on the constrained domain; product default pip cache may
   live elsewhere. That does not excuse the 57.6 vs 6.25 mismatch.

## Modules to inspect

- `capacity/policy.py`, `capacity/envelope.py`, `capacity/contracts.py`
- `storage/contracts.py`, `storage/sanity.py`, `adapters/storage/posix_reservation.py`
- `adapters/host/native_linux.py`, `host/discovery.py`, `host/contracts.py`
- `runtime/provision.py`, `runtime/contracts.py`, `runtime/selection.py`
- `adapters/provisioning/vllm_native.py`
- `model/acquisition.py`, `model/contracts.py`, `model/store.py`
- `adapters/acquisition/huggingface.py`
- `resource/manager.py`, `resource/snapshot.py`, `platform/admission.py`
- `planning/evaluate.py`, `platform/requirement.py`, `platform/available_models.py`
- `adapters/execution/native_process.py` (capture files, K-99)
- `docs/DEBT.md` K-24, K-26, K-27, K-28; `docs/design/EMPIRICAL-STORAGE-CHARACTERIZATION.md`

## Physical probes (read-only)

- Reuse the existing 6.25 GiB EDQUOT write probe. Do not refill the volume.
- `findmnt` / `df` / `statvfs` / quota tool inventory.
- Bounded top-level sizes of historical T3 trees. Abort if MooseFS `du` hangs.
- Do not delete `/workspace/kultrun-state*`. Do not retry realize.

## Additional Cursor-proposed evidence

- Reconstruct the 64 / 57.6 arithmetic from `policy.py` + the live defect line.
- Trace whether `StoragePool.quota_identity` is ever populated (it is not).
- Trace ResourceManager storage: `_safe_and_reserved("storage")` returns
  `(None, 0)`.
- Trace `deployment_capacity()` / `safe_storage()` first-pool selection.
- Distinguish posix_fallocate (1.2A probe) vs actual `write()` (the EDQUOT
  evidence). They may not observe the same constraint on MooseFS/FUSE.

## Destructive actions excluded

- No quota changes, no historical T3 deletion, no r4 sandbox, no vLLM retry,
  no product patches, no merges.

## Criteria for classifying the defect

| If… | Then… |
|---|---|
| 64 GiB is a policy cap, not measured quota | measurement concept incomplete |
| SAFE of an unverified pool authorizes writes | admission / SAFE semantics incorrect |
| realize has no storage preflight | provisioning admission missing |
| paths share one quota but capacity is one scalar / first pool | path/domain incomplete |
| pip EDQUOT does not stale the envelope | invalidation missing |
| sandbox cache is extra on the same domain | acceptance artifact, not root cause |

Expected overall: **combination** of incomplete measurement, incorrect SAFE
authorization, missing provisioning sizing/admission, and missing path→pool
binding.

---

# PLAN CHANGES MADE DURING INVESTIGATION

1. Confirmed Storage Sonar (Stage 2.2) is **not implemented** and was **not**
   the source of the `/workspace` figure.
2. Stage 1.2A storage sanity **exists** but runs only on explicit
   `kultrun storage sanity-check` (K-27). The physical T3 never invoked it.
3. Live GPU SSH later returned connection refused; further host probes were
   not repeated. Prior session evidence is retained as authoritative for
   EDQUOT, `statvfs`, and sizes already captured.
4. `posix_fallocate` was not the syscall that produced the 6.25 GiB bound.
   A real write probe did. That weakens “just enable 1.2A sanity” as the
   whole fix if FUSE fallocate is sparse or quota-blind.

---

# 1. Was `/workspace` capacity produced by Storage Sonar?

**No.**

Storage Sonar is a nickname for **Stage 2.2 empirical characterization**.
The design record states it is **not implemented**:

`docs/design/EMPIRICAL-STORAGE-CHARACTERIZATION.md`

The live `/workspace` numbers came from:

```text
OS/filesystem (os.statvfs)
  → NativeLinuxProvider mount facts (reported total/free)
  → HostDiscoveryService MountFacts
  → CapacityService._pool
       FUSE ∈ FAMILIES_REQUIRING_EVIDENCE
       effective = min(reported_free, UNVERIFIED_POOL_CEILING_BYTES=64 GiB)
       safe = withhold(effective, 10% or 5 GiB floor)
  → CapacityEnvelope.pools[].space  (LayeredBytes)
  → kultrun host / resources display
```

That is **not**:

```text
OS → Storage Sonar → HostProfile → CapacityEnvelope
```

### Exact call path

| Step | Location |
|---|---|
| `os.statvfs` | `src/kultrun/adapters/host/native_linux.py` (`f_bavail * f_frsize` → `free_bytes`) |
| Mount facts | `src/kultrun/host/contracts.py` `MountFacts` — “may be displayed, never authorizes” |
| Discovery | `src/kultrun/host/discovery.py` `_normalize_mounts` |
| Policy ceiling | `src/kultrun/capacity/policy.py` `UNVERIFIED_POOL_CEILING_BYTES`, `FAMILIES_REQUIRING_EVIDENCE` includes `"fuse"` |
| Envelope | `src/kultrun/capacity/envelope.py` `CapacityService._pool` |
| Display | `src/kultrun/main.py` `show_host` |
| Planning scalar | `src/kultrun/planning/evaluate.py` `deployment_capacity` — **first** pool with resolved SAFE |
| Snapshot scalar | `src/kultrun/resource/snapshot.py` `_storage_safe` — same first-pool rule |

### What Storage Sonar / 1.2A actually are

| Name | Stage | Implemented? | Used on this T3? |
|---|---|---|---|
| Storage Sonar (adaptive search to pool ceiling) | 2.2 | No | No |
| Storage sanity ladder (`posix_fallocate`, stops at policy ceiling) | 1.2A | Yes | **No** — K-27, operator-triggered only |
| Policy disbelief cap 64 GiB | 1.2 | Yes | **Yes** — this is the 64 / 57.6 figure |

`kultrun storage sanity-check <mount>` is the only product command that
would run a genuine reservation. `kultrun host` / `runtimes realize` only
**look up** stored evidence (`_stored_sanity` is documented as “a lookup,
never a probe”).

---

# 2. Reconstruct 64.0 GiB EFFECTIVE and 57.6 GiB SAFE

Physical defect line (T3 r3):

```text
pool /workspace reports 204241294983168 bytes free
but only 68719476736 is treated as effective: empirical_evidence_needed
```

### RAW INPUT(S)

```text
filesystem_type = fuse          # /proc/mounts; device mfs#us-ks-2.runpod.net:9421
reported_free   = f_bavail * f_frsize
                = 204_241_294_983_168 B   # 185.756… TiB
reported_total  = f_blocks * f_frsize     # cluster-sized (~873 T displayed)
```

`statvfs` here is **cluster/backing free**, not project quota. Generic
`statvfs` **cannot see** this quota. No `mfsgetquota` binary was present.
`quota` / `repquota` produced nothing. Authoritative quota interface:
**unavailable in-session**.

### NORMALIZATION

```text
family = "fuse"
fuse ∈ FAMILIES_REQUIRING_EVIDENCE
requirement = EMPIRICAL_EVIDENCE_NEEDED
sanity_status = NOT_CHECKED          # sanity never run
confidence = LOW
```

### EFFECTIVE

```text
ceiling   = UNVERIFIED_POOL_CEILING_BYTES = 64 * 1024³ = 68_719_476_736
effective = min(reported_free, ceiling) = 68_719_476_736   # 64.0 GiB
```

Policy comment (verbatim intent): this is **not a claim about the pool** —
it is a bound on how much may be believed having verified nothing (K-24).

### SAFETY → SAFE

```text
reserve = max(int(effective * 0.10), STORAGE_RESERVE_FLOOR_BYTES)
        = max(6_871_947_673, 5_368_709_120)
        = 6_871_947_673                 # 10% wins over 5 GiB floor
SAFE    = effective - reserve
        = 68_719_476_736 - 6_871_947_673
        = 61_847_529_063                # 57.6 GiB
```

### Why these values appeared

Milestone 1 policy for “network FS advertises petabytes.” Same class of
failure as the previous attempt (“239 TB free” then a 6.70 GiB install
could not complete) — recorded in `native_linux.py`, `policy.py`, and
`EMPIRICAL-STORAGE-CHARACTERIZATION.md`. The 64 GiB cap **stopped Kultrun
believing 185 TiB**. It **did not** stop Kultrun treating 57.6 GiB as
writable.

Overlay `/` on the same host (credible local family):

```text
reported ≈ 26.2 GiB free
effective = reported                    # overlay ∈ FAMILIES_WITH_CREDIBLE_SIZE
reserve   = max(10% of 26.2 GiB, 5 GiB) = 5 GiB
SAFE      ≈ 21.2 GiB
```

---

# 3. What REPORTED actually means

| Concept | Did Kultrun distinguish it? | This host |
|---|---|---|
| Backing-cluster capacity | Displayed as reported total | ~873 T MooseFS |
| Mount free (`statvfs` `f_bavail`) | Displayed as reported free; never supposed to authorize | 185.8 TiB |
| Project / user / directory quota | Contract field `StoragePool.quota_identity` exists; **never populated**; no adapter | ~ existing_used + 6.25 GiB writable |
| Writable remaining | Not observed except via accidental installer `write`/`EDQUOT` | 6.25 GiB |
| State-root budget | No | — |
| Operator-configured bound | Only the global 64 GiB FUSE ceiling | 64 GiB |

Kultrun **does** distinguish reported vs effective vs safe **as layers**.
It **does not** distinguish cluster-free vs namespace quota. On this
filesystem those are different by **~four orders of magnitude**.

---

# 4. Can the current sensor see the quota?

**No. `os.statvfs` cannot see this project quota.**

It returned ~186 TiB free while writes failed at +6.25 GiB.

- No RunPod/MooseFS quota CLI on the pod.
- 1.2A `posix_fallocate` was not exercised; even if it were, FUSE often
  accepts fallocate without charging quota (legacy note: `st_blocks=0`
  after “successful” reservation). The **authoritative physical bound we
  have** is a real `write()` loop hitting `errno 122`.

Do not design the product around “statvfs will become truthful.”

Detection order (recommended):

1. OS/FS quota interface if present (`quota`, XFS project, etc.).
2. Filesystem/provider adapter (MooseFS/LizardFS/RunPod metadata).
3. Orchestrator/cloud metadata when authorized.
4. Explicit operator/admin bound (per pool / per state-root).
5. Conservative **transaction-sized** empirical reservation — real
   allocation, not sparse; **not** a 64 GiB ceiling climb.
6. If none of the above: `UNKNOWN` / `quota_not_observable`. **Unknown
   must not authorize multi-gigabyte mutation.**

---

# 5. Path ownership and quota domains

Physical T3 r3 sandbox (all under `/workspace` unless noted):

| Logical purpose | Actual path | Mount | Same quota as /workspace? | Persistent? | Kultrun-owned? | In capacity accounting? |
|---|---|---|---|---|---|---|
| State root | `$KULTRUN_STATE_ROOT` = `…/state` | /workspace | yes | yes | yes | only as “some pool exists” |
| Runtime staging | `state/runtimes/.staging/rinst_*-N` | /workspace | yes | transient | yes | no |
| Runtime final | `state/runtimes/vllm/0.28.0/rinst_*` | /workspace | yes | yes | yes | no |
| Pip cache (this acceptance) | `$PIP_CACHE_DIR` = `…/cache/pip` | /workspace | **yes (sandbox)** | optional cache | **sandbox, not product** | no |
| HF cache | `$HF_HOME` = `…/cache/huggingface` | /workspace | yes (sandbox) | cache | sandbox env | no |
| Model staging | `state/models/staging/<id>` | /workspace | yes | transient | yes | via model peak vs first-pool SAFE |
| Model artifact | `state/models/artifacts/<id>` | /workspace | yes | yes | yes | `ModelRequirement.storage_bytes` is catalog estimate |
| Temp | `$TMPDIR` = `…/tmp` | /workspace | yes (sandbox) | transient | sandbox env | no |
| Telemetry | `state/telemetry/*.sqlite3` | /workspace | yes | yes, bounded-growth | yes | no |
| Exec capture | `tempfile.mkstemp` then unlink | TMPDIR or `/tmp` | sandbox: workspace; default product: often overlay `/tmp` | unbounded while child lives (K-99) | executor | no |
| Product venv | `…/venv` | /workspace | yes | yes | acceptance install | no |
| Overlay OS | `/`, `/root/.cache` | overlay 30G | **different domain** | mixed | no | `/` is a separate envelope pool |

**They share one quota domain** whenever acceptance isolation points them
at `/workspace`. Historical T3 trees (`/workspace/kultrun-state`,
`…-16L-r2`) consume **the same** quota and were correctly not reused — but
they still reduce remaining writable bytes. Capacity **does not subtract
them** (K-26: envelope is not occupancy).

First-class `StorageDomainId` does **not** exist in running code.
`StoragePool` exists as a contract and is **never constructed** in `src/`
outside its definition. Live capacity uses `PoolCapacity` keyed by
`mount_point` only. `quota_identity` is unused.

Planning/acquisition then collapse all pools to **one scalar**: the first
pool with resolved SAFE. On this host that is almost certainly **`/`
(21.2 GiB)**, not `/workspace` (57.6 GiB) — while every Kultrun write of
interest went to `/workspace`.

---

# 6. Runtime provisioning sizing

`RuntimeProvisioningPlan` has **no** estimated final, transient, or
working-space bytes and **no** target storage domain
(`src/kultrun/runtime/contracts.py`).

`ProvisioningService.provision` (`runtime/provision.py`): persist
INSTALLING → create staging venv → `pip install vllm==0.28.0` → metadata
probe → `staging.replace(final)` (rename on same FS) → INSTALLED.

**There is no storage preflight. There is no storage reservation.**

> Runtime provisioning currently mutates storage without prior physical
> storage admission.

Promotion peak: `Path.replace` on the same filesystem is a rename, so
**staging + final do not coexist** on success. Failure `_cleanup(staging)`
drops the incomplete env. Pip cache is **not** cleaned.

### Evidence-based sizes (this host family)

| Item | Bytes / notes |
|---|---|
| Pip cache during failed r3 realize | **5.8 GiB** (`…/cache/pip`) |
| Incomplete staging at ~4 min | **~1.8 GiB** then deleted on fail |
| Failed sandbox total | **~6.9 GiB** |
| Remaining writable after that | **6.25 GiB** then EDQUOT |
| Prior successful state root `/workspace/kultrun-state` | **~23 GiB** top-level `du` |
| Of which `models/` | **6.0 GiB** |
| Prior r2 `models/` | **6.0 GiB** |
| Product venvs `/workspace/opt/kultrun*` | **351 MiB** each (not vLLM) |
| Typical complete native vLLM 0.28 + CUDA wheels | **on the order of 8–15 GiB** persistent (not precisely measured; MooseFS recursive `du` on `runtimes/` hung) |

```text
FINAL_PERSISTENT_BYTES        ≈ 8–15 GiB  (vLLM env; not proven to the byte)
PEAK_TRANSIENT_BYTES          ≈ staging unpack (same order as final) + pip cache
PEAK_TOTAL_ADDITIONAL_WRITABLE
  product-default pip cache on overlay:
      ≈ final/staging on /workspace  (8–15 GiB)  → still > 6.25 GiB
  acceptance PIP_CACHE_DIR on /workspace:
      ≈ 5.8 GiB cache + staging growth → EDQUOT even earlier
```

Final size ≠ required free at start. Cache + unpack must be counted.

---

# 7. Why 5.8 GiB pip cache

`VllmNativeProvisioner` runs `python -m pip install --report … vllm==0.28.0`
with **no** `--no-cache-dir`. It does not set `PIP_CACHE_DIR`.

Pip therefore uses the environment. The acceptance sandbox **forces**
`PIP_CACHE_DIR` onto the same `/workspace` quota as the install.

Wheels for torch / nvidia / vllm easily total ~5–8 GiB. Cache **duplicates**
bytes that also unpack into `site-packages`. It **survives** a failed or
successful install. Kultrun does **not** own or clean it.

**Product vs sandbox:** a commercial install without that env var typically
caches under `~/.cache/pip` (here `/root/.cache`, overlay). That moves cache
**off** the network-volume quota onto the 30G container layer. The sandbox
therefore **increased /workspace peak** relative to default pip. It also
**revealed the true clean-namespace cost** of “everything Kultrun touches
lives in one operator-controlled tree.”

Recommended policy (not implemented):

- Treat pip download cache as **temporary installation cache**, not an
  authoritative artifact.
- Product should **bound** it (dedicated dir under the target pool or
  `--no-cache-dir` when the target pool is the scarce domain).
- Do **not** silently delete a global shared cache as a hidden capacity
  mechanism.
- After successful atomic promotion, deleting **Kultrun-owned** install
  cache is safe; deleting `~/.cache/pip` is not.

---

# 8. Model acquisition sizing

Catalog 7B AWQ (`qwen2.5-7b-instruct-awq`):

```text
storage_bytes = 5.4 GiB     # ModelRequirement: "steady-state size once installed"
peak_additional_bytes = 12.0 GiB  # "most additional storage during acquisition"
```

Physical prior artifact was ~5.58 GB — consistent with `storage_bytes`,
not with peak.

`needed_bytes()` uses **peak if known, else storage**. Acquisition
**does** preflight `needed <= SAFE` (`model/acquisition.py`). That is a
static comparison to envelope SAFE, **not** a ResourceManager reservation.

Hugging Face `snapshot_download(..., local_dir=staging)` plus default Hub
cache (`HF_HOME`) can **duplicate** download bytes (cache + staging) before
promotion. Adapter then deletes `staging/.cache` only. Hub cache remains.

`incremental_storage_demand` is **0** if an exact STORED artifact already
exists — correct for re-use, silent about runtime install cost.

`ModelRequirement.storage_bytes` does **not** mean runtime+model+cache or
peak provisioning.

---

# 9. Full Stage 1.6L storage bill (this class of host)

| Item | Class | Order of magnitude | Counted today? |
|---|---|---|---|
| Kultrun app venv | PERSISTENT | ~0.1–0.4 GiB | no |
| vLLM final env | PERSISTENT | ~8–15 GiB | **no** |
| Runtime staging | TRANSIENT | ~same as final until rename | no |
| Pip cache | OPTIONAL_CACHE | ~6 GiB if on this domain | no |
| Model artifact 7B AWQ | PERSISTENT | ~5.4–6 GiB | catalog `storage_bytes` |
| Model download/staging | TRANSIENT | up to ~12 GiB catalog peak; may duplicate HF cache | peak vs first-pool SAFE |
| HF hub cache | OPTIONAL_CACHE | can rival artifact | no |
| Telemetry SQLite | BOUNDED_GROWTH | small | no |
| Exec capture (K-99) | UNBOUNDED/DEBT | unlinked inode until process exit | no |
| Historical other sandboxes | PERSISTENT occupancy | tens of GiB on same quota | **no** (K-26) |
| Policy reserve | — | 10% or 5 GiB | applied to **wrong** effective |

Peak additional for a **clean** 1.6L vertical on one domain, conservative:

```text
vLLM peak (staging+cache)     12–20 GiB
model peak                    12 GiB  (if not already stored)
overlap if sequential         take max then sum after recalculate
headroom/logs                 ≥ 5 GiB floor already in policy
```

On **6.25 GiB** remaining, **neither** a clean vLLM realize **nor** a 12 GiB
model peak fits. A host with a leftover 6 GiB model and leftover vLLM env
from a *previous* tree can still *serve* — that is occupancy, not this
sandbox’s remaining quota.

---

# 10. Current admission flow

| Question | Answer |
|---|---|
| Storage checked before `runtimes realize`? | **No** |
| Storage reserved before realize? | **No** |
| Storage checked before model acquire? | **Yes** — peak vs envelope SAFE (wrong number / possibly wrong pool) |
| Storage reserved in ResourceManager before acquire? | **No** |
| Fresh capacity after provision/acquire? | Envelope is derived on each `compute()` from **new statvfs**, still quota-blind; no occupancy subtract; EDQUOT does not persist a contradicted bound |
| ResourceManager storage dimension | `request_from_plan` sets `incremental_storage_bytes=NOT_PROVIDED`. If it were set, `_safe_and_reserved("storage")` returns `(None, 0)` → UNRESOLVED. **Storage is not actually admitted.** |
| Foundation selection vs storage | **No** storage in `FoundationSelectionService` |
| Inference reservation | RAM/VRAM only |

---

# 11. Root cause (overall classification)

**Combination. Not acceptance-only. Not a provisioner pip bug.**

| Axis | Verdict |
|---|---|
| Measurement | Incomplete: `statvfs` cluster-free + 64 GiB disbelief cap. Quota invisible. |
| SAFE semantics | **Incorrect for authorization:** LOW-confidence unverified effective still yields numeric SAFE. Policy text says it is not a pool claim; consumers treat it as writable. |
| Sizing | Runtime plan has **zero** storage requirement. Model storage is artifact-only. Peak ≠ final. |
| Admission | Realize has none. Acquire checks the wrong quantity. ResourceManager storage is a stub. |
| Path/domain | All writes share `/workspace` quota; planning uses first SAFE pool (`/` overlay). `StoragePool` unused. Occupancy of sibling trees ignored. |
| Invalidation | `EDQUOT` → `installer_failed`. Envelope still advertises 57.6 GiB. |
| Architecture | Reported/effective/safe layers and 1.2A probe **design** are good. They are **not wired** to mutations, quota, or path ownership. |
| Acceptance sandbox | Useful isolation; pip cache on `/workspace` raised peak. Would still EDQUOT on staging alone (~8–15 GiB > 6.25 GiB). |

---

# 12. Architecture critique

### What is currently good?

- Reported / effective / safe are distinct; reported never *supposed* to
  authorize.
- FUSE/NFS/etc. are not trusted as local disks (allow-list).
- Unknown ≠ zero (`_withhold` returns NOT_MEASURED if reserve eats all).
- Envelope is derived, not persisted (avoids one class of stale bytes).
- 1.2A already classifies `EDQUOT` vs `ENOSPC` vs unsupported; only the
  first two bound capacity.
- Model acquisition already has a SAFE preflight and peak vs stored split.
- Staging + rename promotion is the right persistent-install shape.
- Design docs already name this exact failure mode (petabyte `df`, 6.70 GiB
  install).

### What is merely incomplete?

- K-24 64 GiB ceiling as a Milestone 1 stand-in for Stage 2.2.
- K-27 sanity is manual.
- K-26 occupancy not subtracted.
- `quota_identity` field with no producer.
- Runtime version pins without size recipes.
- Telemetry does not record quota provenance or EDQUOT as capacity facts.

### What is incorrectly modeled?

- **Unverified belief cap is labeled EFFECTIVE and then SAFE**, which other
  domains interpret as “Kultrun can write this many bytes.”
- **Storage is one scalar** (first pool) for planning.
- **ResourceManager claims storage on the reservation record** but cannot
  evaluate pool SAFE.
- **Installer OSError is treated as provisioner failure**, not capacity.

### What is coupled incorrectly?

- Display, planning feasibility, acquisition preflight, and (missing)
  provision preflight all share `LayeredBytes.safe_bytes` without a
  “may this number authorize a mutation?” flag or per-path pool.
- `FAMILIES_REQUIRING_EVIDENCE` still emits a number that authorizes.

### What is missing?

- Path → pool / quota domain.
- Runtime `StorageRequirement` (persistent + peak + domain).
- Mutation admission before realize.
- Quota observation / UNKNOWN-not-unlimited rule for writes.
- EDQUOT feedback into envelope.
- Recalculation after storage mutations (provision, acquire, delete, fail).

### What can be fixed locally? (not “locally” as in one file — locally as in
one domain)

- Capacity: unverified pools must not emit authorizing SAFE.
- Provision: estimate + preflight.
- ResourceManager: implement storage against the pool that owns the path.
- Acquisition: compare to **target path’s** pool, not first SAFE.

### What requires architectural change?

- Treating storage as path-scoped domains with requirements and
  reservations **before** inference. This is still the existing
  `storage` + `capacity` + `resource` ownership if we **use** `StoragePool`
  and stop collapsing it.

### What should explicitly NOT be changed?

- Do not implement Stage 2.2 ceiling-climbing sonar behind `kultrun host`.
- Do not probe RAM/VRAM destructively.
- Do not trust sparse `truncate` as evidence.
- Do not make `statvfs` authorize.
- Do not delete customer/historical trees as a capacity strategy.
- Do not rename reported/effective/safe layers; fix what SAFE means when
  evidence is missing.
- Do not invent `StorageDomain` as a synonym for `StoragePool` unless a
  quota boundary is **not** a mount (then `quota_identity` on the pool is
  the smaller step).

---

# 13. Proposed models (design only)

## Capacity / domain

Keep `StoragePool` (mount + `quota_identity` + fingerprint). Add **path
ownership**: each Kultrun-managed tree names its pool.

For unverified network pools:

```text
reported_bytes     = statvfs (display)
effective_bytes    = UNKNOWN unless
                     credible local FS OR quota API OR operator bound
                     OR verified_lower_bound from a genuine reservation
safe_bytes         = withhold(effective) only when effective is known
capacity_status    = UNKNOWN | BOUNDED | AUTHORITATIVE
source             = statvfs | quota | operator_bound | measured_failure | sanity
confidence         = LOW when source is statvfs on FUSE
```

Unknown ≠ unlimited: storage-consuming mutations are **UNRESOLVED /
blocked**, with an explainable reason, unless an operator bound or
transaction probe supplies a number.

Do **not** put 64 GiB in SAFE. Keep 64 GiB as `unverified_belief_ceiling`
for display and as the **max** a probe may ever attempt, not as writable.

## Requirement

Per operation, per domain:

```text
persistent_bytes
peak_transient_bytes
cache_bytes            # optional; policy may exclude from required_free
reserve_bytes          # policy, not a guess
required_free_bytes    = peak_transient + reserve
                       # or persistent+cache+reserve if cache is on-domain
target_storage_pool
```

Runtime provisioning and model acquisition each have one (or two, if cache
is a second pool).

## Admission

Before realize and before acquire: ResourceManager (extended) or the
mutating service **must** ask the pool that owns the destination path.

Preferred: **one authority** (ResourceManager) with workload types
`RUNTIME_PROVISIONING` and `MODEL_ACQUISITION` (plus existing EVALUATION /
INFERENCE). Short-lived storage reservations released after success/fail.
Do not create a second muteable storage czar.

Optional transaction probe: `posix_fallocate` **or** bounded real write if
fallocate is quota-blind — sized to `required_free_bytes`, **not** 64 GiB.

After EDQUOT/ENOSPC: persist `StorageSanityEvidence` CONTRADICTED with
`observed_failure_upper_bytes`, mark capacity stale, refuse retry until
rediscovery. Normalize `STORAGE_QUOTA_EXCEEDED` / `INSUFFICIENT_STORAGE`
while keeping installer detail.

## Recalculation graph

```text
quota/operator bound/observed EDQUOT
  → rediscover host storage facts
  → recompute envelope (SAFE may become UNRESOLVED or lowered)
  → runtime/foundation feasibility (storage cost of materializing the runtime)
  → provision only if admitted
  → rediscover
  → verify runtime
  → model eligibility + requirements vs current available
  → Available Models
  → selection / DeploymentPlan
  → acquire if needed (admit storage)
  → rediscover
  → RAM/VRAM ResourceRequest
  → deploy
```

If corrected SAFE shrinks, **do not** keep the previous model or foundation
choice. Recompute. Storage cost of vLLM vs llama.cpp belongs in foundation
feasibility later; today only vLLM is the 1.6L vertical, so the honest
outcome on this host is **vLLM cannot be provisioned into this sandbox**,
not “pick another runtime we have not built.”

## Cache

| Cache | Policy |
|---|---|
| Pip install cache | Temporary; Kultrun-owned dir on the target pool or disabled when that pool is scarce; clean after successful promote of **that** install |
| HF hub cache | Optional reusable; must be on a known pool; never confused with ModelArtifact |
| ModelArtifact | Authoritative stored object; delete only via product delete |
| Exec capture | Bound/rotate (K-99); not a capacity lever |
| Unsafe auto-cleanup | Other users’ `~/.cache`, historical T3 roots, unrelated `/workspace` data |

## Headroom

Keep 10% vs 5 GiB floor **once effective is a real writable number**. Do not
invent a new percentage. Apply it to the **quota domain being written**,
and keep separate small reserves in mind for telemetry/logs (today
dominated by the 5 GiB floor on small pools).

## Explainability (target)

```text
vLLM 0.28.0 native install needs approximately
  ~X GiB persistent and ~Y GiB peak workspace on pool /workspace
  (quota not observable via statvfs; last measured writable remaining ~6.25 GiB).

Kultrun SAFE writable on that pool is UNRESOLVED or 6.25 GiB (measured upper
failure), not 57.6 GiB.

This runtime cannot be provisioned on this configuration.
Remediation: free space on this volume, raise the project quota, or choose
a pool with sufficient verified writable capacity.
```

Better than `pip failed: Disk quota exceeded`.

---

# 14. Acceptance sandbox review

**Useful.** It proved a logically fresh namespace still hits the **same**
quota and that clean-install peak is large.

**Distorted:** `PIP_CACHE_DIR`/`HF_HOME`/`TMPDIR` on `/workspace` put caches
on the scarce domain. Default product pip cache might have used overlay.

**Did not cause the bug:** staging vLLM onto `/workspace` with 6.25 GiB left
fails regardless.

**Managed Paths:** Kultrun should declare which paths it owns and which
pool they consume. The sandbox accidentally simulated that declaration.
The product does not have it.

Do not weaken sandbox isolation. Do make the product aware of the same
mapping.

---

# 15. Testing strategy

### T0

- FUSE `statvfs` huge free → effective ceiling is **not** authorizing SAFE.
- `required_free_bytes` composition (persistent + peak + reserve) per pool.
- Path → pool mapping; two paths one quota; two pools not summed.
- EDQUOT invalidates envelope; retry blocked until rediscover.
- Realize refuses when SAFE UNRESOLVED.

### T1 fixtures

- Credible ext4: `statvfs` free is effective.
- Fake `statvfs` petabyte + EDQUOT on write/fallocate.
- Two paths one quota domain.
- Distinct overlay vs workspace pools; mutation to workspace must not use
  overlay SAFE.
- Quota UNKNOWN.
- Replay `StorageSanityEvidence` CONTRADICTED lowering effective.

### T2

- Controlled fake provisioner that would write if admitted.
- Insufficient capacity: **no** large download starts.
- After simulated success/fail, next envelope is not the pre-mutation SAFE.

### Deterministic EDQUOT without RunPod

Prefer in this order:

1. In-process `StorageSanityProbe` returning `QUOTA_EXCEEDED` (already
   patterned in `tests/test_storage_sanity.py`).
2. Linux `user`/`project` quota on a loopback ext4 in CI where privileged.
3. Fault-injection wrapper around reservation/write in the provisioner port.

Do not require a commercial volume for regression. T3 remains the only
place `statvfs` lie vs quota is proven on MooseFS-class FUSE.

### T3 (later, not this task)

Same GPU/volume class: reported cluster-free ≠ SAFE writable; realize
refuses with explainable insufficient storage **before** pip.

---

# 16. Change depth

**Necessary: L2** (cross-domain rewiring), with an L1 capacity-semantics
fix as step 1.

| Level | What | Do it? |
|---|---|---|
| L0 | Wrong stat call | No — `statvfs` is the right reported sensor |
| L1 | Unverified pool SAFE → UNRESOLVED; quota source/confidence; path→pool | **Yes, first** |
| L2 | Runtime storage requirement; admit realize; acquire uses destination pool; EDQUOT invalidation; recompute Available Models | **Yes, required for truthful 1.6L** |
| L3 | New StorageDomain/StorageReservation taxonomy | **No for this bug.** Deepen `StoragePool` + ResourceManager storage. Full sonar remains Stage 2.2 |

Minimal safe implementation: L1 SAFE semantics + realize preflight against
destination pool + persist contradicted bound on EDQUOT.

Deeper follow-up: foundation storage cost, operator UI, provider quota
adapters, K-99 capture caps.

Rabbit holes: 48-minute pool-ceiling sonar; deleting historical T3 to
“make numbers nicer”; treating overlay 27 GiB as `/workspace` quota.

---

# 17. Implementation sequence (recommended)

Owner: **Stream A** (capacity, storage, runtime, resource, planning, model
acquisition preflight). Stream B only if new telemetry columns for quota
provenance are required for acceptance — otherwise later.

Proposed implementation branch: `stage/1.6L-storage-capacity-truth`
from Stream A freeze `6ed042222bea7bdbc48244475597860e01bf0c4a`.
Re-integrate onto a new acceptance line after Stream A review. Do **not**
commit fixes on `investigation/1.6L-storage-capacity-truth`.

```text
1. Capacity: unverified network pool does not emit authorizing SAFE
   (display belief-ceiling separately).
2. Bind Kultrun-owned paths to pools (state root / runtimes / models).
3. ResourceManager: evaluate storage against that pool (stop returning None).
4. RuntimeProvisioningPlan: persistent + peak + target pool (recipe/estimate,
   conservative, versioned).
5. Preflight/reserve before realize; transaction-sized genuine reservation
   if SAFE is UNRESOLVED but operator allows probe; else block.
6. On EDQUOT/ENOSPC: CONTRADICTED evidence, stale, typed error, no silent retry.
7. Rediscover after provision success/fail.
8. Acquisition: SAFE of destination pool; peak includes Hub cache if on-domain.
9. Rediscover after acquire.
10. Available Models / selection / plan consume new envelope.
11. Tests T0/T1/T2 as above.
12. Physical T3 only after (1)–(11): prove refusal or success against
    real writable remaining, not 57.6 GiB.
```

Regression gates: existing capacity, storage sanity, acquisition, runtime
provision unit tests. Physical gate: do not claim L3 1.6L until realize
either admits truthfully or refuses truthfully on a quota-constrained
volume.

---

# 18. Versioning / branch plan

| Ref | SHA | Action |
|---|---|---|
| Stream A | `6ed042222bea7bdbc48244475597860e01bf0c4a` | **Do not modify** |
| Stream B | `792b0ea336112cab33b0e67d7fd1d2f2c5f0595a` | **Do not modify** |
| Acceptance | `34b068c01969d6f16ae1aa526a3ca4e9a88a57f4` | **Do not modify** |
| `kultrun` | `1e51f13ec2a7c2e1fa34b6a3ec0c92f712d4b43e` | **Do not modify** |
| Investigation | `investigation/1.6L-storage-capacity-truth` from 34b068c | docs only |
| Safety tags | `safety/investigation-base-acceptance-34b068c` | created, not moved |
| | `safety/investigation-base-stream-a-6ed0422` | created, not moved |
| | `safety/investigation-base-stream-b-792b0ea` | created, not moved |

Rollback: delete investigation branch/worktree; frozen tags remain.

Acceptance rebuild: only after a reviewed Stream A storage-truth freeze,
new integration wheel, new SHA. Never rebuild 34b068c in place.

---

# 19. Correct product behavior on the current host

If this were a customer’s clean Kultrun install **today**, before pip:

Kultrun should have concluded:

```text
/workspace is a FUSE network volume.
statvfs free (185.8 TiB) is not entitlement.
No quota API, no operator bound, no sanity evidence.
SAFE writable on the state-root pool is UNKNOWN / not authorizing.
vLLM 0.28.0 native materialization needs more than ~6 GiB additional
writable bytes on that pool (conservative peak ≫ remaining).
Therefore: do not start installer mutation.
User-facing: ENVIRONMENT / storage inadequate for this runtime on this
volume, with X vs Y when Y is known, or “quota not observable — refusing
to guess.”
```

**Should vLLM provisioning have begun? No.**

Correct reason: **insufficient or unobservable writable capacity on the
pool that owns the runtime installation**, not “pip crashed.”

Asking the customer to raise quota is acceptable **only after** that
conclusion is produced. Raising quota to make a lying SAFE look true is
not product capacity management.

### After the fix, if capacity *is* sufficient

```text
rediscover host + pools + quota/operator/measured bounds
→ SAFE only from authorizing sources
→ runtime feasibility including storage requirement
→ select foundation (today: vLLM if storage admits; else stop)
→ admit/reserve provisioning storage on the destination pool
→ provision
→ rediscover (occupancy changed)
→ verify
→ model feasibility vs remaining
→ admit/reserve acquisition storage
→ acquire / reuse STORED
→ rediscover
→ Available Models → select → plan
→ RAM/VRAM ResourceRequest
→ instance start → READY → infer
```

---

# 20. Open decisions (Daniel / architecture review)

1. **Authorizing SAFE for unverified FUSE:** always UNRESOLVED until
   quota/operator/probe, vs keep a tiny conservative default (not 64 GiB).
   Recommendation: UNRESOLVED for mutation; display belief-ceiling.
2. **Transaction probe primitive on MooseFS-class FUSE:** `posix_fallocate`
   vs bounded real write. Need one T3 experiment later; do not assume
   1.2A fallocate sees EDQUOT.
3. **Pip cache location:** product-owned under state root vs default
   `~/.cache/pip` (different domain). Affects peak bill.
4. **Whether Stream B telemetry provenance is in the first freeze** or
   deferred.

No other blockers. Do not implement until this investigation is reviewed.
