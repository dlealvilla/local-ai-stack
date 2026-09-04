# AI Stack — Exoskeleton Roadmap

> **HISTORICAL SNAPSHOT — NOT AUTHORITATIVE.**
> This is the pre-Phase-7 roadmap, preserved for project history.
> Its phase numbering has been superseded.
> The current authoritative roadmap is `docs/ROADMAP.md`.

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

Still intentionally deferred into Phase 7:

- managed local-file import
- Hugging Face download/import
- richer artifact metadata enrichment


## Current

### Phase 7 — Model Inventory / Lifecycle

MVP:

- multiple stored models
- normalized ModelInventoryRecord
- stored vs loaded vs running state
- disk usage
- source/revision
- managed Hugging Face download
- managed local-file import
- download progress/state
- start/stop/unload/delete/update lifecycle boundary


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
