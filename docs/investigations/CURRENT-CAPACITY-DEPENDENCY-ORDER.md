# Current capacity dependency order

**Status:** investigation only. No production behavior change.

**Product under test:** Stream A `6ed042222bea7bdbc48244475597860e01bf0c4a`
on `stage/1.6L-storage-capacity-truth` (this worktree).

**WIP at investigation time:** docs-only stage brief
`docs/stages/STAGE-1.6L-storage-capacity-truth.md`. No production-code
implementation from the paused storage/Sonar instruction.

**Why this file lives here:** this branch is Stream A lineage. The earlier
storage-truth investigation (`a5ebd41` on
`investigation/1.6L-storage-capacity-truth`) is an acceptance-merge lineage.
Putting this control-flow report on the implementation branch avoids mixing
bases and leaves that investigation HEAD frozen.

This document answers from **executable repository truth**, not from
design intent.

---

## 1. Direct answers

### Question 1 — Does Kultrun currently follow “understand capacity first, then decide what can be installed”?

**PARTIALLY.**

RAM and VRAM for *serving a model* largely follow measure → feasibility →
select → admit → mutate. Storage does not. Runtime installation mutates
disk before any runtime storage requirement exists, and ResourceManager does
not admit storage. Model storage is a later, weaker, first-pool SAFE check.

### Question 2 — Do RAM/VRAM follow this more completely than storage?

**YES.**

RAM/VRAM have: host discovery → `CapacityEnvelope` SAFE →
`CurrentCapacitySnapshot` (SAFE minus ACTIVE) → Available Models → selector
→ `DeploymentPlan` → `ResourceRequest` → `ResourceManager.admit` →
reservation → launch. Storage has a SAFE *number* on the envelope (including
the FUSE 64 GiB heuristic), a first-pool hard check in model evaluation, and
an acquisition preflight that is **not** ResourceManager. Runtime
provisioning has none of that.

### Question 3 — Is upcoming storage work a repair or a redesign?

**REPAIR EXISTING CAPACITY-FIRST ARCHITECTURE.**

The deployment control flow already exists. Storage is missing or stubbed at
specific seams of that graph. The next work should insert truthful storage
into those seams, not replace foundation selection, Available Models, or
ResourceManager.

### Classification

**CLASS B.**

Capacity-first architecture is fundamentally present. Storage
implementation is incomplete and out-of-order at specific seams. The
FUSE 57.6 GiB figure is also a **sensor/policy defect**, but that is not
the whole problem: even a truthful SAFE would not size or admit a vLLM
install today.

Not CLASS A: the problem is not “only a bad sensor.”
Not CLASS C: RAM/VRAM serving already is capacity-first; foundation
lifecycle already is discover → derive → select → (then) provision.
Not CLASS D except as a label for “B plus a sensor defect.”

Storage is a **combination** of:

- sensor defect (FUSE statvfs + 64 GiB belief bound authorizing SAFE);
- missing sizing (no runtime storage requirement);
- missing admission (RM storage stubbed; realize mutates first);
- wrong execution order for *runtime* storage (install before fit);
- incomplete recomputation after disk mutation / EDQUOT.

---

## 2. Actual executable sequence (not cleaned up)

Stage 1.6L CLI / API, as composed in `src/kultrun/main.py` `build()` and
command handlers. Each CLI invocation re-runs startup discovery.

