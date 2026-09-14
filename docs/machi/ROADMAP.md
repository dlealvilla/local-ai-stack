# Machi implementation roadmap

**Authority for Machi build sequence.** Derived from
[ARCHITECTURE.md](ARCHITECTURE.md). Kultrun `docs/ROADMAP.md` remains
authoritative for Kultrun only.

Work token prefix: `MACHI-0.0.1` for this architecture package.
Implementation tokens will be `MACHI-<milestone>`.

**Rule:** BUILD → package → install on a disposable server → execute
with known input → capture contracts + events + logs → accept or
fix. Do not edit source on the server.

**Rule:** no attached product (Admin UI, Knowledge, marketplace)
before the core exoskeleton can run Blocks 1–9. Observability is
**not** an attached product; it starts at M0.

**Rule:** do not use Kultrun stage numbers as Machi IDs.

---

# 1. Empirical progression

```text
M0                         Kernel events
M0 → M1                    + Install
M0 → M1 → M2               + Discover
M0 → … → M3                + Steward
M0 → … → M4                + Capacity
M0 → … → M5                + Foundation
M0 → … → M6                + Model
M0 → … → M7                + Plan
M0 → … → M8                + Admit
M0 → … → M9                + Serve  = verified deployment
```

After each milestone: independent test of that block, then
cumulative `1 → … → N`. Failures must name a Block ID.

Test modes (names reused from Kultrun because they are good):

| Mode | Use in Machi |
|---|---|
| T0 | contract/architecture/unit |
| T1 | replay captured host/storage fixtures |
| T2 | clean wheel install |
| T3 | real host, no model required |
| T5 | live inference on a real accelerator |

L1 unit evidence never closes a milestone that touches hardware,
storage, or a runtime.

---

# 2. Milestones

## M0 — Kernel

**Milestone ID:** `M0`  
**Architecture IDs (first vertical):** `0.1.1` Registry, `0.1.2`
Unresolved, `0.2.1` Typed IDs, `0.3.1` EventRecord, `0.3.2` Journal,
`0.5.1` Privacy classification.

**Deferred inside Kernel (not required to persist `kernel.alive`):**
`0.3.3` Observers, `0.6.1` DeploymentWitness, `0.7.1` Health aggregator.

`0.4.1` Store was deferred from the first Kernel vertical because M0
did not yet persist addressable entities. It is implemented now as a
Kernel increment so `1.3.2 RegistrySeed` can persist a registry record
without inventing a second persistence mechanism.

**Objective:** Machi can exist as an artifact that persists one
versioned event without owning any domain decision.

**Architecture units:** contracts, Unresolved, EventRecord, journal
port, privacy class. The entity Store (`0.4.1`) is a later Kernel
increment: injected root, create/get, not the event journal.

**Inputs:** none (bootstrap).

**Outputs:** `EventRecord` schema; InstallRun fields present and
`Unresolved(NOT_PROVIDED)` until M1; architecture tests forbidding
Kultrun imports and Kernel imports of adapters / future Blocks.

**Telemetry / analytics added:** envelope fields listed in
[TELEMETRY.md](TELEMETRY.md) §2 “from the first milestone”;
`install.started` waits for M1; M0 proves `kernel.alive`.

**Local tests:** T0 serialize/round-trip; Unresolved has no truth
value; privacy enum present.

**Physical server test:** T2 wheel; `machi version` (or equivalent)
prints build id; one event file on disk.

**Cumulative test:** M0 only.

**Acceptance gate:** an installed artifact writes one `EventRecord`
and reports identity. No host probing.

**Explicit non-goals:** discovery, storage, UI, runtimes.

**Dependencies:** none.

**What this unlocks:** every later block can emit events.

---

## M1 — Install

**Milestone ID:** `M1`  
**Architecture IDs:** `1`, `1.1.1` InstallRecord, `1.2.1` StateRootBinder,
`1.3.1` SelfOwnershipMarker, `1.3.2` RegistrySeed, `1.4.1` InstallRunStore

**Working Component order:** `1.2.1` → `1.3.1` → `1.3.2` → `1.1.1` → `1.4.1`.
Do not implement later Components in an earlier increment.

