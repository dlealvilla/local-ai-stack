# KULTRUN
## Company Brain Platform — Complete Product Vision and Architectural Constitution
### Clean-Slate Rebuild — September 2026

**Kultrun** is the company and the product. **Company Brain** describes
what it is: a self-hosted organisational intelligence layer. Where this
document says "Kultrun", it means the product; where it says "Company
Brain", it means the capability the product delivers.

---

# 0. DOCUMENT PURPOSE

This document defines the complete product vision for a clean-slate rebuild of Kultrun.

The previous implementation should not constrain the new architecture. It should be treated only as an iteration that exposed important requirements, architectural risks, operational realities, and product opportunities.

The new system should therefore be designed **end-to-end before implementation begins**, with:

- clear domain boundaries;
- replaceable infrastructure components;
- normalized internal data models;
- conservative safety;
- strong privacy and permission semantics;
- a complete but intentionally simple first exoskeleton;
- deliberate support for future intelligence without prematurely building every advanced feature.

This document should function as the product's **architectural constitution**.

Technical plans, implementation phases, APIs, repositories, services, schemas, and deployment components should be derived from it.

Two documents derive from this one and are authoritative within their own
scope: `docs/ROADMAP.md` for build sequence and gates, and
`docs/ARCHITECTURE.md` for the module map — where each concept below
lives, what it consumes and produces, and what may depend on what. Where
either disagrees with this document about what a concept *means*, this
document wins.

---

# 1. ONE-SENTENCE PRODUCT VISION

Build a **self-hosted organisational intelligence platform — a secure Company Brain — that non-technical organisations can install onto their existing compute, connect to their knowledge and systems, equip with suitable AI models, and use to organise, manage, enhance, and eventually coordinate the collective intelligence of the company.**

---

# 2. CORE PRODUCT MISSION

The product is not fundamentally:

- a Docker installer;
- an LLM server;
- a model downloader;
- a chatbot frontend;
- a RAG application;
- an analytics dashboard;
- a hardware capacity calculator.

All of those may be important components.

The actual product is an **organisational intelligence operating layer**.

Its purpose is to bring together:

- company knowledge;
- files and information repositories;
- employees and teams;
- permissions and identity;
- AI models;
- AI agents;
- applications;
- infrastructure;
- compute capacity;
- usage;
- analytics;
- workflows;
- organisational context;

into one governed intelligence layer.

Kultrun should progressively answer questions such as:

- What knowledge does this organisation possess?
- Who is allowed to access it?
- What AI capabilities does the organisation have?
- Which models are best suited to this company's work?
- What can the available hardware safely run?
- Which models should be installed?
- Which models should currently be loaded?
- Which model should handle this task?
- How is AI actually being used?
- Which models produce the best outcomes for particular roles and workloads?
- Which teams need specialist AI capabilities?
- Where is organisational intelligence fragmented?
- How can knowledge and AI be used more effectively across teams?

The long-term ambition is a **Company Brain that enhances the collective intelligence and coordination capacity of the organisation**.

---

# 3. PRIMARY PRODUCT EXPERIENCE

The product should feel less like deploying AI infrastructure and more like **installing an intelligence layer for the company**.

A business administrator should be able to:

1. download a small installer;
2. run it on suitable company hardware;
3. allow Kultrun to inspect the machine;
4. answer simple business questions;
5. receive recommended infrastructure and model choices;
6. approve installation;
7. connect company document systems;
8. configure users and permissions;
9. select or accept recommended AI models;
10. begin providing governed AI capabilities to employees;
11. manage Kultrun primarily through an AI Admin Agent and clear visual controls.

The administrator should not need to understand:

- CUDA;
- ROCm;
- MLX;
- vLLM;
- Docker;
- KV caches;
- tensor parallelism;
- model quantization;
- VRAM allocation;
- storage staging;
- process supervision;

to perform ordinary administration.

Those concepts may remain available to advanced administrators, but they are implementation details from the perspective of the normal product experience.

---

# 4. PRIMARY USERS

## 4.1 Business Administrator

The primary administrator may be:

- an operations manager;
- business owner;
- office administrator;
- innovation manager;
- IT generalist;
- technology-savvy manager;
- internal AI champion.

They should not be assumed to be:

- a Linux administrator;
- an ML engineer;
- a Kubernetes engineer;
- a GPU expert.

Kultrun must therefore explain decisions in business language and automate technical configuration.

---

## 4.2 Technical Administrator

Larger organisations may have:

- infrastructure teams;
- security teams;
- ML engineers;
- platform engineers;
- enterprise architects.

These users need deeper access to:

- infrastructure configuration;
- policies;
- runtime configuration;
- logs;
- resource reservations;
- advanced deployment controls;
- networking;
- connectors;
- security controls;
- APIs.

The simple experience must not remove advanced control.

---

## 4.3 Employees / End Users

Employees should be able to access approved organisational AI capabilities without understanding the infrastructure behind them.

Their experience may eventually include:

- general company AI assistant;
- knowledge search;
- model selection where permitted;
- specialist Team Brains;
- tools;
- workflows;
- departmental agents;
- application integrations.

---

## 4.4 Vendor Operator

For connected commercial deployments, vendor systems may need to manage:

- licensing;
- entitlements;
- software versions;
- non-content telemetry;
- optional cloud analytics;
- update availability;
- commercial configuration.

Vendor access must not imply access to customer AI content.

---

# 5. GUIDING ARCHITECTURAL PRINCIPLES

These principles should be treated as non-negotiable unless deliberately revised later.

## 5.1 Core Owns Concepts; Adapters Own Implementations

Kultrun owns concepts such as:

- Model;
- Model Artifact;
- Knowledge Source;
- Inference Instance;
- Capacity Evidence;
- Workload;
- Usage Event;
- Entitlement;
- Team Brain.

Third-party projects implement capabilities behind interfaces.

Kultrun must not allow an external tool to define its domain model.

---

## 5.2 No Single Infrastructure Technology Defines the Product

The product must not fundamentally depend on:

- Docker;
- Kubernetes;
- LiteLLM;
- vLLM;
- Hugging Face;
- OpenCloud;
- Nextcloud;
- Nango;
- PostHog;
- Open WebUI;
- MLflow;
- any specific GPU vendor;
- any specific model provider.

Any of these may be excellent initial implementations.

They remain replaceable.

---

## 5.3 Capability-Based Deployment

Kultrun should ask:

> What capabilities does this host expose?

not:

> Is this the type of server we expect?

Deployment decisions should derive from:

- operating system;
- architecture;
- available compute;
- accelerators;
- memory;
- storage;
- runtimes;
- executors;
- drivers;
- networking;
- security policy.

---

## 5.4 Safety Before Optimisation

When capacity or compatibility is uncertain, the system should prefer:

- conservative estimates;
- additional evidence;
- reduced concurrency;
- more headroom;
- conditional compatibility;
- denial when safety cannot be established.

It should not maximize resource utilisation at the expense of reliability.

---

## 5.5 Explainability

Important recommendations should explain:

- what was detected;
- what evidence was used;
- what assumptions were made;
- why something is allowed or denied;
- what alternatives are available;
- how confident the recommendation is.

---

## 5.6 Graceful Degradation

Optional integrations should improve the product but must not determine whether the core product functions.

Examples:

- no llmfit → AUTO mode falls back to the Kultrun requirement estimator; strict `llmfit` mode does not. llmfit is never capacity authority;
- no PostHog → local product telemetry still functions or is disabled;
- no Docker → native executor may be used;
- no external model source → local imports remain possible;
- no cloud → local operation remains possible.

---

## 5.7 Privacy by Architecture

Prompts, responses, documents, RAG context, proprietary files, and other customer content remain inside the customer environment by default.

Outbound communication must be:

- explicit;
- minimized;
- categorized;
- inspectable;
- configurable where appropriate.

---

## 5.8 Permission Awareness Everywhere

Knowledge available to Kultrun is not automatically available to every user or model.

Identity and authorization must be enforced throughout:

- retrieval;
- RAG;
- search;
- connectors;
- Team Brains;
- agents;
- tools;
- model access;
- administrative actions.

---

## 5.9 Exoskeleton First

The first goal is a complete end-to-end system with simple implementations.

It is preferable to have:

> host detection → model selection → safe acquisition → start → gateway → user request → analytics → admin visibility

working simply,

than to deeply optimize one subsystem while the full product does not yet exist.

---

## 5.10 Kultrun Owns Meaning; Providers Own Observations

A companion to §5.1. Core owns concepts and adapters own implementations —
and specifically, for anything Kultrun learns about the world:

> External tooling answers "what does this machine appear to contain?"
> Kultrun answers "what do those observations mean, and what may we safely
> do with them?"

Kultrun should not reimplement commodity hardware enumeration. Mature
projects already discover CPU topology, NUMA, PCI devices, accelerators and
node features, across more platforms than Kultrun will ever validate.
Rebuilding that is a large proprietary investment in something no customer
would pay for.

So discovery is a **provider architecture**:

```text
mature discovery and vendor tooling
  → replaceable discovery provider adapters
    → Kultrun normalization and reconciliation
      → Kultrun-owned HostCapabilities
        → safe capacity
          → model, runtime and executor decisions
```

Providers may be partial, absent, slow or wrong. Unknown stays unknown, a
failed provider means that source was unavailable rather than that the host
is unsupported, and no provider's schema becomes Kultrun's schema.