```text
1.  build() → HostDiscoveryService.discover
      NativeLinuxProvider: os.statvfs, mounts, memory, accelerators
      HostInventory.establish → HostCapabilities
2.  CapacityService.compute(host, stored_sanity lookup)
      FUSE/network family: effective = min(reported_free, 64 GiB)
      SAFE = withhold(effective, 10% or 5 GiB floor)
      GET never probes. stored_sanity is a lookup.
3.  ExecutionService.capabilities(host) → ExecutorCapabilityProfile
4.  RuntimeResolver.resolve(host, executors, descriptors, policy)
      OS/arch/accelerator/executor/component presence
      NO storage sizes. NO CapacityEnvelope.
      → RuntimeResolution / RuntimeCandidate
5.  FoundationSelectionService: recommend / select
      is_provisionable = native executor + missing vllm is solvable
      Storage cannot make a foundation infeasible.
      Selection change marks downstream_stale (eligible, requirement,
      capacity, resource_request, deployment_plan).
6.  MUTATION: FoundationSelectionService.realize_selected
      create_plan → RuntimeProvisioningPlan (no storage fields)
      ProvisioningService.provision → venv + pip install vllm
      NO ResourceManager. NO storage reservation.
      EDQUOT → installer_failed. Envelope unchanged.
7.  VerificationService.verify_selected (engine import / accelerator probe)
      No storage rediscovery dedicated to this step.
      Next CLI build() will statvfs again; FUSE still cluster-sized.
8.  ModelEligibilityService → EligibleModelView
      Catalog vs selected verified runtime. Not disk.
9.  ModelRequirementEstimator → ModelRequirement
      storage_bytes, peak_additional_bytes (host-independent)
10. AvailableModelsService.evaluate
      planning_capacity = ResourceManager.snapshot bound onto
      DeploymentCapacity (first-pool SAFE storage scalar)
      Funnel: discovery → compatibility → cheap VRAM weight bound
      → deep estimate → evaluate() storage hard check
      → runtime-memory calibration (VRAM sentinel; may mutate)
      → AvailableModelView
11. ModelSelectionService ranks only Available members
12. DeploymentPlanningService persists DeploymentPlan
      expected_ram/vram/unified/storage (peak acquisition)
      plan_basis fingerprints foundation/runtime/selection/requirement/capacity
      NO storage pool/quota. NO storage reservation.
13. MUTATION: DeploymentPreparationService.acquire
      AcquisitionService.acquire: first-pool SAFE vs peak
      writes staging under state_root/models
      records storage_mount = that first pool
      NOT ResourceManager
14. AdmissionService.reserve_for_plan
      ResourceRequest.incremental_storage_bytes = NOT_PROVIDED
      ResourceManager admits RAM + VRAM only
      _safe_and_reserved("storage") → (None, 0)  [stub]
15. MUTATION: InstanceService start
      NativeProcessExecutor launches vLLM
      GPU mapping bound to admitted reservation (VRAM)
```

Operator-only side path: `kultrun storage sanity-check` (posix_fallocate
ladder, K-27). Not on realize or acquire.

---

## 3. Transition map (objects)

| Step | File / function | Input | Output | Next consumer |
|---|---|---|---|---|
| Host discovery | `host/discovery.py` `HostDiscoveryService.discover` | providers | `HostCapabilities` | `CapacityService`, runtime resolve |
| Envelope | `capacity/envelope.py` `CapacityService.compute` | `HostCapabilities`, stored `StorageSanityEvidence` | `CapacityEnvelope` | planning, acquisition, RM, CLI `host` |
| Foundation derive | `runtime/resolve.py` `resolve` | `HostCapabilities`, executor profiles, descriptors | `RuntimeResolution` | foundation selection |
| Foundation select | `runtime/selection.py` `select_auto` / `select_manual` | candidates | `FoundationSelection` | realize, eligibility |
| Runtime plan | `runtime/plan.py` `build_plan` | `RuntimeCandidate`, host | `RuntimeProvisioningPlan` | provision |
| Realize | `runtime/provision.py` `ProvisioningService.provision` | plan | `RuntimeInstallation` | verify |
| Verify | `runtime/verify.py` | installation | `RuntimeCapabilityProfile` | eligibility |
| Eligible models | `runtime/eligibility.py` | catalog + profile | `EligibleModelView` | Available Models |
| Requirement | `platform/requirement.py` `assess_entry` | entry, envelope/capacity | `ModelRequirement` + evaluation | Available, selector |
| Snapshot | `resource/snapshot.py` `current_capacity_snapshot` | envelope, ACTIVE reservations | `ResourceSummary` | `planning_capacity` |
| Bind planning | `platform/capacity_snapshot.py` `planning_capacity` | RM + envelope | `DeploymentCapacity` | Available, evaluate |
| Available | `platform/available_models.py` `evaluate` | eligible + capacity | `AvailableModelView` | selector |
| Select | `platform/model_selection.py` | Available members | `ModelSelection` | DeploymentPlan |
| Plan | `platform/deployment_plan.py` | selection | `DeploymentPlan` | acquire, admit, instance |
| Acquire | `model/acquisition.py` `acquire` | request + envelope | `ModelArtifact` | admit |
| Admit | `resource/manager.py` `admit` | `ResourceRequest` | `ResourceReservation` | instance start |
| Launch | `inference/service.py` + `adapters/execution/native_process.py` | instance + reservation | running process | `infer` |

---

## 4. RAM / VRAM reference path

**Capacity-first: YES, for serving (with listed exceptions).**

