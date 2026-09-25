# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: MACHI-STAGE1-SPINE-CLOSURE-001
Status: AUTHORIZED — STAGE-1 DEPLOYMENT-SPINE CLOSURE
Starting accepted source: 2c12f00286d6e7d6d524baa7a7787099e476bf08
Accepted recovery checkpoint: checkpoint/ollama-nvidia-stage1-2026-09-24

This instruction authorizes the final non-physical closure package for Strategic Stage 1: the Machi deployment spine.

The goal is to leave the product architecture, implementation, evidence projection, documentation, debt/status records, and next-stage decision surface coherent enough that the Lead can declare Stage 1 closed at its proven scope.

This instruction deliberately does not require any new physical hardware campaign.

---

# 1. PRODUCT OUTCOME

At the end of this package, Machi should be able to say, truthfully and simply:

On hardware configurations already proven by accepted physical evidence, Machi can discover the host, derive safe capacity, select and verify an execution foundation, qualify/select a model, compose a plan, reserve resources through one ResourceManager, start a serving instance, complete a real request inference, stop/reconcile/release correctly, select Ollama as a bounded fallback when native vLLM is unavailable by policy, and explain the accepted deployment journey from persisted evidence.

The two current execution macropaths are:

COMMON MACHI CONTROL SPINE
Install
  ↓
Discover
  ↓
Steward
  ↓
Capacity
  ↓
Foundation
  ↓
├── Native / vLLM — PRIMARY
└── Ollama — COMPATIBILITY / FALLBACK
  ↓
Model
  ↓
Plan
  ↓
ONE ResourceManager
  ↓
Serve
  ↓
Request inference
  ↓
DeploymentWitness

The macropaths are different execution paths under shared Machi authority. They are not two independent platforms or two admission systems.

---

# 2. BINDING LEAD DECISION — PHYSICAL BREADTH IS DEFERRED

The Lead has decided that Stage-1 closure must not be blocked by remaining physical breadth campaigns.

Do not create a new RunPod or any other physical host in this instruction.
Do not run a new paid physical test.

Existing accepted evidence is sufficient for the Stage-1 capability claim at its bounded scope.

## Native / vLLM accepted evidence

The accepted L40S campaign already proved, for its exact environment:

- managed native vLLM Foundation;
- empirical qualification of HuggingFaceTB/SmolLM2-135M-Instruct;
- empirical qualification of HuggingFaceTB/SmolLM2-360M-Instruct;
- real request inference;
- stop;
- re-admission;
- restart;
- second request inference;
- negative rejection of the head-dimension-4 tiny Llama before normal weight acquisition.

This is sufficient to satisfy the Stage-1 product capability that Machi can complete a native/vLLM deployment and inference path on a supported host.

NVIDIA-N1/Ampere is now coverage, not a Stage-1 capability blocker.

## Ollama accepted evidence

Bundle 07 on the accepted A40 campaign already proved:

- native/vLLM Foundation READY on that host;
- AUTO preference for vLLM while native was healthy;
- a real isolated native provisioning failure through product code;
- AUTO selection of Ollama under approved fallback policy;
- a fresh Foundation → model → Plan → Admit → Serve chain;
- two real Ollama request-inference cases;
- context-bound negative refusal;
- STOP/release;
- one ResourceManager ledger;
- separate catalogs;
- concrete RuntimeChoice evidence.

That is sufficient for the bounded NVIDIA Stage-1 Ollama fallback capability.

## Explicit pending physical qualification

The closure record must keep the following as OPEN / PHYSICAL_PENDING, not PASS:

- AMD native/vLLM Foundation and downstream macropath qualification, including M-5-AMD-01;
- macOS/Ollama physical qualification;
- NVIDIA Ampere/N1 breadth qualification;
- any Apple/macOS physical acceptance already identified elsewhere and not genuinely closed;
- any other physical proof currently pending in repository truth.

Do not infer one hardware family from another.
Do not claim AMD, macOS, all-NVIDIA, or vendor-wide support.

---

# 3. STARTING STATE / BRANCH DISCIPLINE

Before changing source:

1. sync the GitHub handoff;
2. confirm this instruction id;
3. inspect local HEAD, origin refs, working tree, accepted checkpoints, and branch ancestry;
4. confirm whether 2c12f002... remains the latest accepted product source;
5. confirm whether origin/machi is still behind the accepted line;
6. identify untracked files and whether any contain unique authoritative work.

If repository truth still matches the onboarding result:

