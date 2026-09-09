# Phase 0 handoff — Local telemetry

**NEW_DATA_CHAT_REQUIRED**

Cursor could not open a separate project chat from the Stage 1.6L
runtime agent. Open a **new** Cursor chat, name it
`Data Engineering — Phase 0 Local Telemetry` (or
`Data Warehousing — Phase 0`), and point it at this worktree.

Do **not** continue this work in the Stage 1.6L runtime chat.

---

## Workspace

| | |
|---|---|
| Worktree | `/Users/usyd/Projects/ai-stack-data-warehouse` |
| Branch | `data/phase-0-local-telemetry` |
| Base / runtime calibration commit | `f13e6e9adacf40c86b7e713a098245f8805fafbd` |
| Stream A branch (do not develop here) | `stage/1.6L-real-vllm-inference` |
| Stream A worktree | `/Users/usyd/Projects/ai-stack` |
| Authoritative `kultrun` | `1e51f13ec2a7c2e1fa34b6a3ec0c92f712d4b43e` — do not merge yet |

Create the Cursor chat against `/Users/usyd/Projects/ai-stack-data-warehouse`.
Implement only in this worktree.

---

## What this chat must do

Implement **Data Warehousing Phase 0 — local structured metadata capture**.

This is a Kultrun **product infrastructure service**, not a side script.

```text
Kultrun control plane
        ↓
TelemetryRecorder port
        ↓
SQLiteTelemetryStore adapter
        ↓
<KULTRUN_STATE_ROOT>/telemetry/kultrun-telemetry.sqlite3
```

Phase 0 is the beginning of **Domain A** (customer-local operational +
future AI usage analytics). No vendor export. No licensing.

---

## What this chat must not do

- Do not begin Stage 1.6M.
- Do not edit Stream A runtime/domain semantics:
  discovery, compatibility, ModelRequirement, RuntimeMemoryProfile
  arithmetic, CurrentCapacitySnapshot, Available Models, ModelSelector,
  DeploymentPlan, ResourceManager, InferenceInstance, real vLLM, T3/T5.
- Do not implement PostgreSQL, cloud warehouse, vendor collector,
  uploader, heartbeat batching, consent UI, retention UI, data lake,
  Kafka, ClickHouse, Snowflake, BigQuery, dbt, Airflow, usage
  analytics dashboards, licensing DB.
- Do not copy any provisional/manual seed database into installations.
- Do not place the live SQLite file in git, under `src/`, in model
  storage, or beside source.
- Do not store prompts, responses, conversation text, documents,
  uploaded file contents, RAG documents/chunks/passages, customer
  source-code payloads, secrets, API keys, or raw HTTP bodies.
- Do not let SQLite types leak into runtime, resource, planning, or
  inference modules.
- Do not make telemetry a control-plane dependency. If a write fails,
  the domain fact remains valid; report the telemetry failure; never
  fake success.
- Do not recalculate capacity. Observe the existing snapshot.
- Do not re-collect hardware. Observe Host Discovery.
- Do not use `analytics.UsageEvent` as the Phase 0 operational store.
  `analytics` already owns later usage-event concepts; Phase 0 is
  append-only operational metadata behind a `telemetry` port.
- Do not implement integration (`acceptance/1.6L-with-telemetry`) or
  fresh GPU T3 in this chat.

Later phases (document only): 1 typed writer + timing, 2 content-free
usage/outcome, 3 sanitized exporter, 4 warehouse models, 5 cohort
intelligence.

---

## Authoritative Stream A facts to observe (do not own)

Base commit `f13e6e9` already has:

- `runtime.memory_profile@1` — `RuntimeMemoryProfile` in
  `src/kultrun/runtime/contracts.py`
- classing / sentinel / B−K / raise-only in
  `src/kultrun/runtime/memory.py`
- composition calibration in
  `src/kultrun/platform/runtime_memory.py`
- Available Models gated on resolved vLLM validation in
  `src/kultrun/platform/available_models.py`
- `DeploymentCapacity` / Available Models in planning contracts
- Host discovery → `HostCapabilities`
- Foundation / `RuntimeCapabilityProfile` / `RuntimeInstallation`
- `DeploymentPlan` + reservation + `InferenceInstance`

Operational `RuntimeMemoryProfile` remains authoritative for planning.
Telemetry stores an append-only copy. Never:

```text
SQLite → RuntimeMemoryCalibrationService
```

---

## Required layout

Prefer repository convention:

```text
src/kultrun/telemetry/
  contracts.py
  ports.py
  service.py
  migrations/001_initial.sql
src/kultrun/adapters/telemetry/sqlite.py
```

