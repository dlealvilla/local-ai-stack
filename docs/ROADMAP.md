# AI Deployment Project — MVP Roadmap

This is the authoritative 17-phase MVP roadmap.

Do not renumber this roadmap to introduce Team Brain or deeper
intelligence. Those capabilities belong after or on top of the completed
Company Brain exoskeleton.

Current phase: **Phase 9 — Resource Manager / Multi-model Lifecycle**

---

## Completed foundations (Phases 1–8)

Phases 1–8 established the core infrastructure, model lifecycle and
Capacity Planner foundations.

### Phase 1 — Reliable single-node lifecycle — COMPLETE

- prepare/start/stop/restart
- status/health/logs
- real inference acceptance testing
- native process execution

### Phase 2 — Stable core semantics — COMPLETE

- static capacity vs live utilization
- desired vs observed vs health
- requested/recommended/effective settings
- normalized model/service identity
- normalized Platform State

### Phase 3 — Platform API / control plane — COMPLETE FOUNDATION

- managed Platform API
- read-only platform state
- lifecycle control
- permanent acceptance coverage

### Phase 4 — Gateway + analytics spine — COMPLETE FOUNDATION

- process-backed central Gateway
- frontend routed through Gateway
- normalized UsageEvent
- persistent local analytics
- request/event correlation
- analytics summary API
- filtering by time/model/provider

### Phase 5 — Analytics storage architecture — COMPLETE FOUNDATION

- replaceable UsageStore boundary
- UTC time-partitioned local event storage
- RetentionPolicy
- basic/free 7-day default
- migration from legacy JSONL
- UsageExporter boundary
- cloud export disabled by default
- Analytics API remains storage-independent

### Phase 6 — Model Catalog / Marketplace — COMPLETE DISCOVERY FOUNDATION

- ModelSource interface
- local_files adapter
- Hugging Face adapter
- normalized ModelMetadata
- catalog search/discovery
- compatibility evaluation
- compatible / conditionally compatible / unsupported
- runtime recommendations
- external-source failure isolation

### Phase 7 — Model Inventory / Artifact Lifecycle — COMPLETE FOUNDATION

- multiple stored models
- normalized ModelInventoryRecord
- stored vs loaded vs running state observation
- persistent source/revision metadata
- managed Hugging Face download
- managed local-file import
- safe managed update and delete
- Platform API actions for download/import/update/delete
- active selected/running model protection
- staging and rollback boundaries for model replacement

### Phase 8 — Capacity Planner v1 — COMPLETE FOUNDATION

- storage capacity and commit-admission foundation
- canonical live capacity snapshot
- normalized vendor-neutral resource pools
- protected RAM and dedicated-VRAM headroom
- explicit unified-memory fail-closed semantics
- model artifact/resource-requirement envelope
- thin integrated Inventory model feasibility
- explainable compatibility/storage/memory dimensions
- read-only Platform API feasibility boundary

Phase 8 estimators remain PROVISIONAL. The Phase 8 closure section of
`docs/PROVISIONAL.md` records them. Note that `docs/PROVISIONAL.md` is a
historical register whose earlier entries have been overtaken by later
phases; it is not authoritative project context.

---

## Phase 9 — Resource Manager / Multi-model Lifecycle — CURRENT

### Scope

- one host
- explicit resource reservations
- current capacities/reservations
- dynamic admission
- start/stop/load/unload
- desired/actual state reconciliation
- Platform API
- multiple simultaneous inference servers when safe

### Explicitly excluded from Phase 9

- predictive scheduling
- sophisticated bin packing
- preemption
- Kubernetes
- fleet/multi-host scheduling
- smart model routing
- benchmarking systems
- deep KV-cache prediction
- autonomous optimization

### Exit criteria

Phase 9 exit must demonstrate:

- inspect resources
- evaluate stored model
- reserve
- start
- represent running workload
- admit/reject additional workload correctly
- stop/unload
- release
- reconcile state
- Platform API
- real multi-instance acceptance

