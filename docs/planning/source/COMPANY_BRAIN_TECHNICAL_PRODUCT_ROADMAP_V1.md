# COMPANY BRAIN PLATFORM
## High-Level Technical Product Roadmap for Cursor

**Purpose:** Define the clean-slate technical build sequence for the Company Brain platform.  
**Approach:** Modular, progressive, exoskeleton-first. Every stage must produce explicit, versioned outputs that become the formal input to the next stage.  
**Design rule:** Core owns concepts; adapters own implementations.

---

# 1. Build Objective

Build a secure, modular, self-hosted organisational intelligence platform that can:

- inspect and understand the host it runs on;
- discover, acquire and manage AI models;
- determine safe capacity and resource usage;
- run multiple governed AI workloads;
- expose local and external AI through a stable gateway;
- connect organisational knowledge while preserving permissions;
- provide Admin UI, Admin AI Agent and end-user experiences;
- record normalized usage/effectiveness evidence;
- support connected and air-gapped operation;
- progressively evolve into Team Brains, intelligent routing, model optimization and organisational coordination.

The rebuild should not reproduce the old implementation. It should reuse its architectural lessons while rebuilding from first principles.

---

# 2. Governing Technical Rules

1. **Core owns concepts; adapters own implementations.**
2. **Capability-based deployment, not machine-type assumptions.**
3. **Executor and inference runtime are separate abstractions.**
4. **Resource Manager is authoritative for admission.**
5. **Capacity Planner recommends; evidence providers inform.**
6. **Unknown is valid; fail conservatively rather than invent precision.**
7. **Identity and permission semantics are shared across Gateway, Knowledge, Agents and Admin.**
8. **Prompts, responses, files and RAG content stay local by default.**
9. **Every persistent subsystem must support restart/reconciliation.**
10. **Every mutating workflow defines preflight → admission → mutation → persistence → rollback/reconciliation.**
11. **Admin UI and Admin Agent consume structured Platform APIs, never hidden infrastructure shortcuts.**
12. **Build the complete exoskeleton before deep optimization.**

---

# 3. Stage-to-Stage Handoff Rule

Every stage must end with a **Stage Output Package** containing:

- versioned domain contracts;
- API surfaces;
- persistence schema/migrations;
- adapter interfaces;
- one working reference implementation;
- acceptance-test results;
- `WORKING`, `PROVISIONAL` and `DEFERRED` notes;
- architecture decisions;
- a machine-readable stage checkpoint/manifest.

Recommended form:

```text
docs/stages/STAGE-XX-<name>.md
checkpoints/STAGE-XX-<name>.json
```

The next stage must verify and consume the predecessor output rather than rediscovering facts.

The core technical chain should progressively look like:

```text
PlatformContracts
  ↓
HostCapabilities
  ↓
ResolvedComponentSet
  ↓
StorageCapacity
  ↓
ModelCatalogSnapshot
  ↓
ModelInventory
  ↓
ModelRequirement
  ↓
CapacityAssessment
  ↓
DeploymentPlan
  ↓
AdmissionDecision
  ↓
ResourceReservation
  ↓
InferenceInstance
  ↓
InferenceEndpoint
  ↓
RouteDecision
  ↓
UsageEvent
  ↓
AuthorizedKnowledgeContext
  ↓
TeamBrain
```

---

# 4. Milestone 0 — Architectural Kernel

## Goal
Create the semantic skeleton before building product features.

## Build
- repository/module boundaries;
- stable IDs, schema versions, typed errors and result envelopes;
- configuration ownership;
- adapter registry pattern;
- domain event envelope;
- replaceable persistence boundary;
- Platform API skeleton;
- local administrator identity and `AccessContext`;
- Admin UI shell;
- Admin AI Agent shell and approval model.

Define early contracts for concepts that are expensive to retrofit:

```text
HostCapabilities
ModelMetadata
ModelArtifact
ModelRequirement
ModelInventoryRecord
CapacityEvidence
WorkloadProfile
Workload
ResourceReservation
InferenceInstance
UsageEvent
User
Group
Team
AccessPolicy
KnowledgeSource
KnowledgeItem
DatasetSnapshot
DerivedModel
Entitlement
```

