# Provisional Implementation Register

This file records assumptions, temporary defaults, incomplete modules,
and shortcuts that must be revisited as the AI Platform matures.

The purpose is to allow development of the complete platform architecture
without losing track of lower-level work that still needs improvement.

---

## Performance defaults

### Context length

Current value:

8192 tokens

Status:

PROVISIONAL

Why:

A conservative context size that has previously worked with the current
small quantized model.

Future replacement:

Calculate from:

- model architecture
- model maximum context
- KV-cache requirements
- GPU VRAM
- workload profile
- desired concurrency
- inference backend capabilities

Then validate through an actual startup test.

---

### GPU memory utilization

Current value:

0.85

Status:

PROVISIONAL

Why:

Leaves approximately 15% GPU-memory headroom and has previously worked
for the prototype deployment.

Future replacement:

Backend-specific recommendation based on:

- free VRAM
- model requirements
- other GPU workloads
- concurrency
- runtime validation

---

### Concurrency

Current value:

4

Status:

PROVISIONAL

Why:

Provides a small multi-user target while the concurrency planner is
not yet implemented.

Important:

This is currently a platform-level concept.

It is NOT yet intelligently mapped to vLLM settings such as:

- max_num_seqs
- max_num_batched_tokens
- KV-cache allocation

Future replacement:

Capacity planning + benchmarking + runtime metrics.

---

## Storage

### Data root

Current value:

/workspace

Status:

PROVISIONAL / DEPLOYMENT-SPECIFIC

Why:

RunPod mounts the persistent Network Volume here.

Future replacement:

Detect or configure AI_DATA_ROOT per deployment.

Examples may include:

- /workspace
- /srv/ai
- /mnt/ai
- other persistent storage

---

### Storage capacity

Status:

INCOMPLETE

Current implementation:

Uses filesystem-reported capacity.

Problem:

Network filesystems such as RunPod may report the capacity of the
underlying shared filesystem rather than the user's allocated quota.

Future replacement:

Storage-provider adapters capable of reporting usable quota.

---

## Hardware detection

Current support:

- Linux
- CPU information
- RAM
- NVIDIA GPU detection through nvidia-smi
- VRAM total/free

Status:

PARTIAL

Missing future support:

- AMD
- Intel GPU
- Apple Silicon
- CPU-only deployments
- detailed multi-GPU topology
- provider-specific hardware metadata

---

## Model management

Current support:

- local model discovery
- Hugging Face-style config.json inspection
- safetensors / GGUF / BIN detection
- architecture metadata
- quantization metadata
- model size
- context metadata

Status:

PARTIAL

Missing:

- model downloads
- remote catalogue
- Hugging Face authentication
- model compatibility checks
- engine compatibility checks
- model switching
- model deletion
- integrity validation
- multiple active models

---

## Model memory estimation

Status:

INCOMPLETE

Currently known:

- weight-file size
- model architecture metadata
- available GPU VRAM

Not yet calculated reliably:

- runtime overhead
- KV-cache memory
- activation/workspace memory
- concurrency effects
- multi-GPU distribution

The current preliminary fit assessment must NOT be treated as proof that
a deployment will successfully run.

---

## Runtime validation

Status:

NOT IMPLEMENTED

Future behavior:

1. Produce candidate configuration.
2. Attempt model startup.
3. Observe actual memory allocation.
4. Reduce or adjust settings if needed.
5. Save validated configuration.

---

## Inference backend

Current default:

vLLM 0.10.2

Status:

DEFAULT MODULE, NOT PERMANENT ARCHITECTURE

Future architecture:

Inference backend is replaceable through adapters.

Possible examples:

- vLLM
- llama.cpp
- Ollama
- other serving engines

---

## Gateway

Current default:

direct

Status:

DEFAULT MODULE

LiteLLM is NOT a permanent dependency.

Future gateways may include:

- direct
- LiteLLM
- another gateway
- custom implementation

---

## Frontend

Current default:

Open WebUI 0.11.0

Status:

DEFAULT MODULE

The frontend is not part of the core AI platform.

Future possibilities:

- Open WebUI
- another frontend
- custom frontend
- no frontend / API-only deployment

---

## Tool calling

Current value:

disabled

Status:

PROVISIONAL

Reason:

The current vLLM/Qwen/Open WebUI prototype produced tool-choice errors
without additional parser configuration.

Future replacement:

Model/backend-aware tool capability detection and configuration.

---

## Networking

Current default:

Private loopback bindings.

Open WebUI:
127.0.0.1:3000

