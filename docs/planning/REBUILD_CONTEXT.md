# AI STACK — CLEAN-SLATE REBUILD CONTEXT

**Status:** Authoritative
**Purpose:** Why AI Stack exists, how it relates to the previous AI Deployment Project, and the
doctrine every implementation decision must follow.

Read together with:

- [`docs/source/COMPANY_BRAIN_PLATFORM.md`](source/COMPANY_BRAIN_PLATFORM.md) — the product vision
  and architectural constitution;
- [`docs/DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md) — the operating contract;
- the technical roadmap, which derives its build sequence from this document.

---

## 1. WHAT AI STACK IS

AI Stack is a **new clean-slate implementation**, not a continuation or refactor of the previous AI
Deployment Project codebase.

The previous project had an important purpose: it was used to **explore the technical problem space
by actually building through it**.

During that earlier implementation we learned, through practical experience, how the platform needed
to behave across areas such as:

- host and hardware detection;
- model discovery and acquisition;
- storage safety;
- model inventory;
- capacity planning;
- runtime configuration;
- inference lifecycle;
- resource management;
- gateway design;
- analytics;
- modular adapters;
- persistence and reconciliation;
- failure handling;
- licensing;
- telemetry;
- knowledge integration;
- Team Brain concepts;
- installer design;
- enterprise administration.

That implementation was valuable because it exposed architectural problems and requirements that
would have been difficult to anticipate purely from theory.

It showed us:

- where abstractions were missing;
- where responsibilities became coupled;
- which concepts needed to be first-class;
- which third-party dependencies needed replaceable boundaries;
- where implementation went too deep too early;
- which sequencing decisions created unnecessary rework;
- what information later modules depend on;
- what must be persisted early;
- what must be permission-aware;
- what must remain runtime-, executor-, hardware-, gateway-, and model-source-agnostic.

The earlier project should therefore be treated as **technical exploration and architectural
research**.

It should **not** be treated as the implementation baseline for AI Stack.

---

## 2. WHY AI STACK EXISTS

We have now traversed enough of the technical path to understand the product much more completely.

Instead of continuing to modify an architecture that evolved incrementally while we were still
discovering the problem, AI Stack starts again from first principles.

The objective is now:

> Build the platform from scratch while already knowing the major systems that must exist, how they
> relate to each other, what abstractions they require, and in what dependency order they should be
> implemented.

This is the central purpose of AI Stack.

The previous project answered:

> **What does building this type of platform actually involve?**

AI Stack now answers:

> **Given everything we learned, what is the correct architecture and build sequence from the
> beginning?**

---

## 3. PREVIOUS WORK IS EVIDENCE, NOT CODE TO PRESERVE

Treat the previous AI Deployment Project as a source of:

- architectural lessons;
- validated requirements;
- operational evidence;
- discovered edge cases;
- design decisions;
- failure modes;
- sequencing lessons;
- product insights.

Do **not** assume that previous source files, APIs, directory structures, schemas, class names,
module boundaries, runtime state, checkpoints, temporary solutions or implementation shortcuts must
be preserved.

If an old implementation pattern is still the best solution, it can be recreated deliberately.

If a better structure is now obvious, AI Stack should use the better structure.

**There is no compatibility obligation with the previous internal implementation unless explicitly
stated.**

---

## 4. CLEAN-SLATE PRINCIPLE

For every major subsystem, ask:

1. What concept does the platform actually need to own?
2. What other modules depend on this concept?
3. What must be stable before those modules can be built?
4. What should belong in core?
5. What belongs behind an adapter?
6. What state must survive restart?
7. What failure and reconciliation semantics are required?
8. What information will later intelligence features need?
9. What is the smallest complete implementation we need now?
10. What sophistication should deliberately be deferred?

The architecture must be derived from the complete Company Brain product vision, not from the
structure of the old repository.

---

## 5. BUILD WITH FORESIGHT

AI Stack should be built progressively, but **progressive does not mean improvised**.

The entire architectural skeleton should be understood before deep implementation begins.

We already know the final platform will require concepts such as:

| | |
| --- | --- |
| HostCapabilities | component resolution |
| Executor abstraction | InferenceRuntime abstraction |
| ModelSource | ModelMetadata |
| ModelArtifact | ModelInventory |
| ModelRequirement | CapacityEvidence |
| Capacity Planner | DeploymentPlan |
| Workload | ResourceReservation |
| Resource Manager | InferenceInstance |
| Gateway | identity and AccessPolicy |
| UsageEvent | KnowledgeSource |
| permission-aware retrieval | Admin UI |
| Admin AI Agent | TeamBrain |
| telemetry | entitlements |
| installer/update infrastructure | future adaptation and model intelligence |

Not all of these should be deeply implemented immediately.

But the early architecture must avoid decisions that make them difficult to add later.

---

## 6. PROGRESSIVE BUILD MODEL

Each AI Stack stage should produce a **stable output that becomes the formal input to the next
stage**:

```text
Platform Contracts
        ↓
HostCapabilities
        ↓
Resolved Components
        ↓
Storage Capacity
        ↓
Model Metadata / Artifact
        ↓
Model Requirement
        ↓
Capacity Assessment
        ↓
Deployment Plan
        ↓
Admission Decision
        ↓
Resource Reservation
        ↓
Inference Instance
        ↓
Inference Endpoint
        ↓
Route Decision
        ↓
Usage Event
        ↓
Authorized Knowledge Context
        ↓
Team Brain / Higher Intelligence
```

Later modules must consume these normalized outputs rather than independently rediscovering or
redefining the same information.

---

## 7. EXOSKELETON FIRST

> **Complete the product exoskeleton before deeply optimizing individual subsystems.**

The first priority is a complete end-to-end system that can:

```text
install/bootstrap
→ inspect host
→ understand capacity
→ discover a model
→ evaluate it
→ safely acquire it
→ reserve resources
→ start inference
→ expose it through the gateway
→ accept a request
→ record usage
→ show it to the administrator
→ stop/restart safely
→ reconcile after restart
```

Then add the Company Brain knowledge spine:

```text
identity
→ knowledge source
→ permissions
→ indexing
→ authorized retrieval
→ RAG
→ employee experience
→ Team Brain
```

Only after those major architectural boxes exist should AI Stack go deeply into empirical capacity
learning, intelligent routing, model portfolio optimization, fine-tuning, LoRA, distillation,
multi-host optimization or autonomous organisational coordination.

---

## 8. DO NOT REBUILD OLD TECHNICAL DEBT

Do not reproduce a previous implementation merely because it already existed.

Avoid:

- carrying forward accidental coupling;
- preserving temporary abstractions;
- hard-coding one runtime;
- hard-coding Docker;
- hard-coding NVIDIA;
- making Hugging Face the domain model;
- making LiteLLM the domain model;
- mixing runtime configuration with platform concepts;
- mixing Resource Manager with licensing;
- mixing customer analytics with vendor telemetry;
- mixing retrieval permission with training permission;
- hiding state inside process-specific logic;
- adding sophisticated logic before its upstream contracts are stable.

The previous project taught us where these problems arise. AI Stack exists so we do not need to
rediscover them through another sequence of rewrites.

---

## 9. CORE ARCHITECTURAL DOCTRINE

> **Core owns concepts; adapters own implementations.**

```text
Platform Gateway          InferenceRuntime          ModelSource          Executor
    ↓                          ↓                        ↓                   ↓
Gateway adapter           VLLMRuntimeAdapter       HuggingFaceSource    DockerExecutor
    ↓                          ↓                        ↓                   ↓
LiteLLM                        vLLM                 Hugging Face          Docker
```

Not:

```text
Platform
    ↓
LiteLLM concepts everywhere
```

Third-party technologies accelerate AI Stack. **They do not define AI Stack.**

---

## 10. DEFINITION OF AI STACK

> **The deliberate production-oriented rebuild of the Company Brain platform, created after using
> the previous AI Deployment Project to explore and understand the technical problem space.**

The first project was how we learned the terrain. AI Stack is where we build the road properly.

The goal is not to reproduce the previous code more neatly. The goal is to use everything we learned
to build the **correct modular architecture in the correct order from the beginning**, while still
progressing through small, testable, consolidated stages.

When making implementation decisions, always prioritize the long-term architectural integrity of
AI Stack over compatibility with the exploratory implementation that came before it.