The contracts may be minimal; the boundaries must be intentional.

## Output
**PlatformContracts v1 + PlatformState v1 + ControlPlaneShell v1**

## Completion gate
The contracts serialize without importing runtime/provider libraries, and Admin UI/Admin Agent can call the same Platform API.

---

# 5. Milestone 1 — Host and Bootstrap Foundation

## Stage 1.1 Host Capability Detection
Create `HostDetector` and normalized `HostCapabilities`.

Detect:
- OS/version and architecture;
- CPU and RAM;
- GPU/accelerator vendor, count and memory;
- unified memory where relevant;
- storage and quotas;
- native/Docker/Podman capabilities;
- virtualization;
- network/ports;
- relevant driver/runtime hints.

Reference implementation: **Linux x86_64 + NVIDIA**.  
Synthetic fixtures: CPU-only, Apple Silicon, AMD, Windows-via-Linux-VM style.

### Output
**HostCapabilities v1**

---

## Stage 1.2 Component Registry and Resolver
Create versioned `ComponentManifest` and `ComponentResolver`.

A component describes:
- version;
- supported OS/architecture;
- accelerator compatibility;
- dependencies;
- source;
- checksum/signature;
- license;
- installation method.

### Output
**ResolvedComponentSet v1**

---

## Stage 1.3 Developer Bootstrap / Resume Harness
Create a lightweight host-aware bootstrap orchestrator that:
- detects host;
- loads platform state;
- resolves required components;
- verifies ports;
- reports missing/incompatible pieces;
- verifies runtime/executor availability;
- performs smoke health checks.

This is the precursor to the polished installer.

### Output
**BootstrapAssessment / ResumePlan v1**

---

# 6. Milestone 2 — Execution, Runtime and Storage Foundation

## Stage 2.1 Executor Abstraction
Create:

```text
Executor
├── NativeProcessExecutor      # first reference
├── DockerExecutor             # optional reference
├── PodmanExecutor             # later
├── VMExecutor                 # later
└── KubernetesExecutor         # later
```

Executor owns process/service execution, environment, filesystem mapping, signals, logs and process health—not model semantics.

### Output
**ExecutorSpec + ExecutorHandle**

---

## Stage 2.2 Inference Runtime Abstraction
Create `InferenceRuntime`.

Planned adapters:
- vLLM;
- llama.cpp;
- MLX;
- ROCm-oriented runtime;
- Intel-oriented runtime.

First validated implementation: **vLLM on Linux/NVIDIA**.

Runtime-specific options remain inside adapters.

### Output
**RuntimeProfile + RuntimeLaunchSpec**

---

## Stage 2.3 Storage Capacity and Mutation Safety
Implement the storage chain:

```text
credible remaining host capacity
→ protected reserve
→ safe allocatable capacity
→ administrator allocation
→ platform storage budget
→ current managed usage
→ remaining budget
→ peak additional operation requirement
→ admission
```

Add:
- managed-usage reconciliation;
- staging;
- mutation lock;
- operation preflight;
- rollback/recovery semantics.

### Output
**StorageCapacity v1 + StorageAdmissionDecision**

This output becomes mandatory input to model acquisition.

---

# 7. Milestone 3 — Model Supply Chain

## Stage 3.1 ModelSource and Normalized Metadata
Create `ModelSource`.

Initial adapters:
- Hugging Face;
- local files.

Normalize to platform-owned `ModelMetadata` / `ModelArtifact`.

Start with a curated candidate set, not a giant marketplace.

### Output
**ModelCatalogSnapshot v1**

---

## Stage 3.2 Model Inventory and Lineage Foundation
Create durable Inventory with states such as:

```text
discovered
remote
acquiring
stored
validating
loaded
running
stopped
updating
deprecated
incompatible
derived
```

Preserve lineage hooks:
- parent model/revision;
- derivation type;
- owner/team;
- dataset snapshot reference;
- evaluation/promotion state.

### Output
**ModelInventory v1**

---

## Stage 3.3 Safe Model Acquisition
Workflow:

```text
resolve immutable source
→ calculate storage requirement
→ storage admission
→ lock
→ stage
→ download/import
→ integrity validation
→ commit
→ inventory reconciliation
```

Support resumability, private-source seam, revision pinning and interrupted-operation recovery.

### Output
**Stored ModelArtifact + AcquisitionReceipt**

---

# 8. Milestone 4 — Capacity and Deployment Planning

## Stage 4.1 ModelRequirement
Create normalized model requirement evidence:
- storage;
- RAM;
- VRAM/unified memory;
- runtime compatibility;
- context assumptions;
- configuration assumptions;
- confidence.

Unknown runtime detail remains unknown.

### Output
**ModelRequirement v1**

---

## Stage 4.2 CapacityEvidence Contract
Create `CapacityEvidenceProvider`.

Initial required provider:
- internal conservative estimator.

Planned adapters:
- llmfit;
- Hugging Face Accelerate;
- llm-d-planner;
- runtime-native evidence;
- benchmark providers such as Infermark.

External tools provide evidence only.

### Output
**CapacityEvidence v1**

---

## Stage 4.3 Capacity Planner v1
Answer:
1. Can the model run?
2. What runtime is appropriate?
3. What storage/memory is expected?
4. What safe configured concurrency is reasonable?
5. Can it coexist with current workloads?
6. What are the blockers, alternatives and confidence?

States:

```text
Compatible
Conditional
Unsupported
```

Keep theoretical and observed evidence distinct.

### Output
**CapacityAssessment v1**

---

## Stage 4.4 Deployment Planner
Combine:
- HostCapabilities;
- ComponentResolver;
- ModelArtifact;
- ModelRequirement;
- CapacityAssessment;
- policy/admin preferences.

Produce:
- runtime;
- executor;
- components;
- model/revision;
- resource requirement;
- context;
- configured concurrency;
- ports;
- expected resource use;
- confidence;
- alternatives;
- approvals.

### Output
**DeploymentPlan v1**

This is the direct input to Resource Manager.

---

# 9. Milestone 5 — Resource Manager and Inference Instance

## Stage 5.1 Generic Workload Contract
Define `Workload` independently of inference.

Represent future types:

```text
inference
embedding
reranking
indexing
benchmark
training
evaluation
quantization
distillation
agent_worker
```

Only inference must execute now.

### Output
**WorkloadSpec v1**

---

## Stage 5.2 Resource Admission and Reservations
Resource Manager becomes authoritative.

Keep separate:
- requested requirement;
- admitted reservation;
- observed consumption;
- peak observed consumption.

Resource Manager must:
- reserve before mutation;
- prevent oversubscription;
- persist/reconcile;
- release cleanly;
- explain denial.

### Output
**AdmissionDecision + ResourceReservation**

---

## Stage 5.3 First-Class InferenceInstance
Create `InferenceInstance` with:
- instance ID;
- host;
- model/revision;
- optional adapter;
- runtime;
- executor;
- endpoint;
- reservation;
- context;
- runtime concurrency;
- platform request limit;
- access-policy reference;
- lifecycle/health;
- configuration version.

Explicitly separate:
- request concurrency within one instance;
- simultaneous inference-instance concurrency.

### Output
**InferenceInstance v1**

---

## Stage 5.4 Reference Live Inference Vertical
Start a real model using:

```text
Stored ModelArtifact
+ DeploymentPlan
+ ResourceReservation
+ NativeProcessExecutor
+ VLLMRuntime
```

Implement:
- start;
- health;
- stop;
- restart;
- unload;
- reconciliation.

### Output
**Healthy InferenceEndpoint**

This is the endpoint consumed by Gateway.

---

# 10. Milestone 6 — Governed AI Access Spine

## Stage 6.1 Identity / Team / Policy v1
Expand the local identity model into:
- User;
- Group;
- Team;
- Application/service identity;
- Role;
- AccessPolicy.

Keep `IdentityProvider` replaceable for later SSO/SCIM/enterprise identity.

### Output
**AccessContext v1**

---

