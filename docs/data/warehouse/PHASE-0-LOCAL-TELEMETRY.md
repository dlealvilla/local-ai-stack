# Phase 0 — Minimum Viable Local Telemetry

Status: implemented on `data/phase-0-local-telemetry`.
Base: Stage 1.6L runtime-calibration commit `f13e6e9`.
Integration acceptance remains pending. This stream is not merged into
`kultrun` and does not claim Stage 1.6L accepted.

## Product position

Local telemetry is Kultrun product infrastructure. It observes control-plane
outputs and records them. It does not decide whether a deployment is valid.

Default path, resolved from the existing state-root abstraction:

```text
<KULTRUN_STATE_ROOT>/telemetry/kultrun-telemetry.sqlite3
```

The live file is mutable application state. It is not in git, not under
`src/`, and not beside model weights.

## Privacy

Metadata only. Never stored:

- prompts, responses, conversation text
- documents, uploaded file contents
- RAG documents, chunks, retrieved passages
- customer source-code payloads
- secrets, API keys
- raw HTTP request or response bodies

## Schema

Additive, versioned migrations from v1. Historical rows survive reopen.
Released migration files are never rewritten.

Tables:

- `schema_migrations`
- `host_observation`
- `runtime_observation`
- `capacity_snapshot`
- `model_sizing_observation`
- `runtime_memory_profile`
- `deployment_run`
- `deployment_event`

Memory values are integer bytes. Provenance stays in distinct columns:

`factual_` / `estimated_` / `measured_` / `derived_` / `calibrated_`

Append-only: a later successful run does not overwrite an earlier failure.
`finish_deployment_run` completes the same run row; it does not replace
other runs.

## Ownership

```text
RuntimeMemoryCalibrationService
        ↓
authoritative operational RuntimeMemoryProfile
        ↓
telemetry observation / copy
```

SQLite never feeds calibration, ResourceManager, ModelSelector,
DeploymentPlan, or InferenceInstance.

Telemetry failure is visible and is never reported as success. The domain
fact remains valid.

## Configuration

```text
[telemetry]
enabled = true
# database_path unset → <state_root>/telemetry/kultrun-telemetry.sqlite3
```

Environment overrides for tests and operators:

- `KULTRUN_TELEMETRY_ENABLED`
- `KULTRUN_TELEMETRY_DATABASE`

No cloud endpoint, API key, upload frequency, or warehouse credentials.

## CLI

```text
kultrun telemetry status
```

Shows enabled, database path, schema version, and row counts.

## Later phases (do not begin)

1. Typed event writer + more automatic timing
2. Content-free usage / outcome telemetry
3. Sanitized exporter + hosted ingestion
4. Warehouse models / historical analytics
5. Model-effectiveness / cohort intelligence