**Objective:** this copy of Machi knows where it lives and who it is.

**1.2.1 (first increment) inputs:** artifact, optional `--state-root`,
optional `MACHI_STATE_ROOT`.

**1.2.1 outputs:** `StateRootBinding`; directory established; Kernel
event `install.state_root.bound`.

**1.3.1 (accepted) inputs:** `StateRootBinding` from 1.2.1.

**1.3.1 outputs:** `LocalOwnershipEstablishment`; `.machi-owner.json`;
Kernel event `install.ownership.local_marked`. Status is
`local_marker_present`. Dual ownership and destructive authorization are
always false.

**0.4.1 (this increment):** Kernel Store port and `FileStore` adapter.
Injected root; exclusive create + get; not the journal; not RegistrySeed.

**1.3.2 (next recommended; not this increment):** central registry record
citing the same `marker_id` and root fingerprint. Requires Kernel
`0.4.1` Store. Do not treat InstallRecord as the second ownership half.

**Full M1 outputs:** `InstallRecord`, `InstallRun`, local marker, and
later the registry half. Steward `OwnershipRecord` remains Block 3.

**Telemetry:** `install.state_root.bound` at 1.2.1 and
`install.ownership.local_marked` at 1.3.1 (`restricted`; absolute path
omitted). Never `ownership.verified` from 1.3.1. `install.bound` and
InstallRun correlation wait for 1.4.1.

**Local tests (1.3.1):** marker create; re-entry; two-root isolation;
copied marker fail-closed; unknown content refused; Kultrun collision;
malformed marker; no InstallId/InstallRun fabrication; M0 and 1.2.1
regression.

**Physical (1.3.1):** T3 filesystem host; no GPU. Cumulative
M0 → 1.2.1 → 1.3.1.

**Local tests (0.4.1):** exclusive create; get; identical re-entry;
conflict fail-closed; malformed/unsupported fail-closed; unsafe keys
refused; two-root isolation; corruption locality; journal independence;
M0/1.2.1/1.3.1 regression.

**Physical (0.4.1):** T3 filesystem host; no GPU. Fresh process read;
two store roots; cumulative M0 → 1.2.1 → 1.3.1 → 0.4.1.

**Cumulative:** M0 → 1.2.1 → 1.3.1 → 0.4.1, then M0 → M1.

**Acceptance (full M1):** `machi version` + persisted InstallRun; events
correlated. **1.3.1 gate:** local marker + restricted event + no
destructive authorization + M0/1.2.1 green. **0.4.1 gate:** durable
entity round-trip on an injected root + restricted proof event +
predecessors green.

**Non-goals (1.3.1):** central registry, dual-proof evaluator, Steward
cleanup, reclaim, sibling scan, InstallRecord, InstallRun.

**Unlocks:** 1.3.2 can cite a stable local evidence identity. Discover
still waits for full M1 identity.

---

## M2 — Discover

**Milestone ID:** `M2`  
**Architecture IDs:** `2`, `2.1`–`2.4`

**Objective:** normalized `HostProfile` from adapters; unknown
preserved.

**Inputs:** InstallRecord.

**Outputs:** `HostProfile`, `MountObservation[]`.

**Telemetry:** `discover.completed`; adapter names as provenance, not
as schema.

**Local tests:** T1 fixture replay of the known Linux/NVIDIA shape.

**Physical:** T3 `machi host` matches `HostProfile` fields; GPU
physical vs SAFE distinguished.

**Cumulative:** M0 → M2.

**Acceptance:** profile persisted; reported free on FUSE flagged
untrusted **as observation**, not yet authorizing.

**Non-goals:** Sonar, reclaim, runtimes.

**Unlocks:** Steward and Capacity.

---

## M3 — Steward

**Milestone ID:** `M3`  
**Architecture IDs:** `3`, `3.1`, `3.2`, `3.3`

**Objective:** classify nearby Machi/Kultrun-owned state; delete only
dual-owned CLEANUP ELIGIBLE; keep UNKNOWN.

**Inputs:** HostProfile, mounts, ownership registry.

**Outputs:** `OccupancyMap`, optional `ReclaimResult`.