## Stage 6.2 Central Gateway v1
Platform owns:
- endpoint identity;
- authentication/authorization hooks;
- model access policy;
- queue/limits hook;
- route decision;
- application identity;
- instrumentation.

Initial routing:
- explicit model;
- default model;
- local endpoint;
- administrator policy.

Create `GatewayProvider` adapter seam.

### Output
**GatewayRequest + GatewayResponse + RouteDecision**

---

## Stage 6.3 UsageEvent and Local Analytics
Every request emits `UsageEvent` containing at minimum:
- timestamp;
- model/provider;
- inference instance;
- user/team/application;
- input/output/total tokens;
- latency;
- error;
- cost where available;
- route.

Use replaceable `UsageAnalyticsStore`.  
Initial local history may be ~7 days.

### Output
**UsageEvent v1 + LocalUsageStore**

---

## Stage 6.4 External Provider Federation
Implement one external path.

Recommended initial adapter: **LiteLLM**.

LiteLLM remains behind the platform Gateway and must not become authoritative for:
- identity;
- route semantics;
- model identity;
- UsageEvent;
- permissions;
- Resource Manager;
- cost normalization.

### Output
**External InferenceEndpoint v1**

Completion: same Gateway API can serve local and external inference.

---

# 11. Milestone 7 — Operational Product Experience

The Admin UI and Admin Agent are progressive surfaces, not late standalone projects.

## Stage 7.1 Admin UI v1
Views:
- Host;
- Capacity;
- Catalog;
- Inventory;
- Inference Instances;
- Reservations;
- Gateway;
- Usage;
- Users/Teams;
- Health;
- Configuration.

Settings support:
- Automatic;
- Manual Override;
- recommendation;
- reason;
- confidence.

### Output
**Operational Admin Console v1**

---

## Stage 7.2 Admin AI Agent v1
Structured tools:
- explain host;
- explain capacity/model recommendation;
- search catalog;
- prepare acquisition;
- prepare start/stop;
- explain health/errors;
- explain usage/routing.

Risk model:

```text
read-only                -> no approval
low-risk mutation        -> controlled policy
meaningful mutation      -> explicit admin approval
```

No unrestricted shell access.

### Output
**Admin Agent Toolset v1**

---

## Stage 7.3 Startup / Resume / Reconciliation
Startup becomes idempotent:

```text
detect host
→ load persisted state
→ reconcile models
→ verify components/runtimes
→ reconcile workloads/reservations
→ reconcile ports/endpoints
→ start required services
→ health check
```

### Output
**Reconciled PlatformState**

The infrastructure exoskeleton is complete when restart preserves coherent Inventory, reservations, InferenceInstances and Gateway state.

---

# 12. Milestone 8 — Knowledge Exoskeleton

## Stage 8.1 KnowledgeSource / KnowledgeConnector
Create normalized:
- KnowledgeSource;
- KnowledgeItem;
- source capabilities;
- permission reference;
- provenance;
- content reference;
- indexing state.

Initial sources:
- managed/local files;
- filesystem/network share;
- one enterprise/cloud document source where practical.

### Output
**KnowledgeSourceSnapshot v1**

---

## Stage 8.2 Permission-Aware Indexing and Retrieval
Required flow:

```text
AccessContext
→ candidate knowledge
→ permission enforcement
→ authorized items
→ retrieval
```

Source revalidation must remain possible for sensitive systems.

### Output
**AuthorizedRetrievalResult v1**

---

## Stage 8.3 RAG v1
Keep modules separate:
- indexing;
- chunking;
- embeddings;
- retrieval;
- prompt assembly;
- inference.

Only authorized context reaches the model.

### Output
**Knowledge-Augmented Gateway Request**

---

## Stage 8.4 Knowledge Admin Experience
Admin UI/Admin Agent can:
- connect/disconnect;
- show health;
- show indexing state;
- explain permissions;
- diagnose retrieval;
- reindex.

### Output
**Managed Knowledge Source v1**

---

# 13. Milestone 9 — End-User Company Brain and Team Brain

## Stage 9.1 First-Party End-User UI v1
Minimal:
- authentication;
- conversation;
- streaming;
- model/brain selection where allowed;
- history;
- knowledge interaction;
- source behavior.

