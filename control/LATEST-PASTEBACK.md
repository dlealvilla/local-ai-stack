# PASTE BACK

A. Terminal status

`RUKAN_V0_3_PRODUCTION_CANDIDATE_READY_FOR_SERVER_ACCEPTANCE`

B. Executive TL;DR

Bounded Rukan v0.3 is ready for Daniel's later server acceptance. Usage delivery is owned by an ACK cursor, People access is per capability with a platform parent gate, Admin stays loopback-only, and the frozen wheel serves both UIs without a repository checkout or Node. Production cadence is 21600 seconds. Development, 120 seconds, is explicit. No server-acceptance or pilot blocker remains in this envelope. GA gaps stay documented and were not downgraded.

C. Starting and final SHA

- Starting candidate: `fd13ede7553011033a140d1206982f54536b7032`
- Final: `5aaa43d81645c8266f3cad11b91aa57e93d59b96`
- Implementation commit: `43be965` plus packaging commit `5aaa43d`

D. Branch, origin, worktree

- Branch: `rukan/connected-monitoring-v0.3`
- Pushed: `origin/rukan/connected-monitoring-v0.3` at `5aaa43d`
- `origin/machi` was not moved
- Untracked `docs/machi/proposals/` was left untracked

E. Supported production-candidate envelope

POSIX host. Loopback Admin. SSH tunnel for a remote administrator. One-way HTTPS telemetry into Command Center. Production reporting every 21600 seconds. Development every 120 seconds only when selected. Customer-local People directory with no enforcement. One native vLLM serving path already in the product. Packaged Admin and Command Center UIs.

F. GA exclusions

No human Admin authentication. No employee gateway, chat, Agent Builder, RAG, licensing, or remote control. No Windows secure-credential adapter. No journal rotation. Physical qualification still pending for AMD native/vLLM, macOS/Ollama, and NVIDIA Ampere/N1.

G. Architecture audit summary

ResourceManager remains admission authority. Plan does not admit. Serve does not release. STOP is not RELEASE. Command Center stores reports and does not operate the customer host. Telemetry is one-way. People and customer content stay local. The audit is `docs/machi/RUKAN-V0.3-PRODUCTION-READINESS-AUDIT.md`.

H. Authority and ownership graph

Install identity feeds Plan, then ResourceManager, then Serve, then the local journal and usage rows, then the telemetry outbox, then Command Center intake. People is local Admin only. No observer in that chain authorizes admission or a customer mutation.

I. Findings by classification

- SERVER_ACCEPTANCE_BLOCKER: none remaining
- PILOT_BLOCKER: none remaining
- GA_BLOCKER: PR-01 human Admin auth; PR-02 Windows credentials; PR-03 journal rotation; PR-04 physical breadth
- DEFERRED_PRODUCT: PR-05 employee gateway and chat; PR-06 read-only deployment settings; PR-07 no public intake product

J. Previous defect closure

- People Admin can search, create, edit, suspend, reactivate, deactivate, manage memberships, edit intent, and show effective access
- Platform deny closes inference, model selection, and agent builder
- Provenance is per capability
- A frozen queued report does not resurrect its triggers; a later reason is reported after ACK

K. People UI completion

Verified in the browser against packaged Admin on `127.0.0.1:8794`. Created Ada Example / ada.ui@example.test. Details showed the stable id, timestamps, inherit controls, Suspend, Deactivate, and effective rows: platform `default_deny`, and the other capabilities `platform_parent`. Enforcement text is `gateway_not_available`.

L. Access-policy semantic model

User intent may be allow, deny, or inherit per capability. Team intent may be allow or deny. Missing user intent inherits. Active team allows compose by union. Archived teams grant nothing. Suspended and deactivated users deny every capability.

M. Per-capability provenance

`platform_provenance`, `inference_provenance`, `model_selection_provenance`, and `agent_builder_provenance`. Values include `user_status`, `platform_parent`, `user_deny`, `user_allow`, `team_grant`, and `default_deny`.

N. Directory install binding

`directory.sqlite` records the local InstallId. A later conflicting InstallId fails closed. A fresh directory may bind once. Unresolved identity stays `not_recorded` until a record exists.

O. Cadence default

Product default is production, 21600 seconds. The Admin API default profile is `production`. Development, 120 seconds, is selected in Settings or by the playbook. A release wheel does not inherit the 2-minute profile from the build tree. Isolated install reported `production 21600`.

P. Scheduler evidence

Phase stays epoch-aligned. The 15-minute soak produced periodic gaps of 121.8s, 235.5s, 121.7s, 120.3s, and 120.3s. The 235.5s gap is the intake outage: one catch-up report, not a backfill storm. Event and test reports do not move `next_periodic_at`.

