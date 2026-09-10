# Stage 1.6L — Storage capacity truth (bounded L2)

**Milestone 1 — Walking skeleton (storage correction, not stage close).**

Status: **OPEN — implementation on `stage/1.6L-storage-capacity-truth`. Not
merged. Not deployed. Does not close Stage 1.6L. Does not start 1.6M.**

Base: Stream A `6ed042222bea7bdbc48244475597860e01bf0c4a`
(`stage/1.6L-real-vllm-inference`).

Investigation consumed:
`docs/investigations/STORAGE-CAPACITY-TRUTH-1.6L.md` at
`a5ebd4168d7ff05e110e13fc7d909c935b0c7246`.

This stage does not reopen Stages 1.2–1.6K. It corrects storage truth,
managed ownership, truthful admission, and recomputation so that a later
physical T3 cannot authorize a `/workspace` write from a FUSE heuristic or
from the overlay root's SAFE figure.

```text
CURRENT STAGE                Storage Sonar v1 + managed ownership +
                             truthful per-pool storage admission.
PREDECESSOR OUTPUTS          Stream A 1.6L capture-lifetime HEAD 6ed0422.
                             Investigation a5ebd41 (evidence only).
THIS STAGE'S REQUIRED OUTPUT Dual ownership; StoragePool/quota binding;
                             native+probe+Sonar evidence; ResourceManager
                             storage admission before mutation; EDQUOT/
                             ENOSPC contradiction; 30% real replan.
CORE CONTRACTS AFFECTED      storage.* evidence/ownership; resource
                             storage commitments; optional fields on
                             RuntimeProvisioningPlan / ResourceRequest.
ADAPTERS AFFECTED            storage probes (POSIX, Linux quota, MooseFS
                             optional, Windows/macOS contracts); Sonar
                             real-write; vLLM pip --no-cache-dir.
PERSISTED STATE              ownership registry records; local
                             .kultrun-owner.json at managed roots.
MUTATION / FAILURE BOUNDARY  No large install/download before storage
                             admission. Heuristic 64 GiB is not SAFE.
CANCELLATION / CLEANUP       Owned disposable staging only. Sonar probe
                             files cleaned. Legacy unlabeled never auto-
                             deleted.
```

---

# IMPLEMENTATION REVIEW

Recorded **before** production behavior changes.

## Conclusions confirmed

1. `/workspace` 64.0 GiB EFFECTIVE / 57.6 GiB SAFE is Stage 1.2 FUSE
   policy disbelief (`min(statvfs, 64 GiB)` then withhold), **not**
   Storage Sonar. Sonar (Stage 2.2 ceiling search) is not implemented.
2. `os.statvfs` on MooseFS/FUSE reports cluster free, not project quota.
   Generic `statvfs` cannot see that quota.
3. `RuntimeProvisioningPlan` has no storage sizes.
   `ProvisioningService.provision` mutates with no storage admission.
4. Acquisition preflights SAFE, but `safe_storage` / `deployment_capacity`
   take the **first** pool with resolved SAFE (typically overlay `/`), not
   the destination `/workspace` quota domain.
5. ResourceManager `_safe_and_reserved("storage")` returns `(None, 0)`.
   `incremental_storage_bytes` is `NOT_PROVIDED`. RM is not the storage
   authority in practice.
6. `StoragePool.quota_identity` exists and is unused. `StoragePool` is
   never constructed on the live path. Do **not** invent `StorageDomain`.
7. EDQUOT (errno 122) is reported as `installer_failed`. The envelope is
   not contradicted. The previous SAFE figure remains advertised.
8. Pip cache on the physical T3 was unmanaged (~5.8 GiB) because the
   sandbox pointed `PIP_CACHE_DIR` at `/workspace`. Product default can
   still leak to `~/.cache/pip` on overlay.
9. Stage 1.2A `posix_fallocate` sanity is operator-only (K-27) and was
   not run. FUSE fallocate can be quota-blind; real `write()` is what
   surfaced EDQUOT.

## Conclusions refined

1. **Sonar v1 is not Stage 2.2 ceiling-climbing.** It is an
   operation-targeted real-write fallback: prove
   `min(planned_peak, max_empirical_probe_bytes)` with actual data
   writes. 25 GiB is a probe **budget**, never `available = 25 GiB`.
2. **Unverified FUSE SAFE must be unresolved.** The 64 GiB ceiling remains
   a **belief bound** on effective/display. It does not authorize. This
   is a deliberate change to Stage 1.2 authorizing semantics, not a
   silent reinterpretation of `LayeredBytes.safe_bytes`.
3. **Compatible specialist probes always run on the mutation path**, not
   on GET `/host`. CapacityService remains a read: it consumes
   already-gathered `StorageCapacityEvidence` and never probes.
   That preserves “a capacity read must not allocate storage.”
4. **K-27 is refined, not fully retired.** Operator-triggered 1.2A
   sanity remains. Mutation paths now gather specialist/Sonar evidence
   synchronously and boundedly. No background daemon probe.
5. **Ownership is dual (local marker + registry) at managed-root
   granularity**, not per-file. Path/name matching never authorizes
   deletion. Legacy unlabeled state is inventoried, never auto-deleted.