| Seam | Current behavior |
|---|---|
| Discovery | Host facts: memory total/limit; assigned accelerator memory (`native_linux.py`) |
| SAFE | `CapacityService._memory` / `_accelerator`: reported → effective (cgroup limit) → withhold → SAFE |
| Requirement | `ModelRequirement.ram_bytes`, `estimated_vram_bytes`; vLLM calibrated via `RuntimeMemoryCalibrationService` |
| Current capacity | `ResourceManager.snapshot` = SAFE minus ACTIVE RAM/VRAM per device |
| Available Models | Cheap weight bound + deep VRAM/RAM fit + calibration; `is_selectable` requires `capacity_verdict == "feasible"` |
| Selection | Ranks Available only |
| DeploymentPlan | `expected_ram_bytes`, `expected_vram_bytes`; `plan_basis` includes capacity fingerprint |
| ResourceRequest | RAM + accelerator bytes from the plan |
| RM admission | Load-bearing RAM + VRAM; rejects / unresolved honestly |
| Reservation | `admitted_ram_bytes`, `admitted_vram_bytes`, per-accelerator index |
| Launch | vLLM GPU memory bound to reservation |

Exceptions:

- Foundation/runtime *install* is not RAM-admitted either (pip is not a
  RAM reservation). That is acceptable at this stage; the gap that
  failed T3 is disk.
- Runtime-memory calibration may acquire a sentinel and launch a probe
  (`capacity_stale` refresh). That is a controlled mutation *after*
  estimated-feasible, for VRAM truth, not for storage.
- Unified memory remains unresolved (Stage 1.2 DC-01).

---

## 5. Storage — same questions

| Question | Current answer |
|---|---|
| Where discovered? | `os.statvfs` per mount in `NativeLinuxProvider` → `MountFacts.free_bytes` |
| When normalized? | `CapacityService._pool` at envelope compute |
| When SAFE? | Immediately, from reported/effective, **including unverified FUSE** (64 GiB ceiling then 10%/5 GiB withhold → ~57.6 GiB) |
| What consumes SAFE? | `deployment_capacity` first resolved pool; acquisition `safe_storage`; snapshot `_storage_safe` first resolved pool; `evaluate()` storage hard check |
| Runtime storage requirement? | **Never.** `RuntimeProvisioningPlan` has no storage fields. `RuntimeCandidate` has none. |
| Model storage requirement? | `ModelRequirement.storage_bytes` + `peak_additional_bytes`. Available uses incremental peak (0 if already STORED). |
| When admitted? | Acquisition: local SAFE compare, not RM. Realize: never. Inference RM: storage omitted (`NOT_PROVIDED`). |
| When reserved? | `admitted_storage_bytes` copied from request; request storage is unresolved so ledger storage is unused in practice |
| When mutation allowed? | Realize: immediately after plan. Acquire: after first-pool SAFE compare |
| When remeasured? | Next process `build()` rediscovers host. Envelope not contradicted on EDQUOT. Sanity evidence only if operator ran 1.2A |
| Downstream recompute? | Foundation *selection change* marks stale. Provision success/failure does **not** by itself invalidate capacity or Available Models. Next evaluate uses a fresh envelope from current host facts |

---

## 6. Critical questions

### 17. Before foundation/runtime selection, does Kultrun know whether the runtime fits in storage?

**NO.**

Gap: `runtime/resolve.py` `resolve()` and `is_provisionable()` see host
OS/arch/accelerator/executor/components only. There is no runtime
persistent/peak/cache byte requirement and no comparison to pool SAFE.

### 18. Before `runtimes realize`

| Fact | Known? |
|---|---|
| Persistent runtime bytes | NO |
| Staging/transient bytes | NO |
| Package-cache bytes | NO (`pip install` without `--no-cache-dir`) |
| Peak storage requirement | NO |
| Target storage pool/domain | NO (writes under `state_root/runtimes/...`, path not bound to `StoragePool`) |
| Compare to usable capacity | NO |
| Ask ResourceManager | NO |
| Reserve storage | NO |

Large writes happen first. T3 EDQUOT is this path.

### 19. Model feasibility / Available Models

| Accounted? | Answer |
|---|---|
| Final artifact bytes | `storage_bytes` exists; Available incremental check uses **peak**, and 0 if already STORED |
| Acquisition peak | YES, via `incremental_storage_demand` / `evaluate` |
| Runtime already installed | Not as a storage cost. Eligibility requires verified runtime; disk footprint of that runtime is not subtracted from a destination quota |
| Runtime storage requirement | NO |
| Current remaining storage | PARTIAL: first pool with resolved SAFE, minus ACTIVE incremental storage (usually 0) |
| Exact destination pool | NO. `safe_storage(envelope)` walks pools in envelope order. `ModelArtifact.storage_mount` records whichever pool won, after the fact |

`utilization()` **excludes storage** from ranking ratio. Storage is a
hard fail (`infeasible_storage`) if peak > first-pool budget, else
ignored for ranking.

