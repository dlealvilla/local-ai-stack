================================================================================
=========================== PASTE BACK START ===================================
================================================================================

TASK: RUKAN-FUNCTIONAL-PRODUCT-V0.3-FINISH-001
STATE: PASS
MILESTONE: Rukan functional product v0.3 finish
STAGE: telemetry correctness, people directory, server-test readiness
STEP: close monitoring defects and add customer-local people
PREDECESSOR OUTPUTS: 0e87b9cd80e52f2a0c0d528f41076b33f4c1ddf4 on rukan/connected-monitoring-v0.3
CURRENT_COMMIT: fd13ede7553011033a140d1206982f54536b7032

STATUS: RUKAN_V0_3_FUNCTIONAL_LOCAL_PASS_SERVER_TEST_READY

A. Terminal status: RUKAN_V0_3_FUNCTIONAL_LOCAL_PASS_SERVER_TEST_READY
B. TL;DR: Telemetry cursors now move only on a matching ACK, the development heartbeat is a stable 120-second phase, and People is a real local directory that does not leave the customer host. No paid server test was run.
C. Starting SHA 0e87b9cd80e52f2a0c0d528f41076b33f4c1ddf4. Final SHA fd13ede7553011033a140d1206982f54536b7032.
D. Branch rukan/connected-monitoring-v0.3. Pushed. Untracked docs/machi/proposals/ only. origin/machi remains d38a8e855f099f353e1ac090b990014eed67a826.

CHANGES:

* machi.kernel.cadence is the only interval table: development 120s, production 21600s, custom 60..86400s.
* Operational reports carry cadence_profile, cadence_seconds, and cadence_phase_seconds.
* One queued report is frozen until an ACK names its report id. Cursors, baselines, and the periodic slot move only then.
* Command Center schema 4 records cadence and recomputes sequence gaps. A late report does not replace a newer summary.
* directory.sqlite holds users, teams, memberships, and access intent. Admin People API and page use it.
* docs/machi/RUKAN-REAL-USER-ACCEPTANCE-V0.3.md and `acceptance preflight` prepare the later campaign.

E. Deviations: bearer token remains; phase is epoch-aligned rather than added to each interval; one outstanding report replaces the old 24-report drop; team roles are deferred; access rule is user deny, user allow, team grant, default deny. Enforcement is always gateway_not_available.

F. State machine: compose writes the body and proposed journal offset, window end, and periodic flag. Send failure leaves meta cursors unchanged. ACK applies them and sets delivered_at.

G. Cadence: development is the current default. Production stays 6 hours. Admin Settings names the development profile explicitly.

H. Development heartbeat: real Admin process on 127.0.0.1:8791 and local-test intake on 127.0.0.1:8792. Periodic generated_at values 2026-09-29T03:18:02.474067+00:00 and 2026-09-29T03:20:02.725221+00:00. Gap 120.251 seconds.

I. Production profile remains 21600 seconds with a phase cap of 900 seconds. Tests configure it explicitly.

J. ACK: wrong report id leaves the row queued and last_acked empty. Journal offset does not move before ACK. Event reports do not move next_periodic_at.

K. Sequence 1 then 3 then late 2: high stays 3, the late row is out_of_order, and the gap becomes missing:2 until 2 arrives, then none. Latest trigger stays with the highest sequence. Receipt time still updates.

L. Usage accounting is unchanged: OpenAI and Ollama counts when present, Rukan boundary latency, operator_test versus acceptance_probe, no prompt text.

M. People contracts: kernel.directory_user, kernel.directory_team, kernel.directory_membership, kernel.access_intent, kernel.effective_access.

N. Persistence: <store>/directory.sqlite schema 1, separate from telemetry and Command Center. Audit file stores ids, not emails.

O. Users API: POST /v1/people actions create_user, update_user, set_status, list. Duplicate normalized email is refused. Deactivated users are not reactivated.

P. Teams API: create_team, update_team, set_team_status, add_membership, remove_membership. Archive keeps the membership row.

Q. Resolver: effective action returns capabilities, provenance, configured true, enforcement gateway_not_available. No session and no inference route.

R. Privacy: report dump rejects email keys. Canary name and email were absent from the outbox body, the audit line, and command.sqlite.

S. Audit actions: user.created, user.updated, user.status_changed, team.created, team.updated, team.archived, team.reactivated, membership.added, membership.removed, access_intent.changed. They appear on local Admin Activity only.

T. Admin navigation adds People. Overview stays the readiness, model, usage, and monitoring summary.