vLLM:
127.0.0.1:8000

Future platform API:
127.0.0.1:4000

Status:

SAFE BOOTSTRAP DEFAULT

Future exposure mechanisms should be modular, for example:

- SSH tunnel
- private LAN
- VPN
- reverse proxy
- TLS
- authenticated public API

Public exposure must never be enabled implicitly.

---

## Dependency management

Current prototype versions include:

- vLLM 0.10.2
- Open WebUI 0.11.0
- previously validated Transformers / NumPy / Numba compatibility pins

Status:

PROVISIONAL

Future replacement:

Containerized, versioned runtime images with tested compatibility matrices.

---

# Development strategy

For the next phase:

DO NOT block higher-level architecture development on these items.

Use the provisional defaults to build:

- controller
- lifecycle management
- adapters
- runtime orchestration
- model management interface
- frontend abstraction
- gateway abstraction
- inference abstraction
- API
- deployment packaging
- portability

Then return to this register and systematically replace provisional
assumptions with detection, planning, validation, or user guidance.

---

## Runtime executor

Current default:

docker

Status:

PROVISIONAL DEFAULT / MODULAR COMPONENT

Why:

Docker provides a reproducible runtime environment and avoids depending
on Python packages being installed correctly on the host machine.

The process executor remains available for development and debugging.

Current limitations:

- Docker availability is not yet detected.
- NVIDIA Container Toolkit compatibility is not yet validated.
- Container lifecycle management is not yet implemented.
- Docker image compatibility is not yet automatically selected.
- Model mount paths are currently based on /workspace/models.
- Only vLLM has a Docker execution definition.

Future replacement:

Runtime executor selection should consider:

- operating system
- container runtime availability
- GPU runtime availability
- deployment target
- administrator preference

Possible executors may include:

- Docker
- Podman
- native process
- Kubernetes
- other orchestration systems

---

## Deployment manifest service adapters

Status:

PARTIAL

Current implementation:

The deployment manifest now describes the complete desired stack:

- inference
- gateway
- frontend

Inference specifications are generated through the inference adapter.

However:

- frontend specifications are still generated generically
- gateway specifications are not yet implemented
- `direct` gateway currently means no separate gateway process

Future replacement:

Create dedicated adapter interfaces for:

- frontend providers
- gateway providers

Examples:

Frontend adapters:
- Open WebUI
- custom frontend
- API-only / none

Gateway adapters:
- direct
- LiteLLM
- future gateway implementations

The deployment controller should consume these adapters without
hard-coding provider-specific behavior.

---

## Docker deployment topology

Status:

PROVISIONAL

Current Docker network:

ai-stack-network

Current container names:

- ai-stack-inference
- ai-stack-frontend

Current Open WebUI internal port:

8080

Current persistent Open WebUI data path:

/workspace/open-webui-data

Current model mount:

/workspace/models

Current Open WebUI image:

ghcr.io/open-webui/open-webui:v0.11.0

Current inter-container inference endpoint:

http://ai-stack-inference:8000/v1

These values currently allow the complete bootstrap stack to be
described and deployed consistently.

Future replacement:

Generate deployment-specific names and paths from:

- deployment ID
- configured data root
- selected executor
- selected frontend
- selected inference engine
- network policy

Container image versions should eventually come from a tested
compatibility matrix rather than being embedded in executor code.

Docker provider-specific command construction is also currently
bootstrap logic. It should later move behind cleaner executor/service
integration interfaces.

---

## Emergency native runtime location

Current fallback runtime:

/.runtime/vllm/.venv

Status:

TEMPORARY BOOTSTRAP FALLBACK

Reason:

The initial working native runtime was accidentally created from the
filesystem root rather than from inside the project directory.

It is usable and has been validated with:

- Python 3.12.3
- vLLM 0.10.2
- PyTorch 2.8.0+cu128
- CUDA 12.8
- Transformers 4.55.2
- NumPy 2.2.6
- Numba 0.61.2
- NVIDIA GeForce RTX 4090

This location must NOT become a permanent architectural assumption.

Future runtime manager behavior:

- choose a configurable runtime root
- detect existing compatible runtimes
- create runtimes when necessary
- validate them before use
- allow explicit user overrides
- support multiple engines and versions

---

## Runtime preparation manager

Current behavior:

./ai prepare

creates missing native runtimes under:

/opt/ai-stack/runtime

Current fallback profiles:

vLLM:
- Python 3.12
- vLLM 0.10.2
- Transformers 4.55.2
- NumPy 2.2.6
- Numba 0.61.2

