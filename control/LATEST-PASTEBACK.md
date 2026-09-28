# RUKAN-ANALYTICS-HUB-V0.2-001

## EXACT STATUS

RUKAN_ANALYTICS_HUB_V0_2_LOCAL_PASS

## TL;DR

Command Center is now a loopback service with SQLite as the durable store and an inbox scanned by Refresh deployments. Rukan Admin has a local Analytics page over this deployment's journal and proofs. The vendor interchange is versioned JSONL, not CSV. Nothing is labelled live. No physical host was created.

## SHAS

- Canonical baseline: `c649103f244475f6381ba473f4431e0a7f86f803`
- Final SHA: `404858abde45443d91f9a6f17b301754cc8b4276`
- Branch: `rukan/analytics-hub-v0.2`
- Origin: `origin/rukan/analytics-hub-v0.2` equals that SHA
- `origin/machi` was not moved and remains `c649103f244475f6381ba473f4431e0a7f86f803`

## ARCHITECTURE

Customer-local analytics and the vendor export stay separate. Admin `GET /v1/analytics` reads the deployment journal and inference proofs. `machi analytics export` writes one allow-listed JSONL bundle and does not mutate operational state. Command Center imports that bundle, or an existing support snapshot JSON file, from its inbox into SQLite. The browser is a client. Transport is still manual: export, copy the file into the inbox, Refresh deployments.

## SQLITE SCHEMA

Schema version `1` in `command.sqlite`. Tables: `meta`, `sources` (content hash), `rejections`, `deployments`, `snapshots`, `events`, `inferences`. A newer unknown schema version fails closed. There is no upgrade path yet because this is the first version.

## INBOX / REFRESH

`machi command-center serve --data-dir <dir> --port 8780` creates `<dir>/inbox` and scans it on startup and on `POST /v1/refresh`. Supported files are `*.json` support snapshots and `*.jsonl` analytics bundles. Each file is hashed. A known hash is skipped. A valid file imports in one transaction. A malformed file is recorded by basename and reason and does not block other files. Source files are not deleted. The same bundle twice does not duplicate rows. A second snapshot for the same install appends history. Removing a deployment deletes the local rows only.

## BUNDLE CONTRACT

`rukan.analytics_bundle` version 1. First JSONL record is `kernel.analytics_manifest` with bundle id, install id, exported_at, version, build, commit, privacy policy `rukan.analytics.export.1`, and snapshot/event/inference counts. Counts must match the following records.

## EXPORTED RECORD TYPES

- `kernel.support_snapshot` point-in-time summary
- `kernel.analytics_event` envelope: event id, type, time, install, block, component, outcome, privacy. No payload
- `kernel.analytics_inference`: proof id, instance, plan, reservation, generation, model identity and kind, request kind, status code when the proof has one, completion tokens when reported otherwise `not_recorded`, structural validity, typed failure, proven or failed

## PRIVACY RULES

Export allow-list is `public_ops` and `operational` only. `restricted` and `customer_content` are not exported. Admin local analytics may show restricted envelopes without payloads and counts omitted customer-content events without their bodies. Prohibited keys, including prompt and response, fail the bundle closed. Absolute paths are not stored in rejection rows; the file name is.

## ANALYTICS VIEWS

Command Center: deployment inventory, versions, OS/architecture, accelerators, macropath, models, Witness, event failures by type, inference proven/failed, reported completion-token sums, snapshot history, and support envelopes. Admin Analytics: events by outcome, recent timeline, lifecycle counts, proof count, proven/failed, reported completion tokens, and an explicit missing-data list. Neither surface says live, online, offline, healthy, or last-seen.

## FUTURE-METRIC GAPS

| Designed metric | Active source |
|---|---|
| input tokens | not on the native inference proof; not invented |
| TTFT | not exported as request telemetry |
| queue time | not persisted |
| historical request latency | not persisted; tester elapsed time is not history |
| cost | not persisted |
| user/team/application usage | not persisted |
| routing reason | not persisted |
| utilization | not persisted |
| SLA/availability | not persisted |

## TESTS / BUILDS

- `tests/machi`: pass, including architecture, privacy, idempotent refresh, mixed inbox, schema version, and restart
- `tests/acceptance_lab`: pass, collected separately from `tests/machi`
- ruff: pass
- mypy --strict `src/machi`: pass, 189 files
- Admin vitest 4 passed; Command Center vitest 5 passed
- both production Vite builds passed
- Wheel `machi-0.1.0-py3-none-any.whl`, build `0.1.0+404858abde45`, clean, SHA256 `61d7b486c8f2978ef143f0d9cf2a63aa1d8829d4e62efb71dff671ff8129422a`, size 363049, isolated `verify_ok`

## LIMITATIONS

No automatic copy from a customer deployment to the vendor PC. No OS autostart. Command Center dev UI proxies to port 8780. CSV is not a format. Raw logs are not shipped.

## NEXT RECOMMENDATION

Keep the manual inbox. The next useful step is a documented operator copy path, still not a live fleet connection, and only after Lead review.

## GIT STATE

- `rukan/analytics-hub-v0.2` equals origin at `404858abde45443d91f9a6f17b301754cc8b4276`
- `origin/machi` remains `c649103f244475f6381ba473f4431e0a7f86f803`
- Working tree clean except untracked `docs/machi/proposals/`

## STOP

STOP. Waiting for Lead review. Remote fleet, authentication, licensing, Knowledge, the Runtime Artifact Registry, Dynamo, LibreChat, and physical testing were not started.
