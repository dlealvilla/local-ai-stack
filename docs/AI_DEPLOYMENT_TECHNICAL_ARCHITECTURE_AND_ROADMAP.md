# AI Deployment Project
## Technical Architecture, System Design, and Roadmap

**Document role:** Authoritative technical architecture and implementation roadmap  
**Audience:** Cursor, engineers, technical reviewers, future maintainers  
**Current baseline:** Phase 8 — Capacity Planner v1 complete; Phase 9 not yet started  
**Primary rule:** *Core owns concepts. Adapters own implementations. Complete the exoskeleton before adding deep intelligence.*

---

# 1. Purpose

This document defines the target technical architecture for the AI Deployment Project and the roadmap required to reach it.

The product is not merely a model runner or deployment utility. The long-term goal is a modular private enterprise AI operating layer that can:

- inspect heterogeneous hardware and deployment environments;
- acquire, store, deploy, run, stop, update, and remove models safely;
- manage compute and prevent resource oversubscription;
- expose local and external AI through a governed gateway;
- route requests across local models and external APIs;
- attribute usage, latency, errors, and cost by user, team, application, model, and provider;
- provide permission-aware enterprise knowledge and retrieval;
- support Company Brain, Team Brain, and enterprise agents;
- support later adaptation/training workflows without redesigning the core;
- operate in connected, partially connected, and air-gapped environments;
- remain portable across hardware, runtimes, executors, gateways, model sources, and telemetry providers;
- provide a non-technical installation and administration experience.

Development philosophy:

> Build a complete, functional architectural exoskeleton first. Add sophisticated intelligence, prediction, optimization, and automation only after the full platform skeleton exists.

---

# 2. Product North Star

The platform should become a **private enterprise AI infrastructure and Company Brain platform**.

```text
1. PRIVATE AI INFRASTRUCTURE
   models, runtimes, capacity, workloads, gateway, analytics, administration

                    ↓

2. COMPANY BRAIN
   identity, permissions, enterprise knowledge, agents, teams, governance

                    ↓

3. LEARNED INTELLIGENCE
   capacity learning, intelligent routing, adaptation, optimization,
   team-specific intelligence, continual evaluation
```

---

# 3. Architectural Principles

## 3.1 Core owns concepts; adapters own implementations

Core modules define stable concepts and contracts.

Examples of core-owned concepts:

- `HardwareProfile`
- `ResourcePool`
- `ModelMetadata`
- `ModelArtifact`
- `ModelInventoryRecord`
- `RuntimeProfile`
- `ExecutorSpec`
- `CapacityEvidence`
- `WorkloadProfile`
- `ResourceRequirement`
- `ResourceReservation`
- `AdmissionDecision`
- `WorkloadSpec`
- `WorkloadRecord`
- `InferenceEndpoint`
- `RouteDecision`
- `UsageEvent`
- `Subject`
- `Team`
- `Policy`
- `KnowledgeRecord`
- `AgentProfile`
- `TeamBrain`
- `Entitlement`

Third-party products implement or contribute evidence behind those concepts.

| Third-party technology | Architectural role |
|---|---|
| LiteLLM | Gateway/provider federation adapter |
| vLLM | Inference runtime adapter |
| llama.cpp | Inference runtime adapter |
| MLX | Apple inference runtime adapter |
| Hugging Face | Model source adapter |
| Docker | Executor adapter |
| Podman | Executor adapter |
| Kubernetes | Future executor/orchestration adapter |
| Open WebUI | Replaceable user-facing frontend |
| PostHog | Optional product telemetry exporter |
| llmfit | Capacity evidence provider |
| Hugging Face Accelerate | Capacity evidence provider |
| llm-d-planner | Capacity evidence provider |
| Infermark | Runtime-neutral benchmark provider |

No third-party package should become the semantic owner of a platform concept.

## 3.2 Capability-based, not server-type-based

The platform reasons in detected capabilities rather than named machine types.

It must support, over time:

- Linux x86_64 and ARM64;
- NVIDIA;
- AMD;
- Intel accelerators;
- Apple Silicon;
- physical workstations;
- cloud VMs;
- virtual machines;
- compatible mini-PC/prosumer systems.