**Reference implementation is not architectural dependency.** A tool being
the first one validated does not make it required.

A preferred provider may still be *optional*. Kultrun may eventually
detect, reuse, provision or repair the tooling it prefers, because
plug-and-play means the platform takes responsibility for what it needs
rather than handing a customer a prerequisites list — but preferring
something and depending on it are different commitments, and only the first
survives that tool turning out to be wrong.

**Plug-and-play requires Kultrun to be able to manage its own platform
components.** An administrator should not have to install a discovery tool
by hand because Kultrun chose that tool internally. The target experience
is one command on a fresh supported server:

```text
inspect environment → determine required platform components
  → reuse valid existing components → provision missing supported ones
    → verify → continue
```

Four limits on that, none of which is solved now. Component
implementations stay replaceable. Administrator policy may prohibit
automatic installation. Offline and air-gapped deployments must eventually
work. Vendor drivers may remain administrator-managed or vendor-managed.
And Kultrun must not silently install high-impact system components without
a product policy that says it may — taking responsibility is not the same
as taking liberties.

---

# 6. TOP-LEVEL SYSTEM ARCHITECTURE

The system should conceptually consist of the following planes.

## 6.1 Experience Plane

Interfaces for humans and applications:

- Admin UI;
- Admin AI Agent;
- end-user AI interface;
- programmatic API;
- future team-agent experiences.

---

## 6.2 Control Plane

Owns platform state and decisions:

- host inventory;
- deployment planning;
- model catalog;
- model inventory;
- capacity planning;
- compatibility;
- workload admission;
- Resource Manager;
- configuration;
- policies;
- lifecycle orchestration;
- licensing state.

---

## 6.3 Inference Plane

Runs AI workloads:

- inference instances;
- inference runtimes;
- runtime adapters;
- executors;
- gateway routing;
- request queues;
- runtime concurrency.

---

## 6.4 Knowledge Plane

Connects organisational information:

- platform-managed storage;
- external connectors;
- indexing;
- metadata;
- permissions;
- retrieval;
- RAG;
- search;
- future knowledge graph.

---

## 6.5 Intelligence Plane

Builds higher-order recommendations:

- model effectiveness;
- model ranking;
- model inventory optimization;
- team intelligence;
- Team Brains;
- capacity learning;
- routing intelligence;
- future organisational coordination.

---

## 6.6 Analytics and Evidence Plane

Captures:

- UsageEvents;
- capacity observations;
- model effectiveness;
- performance;
- resource telemetry;
- satisfaction;
- cost;
- system health.

---

## 6.7 Optional Vendor Services Plane

May provide:

- entitlement service;
- billing integration;
- product telemetry collection;
- optional cloud analytics;
- updates;
- crash reporting.

The core customer installation should remain logically distinct from this plane.

---

# 7. LIGHTWEIGHT BOOTSTRAP INSTALLATION

## 7.1 Installer Philosophy

The downloadable application should not contain:

- all supported inference runtimes;
- all container images;
- every hardware library;
- every OS dependency;
- AI model weights;
- every optional integration.

Instead, use a small platform-specific bootstrapper.

Possible bootstrap packages may include:

- Linux AMD64;
- Linux ARM64;
- macOS ARM64;
- Windows AMD64.

Each should contain only enough functionality to:

- inspect;
- plan;
- authenticate if necessary;
- download;
- verify;
- install;
- bootstrap the control plane.

---

# 8. HOST CAPABILITY INSPECTION

Kultrun should produce a normalized `HostCapabilities` representation.

It should inspect at minimum:

## Operating environment

- OS;
- OS version;
- kernel where relevant;
- architecture;
- virtualization state;
- bare metal versus VM.

## CPU

- vendor;
- model;
- architecture;
- core/thread count;
- instruction capabilities where useful.

## Memory

- total RAM;
- currently available RAM;
- shared/unified memory architecture where relevant.

## Accelerators

- GPU/accelerator vendor;
- model;
- count;
- VRAM;
- unified memory;
- driver/runtime versions;
- visible device topology.

Target families include:

- NVIDIA/CUDA;
- AMD/ROCm;
- Intel;
- Apple Silicon/Metal;
- CPU-only.

## Storage

- capacity;
- current free space;
- filesystem information;
- expected performance/type where discoverable;
- platform-managed usage;
- reserved capacity;
- relevant quotas.

## Execution capabilities

- native process execution;
- Docker;
- Podman;
- virtualization;
- later Kubernetes or similar.

## Networking

- interfaces;
- relevant addresses;
- ports;
- DNS;
- outbound connectivity where policy permits;
- local network characteristics needed for deployment.

The result should be normalized and stable regardless of how it was detected.

**How it is obtained is a separate question from what it means.** Kultrun
should not implement this enumeration itself where mature tooling exists.
Per §5.10, observations come from replaceable discovery providers — a
general topology tool, vendor libraries for accelerator detail, native OS
sources where a gap is demonstrated, and a Kubernetes feature source where
one applies. Kultrun collects those observations, normalizes them,
reconciles overlaps, preserves unknowns and surfaces conflicts.

Providers may be partial. A general tool may see that an accelerator exists
without knowing its memory; a vendor library knows its memory but only for
that vendor's hardware; a cluster feature source may label a node without
quantifying anything. `HostCapabilities` is the merge, and it is
Kultrun-owned: not raw topology output, not vendor structures, not cluster
labels.

A normalized value should remain **explainable** — which source supplied
it, when, whether it was measured, reported, derived, configured or
estimated, and with what confidence. A number with no history cannot be
argued with, and §5.5 requires recommendations to be arguable.

---

# 9. DEPLOYMENT PLANNER

The Deployment Planner combines:

- HostCapabilities;
- administrator answers;
- policy;
- model requirements;
- executor availability;
- runtime compatibility;
- storage;
- resource evidence.

It produces a `DeploymentPlan`.

A plan should explain:

- recommended executor;
- recommended runtime;
- required components;
- required downloads;
- expected resource use;
- compatibility;
- confidence;
- administrator actions;
- alternatives.

The administrator should be able to accept safe defaults or manually override selected settings.

---

# 10. EXECUTION ABSTRACTION

Executors are responsible for running processes/services.

Initial executor types should include:

## Native Process Executor

A first-class supported executor.

Important because:

- not every deployment has Docker;
- Apple-native inference may require it;
- small deployments may benefit from fewer layers.

## Docker Executor

Important reference deployment option.

Should remain optional.

Containers answer **how a chosen workload is packaged and launched**. They
do not answer what hardware exists, and they do not answer what Kultrun may
safely consume. Those are §8 and §19–21.

Where a container executor attaches an accelerator, it should use the
vendor-neutral device-attachment standard that container runtimes already
support, with the device specification generated by vendor tooling. Kultrun
should not implement device injection itself. Device attachment happens
*after* the Resource Manager has allocated the device — it is a
consequence of a decision, never a substitute for one.

Native execution is the first validated path and the reference
implementation; container execution is a first-class optional executor.
Container execution is a replaceable execution option, not a requirement.
Neither is privileged in perpetuity. Later, Kultrun may recommend or select
an executor per deployment from host capabilities, runtime support, the
deployment profile, administrator policy and operational evidence — a
choice it earns the right to make once it has evidence on both paths.

Docker must not become mandatory, a commercial container product must not
become a dependency, and Kubernetes must not become the control plane.

## Future Executors

Architecture should allow:

- Podman;
- VM execution;
- Kubernetes;
- remote executors;
- cluster schedulers.

Executor logic must not leak into inference-runtime domain logic.

Runtime defines **what** needs to run. Executor defines **how** that
workload is realized on the host. `InferenceInstance` composes them and
does not implement either:

```text
InferenceInstance
        ↓
InferenceRuntimeAdapter
        ↓
RuntimeLaunchSpec
        ↓
Executor
        ↓
ExecutorHandle
        ↓
Operating Environment
```

A later verified operational runtime (`RuntimeCapabilityProfile`) becomes
an upstream constraint on executable model selection. That verification
and remap are not implied by the existence of the Runtime / Executor seam.

---

# 11. INFERENCE RUNTIME ABSTRACTION

Inference runtimes are separate from executors.

Possible runtime adapters include:

- vLLM;
- llama.cpp;
- MLX/Metal;
- ROCm-oriented runtimes;
- Intel-oriented runtimes;
- future engines.

Each runtime adapter should be responsible for translating platform concepts into runtime-specific configuration.

For example:

- runtime concurrency;
- memory utilisation;
- tensor parallelism;
- model loading;
- context configuration;
- adapter loading.

Core platform logic must not contain vLLM-specific configuration semantics.

---

# 12. FIRST-CLASS INFERENCE INSTANCE

An `InferenceInstance` should be a primary platform concept.

It represents one deployed model-serving workload.

It should conceptually include:

- instance identity;
- host;
- model;
- model revision;
- optional adapter;
- runtime;
- executor;
- endpoint;
- resource reservation;
- configured context;
- runtime concurrency;
- platform concurrency;
- access policy;
- lifecycle state;
- health;
- priority;
- configuration version.

This is different from the stored model artifact.

A stored `ModelArtifact` is data on disk. An `InferenceInstance` is a
deployed serving workload. They must never be collapsed into one object
or one boolean such as `model.running = true`.