- starting source is exactly 2c12f00286d6e7d6d524baa7a7787099e476bf08;
- create a new bounded branch from that exact source, recommended name: stage1/spine-closure;
- do not branch from stale machi;
- do not continue implementation on the closed automation/ollama-macropath branch.

If repository truth has moved legitimately, reconcile before editing and state the exact successor.

Do not merge the control branch into product history.

---

# 4. PREDECESSORS THAT ARE CLOSED — PROTECT THEM

Do not reopen or redesign closed work unless the architecture audit exposes a genuine defect.

Preserve:

- Kernel contracts, events, Store, privacy;
- Install identity and ownership chain;
- Discover provider-neutral contracts;
- PrerequisiteReadiness separation from Discover;
- Steward ownership/occupancy boundaries;
- Capacity as SAFE planning truth, not admission;
- Foundation / Runtime / Executor separation;
- native/vLLM as primary where supported;
- Ollama as compatibility/fallback;
- native and Ollama model catalogs as separate authorities;
- Plan as non-admission;
- ResourceManager as the sole admission authority;
- one reservation ledger;
- Serve as a consumer of authorization, not a planner;
- STOP != RELEASE;
- unsupported/unavailable/unresolved remain explicit;
- exact evidence identity and provenance;
- privacy / no prompt-response telemetry;
- schema migration durability from Bundle 07;
- RuntimeChoice v2 concrete Foundation evidence.

Closed physical evidence remains historical truth and must not be rewritten.

---

# 5. PACKAGE STRUCTURE

Execute this as one product-first closure bundle.

Do not stop after every small correction.

The package has these slices:

1. repository and acceptance-truth audit;
2. full Stage-1 architecture audit;
3. native/vLLM macropath audit;
4. Ollama macropath audit;
5. fallback-policy and failure-semantics audit;
6. shared authority / ResourceManager / lifecycle audit;
7. 0.6.1 DeploymentWitness implementation;
8. Stage-1 documentation/debt/status coherence;
9. explicit pending-physical-qualification register;
10. local QA / package / isolated verification;
11. Stage-1 closure record and checkpoint candidate;
12. post-Stage-1 options decision memo;
13. final paste-back and STOP.

You may fix ordinary implementation defects autonomously inside this bounded scope.

STOP only for a genuine architecture/product amendment that contradicts the binding decisions in this instruction.

---

# 6. FULL STAGE-1 ARCHITECTURE REVIEW

Perform a repository-wide architecture review of the implemented Stage-1 spine, not just the files touched recently.

The review must answer the following.

## A. Concept ownership

For each Block 0–9, confirm:

- what concept it owns;
- its primary inputs;
- its primary outputs;
- what it must not own;
- whether current imports and composition respect that boundary.

Pay special attention to:

Kernel → mechanisms/evidence
Install → this installation
Discover → observations
Steward → ownership/occupancy classification
Capacity → SAFE planning ceilings
Foundation → execution foundation selection
Model → model identity/qualification/artifact
Plan → desired deployment configuration
Admit → authorization/reservation
Serve → execution/readiness/inference/lifecycle

No later block should quietly redefine upstream truth.

## B. Provider / platform neutrality

Audit core/domain packages for leakage of:

- NVIDIA;
- AMD;
- Apple/macOS;
- RunPod;
- Docker;
- Ollama;
- vLLM;
- Linux-specific paths;
- vendor CLI semantics;
- provider-specific identity types;

where those details should live behind adapters/providers.

Concrete providers may exist. Provider-specific semantics must not define generic domain contracts.

Do not introduce abstractions without a concrete need.

## C. Runtime / executor separation

Confirm that:

- runtime engine != executor;
- native process remains first-class;
- Docker/container remains optional/deferred;
- Ollama is an engine/integrated runtime path, not a second platform ontology;
- vLLM provision/verify remains Foundation behavior, not Serve-owned installation.

## D. Truth and authority

Confirm exactly one authority for each:

- host observation;
- ownership;
- SAFE capacity;
- Foundation selection;
- model qualification;
- Plan;
- resource admission;
- ServingInstance;
- inference proof.

Identify and remove accidental duplicate truth objects if any were introduced.

Do not remove legitimate historical evidence records.

## E. Persistence / migration / re-entry

Audit:

- Store schemas;
- schema registrations;
- migration/readback paths;
- current persisted versions;
- create/re-entry behavior;
- idempotence;
- stale/current semantics;
- restart/reacquisition rules.

Do not silently strengthen historical evidence.

## F. Dependency / invalidation

