# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-ANALYTICS-HUB-V0.2-001`
Status: `AUTHORIZED_IMPLEMENTATION`
Canonical baseline: `machi` at `c649103f244475f6381ba473f4431e0a7f86f803`
Predecessor: `RUKAN-DUAL-UI-V0.1-001` / `add9ac3f5acb2d9f4bc335dedc49a274df4d4193`

Build the next bounded Rukan product increment: turn Command Center into a persistent local business data hub and add a small local Analytics page to Rukan Admin.

No physical server is required.

## Product outcome

### Rukan Command Center
Run as a long-lived local service on the business operator PC.

It must:
- own a persistent local datastore;
- own an inbox/import directory;
- serve the Command Center UI;
- expose a **Refresh deployments** action;
- scan all supported files in the inbox;
- validate and import only new valid records idempotently;
- retain deployment/snapshot/event history across browser and service restarts;
- aggregate data across multiple deployments;
- remain non-authoritative for customer-host truth.

The browser must no longer be the durable data authority.

### Rukan Admin
Add a small **Analytics** page over the deployment's own local journal/store using only active truth-backed Rukan facts.

## Data principles

Preserve the existing separation:
1. operational state = authoritative current contracts;
2. EventRecord journal = append-only record of what happened;
3. metrics = derived/rebuildable projections;
4. logs = debugging, not analytics.

Keep three data domains distinct:
- customer-local operational/usage analytics;
- business/vendor product telemetry + support analytics;
- future licensing/entitlement data.

Do not mix licensing into this work.

## Canonical interchange

Do not use CSV as the canonical Rukan-to-Command-Center format.

Use versioned JSON/JSONL because it preserves typed identities, timestamps, schemas, unresolved values, privacy classes and provenance.

CSV may be added later as a human convenience adapter only.

Keep `rukan.support_snapshot` as a compact point-in-time support summary. Do not overload it into the complete analytics feed.

Add a separate versioned analytics export, preferably one transportable JSONL file such as:

`rukan.analytics_bundle.v1.jsonl`

The bundle should have a manifest record with:
- bundle schema/version;
- bundle id;
- install id;
- exported_at;
- Rukan version/build/commit when known;
- included dataset kinds and counts;
- export/privacy policy version.

Subsequent typed records may include only supported active Rukan facts.

## Export what actually exists now

At minimum evaluate/include:

### Support snapshot
The existing `rukan.support_snapshot`.

### Event timeline
Exportable EventRecord facts from the current journal.

Business export rules:
- customer_content: NEVER;
- restricted: default exclude;
- public_ops: eligible;
- operational: eligible only through explicit allow-list projection.

Do not blindly export arbitrary payloads.

Useful event projection fields include event id/type, timestamps, install/run/host identities where permitted, block/component, outcome, privacy and specifically allow-listed safe payload fields.

### Inference facts
Active `InferenceProof` contains useful non-content facts:
- proof id;
- instance/plan/fingerprint/reservation/generation/artifact ids;
- request kind;
- status code;
- completion tokens when reported;
- structural validity;
- typed failure.

Export a bounded projection of those facts. Never prompt or response text.

### Other active facts
Include additional non-content analytics-ready facts only when current Rukan contracts already define stable meaning and they add value.

Avoid redundant duplication when support snapshot + events already carry the information.

## Do not invent future metrics

The telemetry architecture reserves richer measures, but active Rukan does not yet persist all of them.

Do not synthesize or claim, unless repository truth proves they now exist:
- input tokens;
- TTFT;
- queue time;
- cost;
- user/team/application usage;
- requested vs actual routed model;
- route reason;
- utilization percentages;
- SLA/availability;
- historical latency.

The Admin inference seam's current elapsed time is not historical fleet telemetry.

Return a gap table:
`DESIGNED FUTURE METRIC -> ACTIVE RUKAN SOURCE MISSING`.

Do not import the old Kultrun UsageEvent wholesale without a separate product decision.

## Deployment-side export

Add a Rukan-owned read-only analytics export command/service using the internal machi namespace as needed.

Conceptually:

`rukan analytics export --output ...`

It must:
- read persisted Rukan state/journal/proofs;
- not mutate operational state;
- write one versioned export bundle;
- require no network;
- fail closed on prohibited content;
- report included/skipped counts;
- never export prompts/responses/documents/secrets/paths/raw logs.

## Command Center local service

Replace browser localStorage as durable authority.

Preferred implementation:
- Python;
- loopback only;
- SQLite via stdlib;
- static Command Center assets served locally for product use;
- Vite remains development tooling.

Add a command equivalent to:

`machi command-center serve --data-dir <dir> --port <port>`

Use an owned data root containing at least:
- SQLite database;
- inbox directory;
- optional bounded rejected/import metadata.

Do not delete arbitrary source files.

Design it as a long-running local service. If no existing cross-platform service manager exists, do not invent OS startup registration in this bundle; document boot/login autostart as later installer integration.

## Inbox + Refresh

The UI must have a clear **Refresh deployments** button.

Refresh must:
1. scan the inbox;
2. identify supported Rukan snapshot/bundle files;
3. content-hash or otherwise stably identify each source;
4. validate schema/version;
5. enforce privacy/export restrictions;
6. validate bundle identity/count consistency;
7. import transactionally;
8. deduplicate stable source records;
9. retain provenance;
10. update all views.