The architecture is plural from the first schema:

- `models[]` — zero, one, or many stored artifacts;
- `inference_instances[]` — zero, one, or many running or planned
  workloads.

The first working vertical may store several models and run one
instance. That is an acceptance bound, not an architectural limit.

The same stored artifact may have several inference instances (replicas,
different context or concurrency, departmental isolation, different
device placement, different access policy, or different runtime
configuration). Different models may also run at the same time when
hardware permits — including a general model, a coding model, an
embedding model, and other compatible services.

A `ResourceReservation` is a control-plane commitment: Kultrun has
admitted a defined share of SAFE capacity to a future workload. It is
not physical allocation. It does not prove RAM or VRAM has been granted
by the OS, that a GPU context exists, that a process is running, or that
a model is loaded.

A reservation belongs to a future inference or workload instance, not
globally to a model artifact. Several reservations may reference one
stored artifact. Stopping an instance stops the process and does not
silently release the reservation. Release is an explicit later action.
The stored artifact remains until a separate delete operation.

`STORED` and `ACTIVE` / `RUNNING` are lifecycle labels, not fixed
capacity partitions. There is no stored-memory bucket and no active-memory
bucket. Disk, RAM, VRAM and unified memory stay separate physical
accounts. A stored artifact consumes persistent disk whether or not an
instance is running. Active RAM/VRAM commitments follow the reservations
that currently back live or committed workloads, and they move when those
reservations are released and others are admitted. Several
`InferenceInstance` records may exist at once.

There is no long-term global `selected = true`. Selection produces a
`SelectionRecommendation`: a primary recommendation, alternatives,
rejected candidates, and rationale. A model may be recommended but not
stored; stored but not currently recommended; stored with zero, one, or
many instances.

---

# 13. TWO DIFFERENT CONCURRENCY DIMENSIONS

The architecture must distinguish:

## Request Concurrency

Many requests handled by one loaded inference instance.

## Inference-Instance Concurrency

Several model-serving services running simultaneously.

Example:

- one Qwen server serving 30 simultaneous users;
- plus a coding-model server;
- plus an embedding server.

These are different capacity problems and must not be conflated.

---

# 14. MODEL SOURCE ARCHITECTURE

The model ecosystem should use a replaceable `ModelSource` interface.

Initial implementations:

## HuggingFaceSource

Primary public model discovery and acquisition source.

## LocalFileSource

For local administrator-provided artifacts.

Future sources may include:

- NVIDIA NGC;
- ModelScope;
- MLflow registries;
- Ollama-compatible sources;
- internal artifact stores;
- private enterprise registries.

Kultrun should never embed provider-specific API objects throughout the application.

---

# 15. NORMALIZED MODEL METADATA

External model information should normalize into platform-owned structures such as:

`ModelMetadata`

and:

`ModelArtifact`

Fields may include:

- canonical ID;
- display name;
- source;
- source revision;
- family;
- architecture;
- parameter count;
- modalities;
- task labels;
- intended use;
- context length;
- formats;
- quantization;
- artifact files;
- download size;
- installed size;
- license;
- commercial-use warnings;
- supported runtimes;
- supported hardware;
- memory estimates;
- quality/benchmark metadata;
- provenance.

The schema must remain extensible.

---

# 16. MODEL CATALOG / MARKETPLACE EXPERIENCE

The Admin UI should provide a marketplace-like discovery experience.

The objective is not to display every available model blindly.

Kultrun should answer:

> Which models are appropriate for this organisation and this hardware?

Administrators should be able to filter by:

- task;
- size;
- hardware fit;
- runtime;
- license;
- modality;
- quantization;
- context;
- organisation use case.

Model cards should display:

- compatibility;
- reason;
- confidence;
- expected storage;
- expected memory;
- runtime recommendation;
- model license;
- performance evidence where available.

---

# 17. MODEL INVENTORY

The Model Inventory should track all platform-managed AI artifacts.

Kultrun may store many models on disk. Inventory is not synonymous with
the currently running model. Represent it as `models[]` from the
beginning, never as a single `current_model`.

**Model artifact state** (storage, not runtime):

- remote;
- acquiring;
- stored;
- invalid;
- updating;
- deleted.

A stored artifact consumes disk. It does not necessarily consume VRAM,
runtime RAM, execution slots, or ports.

**Inference instance lifecycle** is a different dimension, owned by
`InferenceInstance`:

- planned;
- starting;
- running;
- stopping;
- stopped;
- failed.

Do not represent both through one model status field. `loaded` and
`running` are instance states, not inventory states.

Inventory should eventually expose:

- model/artifact ID;
- revision;
- source;
- disk footprint;
- verification state;
- installed/stored state;
- runtime compatibility;
- last used;
- derivation/lineage (base model, LoRA/PEFT adapter, fine-tune,
  distillation — hooks now, implementations later);
- approval state;
- relevant permissions;
- whether any inference instances currently reference the artifact.

Initial implementation can be much smaller. The schema must not make
derived or adapter models a redesign.

---

# 18. MODEL ACQUISITION

Model acquisition must be treated as a controlled mutation.

The acquisition subsystem should support:

- resumable download;
- integrity validation;
- revision pinning;
- authenticated sources;
- private models;
- staging;
- clean rollback;
- disk admission;
- reconciliation after interrupted operations.

Models should not be downloaded before storage safety is established.

Selection is a recommendation. Acquisition is a separate mutation.
`SELECTED` is not `DOWNLOADED` / `STORED`. Kultrun should reuse an
existing local artifact rather than downloading it again.

Acquisition sits behind a replaceable `ModelAcquisitionProvider`. Hugging
Face is the first real adapter; it is not the lifecycle owner. A stored
`ModelArtifact` is identified by candidate, exact resolved revision,
format and quantization — never by `latest` and never by filesystem path.
Several artifacts may be stored while no inference instance is running.
Stored is not loaded, reserved, or serving.

---

# 19. STORAGE CAPACITY MODEL

Storage planning should follow a deterministic chain.

Conceptually:

`credible remaining host capacity`

→ `protected reserve`

→ `safe allocatable capacity`

→ `administrator platform allocation`

→ `platform storage budget`

→ `current platform-managed usage`

→ `remaining platform budget`

→ `operation-specific storage requirement`

→ `admission decision`

The system must distinguish:

- steady-state model size;
- temporary staging;
- conversion outputs;
- quantization outputs;
- cache growth;
- peak additional storage required during an operation.

A model operation should be admitted based on its **peak additional storage requirement**, not only final model size.

---

# 20. HOST CAPACITY BEFORE MODEL SELECTION

The conceptual order should be:

1. detect host;
2. characterize safe host capacity;
3. build capacity envelope;
4. inspect candidate models;
5. calculate model requirements;
6. evaluate feasibility;
7. select;
8. acquire;
9. deploy.

Commit-time storage verification remains useful as a transaction-safety check, but it must not replace proper host capacity characterization.

---

# 21. CAPACITY INTELLIGENCE — PRODUCT REQUIREMENT

The Capacity Planner must reliably answer:

1. Can this model run on this host?
2. What runtime should be used?
3. What runtime configuration should be used?
4. How much storage will it consume?
5. How much memory will it consume?
6. Can it run with existing workloads?
7. How many simultaneous requests can it support?
8. How confident are these answers?

This is a core product capability.

Capacity-based **model selection** is a named step, not a side effect of
inventory or of the Capacity Planner's estimates. It asks not only
"which models technically fit?" but "which models fit **safely** and
make **sensible use** of this machine?"

**Size is not parameter count and is not artifact size.** For deployment
feasibility, size means the estimated **deployed resource requirement**
under a proposed runtime, quantization, context configuration, placement
and device strategy: weights + runtime overhead + KV/cache +
activations + other required deployment memory. Parameter count and
download bytes may be displayed; they do not decide fit.

Hard eligibility filtering is separate from soft ranking. Conceptually:

```text
ALL CANDIDATES
  → source / metadata validity
  → license / policy eligibility
  → architecture / format compatibility
  → runtime compatibility
  → storage feasibility          (separate hard constraint)
  → memory / deployment feasibility against SAFE capacity
  → upper utilization filter     (> maximum → infeasible)
  → lower utilization filter     (< minimum → underutilized, not preferred)
  → PREFERRED FEASIBLE CANDIDATES
  → deterministic ranking
  → SelectionRecommendation
```

Compatibility against the current deployment remains
`COMPATIBLE`, `CONDITIONALLY_COMPATIBLE`, `UNSUPPORTED`, or
`UNRESOLVED`, with explainable reasons. That is not the same question as
whether a compatible candidate makes sensible use of the machine.

`DeploymentCapacity` is the relevant **SAFE** slice of the current
`CapacityEnvelope` for a proposed placement — not a universal server
score. Discrete GPU: primary limiting capacity is safe VRAM for the
selected accelerator; secondary is safe RAM; storage is a separate hard
constraint. CPU-only: primary is safe RAM; storage remains separate.
Unified memory, when it exists, is its own primary capacity and is never
forced into VRAM semantics. Multi-GPU evaluation uses the proposed
placement, not the sum of every visible device.

`CapacityUtilization` is the maximum of
`required / safe` across the applicable **deployment-limiting memory**
resources (for example `max(required_vram/safe_vram, required_ram/safe_ram)`).
Storage is **not** in this ratio. A large disk must not make a
compute-heavy model look like a better hardware fit. Only the SAFE layer
is the fit boundary; reported and effective may be displayed. Safety
headroom is not subtracted twice.