Primary validated reference: **Linux x86_64 + NVIDIA**.

## 3.3 Native execution is first-class

Docker is optional, not mandatory.

```text
Executor
├── NativeProcessExecutor
├── DockerExecutor
├── PodmanExecutor
├── VMExecutor
└── KubernetesExecutor          # later
```

## 3.4 Runtimes are replaceable

```text
InferenceRuntime
├── VLLMRuntime
├── LlamaCppRuntime
├── MLXRuntime
├── ROCmRuntime
├── IntelRuntime
└── CPURuntime
```

Runtime-specific controls stay inside runtime adapters.

## 3.5 Fail conservatively

Unknown is a valid state. Prefer explicit uncertainty over fabricated precision.

## 3.6 Control plane and data plane remain separated

The control plane decides what should run and under what policy. The data plane executes workloads.

---

# 4. High-Level Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                        EXPERIENCE LAYER                         │
│ Admin UI   User AI UI   Diagnostic Assistant   API / SDK        │
│ Agent Clients   Enterprise Applications                         │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         CONTROL PLANE                           │
│ Platform API                                                     │
│ Identity / Teams / Policy                                       │
│ Model Catalog / Inventory                                       │
│ Capacity Planner                                                 │
│ Resource Manager                                                 │
│ Gateway Control / Routing Policy                                │
│ Knowledge Control                                                │
│ Agent / Team Brain Control                                      │
│ Configuration / Entitlements                                    │
└──────────────┬──────────────────┬──────────────────┬─────────────┘
               │                  │                  │
               ▼                  ▼                  ▼
┌──────────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ AI SERVICE FABRIC    │ │ KNOWLEDGE FABRIC │ │ EXECUTION FABRIC │
│ Central Gateway      │ │ Connectors       │ │ Executors        │
│ Endpoint Registry    │ │ Ingestion        │ │ Runtime adapters │
│ Route Decision       │ │ ACL / provenance │ │ Workloads        │
│ Local endpoints      │ │ Indexing         │ │ Inference        │
│ External providers   │ │ Retrieval        │ │ Future jobs      │
│ LiteLLM adapter      │ │                  │ │                  │
└──────────┬───────────┘ └────────┬─────────┘ └────────┬─────────┘
           │                      │                    │
           └──────────────────────┼────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                 OBSERVABILITY / INTELLIGENCE                    │
│ UsageEvent              Runtime observations                    │
│ CapacityEvidence        Benchmark evidence                      │
│ Audit / Health          Capacity Evidence Dataset               │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  CONTROLLED OUTBOUND BOUNDARY                   │
│ Heartbeat   Product Telemetry   Cloud Analytics   Licensing     │
│ Update Check   Crash/Error Reporting                             │
└─────────────────────────────────────────────────────────────────┘
```

---

# 5. Platform API

The Platform API is the stable control-plane boundary.

It should eventually expose domains such as:

```text
/hardware
/models/catalog
/models/inventory
/capacity
/workloads
/gateway
/routes
/usage
/identity
/teams
/knowledge
/agents
/configuration
/telemetry
/entitlements
/health
```

Frontends should consume platform APIs, not runtime/process internals.

---

# 6. Hardware and Capability Layer

Responsibilities:

- inspect host;
- normalize capabilities;
- expose live resource state;
- identify compatible runtimes/executors;
- inform Capacity Planner and installer.

Eventually capture:

- OS/version;
- CPU/architecture;
- RAM;
- accelerator vendor/count;
- accelerator memory;
- unified memory;
- storage;
- container runtimes;
- virtualization;
- network/ports;
- driver/runtime versions.

Static capability and live availability remain separate concepts.

---

# 7. Model Domain

Core concepts:

```text
ModelMetadata
ModelSource
ModelArtifact
ModelInventoryRecord
ModelRevision
ModelLicenseMetadata
ModelCompatibility
```

Model sources:

```text
ModelSourceAdapter
├── HuggingFaceModelSource
├── LocalFilesModelSource
├── EnterpriseRegistryModelSource      # later
└── FutureModelSource
```

Inventory states should support:

```text
downloading
stored
loaded
running
stopped
updating
failed
```

Inventory eventually exposes source, revision, installed bytes, runtime, executor, load/service state, reservation, activity, quantization, license, lineage.

---

# 8. Model Lineage

```text
BaseModelArtifact
    ├── QuantizedModelArtifact
    ├── ConvertedModelArtifact
    ├── AdapterArtifact
    ├── FineTunedModelArtifact
    └── DistilledModelArtifact
