# AI Deployment Project — Delivery Roadmap

> **Superseded for phase numbering and scope.**
> `docs/AI_DEPLOYMENT_TECHNICAL_ARCHITECTURE_AND_ROADMAP.md` is the
> architectural source of truth and owns the milestone structure and the
> definition of every phase from Phase 10 onward. Where this file and that
> document disagree, that document wins.

This file remains useful for two things only:

- the delivery record of completed Phases 1–8;
- the in-flight Phase 9 work list.

Deeper intelligence — Team Brain, adaptation, learned routing — still
belongs after the Company Brain exoskeleton is complete, now expressed as
Milestone C rather than as post-MVP appendices.

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

## Phase 10 and beyond

Phase numbering and scope from Phase 10 onward are defined by
`docs/AI_DEPLOYMENT_TECHNICAL_ARCHITECTURE_AND_ROADMAP.md` §33. Do not
plan against the numbering this file used previously; it has been
retired. The current sequence is:

```text
MILESTONE A — Private AI infrastructure exoskeleton
Phase 10  Gateway federation + routing v1 (LiteLLM as adapter)
Phase 11  Identity / Teams / Policy
Phase 12  Admin UI v1 + Diagnostic Assistant
Phase 13  Vendor Connectivity / Heartbeat
Phase 14  Licensing / Entitlement skeleton
Phase 15  Bootstrapper / Installer + Release Governance

MILESTONE B — Company Brain exoskeleton
Phase 16  Knowledge / Data Layer
Phase 17  Company Brain / Team Agent v1
Phase 18  Workflow / Multi-Agent Foundation

MILESTONE C — Learned intelligence
Phase 19  Capacity Intelligence v2
Phase 20  Intelligent Routing
Phase 21  Team Brain Adaptation
Phase 22+ Advanced intelligence
```

Notable changes from the retired numbering: identity now lands early, at
Phase 11, ahead of the Admin UI rather than after it; the knowledge layer
and permission-aware retrieval are merged into a single Phase 16; and the
installer moves earlier, to Phase 15, closing Milestone A.

The provisional bootstrap/resume coordinator developed during Phase 9 is
not the Phase 15 installer; it exists to keep the architecture honest
until that phase.

Consult the architecture document for each phase's contracts, completion
criteria and explicitly deferred work.

---

## Exoskeleton completion definition

Milestone A is complete when an administrator can:

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

## Deeper intelligence

Team Brain, adaptation and learned optimization are no longer an
open-ended post-MVP appendix. They are sequenced as Milestones B and C in
the architecture document, and must still not be pulled into current
phases:

- Team agent + permission-scoped RAG on existing base models — Phase 17
- LoRA/PEFT adaptation, dataset curation, evaluation/promotion — Phase 21
- Full fine-tuning, distillation, preference optimization — Phase 22+
- Learned routing, predictive optimization, multi-host fleet scheduling,
  privacy-governed collective intelligence — Phase 22+

See `docs/PRODUCT_VISION.md` for the Team Brain and derived-model
direction.