`SelectionPolicy` holds the preferred-band thresholds. They are policy
defaults, not architecture constants. v0 defaults: minimum utilization
0.20, maximum 1.00. A candidate below the minimum may physically run; it
is `FEASIBLE_UNDERUTILIZED` and is excluded from the default preferred
pool (`underutilizes available deployment capacity`). A candidate above
the maximum is infeasible (`estimated deployment requirement exceeds
safe capacity`). The preferred band is inclusive at both configured
bounds. CPU/GPU offload is `CONDITIONALLY_COMPATIBLE` unless current
policy and runtime explicitly support it; it is never a hidden way to
force an oversized model into the preferred band.

If every otherwise-feasible candidate is underutilized, the selector
returns `NO_PREFERRED_CANDIDATE` and may list underutilized alternatives
separately. It does not silently relax the minimum. If every candidate
exceeds safe capacity, it returns `NO_FEASIBLE_CANDIDATE`. It does not
lower reserves, use reported capacity, invent offload, or pick a model
outside the source set.

Once candidates are inside the preferred band, ranking is deterministic
and explainable. Utilization is one ranking signal, not the winner-take-all
criterion: a 97% candidate is not inherently better than a 70% candidate
of similar capability. v0 may consider feasibility class, trusted
capability evidence, runtime fit, utilization, operating headroom,
context, quantization quality, and a deterministic tie-break. It is not
a learned engine.

Feasibility consumes host capabilities, the capacity envelope, model
requirements from **one** active `ModelRequirementEstimator`, runtime
capabilities and `SelectionPolicy`. It does not reserve resources. A
recommendation is recomputed from current inputs; it is not permanent
truth.

Kultrun supports replaceable requirement estimators behind a port.
llmfit is the initial preferred production requirement estimator.
The Kultrun estimator is the built-in first-party fallback. Normal
default operation is AUTO: llmfit first, and Kultrun only when llmfit
cannot produce a contract-valid `ModelRequirement` for the exact request.
Explicit `llmfit` and `kultrun` modes remain strict (no automatic
failover). Planning never contains provider-specific branches and never
shops for a more favourable estimate. Cross-provider comparison is a
development/validation activity, not a product feature: the Platform API,
Prototype Console, `SelectionRecommendation` and `DeploymentPlan` carry
only the effective estimator's evidence. There is no production
reconciler, average, min/max or dual estimate.

The first implementation is deterministic and explainable. Learned or
empirical recommendation intelligence is later and must not be required
by the first selector.

Planning recommends. The Resource Manager authorizes. Planning must
never create a resource reservation.

---

# 22. CAPACITY EVIDENCE ARCHITECTURE

Kultrun should not attempt to write every estimator itself.

Introduce a formal:

`CapacityEvidenceProvider`

This is **host capacity evidence**, not model-requirement estimation.
llmfit is a `ModelRequirementEstimator` at Stage 1.4B. It must not become
the authoritative `CapacityEnvelope`. Possible capacity-evidence providers
later:

- internal conservative estimator;
- Hugging Face Accelerate;
- llm-d-planner;
- runtime-native estimators;
- vLLM benchmark tools;
- Infermark;
- future providers.

External tools provide evidence.

They do not make admission decisions.

---

# 23. NORMALIZED CAPACITY EVIDENCE

All results normalize into platform-owned `CapacityEvidence`.

Possible fields:

- provider;
- provider version;
- evidence type;
- model;
- revision;
- hardware fingerprint;
- runtime;
- runtime version;
- runtime configuration;
- workload profile;
- estimated model weight memory;
- activation memory;
- KV-cache memory;
- runtime overhead;
- total memory;
- maximum context;
- concurrency estimates;
- throughput;
- TTFT;
- ITL;
- TPOT;
- confidence;
- assumptions;
- timestamp;
- evidence source.

Providers may populate only what they know.

---

# 24. THEORETICAL VS OBSERVED CAPACITY

Kultrun must explicitly differentiate:

## Theoretical Evidence

Derived from:

- parameter counts;
- architecture;
- precision;
- quantization;
- hardware specifications;
- formulas;
- model metadata;
- external estimators.

## Observed Evidence

Derived from actual execution:

- measured RAM;
- measured VRAM;
- TTFT;
- ITL;
- TPOT;
- tokens/sec;
- requests/sec;
- queue delay;
- OOMs;
- failures;
- actual concurrency.

Observed evidence for the exact configuration should generally carry more confidence.

---

# 25. CONCURRENCY AS FIRST-CLASS CAPACITY

Concurrency should not be one number.

At minimum distinguish:

`memory_max_concurrency`

The theoretical memory fit.

`performance_max_concurrency`

The practical level before unacceptable degradation.

`slo_max_concurrency`

Maximum concurrency satisfying defined service objectives.

`configured_concurrency`

The conservative runtime configuration actually selected.

`platform_max_concurrent_requests`

The gateway-level limit.

The Resource Manager should admit according to safe configured policy rather than theoretical maximum.

---

# 26. WORKLOAD PROFILE

Capacity recommendations should eventually incorporate a normalized `WorkloadProfile`.

Possible fields:

- average input tokens;
- average output tokens;
- maximum input tokens;
- maximum output tokens;
- requests/sec;
- burstiness;
- streaming;
- target TTFT;
- target ITL;
- target TPOT;
- priority;
- expected concurrency.

The same model/hardware may have different safe recommendations for:

- interactive assistant usage;
- batch document extraction;
- high-throughput classification.

---

# 27. CONFIDENCE

Recommendations should expose confidence.

Examples:

**HIGH**

- exact model manifest;
- hardware validated;
- runtime estimate available;
- prior observed benchmark available.

**MEDIUM**

- strong theoretical evidence;
- no exact empirical benchmark.

**LOW**

- incomplete metadata;
- extrapolation from dissimilar hardware;
- unresolved runtime assumptions.

Confidence should be visible to advanced administrators and simplified for non-technical users.

---

# 28. CAPACITY LEARNING LOOP

Long-term:

**Estimate → Validate → Deploy → Observe → Benchmark → Compare → Calibrate → Learn → Recommend**

Kultrun should eventually persist a `Capacity Evidence Dataset`.

The dataset should be keyed by fingerprints involving:

- model;
- model revision;
- hardware;
- runtime;
- runtime version;
- configuration;
- context;
- workload;
- concurrency.

This allows recommendations to improve empirically.

---

# 29. RESOURCE MANAGER

The Resource Manager is authoritative for resource admission.

It receives recommendations/evidence but makes the final decision based on current system reality.

It should consider:

- safe RAM;
- safe VRAM/unified memory;
- storage;
- CPU;
- active workloads;
- reservations;
- ports;
- runtime constraints;
- requested concurrency;
- policy;
- priority.

The Resource Manager should:

- reserve before mutation;
- fail conservatively;
- release cleanly;
- persist state;
- reconcile after restart;
- avoid resource oversubscription.

---

# 30. RESOURCE RESERVATIONS

Resource reservations should exist independently of observed runtime usage.

A workload may have:

- requested requirement;
- admitted reservation;
- actual current consumption;
- peak observed consumption.

These are distinct.

Reservations provide scheduling safety.

Observed usage provides learning and diagnostics.

---

# 31. NON-INFERENCE WORKLOAD EXTENSIBILITY

The Resource Manager should not assume every workload is inference.

Future workload types include:

- training;
- fine-tuning;
- LoRA generation;
- evaluation;
- benchmarking;
- quantization;
- conversion;
- distillation;
- indexing.

The first build need not schedule all of these, but the job model should allow extension.

---

# 32. CENTRAL AI GATEWAY

The gateway provides a stable AI access layer.

It may route to:

- local inference instances;
- external commercial APIs;
- Team Brains;
- future specialist services.

The gateway should own platform concerns such as:

- authentication;
- authorization;
- routing;
- request limits;
- queueing;
- usage instrumentation;
- policy;
- model access;
- application identity.

Gateway implementation must remain replaceable.

---

# 33. ROUTING EVOLUTION

Initial routing may simply use:

- administrator-selected model;
- application-selected model;
- basic policy.

Later routing can consider:

- team;
- role;
- task;
- model quality;
- privacy;
- latency;
- cost;
- capacity;
- availability;
- model effectiveness;
- policy.

Kultrun should preserve manual selection and administrative overrides.

---

# 34. END-USER EXPERIENCE

The architecture must not depend on a third-party chat frontend.

A third-party frontend may be supported initially if commercially and technically appropriate, but it should remain a replaceable client of stable platform APIs.

The long-term preferred direction is a lightweight first-party end-user interface.

Initial features only need to support:

- authentication;
- conversation;
- model/brain selection where allowed;
- streaming;
- basic history;
- knowledge interaction;
- clear source/permission behavior.

The differentiation belongs in the Company Brain, not the chat UI.

---

# 35. KNOWLEDGE LAYER

The Company Brain must include a first-class organisational Knowledge Layer.

Kultrun supports:

## Platform-Managed Storage

For customers that want files stored directly under platform management.

## External Knowledge

For customers who retain existing systems of record.

The Company Brain must not require customers to migrate all information.

---