```

Related:

```text
DatasetArtifact
EvaluationArtifact
BenchmarkArtifact
TrainingConfiguration
```

Training is deferred, but future lineage must remain possible.

---

# 9. Capacity Planner

Capacity Planner answers:

> Given model + host + runtime + runtime configuration + workload profile + current state, what appears feasible and what configuration is recommended?

Capacity Planner **recommends**.

Resource Manager **authorizes**.

---

# 10. Capacity Evidence

External estimation/benchmark tools are evidence providers.

```text
Model
Hardware
Runtime
RuntimeConfiguration
WorkloadProfile
       │
       ▼
CapacityEvidenceProvider[]
       ├── Internal estimator
       ├── llmfit adapter
       ├── HF Accelerate adapter
       ├── llm-d-planner adapter
       ├── runtime-native evidence
       ├── vLLM benchmark adapter
       ├── Infermark adapter
       └── future providers
       │
       ▼
Normalized CapacityEvidence
       │
       ▼
Capacity Planner
       │
       ▼
Recommendation + confidence + assumptions
```

CapacityEvidence should support provider/version, evidence type, model/revision, hardware, runtime/configuration, memory components, concurrency, throughput, TTFT, ITL, TPOT, confidence, assumptions, timestamp, and source.

Observed empirical evidence generally has greater confidence than theoretical estimates.

---

# 11. WorkloadProfile

Capacity decisions eventually depend on:

```text
Model + Hardware + Runtime + RuntimeConfiguration + WorkloadProfile
```

WorkloadProfile should support:

```text
average_input_tokens
maximum_input_tokens
average_output_tokens
maximum_output_tokens
request_rate
burstiness
request_concurrency
streaming
target_ttft
target_itl
target_tpot
priority_class
```

---

# 12. Concurrency Model

Do not collapse concurrency into one number.

```text
memory_max_concurrency
performance_max_concurrency
slo_max_concurrency
configured_concurrency
platform_max_concurrent_requests
```

Resource Manager/Gateway use safe configured or admitted limits, not theoretical maxima.

---

# 13. Resource Manager

Resource Manager manages **workloads**, not only models.

Core concepts:

```text
WorkloadSpec
WorkloadRecord
ResourceRequirement
ResourceReservation
ResourcePool
AdmissionDecision
RuntimeBinding
WorkloadState
```

Workload types should be representable as:

```text
inference
embedding
reranking
indexing
benchmark
data_processing
training_adaptation
agent_worker
future_job
```

Core flow:

```text
WorkloadSpec
      ↓
Requirement / Capacity evidence
      ↓
Resource Manager
      ↓
AdmissionDecision
      ↓
ResourceReservation
      ↓
Executor
      ↓
Runtime
      ↓
WorkloadRecord
```

Resource Manager owns reservation accounting, safe admission, oversubscription prevention, release, and workload/resource state.

---

# 14. Gateway Architecture

```text
Client
   ↓
Authentication
   ↓
Subject / Team / Application
   ↓
Policy
   ↓
Requested capability/model
   ↓
RouteDecision
   ↓
EndpointRegistry
   ↓
Local or External Endpoint
   ↓
Inference
   ↓
UsageEvent
   ↓
Response
```

---

# 15. LiteLLM

LiteLLM is a strategic adapter, not the platform's semantic owner.

Platform owns:

```text
Gateway
GatewayProvider
InferenceEndpoint
EndpointRegistry
RouteDecision
RoutePolicy
UsageEvent
Subject identity
Cost normalization
```

LiteLLM may implement provider federation:

```text
GatewayProvider
├── BuiltinGatewayAdapter
├── LiteLLMGatewayAdapter
└── FutureGatewayAdapter
```

or:

```text
Platform Gateway
├── LocalInferenceProvider
│    ├── vLLM
│    ├── llama.cpp
│    └── MLX
└── ExternalProviderFabric
     └── LiteLLM
          ├── OpenAI
          ├── Anthropic
          ├── Azure
          ├── Vertex
          └── Bedrock