### 20. Storage pools / shared quota

`StoragePool` is constructed in tests (`tests/test_contracts.py`), not on
the live path. `quota_identity` is unused. Shared-quota identity for
`/workspace/models`, `/workspace/runtimes`, `/workspace/cache` is **not**
operational.

Shortcuts proven:

- `planning/evaluate.py` `deployment_capacity`: first pool with resolved SAFE
- `resource/snapshot.py` `_storage_safe`: same
- `model/acquisition.py` `safe_storage`: same unless `mount=` passed (callers do not)

On the reference host this picks overlay `/` (credible, smaller) **or**
FUSE `/workspace` (57.6 GiB heuristic) depending on pool order and which
SAFE is resolved — not the destination quota domain.

### 21. ResourceManager

| Resource | Authority |
|---|---|
| RAM | Real: SAFE vs request vs ACTIVE |
| VRAM | Real: per-accelerator SAFE vs request vs ACTIVE |
| Storage | **Stubbed.** `_safe_and_reserved` non-ram/accel/unified returns `(None, 0)`. `request_from_plan` sets `incremental_storage_bytes=NOT_PROVIDED`, so storage is not load-bearing. If it were resolved, SAFE storage would be unresolved and admission would return UNRESOLVED |

Workload types: `INFERENCE` (used). `EVALUATION` exists on the enum.
**No** `RUNTIME_PROVISIONING` or `MODEL_ACQUISITION`.

Per-pool storage accounting: absent.

### 22. Recalculation after mutation

| Event | Recompute capacity / feasibility? |
|---|---|
| Runtime provision success | No dedicated invalidate. Next command rediscovers host; FUSE SAFE unchanged |
| Runtime provision failure | Envelope not contradicted. Status `installer_failed` |
| Model acquisition | Host rediscovered on next command; no pool generation bump; Available not auto-recomputed |
| EDQUOT / ENOSPC | Classified as installer/acquisition OSError / `installer_failed`. **No** contradiction, snapshot invalidation, or feasibility recompute |

VRAM calibration *does* refresh envelope/snapshot when `capacity_stale`
(`refresh_capacity` in `main.py`). That pattern is the model to copy for
storage, and it does not exist for disk.

### 23. Foundation selection vs intended

Actual: DISCOVER host → derive candidates (compat) → rank/select →
invalidate downstream on **selection change** → provision → verify →
eligible models later.

Storage does not participate. Runtime storage cost is not considered.
This is **incomplete**, not a wrong foundation state machine.

### 24. Available Models vs CurrentCapacitySnapshot

RAM/VRAM: same snapshot semantics (SAFE minus ACTIVE).

Storage: a scalar `safe_storage_bytes` / `available_storage_bytes` from
the **first** pool, bound in `planning_capacity`. Weaker: not
per-pool, not destination-bound, not RM-admitted, and SAFE itself may
be the FUSE heuristic. Selector consumes only Available; storage can
exclude a member via `infeasible_storage`, so it is *inside* the
funnel, but not with RAM/VRAM authority.

### 25. DeploymentPlan storage proof

| Field | Present? |
|---|---|
| Storage capacity provenance | PARTIAL: `plan_basis` / envelope fingerprint, not a storage-evidence identity |
| Storage requirement | `expected_storage_bytes` = peak acquisition, not runtime+model |
| Storage pool/domain | NO |
| Storage reservation | NO (reservation is later and RAM/VRAM-only) |

---

## 7. Intended vs actual

```text
INTENDED:
measure → feasibility → selection → admission → mutation → remeasure → recompute

CURRENT RAM/VRAM (serving):
measure → feasibility → selection → admission → mutation
remeasure: snapshot on next evaluate; calibration refresh if probe stale
recompute: Available/plan on next evaluate; foundation select marks stale

CURRENT STORAGE:
measure (statvfs + heuristic SAFE)
→ (skip runtime feasibility)
→ select runtime
→ MUTATE realize
→ (optional) model feasibility vs first-pool SAFE
→ select model / plan
→ acquire preflight (not RM) → MUTATE acquire
→ admit RAM/VRAM
→ launch
remeasure: weak (statvfs again; heuristic unchanged)
recompute: not on EDQUOT; not on provision
```

| Stage | RAM/VRAM | Storage |
|---|---|---|
| Measure | CORRECT | PARTIAL (wrong FUSE authorizing SAFE) |
| Feasibility | CORRECT (models); N/A for runtime install | MISSING for runtime; PARTIAL for models |
| Selection | CORRECT | PARTIAL (models only, bad pool) |
| Admission | CORRECT | MISSING / stubbed |
| Mutation | After admit (launch) | OUT_OF_ORDER (realize, and acquire without RM) |
| Remeasure | PARTIAL (snapshot; live host on next CLI) | MISSING as contradiction |
| Recompute | PARTIAL (stale on foundation select; Available on evaluate) | MISSING after disk failure |

