# AI STACK — TECHNICAL ROADMAP

**Status:** Authoritative build sequence
**Supersedes:** [`docs/source/COMPANY_BRAIN_TECHNICAL_PRODUCT_ROADMAP_V1.md`](source/COMPANY_BRAIN_TECHNICAL_PRODUCT_ROADMAP_V1.md)

This document states **what each stage builds**. The reasoning behind the ordering — the evaluation
criteria, the ten design tensions, the artifact spine, the invariants and the gates — is in
[`docs/BUILD_ARCHITECTURE.md`](BUILD_ARCHITECTURE.md). Read that first; this
document assumes it.

Governing documents: the charter
[`docs/REBUILD_CONTEXT.md`](REBUILD_CONTEXT.md), the constitution
[`docs/source/COMPANY_BRAIN_PLATFORM.md`](source/COMPANY_BRAIN_PLATFORM.md), and the operating
contract [`docs/DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md).

---

## HOW TO READ A STAGE

Every stage uses the same block. Uniformity is deliberate: it makes the sequence auditable in both
directions.

- **Goal** — the one capability this stage adds.
- **Consumes** — predecessor artifacts. A stage cannot begin before these exist (invariant I6).
- **Builds** — core concepts and adapters.
- **Artifact** — the persisted, versioned, inspectable output (invariant I1: exactly one producer).
- **Proof** — capability demonstration, negative proof, and recovery proof where the stage mutates
  state (invariant I5).
- **Level** — acceptance level L1–L4, operating contract §8. Use the lowest sufficient level.
- **Obligations** — which standing obligations this stage discharges.
- **Provisional / Deferred** — approximations to revisit, and sophistication deliberately postponed.

Each stage closes with a Stage Output Package:

```text
docs/stages/STAGE-XX-<name>.md
checkpoints/STAGE-XX-<name>.json
```

and a PASTE BACK per operating contract §10, then STOPS.

---

# PHASE 0 — FOUNDATION

*Proves: the platform knows the machine it is on, safely and with evidence.*

---

### S01 — Control plane skeleton and platform contracts

**Goal.** A running control plane with a versioned Platform API, and the kernel contracts every
later stage depends on — shaped by a real consumer rather than speculation.

**Consumes.** Nothing. Root of the spine.

**Builds.** Module boundaries and the core/adapter split. Stable IDs and schema versioning. The
`Decision` envelope — `{ outcome, reason_code, evidence[], assumptions[], confidence, remedies[] }` —
used by every judgement in the platform. `AccessContext`, carried by every platform call from the
first one, with a single local administrator principal. Domain event envelope, from which
`AuditEvent` derives. Replaceable persistence with versioned migrations. The artifact store. Typed
error taxonomy. The CLI entry point.

**Artifact.** `artifacts/platform-state.json` — `PlatformState v1`.

**Proof.**
`ai-stack status` returns versioned state on a bare machine. *Negative:* an unmigratable state
version is refused with a `Decision`, not silently coerced. *Recovery:* interrupted migration leaves
the prior version intact and readable.

**Level.** L1.

**Obligations.** Establishes audit, decision, persistence and migration. Health registry created.

**Provisional.** Single local principal; no authentication.
**Deferred.** Multi-user identity (S20), authorization policy (S20), SSO.

---

### S02 — Host capability detection

**Goal.** A normalized, accurate account of the machine, and the fingerprint everything downstream
is keyed to.

**Consumes.** `PlatformState v1`.

**Builds.** `HostDetector` and `HostCapabilities`: OS, version, architecture, virtualization; CPU;
RAM including unified memory; accelerators — vendor, count, memory, driver and runtime versions;
storage identity; execution capabilities (native, Docker, Podman); network and ports. Plus
**`HostFingerprint`** — stable across reboots, changing when hardware changes.

Reference implementation Linux x86_64 + NVIDIA. Recorded artifacts from other host classes become
golden fixtures for CPU-only, Apple Silicon, AMD and Windows-via-Linux-VM paths.

**Artifact.** `artifacts/host-capabilities.json` — `HostCapabilities v1`.

**Proof.**
`ai-stack host inspect` on a real machine produces an artifact matching independently observed
hardware. *Negative:* an undetectable accelerator yields `unknown`, never a guess — constitution
§5.4, and operating contract "unknown is valid". *Recovery:* n/a, read-only.

**Level.** L2 — real host required.

**Obligations.** Health registration for the detector. Fingerprint stamping for all later artifacts.

**Provisional.** Accelerator detection via vendor tooling where present.
**Deferred.** Topology and interconnect detail; multi-host (S45).

---

### S03 — Component resolution and host preparation

**Goal.** One product-owned command brings a bare supported host to readiness, idempotently.

**Consumes.** `HostCapabilities v1`.

**Builds.** Versioned `ComponentManifest` — version, supported OS and architecture, accelerator
compatibility, dependencies, source, checksum, signature, license, install method — and
`ComponentResolver`. `EgressPolicy` seam and `SecretStore` seam, both first needed here. Check,
reuse, repair, verify (operating contract §18): never redownload blindly.

**This is the product installer's engine**, not a developer harness. It gains a friendly front end
at S36; it is never rewritten.

**Artifact.** `artifacts/resolved-components.json` — `ResolvedComponentSet v1`,
`artifacts/bootstrap-assessment.json` — `BootstrapAssessment v1`.

**Proof.**
`ai-stack prepare` on a bare host reaches readiness; run twice, the second is a no-op. *Negative:* an
incompatible component is refused with a reason code and alternatives, not force-installed. A
checksum mismatch aborts. With egress disabled, it reports precisely what it cannot obtain rather
than hanging. *Recovery:* interrupted provisioning resumes without duplicate work or partial installs.

**Level.** L2.

**Obligations.** Egress declared and enforced. Secrets via `SecretStore`. Reconciler for partial
installs. Health. Audit for every mutation.

**Provisional.** Curated component set.
**Deferred.** Signed offline bundles (S37), rollback (S37).

---

### S04 — Host storage characterization

**Goal.** Establish what the machine can safely offer for platform storage, before any model is
considered.

**Consumes.** `HostCapabilities v1`.

**Builds.** The capacity chain: credible remaining host capacity → protected reserve → safe
allocatable → administrator allocation → platform budget → current managed usage → remaining budget.

**Decision-bounded by construction.** The previous project's characterization ran ~48 minutes
without converging because it searched for the pool ceiling instead of stopping once evidence
answered the question, lost all evidence on interruption, and orphaned a 42,990 MiB temporary file
from a daemon thread. AI Stack's: bounded by the question asked, persisting evidence continuously,
resumable, never running unbounded work in a request thread, and owning every temporary file through
a lock with guaranteed cleanup.

Filesystem-reported free space is one input signal, never the budget — network and overlay
filesystems routinely report a shared volume rather than the usable quota.

**Artifact.** `artifacts/storage-capacity.json` — `StorageCapacity v1` (HOST scope; never conflated
with transaction admission, S11).

**Proof.**
`ai-stack storage assess` produces a bounded, evidenced budget within a stated time envelope.
*Negative:* where evidence is insufficient it reports low confidence and a conservative floor rather
than an optimistic ceiling. *Recovery:* interrupt mid-probe — evidence to that point survives, the
lock releases, no temporary file is orphaned.

**Level.** L2.

**Obligations.** Reconciler for managed usage and staging. Lock with guaranteed cleanup. Health.

**Provisional.** Conservative reserve heuristics.
**Deferred.** Calibration learning (S39); performance class detection.

> ### GATE G1 — HOST TRUTH (L2)
> The platform's account of the machine is accurate, bounded and evidenced; unknowns are declared as
> unknown. Reverse audit: every artifact traces to exactly one producing stage.

---

# PHASE 1 — MODEL KNOWLEDGE

*Proves: it can decide what it could run, without downloading anything.*

---

### S05 — Model source and normalized metadata

**Goal.** Discover and describe models, **without fetching weights**.

**Consumes.** `PlatformState v1`.

**Builds.** `ModelSource` with **metadata-only resolution as a distinct capability from artifact
acquisition** (build architecture T6). Adapters: Hugging Face, local files. Normalization to
platform-owned `ModelMetadata` and `ModelArtifact` — canonical ID, source, immutable revision,
family, architecture, parameters, modalities, context, formats, quantization, file manifest with
sizes, license and commercial restrictions, provenance.

No provider type crosses the core boundary (invariant I8). Hugging Face is not the domain model.

**Artifact.** `artifacts/model-catalog-snapshot.json` — `ModelCatalogSnapshot v1`.

**Proof.**
`ai-stack model describe <id>` returns full normalized metadata with **zero weight bytes
transferred** — asserted by measuring transfer. *Negative:* a gated model without credentials reports
gated access and the remedy, rather than failing opaquely. A model with unresolvable metadata is
marked incomplete, not guessed. *Recovery:* n/a, read-only.

**Level.** L1 with fixtures; L2 against the live source.

**Obligations.** Egress declared. Source credentials via `SecretStore`.

**Provisional.** Curated candidate set, not a marketplace.
**Deferred.** Additional sources; enrichment; marketplace UI (S24).

---

### S06 — Model requirements

**Goal.** Turn metadata into what this model would demand, split by the two questions it answers.

**Consumes.** `ModelCatalogSnapshot v1`.

**Builds.** **`StorageRequirement`** — resident bytes, file set, staging peak, conversion and
temporary overhead. Admission is judged on **peak additional storage**, not final size.
**`RuntimeRequirement`** — weights memory, activations, KV cache, runtime overhead, context
assumptions, runtime compatibility, with explicit assumptions and confidence.

The split resolves V1's cross-milestone dependency: storage requirements belong to the supply chain,
runtime requirements to capacity.

**Artifact.** `artifacts/model-requirement-<id>.json` — `ModelRequirement v1`.

**Proof.**
Requirements computed from metadata alone for several model classes. *Negative:* unknown runtime
detail stays unknown and lowers confidence; it is never defaulted to a plausible number. *Recovery:*
n/a.

**Level.** L1.

**Obligations.** `Decision` envelope for every estimate, carrying assumptions.

**Provisional.** Conservative analytic estimation.
**Deferred.** Observed calibration (S39).

---

### S07 — Capacity evidence

**Goal.** A provider seam for capacity estimates that the platform normalizes and never delegates
authority to.

**Consumes.** `HostCapabilities v1`, `ModelRequirement v1`.

**Builds.** `CapacityEvidenceProvider` with a required internal conservative estimator.
`CapacityEvidence` normalizes provider, version, evidence type, model and revision, host
fingerprint, runtime and configuration, memory breakdown, context, concurrency, throughput,
confidence, assumptions and timestamp. Providers populate only what they know.

**Theoretical and observed evidence are distinguished from the first version**, even though only
theoretical exists yet — retrofitting the distinction later would restructure the contract
(invariant I3).

**Artifact.** `artifacts/capacity-evidence-<id>.json` — `CapacityEvidence v1`.

**Proof.**
Evidence produced by the internal estimator, fingerprint-stamped. *Negative:* an unavailable or
failing provider degrades to internal evidence with lower confidence; it never blocks the platform
(constitution §5.6). *Recovery:* n/a.

**Level.** L1.

**Obligations.** Egress for any external provider. Fingerprint stamping.

**Provisional.** Internal estimator only.
**Deferred.** llmfit (S09, decision D5); Accelerate; benchmark providers (S39).

---

### S08 — Capacity assessment

**Goal.** Answer whether this host can run this model, with reasons and confidence.

**Consumes.** `HostCapabilities v1`, `StorageCapacity v1`, `ModelRequirement v1`,
`CapacityEvidence v1`.

**Builds.** The Capacity Planner. States `Compatible` / `Conditional` / `Unsupported`, with the
recommended runtime, expected storage and memory, safe configured concurrency, coexistence with
current workloads, blockers, alternatives and confidence. Emits the `Decision` envelope, which is
what makes the Admin Agent possible later without bespoke parsing.

**Artifact.** `artifacts/capacity-assessment-<id>.json` — `CapacityAssessment v1`.

**Proof.**
Assessment of several models against the real host, matching independent reasoning. *Negative:* a
model exceeding accelerator memory is `Unsupported` with the specific blocker, and remains so even
if an external provider disagrees — the platform's feasibility result is authoritative (operating
contract §17). *Recovery:* n/a.

**Level.** L2.

**Obligations.** `Decision` for every outcome.

**Provisional.** Single-workload assessment.
**Deferred.** Evidence fusion (S40); SLO concurrency (S40).

---

### S09 — Model evaluation and selection

**Goal.** Rank feasible candidates and recommend one, explainably.

**Consumes.** `CapacityAssessment v1`, `ModelCatalogSnapshot v1`.

**Builds.** `ModelEvaluationProvider` seam and `ModelSelectionResult`. Core owns the deterministic
fallback — closest safe primary memory fit — which always works. llmfit becomes the first adapter,
contributing fit, quality, speed, context and ranking evidence.

**An evaluation provider can never override an infeasible result** (operating contract §17). It
ranks within the feasible set.

**Artifact.** `artifacts/model-selection.json` — `ModelSelectionResult v1`.

**Proof.**
`ai-stack model select` returns a ranked, explained recommendation for the real host. *Negative:*
with the provider unavailable, selection still succeeds via the deterministic rule at lower
confidence. A provider ranking an infeasible model highly does not change the outcome. *Recovery:*
n/a.

**Level.** L2.

**Obligations.** Egress and secrets for external providers.

**Provisional.** Simple ranking.
**Deferred.** Effectiveness-informed selection (S41); portfolio optimization (S43).

> ### GATE G2 — FEASIBILITY (L2)
> The platform decides what it can run, with explanation and confidence, having downloaded no
> weights. Reverse audit from `ModelSelectionResult` back to `HostCapabilities`.

---

# PHASE 2 — CUSTODY

*Proves: it can take safe custody of an artifact and recover from interruption.*

---

### S10 — Model inventory and lineage

**Goal.** A durable record of every platform-managed artifact.

**Consumes.** `ModelCatalogSnapshot v1`.

**Builds.** Inventory keyed by `(canonical_id, revision, format, quantization)` so quantizations
never collide. States: discovered, remote, acquiring, stored, validating, loaded, running, stopped,
updating, deprecated, incompatible, derived. Location, size, checksum, source, revision, runtime
compatibility, last use, resource association.

**Lineage fields exist from v1** — parent model and revision, derivation type, owner and team,
dataset snapshot reference, evaluation and promotion state — because adding them later restructures
the record (invariant I3). Nothing populates them until S44.

**Artifact.** `artifacts/model-inventory.json` — `ModelInventory v1`.

**Proof.**
Inventory survives restart and reflects real on-disk state. *Negative:* a record whose files are
missing is marked inconsistent, not silently deleted — constitution "do not delete incompatible
artifacts". *Recovery:* inventory and filesystem diverge; reconciliation repairs or fails
conservatively.

**Level.** L1/L2.

**Obligations.** Reconciler. Audit. Migration.

**Provisional.** Local filesystem store.
**Deferred.** Derived artifacts (S44).

---

### S11 — Transaction storage admission

**Goal.** Prove one specific mutation is safe at commit time.

**Consumes.** `StorageCapacity v1` (HOST), `StorageRequirement` from `ModelRequirement v1`,
`ModelInventory v1`.

**Builds.** Admission against remaining platform budget using **peak additional requirement**.
Explicit mutation lock; staging area; preflight; rollback semantics.

**TRANSACTION scope, structurally distinct from HOST scope (S04).** A transaction result may never
be promoted into a field claiming a host ceiling (build architecture T5).

**Artifact.** `artifacts/storage-admission-<op>.json` — `StorageAdmissionDecision v1`.

**Proof.**
Admission granted for a model that fits. *Negative:* refused for one that does not, with the
shortfall quantified; refused when peak staging exceeds budget even though final size fits — the
case naive implementations miss. *Recovery:* lock released on abort; no orphaned staging.

**Level.** L2.

**Obligations.** Lock. Reconciler for staging. Audit.

**Deferred.** Multi-operation scheduling.

---

### S12 — Safe acquisition

**Goal.** Take custody of a model artifact, safely and recoverably.

**Consumes.** `ModelSelectionResult v1`, `StorageAdmissionDecision v1`, `ModelInventory v1`.

**Builds.** Resolve immutable revision → storage admission → lock → stage → transfer → integrity
validation → commit → inventory reconciliation. Resumable transfers, revision pinning, authenticated
and private sources, clean rollback.

**Feasibility gates acquisition** (build architecture T6): a model that cannot run is not acquired
without an explicit administrator override, which is recorded.

**Artifact.** Stored `ModelArtifact` plus `artifacts/acquisition-receipt-<id>.json` —
`AcquisitionReceipt v1`.

**Proof.**
Acquire a real model end to end; checksums verified; inventory consistent. *Negative:* acquisition
of an `Unsupported` model is refused with the blocker; a corrupted transfer fails validation and
does not commit. *Recovery:* **kill the process mid-transfer** — staging is reconciled, the lock
released, budget accounting correct, and resumption completes without re-transferring verified
bytes.

**Level.** L2.

**Obligations.** Lock, reconciler, audit, egress, secrets. All discharged here.

**Provisional.** Single concurrent acquisition.
**Deferred.** Parallel transfers; mirrors; offline bundles (S37).

> ### GATE G3 — CUSTODY (L2)
> Acquires safely, refuses unsafely, recovers cleanly from interruption. The recovery proof is the
> point of this gate.

---

# PHASE 3 — EXECUTION

*Proves: it serves governed inference, concurrently, and refuses what is unsafe.*

---

### S13 — Executor abstraction

**Goal.** Run processes and services without model semantics leaking in.

**Consumes.** `HostCapabilities v1`, `ResolvedComponentSet v1`.

**Builds.** `Executor` owning process and service execution, environment, filesystem mapping,
signals, logs and process health — **not** model or runtime semantics. `NativeProcessExecutor` first;
Docker is optional and never assumed (constitution §10).

**Artifact.** `ExecutorHandle` in `PlatformState`.

**Proof.**
Start, observe, signal and stop a process; handle survives control-plane restart. *Negative:* an
unavailable executor is reported with alternatives, not silently substituted. *Recovery:* orphaned
processes are reconciled after restart.

**Level.** L2.

**Obligations.** Reconciler for processes. Health. Audit.

**Deferred.** Podman, VM, Kubernetes, remote executors.

---

### S14 — Inference runtime abstraction

**Goal.** Translate platform concepts into runtime-specific configuration, inside the adapter.

**Consumes.** `HostCapabilities v1`, `ResolvedComponentSet v1`.

**Builds.** `RuntimeProfile` — declarative capability descriptor, consumed by planning — split from
`RuntimeLaunchSpec` and the adapter implementation, needed only at launch. First adapter vLLM on
Linux/NVIDIA. Runtime concurrency, memory utilization, tensor parallelism, context and adapter
loading stay inside the adapter (constitution §11).

**Artifact.** `artifacts/runtime-profiles.json` — `RuntimeProfile v1`.

**Proof.**
Profiles enumerated for the host; a launch spec generated for a stored model. *Negative:* an
incompatible model/runtime pairing is refused at spec generation, before any process starts.
*Recovery:* n/a.

**Level.** L1/L2.

**Obligations.** Health.

**Deferred.** llama.cpp, MLX, ROCm, Intel runtimes.

---

### S15 — Deployment planning

**Goal.** One approved, explainable plan describing exactly what will run.

**Consumes.** `HostCapabilities v1`, `ResolvedComponentSet v1`, `ModelInventory v1`,
`CapacityAssessment v1`, `RuntimeProfile v1`.

**Builds.** `DeploymentPlan`: runtime, executor, components, model and revision, resource
requirement, context, configured concurrency, ports, expected resource use, confidence, alternatives
and required approvals. Automatic and manual-override settings, with overrides validated, explained
and recorded (constitution §82).

**Artifact.** `artifacts/deployment-plan-<id>.json` — `DeploymentPlan v1`.

**Proof.**
A complete plan for a real stored model on the real host. *Negative:* an override producing an
unsafe plan is rejected with the violated constraint. *Recovery:* n/a.

**Level.** L2.

**Obligations.** `Decision`. Audit for overrides.

**Deferred.** Multi-host placement (S45).

---

### S16 — Workload contract and Resource Manager

**Goal.** Authoritative admission against live reality, with reservations that outlive any single
process.

**Consumes.** `DeploymentPlan v1`, `HostCapabilities v1`, `StorageCapacity v1`.

**Builds.** Generic `WorkloadSpec` representing inference, embedding, reranking, indexing,
benchmark, training, evaluation, quantization, distillation and agent workers — **only inference and
embedding execute now**, but the job model must not assume inference (constitution §31). Resource
Manager: reserve before mutation, prevent oversubscription, persist and reconcile, release cleanly,
explain denial.

Four quantities kept distinct: requested requirement, admitted reservation, observed consumption,
peak observed consumption.

`configured_concurrency` and `platform_max_concurrent_requests` exist from here; the other three
concurrency dimensions are deferred to S40.

**Artifact.** `artifacts/admission-<id>.json` — `AdmissionDecision v1`;
`artifacts/reservations.json` — `ResourceReservation v1`.

**Proof.**
Reservation granted, persisted, and surviving control-plane restart. *Negative:* a workload
exceeding safe capacity is denied with the specific constraint and the headroom shortfall.
*Recovery:* reservation rolled back when the subsequent runtime start fails, with no leak.

**Level.** L2.

**Obligations.** Reconciler. Audit. Health. `Decision`.

**Provisional.** Single-host; no priority or preemption.
**Deferred.** Training workloads; quotas; scheduling (S44).

---

### S17 — Inference instance lifecycle

**Goal.** A first-class, healthy, controllable model-serving workload.

**Consumes.** `DeploymentPlan v1`, `ResourceReservation v1`, `ExecutorHandle`,
`RuntimeLaunchSpec`, stored `ModelArtifact`.

**Builds.** `InferenceInstance`: identity, host, model and revision, optional adapter, runtime,
executor, endpoint, reservation, context, runtime concurrency, platform request limit, access-policy
reference, lifecycle state, health, configuration version. Start, health, stop, restart, unload,
reconcile.

Distinct from the stored artifact (constitution §12).

**Artifact.** `artifacts/inference-instances.json` — `InferenceInstance v1`.

**Proof.**
A real model starts under Resource Manager control and reports healthy. *Negative:* start refused
without a valid reservation. *Recovery:* stop leaves clean process, port, accelerator and reservation
state; a killed control plane reconciles the running instance on restart rather than orphaning or
double-starting it.

**Level.** L3 — live inference.

**Obligations.** Reconciler. Health. Audit.

**Deferred.** Multi-adapter serving (S44).

---

### S18 — Gateway spine and first governed request

**Goal.** The first inference AI Stack ever performs traverses the platform gateway and is recorded.

**Consumes.** `InferenceInstance v1`, `AccessContext v1`.

**Builds.** The minimal Gateway owning endpoint identity, route decision, request limits and
instrumentation. `UsageEvent` emitted for every request, carrying from v1: timestamp, model and
provider, model revision, inference instance, user, **team**, application, input/output/total
tokens, latency, error, cost, route, **workload label**, **role family**, runtime configuration
version and **host fingerprint**.

The last four are nullable and unpopulated until later phases. They exist now because the
effectiveness dataset (S41) and portfolio optimizer (S43) join on them, and data recorded without
them is permanently unusable (constitution §120).

**No bypass path is created** (build architecture T3, constitution §98).

**Artifact.** `artifacts/usage/` — `UsageEvent v1` stream.

**Proof.**
A real request answered through the gateway by a locally served model, producing a UsageEvent with
correct token accounting. *Negative:* a request naming an unknown or stopped model is refused with a
route decision, not passed through. *Recovery:* an instance failing mid-request produces an error
event, not a lost one.

**Level.** L3.

**Obligations.** Audit. Health. `Decision` for route refusals.

**Provisional.** Single local route; single principal.
**Deferred.** Authentication and policy (S21); external providers (S23); intelligent routing (S42).

---

### S19 — Concurrent instances and safe refusal

**Goal.** Prove the two concurrency dimensions are genuinely separate (constitution §13).

**Consumes.** `AdmissionDecision v1`, `InferenceInstance v1`.

**Builds.** Simultaneous inference-instance concurrency alongside request concurrency. An LLM
instance and an embedding instance running together, each with its own reservation. Explicit,
administrator-approved **stop-to-make-room**.

The embedding instance is not incidental: the knowledge phase depends on it, and discovering at S29
that the capacity model cannot hold two instances would invalidate Phase 3.

**Artifact.** Extended `InferenceInstance v1` and `ResourceReservation v1` sets.

**Proof.**
Two instances serve concurrently with correct per-instance accounting, and requests to both succeed.
*Negative:* an unsafe third is refused with the specific shortfall while the two keep serving —
denial must not disturb running work. *Recovery:* stop-to-make-room frees exactly the expected
resources and the new instance starts.

**Level.** L4 — integrated.

**Obligations.** Reconciler across multiple workloads.

**Provisional.** Administrator-approved eviction only.
**Deferred.** Automatic eviction policy; priority preemption.

> ### GATE G4 — EXOSKELETON (L3/L4)
> A governed request is answered by a locally served model and recorded as usage, with a second
> concurrent instance running and an unsafe third correctly refused. Reverse audit runs the full
> chain from `UsageEvent` back to `HostCapabilities`.

---

# PHASE 4 — GOVERNED ACCESS

*Proves: identity, policy and usage accounting apply to every request.*

---

### S20 — Identity, teams and policy

**Goal.** Real principals and authorization, expanding the kernel's single-principal `AccessContext`
additively.

**Consumes.** `AccessContext v1`.

**Builds.** User, Group, Team, application and service identity, Role, `AccessPolicy`. Typed
`PolicyStore` — one mechanism for admission, access, routing, outbound and model-access policy
rather than five ad-hoc systems. `IdentityProvider` seam kept replaceable for later SSO and SCIM.

**Artifact.** `artifacts/access-context.json` — `AccessContext v2` (additive), `PolicyStore v1`.

**Proof.**
Multiple users and teams resolve to correct contexts and policies. *Negative:* a user without model
access is denied with reason and remedy. *Recovery:* policy store corruption fails closed.

**Level.** L1/L2.

**Obligations.** Audit for identity and policy changes. Migration.

**Deferred.** SSO, SCIM, enterprise directories.

---

### S21 — Gateway v1

**Goal.** Full platform ownership of the AI access layer.

**Consumes.** `AccessContext v2`, `PolicyStore v1`, `InferenceInstance v1`.

**Builds.** Authentication and authorization, model access policy, queueing and limits, application
identity, route decision, instrumentation. `GatewayProvider` adapter seam.

**Artifact.** `artifacts/route-decisions/` — `RouteDecision v1`.

**Proof.**
Authenticated users reach permitted models. *Negative:* unauthenticated requests and requests for
unpermitted models are refused, and the refusal is recorded as a UsageEvent — denials are usage
evidence too. Queue limits shed load rather than exhausting resources. *Recovery:* queued requests
resolve or fail cleanly on instance loss.

**Level.** L3.

**Obligations.** Audit. Health. `Decision`.

**Deferred.** Intelligent routing (S42); Team Brain routing (S44).

---

### S22 — Usage store and local analytics

**Goal.** Durable, queryable usage the administrator owns.

**Consumes.** `UsageEvent v1`.

**Builds.** Replaceable `UsageAnalyticsStore`. Time-partitioned local storage, `RetentionPolicy`,
approximately seven days on the basic tier. Summary and filtering by time, model, provider, user and
team. The gateway emits without knowing how events are persisted.

**Artifact.** `LocalUsageStore v1`.

**Proof.**
Events persist, survive restart, and aggregate correctly. *Negative:* retention prunes on schedule
and never deletes outside its window. *Recovery:* a store failure degrades to buffered emission
rather than dropping requests.

**Level.** L2.

**Obligations.** Reconciler. Migration. Health.

**Deferred.** Long-term retention as an entitlement (S35); cloud export (S34).

---

### S23 — External provider federation

**Goal.** One gateway API serving local and external inference identically.

**Consumes.** `RouteDecision v1`, `PolicyStore v1`.

**Builds.** One external path, initially via LiteLLM **behind** the platform gateway. It must not
become authoritative for identity, route semantics, model identity, UsageEvent, permissions,
Resource Manager or cost normalization (charter §8).

**Artifact.** External `InferenceEndpoint v1`.

**Proof.**
The same client call reaches a local or external model with identical envelopes and comparable
UsageEvents. *Negative:* with the external provider unreachable, local inference is unaffected
(constitution §5.6); with egress disabled, external routes are unavailable and clearly reported.
*Recovery:* provider failure mid-request yields a clean error event.

**Level.** L3.

**Obligations.** Egress. Secrets. Cost normalization into `UsageEvent`.

**Deferred.** Multi-provider cost optimization (S42).

---

# PHASE 5 — OPERATIONS

*Proves: an administrator can see, act, restart, and move to another machine.*

---

### S24 — Platform API consolidation and Admin UI

**Goal.** Every capability built so far, visible and controllable through one structured API.

**Consumes.** All prior artifacts.

**Builds.** Consolidated Platform API. Admin console: Host, Capacity, Catalog, Inventory, Inference
Instances, Reservations, Gateway, Usage, Users and Teams, Health, Configuration. Automatic and
manual-override settings showing recommendation, reason and confidence. The UI contains no
infrastructure logic (constitution §98).

**Proof.**
Every earlier artifact is inspectable and every earlier action performable through the UI.
*Negative:* an action the principal is not authorized for is unavailable and refused server-side.
*Recovery:* the UI degrades to read-only when the control plane is unhealthy.

**Level.** L4.

**Obligations.** Audit for UI-initiated mutations.

**Deferred.** Marketplace UX; dashboards (S41).

---

### S25 — Admin AI Agent v1

**Goal.** Conversational administration over structured APIs, working even before a local model
exists.

**Consumes.** Platform API, `Decision` envelopes from every stage.

**Builds.** `PlatformIntelligenceProvider` with three implementations (build architecture T7):
deterministic guided mode, external BYO-key, and gateway-backed local. Structured tools: explain
host, explain capacity and recommendation, search catalog, prepare acquisition, prepare start and
stop, explain health and errors, explain usage and routing. Risk model: read-only needs no approval;
low-risk mutation follows policy; **meaningful mutation requires explicit administrator approval**.

**No unrestricted shell access, and no backdoor** — the agent uses the same API as the UI.

**Proof.**
The agent explains real host, capacity and recommendation from live `Decision` evidence, and
proposes an installation for approval. *Negative:* it cannot perform a meaningful mutation without
approval, and cannot read what the principal cannot. With no LLM available it degrades to guided
mode rather than failing. *Recovery:* an abandoned proposal leaves no partial mutation.

**Level.** L4.

**Obligations.** Audit for every agent-initiated action, recording the approval.

**Provisional.** Narrow tool set.
**Deferred.** Conversational onboarding (S36); autonomous action.

---

### S26 — Reconciliation orchestration and restart

**Goal.** Restart is idempotent and coherent across every stateful subsystem.

**Consumes.** Every reconciler registered by its own stage (invariant I7).

**Builds.** The orchestrator only — detect host, load persisted state, reconcile models, verify
components and runtimes, reconcile workloads and reservations, reconcile ports and endpoints, start
required services, health check. Individual reconcilers were built by the stages that created the
state.

**Proof.**
Full restart with instances running: inventory, reservations, instances and gateway state all
coherent afterwards, with nothing redownloaded. *Negative:* an unreconcilable divergence fails
conservatively and reports, rather than guessing. *Recovery:* restart during reconciliation is itself
safe.

**Level.** L4.

**Obligations.** Discharges the reconciliation registry.

> ### GATE G5 — OPERABILITY (L4)
> Restarts and reconciles coherently; the administrator can see and act on everything.

---

### S27 — Portability

**Goal.** Prove the architecture is capability-based, not fitted to one machine.

**Consumes.** Artifacts produced on the original host; a **different** physical host.

**Builds.** No new subsystem. It exercises fingerprint-based revalidation (build architecture T8):
artifacts keyed to a different fingerprint are stale, not wrong — retained, revalidated, reused only
if they still hold.

**Proof.**
On a different host with the storage volume carried over: capacity recomputed for the new machine,
stale evidence invalidated by fingerprint, persisted models re-evaluated against current hardware,
compatible artifacts reused without redownload, incompatible ones retained and marked, and the stack
brought to working inference. *Negative:* a model that fitted the old accelerator and does not fit
the new one is marked incompatible and **not deleted** (constitution; operating contract §18).
*Recovery:* interrupted migration leaves both hosts' state coherent.

**Level.** L4.

> ### GATE G6 — PORTABILITY (L4)
> The gate the previous project never had. Restart on the same machine proves persistence; only a
> different machine proves the architecture is genuinely capability-based. This is also the
> development discipline: replacement servers exercise it continuously (operating contract §15).

---

# PHASE 6 — KNOWLEDGE

*Proves: company knowledge is reachable and permission-aware.*

- **S28 — Knowledge source and connector.** Normalized `KnowledgeSource` and `KnowledgeItem` —
  internal ID, source, external ID, path, type, owner, version, checksum, metadata, timestamps,
  **permission references**, indexing state, content reference, provenance. Connectors advertise
  capabilities rather than pretending providers are identical. Content need not be copied locally.
  *Negative:* a connector losing credentials degrades that source without affecting others.
  **Artifact:** `KnowledgeSourceSnapshot v1`. **L2.**

- **S29 — Permission-aware indexing and retrieval.** `AccessContext` → candidate knowledge →
  permission enforcement → authorized items → retrieval. Embeddings served by the second inference
  instance proven at S19. Source revalidation at retrieval time for sensitive systems.
  *Negative — the decisive proof:* two users with different permissions issue the same query and
  receive different authorized sets; unauthorized content is never retrieved, ranked or logged.
  **Artifact:** `AuthorizedRetrievalResult v1`. **L4.**

- **S30 — RAG.** Indexing, chunking, embedding, retrieval, prompt assembly and inference kept as
  separate modules. Only authorized context reaches the model, through the gateway.
  *Negative:* with retrieval returning nothing authorized, the model answers without fabricating
  sources. **Artifact:** knowledge-augmented `GatewayRequest`. **L4.**

- **S31 — Knowledge administration.** Connect, disconnect, health, indexing state, permission
  explanation, retrieval diagnosis, reindex — in Admin UI and Agent. **L4.**

> ### GATE G7 — COMPANY BRAIN (L4)
> Only authorized knowledge reaches the model, for real users against a real source.

---

# PHASE 7 — PEOPLE

- **S32 — End-user experience.** First-party UI: authentication, conversation, streaming, model and
  brain selection where permitted, history, knowledge interaction, source behaviour. Third-party
  frontends remain replaceable clients of stable APIs (constitution §34). **L4.**

- **S33 — TeamBrain scoping.** Base model + team permissions + team knowledge + team tools + team
  profile. The contract carries adapter and derived-model references from v1, unpopulated until S44
  (invariant I3). No training. **L4.**

---

# PHASE 8 — COMMERCIAL

- **S34 — Outbound boundary and telemetry.** Three data domains kept separate: customer AI
  analytics, vendor product telemetry, licensing. Single outbound agent for heartbeat, telemetry,
  update checks and entitlement renewal, each channel independently visible and configurable.
  *Negative — the decisive proof:* **air-gapped mode disables all outbound communication and the
  platform remains fully operational** for local inference, knowledge, analytics and administration.
  Prompts, responses, documents and RAG content are never transmitted. **L4.**

- **S35 — Entitlements.** Generic signed feature and capacity claims; local verification; connected
  renewal; grace periods; offline licensing. Marketing tiers stay out of core logic.
  *Negative:* an expired entitlement restricts new installs and premium features while **never**
  destroying data, killing production inference, or locking administrators out. **L2.**

- **S36 — Installer and conversational onboarding.** The friendly front end over S03's engine — never
  a second implementation (build architecture T1, operating contract §15). Inspect host → business
  questions → resolve components → deployment plan → approval → download and verify → install →
  initialize → health check. This is where the intelligence provider's guided mode matters most.
  **L4.**

- **S37 — Updates and rollback.** Independently versioned, signed, verified, rollback-aware packages
  for core, UI, runtime adapters, executors, connectors and telemetry. Offline bundles. **L2/L4.**

- **S38 — Commercial governance.** Dependency inventory, provenance, license metadata,
  Green/Amber/Red classification, SBOM, and an audit of the actual packaged artifact. **L1.**

> ### GATE G8 — PRODUCT (L4)
> A non-technical administrator installs AI Stack on a supported host and reaches working inference.

---

# PHASE 9 — INTELLIGENCE

*Begins only after the exoskeleton and Company Brain gates pass.*

- **S39 — Observed capacity evidence.** Measured RAM and VRAM, context, concurrency, TTFT, ITL,
  TPOT, throughput, queue delay, OOM and failure. Populates the observed side of the S07 contract,
  which already distinguishes it.
- **S40 — Capacity intelligence v2.** Fuse theoretical and observed. Introduce
  `memory_max_concurrency`, `performance_max_concurrency` and `slo_max_concurrency` alongside the
  existing configured values, plus `WorkloadProfile`. Resource Manager stays authoritative.
- **S41 — Model outcomes and effectiveness dataset.** `ModelOutcome` joining model and
  configuration, task and workload, team and role, organisation cohort, latency, tokens, errors,
  cost, explicit ratings and behavioural proxies. Joins on the S18 cohort fields. Cohort-level and
  privacy-preserving; raw content stays local.
- **S42 — Intelligent routing.** Policy, team, role, task, privacy, capacity, quality, latency, cost,
  availability and effectiveness. Manual override always available.
- **S43 — Portfolio optimizer.** Explainable portfolios: highest quality, balanced, broadest
  coverage, lowest resource use, lowest cost, best concurrent mix. Never one opaque answer.
- **S44 — Adaptation and TeamBrain v2.** `DatasetSnapshot` first: **retrieval permission does not
  imply training permission** (constitution §76). `ModelAdaptationProvider` for LoRA, PEFT, SFT,
  preference optimization, merging and distillation. Training infrastructure separate from inference.
  Draft → evaluating → approved → production → deprecated, with rollback.
- **S45 — Multi-host and coordination.** Extend the same normalized `HostCapabilities`,
  `ResourceReservation` and `DeploymentPlan` semantics to a fleet. "Which host should run this?"
  becomes an extension of "can this host run this?". Organisational coordination only after
  identity, knowledge, teams, agents, analytics and Team Brains are mature.

---

## WHAT MUST NOT DELAY THE EXOSKELETON

Exhaustive benchmarking; Kubernetes; multi-host orchestration; deep capacity calibration; learned
routing; the portfolio optimizer; many model sources or connectors; knowledge graphs; fine-tuning
and distillation; autonomous Team Brain learning; organisational coordination; custom billing; a
perfect UI; an exhaustive audit UI.

**Create seams. Defer depth.**

---

## REQUIRED BRIEF BEFORE EACH STAGE

```text
STAGE
PREDECESSOR OUTPUTS          (artifacts that must already exist)
THIS STAGE'S REQUIRED OUTPUT
CORE CONTRACTS AFFECTED
ADAPTERS AFFECTED
PERSISTED STATE
MUTATION / FAILURE BOUNDARY
OBLIGATIONS DISCHARGED       (reconciler / health / audit / egress / secrets)
PROOF OF WORK                (capability / negative / recovery)
ACCEPTANCE LEVEL             (L1-L4)
PROVISIONAL ITEMS
DEFERRED ITEMS
STOP BOUNDARY
```

If a proposed change is not necessary to produce the current stage output, defer it.

If a stage requires **restructuring** a predecessor's contract, stop: that is evidence the sequence
is wrong (invariant I3), and it is a `DECISION_REQUIRED` condition, not a task.