# 36. MANAGED FILE STORAGE

A managed storage implementation may use software such as OpenCloud, Nextcloud, or another provider behind a replaceable:

`ManagedStorageProvider`

The platform-owned API should expose concepts such as:

- files;
- folders/spaces;
- users;
- groups;
- quotas;
- sharing;
- permissions;
- versions.

The external product is an implementation detail.

---

# 37. KNOWLEDGE CONNECTOR ARCHITECTURE

Use a modular:

`KnowledgeConnector`

Initial connector priorities:

- SharePoint;
- OneDrive;
- Google Drive;
- SMB/network shares;
- filesystem;
- WebDAV;
- managed platform storage.

Future connectors:

- Box;
- Dropbox;
- Confluence;
- Notion;
- S3;
- Azure storage;
- Google Cloud;
- databases;
- email;
- Slack;
- Teams;
- internal enterprise systems.

Connectors advertise capabilities rather than pretending every provider is identical.

---

# 38. INTEGRATION HELPERS

Tools such as Nango may simplify:

- OAuth;
- token refresh;
- connection management;
- SaaS API integration.

Tools such as rclone may simplify:

- file transport;
- mirroring;
- sync;
- migration;
- generic storage access.

Both must remain optional implementation adapters.

---

# 39. NORMALIZED KNOWLEDGE MODEL

All knowledge sources should normalize to a platform-owned representation.

A `KnowledgeItem` may contain:

- internal ID;
- source;
- external ID;
- path;
- type/MIME;
- owner;
- version;
- checksum;
- metadata;
- modification timestamps;
- permission references;
- indexing state;
- content location/reference;
- provenance.

Kultrun should not assume that content itself must be copied locally.

---

# 40. IDENTITY AND PERMISSIONS

Identity and authorization are central to the Company Brain.

Kultrun should represent:

- users;
- groups;
- teams;
- roles;
- applications/service identities;
- administrative roles;
- access policies.

Permissions may come from:

- platform-managed identity;
- enterprise identity providers;
- original knowledge sources.

Identity should later integrate with enterprise SSO providers without defining the initial architecture around one provider.

---

# 41. PERMISSION-AWARE RETRIEVAL

This is non-negotiable.

The retrieval path should conceptually be:

`authenticated user`

→ `candidate knowledge`

→ `permission enforcement`

→ `authorized context`

→ `model`

The AI must never retrieve or expose information the requesting user is unauthorized to access.

For sensitive sources, source-system authorization may be revalidated at retrieval time.

---

# 42. INDEXING AND RAG

The first knowledge intelligence capability should support permission-aware:

- indexing;
- search;
- retrieval;
- RAG.

Future capabilities can include:

- semantic search;
- metadata enrichment;
- classification;
- summarization;
- duplicate detection;
- entity extraction;
- knowledge graphs;
- organisational memory.

These should be modular layers, not monolithic knowledge code.

---

# 43. ADMIN AI AGENT — CORE MVP FEATURE

The Admin AI Agent must exist from the beginning.

It is not a future enhancement.

It should act as:

- onboarding guide;
- configuration assistant;
- diagnostics assistant;
- operational copilot;
- capacity explainer;
- model advisor;
- connector setup assistant;
- storage assistant;
- permission assistant;
- analytics assistant;
- licensing assistant;
- troubleshooting assistant.

---

# 44. ADMIN AGENT OPERATING MODEL

The Admin Agent should use structured platform APIs and diagnostics.

It should not need unrestricted shell access.

Its actions should be classified by risk.

Examples:

## Read-only

- inspect capacity;
- explain logs;
- show models;
- show usage.

## Low-risk mutations

- update labels;
- modify approved preferences.

## Meaningful mutations

- install model;
- start/stop model;
- connect repository;
- modify permissions;
- upgrade platform.

Meaningful actions require administrator approval.

---

# 45. CONVERSATIONAL ONBOARDING

The Admin Agent should ask business questions.

Examples:

- What do your employees primarily need AI for?
- Where are your documents stored?
- How many people will use this?
- Should information remain entirely inside your infrastructure?
- Is response speed or maximum model quality more important?
- Which departments should initially have access?

It should translate those into technical decisions.

---

# 46. ANALYTICS — CUSTOMER-SIDE AI USAGE

Each AI request should create a normalized `UsageEvent`.

At minimum it should support:

- timestamp;
- model;
- provider;
- inference instance;
- user;
- team;
- application;
- input tokens;
- output tokens;
- total tokens;
- latency;
- errors;
- cost;
- routing information.

Where available:

- TTFT;
- throughput;
- queue time;
- resource usage.

---

# 47. LOCAL ANALYTICS RETENTION

Basic deployments should maintain a bounded local analytics history.

A reasonable initial product policy is approximately seven days for the basic/free tier.

Storage should use replaceable adapters.

The gateway emits events without knowing how they are persisted.

---

# 48. THREE DATA DOMAINS

Kultrun must clearly separate:

## Customer AI Analytics

Belongs primarily to the customer.

## Vendor Product Telemetry

Used to understand how the product is used.

## Licensing / Entitlement Data

Used for commercial authorization.

These domains may share transport infrastructure but remain logically separate.

---

# 49. CUSTOMER CONTENT PRIVACY

The following should remain local by default:

- prompts;
- model responses;
- files;
- documents;
- retrieved RAG content;
- proprietary information;
- confidential payloads.

Vendor telemetry should operate primarily on metadata and aggregates.

---

# 50. PRODUCT-USAGE TELEMETRY

The vendor may collect approved non-content events such as:

- installation;
- active deployment;
- version;
- hardware category;
- executor used;
- runtime used;
- model download;
- feature usage;
- connector setup;
- capacity warning;
- recommendation accepted;
- override used;
- error class.

A provider such as PostHog may initially be used behind:

`ProductTelemetryExporter`

It is not fundamental to the product.

---

# 51. HEARTBEAT / TELEMETRY AGENT

Connected deployments should include a lightweight outbound agent.

Responsibilities may include:

- deployment heartbeat;
- product usage batching;
- entitlement renewal;
- update checks;
- optional crash/error reporting;
- optional cloud analytics export.

It represents a clear outbound boundary.

---

# 52. TELEMETRY TRANSPARENCY

Admin UI should display:

- whether licensing connectivity is enabled;
- whether product telemetry is enabled;
- whether cloud analytics export is enabled;
- whether update checks are enabled;
- last heartbeat;
- categories of data transmitted.

The system should explicitly state that prompts, responses, documents, and RAG content are not transmitted by default.

---

# 53. AIR-GAPPED MODE

Air-gapped customers must be able to disable outbound communication entirely.

They should still be able to operate:

- local inference;
- local knowledge;
- local analytics;
- local administration;
- offline licensing.

Offline install bundles should be supported later through the same component manifests.

---

# 54. LICENSING AND ENTITLEMENTS

Licensing should be designed from the beginning but not coupled to one pricing model.

Use generic entitlements.

Possible feature entitlements:

- long-term analytics;
- advanced routing;
- private registries;
- SSO;
- audit features;
- multi-host orchestration;
- advanced capacity optimization;
- enterprise governance.

Possible capacity entitlements:

- hosts;
- users;
- GPUs;
- inference instances;
- concurrent models;
- storage;
- sites.

---

# 55. COMMERCIAL MODEL FLEXIBILITY

The architecture should permit future commercial models such as:

- per host;
- per GPU;
- per user;
- per concurrent model;
- feature tiers;
- capacity tiers;
- usage pricing;
- support/SLA;
- annual enterprise contracts;
- hybrid models.

Marketing tiers should not be hard-coded into product logic.

---

# 56. LICENSE BEHAVIOUR

Connected deployments may receive signed renewable entitlement leases.

Temporary vendor connectivity loss should not break production.

Use:

- local verification;
- grace periods;
- transparent warnings.

Expired entitlements should degrade gracefully.

Possible restrictions:

- no new model installs;
- no additional hosts;
- premium features disabled;
- upgrades restricted.

Do not:

- destroy data;
- abruptly kill production inference;
- lock administrators out of their own information.

---

# 57. THIRD-PARTY LICENSING POLICY

Before commercial release, every bundled third-party dependency should have:

- identity;
- version;
- provenance;
- license;
- redistribution rights;
- commercial restrictions.

Classify dependencies:

## Green

Permissive commercial use.

## Amber

Copyleft, source-available, branding, redistribution, hosted-service or commercial complications.

## Red

Commercially unacceptable or incompatible.

Amber/Red components should remain replaceable unless explicitly accepted.

Generate an SBOM and audit the actual packaged artifact.

---

# 58. MODEL LICENSE AWARENESS

The Model Catalog should surface:

- model license;
- restrictions;
- commercial-use concerns;
- gated access;
- provenance.

Kultrun should not imply that every discoverable model is legally appropriate for every company.

---

# 59. MODEL EFFECTIVENESS INTELLIGENCE

Long-term, Kultrun should empirically learn:

> Which models work best for which organisations, roles, tasks, hardware, and configurations?

This requires structured contextual data.

---

# 60. ORGANISATION CONTEXT

Possible organization-level labels:

- industry;
- employee-size band;
- number of AI users;
- sites;
- broad workload volume;
- deployment environment;
- hardware class.

Avoid unnecessary identifying information.

---

# 61. ROLE AND TEAM CONTEXT