```

LiteLLM must not own enterprise identity, platform permissions, model identity, Resource Manager state, knowledge permissions, UsageEvent semantics, or entitlements.

---

# 16. Routing

Routing v1:

- explicit model;
- default route;
- local endpoint;
- external endpoint;
- administrator override;
- simple fallback.

Later inputs:

```text
availability
capacity
latency
cost
policy
privacy
data sensitivity
quality
SLO
local-vs-cloud preference
team policy
```

Routing must not directly reserve resources.

---

# 17. Usage Analytics

Normalized `UsageEvent` should support:

```text
request_id
timestamp
subject/user
team
application
model
provider
endpoint
route
input_tokens
output_tokens
latency
error
actual_cost
estimated_cost
```

Local-model cost may be infrastructure-derived.

---

# 18. Three Distinct Outbound/Data Domains

Keep logically separate:

1. Customer AI usage analytics
2. Vendor product telemetry
3. Licensing/entitlements

Prompts, responses, documents, RAG content, and proprietary payloads are not vendor telemetry by default.

---

# 19. Heartbeat / Telemetry Agent

```text
Platform
   ↓
Heartbeat / Telemetry Agent
   ├── Entitlement client
   ├── ProductTelemetryExporter
   ├── CloudUsageExporter
   ├── UpdateChecker
   └── CrashReporter
```

Each channel independently configurable.

Air-gapped mode: all outbound disabled.

---

# 20. Identity and Policy

Core concepts:

```text
Subject
├── User
├── Team
├── Application
└── Agent

Role
Permission
Policy
AccessContext
```

Future adapters:

```text
OIDC
SAML
SCIM
Microsoft Entra ID
Google Workspace
LDAP
LocalIdentity
```

The same normalized identity must be usable by Gateway, Analytics, Knowledge, Agents, Team Brain, and Audit.

---

# 21. Knowledge / Company Brain

```text
Enterprise Sources
       ├── Managed storage
       ├── SharePoint / OneDrive
       ├── Google Drive
       ├── SMB/filesystems
       ├── WebDAV
       ├── databases
       └── future SaaS
       ↓
KnowledgeSourceAdapter
       ↓
Ingestion
       ↓
KnowledgeRecord
       ↓
ACL + Provenance + Version
       ↓
Indexing
       ↓
Permission-aware Retrieval
       ↓
Company / Team / Agent Context
```

KnowledgeRecord should eventually support source, external ID, version, checksum, MIME/content type, owner, ACL, provenance, content reference, metadata, indexing status.

Critical invariant:

> Retrieval must never grant broader access than the source permissions allow.

---

# 22. Company Brain and Team Brain

Company Brain is the permission-aware organizational intelligence layer.

A TeamBrain should eventually reference:

```text
team identity
knowledge scope
tool scope
base-model policy
routing policy
agent profile
evaluation profile
dataset provenance
derived-model lineage
adapter/fine-tuned artifact
```

Initial Team Brain:

```text
Base Model
+
Team permissions
+
Team knowledge
+
Team tools
+
Team prompt/profile
```

Do not begin with training.

---

# 23. Agent Architecture

`AgentProfile` may include:

```text
agent_id
subject identity
team
model/routing policy
knowledge scope
tools
memory scope
permissions
budget
priority
evaluation profile
```

Agents must not bypass identity, knowledge ACL, Gateway policy, Resource Manager, or audit.

---

# 24. Training and Adaptation

MVP need not execute training, but Resource Manager should represent `training_adaptation`.

Future TrainingJob concepts:

```text
priority
CPU requirement
RAM requirement
VRAM requirement
storage requirement
estimated duration
checkpoint support
pause
resume
cancel
quota
preemption policy
```

Evolution:

```text
Team profile + RAG
        ↓
LoRA / PEFT
        ↓
Evaluation
        ↓
Promotion
        ↓
Adapter serving
        ↓
Full fine-tuning where justified
        ↓
Distillation / preference optimization
```

---

# 25. Capacity Intelligence Loop

```text
Estimate
   ↓