Default DB path, resolved through the existing state-root abstraction
(no second state-root concept):

```text
<KULTRUN_STATE_ROOT>/telemetry/kultrun-telemetry.sqlite3
```

Config: local telemetry enabled true/false only. Default enabled unless
an existing convention strongly forbids it. Optional path override for
tests. No cloud endpoint, API key, upload frequency, or credentials.

---

## Schema (Phase 0 only)

`schema_migrations` plus:

- `host_observation`
- `runtime_observation`
- `capacity_snapshot`
- `model_sizing_observation`
- `runtime_memory_profile`
- `deployment_run`
- `deployment_event`

No dozens of empty future tables. Store memory as integer bytes, never
formatted `"10.4 GiB"`. Preserve FACTUAL / ESTIMATED / MEASURED /
DERIVED / CALIBRATED as distinct columns. Append-only: later runs must
not overwrite earlier failures.

Migrations from day one: deterministic, idempotent startup, record
version only after success, never rewrite released migration files.

---

## Port

Small typed `TelemetryRecorder` (or repository-consistent name):

```text
record_host_observation
record_runtime_observation
record_capacity_snapshot
record_model_sizing
record_runtime_memory_profile
start_deployment_run
record_deployment_event
finish_deployment_run
```

No generic event bus. Wire from composition (`src/kultrun/main.py`) so
existing workflows emit observations. Telemetry failure must not break
deployment.

Distinguish runtime-memory **probes** from actual **deployments**.

Capture natural stage durations only at existing boundaries (host
discovery, foundation, provision, verify, model discovery, sizing,
memory probe, acquire, admit, launch→ready, overall deploy).

CLI: `kultrun telemetry status` — enabled, path, schema version, row
counts. No SQL console. No dashboard.

---

## Tests and local acceptance

Minimum: DB creation under a temp state root; migration 001 once and
idempotent reopen; append two sizing rows for one model; privacy
(DTOs have no prompt/response/document/RAG fields); host / runtime /
capacity / sizing / runtime-memory / deployment inserts; simulated
SQLite failure leaves the domain operation valid.

Runtime-memory fixture must persist the accepted T3 failure shape:

```text
static estimate ≈ 10.37 GiB
model load ≈ 9.38 GiB
available KV ≈ −2.38 GiB
derived non-KV ≈ 12.75 GiB
calibrated requirement > 10.37 GiB
failure/unusable-for-serving state
```

After a local product/fixture flow, **query SQLite and print actual
rows**. Do not report only “tests passed”.

Run focused tests, full pytest, ruff, mypy src+tools, packaging.

---

## Documentation this chat should write

Under `docs/data/warehouse/` (keep separate from Stage 1.6L docs):

- `README.md`
- `PHASE-0-LOCAL-TELEMETRY.md`
- `DATA-DOMAINS.md` (A local ops/usage, B vendor telemetry, C licensing;
  future infra/runtime/model/deployment/usage/outcome/org/governance/
  vendor/licensing — document only)
- this file (`PHASE-0-HANDOFF.md`)

Document future: local SQLite → sanitized exporter → vendor ingestion →
PostgreSQL. Do not implement it.

Runtime docs may later link here. Do not rewrite Stage 1.6L.

---

## Governing product docs (read, do not relocate)

- `docs/PRODUCT_VISION.md`
- `docs/ARCHITECTURE.md` — core owns concepts; adapters own
  implementations; `analytics` already exists for later usage events
- `docs/ROADMAP.md` — do not begin 1.6M; do not merge to `kultrun`
- `docs/DEVELOPMENT_WORKFLOW.md` — bounded-step PASTE BACK
- `docs/DEBT.md`

Python: `.venv/bin/python`. Commit/push only when asked, except the
user instruction that created this stream already authorized Phase 0
implementation in **this** data chat.

Do not commit to `main`, `phase9`, or `backup/*`.

---

## Integration and T3 (not this chat)

After Stream A and Stream B are independently clean and pushed, a
**later** step creates temporary `acceptance/1.6L-with-telemetry` in
`../ai-stack-acceptance`. Fixes go back to the owning stream. Fresh
GPU T3/T5 uses the clean **integration** wheel, not the WIP wheel
`c4fdd71d...` and not Stream A alone unless a later instruction says
otherwise.

Merge order later: close/merge 1.6L first; rebase data onto new
`kultrun`; do not squash runtime and warehouse into one commit.

---

## Required return format

Use exactly the DATA STREAM PASTE BACK block from the consolidated
instruction (Part 44). Then STOP. Do not start integration or T3.
