# Three data domains

Kultrun keeps these domains separate from the first database.

## Domain A — customer-local operational and AI-usage analytics

Belongs primarily to the customer. Lives on the installation.

Phase 0 implements only the beginning of this domain: structured
operational metadata in local SQLite. Later Domain A work may add
content-free usage and outcome events (`analytics.UsageEvent` at
Stage 1.7). That is not this phase.

## Domain B — vendor product telemetry

Used to understand how the product is used. Optional. Off by default
for air-gapped installations.

Phase 0 does not implement Domain B. Later, selected Domain A metadata
may be transformed into sanitized Domain B export. The local database
and a future vendor warehouse are not the same database.

## Domain C — vendor licensing / entitlement data

Commercial authorization. Completely out of scope for Phase 0.

These domains may later share transport. They remain logically separate.

## Future warehouse domains (document only)

Do not create empty production tables for these now:

| Domain | Later contents |
|---|---|
| infra | host, driver, component, storage planning facts |
| runtime | foundation, installation, verification history |
| model | catalog, sizing, calibration, artifact lineage |
| deployment | plans, reservations, instances, lifecycle timing |
| usage | content-free request metrics |
| outcome | explicit rating, accept/reject, task success |
| organisation / cohort | pseudonymous org, industry, size band, region |
| governance | policy, approval, audit joins |
| vendor telemetry | sanitized Domain B batches |
| licensing | entitlement records |

## Future customer / usage metadata (document only)

When real users exist, Domain A may collect metadata such as:

- pseudonymous organisation, industry, size band, region
- pseudonymous team / application / user
- business function, user-role taxonomy, task class
- model, version, runtime, hardware, context, configuration
- input tokens, output tokens, request count
- latency, TTFT, throughput
- errors, retries, regenerations, fallbacks, model switches
- resource use, cost
- explicit rating, accept/reject, task success

No prompt or response content by default.

## Future warehouse direction (document only)

```text
Local SQLite
      ↓
future sanitized exporter
      ↓
vendor ingestion
      ↓
PostgreSQL / analytical store
      ↓
warehouse / data marts
```

Not implemented in Phase 0. No PostgreSQL, cloud collector, uploader,
heartbeat batching, consent UI, retention UI, data lake, Kafka,
ClickHouse, Snowflake, BigQuery, dbt, or Airflow.