U. Models library is unchanged: exact artifact or digest cards, no Recommended row.

V. People page lists users and teams, creates both, and states that login is not enabled.

W. Analytics still shows requests, tokens, latency, and purpose. Activity appends directory ids locally.

X. Settings shows Development — every 2 minutes, Production — every 6 hours, or custom seconds, plus phase, next slot, and last ACK time.

Y. Command Center deployments show the reported cadence text and judge lateness from that interval, not a fixed 6 hours. They do not say online or offline.

Z. Portfolio, reporting, and model landscape remain report evidence. They do not read directory.sqlite.

AA. Soak used the real admin serve and command-center intake processes, not the browser. Two periodic reports arrived 120.251 seconds apart. The run exited 0. SIGINT previously printed a KeyboardInterrupt from the server loop; serve paths now catch that interrupt and close the databases.

AB. Playbook: docs/machi/RUKAN-REAL-USER-ACCEPTANCE-V0.3.md. SSH tunnel to loopback Admin. No public Admin. No RunPod.

AC. `python -m machi.main acceptance preflight --data-dir <dir> --cert <cert> --key <key>` checks writability and optional cert paths. Evidence layout is acceptance-evidence/ and is gitignored.

AD. Later commands are in the playbook: admin serve, command-center serve, intake with cert and key, credential issue, ssh -L 8765:127.0.0.1:8765. This run did not execute them against a remote host.

AE. Admin stays loopback. Intake write-only. Non-loopback plaintext still fails closed. Credential file remains mode 0600 on POSIX. No passwords.

AF. Admin vitest 4, tsc, vite build. Command Center vitest 5, tsc, vite build.

AG. tests/machi 631 passed. tests/acceptance_lab 51 passed, collected separately. ruff check . passed. mypy --strict src/machi: 200 files, no issues.

AH. Wheel machi-0.1.0-py3-none-any.whl, build id 0.1.0+fd13ede75530, SHA256 a4c3df4ced22426717bc8f24f3448c1756004a8b7ba5be7696fb5f6c299f8f32, size 398037, clean_source true. verify_ok.

AI. Command Center schema 4 adds cadence_profile and cadence_seconds. Version 3 upgrades in place. Directory schema starts at 1. Report contract fields replaced cadence_hours before promotion. Fingerprint regenerated.

AJ. No employee login, gateway, chat, LibreChat, Agent Builder, RAG, remote control, or public intake. Team roles are deferred. R-03-01 deployment settings remain read-only.

AK. Next stage can authenticate a user, call the effective-access resolver, and only then open a gateway in front of an admitted ServingInstance. Do not start it here.

AL. Git: branch rukan/connected-monitoring-v0.3, committed YES, pushed YES. origin/machi unchanged.

AM. STOP

EVIDENCE:

* focused tests: test_rukan_monitoring.py, test_rukan_people.py, tools/rukan_dev_soak.py
* regression tests: tests/machi 631; tests/acceptance_lab 51
* soak gap_s 120.251154

SOURCE SIDE (real-host stages):

* predecessor: 0e87b9cd80e52f2a0c0d528f41076b33f4c1ddf4
* source commit(s): fd13ede7553011033a140d1206982f54536b7032
* files changed: cadence, telemetry, intake, people directory, Admin, Command Center, playbook
* local tests: listed above
* final source commit: fd13ede7553011033a140d1206982f54536b7032
* artifact / SHA-256 / build id: machi-0.1.0-py3-none-any.whl / a4c3df4ced22426717bc8f24f3448c1756004a8b7ba5be7696fb5f6c299f8f32 / 0.1.0+fd13ede75530

DEPLOYMENT SIDE (real-host stages):

* target host and fingerprint: none; playbook only
* transferred hash == local hash: not applicable
* installed build identity: not applicable
* install/upgrade result: not applicable
* commands under acceptance: local soak and preflight only
* observations and diagnostics: two periodic reports 120.251 seconds apart
* acceptance result: local functional pass; server campaign not run
* attempts, if more than one: one soak

BEHAVIOR:

* Development reports repeat on a stable 120-second phase.
* An event report does not postpone that phase.
* People can be created locally and do not appear in Command Center.

SCOPE:

* non-goals preserved: employee login, gateway, chat, RAG, remote control, paid infrastructure
* adjacent issues recorded: R-03-01; untracked docs/machi/proposals/ not committed

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

* Lead review of fd13ede7553011033a140d1206982f54536b7032
* DO NOT begin it

================================================================================
============================ PASTE BACK END ====================================
================================================================================
