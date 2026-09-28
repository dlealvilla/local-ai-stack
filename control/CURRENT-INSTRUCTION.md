# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-ANALYTICS-HUB-V0.2-FIX-001`
Status: `AUTHORIZED_CORRECTION`
Predecessor instruction: `RUKAN-ANALYTICS-HUB-V0.2-001`
Correction starting source: `404858abde45443d91f9a6f17b301754cc8b4276`
Branch: `rukan/analytics-hub-v0.2`

The v0.2 implementation is close but is NOT yet accepted.

Do not expand scope. Fix the following provenance/history defects, add regression tests, rerun the complete v0.2 QA gates, publish paste-back, and STOP.

## 1. Bundle installation identity must fail closed

Current problem:

`AnalyticsBundle._check_counts` verifies snapshot install ids against the manifest, but does not verify `AnalyticsEvent.install_id` or `AnalyticsInference.install_id`.

The Command Center importer then stores event/inference rows under `bundle.manifest.install_id`, silently overriding the record's own claimed installation identity.

This can misattribute an untrusted/malformed record to the wrong deployment.

Required behavior:

- every support snapshot in a bundle must belong to the manifest install id;
- every analytics event in a bundle must have the same install id as the manifest;
- every analytics inference in a bundle must have the same install id as the manifest;
- any mismatch fails the whole bundle before SQLite mutation;
- importer must never silently replace a source record's installation identity with the manifest identity as a way to make a malformed bundle fit.

Keep generated Rukan bundles unchanged when valid.

Add negative tests for mismatched event install id and mismatched inference install id. Prove transaction rollback and no partial rows.

## 2. Snapshot count must remain truthful when older history arrives later

Current problem:

`_apply_snapshot` recomputes the number of stored snapshots, but the deployments UPSERT updates `snapshot_count` only when the imported snapshot is at least as new as `latest_exported_at`.

If an older previously unseen snapshot arrives after a newer snapshot:
- snapshot history correctly gains a row;
- latest deployment metadata should stay on the newer snapshot;
- but `deployments.snapshot_count` remains stale.

Required behavior:

- latest deployment metadata must continue to reflect the newest `exported_at`;
- snapshot_count must reflect the actual number of retained snapshots regardless of import order;
- importing older history must not regress latest version/model/Witness/etc.;
- importing snapshots in arbitrary order must converge to the same database state.

Prefer separating "latest projection update" from "history count update" rather than weakening the latest timestamp guard.

Add tests:
- newer then older;
- older then newer;
- three snapshots shuffled;
- snapshot_count is correct;
- latest metadata is always from the newest snapshot.

## 3. Remove + Refresh must be recoverable

Current problem:

`CommandHub.remove(install_id)` deletes snapshots/events/inferences/deployment rows but leaves the source hash records in `sources`.

If the source files remain in the inbox, Refresh sees their hashes as already imported and skips them, so the removed deployment cannot be reconstructed from the files the operator still has.

Required product behavior:

"Remove local copy" removes the Command Center's imported local database representation. If supported source files for that deployment remain in the inbox, a later Refresh must be able to ingest them again.

Fix provenance/schema as needed.

The source/import table should retain enough source identity to associate an imported source with its installation and preferably logical bundle/snapshot identity, not only content hash.

Because v0.2 has not been accepted/promoted yet, it is acceptable to correct the initial schema before canonical release. Preserve explicit schema version handling and tests.

Required tests:
- import bundle -> remove deployment -> Refresh same unchanged file -> deployment returns;
- same for a standalone support snapshot;
- removing deployment A must not make deployment B's sources eligible or delete B data;
- normal Refresh without Remove remains idempotent;
- source files are never deleted by Remove.

## 4. Logical duplicate provenance

While correcting `sources`, inspect whether the same logical bundle/snapshot with different byte serialization can create duplicate source-provenance rows.

Use the smallest robust identity:
- content hash for exact file idempotency;
- stable bundle id or snapshot id where available for logical idempotency.

Do not over-engineer a generic ingestion framework.

Facts remain deduplicated by their existing stable ids.

## 5. Preserve all accepted v0.2 behavior

Do not change:
- loopback-only Command Center;
- SQLite durable authority;
- inbox + Refresh model;
- JSON/JSONL canonical interchange;
- manual/external transport only;
- Rukan Admin Analytics;
- privacy allow-list;
- no raw logs;
- no prompts/responses/documents;
- no live/online/healthy claims;
- no invented future metrics;
- no remote fleet/auth/licensing/Knowledge/Registry/Dynamo/LibreChat/physical work.

## 6. QA

Run all prior v0.2 gates plus the new correction tests.

At minimum:
- bundle count validation;
- snapshot install mismatch;
- event install mismatch;
- inference install mismatch;
- transaction rollback on identity mismatch;
- shuffled snapshot history convergence;
- remove/reimport bundle;
- remove/reimport snapshot;
- multi-deployment removal isolation;
- exact-file refresh idempotency;
- logical source idempotency if implemented;
- persistence/restart;
- privacy negative tests;
- full tests/machi;
- tests/acceptance_lab;
- ruff;
- mypy strict;
- Admin tests/typecheck/build;
- Command Center tests/typecheck/build;
- wheel build + isolated verify if Python changes.

## 7. Terminal status

Only return:

`RUKAN_ANALYTICS_HUB_V0_2_LOCAL_PASS`

when these corrections pass and the branch is clean/pushed.

Paste back:
- exact status;
- final SHA;
- fixes for all three defects;
- schema/provenance changes;
- added tests;
- full QA/build evidence;
- remaining limitations;
- git state.

Then STOP.

# END INSTRUCTION
