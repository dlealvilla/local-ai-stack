# AI Deployment Project — Product Vision

## North Star

The AI Deployment Project is not merely an LLM deployment utility.

Its long-term product is a secure, self-hosted organisational intelligence
operating layer — a "Company Brain" — that connects:

- AI models
- enterprise knowledge
- users and groups
- applications
- analytics
- permissions
- workflows
- infrastructure

## Immediate product promise

A customer downloads the platform, runs it on a supported
server/workstation/VM, and the platform determines the machine's
capabilities and safely configures itself without requiring the
administrator to understand Linux, Docker, CUDA, vLLM, VRAM,
quantization, ports, or model-serving infrastructure.

The final administrator experience should approximate:

download/run product
→ detect host
→ inspect CPU/RAM/GPU/storage/runtime capabilities
→ inspect existing state
→ select safe executor/runtime
→ recommend compatible models
→ acquire/reuse model artifacts
→ calculate resource requirements
→ configure/start services
→ verify health
→ READY

Advanced/manual controls must also exist for technical administrators,
but automatic safe recommendations are the default.

## Capacity and model optimization as core differentiator

The steps above that determine what a host can safely run, and which
model best uses it, are not internal plumbing. They are the product's
central differentiator: the platform extracts more usable value per
purchased GPU-hour and gigabyte than manual configuration, without
gambling with stability.

Two commitments follow. Capacity evidence is conservative and
explainable, so a confident wrong answer is never preferred to an
honest uncertain one. And characterization is decision-bounded: the
platform characterizes only as much as the current decision requires,
because a bootstrap that spends an hour measuring storage has already
failed the administrator.

`docs/CAPACITY_ARCHITECTURE.md` is authoritative for this domain.

## Portability

"Any server" means capability-based portability across supported
environments, not a promise that literally every computer can run every
model.

Primary validated enterprise reference environment:

- Linux x86_64
- NVIDIA GPU

The architecture must remain capable of supporting:

- Linux ARM64
- Apple Silicon / MLX-style runtimes
- CPU / llama.cpp-style runtimes
- suitable AMD environments
- physical servers
- workstations
- VMs
- cloud VMs
- Mac Studio
- compatible mini-PC/prosumer hardware
- Windows-centric deployments through supported Linux VM approaches
  where appropriate

Do not encode hardware support as giant server-model-specific if/else
trees. Detect capabilities and make decisions from capabilities.

## Core engineering principles

The governing architectural rule is:

**Core owns concepts; adapters own implementations.**

Other non-negotiable principles:

- Exoskeleton first.
- Complete an end-to-end modular product before deeply optimizing
  subsystems.
- Prefer a simple real implementation behind a strong replaceable
  interface.
- Runtime, executor, gateway, model source, storage provider, connector,
  telemetry provider, frontend and licensing provider must remain
  replaceable.
- Do not make Docker mandatory. Native process execution is first class.
- Do not make vLLM a permanent dependency.
- Do not make LiteLLM a permanent dependency.
- Do not duplicate logic that already exists in the platform.
- Reuse existing seams before creating new abstractions.
- Security and permission architecture must not be weakened for speed.
- Permission-aware retrieval is non-negotiable.
- Customer prompts, responses, documents and RAG content remain local by
  default.
- Avoid premature Kubernetes, fleet scheduling, sophisticated bin
  packing, predictive optimization or other deep infrastructure until the
  exoskeleton requires them.
- Do not derail the current roadmap to build future intelligence features
  early.

## Bootstrap / installability requirement

Non-technical installability is a core product requirement.

The eventual customer should not manually:

- install vLLM
- choose CUDA/PyTorch versions
- download model files into directories
- calculate VRAM
- manage ports
- create process services
- understand executors
- reconcile runtime state

The platform itself must progressively own those decisions.

A provisional host-aware bootstrap/resume orchestration layer should be
developed before the polished installer, so we continuously verify that
the architecture supports the final plug-and-play experience. This early
coordinator is not Phase 16's polished installer.

It should eventually orchestrate existing platform components for:

- host detection
- storage capacity/sonar
- persisted-state inspection
- model compatibility
- model selection/recommendation
- model reuse/acquisition
- runtime selection
- runtime provisioning/repair
- capacity planning
- clean process/port/reservation checks
- ResourceManager lifecycle
- health/smoke verification

The eventual goal is a command conceptually similar to `ai bootstrap` or
`ai start`, which is idempotent:

- first run → provision
- second run → reuse
- different host → recalculate
- missing runtime → repair
- compatible model present → reuse
- incompatible model present → retain in inventory but do not run
- stale state → reconcile

Polished installer, packaging, conversational onboarding and
customer-facing recovery UX remain Phase 16 work.

## Model artifact / host portability policy

Persisted models form a reusable model warehouse.

A model being stored does NOT mean it should automatically run on the
current host.

On every host:

detect hardware
→ evaluate stored artifacts
→ classify compatible / conditionally compatible / unsupported
→ independently select the appropriate model/runtime combination

Rules:

- Reuse compatible artifacts.
- Do not delete incompatible artifacts merely because the current host
  cannot run them.
- Do not redownload a model if an appropriate compatible persisted
  artifact already exists.

Longer term, distinguish:

- shared/persistent model repository
- local high-speed execution cache/staging

## Inference instance model

"InferenceInstance" should become a first-class platform concept.

An inference instance is one deployed model-serving service and
eventually includes:

- instance ID
- model and revision/version
- runtime
- executor
- host/GPU allocation
- resource reservation
- endpoint/port
- context/runtime settings
- runtime request concurrency
- platform/gateway concurrency limits
- lifecycle state
- access-policy references

### Two concurrency dimensions

1. **Request concurrency** — many simultaneous requests handled by one
   loaded inference server.
2. **Model/inference-server concurrency** — several separate
   model-serving instances running simultaneously.

One ordinary vLLM server generally represents one loaded base-model
serving instance and may serve many requests concurrently. Different
unrelated base models generally require separate inference-server
instances. LoRA/adapters are a separate multi-variant case.

Enterprise capability should support several simultaneous inference
instances when hardware permits, including:

- multiple vLLM instances sharing a GPU with safe per-instance memory
  allocations
- instances on different GPUs
- eventually instances across hosts

Runtime-specific translation belongs in adapters. The current generic
platform `concurrency` concept still needs to be bound to the appropriate
vLLM runtime control, likely `--max-num-seqs` or equivalent.

### Access boundaries

Access assignments belong above the inference server:

- users
- groups
- roles
- departments
- applications

Identity/access policy and the gateway enforce access.

- Do not put user authorization inside vLLM.
- Do not put licensing logic inside ResourceManager or runtime adapters.

## Knowledge / Company Brain architecture

The platform must include a permission-aware Knowledge/Data Layer above
storage and connectors.

Two paths:

1. **Platform-managed storage** — customers may store files directly in
   the platform.
2. **Existing enterprise systems** — customers connect existing
   document/file systems without migrating everything.

Use platform-owned abstractions such as:

- ManagedStorageProvider
- KnowledgeConnector
- source-agnostic knowledge schema

Potential replaceable implementations/helpers include OpenCloud,
Nextcloud, Microsoft 365 / SharePoint / OneDrive, Google Drive,
SMB/filesystem, WebDAV, Nango and rclone. None of these should become
fixed architectural dependencies.

Track source-aware metadata including:

- source
- external identifier/path
- MIME/type
- revision/checksum
- metadata
- owner
- allowed users/groups/roles
- permissions
- indexing state
- content reference

Keep separate: identity, groups, source permissions, indexing, retrieval
and generation.

At retrieval time, the platform must never return content that the
requesting user is not authorized to access.

## Admin AI Agent

An always-present permission-aware Admin AI Agent is part of the MVP.

It is embedded in the enterprise administration experience and acts as
setup guide, operational copilot, diagnostics assistant, configuration
assistant and knowledge-management helper.

It should:

- explain infrastructure issues in plain language
- interpret hardware/capacity recommendations
- inspect platform APIs and diagnostics
- recommend remediation
- perform mutations only with administrator approval
- manage models, runtimes, capacity, users/groups, connectors, indexing,
  analytics, licensing, policies, troubleshooting and updates through
  structured platform APIs