**Telemetry:** `steward.classified`, `steward.reclaim.*`.

**Local tests:** unique_occupancy: UNKNOWN parent cannot hide
RECLAIMABLE children; no delete without dual proof.

**Physical:** T3 on a host with leftover sibling `models`/`runtimes`;
product deletes them; journals remain. No operator `rm`.

**Cumulative:** M0 → M3.

**Acceptance:** OccupancyMap mutually exclusive classes; reclaim is
idempotent.

**Non-goals:** using reclaimed bytes (that is M4).

**Unlocks:** Capacity remaining and recharacterize.

---

## M4 — Capacity

**Milestone ID:** `M4`  
**Architecture IDs:** `4`, `4.1`–`4.6`

**Objective:** authorizing remaining on the destination pool;
HostMinimumVerdict; SAFE is the only authorizing layer.

**Inputs:** HostProfile, OccupancyMap, ReclaimResult.

**Outputs:** `CapacityEvidence`, `CapacityEnvelope`,
`HostMinimumVerdict`.

**Telemetry:** `capacity.characterized`, `capacity.minimum.completed`,
sonar tier outcomes including EDQUOT as capacity evidence.

**Local tests:** FUSE reported free cannot authorize; remaining after
occupancy; occupancy drop may recharacterize.

**Physical:** T3 pool-bound probe; EDQUOT recovery; post-reclaim
Sonar when SAFE still blocks.

**Cumulative:** M0 → M4.

**Acceptance:** envelope persisted with provenance; min gate PASS or
FAIL with reason; live remaining must not rewrite realize-time
verdict.

**Non-goals:** runtime pip, models.

**Unlocks:** Foundation feasibility.

---

## M5 — Foundation

**Milestone ID:** `M5`  
**Architecture IDs:** `5`, `5.1`–`5.6`

**Objective:** one selected, provisioned, verified execution
foundation. Native process is first-class. Docker is optional.

**Inputs:** HostProfile, CapacityEnvelope, HostMinimumVerdict PASS.

**Outputs:** `FoundationSet`, `FoundationSelection`,
`RuntimeInstallation`, `RuntimeCapability`.

**Telemetry:** `foundation.resolved`, `.selected`, `.verified`;
funnel counts (COMPATIBLE+CONDITIONAL = feasible).

**Local tests:** executor ⟂ runtime; CONDITIONAL product is
selectable; container unsupported is FILTERED not selected.

**Physical:** T3/T5-prep native vLLM install + verify on the reference
NVIDIA host. llama.cpp/MLX may remain FUTURE.

**Cumulative:** M0 → M5.

**Acceptance:** selected ≠ recommended may differ; verification
VERIFIED; installation bytes recorded.

**Non-goals:** serving a model.

**Unlocks:** Model funnel.

---

## M6 — Model

**Milestone ID:** `M6`  
**Architecture IDs:** `6`, `6.1`–`6.5`

**Objective:** Available Models from catalog; one selection; local
artifact.

**Inputs:** RuntimeCapability, CapacityEnvelope remaining.

**Outputs:** `AvailableModels`, `ModelSelection`, `ModelArtifact`.

**Telemetry:** `model.funnel.completed`, `.selected`, `.acquired`;
blocked reasons for important exclusions.

**Local tests:** estimated ≠ available; recommended ≠ selected;
unknown catalog fields stay unresolved.

**Physical:** T5-prep acquire or reuse qwen-class AWQ; no Hub as
compatibility authority.

**Cumulative:** M0 → M6.

**Acceptance:** AUTO selection persisted; artifact digest/size
recorded.

**Non-goals:** marketplace UX.

**Unlocks:** Plan.

---

## M7 — Plan

**Milestone ID:** `M7`  
**Architecture IDs:** `7`, `7.1`–`7.3`

**Objective:** one CURRENT `DeploymentConfiguration`. It does not
launch.

**Inputs:** FoundationSelection, ModelSelection, artifact, envelope.

**Outputs:** `DeploymentConfiguration`, `ResourceRequest`.

**Telemetry:** `plan.created`; STALE when upstream invalidates.