Open WebUI:
- Python 3.12
- Open WebUI 0.11.0

Status:

PROVISIONAL FALLBACK IMPLEMENTATION

Future replacement:

The runtime manager should eventually:

- inspect operating system and hardware
- detect available local storage
- choose runtime location
- resolve tested compatibility profiles
- select appropriate engine/version
- detect existing compatible runtimes
- support upgrades and rollback
- validate installed runtimes
- support additional inference engines/frontends
- support automatic or administrator-selected execution methods

The public concept of "prepare runtimes" should remain stable even
when the implementation becomes more intelligent.

---

## Process lifecycle supervision

Current status:

PROVISIONAL

Native services are currently tracked using:

- one PID file per service
- one isolated process session/group per service
- SIGTERM for graceful shutdown
- SIGKILL fallback after timeout

This is intentionally simple and sufficient for the current
single-node vertical slice.

Future improvements may include:

- richer persisted service identity
- PID reuse protection
- structured service state
- crash/recovery detection
- automatic restart policies
- configurable shutdown timeouts
- operating-system service integration
- container/orchestrator-specific lifecycle adapters

The public lifecycle concepts should remain stable:

start
stop
restart
status
health
logs

---

## Restart orchestration

Current status:

PROVISIONAL

./ai restart currently performs:

1. controlled shutdown in reverse service order
2. normal startup in dependency order

The orchestration currently lives in the CLI layer.

Future improvement:

Move deployment lifecycle orchestration into a reusable core service
so CLI, Platform API, Admin UI, and future integrations all invoke the
same lifecycle interface.

The public command and lifecycle concept should remain unchanged.

---

## Log management

Current status:

PROVISIONAL

Native service stdout/stderr is stored in local text files under:

logs/

Current CLI:

./ai logs
./ai logs inference
./ai logs frontend

The CLI currently displays the most recent lines only.

Future improvements may include:

- structured logging
- timestamps and severity normalization
- searchable logs
- log rotation and retention policies
- streaming / follow mode
- metrics and trace correlation
- Admin UI log viewer
- external observability integrations

The platform-level concept of service logs should remain stable.

---

## Health and readiness

Current status:

PROVISIONAL

The platform distinguishes:

status
- whether the configured TCP endpoint is reachable

health
- whether the service responds through its functional API

Current probes:

vLLM
- GET /v1/models

Open WebUI
- GET /

Future improvements:

- provider-specific health adapters
- separate startup/readiness/liveness concepts
- degraded service states
- dependency health
- richer diagnostic reasons
- historical health state
- Admin UI health visualization
- monitoring integration

The platform-level health concept should remain stable.

---

## Open WebUI security and network behaviour

Current status:

PROVISIONAL

Observed bootstrap behaviour includes:

- CORS_ALLOW_ORIGIN=*
- startup access to Hugging Face for embedding-model assets

These are acceptable for the current development environment.

Future production work must address:

- restrictive CORS policy
- offline/air-gapped startup
- pre-bundled or configurable embedding models
- explicit outbound-network policies
- administrator-controlled external downloads

---

## End-to-end acceptance testing

Current status:

WORKING WITH PROVISIONAL COVERAGE

./ai test currently validates:

- inference model discovery
- one real chat-completion request
- token usage returned by the inference API
- Open WebUI HTTP availability

This establishes the first repeatable vertical-slice test.

Future coverage should expand as new platform layers are added:

- Platform API
- gateway
- usage-event persistence
- token/cost analytics
- external API providers
- routing decisions
- Admin UI
- authentication and authorization
- licensing/entitlements

Each future major vertical slice should extend this same
acceptance-test concept rather than replacing it.

---

## Static capacity vs live utilization

The platform must distinguish between two different concepts.

STATIC CAPACITY
Used by planning and compatibility logic.

Examples:
- total GPU VRAM
- GPU count
- model weight size
- architecture capability

LIVE UTILIZATION
Used by monitoring and operational state.

Examples:
- currently free VRAM
- GPU utilization
- active processes
- request load
- tokens per second

The planner must not classify a deployment as incompatible merely
because an already-running deployment is consuming GPU memory.

Current static model-fit logic remains PROVISIONAL because it only
compares model weight size against total GPU VRAM.

Future planning must include:
- runtime overhead
- KV cache
- context length
- concurrency
- quantization
- tensor parallelism
- engine-specific requirements
- measured startup validation

---

## Normalized platform state

Current status:

WORKING WITH PROVISIONAL SCHEMA

core/platform_state.py provides a normalized representation of:

- hardware
- selected model
- planning result
- desired deployment
- observed runtime state
- functional health

Important semantic separation:

DESIRED
What the deployment manifest says should exist.

OBSERVED
What is currently running.

HEALTH
Whether the running service responds correctly.

Provider-specific configuration remains nested under:

deployment.services[].desired.spec

This prevents generic platform consumers from becoming tightly
coupled to vLLM, Open WebUI, LiteLLM, Docker, or future providers.

Current schema_version:

1

Future consumers:

- Platform API
- CLI
- Admin UI
- monitoring
- gateway/control plane
- automation

Future additions may include:

- configuration auto/manual metadata
- model inventory
- richer service lifecycle state
- metrics
- usage analytics
- route decisions
- identity
- licensing/entitlements

Do not add those prematurely.

The normalized platform-state concept should remain stable even
as the schema evolves.

---

## Auto and manual configuration semantics

Current status:

WORKING STRUCTURE / PROVISIONAL INTELLIGENCE

Configurable performance parameters are normalized into:

mode
- auto
- manual

requested
- explicit administrator/config value
- null when mode is auto

recommended
- platform recommendation when available

effective
- value actually supplied to the deployment

reason
- explanation for the effective/recommended value

confidence
- quality/source of the recommendation

Current bootstrap configuration uses explicit values, therefore:

context_length
gpu_memory_utilization
concurrency

currently appear as MANUAL/configured settings.

These remain provisional defaults.

Current automatic recommendation coverage is incomplete.

gpu_memory_utilization:
- preliminary automatic resolver exists

context_length:
- automatic resolver FUTURE

concurrency:
- automatic resolver FUTURE

Future Admin UI controls should use this normalized representation
rather than interpreting raw TOML values directly.

The AUTO/MANUAL semantic structure should remain stable while
recommendation algorithms improve.

---

## Model and service identity

Current status:

WORKING STRUCTURE / PROVISIONAL COVERAGE

The platform distinguishes between:

logical_name
- name exposed to clients/applications
- example: local-llm

model_id
- concrete model artifact/deployment identity
- example: qwen3-8b-awq

provider
- implementation/provider serving the model
- example: vllm

service_id
- platform-managed service identity
- example: inference

role
- generic service role
- inference / gateway / frontend

This distinction is important for future:

- gateway routing
- usage analytics
- token accounting
- model switching
- external API providers
- multi-model deployments
- multi-server deployments

Future usage events should eventually distinguish:

requested_model
actual_model
provider
service_id
route_reason

Do not collapse these identities into one field.

Current model source coverage:

- local filesystem

Future model/provider sources may include:

- external API
- Hugging Face
- remote inference service
- managed provider
- other model registries

The identity structure should evolve without tying the platform
to any single inference engine.

---

## Platform API

Current status:

WORKING READ-ONLY FOUNDATION

The Platform API is the CONTROL PLANE interface.

It is separate from the future AI Gateway, which will handle
model inference traffic.

Current endpoints:

GET /health
GET /state
GET /hardware
GET /models
GET /deployment

Current transport implementation:

Python ThreadingHTTPServer

Status:

PROVISIONAL

This deliberately avoids introducing another runtime dependency
while the resource/API boundaries are being validated.

Future improvements may include:

- production HTTP framework
- authentication
- authorization
- versioned API paths
- structured errors
- lifecycle actions
- configuration writes
- model management
- metrics
- pagination
- API documentation
- Admin UI integration

The Platform API resource concepts should remain stable even if
the HTTP implementation changes.

---

## Managed Platform API lifecycle

Current status:

WORKING / PROVISIONAL IMPLEMENTATION

The Platform API is now a managed deployment service:

service_id:
platform_api

role:
platform_api

provider:
builtin_http

It participates in:

start
stop
restart
status
health
logs

Current implementation uses:

python -m platform_api.server

A dedicated /live endpoint provides non-recursive API liveness.

Future improvements may replace the HTTP implementation while
preserving the Platform API service and resource contracts.

The Platform API remains the CONTROL PLANE.

The future AI Gateway remains a separate DATA PLANE service.

---

## Platform API acceptance coverage

The permanent vertical-slice acceptance test now validates:

- local model discovery
- real chat completion
- token usage returned by inference
- Open WebUI availability
- Platform API liveness
- normalized Platform State API
- expected Platform State schema version

Current Platform State schema_version:

1

Future phases should continue extending this acceptance test as
new vertical slices are introduced.

Examples:

gateway
usage-event persistence
analytics
external providers
routing
Admin UI