Select configuration
   ↓
Deploy
   ↓
Benchmark
   ↓
Observe
   ↓
Compare prediction vs reality
   ↓
Calibrate
   ↓
Improve recommendations
   ↓
Safely admit
```

A future Capacity Evidence Dataset should key evidence by model/revision, hardware, runtime/version, runtime configuration, context, concurrency, and WorkloadProfile.

---

# 26. Installer / Bootstrapper

```text
detect host
    ↓
build capability profile
    ↓
identify compatible components
    ↓
recommend safe configuration
    ↓
download only required components
    ↓
provision runtime/executor
    ↓
configure platform
    ↓
validate health
```

Core concepts:

```text
HostDetector
CapabilityResolver
ComponentResolver
InstallPlan
RuntimeProvisioner
ExecutorProvisioner
ValidationResult
```

Non-technical installability is a requirement.

---

# 27. Admin UI

Dedicated enterprise Admin UI; Open WebUI remains replaceable user frontend.

Initial areas:

```text
Overview
Hardware
Models
Catalog
Inventory
Capacity
Workloads
Gateway
Usage
Teams / Identity
Knowledge
Configuration
Health
Vendor Connectivity
Licensing
```

Advanced settings should support Auto/Manual, recommended value, reason, and confidence.

---

# 28. Diagnostic Assistant

Initial model:

```text
read-only diagnosis
        ↓
recommendation
        ↓
explicit administrator approval
        ↓