Q. Usage delivery

Each usage row gets `usage_seq`. A report includes rows above `ack_usage_seq` through the proposed sequence. Only a matching ACK advances the cursor. `occurred_at` is analytics time. Eight concurrent inserts produced sequences 1..8 once. The next report carried one new request, not a replay of the first eight.

R. Event journal delivery

The compose cursor does not consume a trailing partial line. A shrunk journal sets `journal_truncated` and does not skip ahead. Rotation is not supported and is `R-03-04`.

S. Telemetry stream

Each local telemetry database mints `tstream_…` once. Command Center gaps are computed inside install plus stream. A new database is a new stream and does not collide with the old sequence.

T. Duplicate and collision

Same report id and same body digest is an idempotent ack. A different body for that id is rejected. The same install, stream, and sequence with a different report id is rejected and does not overwrite.

U. Clock skew

Freshness uses receiver `received_at`. A generated time more than two hours away is stored as `source_clock_ahead` or `source_clock_behind` and is still accepted. Command Center shows the clock column.

V. Telemetry configuration authority

The browser supplies endpoint, key, secret, and profile. `install_id` comes from the local install record. Production enablement refuses `not_recorded` unless local-test mode is explicit.

W. Degraded accounting

A failed usage insert returns false, increments `usage_records_dropped`, and does not fail inference. Reports with drops say `usage_accounting_status=degraded`.

X. Outbox

One queued report stays frozen until a matching ACK. A wrong ACK does not advance cursors. Send failure leaves the row queued. Delivered history compacts to 48. Unacknowledged rows are not deleted.

Y. Retention

Delivered outbox keeps 48. Acknowledged usage keeps the newest 2000. Unacknowledged usage is kept. Directory audit compacts after 200000 bytes to the last 400 lines. Command Center clears raw report documents beyond the newest 200 per install and keeps structured rows. Rejection rows keep the newest 500. The operational journal is not deleted.

Z. Sensitive-file permissions

POSIX mode `0600` for telemetry SQLite, directory SQLite, Command Center SQLite, credential files, and their WAL/SHM when present. Non-POSIX hosts are not given a weaker mode.

AA. SQLite concurrency

WAL and a 4 second busy timeout. Eight processes opening one fresh Command Center database migrate once to schema 5. Ten deployments reported concurrently into one hub without shared usage totals. Admin and intake can share the Command Center database.

AB. Mini-fleet

Ten independent install ids and credentials. Nine accepted. One bad credential was rejected. Accepted report count 9, distinct installs 9, request sum 9.

AC. Admin security

Non-loopback bind is refused. A POST with `Origin: https://evil.example` returned 403. Request bodies are size-bounded. Malformed JSON is refused. Handler errors return a generic refusal. Static paths cannot escape the UI root.

AD. Intake security

Write-only. GET returned 404 from the packaged intake. Non-loopback plaintext is refused. Loopback plaintext requires local-test. Production HTTPS uses certificate and hostname verification. Bearer comparison uses `hmac.compare_digest`. The secret is not a URL query. Revoked credentials are rejected.

AE. Command Center rendering

Imported strings are React text. The clock and cadence columns render report metadata. The packaged JavaScript is served as `text/javascript`.

AF. PII and privacy

Canaries for name, email, and team data stay in the local directory. The existing people test and the soak checked that `canary.soak@example.test` and `Canary Soak` did not enter `command.sqlite`. Prompts are not stored on the usage row.

AG. Model and deployment authority

Model cards stay on artifact or digest identity. Deployment settings remain read-only. ResourceManager is still the only admission authority.

AH. Artifact-only install

Clean wheel `machi-0.1.0-py3-none-any.whl`, build `0.1.0+5aaa43d81645`, size 557828, SHA256 `1d6faa228ef5f3cc546e07192f2356ad9d2fcd3bb305c39231cf1b45b2ccd5a3`, `clean true`. `tools/verify_machi.py` printed `verify_ok`. A fresh venv with `PYTHONPATH` unset, started from `/tmp`, served Admin and Command Center HTML, served JavaScript as `text/javascript`, created a person, reported production 21600, answered intake GET with 404, and issued a credential. Node was not used at runtime.

AI. Migration

Command Center schema 1 upgrades to 5. Schema 4 opens as 5. Schema 9 fails closed. Fresh telemetry and directory databases create the current tables. Telemetry adds `usage_seq` and `proposed_usage_seq` when missing.

AJ. I/O and permission failure

Usage insert failure is caught, counted, and does not raise into inference. Directory and telemetry files are owner-only on POSIX. A conflicting directory install binding raises `ValidationError`.