Do not replace the existing test with isolated component tests.

---

## Platform API lifecycle actions

Current status:

WORKING / PROVISIONAL

First write operation:

POST /deployment/restart

Current behavior:

- preserves the Platform API control-plane process
- stops AI workload services in reverse dependency order
- starts AI workload services in dependency order

Current control-plane role:

platform_api

Current workload roles include:

inference
frontend
gateway when process-backed

PROVISIONAL LIMITATIONS

Lifecycle API operations are currently synchronous.

A restart request may therefore remain open while a model loads.

Future design should introduce:

- asynchronous operations
- operation IDs
- progress/state reporting
- cancellation where appropriate
- administrator identity
- authorization
- audit records

Example future model:

POST /deployment/restart
        ↓
operation_id
        ↓
GET /operations/{id}
        ↓
stopping / starting / healthy / failed

The reusable lifecycle logic should live in core/control.py,
not in the HTTP or Admin UI layers.

---

## Built-in AI Gateway

Current status:

WORKING / PROVISIONAL

Provider:

builtin_proxy

Endpoint:

127.0.0.1:4000

Current request path:

Open WebUI / clients
        ↓
AI Gateway
        ↓
vLLM
        ↓
local model

Current capabilities:

- OpenAI-compatible GET forwarding
- OpenAI-compatible POST forwarding
- streaming response forwarding
- local gateway liveness
- managed platform lifecycle
- generic gateway adapter boundary

Current limitations:

- one upstream inference backend
- no persistent analytics
- no users/teams/applications
- no authentication
- no external AI APIs
- no cost tracking
- no routing logic
- no fallback logic
- no budgets
- no rate limiting

The builtin proxy is intentionally simple.

Future gateway implementations may include:

- improved built-in gateway
- LiteLLM
- another external gateway
- enterprise-specific implementations

The platform owns the GATEWAY CONCEPT.

No particular gateway implementation should become a permanent
architectural dependency.

---

## Usage Event v1

Current status:

WORKING FOUNDATION / PROVISIONAL STORAGE

Gateway requests now produce normalized UsageEvent records.

Current fields include:

- schema version
- event ID
- timestamp
- HTTP method
- endpoint
- requested model
- logical model
- actual model
- provider
- gateway service ID
- HTTP status
- success/failure
- latency
- input tokens
- output tokens
- total tokens
- streaming indicator

Future fields already have conceptual slots for:

- user
- team
- application
- route decision
- cost

Current storage provider:

jsonl

Current default persistent location:

/workspace/data/analytics/usage-events.jsonl

JSONL is PROVISIONAL.

Future storage may use:

- SQLite
- PostgreSQL
- ClickHouse
- another analytics/event system

Core UsageEvent semantics must not depend on the chosen store.

Current token extraction works for normal JSON responses.

Streaming token accounting remains PROVISIONAL and may initially
produce null token fields until proper SSE usage extraction is added.

Analytics recording failures must not prevent an inference
response from being returned to the client.

---

## Usage-event acceptance coverage

The permanent acceptance test now verifies end-to-end
correlation between:

gateway response request ID
        ↓
persisted UsageEvent event_id

It also validates:

- /v1/chat/completions event path
- requested logical model
- successful response
- exact total-token agreement between upstream response
  and stored UsageEvent

Current lookup implementation is PROVISIONAL because the JSONL
adapter performs a linear scan.

Future indexed stores should preserve the same conceptual lookup:

event_id -> UsageEvent

---

## Analytics Summary API

Current status:

WORKING FOUNDATION / PROVISIONAL AGGREGATION

Endpoint:

GET /analytics/summary

Current metrics:

- requests
- successful requests
- errors
- error rate
- input tokens
- output tokens
- total tokens
- average latency

Current slices:

- model
- provider
- day

Architecture:

UsageEvents
    ↓
Usage Store
    ↓
core analytics engine
    ↓
Platform API
    ↓
future Admin UI

Current aggregation loads all JSONL events into memory.

This is PROVISIONAL.

Future analytics should add:

- time/date filters
- user
- team
- application
- tenant
- model/provider combinations
- local vs external
- p50/p95/p99 latency
- time to first token
- tokens per second
- cached/reasoning tokens
- cost
- local infrastructure cost
- routing/fallback/retry metrics
- deployment/server/GPU dimensions
- report/export support

Analytics remains a core MVP capability.

---

## Analytics API acceptance coverage

The permanent acceptance test now validates the first analytics
API contract.

It verifies:

- analytics is enabled
- analytics schema version
- request aggregation
- successful-request aggregation
- token aggregation
- model slicing
- provider slicing
- daily slicing

Exact aggregate values are intentionally not hard-coded because
usage data grows as requests are made.

Future acceptance coverage should expand alongside:

- time filters
- model/provider filters
- user/team/application dimensions
- latency percentiles
- cost analytics
- routing analytics

---

## Analytics filters

GET /analytics/summary supports:

start
- inclusive ISO-8601 timestamp

end
- exclusive ISO-8601 timestamp

model
- matches logical or actual model

provider
- matches inference/provider identity

Examples:

/analytics/summary?provider=vllm

/analytics/summary?model=qwen3-8b-awq

/analytics/summary?start=2026-08-26T00:00:00Z&end=2026-08-27T00:00:00Z

Filters are applied to raw UsageEvents before aggregation.

PROVISIONAL:

- timestamps are currently interpreted in UTC
- no timezone preference exists yet
- no pagination/query planner exists
- JSONL still requires full-file scanning

Future Admin UI controls should generate these filters rather
than reading or filtering raw usage data itself.

---

## Future analytics storage architecture

Status:

DESIGN AGREED / NOT YET IMPLEMENTED

The current JSONL UsageStore remains WORKING but PROVISIONAL.

Do NOT build long-term analytics around one indefinitely growing
JSONL file.

Target architecture:

Gateway
    ↓
UsageEvent
    ↓
Usage Pipeline
    ├── Local UsageStore
    │      ↓
    │   retention policy
    │
    └── Optional UsageExporter
           ↓
       external/cloud analytics

LOCAL BASIC PRODUCT

Default analytics retention target:

7 days

The local analytics store must remain bounded.

Preferred future local-storage pattern:

time-partitioned event storage

Example:

data/analytics/usage/
    2026-08-24.*
    2026-08-25.*
    2026-08-26.*

The exact storage format is intentionally NOT fixed yet.

Possible implementations include:

- partitioned JSONL
- SQLite where appropriate
- Parquet + DuckDB
- another embedded/local analytics store

Storage should remain behind a replaceable UsageStore adapter.

Retention should be a separate platform concept rather than
hard-coded into the Gateway.

PAID / OPTIONAL CLOUD ANALYTICS

A future UsageExporter may asynchronously send structured,
non-content UsageEvent telemetry to a vendor-hosted analytics
service.

The Gateway must not wait for cloud analytics before returning
an inference response.

Future export architecture should support:

- buffering
- batching
- retry
- failure isolation
- eventual delivery
- optional persistent export queue

Potential long-term cloud analytics storage may include an
analytical database such as ClickHouse, but this is NOT fixed.

PRIVACY BOUNDARY

Vendor cloud analytics should contain structured operational
telemetry only.

Examples:

- timestamps
- request/event IDs
- model/provider
- input/output/total token counts
- latency
- status/errors
- routing metadata
- user/team/application identifiers when enabled
- deployment identifiers
- cost metadata

Do NOT upload by default:

- prompts
- responses
- uploaded files
- documents
- RAG contents
- proprietary request payloads
- arbitrary raw service logs

SERVICE LOGS AND USAGE EVENTS ARE SEPARATE CONCEPTS.

Raw runtime/service logs should have their own local rotation
and retention policy.

They must not automatically flow into vendor analytics.

PRODUCT DIRECTION

Basic/free:
- analytics included
- bounded local analytics history
- target default approximately 7 days

Paid:
- analytics included
- optional richer/configurable retention
- optional vendor-cloud export
- long-term historical analytics/reporting

Entitlements may later determine available retention and export
features without changing the Gateway or UsageEvent concepts.

CORE DESIGN RULE

Gateway emits UsageEvents.

UsageStore decides how local events are stored.

RetentionPolicy decides how long local events remain.

UsageExporter decides whether sanitized telemetry leaves the
deployment.

Analytics API consumes normalized analytics independently of
those implementation choices.

---

## Partitioned analytics storage

Current status:

WORKING FOUNDATION

The local UsageStore now uses daily UTC partitions.

Example:

data/analytics/usage/
    2026-08-26.jsonl
    2026-08-27.jsonl

Basic/free default:

local_retention_days = 7

RetentionPolicy is separate from UsageStore.

The Gateway emits UsageEvents through UsagePipeline and does
not own storage or retention decisions.

Current UsageStore:

partitioned_jsonl

Current format remains PROVISIONAL.

Future replacements may include:

- SQLite where appropriate
- Parquet / DuckDB
- PostgreSQL
- ClickHouse
- another local analytical store

The Analytics API must remain independent of these choices.

A UsageExporter interface now exists.

Current exporter:

disabled

Future cloud export must be:

- optional
- non-content by default
- failure-isolated from inference
- eventually asynchronous/batched/durable

Prompts, responses, documents, RAG contents and proprietary
payloads must not be exported by default.

---

## Model Catalog foundation

Current status:

WORKING FOUNDATION

The platform now distinguishes:

Catalog
- what models can be discovered/imported

Inventory
- what model artifacts are actually stored locally

Deployment
- what model services are currently loaded/running

Model discovery is provided through replaceable ModelSource
adapters.

Current ModelSource:

local_files

Next external ModelSource:

huggingface

Future examples:

- NVIDIA NGC
- ModelScope
- Ollama-compatible sources
- MLflow
- private enterprise registries
- internal artifact repositories

Every ModelSource must normalize provider-specific metadata into
the internal ModelMetadata schema.

Current normalized fields include:

- catalog ID
- model name
- family
- architecture
- parameter-count slot
- quantization
- context length
- source
- revision
- license
- download-size slot
- installed size
- weight format
- runtime compatibility slot
- hardware requirement slots
- compatibility result slot

Several values are currently intentionally None.

Do not guess missing metadata.

Compatibility evaluation remains a separate subsystem.

ModelSource discovers metadata.

CompatibilityEvaluator determines whether the detected host can
use the model.

CapacityPlanner determines whether it can safely be stored and
executed alongside existing workloads.

---

## Hugging Face ModelSource

Current status:

WORKING EXTERNAL CATALOG FOUNDATION

The Model Catalog now supports:

local_files
huggingface

Hugging Face discovery uses the public Hub API through the
ModelSource adapter boundary.

The platform core does not require the huggingface_hub SDK.

Optional environment credential:

HF_TOKEN

Future credential handling should use enterprise secret
management rather than application configuration files.

Current API examples:

/catalog/models?source=huggingface&search=qwen&limit=5

/catalog/models?source=local_files

/catalog/models?search=qwen

Hugging Face metadata is normalized into ModelMetadata.

Some metadata may remain None when the source does not provide
it in discovery results.

Do not guess missing values.

External ModelSource availability is not part of the core local
acceptance test because internet/provider outages must not make
the local AI platform unhealthy.

Future catalog improvements include:

- source-specific pagination
- caching
- private/gated repositories
- richer revision selection
- exact downloadable artifact sizing
- license-policy evaluation
- model detail endpoint
- download/import operations
- additional ModelSource adapters

---

## Model compatibility evaluator

Current status:

WORKING CONSERVATIVE FOUNDATION

Compatibility evaluation is separate from:

- ModelSource
- Model Inventory
- Capacity Planner
- Resource Manager
- runtime execution

Compatibility answers:

"Is this model a plausible candidate for this host?"

It does NOT answer:

"Can this model be started right now?"

Static compatibility uses total hardware capacity.

It deliberately does not use current free VRAM because free
VRAM changes when workloads are loaded.

Live resource availability belongs to Capacity Planner and
Resource Manager.

Current classifications:

- compatible
- conditionally_compatible
- unsupported

Current v1 inputs:

- weight format
- candidate runtime family
- detected operating system
- detected architecture
- accelerator vendor
- total VRAM
- total RAM
- known artifact size
- gated/private source state
- metadata completeness

Current v1 GPU sizing rule:

A known model artifact occupying <= 75% of the largest single
GPU's total VRAM may be classified as a static compatible
candidate when no other condition is unresolved.

This threshold is PROVISIONAL.

It is not a start/admission threshold.

Runtime overhead, KV cache, context, concurrency, reservations,
live usage, multiple GPUs and multiple running models belong to
the Capacity Planner / Resource Manager.

Unknown artifact size results in conditional compatibility,
rather than a guessed fit.

GGUF currently recommends the future llama.cpp runtime adapter
and remains conditional until that runtime exists.

Future evaluator improvements include:

- detailed architecture/runtime support matrices
- compute capability
- CUDA/ROCm/Metal versions
- quantization support
- exact model memory estimates
- multi-GPU execution
- CPU/GPU offload strategies
- conversion requirements
- source license/policy checks

---

## Model Inventory foundation

Current status:

WORKING READ-ONLY FOUNDATION

The platform now distinguishes:

Catalog
- models that may be discovered or obtained

Inventory
- model artifacts currently stored on this host

Deployment
- models selected, loaded and running through inference services

