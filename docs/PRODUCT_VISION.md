# AI Stack — Product Vision

## North Star

Build plug-and-play private enterprise AI infrastructure that:

- understands the hardware it is installed on;
- recommends safe deployment settings;
- lets administrators discover and manage appropriate models;
- stores multiple models independently from the installer;
- runs multiple models concurrently when capacity permits;
- provides unified control, routing and analytics;
- preserves sensitive customer AI content locally by default;
- remains independent of any single OS, hardware vendor,
  container system, inference runtime, model hub, gateway,
  telemetry vendor or commercial model.

## Core architectural principle

Core owns concepts.
Adapters own implementations.

Prefer simple WORKING implementations behind strong modular
boundaries before adding sophisticated intelligence.

## Major platform domains

- Control Plane
- Host / Hardware Detection
- Deployment Planner
- Hardware Abstraction
- Executors
- Inference Runtimes
- Model Sources
- Model Metadata Normalization
- Model Catalog / Marketplace
- Model Inventory
- Model Download / Storage Management
- Compatibility Evaluation
- Capacity Planner
- Resource Manager
- Concurrent Model Scheduling
- Central AI Gateway
- Route Decisions
- Customer Usage Analytics
- Local Analytics Storage / Retention
- Optional Cloud Analytics Export
- Vendor Product Telemetry
- Heartbeat / Telemetry Agent
- Licensing / Entitlements
- Admin UI
- Bootstrapper / Installer

## Model architecture

Models are separate artifacts from the installer.

Model discovery uses replaceable ModelSource adapters.

MVP sources:

- Hugging Face
- local files

Future examples:

- NVIDIA NGC
- ModelScope
- Ollama-compatible sources
- MLflow
- private enterprise registries
- internal artifact repositories

All provider metadata must normalize into an internal model schema.

## Model Catalog MVP

Administrators should be able to discover/import models and view:

- family
- architecture
- parameters
- quantization
- context length
- source
- revision
- license
- download size
- expected installed size
- supported runtimes
- hardware requirements
- host compatibility

Compatibility states:

- Compatible
- Conditionally compatible
- Unsupported

## Model Inventory

Stored and running state must remain separate.

Possible states include:

- downloading
- stored
- loading
- loaded
- running
- stopped/unloaded
- updating
- incompatible

Lifecycle actions should eventually include:

- download
- resume
- start
- stop
- unload
- restart
- delete
- update
- convert
- quantize

## Capacity / Resources

Capacity Planner considers:

- storage
- RAM
- VRAM / unified memory
- runtime overhead
- model size
- quantization
- caches
- context
- concurrency
- safety margins
- existing workloads

Resource Manager tracks reservations and live usage across:

- CPU
- RAM
- VRAM / unified memory
- storage
- accelerators
- ports
- processes
- workloads

Concurrent model execution is first-class.

## Gateway

All enterprise AI traffic may flow through a central logical
gateway.

The gateway supports:

- local models
- external APIs
- future routing

Gateway implementation remains replaceable.

Routing intelligence evolves later.

Initial routing may be manual/default.

## Analytics

Analytics is a core MVP capability.

Every AI request produces a normalized UsageEvent.

Basic analytics include:

- requests
- input/output/total tokens
- latency
- errors
- model/provider usage
- time slicing

Future dimensions include:

- user
- team
- application
- department
- deployment
- server
- route
- cost
- local vs external
- infrastructure utilization

## Privacy-first analytics

Prompts, responses, documents, RAG content and proprietary
payloads remain local by default.

Basic/free target:

approximately 7 days of bounded local analytics.

Paid deployments may optionally export structured non-content
UsageEvent telemetry for long-term analytics.

Local UsageStore and cloud UsageExporter remain replaceable.

## Three separate outbound/data domains

1. Customer AI usage analytics
2. Vendor product-usage telemetry
3. Licensing / entitlement information

These must remain logically separate.

## Heartbeat / Telemetry Agent

A future lightweight outbound boundary may provide independent
channels for:

- entitlement heartbeat
- optional cloud analytics
- product telemetry
- update checks
- crash/error reporting

Administrators must be able to see what leaves the deployment.

Air-gapped deployments may disable outbound connectivity.

## Licensing

Use signed feature/capacity entitlements.

Support:

- connected leases/renewal
- reasonable grace periods
- graceful restriction
- offline signed licenses

Never use destructive remote shutdown behavior.

Running workloads and customer data must be protected.

## Portability

Primary validated reference:

Linux x86_64 + NVIDIA

Architecture should also allow:

- Linux ARM64
- AMD / ROCm
- Intel accelerators
- CPU-only
- Apple Silicon / Metal / MLX
- virtual machines
- cloud VMs
- workstations
- enterprise rack servers
- suitable mini-PC/prosumer hardware

Executors and runtimes remain independent.

## Development philosophy

Vertical first.
Sophistication second.

Use:

WORKING
- functional enough now

PROVISIONAL
- working assumption/implementation expected to improve

FUTURE
- architectural slot intentionally not implemented yet

Complete the exoskeleton first, then make each module smarter.