**Local tests:** planning ⟂ resource (no import); CURRENT vs STALE.

**Physical:** T3 compose plan; restart process still sees CURRENT.

**Cumulative:** M0 → M7.

**Acceptance:** configuration names runtime, model, executor, pool,
RAM/VRAM/storage, context.

**Non-goals:** admit, start.

**Unlocks:** Admit.

---

## M8 — Admit

**Milestone ID:** `M8`  
**Architecture IDs:** `8`, `8.1`–`8.3`

**Objective:** ResourceManager is the only author of “you may run this
now.”

**Inputs:** DeploymentConfiguration, CapacitySnapshot.

**Outputs:** `ResourceReservation` ADMITTED or typed rejection.

**Telemetry:** `admit.completed` / `.rejected`.

**Local tests:** executor cannot admit; snapshot is now, not
historical envelope alone.

**Physical:** T3 ADMITTED for the plan; second overlapping request
rejects or waits per policy (v0: reject).

**Cumulative:** M0 → M8.

**Acceptance:** reservation names devices and storage; not a process.

**Non-goals:** start.

**Unlocks:** Serve.

---

## M9 — Serve (core complete)

**Milestone ID:** `M9`  
**Architecture IDs:** `9`, `9.1`–`9.6`, `0.6` Witness acceptance

**Objective:** a real model answers a **request** inference; restart
works; Witness answers the journey without logs.

**Inputs:** CURRENT configuration + ADMITTED reservation.

**Outputs:** `ServingInstance`, `ReadinessProof`, `InferenceProof`,
`DeploymentWitness`.

**Telemetry:** serve lifecycle; `inference.completed` with
`purpose=request`; usage metrics without prompt text.

**Local tests:** readiness not counted as request; stop ≠ release;
identity cookie reacquire.

**Physical:** T5 start → infer → stop → GPU empty → restart → infer;
Witness layers equivalent to Kultrun’s guided report, composed from
journal + stored contracts **without live re-resolve**.

**Cumulative:** M0 → M9 = core product.

**Acceptance:** request inference PASS; model identity matches
selection; Witness OVERALL PASS; manual intervention NONE for the
happy path.

**Non-goals:** llama.cpp, Admin UI, Knowledge, multi-instance,
streaming, public bind.

**Unlocks:** outer product attachment (Admin, Knowledge, more
runtimes) without moving truth into the UI.

---

# 3. After the core (attached, not this package’s implementation)

| Later | Attaches at | Notes |
|---|---|---|
| Additional foundations | 5 catalogue | llama.cpp, MLX as FUTURE until selected |
| Gateway / auth | 9 + identity | loopback remains default |
| Admin UI | Witness + control APIs | progressive disclosure |
| Knowledge/RAG | Serve as a consumer of inference | never admits resources |
| Teams / Team Brain | identity + Knowledge + Serve | composition, not a model |
| Marketplace | 6 catalog | policy, not Hub |
| Licensing | entitlement | local inference without SaaS |
| Vendor export | EventRecord allow-list | default off |
| Fleet | host-scoped IDs already | new outer plane |

---

# 4. Per-unit test template (every Capability)

Each Capability declares:

- **TEST INPUT** — fixture or prior contract IDs
- **EXPECTED OUTPUT** — named contract
- **EXPECTED STATE CHANGE** — records created/replaced
- **EXPECTED TELEMETRY** — event types
- **EXPECTED FAILURE** — typed blocked/fail
- **OBSERVABLE SERVER EVIDENCE** — files, processes, GPU
- **ACCEPTANCE** — T0/T1/T2/T3/T5 as the milestone requires

Failures are attributed to the Capability ID, not to “the stack.”

---

# 5. Current vs future

| Already proven in Kultrun (rebuild, not copy) | Machi redesign | Implement again | Future outer |
|---|---|---|---|
| Host discovery, native vLLM path, admission, ownership, Sonar, reclaim, report-as-projection (after honesty fix) | Event unification; Block sequence; Witness not live-resolver; Install first; Steward before Capacity | Entire runtime from empty tree | UI, Knowledge, brains, marketplace, fleet, extra runtimes |

Conceptual reuse ≠ code reuse.