Third-party frontends remain replaceable clients.

### Output
**Employee AI Experience v1**

---

## Stage 9.2 TeamBrain Logical Model
TeamBrain is not one model.

Represent:
- team;
- membership/policy;
- knowledge scope;
- tools;
- agent configuration;
- base-model/portfolio policy;
- routing policy;
- memory placeholder;
- evaluation profile;
- optional adapter/derived-model references.

Initial specialization:

```text
base model
+ team permissions
+ team knowledge
+ team tools
+ team profile
```

### Output
**TeamBrain v1**

---

## Stage 9.3 Team Agent v1
Execution goes through:
- AccessContext;
- Gateway;
- permission-aware Knowledge;
- approved tools;
- TeamBrain policy.

### Output
**Governed Team Agent Execution**

---

# 14. Milestone 10 — Outbound, Telemetry and Entitlements

## Stage 10.1 Three Data Domains
Keep separate:
1. Customer AI Analytics;
2. Vendor Product Telemetry;
3. Licensing/Entitlements.

### Output
**OutboundDataPolicy v1**

---

## Stage 10.2 Heartbeat / Telemetry Agent
Single outbound boundary for:
- heartbeat;
- product telemetry;
- optional cloud analytics;
- update checks;
- crash reporting;
- entitlement renewal.

All channels independently visible/configurable.

Air-gapped mode disables all outbound communication.

### Output
**OutboundChannelState v1**

---

## Stage 10.3 Entitlements
Generic signed entitlements:
- feature claims;
- capacity claims;
- local verification;
- connected renewal;
- grace;
- offline license.

Marketing tier names do not belong in core logic.

### Output
**EntitlementState v1**

---

# 15. Milestone 11 — Installer, Updates and Commercial Release Foundation

## Stage 11.1 Product Bootstrapper
Convert the developer bootstrap harness into the non-technical installer:

```text
inspect host
→ ask business/admin questions
→ resolve components
→ build DeploymentPlan
→ obtain approval
→ download/verify
→ install
→ initialize
→ health check
```

### Output
**InstallPlan + InstallationReceipt**

---

## Stage 11.2 Component Installation / Offline Bundle
Install only required compatible components from versioned manifests.

### Output
**InstalledComponentInventory**

---

## Stage 11.3 Modular Updates and Rollback
Update independently:
- core;
- UI;
- runtime adapters;
- executors;
- connectors;
- telemetry components.

Packages are versioned, signed/verified and rollback-aware.

### Output
**UpdatePlan + UpdateReceipt**

---

## Stage 11.4 Third-Party Commercial Governance
Generate:
- dependency inventory;
- provenance;
- license metadata;
- Green/Amber/Red classification;
- SBOM;
- packaged-artifact audit.

### Output
**CommercialReleaseManifest**

---

# 16. Milestone 12 — Capacity and Model Effectiveness Intelligence

Only begin after the complete exoskeleton works.

## Stage 12.1 Observed Capacity Evidence
Collect actual:
- RAM/VRAM;
- context;
- concurrency;
- TTFT/ITL/TPOT;
- throughput;
- queue delay;
- OOM/failure.

### Output
**Observed CapacityEvidence**

---

## Stage 12.2 WorkloadProfile
Normalize:
- input/output length;
- request rate;
- burstiness;
- concurrency;
- streaming;
- SLO targets;
- priority.

### Output
**WorkloadProfile v1**

---

## Stage 12.3 Capacity Intelligence v2
Fuse theoretical and observed evidence.

Differentiate:

```text
memory_max_concurrency
performance_max_concurrency
slo_max_concurrency
configured_concurrency
platform_max_concurrent_requests
```

### Output
**Evidence-Fused CapacityRecommendation**

Resource Manager remains authoritative.

---

## Stage 12.4 ModelOutcome / ModelExperience
Capture:
- model/configuration;
- task/workload;
- team/role;
- organization cohort;
- latency/tokens/errors/cost;
- explicit ratings;
- retries/regeneration/switching;
- task/acceptance proxies.

Raw customer content remains local by default.