AK. Process signals

`SIGINT` and `SIGTERM` stop Admin, Command Center, and intake through `serve_until_stopped` without a traceback. The soak restarted Admin with SIGTERM and reporting resumed.

AL. Telemetry agent health

The agent starts with Admin, ticks on its own thread, records `last_tick_error` instead of disappearing, and stops when Admin stops. Restart resumes from SQLite.

AM. UI and backend coherence

People controls call `/v1/people`. Settings defaults to Production and labels Development only when that profile is selected. Command Center shows receiver time, cadence, and clock skew. Effective access in the UI matches the API.

AN. Documentation

Updated the monitoring note, people access note, telemetry note, analytics cadence sentence, debt register, acceptance playbook, and the production-readiness audit. Historical evidence docs were left in place.

AO. Preflight

`python -m machi.main acceptance preflight` now checks Python, POSIX credentials, the wheel path, writable data dir, certificate and key together, HTTPS endpoint, optional ports, and packaged UI. It prints PASS or BLOCKED and optional JSON. It does not open a service and does not spend money.

AP. Playbook

`docs/machi/RUKAN-REAL-USER-ACCEPTANCE-V0.3.md` is artifact-only. Customer Admin stays on loopback. Daniel uses an SSH tunnel. Telemetry uses machine-authenticated HTTPS. The test must select Development. Expected observations are listed. No remote campaign was run.

AQ. Local production-like acceptance

Packaged Admin, Command Center, and intake were real processes from the frozen wheel. People, monitoring, the credential CLI, and write-only intake were exercised. The development soak used real processes for Admin, intake, and Command Center.

AR. Soak

`tools/rukan_dev_soak.py` ran 906 seconds and exited 0. Six periodic reports. Generated times:

- 2026-09-29T05:12:03.889210+00:00
- 2026-09-29T05:14:05.669420+00:00
- 2026-09-29T05:18:01.203051+00:00
- 2026-09-29T05:20:02.908986+00:00
- 2026-09-29T05:22:03.199280+00:00
- 2026-09-29T05:24:03.462452+00:00

Gaps seconds: 121.78021, 235.533631, 121.705935, 120.290294, 120.263172. Intake was stopped, a slot was crossed, intake was restored, a test report was injected, and Admin was restarted. No trigger storm. The People canary was absent from Command Center. Store: `/var/folders/y9/2yjwrjq143s4dcm4h5639fsr0000gp/T/rukan-soak-po4fyzss`.

AS. Backend QA

`tests/machi` exited 0. `tests/acceptance_lab` exited 0, collected separately. `ruff check .` passed. `mypy --strict src/machi` passed, 201 files. Readiness tests covered usage cursor, trigger non-resurrection, access truth table, collision, skew, retention, permissions, install binding, origin refusal, mini-fleet, and concurrent schema open.

AT. Frontend QA

Admin Vitest 4 passed. Admin `tsc` and production build passed. Command Center Vitest 5 passed. Command Center `tsc` and production build passed.

AU. Wheel

`machi-0.1.0-py3-none-any.whl`  
SHA256 `1d6faa228ef5f3cc546e07192f2356ad9d2fcd3bb305c39231cf1b45b2ccd5a3`  
size 557828  
build `0.1.0+5aaa43d81645`  
clean source true  
`verify_ok`

AV. Debt register

| ID | Class | Server acceptance | Pilot | GA |
| --- | --- | --- | --- | --- |
| R-03-01 | DEFERRED_PRODUCT | no | no | no |
| R-03-02 | GA_BLOCKER | no | no | yes |
| R-03-03 | GA_BLOCKER | no | no | yes |
| R-03-04 | GA_BLOCKER | no | no | yes |
| physical lanes | GA_BLOCKER | no | no | yes |

AW. Remaining GA blockers

PR-01 no human Admin auth, loopback plus SSH tunnel is the test path. PR-02 no Windows secure credential adapter. PR-03 no journal rotation. PR-04 AMD, macOS/Ollama, and NVIDIA Ampere/N1 physical qualification remain outside this software gate.

AX. Recommended next action

Server acceptance by Daniel using the frozen wheel and `docs/machi/RUKAN-REAL-USER-ACCEPTANCE-V0.3.md`. Do not start RunPod. Do not redesign this envelope first.

AY. Git state

`rukan/connected-monitoring-v0.3` pushed to origin at `5aaa43d81645c8266f3cad11b91aa57e93d59b96`. Working tree clean except untracked `docs/machi/proposals/`. `origin/machi` was not moved.

AZ. STOP

STOP for Lead review. The next step is not started.
