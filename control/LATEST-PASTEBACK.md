================================================================================
=========================== PASTE BACK START ===================================
================================================================================

TASK: RUKAN-CONNECTED-MONITORING-V0.3-001
STATE: PASS
MILESTONE: Rukan connected monitoring v0.3
STAGE: local one-way operational reporting
STEP: usage, outbox, machine auth, intake, Admin and Command Center surfaces
PREDECESSOR OUTPUTS: d38a8e855f099f353e1ac090b990014eed67a826 on machi
CURRENT_COMMIT: 0e87b9cd80e52f2a0c0d528f41076b33f4c1ddf4

STATUS: RUKAN_CONNECTED_MONITORING_V0_3_LOCAL_PASS_EXTERNAL_ENDPOINT_REQUIRED

A. Terminal status: RUKAN_CONNECTED_MONITORING_V0_3_LOCAL_PASS_EXTERNAL_ENDPOINT_REQUIRED
B. TL;DR: Local connected monitoring is implemented and tested, including loopback HTTPS. No owned public endpoint, certificate, or domain was present, so this is not an Internet PASS.
C. Starting SHA d38a8e855f099f353e1ac090b990014eed67a826. Final SHA 0e87b9cd80e52f2a0c0d528f41076b33f4c1ddf4.
D. Branch rukan/connected-monitoring-v0.3. Worktree clean except untracked docs/machi/proposals/. origin/rukan/connected-monitoring-v0.3 is 0e87b9c. origin/machi remains d38a8e8.

CHANGES:

* kernel.inference_usage and kernel.operational_report are new Kernel contracts. InferenceProof is unchanged.
* Admin records non-content usage, composes reports, and retries a SQLite outbox from a daemon thread.
* Command Center schema 3 stores credentials, reports, rollups, gaps, and aliases. Intake is a separate write-only server.
* Admin and Command Center navigation and production assets were rebuilt around the real APIs.

E. Architecture review and deviations, recorded in docs/machi/RUKAN-CONNECTED-MONITORING-V0.3.md:
* Bearer token over TLS, not HMAC. The secret is the credential; HMAC does not change the threat model once TLS is mandatory.
* The agent is a thread in the Admin process, not a new daemon.
* Usage is rukan-telemetry.sqlite, not an EventRecord payload.
* Vendor reports send rollups plus cumulative counters, not raw request rows.
* Context, concurrency, placement, and reserve stay read-only. No Plan recompute mutation exists. Debt R-03-01.
* Family is shown only from stored catalog family. No marketing parser. No Recommended row.
* Actor origin is recorded for new monitoring actions only.
* Missed six-hour windows are not backfilled. Cumulative counters and sequence gaps show the miss.
* Reporting disabled pauses compose and send. Send test report is explicit.

F. Product vision: customer content stays local. Command Center is a portfolio of reports, not host authority. A report is not online, offline, or healthy.

G. Telemetry agent: TelemetryAgent in the Admin process. Browser does not schedule.

H. Six-hour scheduler: cadence_hours default 6, allowed 1..24. Jitter is sha256(install_id) mod 900 seconds, stable per deployment.

I. Event triggers: serve.ready/stopped/failed, admit.released/rejected/reconciliation_detected, plan.created/stale, foundation.selected, model.selected/acquisition/qualification, capacity.safe_envelope.derived, witness contradictory/failed. Coalesce 45 seconds. Failure and admission rejection flush immediately. Send stays off the request path.

J. Settings triggers: telemetry enablement, endpoint, cadence, credential configure, and observed macropath, model, version, or SAFE-byte changes. UI theme and aliases do not trigger a deployment report.

K. Outbox: canonical JSON is stored before send. Ack marks delivered and records last_acked. Failure keeps the row, backoff 30s doubling to 1 hour. Cap 24 queued reports. Restart reads the same sqlite file.

L. Report contract: kernel.operational_report version 1, schema rukan.operational_report, privacy rukan.telemetry.export.1. Max 512000 bytes, 64 events, 32 rollups, 16 triggers.

M. Credential: tkey_ id plus token_urlsafe secret, shown once. Receiver stores sha256 only. Bound to one install_id. Rotate revokes the old key.

N. TLS: non-loopback without a certificate fails closed. Loopback plaintext requires --local-test. Python ssl with operator cert/key. No reverse proxy in the ontology.

O. Usage record: kernel.inference_usage version 1. Purposes operator_test, acceptance_probe, user_request. Admin tester cannot label user_request.

P. Native tokens: OpenAI usage.prompt_tokens and usage.completion_tokens when present.

Q. Ollama tokens: prompt_eval_count and eval_count when present. total_duration is runtime duration, not Rukan latency.

R. Latency: wall clock at the Admin completion boundary, milliseconds. Not TTFT.

S. Aggregation: requests, success, failure, token sums and sample counts, latency sum/count/min/max and average. No percentile.

T. Admin navigation: Overview, Models, Deployment, Inference, Analytics, Activity, System, Settings.

U. Overview: readiness sentence, active model, 24h usage, SAFE capacity, monitoring queue, recent activity. No numeric health score.

V. Models: exact artifact or digest cards. Family only when stored. Running/Installed/Compatible/Available from real state. Recommended omitted.

W. Analytics: 24h, 7d, 30d, all, plus the existing operational-event view.

X. Activity: timestamp, action, outcome, actor origin, subject. No secrets or paths.

Y. Settings: reporting, endpoint, key id, secret entry, cadence, categories, exclusions, preview, send test. Deployment controls read-only.

Z. Command Center navigation: Overview, Deployments, Detail, Analytics, Models, Reporting, Settings, Import.

AA. Overview counts known deployments, reports, cadence freshness, and rejected reports. Wording stays report-centric.