6. **Runtime cannot import resource or capacity.** Storage admission is
   orchestrated by `platform`. Runtime may import `storage` (tier 2) to
   size requirements, write markers, and normalize errno.
7. **Model cannot import resource.** Acquisition destination-pool
   preflight stays; ResourceManager admission is composed in platform.
8. **No new mandatory third-party dependency.** No psutil. MooseFS
   tools optional/read-only. Windows/macOS native adapters are
   ctypes/stdlib behind the same ports.

## Implementation boundaries

In scope:

- Dual ownership + Step 0 cleanup of **positively owned** disposable
  state.
- StoragePool/quota topology and managed-path binding.
- Normalized storage evidence, 10% native-vs-probe arbitration, hard
  upper-bound rule.
- Probe registry + POSIX/Linux quota + optional MooseFS + Windows/macOS
  contracts.
- Storage Sonar v1 real-write fallback (packaged, not a constant).
- Runtime and model storage requirement objects; RM per-pool
  `RUNTIME_PROVISIONING` / `MODEL_ACQUISITION`.
- EDQUOT/ENOSPC contradiction + rediscovery.
- Real 30% replan (new plan identities, real smaller candidates).
- Support matrix, footprint report, T0/T1/controlled T2.

Out of scope (explicit):

- Merge into Stream A / B / acceptance / `kultrun`.
- GPU / T3 physical validation.
- Stage 2.2 adaptive ceiling search behind GET.
- Multi-host storage, SAN, volume resize, NVMe tiering, fleet cache.
- Full installer/upgrade UX. Generations are a seam only.
- Stream B telemetry provenance (unless a later decision requires it).
- Auto-delete of unlabeled legacy trees or customer data.

## Likely files / modules

| Area | Location |
|---|---|
| Contracts | `src/kultrun/storage/contracts.py`, optional fields on runtime/resource |
| Ownership | `src/kultrun/storage/ownership.py` |
| Topology | `src/kultrun/storage/topology.py` |
| Evidence/arbitration | `src/kultrun/storage/evidence.py` |
| Probe registry | `src/kultrun/storage/probes.py` + `ports.py` |
| Sonar core | `src/kultrun/storage/sonar.py` |
| Step 0 | `src/kultrun/storage/cleanup.py` |
| Footprint | `src/kultrun/storage/footprint.py` |
| Reduction | `src/kultrun/storage/reduction.py` (bytes policy only) |
| Adapters | `src/kultrun/adapters/storage/` |
| Envelope SAFE leak | `src/kultrun/capacity/envelope.py` |
| RM | `src/kultrun/resource/manager.py`, `ledger.py`, `snapshot.py` |
| Orchestration | `src/kultrun/platform/` (admit before provision/acquire) |
| Pip cache | `src/kultrun/adapters/provisioning/vllm_native.py` |

## Risks

- Existing tests assume FUSE pools yield an integer SAFE (57.6 GiB class).
  Those tests must change with the authorizing semantics; the meaning of
  `safe_bytes` does not change.
- Fixture hosts that have both overlay `/` (credible) and FUSE
  `/workspace` (now unresolved SAFE) will no longer silently admit
  `/workspace` mutations against overlay SAFE. Tests and planning must
  name the destination pool.
- Real-write Sonar must never run at 25 GiB on a developer disk. Tests
  use fault injection; live writes are tiny on `tmp_path`.
- `posix_fallocate` remains the 1.2A primitive and is **not** Sonar.
  Mixing them would re-introduce quota-blind “success.”

## Architecture invariants (preserved)

- Core owns concepts; adapters own implementations. No MooseFS/RunPod/XFS
  /Windows/macOS logic in CapacityService or ResourceManager.
- ResourceManager remains the only admission authority.
- Capacity owns reported → effective → safe. Sonar provides evidence, never
  selection.
- RuntimeProvisioningPlan owns runtime storage requirement; ModelRequirement
  owns model storage; Available Models means actually deployable.
- DeploymentPlan remains immutable; reductions mint new plan identities.
- Runtime ⊥ Executor; telemetry never decides; unknown is not zero and not
  unlimited.

## Decision boundary

No genuine architecture contradiction was found that requires
`DECISION_REQUIRED` before implementation.

Open product choices that this increment **does** resolve locally (and
records as policy, not blockers):

- Unverified FUSE authorizing SAFE = **unresolved** (not a tiny default).
- Sonar primitive = **real write**, not fallocate.
- Pip = **`--no-cache-dir`** (managed shared cache is a later option).
- Stream B telemetry provenance **deferred**.

---

# Architecture

See `docs/ARCHITECTURE.md` Part IV `storage` (updated in this branch) and
`docs/design/STORAGE-SONAR-SUPPORT-MATRIX.md`.

---

# Acceptance (this increment)

Local only: T0, T1, controlled T2, full pytest, ruff, mypy, packaging.
Physical T3/T5 is a later review, not this commit series.

---

# Debt

See `docs/DEBT.md`: K-27 refined; new deferred-probe entries; K-31 and
K-99 remain OPEN and untouched.