Verify that changes to relevant upstream evidence correctly invalidate or forbid reuse of downstream objects.

At minimum review:

Host/Capacity change
  → Foundation / Model reconsideration

Foundation change
  → Model/Plan invalidation

Model/qualification change
  → Plan invalidation

Plan stale
  → no new admission

Capacity evidence mismatch
  → admission refusal

Reservation released/mismatched
  → no Serve authorization

STOP must not by itself rewrite or release a reservation.

## G. Failure semantics

Audit typed behavior for:

- unsupported;
- unavailable;
- unresolved;
- prerequisite blocked;
- provisioning failed;
- verification failed;
- stale;
- qualification does not cover;
- reservation mismatch;
- process exit before ready;
- readiness failure;
- inference failure;
- stop/reconcile failure.

No fake success.
No unknown-as-zero.
No inferred PASS from absence of error.

## H. Privacy / telemetry

Confirm:

- prompts/responses are not persisted in operational events;
- model/customer paths and secrets are not emitted where prohibited;
- Witness does not become a content log;
- vendor/cloud export remains optional and non-authoritative;
- local inference does not require outbound telemetry.

## I. Security boundary

Audit current loopback-only assumptions and existing authentication debt.

Do not implement a new authentication system in this package.

Record exactly what is safe only because the API/runtime is loopback/local and what must change before a remote or central command surface can issue control actions.

This will directly inform the next-stage frontend/command-center decision memo.

---

# 7. NATIVE / vLLM MACROPATH REVIEW

Treat the native path as the primary direct-managed-engine macropath.

Verify the implemented chain:

FoundationSelection(vLLM)
  ↓
verified native generation / RuntimeCapability
  ↓
explicit Model source
  ↓
runtime-specific compatibility
  ↓
qualification evidence
  ↓
DeployableModels
  ↓
ModelSelection / verified warehouse ModelArtifact
  ↓
DeploymentConfiguration
  ↓
ResourceRequest
  ↓
ResourceManager reservation
  ↓
ServingInstance
  ↓
ReadinessProof
  ↓
InferenceProof
  ↓
STOP
  ↓
release

Confirm:

- the old architecture-name-only compatibility defect is no longer sufficient for deployability;
- qualification coverage includes the execution-environment identity required by current contracts;
- the tiny head-dimension-4 Llama is still rejected by current qualification logic;
- a ModelSelection outside DeployableModels is refused;
- Plan cannot omit required qualification identity;
- Serve cannot run a Plan whose evidence/reservation does not match;
- restart/re-entry behavior is consistent with the accepted L40S proof.

Do not rerun physical inference.

Use local tests, fixtures, persisted evidence, and accepted physical records.

---

# 8. OLLAMA MACROPATH REVIEW

Treat Ollama as the compatibility/fallback macropath, not as another core platform.

Verify the implemented chain:

FoundationSelection(Ollama)
  ↓
managed/verified Ollama Foundation generation
  ↓
Ollama provider catalog / digest identity
  ↓
provider-authoritative qualification + Machi shadow evidence
  ↓
provider Plan
  ↓
same ResourceManager
  ↓
provider ServingInstance / residency evidence
  ↓
InferenceProof
  ↓
STOP
  ↓
release

Confirm:

- Ollama digest remains provider model identity;
- tag remains display/reference, not durable identity;
- Ollama model store is not silently treated as the native Model Warehouse;
- native and Ollama catalogs are not merged;
- no cross-catalog model equivalence or translation exists;
- provider Plan cites the exact Foundation generation and provider qualification/context;
- Serve verifies actual generation/environment identity;
- STOP/reconcile cannot invent success;
- reservation release is separate;
- runtime residency evidence does not become a second admission authority.

Do not deepen Ollama merely to retire future debt.

Do not run macOS/Ollama physically. Record it as pending qualification.

---

# 9. FALLBACK POLICY / AUTO REVIEW

This is a critical closure gate.

Audit the code and tests against the approved semantics:

AUTO:
- if native vLLM is supported/healthy: select native vLLM;
- else if native vLLM is unavailable by an approved fallback state and Ollama is supported/ready: select Ollama;
- else: typed refusal / unresolved outcome.

Explicit modes:
- VLLM → vLLM or fail closed;
- OLLAMA → Ollama or fail closed.

They must never silently switch.

Confirm the approved vLLM-unavailable categories in repository truth.

Do not broaden fallback categories merely to make tests pass.

A fallback must cause a fresh recomputation:

Foundation
  → model view
  → Plan
  → Admit
  → Serve

It must not:

- retry secretly inside Serve;
- reuse an incompatible Plan;
- reuse an incompatible reservation;
- translate a native model into an Ollama model;
- mutate the original healthy Foundation;
- create a second ResourceManager;
- claim physical live failover after an inference/request failure.

## Required local test matrix

At minimum preserve/add deterministic tests for:

1. AUTO + healthy vLLM → vLLM selected.
2. AUTO + approved native unavailable state + Ollama READY → Ollama selected.
3. AUTO + vLLM conditionally supported / reconcile-required → behavior matches current approved policy, not an invented fallback.
4. explicit VLLM + native failure → typed failure, no Ollama.
5. explicit OLLAMA + Ollama failure → typed failure, no vLLM.
6. fallback creates new Plan identity.
7. fallback creates new reservation identity.
8. one ResourceManager ledger sees both paths.
9. no cross-catalog translation.
10. Serve does not own retry/fallback.
11. RuntimeChoice cites the concrete Foundation evidence consulted.
12. historical RuntimeChoice readback does not manufacture missing ids.

If current architecture supports more relevant negative cases, include them.

---

# 10. RESOURCE / LIFECYCLE CLOSURE REVIEW

Re-check the Stage-1 safety spine across both macropaths.

Confirm:

- ResourceManager is the only author of execution authorization;
- a bare Plan never starts;
- reservations are durable according to current contract;
- aggregate accounting cannot oversubscribe the SAFE envelope;
- accelerator identity remains exact;
- RAM / accelerator memory / storage remain separate resources;
- stop does not imply release;
- release after confirmed death is explicit;
- re-entry cannot adopt an unrelated process;
- stale Plan/capacity cannot mint a new reservation;
- provider residency cannot override global admission.

Where a future enforcement gap remains, such as cgroups, GPU partitions, multi-host, lease expiry, preemption, keep it deferred rather than pretending Stage 1 implements it.

---

# 11. IMPLEMENT 0.6.1 DEPLOYMENTWITNESS

This is the main new Stage-1 closure capability.

## Product purpose

A user/operator should be able to ask:

What happened to this deployment, and is there enough persisted evidence to say the accepted journey succeeded?

Witness is an evidence projection, not an orchestrator.

## Architectural boundary

Witness must:

- read already persisted contracts/events/evidence;
- connect the identities that belong to one deployment journey;
- expose missing, contradictory, stale, or mismatched layers;
- preserve provenance;
- remain privacy-safe.

Witness must not:

- rediscover hardware;
- rerun Capacity;
- reprovision a Foundation;
- query a model registry to strengthen old evidence;
- create or change ModelSelection;
- compose a new Plan;
- admit resources;
- start/stop a process;
- re-run inference;
- mutate historical facts;
- contact a vendor cloud;
- become a second health engine.

Use current Kernel contracts/ports and the smallest seam needed.

## Minimum Stage-1 evidence layers

The exact contract shape should follow repository truth, but the Witness should be able to represent the accepted chain through at least:

Install identity/correlation
  ↓
relevant host/capacity evidence identity
  ↓
FoundationSelection / generation
  ↓
Model qualification / selection / artifact OR provider digest
  ↓
Plan
  ↓
Reservation
  ↓
ServingInstance
  ↓
Readiness / provider evidence
  ↓
InferenceProof
  ↓
STOP / release state where applicable

Do not force native and Ollama to pretend their model identities are the same.

Witness should project through the shared concepts while preserving macropath-specific evidence.

## Outcome semantics

Use existing repository conventions if already defined.

If no complete Witness outcome model exists, introduce the smallest typed model that distinguishes at least:

- evidence supports the accepted journey;
- evidence is incomplete;
- evidence is contradictory/mismatched;
- evidence records a real failure.

Do not use a simple boolean if that would erase unresolved truth.

Do not invent PASS when required evidence is missing.

## Tests

Cover:

- complete native evidence chain;
- complete Ollama/provider evidence chain;
- missing Model qualification;
- mismatched Foundation generation;
- stale/wrong Plan;
- wrong/released reservation;
- missing inference proof;
- failed inference;
- stop/release distinctions;
- historical evidence with unresolved fields;
- privacy/event serialization;
- deterministic re-composition;
- no live resolver/provider invocation;
- architecture import non-edges.

Witness should be reconstructable after process restart from persisted evidence.

---

# 12. STAGE-1 DEBT / STATUS RECONCILIATION

Update authoritative Machi documentation and debt so the repository tells the truth after this closure.

Do not rewrite historical evidence documents merely to make them look current.