Normalize roles rather than relying entirely on free-text job titles.

Possible fields:

- department;
- role family;
- seniority band;
- team;
- workload category.

Named identities stay local unless required for customer analytics.

---

# 62. WORKLOAD LABELS

Examples:

- summarization;
- document Q&A;
- coding;
- drafting;
- extraction;
- analysis;
- classification;
- research;
- customer support;
- translation;
- brainstorming;
- spreadsheet reasoning.

These labels become important for empirical model recommendations.

---

# 63. PER-MODEL USAGE METRICS

For every model/configuration, capture where permitted:

- input tokens;
- output tokens;
- total tokens;
- request count;
- tokens/request;
- latency;
- TTFT;
- tokens/sec;
- errors;
- retries;
- regenerations;
- fallback frequency;
- model switching;
- cost;
- resource consumption;
- concurrency;
- workload label;
- role/team cohort;
- organisation cohort;
- runtime/configuration.

---

# 64. SATISFACTION AND OUTCOME SIGNALS

Use both explicit and behavioural signals.

## Explicit

- thumbs up/down;
- helpful/not helpful;
- rating;
- optional review;
- model comparison;
- administrator evaluation.

## Behavioural Proxies

- regeneration;
- retry;
- model switching;
- abandonment;
- copy/export;
- repeated use;
- task completion signals where available.

Behaviour should be treated as evidence, not certainty.

---

# 65. NORMALIZED MODEL OUTCOME

Create a conceptual:

`ModelOutcome`

or:

`ModelExperience`

joining:

- model;
- configuration;
- task;
- role/team;
- organisation cohort;
- hardware;
- usage metrics;
- explicit feedback;
- behavioural signals;
- task success indicators.

---

# 66. PRIVACY-PRESERVING EFFECTIVENESS DATA

Vendor learning should prefer cohort-level records such as:

> Mid-sized professional-services organisations, Finance roles, Document-Q&A workload, Model X, median latency Y, acceptance Z.

rather than:

> Named employee submitted these prompts.

Raw content remains local by default.

Written reviews should not be exported unless appropriately permitted.

---

# 67. MODEL EFFECTIVENESS DATASET

Long-term combine:

1. normalized model metadata;
2. capacity evidence;
3. organization context;
4. role/team context;
5. workload labels;
6. usage metrics;
7. satisfaction/outcomes.

This becomes a core learning asset.

---

# 68. MODEL INVENTORY OPTIMIZER — FUTURE

Above simple feasibility, build a future Model Inventory Optimizer.

Near-term Capacity Planner / feasibility:

> Can this model fit, and is it a sensible model to deploy on this host?

Future Model Inventory Optimizer:

> What portfolio of models should this organisation keep stored and/or
> running given workloads, hardware, outcomes, cost and policy?

Do not pull the optimizer into the first vertical. The first selector
must not depend on it.

---

# 69. OPTIMIZER INPUTS

The optimizer can consider:

- storage;
- RAM;
- VRAM;
- unified memory;
- runtime compatibility;
- model quality;
- task coverage;
- latency;
- throughput;
- license;
- cost;
- reliability;
- usage;
- role effectiveness;
- redundancy;
- hardware.

---

# 70. OPTIMIZER OUTPUTS

Offer explainable portfolios:

- Highest Quality;
- Balanced;
- Broadest Coverage;
- Lowest Resource Use;
- Lowest Cost;
- Best Concurrent Mix.

It should not return one opaque “correct” answer.

---

# 71. MODEL OPTIMIZER METHODS

Possible later approaches:

- weighted scoring;
- constrained optimization;
- knapsack-style optimization;
- Pareto fronts;
- multi-objective optimization;
- eventually learned recommendations.

Do not prematurely build this.

Collect the data needed first.

---

# 72. TEAM BRAIN — LONG-TERM PRODUCT CONCEPT

The Company Brain should eventually support specialised collective brains for teams.

A Team Brain is **not simply one fine-tuned model**.

It is a logical object combining:

- team identity;
- membership;
- access permissions;
- team knowledge;
- team agent;
- tools;
- workflows;
- base model or portfolio;
- optional model adapter;
- optional derived model;
- team memory;
- evaluation profile;
- routing policy.

---

# 73. TEAM BRAIN — FIRST STAGE

Before training custom models, Team Brains should work through:

`Base model`

+

`permission-scoped team knowledge`

+

`team agent configuration`

+

`team tools`

This already creates significant specialization.

---

# 74. MODEL ADAPTATION

Later allow:

- LoRA;
- PEFT;
- supervised fine-tuning;
- preference optimization;
- model merging;
- full fine-tuning where justified;
- distillation.

These belong behind a replaceable:

`ModelAdaptationProvider`

Training infrastructure must remain separate from inference infrastructure.

---

# 75. DERIVED MODEL LINEAGE

Derived artifacts should record:

- parent model;
- parent revision;
- derivation type;
- training configuration;
- dataset snapshot;
- provenance;
- owner/team;
- permissions;
- version;
- evaluation;
- approval state;
- runtime compatibility;
- resource requirements.

A LoRA adapter should be representable without pretending it is a complete independent base model.

---

# 76. TRAINING DATA GOVERNANCE

A critical principle:

**Permission to retrieve knowledge does not imply permission to train on it.**

Training data requires:

- explicit authorization;
- provenance;
- team scope;
- snapshot/version;
- retention;
- policy.

Highly sensitive or revocable factual information should generally remain in RAG rather than model weights.

---

# 77. MODEL EVALUATION AND PROMOTION

Custom models/adapters should move through lifecycle states such as:

- draft;
- evaluating;
- approved;
- production;
- deprecated.

Evaluation should compare derived models with base models on:

- team tasks;
- quality;
- satisfaction;
- latency;
- tokens;
- resource usage;
- safety;
- cost.

Rollback must remain possible.

---

# 78. RESOURCE MANAGEMENT FOR TRAINING

Future Resource Manager job types should include:

- inference;
- training;
- evaluation;
- benchmarking;
- quantization;
- distillation.

Training should not jeopardize primary inference.

Future scheduling can consider:

- priorities;
- quotas;
- isolation;
- pause/cancel;
- checkpoints;
- available capacity.

---

# 79. TEAM-SPECIFIC SERVING

The gateway should eventually select Team Brain models/adapters according to:

- authenticated user;
- team;
- policy;
- task.

Where runtimes support efficient multi-adapter serving, runtime adapters can exploit it.

Core architecture must not depend on any one runtime's LoRA API.

---

# 80. FUTURE ORGANISATIONAL COORDINATION

The exact design remains intentionally open.

However, the architecture should leave room for Company Brain agents that:

- understand teams;
- find relevant knowledge;
- connect people and expertise;
- identify duplicated effort;
- assist collaboration;
- coordinate knowledge flows;
- potentially coordinate work across teams.

This should be built only after:

- identity;
- permissions;
- knowledge;
- agents;
- analytics;
- Team Brains;

are sufficiently mature.

---

# 81. ADMIN UI

The admin experience should provide clear views for:

- Hosts;
- Models;
- Model Catalog;
- Inference Instances;
- Capacity;
- Knowledge Sources;
- Storage;
- Users/Teams;
- Permissions;
- Analytics;
- Logs;
- Telemetry;
- Licensing;
- Platform Health;
- Updates.

The Admin AI Agent should remain accessible throughout.

---

# 82. AUTOMATIC VS MANUAL SETTINGS

Configuration should support:

**Automatic**

Use recommended safe settings.

**Manual Override**

Advanced administrator changes setting.

Overrides should be:

- validated;
- explained;
- recorded;
- reversible where possible.

---

# 83. HEALTH AND OBSERVABILITY

The system should expose:

- service health;
- model health;
- runtime health;
- GPU/CPU/RAM/storage;
- resource reservations;
- error state;
- logs;
- gateway health;
- connector health;
- telemetry state;
- licensing state.

Keep three lifecycle dimensions distinct:

- **desired** — what Kultrun wants (for example RUNNING);
- **observed** — what actually exists (RUNNING, EXITED, absent);
- **health** — whether it is functioning correctly (HEALTHY, UNHEALTHY).

A reachable port is status, not health. An instance may be desired
RUNNING, observed EXITED, and UNHEALTHY.

Capacity, reservation and utilization remain three different facts:
what can safely exist, what Kultrun has authorized, and what processes
are consuming now.

The Admin Agent should use this same structured information.

---

# 84. STARTUP / RESUME

Platform startup should be incremental and idempotent.

It should:

- inspect current host;
- load persisted platform state;
- reconcile installed models;
- verify runtimes;
- reconstruct missing compatible runtime components when necessary;
- verify ports;
- reconcile reservations;
- start required services;
- run lightweight health checks.

It should not redownload everything.

---

# 85. SHUTDOWN / CHECKPOINTING

Graceful shutdown should preserve:

- model inventory;
- workload state;
- reservations;
- configuration;
- analytics;
- logs;
- operational checkpoint information.

Kultrun should resume coherently after interruption.

---

# 86. UPDATES

Updates should be modular.

Kultrun should be able to update:

- core platform;
- admin UI;
- runtime adapters;
- executors;
- model-source adapters;
- connectors;
- telemetry components;

without requiring replacement of unrelated components.

Update packages should be:

- versioned;
- signed;
- verified;
- rollback-aware.

---

