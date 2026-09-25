# Machi contracts

**Role:** supporting. Semantics live in [ARCHITECTURE.md](ARCHITECTURE.md).
This is the named chain a milestone can test.

Contracts reference other entities **by identifier**, not by import.
Unknown is `Unresolved`, never zero, never a pass.

---

# 1. Semantic categories

| Category | Meaning | Example |
|---|---|---|
| Observation | Raw or adapter-normalized fact about the world | `HostObservation`, `MountObservation` |
| Readiness | Environment usability of a selected prerequisite | `PrerequisiteReadinessReport` |
| Profile | Machi-owned normalization | `HostProfile` |
| Evidence | Measurement with provenance | `CapacityEvidence` |
| Inventory | Owned bytes and their class | `OccupancyMap` |
| Envelope | Policy interpretation of evidence | `CapacityEnvelope` |
| Feasible set | What remains possible | `FoundationSet`, `AvailableModels` |
| Recommendation | Ranked preference, not authority | `FoundationRecommendation` |
| Selection | Chosen alternative (AUTO or MANUAL) | `FoundationSelection`, `ModelSelection` |
| Artifact | Durable acquired object | `ModelArtifact`, `RuntimeInstallation` |
| Configuration | Authoritative intended execution | `DeploymentConfiguration` |
| Request | What admission is asked to grant | `ResourceRequest` |
| Reservation | What admission granted | `ResourceReservation` |
| Runtime state | Desired vs observed serving | `ServingInstance` |
| Proof | Bounded real result | `InferenceProof` |
| Witness | Read-time projection | `DeploymentWitness` |
| Event | Immutable record that something happened | `EventRecord` |

Recommendation never authorizes. Reservation never launches.

---

# 2. Main contract chain

```text
StateRootBinding
    → LocalOwnershipEstablishment   (1.3.1 local marker only; not dual proof)
    → LocalOwnershipRegistryRecord   (1.3.2 local control-plane registry; not dual proof)
    → InstallRecord
    → HostProfile
    → OccupancyMap
    → CapacityEnvelope
    → FoundationSet
    → FoundationSelection
    → RuntimeInstallation + RuntimeCapability
    → AvailableModels
    → ModelSelection + ModelArtifact
    → DeploymentConfiguration
    → ResourceRequest
    → ResourceReservation
    → ServingInstance
    → InferenceProof
    → DeploymentWitness
```

Every arrow is an explicit producer/consumer pair. Changing an
upstream contract **invalidates** dependents (see §4). It does not
rewrite them in place.

---

# 3. Contract catalogue (core)

Persist paths in this table describe the **current FileStore / JSONL
adapters**, not a rule that Kernel Store or Journal must be a
filesystem. `.machi-owner.json` is 1.3.1 local evidence, not a Store
entity.