Current inventory is derived from:

- local model storage
- selected model plan
- normalized Platform State

Current states include:

artifact.state
- stored

deployment.load_state
- loaded
- unloaded

deployment.service_state
- running
- stopped

Current inventory fields include:

- inventory ID
- model ID
- local path
- disk usage
- weight formats
- architecture
- family
- quantization
- context length
- selected state
- loaded/unloaded state
- running/stopped state
- runtime
- executor
- health

Currently unavailable fields remain explicit None values:

- original external source revision
- true resource reservation
- active request count
- last-used timestamp

Do not infer or invent these values.

FUTURE:

Persistent inventory state should preserve:

- source provider/repository
- exact revision
- checksum
- download state/progress
- lifecycle timestamps
- update availability
- conversion/quantization lineage
- resource reservations
- last-used state

---

## Model download API

Current status:

WORKING FOUNDATION

Endpoint:

POST /inventory/models/download

Example request:

{
  "provider": "huggingface",
  "source_model_id": "organization/model",
  "revision": "main",
  "target_name": "local-model-name"
}

Responsibilities remain separated:

Platform API
- transport
- request validation
- HTTP response mapping

Control layer
- model-management use case

ModelTransfer
- transfer orchestration and staging

ModelTransfer adapter
- provider-specific implementation

Inventory
- persistent artifact ownership/source metadata

Deployment
- intentionally unchanged by download

Current download operations are synchronous.

This is PROVISIONAL.

Future Admin UI downloads should use durable asynchronous
operations/jobs with:

- operation IDs
- progress
- cancellation
- pause/resume where supported
- retries
- error history
- capacity checks before transfer

---

## Managed model update

Status:

WORKING FOUNDATION

Endpoint:

POST /inventory/models/update

Current MVP contract:

- platform-managed artifacts only
- Hugging Face sources only
- selected models are blocked
- running models are blocked
- loaded models are blocked
- replacement is downloaded to staging first
- exact resolved revision is persisted
- previous artifact is retained temporarily for rollback
- failed replacement restores the previous artifact

PROVISIONAL:

Update operations are synchronous.

FUTURE:

- asynchronous operations/jobs
- progress reporting
- cancellation
- resumable transfers
- upstream update detection
- verified checksums
- Capacity Planner preflight
- Resource Manager coordination


<!-- PHASE8_CAPACITY_PLANNER_V1_CLOSURE -->

## Phase 8 Capacity Planner v1 closure

Phase 8 intentionally closes at the functional-exoskeleton boundary.

### WORKING

- storage capacity and commit-admission foundation;
- canonical live capacity snapshot;
- normalized vendor-neutral resource pools;
- protected RAM and dedicated-VRAM headroom;
- explicit unified-memory fail-closed semantics;
- model artifact/resource-requirement envelope;
- thin integrated Inventory model feasibility;
- explainable compatibility/storage/memory dimensions;
- read-only Platform API feasibility boundary.

### PROVISIONAL

The Phase 8 candidate-memory estimator deliberately uses:

    local weight artifact bytes
        +
    max(25% of artifact bytes, 1 GiB)

This is LOW-confidence planning evidence only.

It is not an exact runtime RAM/VRAM prediction.

Current protected RAM and VRAM policy values are also working defaults
rather than finalized hardware-specific policy.

### DEFERRED REFINEMENTS

Refine only after the wider product exoskeleton exists:

- exact vLLM weight-residency evidence;
- vLLM startup/log runtime profiling;
- KV-cache prediction;
- activation-peak prediction;
- CUDA graph / non-framework overhead modeling;
- empirical runtime calibration;
- context-length-aware memory estimation;
- concurrency-aware memory estimation;
- benchmark-derived memory profiles;
- vLLM-specific candidate estimator;
- llama.cpp estimator;
- MLX estimator;
- ROCm estimator;
- Intel accelerator estimator;
- CPU/GPU offload planning;
- Apple unified-memory shared-backing accounting;
- AMD/Intel memory architecture accounting;
- multi-GPU topology;
- tensor/pipeline-parallel placement;
- quantization/conversion recommendations;
- remote catalog-model runtime feasibility before installation;
- concurrent placement;
- Resource Manager reservations;
- sophisticated scheduling and oversubscription policy.

Resource Manager reservations belong to Phase 9.

Any Step 35G runtime-evidence work discovered during closure is preserved
as deferred work and is not part of Capacity Planner v1 admission.

The Capacity Planner interface should remain stable while its estimators
and resource adapters improve later.

