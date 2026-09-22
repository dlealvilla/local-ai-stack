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

**0.4.1 (accepted):** Kernel Store port and `FileStore` adapter.
Injected root; exclusive create + get; not the journal; not RegistrySeed.

**1.3.2 (accepted):** local control-plane registry record citing the
same `marker_id` and root fingerprint. Uses Kernel `0.4.1` Store with an
injected registry Store root. Does not evaluate dual proof.

**1.1.1 (accepted):** install-scoped identity. One stable `InstallId`
per local ownership identity. Build fields are creation provenance.
Not InstallRun. Not host identity.

**1.4.1 (accepted):** durable InstallRun correlation. One current
`InstallRunId` per `InstallId`, reused across CLI processes. Lookup by
InstallId. Not a process, host, or run-history engine.

**Full M1 outputs:** `InstallRecord`, `InstallRunRecord`, local marker,
and registry half. Steward `OwnershipRecord` remains Block 3.

**Telemetry:** `install.state_root.bound` at 1.2.1,
`install.ownership.local_marked` at 1.3.1, and
`install.ownership.registry_seeded` at 1.3.2 (`restricted`; absolute path
omitted). `install.record.established` at 1.1.1 (`restricted`; resolved
`install_id`; `install_run_id` and `host_id` unresolved). Never
`ownership.verified`. `install.bound` at 1.4.1 (`restricted`; resolved
`install_id` and `install_run_id`; `host_id` unresolved). Historical
events are not rewritten.

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

**Cumulative:** M0 → 1.2.1 → 1.3.1 → 0.4.1 → 1.3.2 → 1.1.1 → 1.4.1.

**Acceptance (full M1):** `machi version` + persisted InstallRun;
`install.bound` with resolved install and run ids; host unresolved;
predecessors green. Physical 1.4.1 accepted on `99b96bf`.

**Unlocks:** Discover (`2.1.1`).

---

## M2 — Discover

**Milestone ID:** `M2`  
**Architecture IDs:** `2`, `2.1`–`2.5`

**Working Component order:** `2.1.1` → `2.2.1` → `2.3` (generic
Accelerator Discovery + NVIDIA and Apple providers) → `2.5.1`
PrerequisiteReadiness → `2.4.1`. `2.5` is sequenced before `2.4`
because a usable vendor CLI is a discovered-environment concern, not
a mount concern. Do not treat NVIDIA as the capability. Do not
implement later Components in an earlier increment.

**Objective:** normalized host observations from adapters; unknown
preserved. HostProfile is the milestone output, not this increment.

**2.1.1 (accepted):** OS family and CPU architecture through a
replaceable adapter. Physical evidence `b9d869b`.

**2.2.1 (accepted):** reported physical/system memory in integer
bytes through a replaceable adapter. Source-agnostic
`MemoryObservation`. Native observer selects Linux `/proc` or macOS
`sysconf` providers. Windows unsupported (not zero). Event
`discover.memory.observed` (`public_ops`). No HostId. No HostProfile.
No safe-capacity arithmetic. No available/swap/cgroup in this
Component.

**Inputs (2.2.1):** current host; 2.1.1 OS family for native source
selection; optional M1 InstallId/InstallRunId from composition.

**Outputs (2.2.1):** `MemoryObservation`; Discover event with `host_id`
unresolved.

**Telemetry:** `discover.memory.observed`. Block-complete
`discover.completed` remains later.

**Local tests:** native current-host observation; Linux table fixtures
(KiB conversion, missing/malformed/unknown unit/zero); Windows
unsupported; M1 + 2.1.1 regression.

**Physical:** accepted on `66e8ee0`. Linux `MemTotal × 1024` matched
the packaged observer after empty-state M1 + 2.1.1 reconstruction.

**Cumulative:** M0 → M1 → 2.1.1 → 2.2.1.

**Non-goals (2.2.1):** HostId, HostProfile, NVIDIA, mounts,
available/swap/cgroup, capacity, remediation, Windows native reader.

**Unlocks:** `2.3` Accelerator Discovery.

**2.3 (NVIDIA physical PASS; Apple physical pending):** generic
accelerator observation through a replaceable observer. Native
orchestration selects applicable NVIDIA (`nvidia-smi` CSV) and Apple
(`system_profiler` JSON) providers. Event
`discover.accelerator.observed` (`public_ops`). No HostId. No
HostProfile. No safe-VRAM arithmetic. Unavailable tooling is not a
measured zero-device result. Apple unified memory is Unresolved, not
system RAM copied as VRAM.

**Inputs (2.3):** current host; 2.1.1 OS family for applicability;
optional M1 InstallId/InstallRunId from composition. Does not consume
`MemoryObservation`.

**Outputs (2.3):** `AcceleratorObservation`; Discover event with
`host_id` unresolved.

**Telemetry:** `discover.accelerator.observed`. Block-complete
`discover.completed` remains later.

**Local tests:** generic orchestration; NVIDIA CSV fixtures
(single/multi/malformed/missing tool); Apple JSON fixtures and real
Apple Silicon host; NVIDIA negative path on a non-NVIDIA Mac; M0 →
2.2.1 regression.

**Physical:** NVIDIA Linux PASS on the exact combined candidate
(`1c774a0` / SHA `351cee81…`). Apple Silicon physical and Checkpoint A
remain later on that same SHA.

**Cumulative:** M0 → M1 → 2.1.1 → 2.2.1 → 2.3 local → 2.3 NVIDIA physical.

