# Machi implementation roadmap

**Authority for Machi build sequence.** Derived from
[ARCHITECTURE.md](ARCHITECTURE.md). Strategic stage meaning lives in
[../STRATEGY.md](../STRATEGY.md). Kultrun `docs/ROADMAP.md` remains the
earlier Kultrun sequence only. This document does not renumber itself
to match those four stages.

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

**Objective:** classify caller-supplied roots. Verified ownership
requires the local marker and the registry to agree. Unknown, conflict,
and legacy state are preserved. A reclaimable result is a candidate,
not a deletion.

**Inputs:** known roots; Install marker, registry, and InstallRecord;
optional `MountObservation` from 2.4. Does not re-run mount discovery
and does not consume Capacity.

**Outputs:** `OccupancyMap`. Events `steward.resource.classified`,
`steward.ownership.conflict`, `steward.occupancy.observed`,
`steward.reclaimability.assessed`. No Store entity. No SAFE bytes.

**Telemetry:** those four events, `operational`, without root paths.

**Local tests:** dual proof, copied and malformed markers, legacy,
active protection, obsolete candidate left on disk, symlink escape,
hard link, inaccessible tree, shared backing, typed defaults.

**Physical:** disposable filesystem fixtures on an owned host. No GPU.
No deletion of ambiguous trees.

**Cumulative:** M0 → M1 → 2.1.1 → 2.2.1 → 2.3 → 2.5.1 → 2.4.1 → 3.

**Acceptance:** verified roots report occupancy; conflict fails closed;
obsolete unprotected is a candidate and the bytes remain.

**Non-goals:** automatic GC, pressure cleanup, SAFE storage, mount
crawl, path-name ownership, model or runtime lifecycle.

**Unlocks:** Capacity (`4`).

See [M3.md](M3.md).

---

## M4 — Capacity

**Milestone ID:** `M4`  
**Architecture IDs:** `4`, `4.1`–`4.5`

**Objective:** a SAFE planning envelope. RAM, execution limit,
per-device accelerator memory, and storage stay separate. Reported,
proven, and SAFE stay distinct. Bounded Storage Sonar is included.
It corroborates or contradicts. It does not inflate, and it is not a
±10% agreement test.

**Inputs:** Discover memory, accelerators, and mounts; optional
Steward occupancy; optional specialist and administrator bounds.

**Outputs:** `CapacityEnvelope`. Events `capacity.observed`,
`capacity.safe_envelope.derived`, `capacity.storage_sonar.completed`.
No Store entity. No admission.

**Telemetry:** those events, `operational`, without paths.

**Local tests:** execution limit, reserves, separate GPUs, unified
memory, shared backing, specialist override, Sonar corroboration,
contradiction, non-inflation, administrator bound, exclusive probe
cleanup.

**Physical:** disposable filesystem and the current host. No production
GiB Sonar writes. No GPU pod unless a later case needs one.

**Cumulative:** M0 → M3 → 4.

**Acceptance:** SAFE is smaller than a contradicted report; default
evaluation does not write a probe file.

**Non-goals:** ResourceManager, placement, vLLM tuning, the 20%
deployment retry ladder, every filesystem specialist, automatic
cleanup of reclaim candidates.

**Unlocks:** Foundation (`5`).

See [M4.md](M4.md).

---

## M5 — Foundation

**Milestone ID:** `M5`  
**Architecture IDs:** `5`, `5.1`–`5.6`

**Objective:** one selected, provisioned, verified execution
foundation. `FoundationSelection` names the family and the engine.
Native process is first-class. Docker is optional and not implemented.
`VllmExecutionMacropath` is PRIMARY. `OllamaExecutionMacropath` is the
compatibility fallback and is not implemented here. AUTO selects
supported native vLLM and otherwise returns a typed refusal. Explicit
vLLM fails closed. Dynamo stays a deferred Stage-2 family. None of
these paths own host or admission truth.