- preserve permissions/privacy
- support local/offline operation where possible
- never jeopardize primary inference workloads

## Analytics / telemetry / licensing

Keep three domains separate:

1. Customer-side AI usage analytics
2. Vendor product telemetry
3. Licensing / entitlement data

Customer AI usage analytics eventually include requests, input/output
tokens, latency, errors, model/provider usage, time slices and later
cost/effectiveness metrics.

Vendor product telemetry must be optional/modular and content-free by
default. Do not transmit prompts, responses, documents, RAG content or
proprietary payloads to the vendor by default.

Connected licensing should use signed entitlements / short-lived
lease-style tokens with reasonable grace periods. Air-gapped deployments
should support signed offline license files.

Nonpayment should fail gracefully: warnings → restrict new
deployments/updates/paid capabilities where appropriate, before
disrupting existing running workloads. Do not build a destructive kill
switch.

## Frontend strategy

Enterprise Admin UI and end-user chat/workspace UI are separate
products/surfaces.

Current replaceable end-user candidates include LibreChat and Open WebUI.
LibreChat currently has the cleaner commercial licensing position. Open
WebUI may be useful but must not become a mandatory architectural
dependency.

Long-term commercial preference is a lightweight first-party end-user UI
after gateway, identity, knowledge/RAG, streaming inference and APIs
stabilize.

The product's differentiation is primarily the control plane,
orchestration, governance, knowledge, analytics and Admin AI Agent — not
the third-party chat UI.

## Third-party licensing

Before commercial release, maintain formal dependency/license governance.

Classify bundled/embedded models and dependencies at minimum:

- **Green** — permissive commercial use
- **Amber** — copyleft/source-available/branding/redistribution/hosted-service
  or other material restrictions
- **Red** — commercially incompatible dependency or unacceptable
  restriction

Amber/Red components should remain replaceable unless an explicit
commercial decision accepts them.

Eventually generate an SBOM and perform a packaged-license audit. The
Model Catalog should surface model licenses/provenance and commercial-use
warnings. Avoid making Docker Desktop a commercial dependency.

## Team Brain — post-exoskeleton direction

Future Team Brain functionality should be preserved architecturally but
must not derail the MVP roadmap.

TeamBrain is NOT simply "one fine-tuned model per department." A future
TeamBrain may compose:

- team identity/membership/permissions
- permission-scoped knowledge/RAG
- team agent/persona/tools/workflows
- selected base model/model portfolio
- optional LoRA/PEFT adapters
- optional fine-tuned/distilled derived models
- evaluation profile
- memory/state where appropriate
- routing/access policy

Development sequence after the core exoskeleton:

1. Team agent + permission-scoped RAG using existing base models
2. LoRA/PEFT adaptation, dataset curation, evaluation/promotion
3. Full fine-tuning/distillation/preference optimization where justified
4. Later privacy-governed collective intelligence and learned
   optimization

Frequently changing factual company knowledge belongs primarily in RAG,
not model weights.

Training requires explicit dataset provenance and authorization.
Permission to retrieve information does not automatically grant
permission to train on it.

## Derived models / training future hooks

Preserve foundational support for model/artifact lineage.

Derived artifacts should eventually track:

- base/parent model
- exact revision
- derivation type
- training recipe/config
- dataset snapshot/provenance
- owner/team
- permissions
- creation/version
- evaluation
- approval/promotion state
- runtime compatibility
- resource requirements

A future ModelAdaptationProvider should remain separate from inference
runtimes/executors.

Potential techniques, in order of likely adoption:

- LoRA/PEFT first
- supervised fine-tuning
- preference optimization
- merging
- distillation

Resource Manager contracts should eventually represent
training/adaptation jobs separately from inference workloads, but full
training execution is not an MVP requirement.

## Development philosophy

Vertical first. Sophistication second.

Status vocabulary used across this repository:

- **WORKING** — functional enough now
- **PROVISIONAL** — working assumption/implementation expected to improve
- **FUTURE** — architectural slot intentionally not implemented yet

Complete the exoskeleton first, then make each module smarter.