controlled action
```

It should explain hardware, configuration, compatibility, capacity, failed lifecycle operations, routing, health, usage, and cost.

---

# 29. Licensing / Entitlements

Core concepts:

```text
Entitlement
LicenseLease
FeatureClaim
CapacityClaim
GracePolicy
OfflineLicense
```

Connected: signed lease + renewal + grace.

Air-gapped: signed offline license + local verification.

No destructive kill switch.

---

# 30. Third-Party Governance

Before commercial release, every bundled dependency should record:

```text
name
version
source
license
provenance
redistribution rights
commercial-use status
SBOM identity
```

Classification:

```text
GREEN   permissive/commercially acceptable
AMBER   obligations/restrictions require review
RED     incompatible or explicit commercial decision required
```

Generate an SBOM for packaged releases.

---

# 31. Security / Privacy Invariants

- Prompts, responses, documents, RAG content, and proprietary payloads are not vendor telemetry by default.
- Knowledge retrieval cannot broaden enterprise permissions.
- Secrets stay separate from normal analytics/config.
- Outbound categories must be visible/configurable.
- Sensitive admin actions should eventually be auditable.

---

# 32. MVP Architecture Completion Criteria

The architecture is sufficiently realized for MVP when a non-technical administrator can:

1. install on a supported host;
2. have hardware detected automatically;
3. discover/import models;
4. see compatibility;
5. deploy safely;
6. run multiple workloads without oversubscription;
7. expose local/external AI through Gateway;
8. optionally use LiteLLM for external federation;
9. see usage/latency/errors/tokens/cost;
10. configure users/teams/policies;
11. connect at least one enterprise knowledge source;
12. perform permission-aware retrieval;
13. use a team/enterprise agent against permitted knowledge;
14. troubleshoot in Admin UI;
15. inspect telemetry/licensing state;
16. operate fully locally where required.

---

# 33. Technical Roadmap

## MILESTONE A — PRIVATE AI INFRASTRUCTURE EXOSKELETON

### Phase 9 — Resource Manager / Multi-Model Lifecycle

**Objective:** authoritative resource admission and workload lifecycle.

**Must achieve**
- `WorkloadSpec`
- `WorkloadRecord`
- `ResourceRequirement`
- `ResourceReservation`
- `AdmissionDecision`
- durable reservation state
- reservation before start
- release after stop/unload
- oversubscription prevention
- explainable denial
- multiple workload records
- runtime-agnostic core
- generic `workload_type` even if only inference executes initially

**Must not build yet**
- advanced scheduler
- preemption
- multi-host scheduling
- training execution
- learned memory prediction

**Completion criteria**
- two workloads cannot overcommit the same pool
- denied admission causes no lifecycle mutation
- reservation is created before start
- reservation is released after stop/unload
- multiple workload records coexist safely

---

### Phase 10 — Gateway Federation and Routing v1

**Objective:** platform-owned Gateway abstraction plus LiteLLM integration.

**Must achieve**
- `GatewayProvider`
- `InferenceEndpoint`
- `EndpointRegistry`
- `RouteDecision`
- `RoutePolicy`
- local provider adapter
- LiteLLM adapter
- explicit/default routing
- local and external endpoint support
- normalized UsageEvent
- cost attribution

**Completion criteria**
- same platform API can route local and external requests
- LiteLLM can be replaced without changing core contracts
- every request produces normalized usage metadata
- manual selection/override works

**Deferred**
- cost-aware routing
- learned routing
- quality routing
- advanced fallback graphs

---

### Phase 11 — Identity / Teams / Policy

**Objective:** one shared normalized identity model.

**Must achieve**
- Subject
- User
- Team
- Application
- Agent placeholder
- Role
- Permission
- Policy
- AccessContext

**Completion criteria**
- requests attributed to Subject
- users belong to teams
- policies reference subjects/teams
- UsageEvent carries identity
- Knowledge/Agents can reuse the same identity model

---

### Phase 12 — Admin UI v1 + Diagnostic Assistant

**Objective:** non-technical infrastructure control surface.

**Must achieve**
- Overview
- Hardware
- Catalog
- Inventory
- Capacity
- Workloads
- Gateway
- Usage
- Teams
- Configuration
- Health
- Vendor Connectivity
- read-only diagnostic assistant with recommendations

**Completion criteria**
Normal platform administration no longer requires shell commands.

---

### Phase 13 — Vendor Connectivity / Heartbeat

**Objective:** one controlled outbound boundary.

**Must achieve**
- HeartbeatAgent
- ProductTelemetryExporter
- CloudUsageExporter
- UpdateChecker
- CrashReporter
- independent channel toggles
- air-gapped mode

---

### Phase 14 — Licensing / Entitlement Skeleton

**Must achieve**
- signed entitlement
- local verification
- feature/capacity claims
- renewal
- grace
- offline license
- Admin UI status

---

### Phase 15 — Bootstrapper / Installer + Release Governance

**Must achieve**
- HostDetector
- CapabilityResolver
- ComponentResolver
- InstallPlan
- RuntimeProvisioner
- ExecutorProvisioner
- ValidationResult
- guided install
- dependency/license manifest
- Green/Amber/Red classification
- SBOM
- signed release metadata
- offline hooks

**Milestone A completion:** clean supported host can become a functioning private AI deployment through a guided workflow.

---

# MILESTONE B — COMPANY BRAIN EXOSKELETON

### Phase 16 — Knowledge/Data Layer

**Must achieve**
- KnowledgeSourceAdapter
- KnowledgeSource
- KnowledgeRecord
- ACL
- Provenance
- Indexer
- RetrievalContext
- RetrievalResult
- at least a small initial connector set
- permission-aware retrieval

**Completion criteria**
A user retrieves only content they are authorized to access.

---

### Phase 17 — Company Brain / Team Agent v1

**Must achieve**
- AgentProfile
- TeamBrain
- knowledge scope
- tool scope
- model/routing policy
- team permissions
- profile/prompt configuration

Initial implementation:

```text
Base model + Team identity + Team knowledge + Team tools + Team profile
```

**Completion criteria**
A team agent can use permitted organizational knowledge/tools through Gateway and produce UsageEvents.

---

### Phase 18 — Workflow / Multi-Agent Foundation

**Must achieve**
- Task
- AgentExecution
- ToolInvocation
- Workflow
- HumanApproval
- Delegation

**Completion criteria**
Structured agent execution, governed tools, approval points, and simple delegation are representable.

---

# MILESTONE C — LEARNED INTELLIGENCE

### Phase 19 — Capacity Intelligence v2

**Must achieve**
- CapacityEvidence
- CapacityEvidenceProvider
- CapacityEvidenceDataset
- WorkloadProfile
- selected theoretical/empirical providers
- concurrency distinctions
- prediction-vs-observation comparison
- confidence/assumption reporting

Capacity Planner remains advisory; Resource Manager remains authoritative.

---

### Phase 20 — Intelligent Routing

**Possible inputs**
- availability
- capacity
- latency
- cost
- privacy
- policy
- quality
- SLO
- team preference

**Completion criteria**
Explainable policy-generated RouteDecision with admin override.

---

### Phase 21 — Team Brain Adaptation

**Must achieve**
- DatasetArtifact
- provenance
- TrainingJob
- AdapterArtifact
- EvaluationArtifact
- PromotionState
- LoRA/PEFT
- evaluation
- promotion
- adapter serving

Training runs through Resource Manager workload contracts.

---

### Phase 22+ — Advanced Intelligence

Potential later:
- full fine-tuning
- distillation
- preference optimization
- continual evaluation
- learned routing
- multi-host placement
- fleet scheduling
- cost/energy optimization
- automatic capacity calibration
- automatic Team Brain improvement
- organizational collective intelligence

---

# 34. Current Baseline

```text
Phase 8: COMPLETE
Capacity Planner v1: functional
Model Inventory: functional
Model Catalog: functional foundation
Storage lifecycle: safe foundation
Gateway: existing foundation; federation/routing abstraction still required
Analytics: foundational work exists
Resource Manager: NEXT
Company Brain: architecture defined, not implemented
Team Brain: architecture defined, implementation deferred
LiteLLM: planned Gateway adapter, not platform authority
```

Next technical phase:

> **Phase 9 — Resource Manager / Multi-model lifecycle**

---

# 35. Scope-Control Rules

Before adding sophistication, ask:

> Does another major subsystem still lack a working implementation?

If yes, complete the missing subsystem first.

A subsystem is "done enough" when:

1. core concept exists;
2. interfaces are clear enough for adjacent systems;
3. one working vertical implementation exists;
4. failure behavior is explicit;
5. obvious safety invariants are enforced;
6. deferred sophistication is documented.

---

# 36. Architecture Decision Rules

Prefer:

1. platform-owned interfaces over third-party semantics;
2. replaceability over convenience coupling;
3. explicit contracts over hidden global state;
4. deterministic safe failure over heuristic success;
5. smallest complete vertical implementation;
6. portability;
7. permission safety;
8. offline capability where practical;
9. few mandatory infrastructure dependencies;
10. explicit documentation of provisional implementations.

---

# 37. Mandatory Labels

Use:

```text
WORKING
PROVISIONAL
DEFERRED
```

Example:

```text
PROVISIONAL:
candidate-memory estimator uses artifact bytes plus a simple safety allowance.