# 87. COMPONENT REGISTRY

The bootstrapper should resolve dependencies from a versioned component registry/manifest.

A component should define:

- version;
- supported OS;
- architecture;
- accelerator compatibility;
- dependencies;
- source;
- checksum;
- signature;
- license;
- artifact location.

Avoid hard-coded download logic scattered throughout the codebase.

---

# 88. MULTI-ARCHITECTURE SUPPORT

Where practical, container images/packages should support:

- AMD64/x86_64;
- ARM64.

Hardware-specific runtime artifacts remain conditional.

---

# 89. DEPLOYMENT PROFILES

Kultrun should eventually classify deployment support.

Example:

## Certified

Extensively validated.

## Supported

Expected and supported.

## Compatible

Evidence indicates likely compatibility.

## Experimental

May work but not fully validated.

## Unsupported

Known incompatibility.

This enables broad hardware support without pretending every environment has identical guarantees.

**A profile is earned from evidence, not declared.** The tier a hardware
shape holds should follow from the acceptance level actually reached on it:
integrated acceptance certifies, proven live inference supports, real
detection and capacity make it compatible, a captured observation alone
makes it experimental, and a known incompatibility makes it unsupported.

A profile applies to a defined hardware, software and environment shape.
One validated NVIDIA system does not certify every NVIDIA system. Support
accumulates as evidence accumulates, which is what makes broad portability
a claim the product can substantiate rather than a marketing statement.

An organisation may additionally record its **own** support statement — that
a configuration is vendor-supported, or backed by its infrastructure team.
That is useful and should be displayable, and it is a **different fact**
from Kultrun's evidence profile. An external declaration must never promote
Kultrun's classification: the profile means "this is the acceptance level
actually reached", and a statement that could change it would turn the
ladder into opinion.

---

# 90. INITIAL REFERENCE DEPLOYMENTS

The strongest initial reference environment should be:

**Linux x86_64 + NVIDIA GPU**

But the architecture should immediately preserve paths for:

- Linux CPU-only;
- Linux VMs;
- ARM64;
- Windows + Linux VM;
- Apple Silicon native inference;
- AMD;
- Intel;
- prosumer systems.

---

# 91. MAC STUDIO / APPLE SILICON

Treat Apple systems as a distinct valid host type.

Possible pattern:

- control-plane services may use containers;
- inference may use native MLX/Metal or llama.cpp;
- unified memory must be handled explicitly;
- Docker must not be assumed to expose native Apple GPU functionality.

---

# 92. WINDOWS ENTERPRISE ENVIRONMENTS

Do not require the entire AI stack to be native Windows.

A supported path may use:

- Hyper-V;
- VMware;
- Linux VM.

Kultrun should focus on capabilities, not ideological OS purity.

---

# 93. PROSUMER / MINI-PC HARDWARE

GMKtec, GEEKOM and similar systems are valid potential hosts where capabilities are sufficient.

Kultrun should evaluate:

- compute;
- RAM;
- storage;
- accelerator;
- reliability requirements;

rather than reject hardware because it is not traditional rack equipment.

---

# 94. MULTI-HOST FUTURE

The initial build may operate one host at a time.

The architecture should later allow a central control plane to understand:

- multiple hosts;
- model placement;
- fleet capacity;
- service routing;
- workload movement;
- host health;
- distributed storage considerations.

Do not prematurely build orchestration complexity.

---

# 95. MODEL PLACEMENT FUTURE

Later:

> Which host should run Model X?

can become an extension of:

> Can this host run Model X?

Multi-host placement should build on the same normalized:

- HostCapabilities;
- ModelRequirements;
- CapacityEvidence;
- WorkloadProfile;
- ResourceManager semantics.

---

# 96. DATA STORAGE ABSTRACTION

Persistent stores should use replaceable adapters.

Possible storage domains:

- configuration;
- model inventory;
- workload state;
- reservations;
- local analytics;
- capacity evidence;
- knowledge metadata;
- licensing state.

Do not allow business logic to depend directly on one database.

---

# 97. NORMALIZED DOMAIN OBJECTS

The clean-slate architecture should define platform-owned domain contracts early.

Important concepts include:

- HostCapabilities;
- CapacityEnvelope;
- DeploymentCapacity;
- CapacityUtilization;
- ModelMetadata;
- ModelArtifact;
- ModelRequirement;
- ModelEstimationRequest;
- ModelRequirementEstimator;
- ModelSource;
- ModelInventoryRecord;
- CompatibilityEvidence;
- FeasibilityResult;
- SelectionPolicy;
- SelectionRecommendation;
- InferenceInstance;
- Workload;
- WorkloadProfile;
- ResourceReservation;
- CapacityEvidence;
- DeploymentPlan;
- UsageEvent;
- ModelOutcome;
- KnowledgeSource;
- KnowledgeItem;
- AccessPolicy;
- User;
- Group;
- Team;
- TeamBrain;
- DatasetSnapshot;
- DerivedModel;
- Entitlement.

Names may evolve.

The conceptual boundaries should not.

---

# 98. API-FIRST INTERNAL DESIGN

Major platform capabilities should expose structured interfaces usable by:

- Admin UI;
- Admin Agent;
- CLI;
- tests;
- automation;
- future external integrations.

The UI should not contain infrastructure logic.

The AI Agent should not be given special backdoor access.

---

# 99. FAILURE SEMANTICS

Every mutating workflow should clearly define:

- preflight;
- admission;
- mutation boundary;
- rollback;
- persistence;
- reconciliation;
- error mapping.

Examples:

- download model;
- update model;
- delete model;
- start inference instance;
- stop inference instance;
- install connector;
- update platform.

---

# 100. CONSERVATIVE MUTATION PRINCIPLE

Before expensive or irreversible mutation:

- establish credible requirements;
- verify capacity;
- validate compatibility;
- acquire required lock/reservation;
- perform mutation;
- reconcile result.

Avoid optimistic mutation followed by cleanup.

---

# 101. LOCKING AND SERIALIZATION

Operations that compete for finite platform resources should use explicit concurrency control.

Examples:

- model acquisition;
- model update;
- model deletion;
- platform storage mutations;
- workload admission.

Do not rely on accidental serialization.

---

# 102. RECONCILIATION

Persisted state and real runtime state may diverge.

The system needs reconciliation for:

- inference processes;
- reservations;
- installed models;
- download staging;
- ports;
- runtime availability.

Restart should repair or fail conservatively.

---

# 103. SECURITY MODEL

The product must assume it may contain:

- sensitive models;
- confidential business files;
- private prompts;
- proprietary knowledge;
- enterprise credentials.

Security should therefore cover:

- authentication;
- authorization;
- secrets;
- encryption;
- network exposure;
- auditability;
- connector credentials;
- model provenance;
- artifact integrity;
- update signing.

---

# 104. SECRETS

Credentials for:

- model hubs;
- connectors;
- external AI APIs;
- telemetry;
- licensing;

should never be embedded in ordinary configuration files or logs.

Use an abstraction that can later integrate with enterprise secret managers.

---

# 105. AUDITABILITY

Future enterprise deployments should be able to answer:

- who changed a setting;
- who installed a model;
- who modified a permission;
- who connected a knowledge source;
- who started/stopped a service;
- what the Admin Agent changed;
- what approval was given.

The schema should leave room for audit events even if full audit UI comes later.

---

# 106. COST INTELLIGENCE

Kultrun should eventually compare:

- external API cost;
- local infrastructure cost;
- local resource use;
- model efficiency.

This feeds:

- analytics;
- routing;
- Model Optimizer;
- procurement;
- business decisions.

---

# 107. MODEL QUALITY INTELLIGENCE

Model quality should not rely solely on public benchmarks.

The system should eventually combine:

- public benchmark metadata;
- organization-specific evaluations;
- explicit user ratings;
- behavioural outcomes;
- operational cost;
- latency;
- reliability.

This creates context-specific model effectiveness.

---

# 108. COMPANY COHORT LEARNING

For customers who permit it, aggregated vendor-side learning can identify patterns such as:

> Model family X is highly effective for Finance document analysis in professional-services companies of 100–500 employees.

This can improve cold-start recommendations for new deployments.

Cohort learning must use privacy-preserving, non-content data wherever possible.

---

# 109. COLD-START RECOMMENDATIONS

During onboarding, the Admin Agent can combine:

- industry;
- company size;
- primary departments;
- intended workloads;
- privacy needs;
- hardware;

with accumulated effectiveness evidence.

It can then recommend:

- model portfolio;
- runtime;
- context;
- concurrency;
- knowledge setup.

---

# 110. EXPLAINABLE RECOMMENDATIONS

Recommendations should describe why.

Example:

> I recommend Model A because it fits your 24 GB GPU, has strong evidence for document-Q&A workloads, similar organisations report high acceptance rates, and it leaves enough headroom to run the embedding service concurrently.

This should be the direction of the product.

---

# 111. FIRST WORKING EXOSKELETON — REQUIRED END-TO-END FLOW

The first major milestone should prove the complete product spine.

A new installation should be able to:

1. inspect the host;
2. create normalized HostCapabilities;
3. establish safe capacity;
4. launch the control plane;
5. show Admin UI;
6. operate the Admin Agent at a basic level;
7. search a small curated model set;
8. evaluate model compatibility;
9. recommend one model;
10. safely acquire/import it;
11. register it in inventory;
12. create a resource reservation;
13. start an inference instance;
14. expose it through the gateway;
15. accept an end-user request;
16. record a UsageEvent;
17. show the event in admin analytics;
18. stop/restart the workload safely;
19. persist/reconcile state after platform restart.