---

## 8. Where Sonar should sit (do not implement here)

Governing architecture is capacity-first. Sonar is **evidence**, not
selection or admission.

Correct insertion:

```text
minimal topology (mount → quota domain / StoragePool)
→ Step 0 owned disposable cleanup
→ rediscover native/declared
→ always run compatible specialist probe
→ 10% arbitration + hard-upper-bound
→ fallback Sonar if authorizing usable still unresolved
   (operation-targeted: planned peak, not ceiling climb)
→ authorizing SAFE for that pool
→ THEN runtime feasibility (can this runtime install fit?)
→ select / admit / provision
→ rediscover
→ THEN model feasibility (Available Models)
→ select / plan / admit / acquire / deploy
```

GET `/host` and `CapacityService.compute` must still **not** probe.
Platform gathers evidence and passes it in, as `stored_sanity` already
does for 1.2A.

If Sonar ran only at realize time, foundation selection would still be
storage-blind. Authorizing pool capacity must exist **before** runtime
feasibility, even if the empirical write is sized to the planned runtime
peak rather than 25 GiB.

Relationship to probes: native/specialist first; Sonar only when they
cannot authorize; skip large Sonar if evidence already proves
insufficiency.

---

## 9. Ownership reuse (do not implement here)

Reusable (not sufficient alone):

| Existing | Fit |
|---|---|
| `PlatformState.installation_id` | Whole-product install identity; too coarse for per-root cleanup |
| `RuntimeInstallation` / `RuntimeProvisioningPlan` | Runtime generation seam; no local FS marker, no cleanup policy |
| `ModelArtifact` + inventory | Model artifact identity + `storage_mount` after acquire; no dual marker/registry |
| `StoragePool.generation` | Intended invalidation of evidence; unused live |
| `ExecutionOwnership` | Process handles, not files |
| Foundation/plan/selection `generation` | Downstream stale, not install generations |
| `.kultrun-probe` | Sanity probe artifacts only |
| `state_root` layout (`runtimes/`, `models/`) | Convention; must not authorize delete |

**New concepts required:** local `.kultrun-owner.json` (or equivalent) at
managed roots; central ownership registry contract; cleanup eligibility /
protection flags; installation-generation object linking runtime + staging
+ caches. Do not delete by path substring.

---

## 10. WIP review (paused implementation)

Production code from the previous storage/Sonar prompt: **none**.

| Artifact | Classification |
|---|---|
| `docs/stages/STAGE-1.6L-storage-capacity-truth.md` | ALIGNED (implementation review; FUSE SAFE unresolved; RM remains authority; Sonar not on GET) |
| Ownership / Sonar / probes / RM storage code | NOT STARTED |

The paused prompt’s intended product order (cleanup → evidence → Sonar →
size → admit → mutate → recompute) is **aligned** with CLASS B repair.
Likely modification when resumed: authorizing storage must feed
**foundation/runtime feasibility**, not only the realize preflight.
Nothing to revert.

---

## 11. Key code evidence

1. `capacity/envelope.py` `_pool`: FUSE `effective = min(reported, 64 GiB)` then SAFE from withhold — heuristic authorizes.
2. `runtime/resolve.py` `resolve`: no storage.
3. `runtime/selection.py` `realize_selected` → `ProvisioningService.provision` with no RM.
4. `runtime/contracts.py` `RuntimeProvisioningPlan`: no storage requirement fields.
5. `resource/manager.py` `_safe_and_reserved`: storage → `(None, 0)`.
6. `platform/admission.py` `request_from_plan`: `incremental_storage_bytes=NOT_PROVIDED`.
7. `planning/evaluate.py` `deployment_capacity`: first resolved SAFE pool.
8. `model/acquisition.py` `safe_storage` / `acquire`: first-pool preflight; OSError not envelope contradiction.
9. `adapters/provisioning/vllm_native.py`: `pip install` without `--no-cache-dir`.
10. `utilization()`: storage excluded from ranking; `_hard_capacity_failures` can still set `infeasible_storage`.

---

## 12. Physical follow-up

**NONE** for this architectural question.

Already known: FUSE reported ~186 TiB; product 64.0 / 57.6 GiB; real
write hit EDQUOT with ~6.25 GiB remaining. That confirms sensor + missing
runtime admission. It does not require a new GPU probe to decide CLASS B.