**Non-goals (2.3):** Intel, HostId, HostProfile, Capacity, driver
install, MIG/XCP mutation, mounts.

**Unlocks:** `2.5.1` PrerequisiteReadiness, then `2.4.1` Mount
enumerator after 2.5.1 closes. Intel remains deferred. Cgroup/execution
memory limit remains deferred until HostProfile or Capacity needs a
distinct execution ceiling.

**Chronology (do not flatten):** last completed forward feature before
this increment was `2.2.1` (`66e8ee0` / `b341819`). The
provider/portability audit (`e88cc39`) is a correction on that
foundation. `2.3` NVIDIA+Apple remains historically proven on SHA
`351cee81…`. This NVIDIA+AMD line adds `amd-smi` locally; physical
proof of the new candidate is later. Apple physical remains deferred.
Intel is out. See [M2-2.3.md](M2-2.3.md),
[M2-2.3-NVIDIA-PHYSICAL.md](M2-2.3-NVIDIA-PHYSICAL.md), and
[ACCEPTANCE-LAB.md](ACCEPTANCE-LAB.md).

**2.5.1 PrerequisiteReadiness (this increment):** inspect, diagnose,
plan, and optionally remediate bounded environment prerequisites for a
selected provider/runtime/path. Discover remains read-only. Product
default policy is `plan_only`. `remediate` may install only an
allowlisted interpreter dependency into the interpreter the target CLI
actually uses, then re-inspect and verify. First adapter:
`AmdSmiPrerequisiteAdapter` (stock ROCm `amd-smi` missing `yaml` is
the first instance of the generic missing-module class).

**Inputs (2.5.1):** selected `PrerequisitePolicy`; current host
environment; optional M1 InstallId/InstallRunId from composition. Does
not consume Discover observations.

**Outputs (2.5.1):** `PrerequisiteReadinessReport`; events
`prerequisite.*`. No Store entity.

**Telemetry:** `prerequisite.inspected`, `prerequisite.diagnosed`,
`prerequisite.plan_created`, `prerequisite.remediation_started`,
`prerequisite.remediation_completed`, `prerequisite.remediation_failed`,
`prerequisite.verified` (privacy `operational`).

**Local tests:** fixture host covering READY/`NO_OP`, missing
executable, missing allowlisted module, unrecognized failure, timeout,
permission, not-applicable, policy modes, interpreter identity, forged
package refusal, offline source representation, serialization, event
privacy, architecture non-edges.

**Physical:** PASS on one owned MI300X stock ROCm image (template
`runpod-torch-v240-rocm61`). Test C PLAN_ONLY left `amd-smi` broken;
Test A REMEDIATE verified READY and independent `amd-smi` plus AMD
observer; Test B READY → `NO_OP`. Not a GPU-market matrix.

**Cumulative:** M0 → M1 → 2.1.1 → 2.2.1 → 2.3 → 2.5.1.

**Non-goals (2.5.1):** driver installation; package-manager framework;
dependency graph; transactional rollback; arbitrary packages; runtime
provisioning; optimizer; command-center UI; global settings registry;
PyYAML as a Machi wheel dependency.

**Unlocks:** `2.4.1` Mount enumerator.

See [M2-2.5.1.md](M2-2.5.1.md).

**2.4.1 Mount enumerator (this increment):** filesystem/mount
topology through a replaceable observer. Native orchestration selects
Linux (`mountinfo` + native stat) or macOS (`getfsstat`) providers.
Windows unsupported (not zero). Event `discover.mounts.observed`
(`operational`; metadata only). No HostId. No HostProfile. No SAFE
storage arithmetic. No Steward ownership. No directory crawl. Reported
total/free/available stay distinct. Backing identity is recorded when
visible and `Unresolved` when not. Default write probe is off; a tiny
exclusive temp write is observational evidence only.

**Inputs (2.4.1):** current host; 2.1.1 OS family for native source
selection; optional M1 InstallId/InstallRunId from composition. Does
not consume PrerequisiteReadiness, Steward, or Capacity.

**Outputs (2.4.1):** `MountObservation`; Discover event with `host_id`
unresolved.

**Telemetry:** `discover.mounts.observed`. Block-complete
`discover.completed` remains later.

**Local tests:** Linux table fixtures covering local rw, read-only,
pseudo, overlay, network, shared backing, unresolved backing,
invalid/duplicate rows, distinct capacity fields, path capability,
probe policy/bounds, settings, serialization, privacy; macOS fixture;
Windows unsupported; current-host observation; architecture non-edges.

**Physical:** accepted on frozen wheel `3fbf6c83…` — Darwin local/RO/pseudo
and Docker Linux overlay/container (write-probe success + shared
backing). Quota/FUSE specialist residual recorded. Target population is
`MACHI_RELEVANT_STORAGE_TOPOLOGY_BEHAVIOR`, not GPU market share. See
[M2-2.4.1-PHYSICAL.md](M2-2.4.1-PHYSICAL.md).

**Cumulative:** M0 → M1 → 2.1.1 → 2.2.1 → 2.3 → 2.5.1 → 2.4.1.

**Non-goals (2.4.1):** SAFE storage, Storage Sonar, quota specialists,
ownership inference, HostProfile, remount, reclaim, customer-tree
walk, Windows native reader.

**Unlocks:** Steward (`3`).

See [M2-2.4.1.md](M2-2.4.1.md).

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