Scanning the same bundle twice must not duplicate data.

Newer bundles for the same installation append history.

Malformed files must not block valid files. Show rejected count/reason.

Automatic scan on service startup is encouraged. Background polling is not required.

## SQLite model

Keep it small, versioned and migratable.

Represent concepts equivalent to:
- deployments/installations;
- imported source files/bundles;
- support snapshots;
- event envelopes;
- inference facts;
- rejected/import-error evidence.

Preserve Rukan source identities. Do not collapse install id, install-run id, host id, model identity, plan, reservation, instance or proof into one ambiguous id.

Use transactions and schema versioning.

## Command Center UI

Keep the existing screens, now backed by the local service/database.

Header:
- service status;
- last refresh;
- latest imported/rejected counts;
- Refresh deployments.

Deployments:
- search/sort/history;
- snapshot count;
- evidence exported time;
- simple truthful aggregate counts/distributions for known deployments, versions, macropaths, Witness outcomes and accelerator models.

Never show online/offline/healthy from imported files.

Deployment detail:
- Summary;
- Timeline;
- Inference analytics;
- Snapshots;
- Support evidence.

Timeline:
- imported EventRecord projections;
- useful filtering by event type/outcome/block.

Inference analytics:
- total persisted proof/request facts;
- completed/failed facts;
- reported completion-token totals/averages only when available;
- status/failure distribution;
- model/artifact identity where supported.

Clearly label unrecorded metrics.

Add a simple cross-deployment Analytics section for imported truth-backed facts such as:
- Rukan version;
- OS/architecture;
- accelerator;
- macropath/runtime;
- model identities;
- Witness outcomes;
- event failures;
- inference success/failure;
- reported completion tokens.

No decorative fake KPI cards.

## Rukan Admin local Analytics

Add an Analytics page powered directly by local Rukan records.

Minimum truth-backed views:
- event counts by outcome;
- recent/event timeline;
- lifecycle event counts;
- inference proof count;
- successful/failed inference facts;
- reported completion-token total where available;
- current runtime/model context;
- explicit missing-data labels.

Local Admin may see locally permitted data that is not vendor-exportable. Do not loosen export privacy because Admin can see it.

## Privacy hard gate

Never export:
- prompts;
- generated responses;
- messages;
- documents;
- RAG context;
- proprietary file contents;
- credentials/secrets;
- absolute paths;
- arbitrary raw logs;
- customer_content records;
- restricted records unless a future explicit projection authorizes them.

Use allow-list projection, not denylist-only sanitization.

Add negative privacy tests.

## Transport limitation

There is no automatic customer-to-business transport yet.

v0.2 truth is:

Deployment
-> analytics export bundle
-> manual/external file transfer
-> Command Center inbox
-> Refresh

Do not claim sync, heartbeat or fleet connectivity.

## Migration

Current v0.1 browser snapshot workflow must remain usable.

At minimum:
- manual existing support snapshot JSON files can be placed in the inbox;
- they import into the new service/database;
- browser localStorage is no longer durable authority.

Do not attempt to scrape arbitrary browser profiles.

## QA

Run:
- full tests/machi;
- tests/acceptance_lab;
- bundle serialization/readback;
- privacy allow-list and prohibited-content cases;
- idempotent refresh;
- duplicate bundle;
- mixed valid/invalid inbox;
- transaction rollback;
- SQLite schema/migration;
- service restart persistence;
- multiple deployments and multiple bundles per deployment;
- timeline and inference aggregation;
- Admin local analytics;
- architecture tests;
- ruff;
- mypy strict;
- both frontend test/typecheck/build suites;
- wheel build and isolated verify if Python changes.

No physical testing.

## Non-goals

Do not build:
- automatic deployment-to-vendor transport;
- cloud Command Center;
- remote control;
- online/offline heartbeat;
- auth/tenancy;
- licensing/billing;
- Knowledge/RAG;
- agents/Team Brain;
- Dynamo;
- Runtime Artifact Registry;
- LibreChat/Open WebUI;
- raw log shipping;
- Postgres/Kafka/data lake;
- Parquet unless a concrete need emerges;
- CSV as canonical format;
- new usage ontology;
- RunPod tests.

## Acceptance

Pass only if:
- v0.1 behavior remains intact;
- Command Center has a persistent local service + SQLite store;
- inbox + Refresh works in one action;
- refresh is idempotent;
- existing support snapshots import;
- versioned analytics bundles import;
- implemented safe active Rukan analytics are captured;
- timelines and inference analytics work;
- aggregate analytics are truth-backed;
- Rukan Admin has local Analytics;
- privacy tests pass;
- transport remains explicitly manual/external;
- full QA/build pass;
- pushed branch clean.

Use branch:

`rukan/analytics-hub-v0.2`

Terminal success:

`RUKAN_ANALYTICS_HUB_V0_2_LOCAL_PASS`

Paste back exact status, SHAs, architecture, SQLite schema, inbox/refresh behavior, bundle contract, exported record types, privacy rules, analytics views, future-metric gaps, tests/builds, limitations, next recommendation, git state, then STOP.

# END INSTRUCTION