### Output
**ModelOutcome v1**

---

# 17. Milestone 13 — Intelligent Routing and Model Portfolio Optimization

## Stage 13.1 Model Effectiveness Dataset
Join:
- ModelMetadata;
- CapacityEvidence;
- WorkloadProfile;
- UsageEvent;
- ModelOutcome;
- organization/team cohort.

### Output
**ModelEffectivenessDataset**

---

## Stage 13.2 Intelligent Routing
Route based on:
- policy;
- team/role;
- task;
- privacy;
- capacity;
- quality;
- latency;
- cost;
- availability;
- effectiveness evidence.

Manual override remains available.

### Output
**Explainable RouteDecision v2**

---

## Stage 13.3 Model Inventory Optimizer
Provide explainable portfolios:
- Highest Quality;
- Balanced;
- Broadest Coverage;
- Lowest Resource Use;
- Lowest Cost;
- Best Concurrent Mix.

### Output
**ModelPortfolioRecommendation**

---

# 18. Milestone 14 — Team Brain Adaptation

## Stage 14.1 Training Data Governance
Create `DatasetSnapshot`.

Retrieval permission does **not** imply training permission.

Track:
- provenance;
- authorization;
- scope;
- snapshot/version;
- retention;
- policy.

### Output
**Approved DatasetSnapshot**

---

## Stage 14.2 ModelAdaptationProvider
Replaceable adaptation seam for:
- LoRA/PEFT;
- SFT;
- preference optimization;
- merging;
- distillation.

Training infrastructure remains separate from inference infrastructure.

### Output
**DerivedModel / AdapterArtifact**

---

## Stage 14.3 Evaluation and Promotion
Lifecycle:

```text
draft
→ evaluating
→ approved
→ production
→ deprecated
```

Compare against base model on quality, outcomes, latency, resource use, cost and safety.

### Output
**Promoted DerivedModel**

---

## Stage 14.4 Team-Specific Serving
TeamBrain may reference base model + adapter/derived model + routing policy.

### Output
**Adapted TeamBrain v2**

---

# 19. Milestone 15 — Multi-Host and Organisational Coordination

## Stage 15.1 Multi-Host Control Plane
Extend existing:
- HostCapabilities;
- Resource Manager;
- DeploymentPlan;
- InferenceInstance;
- Gateway endpoint registry.

### Output
**FleetState v1**

---

## Stage 15.2 Model Placement
Answer:

> Which host should run this workload?

using the same normalized capacity/resource semantics.

### Output
**PlacementDecision**

---

## Stage 15.3 Organisational Coordination Intelligence
Only after identity, knowledge, teams, agents, analytics and TeamBrains are mature.

Potential capabilities:
- expertise discovery;
- duplicate-effort detection;
- cross-team knowledge flow;
- governed task coordination;
- organisational recommendations.

### Output
**Explainable CoordinationRecommendation**

Human approval remains central initially.

---

# 20. Cross-Cutting Progressive Rules

## Admin UI and Admin Agent
Every important backend stage should also add:
- Platform API;
- Admin UI representation;
- Admin Agent read/explain tool.

Meaningful Admin Agent mutations follow:

```text
proposal → administrator approval → structured API action
```

---

## Reconciliation
Reconciliation is implemented alongside stateful modules, not postponed.

Examples:
- acquisition → staging/inventory reconciliation;
- Resource Manager → reservations/workloads;
- inference → process/endpoints;
- knowledge → source/index state;
- telemetry → outbound queue;
- updates → install/version state.

---

## Future-data foresight
Preserve structured fields early for:
- immutable model revision;
- runtime/version;
- hardware fingerprint;
- configuration version;
- UsageEvent;
- workload label hooks;
- team/role;
- CapacityEvidence;
- model lineage;
- knowledge provenance;
- dataset provenance;
- optional future outcome signals.

Do not collect sensitive content merely because it may become useful.

---

# 21. What Must Not Delay the Exoskeleton