AB. Deployments show last report, report age, and cadence label. Detail includes report history and support evidence.

AC. Existing deployment analytics remain. Usage rollups feed the landscape.

AD. Model landscape cards use reported model identity, deployment count, requests, tokens, and failures.

AE. Reporting shows accepted, rejected, gaps, key ids, and rejection reasons. No secrets.

AF. Issue, rotate, and revoke from the loopback settings API and the credential CLI. Secret prints once.

AG. Privacy: prohibited content keys fail the report. Credential file mode 0600. Rejected bodies are not stored. Intake has no read or control routes.

AH. Local acceptance: tests/machi/test_rukan_monitoring.py covers parsers, purpose split, coalesce, outbox retry and restart, good/bad/revoked credentials, install mismatch, idempotency, sequence gap, privacy rejection, plaintext refusal, explicit loopback HTTP, and a temporary OpenSSL HTTPS listener on 127.0.0.1. Production Admin was exercised at http://127.0.0.1:8766/ and Command Center at http://127.0.0.1:8780/.

AI. External acceptance was not run. The environment had no Rukan intake hostname, certificate, or domain variable. Remaining inputs:
* a hostname or address customer deployments can reach;
* a TLS certificate and private key for that name;
* the intake bind address, port, and firewall opening;
* the public https URL to save in Admin monitoring settings.
Command: python -m machi.main command-center intake --data-dir <dir> --host <address> --port 8781 --cert <cert> --key <key>

AJ. Customer host keeps Admin running: python -m machi.main admin serve --store-dir <store> --journal-dir <journal> --static-dir ui/admin/dist --port 8765. This session used 8766 because 8765 was already listening. Vendor host keeps Command Center on 127.0.0.1:8780 and, separately, the intake process. Outbox and usage survive in <store>/rukan-telemetry.sqlite. Restart Admin to resume the agent. Inbox files are not deleted by Remove.

AK. Admin production build and Command Center production build succeeded. Browser checks: Admin Overview, Models, Analytics, Settings; Command Center Overview, Reporting, Settings. Command Center JavaScript is served as text/javascript.

AL. tests/machi 626 passed on the full rerun. One earlier run had a single unrelated failure in test_slow_progress_outlasts_inactivity_interval; that test passed alone and in the rerun. tests/acceptance_lab 51 passed, collected separately. ruff check . passed. mypy --strict src/machi: 196 files, no issues. Admin vitest 4 passed. Command Center vitest 5 passed. Both tsc and vite builds passed.

AM. Wheel machi-0.1.0-py3-none-any.whl, build id 0.1.0+0e87b9cd80e5, SHA256 c53037f1881ca476d799b5fabc912ae007d493f3fd555228ec4a9fe89d7a4c13, size 387754, clean_source true. verify_machi.py: verify_ok.

AN. Command Center schema 3. Version 2 gains report columns and intake tables. Version 1 still rebuilds sources, then follows the version 2 upgrade. Usage sqlite starts at schema 1. Schema fingerprint regenerated.

AO. Limitations: no human login, no remote control, no percentiles, no Recommended models, no deployment-setting mutation, no backfill of missed windows, no public intake. R-03-01 is open.

AP. Recommended next increment: Lead review, then an owned HTTPS intake endpoint acceptance. Do not start it here.

AQ. Git: branch rukan/connected-monitoring-v0.3, committed YES, pushed YES. Untracked docs/machi/proposals/ only. origin/machi unchanged at d38a8e855f099f353e1ac090b990014eed67a826.

AR. STOP

EVIDENCE:

* focused tests: tests/machi/test_rukan_monitoring.py
* regression tests: tests/machi 626; tests/acceptance_lab 51
* wheel verify_ok as listed above

SOURCE SIDE (real-host stages):

* predecessor: d38a8e855f099f353e1ac090b990014eed67a826
* source commit(s): 0e87b9cd80e52f2a0c0d528f41076b33f4c1ddf4
* files changed: usage, report, telemetry, intake, Admin, Command Center, docs
* local tests: listed above
* final source commit: 0e87b9cd80e52f2a0c0d528f41076b33f4c1ddf4
* artifact / SHA-256 / build id: machi-0.1.0-py3-none-any.whl / c53037f1881ca476d799b5fabc912ae007d493f3fd555228ec4a9fe89d7a4c13 / 0.1.0+0e87b9cd80e5

DEPLOYMENT SIDE (real-host stages):

* target host and fingerprint: none; no owned external endpoint
* transferred hash == local hash: not applicable
* installed build identity: not applicable
* install/upgrade result: not applicable
* commands under acceptance: local only
* observations and diagnostics: not applicable
* acceptance result: local connected pass; external endpoint required
* attempts, if more than one: one

BEHAVIOR:

* A deployment can record usage, queue a report, and upload it with a deployment credential.
* Command Center stores the report, sequence, trigger, and gap without becoming host authority.
* Upload failure does not block inference.
* Prompts and responses are not in the usage store or the report.

SCOPE:

* non-goals preserved: human auth, remote control, Knowledge, RAG, Team Brain, LibreChat, Dynamo, licensing, Kubernetes, GPU qualification
* adjacent issues recorded: R-03-01 read-only deployment settings; untracked docs/machi/proposals/ not committed

GIT:

* branch: rukan/connected-monitoring-v0.3
* working tree: untracked docs/machi/proposals/ only
* committed: YES
* pushed: YES

CHECKPOINT:

* path: none
* token/hash: none

QUESTIONS / DECISIONS:

* NONE

NEXT:

* Lead review of 0e87b9cd80e52f2a0c0d528f41076b33f4c1ddf4
* DO NOT begin it

================================================================================
============================ PASTE BACK END ====================================
================================================================================