**Inputs:** HostProfile, CapacityEnvelope, HostMinimumVerdict PASS.

**Outputs:** `FoundationSet`, `FoundationSelection`,
`RuntimeInstallation`, `RuntimeCapability`.

**Telemetry:** `foundation.inspected`, `foundation.selected`.
Operational only. No paths and no package credentials.

**Local tests:** executor ⟂ runtime; CONDITIONAL product is
selectable; container unsupported is FILTERED not selected.

**Status:** `DEVELOPMENT_CLOSED`. NVIDIA CUDA is
`QUALIFIED`. AMD ROCm is `IMPLEMENTED_UNQUALIFIED`. Outstanding gate:
`M-5-AMD-01`. Instance `READY` is not provider qualification.

**Physical:** NVIDIA CUDA passed on an A40. AMD MI300X / gfx942
qualification of the then-approved native vLLM recipe is deferred.
No model download and no server. llama.cpp/MLX remain deferred.

See [M5.md](M5.md) and [M5-PHYSICAL.md](M5-PHYSICAL.md).

**Cumulative:** M0 → M5.

**Acceptance:** selected ≠ recommended may differ; verification
VERIFIED; installation bytes recorded.

**Non-goals:** serving a model.

**Unlocks:** Model. Blocks 6–9 may use the qualified NVIDIA CUDA
native vLLM path as the development reference. Their contracts stay
generic. AMD public or commercial support stays blocked until
`M-5-AMD-01` closes.

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

---

# 6. Strategic stage map

[../STRATEGY.md](../STRATEGY.md) is the strategy. This table only places
existing components. Classifications do not reopen accepted checkpoints.

| Component | Class | Strategic stage | Reason |
|---|---|---|---|
| M0 Kernel | KEEP | 1 | Event, privacy, and provenance spine |
| M1 Install | KEEP | 1 | Install identity before host facts |
| M2 Discover, including 2.4 Mounts and 2.5 PrerequisiteReadiness | KEEP | 1 | Host and mount truth; readiness is not discovery |
| M3 Steward | KEEP | 1 | Ownership before capacity. Accepted at Tier 2 |
| M4 Capacity | KEEP | 1 | SAFE bytes are the only storage authorization. Accepted at Tier 2 |
| M5 Foundation | MODIFY | 1 | Development closed. NVIDIA CUDA qualified. AMD ROCm implemented, qualification deferred (`M-5-AMD-01`) |
| M6 Model | KEEP | 1 | Local implementation. Physical NVIDIA acceptance still required before close. AMD stays `M-5-AMD-01` |
| M7 Plan | KEEP | 1 | Plan is not admission and not launch |
| M8 Admit | KEEP | 1 | ResourceManager remains the only admission authority |
| M9 Serve | KEEP | 1 | One real request path. Comparative campaigns are Stage 2 |
| OllamaExecutionMacropath | REPOSITION | 1 exit | Compatibility fallback after the vLLM path. Not before Capacity |
| Acceptance lab, coverage-driven physical tests | KEEP | 1–2 | Evidence infrastructure already exists. It is not a benchmark warehouse |
| Dynamo | DEFER | 2 | Fabric family. No integration until the evidence in strategy |
| Additional engines (llama.cpp, MLX, SGLang, TensorRT-LLM) | DEFER | 1–2 | Catalogue entries when a coverage gap is real |
| Gateway, Admin UI, Knowledge/RAG | DEFER | 3 | Attach after a dependable serve path |
| Organisational nouns, usage analytics beyond the local event | DEFER | 3 | Typed context before logs are mined. No analytics UI now |
| Team Brain, memory, agents, learned routing | DEFER | 4 | Downstream of inference, identity, and knowledge |
| Marketplace, fleet, licensing backend | DEFER | 3–4 | Not part of the spine |
| Untracked `docs/machi/proposals/MACROPATH-*.md` | not adopted | — | Superseded where they disagree with vLLM primary / Ollama fallback |