## M-6-03

The Lead has chosen not to require a new NVIDIA-N1 probe for Stage-1 closure.

Repository truth already contains real hardware qualification on L40S.

If the current debt retirement condition still allows Lead choice not to run the N1 probe, retire M-6-03 accordingly.

Preserve:

- exact L40S scope;
- exact model revisions;
- fact that this is not class-wide NVIDIA/Ada support;
- N1/Ampere as future hardware coverage.

Do not claim broader qualification.

## M-9-02

The tiny-Llama failure remains truthful and useful.

The Lead authorizes the SmolLM2 qualified models as the Stage-1 native inference acceptance artifacts instead of the incompatible tiny Llama.

If the current M-9-02 retirement condition is satisfied by that authorized replacement plus its existing physical proof, retire it as a Stage-1 acceptance blocker while preserving the tiny-Llama negative evidence prominently.

If the exact debt semantics make retirement inappropriate, reclassify or annotate it so it no longer falsely blocks Stage 1. Explain the choice in the paste-back.

Do not pretend the tiny model now executes.

## M-9-01

Retire only the Witness portion actually implemented.

Do not accidentally claim automatic restart, public bind, multi-instance, or other deferred Serve depth if the debt item groups those together.

If necessary, split the debt cleanly so Witness can retire while unrelated deferred items remain open.

## AMD

Keep M-5-AMD-01 and any related physical qualification items OPEN.

Do not downgrade or hide them.

## Ollama future debt

Do not reopen Stage-1 Ollama development merely to retire:

- loopback/auth isolation;
- host zstd supply-chain gap;
- provider residency semantics;
- provider-neutral schema wording;
- live request-failure failover;
- productized model acquisition;

unless the architecture audit identifies a direct Stage-1 correctness defect.

## macOS/Ollama

Ensure repository truth contains an explicit pending qualification record for macOS/Ollama if none currently exists.

This may be a debt/coverage/qualification record rather than a new product capability.

Do not claim physical support.

---

# 13. DOCUMENTATION COHERENCE PASS

Correct stale current-status text in authoritative or operator-facing Machi docs.

At minimum audit and update where appropriate:

- docs/machi/README.md;
- docs/machi/MACHI_LEAD_DEVELOPER.md;
- .cursor/agents/machi-lead-developer.md;
- docs/machi/ROADMAP.md;
- docs/machi/ARCHITECTURE.md only where implementation truth now requires clarification, not redesign;
- docs/machi/CONTRACTS.md for Witness if needed;
- docs/machi/TELEMETRY.md for Witness events/privacy if needed;
- docs/DEBT.md;
- current checkpoint index/readme if one exists.

Remove or correct stale statements such as:

- Next: Model. Not started;
- fallback not implemented;
- physical Model qualification not run;
- Serve is not started;
- Ollama planner deferred if a bounded provider Plan is now real;
- any status that implies machi is the latest accepted product tip when it is not.

Historical milestone docs may continue to describe what was true at that historical checkpoint.

Do not flatten chronology.

---

# 14. STAGE-1 PHYSICAL-QUALIFICATION BACKLOG

Create or update one clear authoritative record of remaining physical qualification, separate from implementation closure.

Prefer an existing coverage/evidence mechanism if one already exists. Do not invent a competing system.

It should list at least:

## Native / vLLM

Accepted:
- exact L40S native proof.

Pending:
- NVIDIA Ampere/N1 breadth;
- AMD native/vLLM / MI300X or approved AMD target;
- any other current hardware-family qualification still open.

## Ollama

Accepted:
- exact A40 NVIDIA fallback/Serve proof.

Pending:
- macOS/Ollama;
- AMD/Ollama only if it is actually part of a future accepted test plan;
- other hardware/platform breadth only where repository truth already identifies it.

For every pending case include:

- what exact claim it would prove;
- required host prerequisites;
- expected macropath;
- what current evidence cannot be reused;
- current status PHYSICAL_PENDING;
- no false ETA.

This backlog is the place for the user's later dedicated test campaigns.

---

# 15. DEFINE THE STAGE-1 CLOSURE CLAIM PRECISELY

Do not use an unqualified statement such as STAGE1_COMPLETE if that could be read as all hardware/platform support.

Preferred semantic:

STAGE1_DEPLOYMENT_SPINE_IMPLEMENTATION_CLOSED_PHYSICAL_BREADTH_PENDING

or a repository-consistent equivalent with the same meaning.

The closure claim should mean:

- architecture spine 0→9 exists for the accepted scope;
- real native request inference exists on accepted L40S evidence;
- real Ollama fallback/Serve exists on accepted A40 evidence;
- AUTO control-plane fallback semantics are implemented and locally verified;
- Witness can project the accepted deployment journey from persisted evidence;
- local regression/package gates pass;
- no known Stage-1 architecture blocker remains;
- remaining physical platform/hardware breadth is explicitly pending.

It must not mean:

- AMD supported;
- macOS/Ollama supported;
- all NVIDIA supported;
- live request-failure failover;
- multi-model production scheduling;
- multi-host;
- public remote control;
- production fleet HA.

---

# 16. LOCAL QA / PACKAGE GATES

No new physical server is required.

Run all relevant local/isolated gates.

At minimum:

- full tests/machi;
- architecture tests;
- Witness-focused tests;
- native qualification/funnel tests;
- Plan tests;
- Admit tests;
- Serve tests;
- Ollama Foundation/qualification/Serve tests;
- RuntimeChoice/fallback tests;
- schema migration tests;
- privacy/event tests;
- any cumulative verification harness;
- ruff check;
- strict mypy over Machi source;
- repository-owned Machi wheel build;
- isolated wheel verification;
- any current clean-install T2 test that can run without a physical accelerator.

Use accepted physical records as evidence inputs where appropriate, not as an excuse to fake live hardware.

If a local closure defect is found:

- fix it;
- rebuild;
- rerun affected tests;
- continue the bundle.

If a defect requires a new product/architecture choice, return DECISION_REQUIRED.

---

# 17. STAGE-1 CLOSURE RECORD / CHECKPOINT

If all non-physical closure gates pass, create a clear Stage-1 closure record following current repository conventions.

Recommended artifacts, subject to repository convention:

- docs/machi/STAGE1-SPINE-CLOSURE.md;
- checkpoints/MACHI-STAGE1-SPINE-CLOSURE.json;
- a recovery checkpoint branch/tag consistent with existing practice.

The closure record must contain:

- final source SHA;
- wheel/build identity;
- local QA summary;
- architecture-audit disposition;
- Witness status;
- native/vLLM accepted physical evidence references;
- Ollama accepted physical evidence references;
- exact fallback policy;
- ResourceManager single-ledger invariant;
- explicit unsupported/unproven claims;
- pending physical qualification list;
- relevant debt retired/reclassified;
- remaining nonblocking debt;
- no claim of AMD/macOS qualification.

Do not create fake physical evidence entries for this run.

---

# 18. BRANCH / PROMOTION READINESS

The stale machi branch is a process hazard.

During this package:

1. verify ancestry from origin/machi to the accepted line and closure branch;
2. ensure the closure branch contains all accepted M0→M9 and Ollama work;
3. identify whether promotion can be a clean fast-forward or requires another integration action;
4. produce an exact promotion recommendation.

Do not move/push machi automatically in this instruction unless existing authoritative workflow explicitly says the closure package itself owns that promotion.

Default: leave promotion for Lead review immediately after this paste-back.

The final packet must make it impossible for the next developer to accidentally branch from stale machi.

---

# 19. POST-STAGE-1 PRODUCT / ROADMAP OPTIONS MEMO

After the closure work is complete, produce a decision-useful memo for the Lead.

Do not implement any option.

Evaluate the next workstreams against:

- product/customer value;
- ability to demonstrate something useful;
- architectural dependencies;
- security/auth requirements;
- privacy/offline compatibility;
- reuse of existing contracts;
- support burden;
- commercial value;
- engineering risk;
- whether it belongs to product track or lab track;
- whether it blocks later Company Brain capabilities.

At minimum assess the following.

## Option A — Simple local operator/admin frontend

Goal:

A simple visual surface to interact with Machi rather than operating entirely through developer tooling.

Potential initial capabilities:

- deployment status / Witness;
- running model;
- selected macropath;
- host/capacity summary;
- current Plan and reservation;
- start/stop where safely supported;
- model selection/discovery only through existing control contracts;
- system health;
- local usage/operations metrics;
- clear pending/unsupported states.

Respect progressive disclosure.

Do not let the UI own:

- ResourceManager;
- runtime truth;
- model truth;
- host truth;
- deployment lifecycle semantics.

Assess what minimal local control API already exists and what must be added.

## Option B — Central business deployment command center

Goal:

A business/operator view across customer deployments/hosts.

This is not automatically the same plane as the local Admin frontend.

Assess a clean separation such as:

CUSTOMER HOST / LOCAL CONTROL PLANE
Machi deployment
+ local Admin UI
+ local truth

          optional metadata/evidence export
                    ↓

BUSINESS / VENDOR COMMAND CENTER
deployment inventory
health/status
version/qualification
operational metadata
support signals
fleet overview

The central plane must not become the owner of:

- customer host truth;
- local ResourceManager;
- prompts/responses/files;
- mandatory connectivity for inference.

Identify authentication, tenancy, consent, telemetry, fleet identity, and offline implications.

Assess whether the local frontend and central command center should be:

- one workstream with two clearly separated planes;
- or two sequential workstreams.

## Option C — Runtime Artifact Registry

Assess the existing post-spine roadmap workstream:

- exact runtime/software artifact identity;
- pinned binaries/packages;
- checksums/provenance;
- approved upstream sources;
- customer mirrors;
- offline bundles;
- managed helper artifacts such as the current Ollama zstd gap;
- separation from Model Warehouse.

Explain why/when it should precede scaled commercial deployment.

## Option D — NVIDIA Dynamo macropath / Stage-2 empirical lab

Treat Dynamo as a new Foundation family / distributed inference fabric, not a vLLM optimizer.

Assess:

- what customer or scale problem would justify it now;
- what evidence should be gathered first;
- what provider/Industry Solution Selection Gate applies;
- what can be learned versus direct vLLM/Ollama;
- how to avoid destabilizing the product spine.

Do not implement Dynamo in this package.

## Option E — Gateway / authentication / identity foundation

Assess whether a minimal secure API/auth boundary should come before any remotely reachable frontend or command center.

Distinguish:

- local loopback operator UI;
- LAN/remote Admin;
- vendor/fleet command center.

## Option F — Other roadmap-aligned next step

If repository/product truth identifies a stronger candidate, include it.

Examples may include:

- installer/bootstrap productization;
- host eligibility/feasibility UX;
- diagnostics/support bundle;
- usage analytics surface;
- model/runtime management UX.

Do not add speculative work merely to fill a list.

## Recommendation format

Return:

- best immediate product-track next step;
- best parallel lab-track next step;
- prerequisites;
- what should remain deferred;
- a proposed sequence for the next 2–4 bounded workstreams.

This is advisory. STOP before implementing it.

---

# 20. EXPECTED LIKELY DIRECTION — NOT A PRE-AUTHORIZATION

The Lead is currently interested in a simple frontend and a central business command center after Stage 1.

Treat that interest seriously, but do not force the architecture to combine them.

The likely shape to investigate is:

Stage-1 deployment spine
        ↓
DeploymentWitness / health / control contracts
        ↓
simple LOCAL operator/admin frontend
        ↓
secure identity/control boundary
        ↓
optional CENTRAL deployment command center

The Runtime Artifact Registry may run in parallel or immediately before scaled distribution.

Dynamo is likely a lab/product-infrastructure experiment rather than the fastest path to an operator-visible product.

The final memo should challenge or confirm this based on repository truth.

---

# 21. FORBIDDEN SCOPE

Do not begin:

- new physical GPU/macOS acceptance;
- AMD physical qualification;
- macOS/Ollama physical qualification;
- Ampere/N1 campaign;
- Dynamo implementation;
- llama.cpp;
- MLX;
- SGLang;
- TensorRT-LLM;
- ContainerExecutor;
- Kubernetes;
- public remote API exposure;
- full authentication platform;
- frontend implementation;
- central command-center implementation;
- Knowledge/RAG;
- Team Brain;
- agents;
- marketplace;
- multi-host placement;
- fleet scheduler;
- live request-failure automatic failover;
- cross-catalog model equivalence;
- automatic quantization/conversion;
- broad benchmarking.

Do not let the options memo turn into implementation.

---

# 22. ARCHITECTURE AMENDMENT RULE

Fix implementation defects autonomously when the intended semantics are already clear.

Examples:

- stale import boundary;
- missing fail-closed check;
- missing Witness serialization;
- incomplete local test;
- stale docs;
- incorrect identity citation;
- status/debt text inconsistent with accepted evidence.

Return DECISION_REQUIRED before changing:

- Block ownership;
- ResourceManager authority;
- vLLM-primary / Ollama-fallback product policy;
- catalog separation;
- fallback semantics;
- runtime/executor separation;
- physical-qualification deferral decision;
- local-vs-central control-plane authority;
- customer privacy/default-off telemetry principles;
- Stage-1 closure definition established above.

---

# 23. ACCEPTANCE GATE

This bundle is PASS only when all of the following are true:

Repository truth reconciled ........................ PASS
Full Stage-1 architecture audit .................... PASS
Native macropath audit ............................. PASS
Ollama macropath audit ............................. PASS
AUTO/fallback local matrix ......................... PASS
One-ledger ResourceManager invariant ............... PASS
Lifecycle STOP/release invariants .................. PASS
0.6.1 DeploymentWitness ............................ PASS
Witness native chain tests ......................... PASS
Witness Ollama chain tests ......................... PASS
Privacy / persistence / migration .................. PASS
Relevant debt/status reconciliation ................ PASS
Pending physical qualification ledger .............. PASS
Full tests ......................................... PASS
Architecture tests ................................. PASS
ruff ............................................... PASS
mypy --strict ...................................... PASS
Wheel build + isolated verify ...................... PASS
Stage-1 closure record ............................. PASS
Post-Stage-1 options memo .......................... PASS
No new physical campaign performed ................. PASS
Git clean / pushed branch .......................... PASS

If all pass, use exact terminal status:

STAGE1_DEPLOYMENT_SPINE_IMPLEMENTATION_CLOSED_PHYSICAL_BREADTH_PENDING

If local implementation is complete but an architecture decision blocks closure:

DECISION_REQUIRED

If a local product defect prevents closure:

PRODUCT_FAILURE

Do not use a physical PASS status for this run.

---

# 24. FINAL PASTE BACK

Return one complete packet:

A. EXACT STATUS
B. EXECUTIVE TL;DR
C. STARTING / FINAL SHA
D. BRANCH / ORIGIN / WORKTREE
E. STAGE-1 ARCHITECTURE AUDIT
F. BLOCK 0–9 FINAL STATUS
G. NATIVE / VLLM MACROPATH AUDIT
H. OLLAMA MACROPATH AUDIT
I. AUTO / FALLBACK POLICY AUDIT
J. RESOURCE / LIFECYCLE AUDIT
K. PERSISTENCE / MIGRATION / RE-ENTRY AUDIT
L. PRIVACY / SECURITY-BOUNDARY AUDIT
M. DEPLOYMENTWITNESS IMPLEMENTATION
N. DEPLOYMENTWITNESS TEST EVIDENCE
O. DEBT RETIRED / RECLASSIFIED
P. DOCUMENTATION COHERENCE CHANGES
Q. ACCEPTED PHYSICAL EVIDENCE INHERITED
R. PHYSICAL QUALIFICATION LEFT PENDING
S. AMD PENDING QUALIFICATION
T. MACOS / OLLAMA PENDING QUALIFICATION
U. NVIDIA BREADTH PENDING QUALIFICATION
V. LOCAL QA
W. WHEEL / BUILD / SHA256 / ISOLATED VERIFY
X. STAGE-1 CLOSURE CLAIM — EXACT BOUNDARY
Y. STAGE-1 CLOSURE RECORD / CHECKPOINT
Z. MACHI BRANCH PROMOTION READINESS
AA. POST-STAGE-1 OPTION A — LOCAL FRONTEND
AB. OPTION B — CENTRAL COMMAND CENTER
AC. OPTION C — RUNTIME ARTIFACT REGISTRY
AD. OPTION D — NVIDIA DYNAMO
AE. OPTION E — GATEWAY / AUTH / IDENTITY
AF. OTHER ROADMAP OPTION IF MATERIAL
AG. RECOMMENDED NEXT 2–4 WORKSTREAMS
AH. PROVIDER / INDUSTRY DECISION GATES AHEAD
AI. REMAINING NONBLOCKING DEBT
AJ. EXACT NEXT LEAD DECISIONS
AK. GIT STATE
AL. STOP

Be concise in the executive sections but technically complete in the audit/evidence sections.

---

# 25. GIT REQUIREMENTS

Meaningful source/docs/tests must be committed.

Push the closure branch.

Record:

- starting accepted SHA;
- final implementation SHA;
- branch;
- origin equality;
- working-tree status;
- wheel filename;
- build id;
- SHA256;
- closure checkpoint/record;
- files changed;
- tests.

Do not commit untracked proposal files unless this instruction explicitly adopts their content through authoritative docs. Their existence does not make them policy.

---

# 26. STOP

After publishing the complete paste-back:

STOP.

Do not start the frontend.
Do not start the command center.
Do not start the Runtime Artifact Registry.
Do not start Dynamo.
Do not start AMD/macOS/Ampere testing.

Wait for Lead review and selection of the next workstream.

# END INSTRUCTION
