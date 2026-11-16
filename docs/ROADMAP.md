# Local AI Stack Roadmap

## Where we are now

The current public release is [v0.1.0](https://github.com/dlealvilla/local-ai-stack/releases/tag/v0.1.0). The path that works today is **Linux + NVIDIA + vLLM**. Phases 1–7 below are complete foundations: lifecycle, core semantics, Platform API, gateway and analytics, model catalog, and model inventory. Prototypes and vertical slices of later capacity and resource work are already in the tree; many settings remain provisional (see [`PROVISIONAL.md`](PROVISIONAL.md) and the [README](../README.md) status note). This is not a finished commercial appliance.

## What's next

In plain terms, the next work already listed later in this document is:

- a capacity planner (disk, RAM and VRAM feasibility, safety margins, conservative recommendations)
- a resource manager so more than one model can be admitted, started, and stopped safely
- a gateway routing skeleton (local provider first, plus an external-provider boundary)
- a first-party admin UI (the [design demo](https://local-ai-stack-demo.vercel.app) is mock screens only)
- later: heartbeat / telemetry, a licensing / entitlement skeleton, and a bootstrapper / installer — only after the foundations above stabilize

This section restates existing phases; it does not add new commitments.

## Where newcomers can help

You do not need a GPU to contribute. See [Contribute without a GPU](../CONTRIBUTING.md#contribute-without-a-gpu). Look for issues labelled [good first issue](https://github.com/dlealvilla/local-ai-stack/labels/good%20first%20issue) or [help wanted](https://github.com/dlealvilla/local-ai-stack/labels/help%20wanted), and use [Discussions](https://github.com/dlealvilla/local-ai-stack/discussions) for questions and ideas.

---

## Completed

### Phase 1 — Reliable single-node lifecycle
COMPLETE

- prepare/start/stop/restart
- status/health/logs
- real inference acceptance testing
- native process execution

### Phase 2 — Stable core semantics
COMPLETE

- static capacity vs live utilization
- desired vs observed vs health
- requested/recommended/effective settings
- normalized model/service identity
- normalized Platform State

### Phase 3 — Platform API / control plane
COMPLETE FOUNDATION

- managed Platform API
- read-only platform state
- lifecycle control
- permanent acceptance coverage

### Phase 4 — Gateway + analytics spine
COMPLETE FOUNDATION

- process-backed central Gateway
- Open WebUI routed through Gateway
- normalized UsageEvent
- persistent local analytics
- request/event correlation
- analytics summary API
- filtering by time/model/provider

### Phase 5 — Analytics storage architecture
COMPLETE FOUNDATION

- replaceable UsageStore boundary
- UTC time-partitioned local event storage
- RetentionPolicy
- basic/free 7-day default
- migration from legacy JSONL
- UsageExporter boundary
- cloud export disabled by default
- Analytics API remains storage-independent

### Phase 6 — Model Catalog / Marketplace
COMPLETE DISCOVERY FOUNDATION

- ModelSource interface
- local_files adapter
- Hugging Face adapter
- normalized ModelMetadata
- catalog search/discovery
- compatibility evaluation
- compatible / conditionally compatible / unsupported
- runtime recommendations
- external-source failure isolation

Phase 6 follow-on capabilities now implemented in Phase 7:

- managed local-file import
- managed Hugging Face download
- persistent source/revision metadata


## Current

### Phase 7 — Model Inventory / Artifact Lifecycle — COMPLETE FOUNDATION

WORKING:

- multiple stored models
- normalized ModelInventoryRecord
- stored vs loaded vs running state observation
- disk usage
- persistent source/revision metadata
- managed Hugging Face download
- managed local-file import
- transfer/download state
- safe managed update
- safe managed delete
- Platform API actions for download/import/update/delete
- active selected/running model protection
- staging and rollback boundaries for model replacement

PROVISIONAL:

- transfer and update operations are synchronous
- integrity/checksum verification is not yet implemented
- automatic upstream update detection is not yet implemented

FUTURE / Phase 9:

- per-model start
- per-model stop
- per-model unload
- concurrent model lifecycle orchestration
- Resource Manager admission and reservations


## Next

### Phase 8 — Capacity Planner v1

MVP:

- disk feasibility
- RAM/VRAM feasibility
- runtime overhead estimates
- safety margins
- context/concurrency effects
- existing workload awareness
- conservative recommendations
- oversubscription warnings

### Phase 9 — Resource Manager / Multi-model

MVP:

- CPU/RAM/VRAM/storage/port reservations
- per-model start/stop/unload
- concurrent model services
- admission checks
- unload recommendations
- live utilization observation
- stored models separated from loaded/running models

### Phase 10 — Gateway provider/routing skeleton

MVP:

- local provider
- external-provider adapter boundary
- RouteDecision
- manual/default route selection
- usage/cost identity preserved

FUTURE:

- cost-aware routing
- latency-aware routing
- policy routing
- fallback
- quality-aware routing

### Phase 11 — Admin UI v1

Pages:

- Overview
- Hardware
- Model Catalog
- Model Inventory
- Capacity
- Deployments
- Usage Analytics
- Logs / Health
- Configuration
- Vendor Connectivity

### Phase 12 — Heartbeat / Telemetry Agent

Separate configurable channels:

- licensing heartbeat
- product telemetry
- optional cloud analytics
- update checks
- crash/error reporting

Customer content excluded by default.

### Phase 13 — Licensing / Entitlement skeleton

MVP architecture:

- signed entitlement claims
- features
- capacities
- local verification
- renewal/grace period
- offline license support
- graceful restriction rather than destructive shutdown

### Phase 14 — Bootstrapper / Installer

Only after the control plane, catalog, inventory, capacity,
analytics and admin-facing foundations stabilize.

Installer should:

- inspect host capabilities
- select compatible executor/runtime
- create required runtime environments
- install only required components
- keep models separate
- support future offline bundles


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

After this point, prioritize deeper intelligence rather than
major architectural restructuring.