| Name | Producer | Consumers | Category | Persist | Provenance required |
|---|---|---|---|---|---|
| `EventRecord` | every block | journal, Witness, export | Event | append-only | emitter Block ID + payload version |
| `StoreProof` | 0.4.1 proof CLI | Kernel Store proof only | Proof / test | `<store>/<kind>/<key>.json` | opaque token; not RegistrySeed |
| `StateRootBinding` | 1.2.1 StateRootBinder | 1.3.1, 1.3.2, 1.1.1, 1.4.1, composition | Profile / location | directory exists; contract is returned, not an entity file yet | selection source |
| `LocalOwnershipMarker` | 1.3.1 SelfOwnershipMarker | 1.3.2, composition, later Steward | Evidence (local only) | `.machi-owner.json` | schema, product `machi`, `marker_id`, root fingerprint |
| `LocalOwnershipEstablishment` | 1.3.1 SelfOwnershipMarker | 1.3.2, composition; never Steward delete | Evidence (local only) | no; result of establish | `dual_ownership=false`, `destructive_authorization=false` |
| `LocalOwnershipRegistryRecord` | 1.3.2 RegistrySeed | composition; later Steward evaluator | Evidence (control-plane registry) | injected Store `<kind>/<marker_id>.json` | same `marker_id` + root fingerprint as 1.3.1; not `OwnershipRecord` |
| `LocalOwnershipRegistryEstablishment` | 1.3.2 RegistrySeed | composition; never Steward delete | Evidence (control-plane registry) | no; result of seed | `registry_seed_present`; `dual_ownership=false`; `destructive_authorization=false` |
| `InstallRecord` | 1.1.1 InstallIdentity | 1.4.1, later Blocks | Profile | injected Store `<kind>/<marker_id>.json` | `InstallId`; marker/root correlation; creation-build provenance (not current version) |
| `InstallRecordEstablishment` | 1.1.1 InstallIdentity | composition | Profile | no; result of establish | `install_record_present`; `dual_ownership=false`; `destructive_authorization=false` |
| `InstallRunRecord` | 1.4.1 InstallRunStore | EventRecord.correlation | Profile | injected Store `<kind>/<install_id>.json` | `InstallRunId`; InstallId correlation; creation-build provenance (not current version) |
| `InstallRunEstablishment` | 1.4.1 InstallRunStore | composition | Profile | no; result of establish | `install_run_present`; `dual_ownership=false`; `destructive_authorization=false` |
| `OSArchitectureObservation` | 2.1.1 OS/arch adapter | Discover events; later HostProfile | Observation | no | adapter id; raw + normalized OS/arch; unobserved vs unrecognized |
| `MemoryObservation` | 2.2.1 Memory observer | Discover events; later HostProfile / Capacity | Observation | no | physical_total_bytes; source; not safe allocatable |
| `AcceleratorObservation` | 2.3 Native accelerator observer | Discover events; later HostProfile / Capacity | Observation | no | devices + provider reports; topology; not safe VRAM |
| `AcceleratorDevice` | 2.3 providers via native observer | `AcceleratorObservation` | Observation | no | per-device identity/model/topology/memory; never aggregated |
| `AcceleratorProviderReport` | 2.3 native observer | `AcceleratorObservation` | Observation | no | observed / not_applicable / unavailable / failed; not a device count synonym |
| `PrerequisitePolicy` | 2.5.1 composition | PrerequisiteReadiness | Configuration (selected/desired) | no | mode + dependency source + provenance |
| `PrerequisiteSetting` | 2.5.1 policy/adapter | command-center later; optimizer later | Configuration | no | value, provenance, reason, bounds, support, mutability, invalidation |
| `PrerequisiteTarget` | 2.5.1 adapter | inspection/plan/report | Profile | no | target id + adapter id; not a GPU |
| `PrerequisiteInspection` | 2.5.1 adapter | diagnosis, report | Observation | no | executable/interpreter facts; readiness; paths stay off events |
| `PrerequisiteDiagnosis` | 2.5.1 adapter | plan, report | Evidence | no | diagnosis code; remediable flag; unknown ≠ missing |
| `PrerequisitePlan` / `PrerequisiteAction` | 2.5.1 adapter | remediate, report | Recommendation | no | allowlisted actions only; `NO_OP` when READY |
| `RemediationResult` / `VerificationResult` | 2.5.1 adapter | report | Proof | no | mutation never assumed successful |
| `PrerequisiteReadinessReport` | 2.5.1 orchestration | CLI, later composition | Readiness | no | before/after readiness; inspectable settings; mutated flag |
| `HostObservation` | 2 adapters | Discover | Observation | optional raw | adapter name, tool version |
| `HostProfile` | 2 Discover | Capacity, Foundation, Admit | Profile | yes | observation IDs |
| `MountObservation` | 2.4.1 Mount enumerator | Discover events; later Steward / Capacity | Observation | no | mount topology; reported total/free/available flagged as not SAFE; backing identity or Unresolved; not ownership |
| `OwnershipRecord` | 3.1 | Steward, reclaim | Inventory | yes | dual proof (local marker **and** registry). Not the 1.3.1 contract. |
| `OccupancyMap` | 3.2 | Steward, Capacity remaining | Inventory | yes | classifier version |
| `ReclaimPlan` / `ReclaimResult` | 3.3 | Capacity recharacterize | Inventory | yes | dual-owned roots only |
| `CapacityEvidence` | 4.2 | Envelope | Evidence | yes | pool identity, method, bounds |
| `CapacityEnvelope` | 4.3 | Feasibility, Foundation, Model, Admit | Envelope | yes | evidence IDs, policy version |
| `HostMinimumVerdict` | 4.5 | Install progress, Foundation | Feasible set / gate | yes | profile version, realize-time bytes |
| `FoundationSet` | 5.3 | Select | Feasible set | yes | HostProfile + Envelope IDs |
| `FoundationSelection` | 5.6 | Provision, Plan | Selection | yes | recommended vs selected |
| `RuntimeInstallation` | 5.4 | Verify, Plan | Artifact | yes | exact version, path, size |
| `RuntimeCapability` | 5.5 | Model funnel | Profile | yes | verify method |
| `ModelCatalogView` | 6.1 | funnel | Observation | derived | catalog generation |
| `AvailableModels` | 6.3 | Select | Feasible set | yes | Envelope + RuntimeCapability IDs |
| `ModelSelection` | 6.4 | Plan, Acquire | Selection | yes | mode AUTO/MANUAL |
| `ModelArtifact` | 6.5 | Plan, Serve | Artifact | yes | digest, bytes, source |
| `DeploymentConfiguration` | 7 Plan | Admit, Serve | Configuration | yes | CURRENT vs STALE |
| `ResourceRequest` | 7→8 | Admit | Request | yes | configuration ID |
| `CapacityEnvelope` (current snapshot) | 8.1 | Admit | Envelope (now) | yes | evidence id |
| `ResourceReservation` | 8.2 | Serve | Reservation | yes | request ID, devices |
| `ServingInstance` | 9.1 | Serve, Witness | Runtime state | yes | configuration + reservation IDs |
| `ReadinessProof` | 9.3 | Serve | Proof | yes | not a user inference |
| `InferenceProof` | 9.4 | Witness, usage | Proof | yes | purpose=request; no prompt text |
| `DeploymentWitness` (`kernel.deployment_witness`) | 0.6.1 | CLI, API, Admin | Witness | derived | cited install, capacity, foundation, model, plan, reservation, instance, and proof ids; no customer content |