This vertical slice is more important than advanced optimization.

The near-term roadmap names each of these steps. It does not compress
catalog, metadata, feasibility, selection, acquisition, inventory,
admission and inference instance into a single “models” or “admission”
label. Depth stays later; the seams are visible in Milestone 1.

---

# 112. KNOWLEDGE EXOSKELETON

Shortly after or alongside the initial inference vertical:

1. configure one managed/local knowledge source;
2. ingest a small set of documents;
3. record permissions;
4. index;
5. retrieve only authorized content;
6. answer via RAG;
7. expose knowledge source health to Admin UI;
8. allow Admin Agent to explain/configure the source.

Then expand connectors.

---

# 113. INITIAL MODEL CATALOG SCOPE

Do not implement a massive marketplace.

Start with:

- a curated candidate set (approximately 4–8 representative variants);
- a Hugging Face adapter behind a Kultrun-owned `ModelSource` port;
- local file import as a later adapter;
- explicit revision;
- source-independent `ModelMetadata` and `ModelRequirement`;
- evidence, confidence and unresolved fields on every load-bearing estimate.

Stage 1.4A displays the catalog. It does not recommend. Stage 1.4B
evaluates and recommends. Do not search the whole Hub in v0.

This is enough to validate the architecture.

---

# 114. INITIAL CAPACITY SCOPE

Initial Capacity Planner should provide:

- Compatible / Conditionally compatible / Unsupported / Unresolved;
- estimated storage;
- estimated RAM/VRAM;
- runtime recommendation;
- safe configured concurrency;
- confidence;
- evidence explanation.

Use:

- internal conservative logic;
- a small number of optional evidence providers;
- live hardware state.

Do not build exhaustive benchmark fusion yet.

---

# 115. INITIAL ANALYTICS SCOPE

Capture:

- model;
- user/team/app;
- tokens;
- latency;
- error;
- timestamp;
- cost where applicable.

Build the central UsageEvent spine before sophisticated dashboards.

---

# 116. INITIAL TELEMETRY SCOPE

Start with clear event categories:

- installation heartbeat;
- version;
- permitted product feature usage;
- entitlement renewal.

Do not create opaque data collection.

---

# 117. INITIAL LICENSING SCOPE

Build generic feature/capacity entitlements.

Do not prematurely define complex pricing.

Ensure the product can later support multiple commercial strategies.

---

# 118. INITIAL ADMIN AGENT SCOPE

The first Admin Agent should be narrow but real.

It should:

- explain detected host;
- explain model recommendation;
- show capacity;
- help install/start/stop model;
- explain health/errors;
- help connect a basic knowledge source.

The goal is to establish the interaction model.

---

# 119. WHAT SHOULD NOT DELAY THE EXOSKELETON

Do not allow the following to block the first complete product:

- exhaustive hardware benchmarking;
- automatic multi-host orchestration;
- sophisticated model optimizer;
- fine-tuning;
- distillation;
- Team Brain training;
- advanced SLO optimization;
- knowledge graph;
- dozens of connectors;
- dozens of model sources;
- autonomous organisational coordination;
- custom billing engine;
- perfect UI;
- exhaustive audit system;
- Kubernetes.

Build interfaces where needed.

Defer depth.

---

# 120. WHAT MUST BE DESIGNED EARLY EVEN IF IMPLEMENTED LATER

Some concepts are expensive to retrofit and therefore need early contracts.

These include:

- identity and teams;
- permission-aware knowledge;
- model lineage;
- resource reservations;
- workload type;
- request versus inference-instance concurrency;
- normalized UsageEvent;
- CapacityEvidence;
- WorkloadProfile hooks;
- derived model artifacts;
- dataset provenance;
- entitlement boundaries;
- data-domain separation;
- model-source abstraction;
- executor/runtime separation.

---

# 121. FIRST-CLASS MODULAR EXTENSION POINTS

At minimum, preserve replaceable boundaries for:

- HostDiscoveryProvider;
- Executor;
- ContainerEngine;
- InferenceRuntime;
- ModelSource;
- ModelMetadataEnricher;
- CapacityEvidenceProvider;
- CapacityEstimator;
- BenchmarkProvider;
- ResourceStateProvider;
- StorageBackend;
- ManagedStorageProvider;
- KnowledgeConnector;
- Retriever;
- EmbeddingProvider;
- Gateway;
- ProductTelemetryExporter;
- UsageAnalyticsStore;
- EntitlementProvider;
- ModelAdaptationProvider;
- IdentityProvider.

Exact interface names may change.

The modular responsibilities should not.

---

# 122. PRODUCT DIFFERENTIATION

The strongest long-term differentiation is not:

> We can run an open-source model.

Many products can.

Nor is it that Kultrun can enumerate a PCI bus. Commodity hardware
discovery is not differentiation, and reimplementing it would spend the
project's scarcest resource on something a customer will never notice.

The differentiation is the integrated intelligence created by combining:

## Host Intelligence

What can this hardware safely do?

## Model Intelligence

Which models are suitable?

## Capacity Intelligence

How should they be configured?

## Organisational Knowledge

What does the company know?

## Permission Intelligence

Who can access what?

## Usage Intelligence

How is AI being used?

## Effectiveness Intelligence

Which AI works best for which tasks and roles?

## Portfolio Intelligence

Which models should the organisation keep?

## Team Intelligence

How should AI adapt to individual teams?

## Agent Intelligence

How can Kultrun help operate and eventually coordinate the organisation?

---

# 123. LONG-TERM PRODUCT STATE

A mature deployment should eventually be able to tell an administrator:

> Your company has 380 employees across Finance, Operations, Sales and Engineering.

> You currently have four AI hosts with 192 GB of total accelerator memory.

> Twelve models are stored and five inference instances are running.

> Finance primarily uses document analysis and spreadsheet reasoning. Model A currently produces the highest first-response acceptance rate for that workload.

> Engineering performs significantly better with Model B.

> Operations has overlapping models C and D. Removing D would free 48 GB without materially reducing workload coverage.

> Your SharePoint and Google Drive knowledge are indexed and permission synchronized.

> Finance Brain uses the Finance knowledge scope, Model A and a Finance-specific adapter.

> The Sales team has elevated API usage this month.

> I recommend moving one workload to local Model E to reduce external API cost by approximately X while maintaining observed quality.

> Would you like me to prepare the change for approval?

That is the eventual product experience.

---

# 124. FINAL PRODUCT DEFINITION

The product is a **secure, modular, self-hosted Company Brain platform** that:

- installs onto suitable existing infrastructure with minimal technical knowledge;
- understands the hardware it runs on;
- determines what AI workloads can safely operate;
- discovers and manages AI models;
- stores and runs multiple models;
- manages concurrent inference;
- connects to company files and knowledge systems;
- preserves permissions;
- provides governed organisational AI access;
- tracks AI usage and effectiveness;
- helps administrators operate Kultrun conversationally;
- learns which models work best for different businesses, roles and workloads;
- can eventually optimize the organisation's model portfolio;
- can create specialised collective Team Brains;
- can evolve toward helping coordinate intelligence and work across the organisation.

Its architecture must remain portable across:

- hardware;
- operating systems;
- executors;
- inference runtimes;
- model sources;
- storage systems;
- knowledge platforms;
- analytics providers;
- telemetry providers;
- licensing providers.

The guiding product idea is:

> **Install a private intelligence layer onto the compute and knowledge an organisation already owns, then progressively make that organisation's collective intelligence easier to access, safer to govern, more effective to use, and increasingly capable over time.**

---

# 125. GOVERNING BUILD PHILOSOPHY

The rebuild should follow four rules.

## Rule 1 — Design the complete skeleton before deep implementation

Know how:

host detection  
→ capacity  
→ models  
→ runtime  
→ gateway  
→ identity  
→ knowledge  
→ analytics  
→ Admin Agent  
→ telemetry  
→ licensing

connect end-to-end.

## Rule 2 — Build the smallest complete working version

A provisional implementation behind the right boundary is preferable to a sophisticated isolated subsystem.

## Rule 3 — Preserve data needed for future intelligence

Collect structured:

- model metadata;
- usage metrics;
- capacity evidence;
- workload labels;
- role/team labels;
- satisfaction/outcomes;
- lineage;
- provenance;

early enough that future optimizers do not require redesign.

## Rule 4 — Let evidence improve Kultrun

The long-term intelligence loop is:

**Detect → Estimate → Validate → Deploy → Observe → Learn → Recommend → Safely Act.**

For capacity specifically:

**Estimate → Validate → Observe → Learn → Recommend → Safely Admit.**

For the Company Brain as a whole:

**Connect → Understand → Govern → Assist → Measure → Learn → Enhance → Coordinate.**

---

# 126. NORTH STAR

The ultimate measure of success is not how many infrastructure features Kultrun contains.

Success is:

> **A company can install Kultrun onto infrastructure it already controls, connect the knowledge it already possesses, give its people secure access to appropriate AI capabilities, and progressively become a more intelligent, coordinated and capable organisation — without needing a team of AI infrastructure specialists to make it happen.**