DEFERRED:
SLO-aware learned concurrency optimization.
```

---

# 38. Guidance for Cursor

For every implementation task:

1. identify current roadmap phase;
2. identify core concept;
3. identify owning module;
4. identify adapter boundary;
5. define dependencies before code changes;
6. avoid adjacent future functionality;
7. preserve stable interfaces unless a real architectural defect exists;
8. mark shortcuts PROVISIONAL;
9. mark recognized future capability DEFERRED;
10. update architecture docs if a core contract materially changes.

Cursor must not:

- make LiteLLM the authoritative Gateway model;
- make vLLM assumptions part of Resource Manager core;
- hard-code NVIDIA into core resource contracts;
- require Docker;
- make Hugging Face the only ModelSource;
- make Open WebUI the Admin UI;
- make PostHog mandatory;
- allow knowledge retrieval to bypass ACL;
- let agents bypass Gateway/Policy/Resource Manager;
- start Team Brain with fine-tuning;
- over-refine Capacity Planner before completing the exoskeleton.

---

# 39. Final Technical Doctrine

```text
Platform concept
        ↓
Stable interface
        ↓
Replaceable implementation adapter
        ↓
External/runtime technology
```

Examples:

```text
GatewayProvider → LiteLLMGatewayAdapter → LiteLLM
InferenceRuntime → VLLMRuntimeAdapter → vLLM
ModelSource → HuggingFaceAdapter → Hugging Face
CapacityEvidenceProvider → LLMFitAdapter → llmfit
ProductTelemetryExporter → PostHogExporter → PostHog
```

The platform becomes more capable by adding implementations and evidence, not by surrendering ownership of its core concepts.