Lifecycle: observations and events are immutable. Profiles and
selections are replaced by a new generation when invalidated.
Reservations are released only by explicit release, not by stop.

Versioning: `kind` + integer version, same as Kultrun `contract()`.
A change of meaning keeps a new version. Name reuse with a new
meaning is a human-reviewed event (Kultrun K-05).

`LocalOwnershipMarker` is not `OwnershipRecord`. Steward 3.1 keeps that
name for dual-proof inventory. 1.3.1 status is `local_marker_present`.
1.3.2 status is `registry_seed_present`. Neither is `ownership.verified`.

The 1.3.2 registry is the local customer Machi control plane. It is not
a vendor cloud service. The registry Store is injected; it is not the
same authority as `.machi-owner.json`.

`InstallRecord` is keyed by that same `marker_id`. Build fields on it
are the creating artifact's provenance. Artifact SHA is omitted: Kernel
`BuildIdentity` does not carry a wheel hash, and 1.1.1 does not invent
one.

The Kernel `Store` port is not a domain contract. Callers persist their
own versioned contracts under caller-owned keys. `StoreProof` exists
only to prove 0.4.1; it is not a registry record.

---

# 4. Invalidation

```text
HostProfile changes
    invalidates CapacityEnvelope, FoundationSet, AvailableModels,
    DeploymentConfiguration (STALE), not a live reservation until re-admit

OccupancyMap / ReclaimResult changes
    invalidates remaining in CapacityEnvelope; may require recharacterize

CapacityEnvelope changes
    invalidates HostMinimumVerdict, FoundationSet, AvailableModels, Plan

FoundationSelection or RuntimeCapability changes
    invalidates AvailableModels, Plan

ModelSelection or ModelArtifact changes
    invalidates Plan

DeploymentConfiguration STALE
    invalidates ResourceRequest; existing reservation must not be
    reused for a different configuration

Stop ServingInstance
    does not invalidate Reservation or Plan
```

Recompute is **explicit and directed**, not a workflow engine. The
control plane (composition root) sequences invalidation. Domains do
not import each other to “refresh the world.”

---

# 5. Diagram D — contract flow

```mermaid
flowchart LR
  IR[InstallRecord] --> HP[HostProfile]
  HP --> OM[OccupancyMap]
  OM --> CE[CapacityEnvelope]
  CE --> FS[FoundationSet]
  FS --> FSel[FoundationSelection]
  FSel --> RC[RuntimeCapability]
  RC --> AM[AvailableModels]
  AM --> MS[ModelSelection]
  MS --> DC[DeploymentConfiguration]
  DC --> RR[ResourceRequest]
  RR --> Res[ResourceReservation]
  Res --> SI[ServingInstance]
  SI --> IP[InferenceProof]
  IP --> DW[DeploymentWitness]
  EV[EventRecord] -.-> IR
  EV -.-> HP
  EV -.-> OM
  EV -.-> CE
  EV -.-> FSel
  EV -.-> MS
  EV -.-> DC
  EV -.-> Res
  EV -.-> IP
```
