# Cursor Architecture Guide
## AI Deployment Project

**Purpose:** Operational architecture guide for Cursor.

Read `AI_DEPLOYMENT_TECHNICAL_ARCHITECTURE_AND_ROADMAP.md` before making architectural changes.

---

# 1. Current technical position

```text
Phase 8: COMPLETE
Phase 9: NEXT
```

Next subsystem:

> **Resource Manager / Multi-model lifecycle**

Do not restart Capacity Planner refinement unless a real defect blocks Phase 9.

---

# 2. Primary rule

> **Core owns concepts. Adapters own implementations.**

```text
Core concept                  Adapter / implementation
──────────────────────────    ─────────────────────────────
GatewayProvider               LiteLLM
InferenceRuntime              vLLM / llama.cpp / MLX
ModelSource                   Hugging Face / local files
Executor                      process / Docker / Podman
CapacityEvidenceProvider      llmfit / Accelerate / benchmarks
ProductTelemetryExporter      PostHog / future exporter
```

Never let a third-party library become the platform's semantic authority.

---

# 3. Product direction

```text
PRIVATE AI INFRASTRUCTURE
        ↓
COMPANY BRAIN
        ↓
LEARNED INTELLIGENCE
```

Do not jump directly to the third layer.

---

# 4. Phase discipline

Before coding, identify:

```text
Current phase
Required outcome
Core contracts
Adapters involved
Completion criteria
Deferred work
```

Stop a phase once its exoskeleton exists.

---

# 5. Phase 9 requirements

Core concepts:

```text
WorkloadSpec
WorkloadRecord
ResourceRequirement
ResourceReservation
AdmissionDecision
RuntimeBinding
WorkloadState
```

Represent workload types generically:

```text
inference
embedding
reranking
indexing
benchmark
training_adaptation
agent_worker
```

Phase 9 must achieve:

- durable reservation state;
- admission before start;
- no mutation after denied admission;
- oversubscription prevention;
- release after stop/unload;
- multiple workload records;
- runtime-agnostic core.

Do not add:

- advanced scheduler;
- fleet scheduling;
- training implementation;
- learned memory prediction.

---

# 6. LiteLLM rule

Correct:

```text
Platform Gateway
    ↓
GatewayProvider
    ↓
LiteLLMGatewayAdapter
    ↓
LiteLLM
```

Platform retains ownership of:

- endpoint identity;
- RouteDecision;
- route policy;
- Subject/team/application identity;
- UsageEvent;
- Resource Manager state;
- knowledge policy;
- cost normalization.

---

# 7. Runtime rule

Runtime-specific controls remain in runtime adapters.

Do not move vLLM-specific settings into generic core semantics.

---

# 8. Capacity rule

Capacity Planner recommends. Resource Manager admits.

```text
CapacityEvidenceProvider
        ↓
CapacityEvidence
        ↓
Capacity Planner
        ↓
recommendation
        ↓
Resource Manager
        ↓
AdmissionDecision
```

External estimators never directly authorize platform admission.

---

# 9. Concurrency rule

Keep distinct:

```text
memory_max_concurrency
performance_max_concurrency
slo_max_concurrency
configured_concurrency
platform_max_concurrent_requests
```

---

# 10. Identity rule

Use one identity model across Gateway, Analytics, Knowledge, Agents, Team Brain, and Audit.

```text
Subject
User
Team
Application
Agent
Role
Permission
Policy
AccessContext
```

---

# 11. Knowledge rule

Knowledge retrieval must preserve ACL semantics.

Core concepts:

```text
KnowledgeSource
KnowledgeRecord
ACL
Provenance
RetrievalContext
```

Never return content outside the requesting Subject's permitted scope.

---

# 12. Team Brain rule

Do not start with training.

First:

```text
Base model
+
Team identity
+
Team permissions
+
Team knowledge
+
Team tools
+
Team profile
```

Training comes later through Resource Manager workload contracts.

---

# 13. Outbound-data rule

Keep separate:

```text
Customer AI analytics
Vendor product telemetry
Licensing / entitlement
```

Prompts, responses, documents, RAG content, and proprietary payloads are not vendor telemetry by default.

---

# 14. Required labels

Use:

```text
WORKING
PROVISIONAL
DEFERRED
```

Do not let provisional heuristics silently become permanent architecture.

---

# 15. Scope-control test

Before adding sophistication, ask:

> Does another major architecture subsystem still lack a working vertical implementation?

If yes, finish that missing subsystem first.

---

# 16. "Done enough"

A subsystem is ready to move on when:

1. core concept exists;
2. interface is understandable;
3. one working implementation exists;
4. failure semantics are explicit;
5. major safety invariants are enforced;
6. future sophistication is documented.

---

# 17. Forbidden shortcuts

Do not:

- make LiteLLM the core Gateway model;
- hard-code vLLM in Resource Manager;
- hard-code NVIDIA into vendor-neutral resource contracts;
- require Docker;
- couple model lifecycle exclusively to Hugging Face;
- make Open WebUI the enterprise Admin UI;
- make PostHog mandatory;
- allow agents to bypass policy/Gateway;
- allow RAG to bypass ACL;
- start fine-tuning before Team Agent/RAG exists;
- add multi-host scheduling before single-host workload control works;
- over-refine Capacity Planner before the wider exoskeleton is implemented.

---

# 18. Architecture changes

If implementation reveals a core-contract problem:

1. state the architectural problem;
2. identify affected modules;
3. distinguish defect from enhancement;
4. update architecture documentation;
5. preserve adapter replaceability;
6. avoid unrelated refactoring.

---

# 19. Roadmap

```text
Phase 9   Resource Manager / Multi-model lifecycle
Phase 10  Gateway federation + LiteLLM
Phase 11  Identity / Teams / Policy
Phase 12  Admin UI + Diagnostic Assistant
Phase 13  Heartbeat / Vendor Connectivity
Phase 14  Licensing / Entitlements
Phase 15  Installer / Release Governance

Phase 16  Knowledge/Data Layer
Phase 17  Company Brain / Team Agent v1
Phase 18  Workflow / Multi-Agent Foundation

Phase 19  Capacity Intelligence v2
Phase 20  Intelligent Routing
Phase 21  Team Brain Adaptation
Phase 22+ Advanced intelligence
```

---

# 20. Final instruction to Cursor

Optimize for:

```text
modularity
replaceability
portability
permission safety
explicit contracts
conservative admission
complete vertical functionality
scope discipline
```

The goal is not to perfect each subsystem before moving on.

The goal is a coherent enterprise AI platform whose major architecture already fits together before deeper optimization begins.