### Remaining Phase 9 work

1. Diagnose/resolve the Qwen chat-completion smoke timeout.
2. Implement persisted workload/reservation reconciliation and recovery
   (Step 07).
3. Begin provisional host-aware bootstrap/resume orchestration using the
   existing platform seams.
4. Bind platform/runtime request concurrency to runtime-specific controls
   through adapters.
5. Prove at least two genuinely simultaneous inference-server instances
   with safe per-instance resource allocations.
6. Expose ResourceManager lifecycle through Platform API.
7. Run integrated Phase 9 acceptance.
8. Merge accepted Phase 9 into `main`.

---

## Phase 10 — Unified AI Gateway / Provider Abstraction / Static Routing

Static routing first.

- local provider
- external-provider adapter boundary
- RouteDecision
- manual/default route selection
- usage/cost identity preserved

Deferred to later phases: cost-aware, latency-aware, policy, fallback and
quality-aware routing.

## Phase 11 — Enterprise Admin UI

Administration surface for the control plane, including overview,
hardware, model catalog, model inventory, capacity, deployments, usage
analytics, logs/health, configuration and vendor connectivity.

The Admin UI is a separate surface from any end-user chat/workspace UI.

## Phase 12 — Admin AI Agent v1

Permission-aware administration copilot embedded in the Admin UI:

- setup guide
- operational copilot
- diagnostics assistant
- configuration assistant
- knowledge-management helper

Mutations occur only with administrator approval, through structured
platform APIs.

## Phase 13 — Knowledge / Data Layer

Permission-aware knowledge layer above storage and connectors:

- ManagedStorageProvider
- KnowledgeConnector
- source-agnostic knowledge schema
- source-aware metadata, ownership and permissions
- indexing state and content references

No specific storage vendor or connector helper becomes a fixed
architectural dependency.

## Phase 14 — Identity + Permission-Aware Indexing/Search/RAG

- identity and groups
- source permission mapping
- permission-aware indexing
- permission-aware search and retrieval
- retrieval-time authorization enforcement

The platform must never return content the requesting user is not
authorized to access.

## Phase 15 — Analytics / Telemetry / Entitlements

Completes the three separate outbound/data domains:

- customer AI usage analytics
- vendor product telemetry, optional and content-free by default
- licensing/entitlement, with signed entitlements, lease-style tokens,
  grace periods, offline license files and graceful restriction

No destructive kill switch.

## Phase 16 — Bootstrapper + Conversational Onboarding

The polished installer and customer-facing onboarding/recovery UX:

- inspect host capabilities
- select compatible executor/runtime
- create required runtime environments
- install only required components
- keep models separate from the installer
- support future offline bundles
- conversational onboarding

The provisional bootstrap/resume coordinator developed during Phase 9 is
not this phase; it exists to keep the architecture honest until here.

## Phase 17 — Full MVP Integration / Acceptance

End-to-end integration and acceptance of the complete Company Brain
exoskeleton.

---

## Exoskeleton completion definition

An administrator can:

1. install the platform;
2. detect hardware;
3. browse/import models;
4. see compatibility;
5. download/store multiple models;
6. see storage and compute capacity;
7. safely start/stop one or more models;
8. use them through one gateway;
9. view meaningful analytics;
10. manage the deployment through the Admin UI.

After this point, prioritize deeper intelligence rather than major
architectural restructuring.

---

## Post-MVP / deeper intelligence

These are preserved architecturally but are **not** part of the MVP
sequence above, and must not be pulled into current phases:

1. Team agent + permission-scoped RAG using existing base models
2. LoRA/PEFT adaptation, dataset curation, evaluation/promotion
3. Full fine-tuning/distillation/preference optimization where justified
4. Privacy-governed collective intelligence and learned optimization

Also post-MVP: multi-host fleet scheduling, predictive optimization,
advanced routing intelligence and training execution.

See `docs/PRODUCT_VISION.md` for the Team Brain and derived-model
direction.