Do not let these block the first complete product:
- exhaustive benchmarks;
- Kubernetes;
- multi-host orchestration;
- deep capacity calibration;
- learned routing;
- portfolio optimizer;
- dozens of model sources/connectors;
- knowledge graph;
- fine-tuning/distillation;
- autonomous Team Brain learning;
- organisational coordination;
- custom billing;
- perfect UI;
- exhaustive enterprise audit UI.

Create seams. Defer depth.

---

# 22. First Infrastructure Exoskeleton Gate

A clean supported installation must be able to:

1. detect host;
2. produce HostCapabilities;
3. resolve components;
4. initialize state/control plane;
5. show Admin UI;
6. run basic Admin Agent;
7. browse curated models;
8. calculate ModelRequirement;
9. produce CapacityAssessment;
10. produce DeploymentPlan;
11. safely acquire model;
12. register Inventory;
13. obtain ResourceReservation;
14. start InferenceInstance;
15. expose Gateway endpoint;
16. authenticate a user/application;
17. answer a request;
18. emit UsageEvent;
19. show usage and health;
20. stop/restart safely;
21. reboot/reconcile coherently.

Only then is the infrastructure skeleton complete.

---

# 23. First Company Brain Gate

The first Company Brain is complete when:

1. a KnowledgeSource can be connected;
2. items normalize to KnowledgeItem;
3. permissions are preserved;
4. content is indexed;
5. retrieval is permission-aware;
6. RAG receives only authorized context;
7. employee UI can use it;
8. Admin UI shows knowledge health;
9. Admin Agent can configure/diagnose it;
10. a TeamBrain can scope model + knowledge + tools to a team.

---

# 24. Required Cursor Brief Before Each Stage

Before implementation, Cursor should produce:

```text
CURRENT STAGE
PREDECESSOR OUTPUTS
THIS STAGE'S REQUIRED OUTPUT
CORE CONTRACTS AFFECTED
ADAPTERS AFFECTED
PERSISTED STATE
MUTATION / FAILURE BOUNDARY
ACCEPTANCE TESTS
PROVISIONAL ITEMS
DEFERRED ITEMS
```

If a proposed change is not necessary to produce the current stage output, it should normally be deferred.

---

# 25. Final High-Level Sequence

```text
0. Architectural Kernel
      ↓
1. Host + Bootstrap Foundation
      ↓
2. Executor + Runtime + Storage Foundation
      ↓
3. Model Supply Chain
      ↓
4. Capacity + Deployment Planning
      ↓
5. Resource Manager + InferenceInstance
      ↓
6. Identity + Gateway + UsageEvent
      ↓
7. Operational Admin UI + Admin Agent + Reconciliation
      ↓
8. Permission-Aware Knowledge + RAG
      ↓
9. End-User Company Brain + TeamBrain
      ↓
10. Telemetry + Entitlements + Air-Gap Boundary
      ↓
11. Product Installer + Updates + Commercial Governance
      ↓
12. Capacity + Model Effectiveness Intelligence
      ↓
13. Intelligent Routing + Portfolio Optimization
      ↓
14. Team Brain Adaptation
      ↓
15. Multi-Host + Organisational Coordination
```

The stages are architectural dependencies, not merely calendar phases.

---

# 26. Final Directive to Cursor

The clean-slate rebuild should use the previous attempt as evidence, not as code structure to preserve.

At every stage:

- consume normalized predecessor outputs;
- emit normalized successor outputs;
- preserve replaceable boundaries;
- preserve permission safety;
- preserve local/offline operation;
- implement reconciliation with persistent state;
- expose structured APIs;
- keep Admin UI/Admin Agent aligned;
- record only the minimum future-useful evidence;
- mark approximations `PROVISIONAL`;
- mark future sophistication `DEFERRED`;
- stop refining once the next architectural dependency is unblocked.

The technical learning loop is:

```text
Detect
→ Estimate
→ Validate
→ Deploy
→ Observe
→ Learn
→ Recommend
→ Safely Act
```

The Company Brain product loop is:

```text
Connect
→ Understand
→ Govern
→ Assist
→ Measure
→ Learn
→ Enhance
→ Coordinate
```

The architecture is successful if these loops can become more intelligent over time without forcing the platform to abandon or rewrite its core domain boundaries.
