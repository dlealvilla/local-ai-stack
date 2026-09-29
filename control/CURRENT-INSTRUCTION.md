# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-V0.3-PRODUCTION-READINESS-GATE-001`
Status: `AUTHORIZED_PRODUCTION_READINESS_AUDIT_AND_HARDENING`
Supersedes: `RUKAN-FUNCTIONAL-PRODUCT-V0.3-FIX-002`
Starting source: `fd13ede7553011033a140d1206982f54536b7032`
Branch: `rukan/connected-monitoring-v0.3`
Canonical baseline remains: `d38a8e855f099f353e1ac090b990014eed67a826`

This is a **production-readiness gate**, not a routine feature increment.

The goal is to maximize the probability that the currently implemented Rukan product works coherently when Daniel begins real server acceptance.

Do not optimize for the appearance of completion.

Audit deeply, challenge assumptions, find logic gaps, repair all blockers inside the bounded product scope, and prove the resulting candidate locally.

If a blocker cannot responsibly be corrected inside this scope, do NOT claim readiness. Return a precise NOT-READY result.

No paid/external server acceptance is authorized in this instruction.

---

# 0. WHAT "PRODUCTION READY" MEANS FOR THIS GATE

Do NOT claim that the entire future Company Brain is GA-ready.

The bounded product under review is:

## Customer-host Rukan

- accepted Stage-1 Blocks 0–9 deployment spine;
- customer-local Admin;
- Overview;
- Models;
- Deployment;
- Inference tester;
- Analytics;
- Activity;
- People / Users & Teams;
- System;
- Settings;
- model/runtime deployment state already implemented;
- non-content inference usage accounting;
- automatic operational reports;
- 2-minute development/test reporting profile;
- 6-hour production reporting profile;
- secure one-way telemetry sender;
- customer-local People directory and future access-intent resolver.

## Business-side Rukan Command Center

- persistent local service;
- SQLite;
- deployment portfolio;
- report history;
- analytics;
- model landscape;
- reporting/intake accountability;
- support evidence;
- credential issue/rotate/revoke;
- secure external telemetry intake.

## Explicitly NOT in this bounded product

- human administrator authentication;
- employee authentication/login;
- employee inference gateway;
- employee chat;
- LibreChat/Open WebUI;
- Agent Builder;
- Knowledge/RAG;
- remote customer control;
- licensing/billing;
- general multi-tenant cloud control plane;
- Online/Offline liveness semantics.

A PASS means this bounded product is a **production candidate ready for real server acceptance / controlled pilot validation**, not general commercial GA.

---

# 1. REQUIRED TERMINAL CLASSIFICATION

Every finding must be classified as one of:

## SERVER_ACCEPTANCE_BLOCKER

Likely to:
- make the upcoming server test fail;
- corrupt/misattribute data;
- lose monitoring/usage evidence;
- break restart/upgrade;
- expose an unsafe network surface;
- make the UI claim functionality that is not real.

Must be fixed before PASS.

## PILOT_BLOCKER

May not stop a narrow lab test, but is unacceptable for a controlled real customer pilot.

Fix in this run wherever technically within the bounded v0.3 scope.

If left unresolved, terminal status is NOT_READY unless Lead explicitly accepts it.

## GA_BLOCKER

Required before broad general-availability production, but intentionally outside the present bounded product.

Examples may include:
- human Admin authentication;
- Windows secure secret adapter if Windows is not currently in the declared pilot envelope;
- HA / multi-operator cloud service.

Record clearly. These do not automatically block server acceptance if the current supported envelope excludes them.

## DEFERRED_PRODUCT

Later Company Brain functionality, not a defect in v0.3.

Do not confuse deferred products with bugs.

---

# 2. REQUIRED ARCHITECTURE AUDIT DOCUMENT

Create:

`docs/machi/RUKAN-V0.3-PRODUCTION-READINESS-AUDIT.md`

This must be a real audit, not a summary of tests.

For every major subsystem include:

- product purpose;
- domain owner;
- authoritative state;
- inputs;
- outputs;
- persistence;
- network exposure;
- secrets/PII/content handled;
- invariants;
- failure modes;
- recovery mechanism;
- restart behavior;
- concurrency model;
- upgrade/migration behavior;
- test evidence;
- readiness classification;
- remaining debt.

Audit at least:

1. Kernel contracts / IDs / schema registry;
2. Install identity / state root / ownership;
3. Discover/Capacity source facts used by UI;
4. Foundation/runtime selection;
5. Model identities/catalog/warehouse/provider paths;
6. Plan;
7. ResourceManager;
8. Serve/lifecycle;
9. Admin API;
10. Admin UI;
11. inference usage recorder;
12. TelemetryStore / scheduler / outbox;
13. telemetry credential storage;
14. operational report contract;
15. telemetry HTTP client;
16. external intake;
17. Command Center hub/database;
18. Command Center UI;
19. People contracts;
20. People persistence;
21. People API/UI;
22. future effective-access resolver;
23. packaging/static assets;
24. service lifecycle;
25. migrations/upgrade;
26. acceptance/preflight/evidence workflow.

Include a final dependency/authority graph.

No subsystem may secretly become authority for a domain it only observes.

---

# 3. FIRST CLOSE ALL KNOWN LEAD-REVIEW DEFECTS

The previous correction remains mandatory.

## 3.1 Complete People Admin UI

Expose the real backend capabilities:

### Users
- search/filter;
- create;
- edit name;
- edit email;
- suspend;
- reactivate suspended;
- deactivate with confirmation;
- memberships;
- configured access intent;
- effective access;
- stable id in technical details;
- timestamps where useful.

### Teams
- search/list;
- create;
- edit;
- archive;
- reactivate;
- member count/list;
- add/remove membership;
- team access intent;
- stable id in technical details.

### Access
Expose:
- Platform access;
- Inference access;
- Model selection;
- Agent Builder.

Configured policy and effective resolved result are separate.

Always show:

`Employee gateway enforcement is not available yet.`

Render API refusals/errors instead of silently reloading.

## 3.2 Platform access parent gate

If effective platform access is not ALLOW:

- inference = DENY;
- model selection = DENY;
- agent builder = DENY.

Inactive/suspended/deactivated user denies everything.

Default deny.

## 3.3 Per-capability provenance

One global provenance string is insufficient.

Effective access must explain the actual rule for each capability.

Use a typed map/fields or equivalently strong representation.

## 3.4 Trigger resurrection

While one frozen report is waiting for ACK:
- do not rescan ACK-owned journal state in a way that re-adds already-frozen reasons;
- do not lose later events;
- after ACK, later events/state changes must be found naturally.

Prove:
- no redundant report after ACK if nothing new happened;
- new event while queued is reported after ACK;
- new model/runtime/SAFE state change while queued is reported after ACK;
- usage while queued appears after ACK.

---

# 4. ACCESS-POLICY COHERENCE AUDIT — DO THIS BEFORE FUTURE GATEWAY WORK

The current People/access model must be coherent enough to become the next-stage authorization input.

Audit whether the current binary `allow/deny` AccessIntent can truthfully represent:

> team defaults/grants + per-user override

without freezing inherited values accidentally.

Current danger:

If creating one user intent row requires explicit values for all capabilities, changing one user override can unintentionally stop future team inheritance for unrelated capabilities.

You MUST address this semantic ambiguity now.

A recommended simple model is:

## Organisation default

DENY.

## Team policy

Teams contribute bounded grants/defaults.

Do not invent a generic RBAC engine.

## User override

Per capability:
- INHERIT;
- ALLOW;
- DENY.

Then:

`user DENY > user ALLOW > active team grant > default DENY`

with Platform as parent gate.

Cursor may choose a different equally simple model, but it must satisfy:

- per-capability inheritance is expressible;
- team changes can affect users who have not explicitly overridden that capability;
- an override on one capability does not silently pin unrelated capabilities;
- multiple-team composition is deterministic;
- archived teams contribute nothing;
- provenance is per capability;
- default deny;
- no contradictory platform/subordinate effective state.

If contract changes are needed, do them before promotion and regenerate schema fingerprints.

Add complete truth-table tests.

---

# 5. IDENTITY / DIRECTORY BINDING AUDIT

People are customer-local product state.

Audit whether `directory.sqlite` is unambiguously bound to the correct Rukan installation/state root.

Production requirement:

- directory authority must not silently attach to a different InstallId after state-root copying/misconfiguration;
- where InstallId is resolved, persist/verify an install binding;
- fail closed on a conflicting install binding;
- fresh directory may initialize once against the local InstallId;
- local tests with unresolved identity may use explicit test mode only.

Do not put InstallId into PII export.

Audit IDs for collision resistance and stable serialization.

No directory record may use display name/email as authorization identity.

---

# 6. TELEMETRY PERIODIC SCHEDULE AUDIT

Preserve:

- development profile: 120 seconds;
- production profile: 21,600 seconds;
- custom bounded profile;
- one central cadence policy;
- stable epoch phase;
- no cumulative jitter;
- event/test reports do not postpone periodic schedule;
- bounded catch-up.

Deep-test clock behavior:

- exactly on slot;
- just before/after slot;
- process stopped across one missed slot;
- process stopped across many missed slots;
- clock jumps forward;
- clock jumps backward;
- profile changes development → production;
- production → development;
- custom change;
- restart between schedule computation and next slot.

No backfill storm.

---

# 7. PRODUCTION VS DEVELOPMENT CADENCE MUST NOT BE ACCIDENTAL

We are using 2 minutes for the upcoming development/server campaign.

A production-capable artifact must not accidentally deploy all future customers at 2-minute cadence because the source tree happened to be built during development.

Create an explicit operating/profile rule.

Preferred outcome:

- release/product default is Production / 6 hours;
- the acceptance playbook explicitly selects Development / 120 seconds;
- source/local dev tooling may explicitly opt into Development;
- Admin clearly labels Development cadence;
- latest report always carries the actual selected profile/seconds.

If Cursor chooses another mechanism, it must make accidental 2-minute production reporting impossible.

Update playbook accordingly.

---

# 8. USAGE DELIVERY MUST BE LOSSLESS / NON-DUPLICATING UNDER CONCURRENCY

This is a critical accountability audit.

Current usage export is time-window based.

Prove or correct all race/boundary cases.

Must not:
- double-count a usage row exactly on a window boundary;
- omit a row inserted after report composition whose `occurred_at` is earlier than/equal to the report window end;
- lose a usage row because the request and telemetry thread race;
- count one request in two operational reports.

Preferred design:

Use an ACK-owned stable local usage ingestion sequence/cursor separate from event time.

For example:
- append usage row with monotonically increasing local sequence;
- report freezes rows `usage_seq > ack_usage_seq AND <= proposed_usage_seq`;
- ACK advances `ack_usage_seq`;
- event/occurred time remains for analytics, not delivery correctness.

Cursor may prove another design, but timestamp-only delivery windows are unacceptable if race tests can lose/duplicate usage.

Tests:
- identical timestamps;
- boundary timestamps;
- usage insert concurrent with report composition;
- usage insert while queued;
- failure/retry;
- restart;
- ACK;
- next report;
- cumulative counters remain consistent.

---

# 9. EVENT JOURNAL DELIVERY AUDIT

Audit byte-offset cursor behavior against current actual journal implementation.

Prove:

- no partial-line corruption;
- truncation/shrink is detected rather than silently skipping;
- malformed line does not wedge future valid lines;
- max event limit/backlog preserves later events;
- trigger reasons correspond coherently to exported event slices;
- no event is lost across ACK/restart;
- no already-ACKed event is exported again except explicit idempotent resend of the same frozen report.

If journal rotation does not exist today, document the bounded current assumption.

Do not claim support for future rotated journals unless implemented/tested.

---

# 10. TELEMETRY STREAM RESET / SEQUENCE COLLISION AUDIT

Ask:

What happens if:
- `rukan-telemetry.sqlite` is deleted/corrupted/reinitialized;
- InstallId stays the same;
- Command Center already has sequences 1..N;
- a new local telemetry DB starts again at sequence 1?

This must not silently masquerade as old out-of-order history forever or collide with old report semantics.

Implement explicit stream-generation/reset identity if required.

A robust simple seam may include:
- stable `telemetry_stream_id` in OperationalReport;
- receiver cursor keyed by install + stream;
- explicit stream reset evidence;
- latest deployment summary remains coherent.

Do not let arbitrary unauthenticated resets erase history.

Key rotation alone should not necessarily reset a stream.

Test reset/re-pair behavior.

---

# 11. REPORT IDEMPOTENCY / COLLISION RULES

Receiver must distinguish:

## Exact duplicate
Same report_id + same body digest:
- idempotently accepted/acknowledged;
- no duplicate aggregates.

## Conflicting duplicate
Same report_id + different body digest:
- reject as integrity conflict;
- preserve bounded rejection evidence;
- do not overwrite original.

## Sequence collision
Same install/stream + same sequence + different report:
- flag/reject conflict unless explicit reset semantics apply.

## Late valid report
Preserve history without regressing current summary.

Add tests.

---

# 12. REPORT FRESHNESS AND CLOCK SKEW

Customer clocks may be wrong.

Command Center must distinguish:

- `generated_at` — customer source clock;
- `received_at` — business receiver clock.

Report freshness / "last report received" must use receiver time.

Do not infer freshness from customer-generated time.

Detect and surface substantial source clock skew as report evidence/warning where simple, for example:
- generated far in future;
- generated materially older than received.

Do not reject a useful report solely for benign clock skew unless it violates schema/integrity constraints.

Test +2h / -2h source clock.

---

# 13. TELEMETRY CONFIGURATION AUTHORITY

Audit Admin monitoring configuration.

The browser must NOT be allowed to invent local deployment identity.

Requirements:

- install_id used for telemetry configuration is derived from trusted local operational state;
- browser config supplies endpoint/key/secret/profile, not arbitrary InstallId;
- production reporting refuses enablement if the local InstallId is unresolved;
- explicit local-test fixtures may use unresolved identity only in local-test mode.

Credential key/install binding remains receiver enforced.

---

# 14. INFERENCE USAGE ACCOUNTABILITY

Current usage recording must remain non-blocking to inference, but accountability failures must not be silent.

Audit:

- if usage SQLite write fails, inference response still succeeds;
- Admin receives a local warning/data-gap counter;
- telemetry/report can truthfully indicate usage accounting had dropped records;
- no prompt/response is used to reconstruct missing metrics;
- no false complete-volume claim if accounting is degraded.

Add a bounded metric/state such as:
- usage_records_dropped;
- usage_accounting_status;
or equivalent.

Do not send exception bodies/customer content.

Similarly, telemetry agent internal composition errors must remain visible locally rather than vanish behind a catch-all.

---

# 15. OUTBOX / DELIVERY STATE MACHINE AUDIT

Write an explicit state machine in the audit doc.

At minimum:

```text
LOCAL FACTS
  ↓
COMPOSE
  ↓
FROZEN_QUEUED
  ├─ send fail → RETRY_WAIT → FROZEN_QUEUED
  └─ matching ACK
        ↓
     DELIVERED
        ↓
     ACK cursors advance
```

Test:

- crash before durable compose;
- crash after body write before send;
- crash during network send;
- server accepted but client lost ACK;
- exact resend;
- client receives wrong ACK;
- client crashes after ACK received but before local commit (simulate where practical);
- restart;
- no unacknowledged deletion.

At-least-once + idempotent receiver must converge.

---

# 16. STORAGE GROWTH / RETENTION — MUST BE BOUNDED

2-minute development reporting can create 720 periodic reports/day/deployment before event-trigger reports.

Audit all continuously growing stores:

Customer:
- telemetry outbox/delivered history;
- usage rows;
- telemetry-actions;
- directory audit;
- event journal.

Command Center:
- operational reports;
- raw report document;
- rollups;
- snapshots;
- rejections;
- imported source history.

Define explicit retention for the bounded v0.3 product.

Requirements:

- NEVER delete unacknowledged reports;
- preserve source/local usage required for the unacked cursor;
- delivered customer outbox history can be compacted safely after ACK;
- Command Center should retain meaningful report metadata/rollups even if old raw report documents are compacted;
- development profile must not cause uncontrolled growth;
- retention is configurable or at least centrally policy-owned;
- retention operations are transactional and tested;
- no People PII is introduced into vendor retention.

Do not build a data warehouse.

Choose simple conservative defaults and document them.

---

# 17. SENSITIVE LOCAL FILE PERMISSIONS

Audit file permissions for:

Customer:
- credential secret;
- telemetry SQLite + WAL/SHM;
- directory SQLite + WAL/SHM;
- local directory audit;
- other newly sensitive v0.3 state.

Business:
- Command Center database;
- certificate/private-key handling where applicable.

On supported POSIX pilot hosts:
- use restrictive directories/files where Rukan owns them;
- do not leave user emails/usage secrets world-readable due default umask;
- verify permissions in tests/preflight.

Do not fake POSIX chmod semantics on Windows.

If Windows secure persistence is not implemented, classify that platform limitation explicitly.

---

# 18. SQLITE / PERSISTENCE COHERENCE AUDIT

For every SQLite database:

- WAL policy;
- busy timeout;
- transaction boundaries;
- indexes used by current queries;
- migration version;
- failure rollback;
- multiple readers/writers;
- close/restart;
- corruption/integrity detection;
- disk-full behavior;
- read-only/unwritable directory behavior.

Run process-level concurrency, not only thread-level tests.

At minimum simulate:

- Admin UI reads while telemetry writes;
- inference usage inserts while telemetry report composition reads;
- Command Center UI reads while intake writes;
- credential operation while intake receives;
- People UI mutations while Activity reads.

SQLite lock errors must fail safely and surface meaningful local status.

---

# 19. MINI-FLEET LOCAL INTAKE TEST

Before server testing, simulate multiple independent deployments locally.

At minimum:
- 10 separate install ids;
- 10 credentials;
- concurrent uploads;
- several reports each;
- mix periodic/event triggers;
- duplicates;
- one bad credential;
- one sequence gap;
- one late report;
- one clock-skewed report;
- credential rotation on one deployment.

Verify:

- no cross-install data contamination;
- correct latest summary per install;
- aggregate requests/tokens correct;
- no duplicate rollups;
- no SQLite lock corruption;
- Command Center query remains responsive.

This is not a scale benchmark. It is a coherence/concurrency proof.

---

# 20. SECURITY / THREAT MODEL AUDIT

Add a bounded threat model to the audit doc.

Actors:

- malicious website in administrator browser;
- untrusted process on customer host;
- network attacker;
- leaked telemetry credential;
- malformed telemetry client;
- malformed imported bundle;
- accidental operator misconfiguration.

Audit:

## Admin
- loopback bind;
- Host handling;
- Origin handling;
- CORS behavior;
- CSRF-like cross-origin POST attempts;
- request-body size limits;
- JSON parsing bounds;
- unknown route/action behavior;
- exception/error-body leakage;
- static-file path traversal;
- no secret returned after configuration.

## Telemetry client
- verified TLS for non-loopback;
- hostname verification;
- bounded connect/read timeout;
- secret never in URL;
- secret never logged;
- endpoint scheme validation;
- local-test exception constrained to loopback.

## Intake
- exact write-only route;
- no read/control routes exposed externally;
- request body max checked before unbounded allocation where practical;
- content type;
- constant-time secret verifier comparison where applicable;
- credential install binding;
- revoked key;
- malformed schema;
- body/report collision;
- no raw rejected body persistence;
- no secret in rejection logs;
- basic abuse/rate bound if current server can support it simply.

Do not add a full WAF/OAuth system.

---

# 21. ADMIN TRUST BOUNDARY

Human authentication is still deferred.

Therefore:

- Admin remains strictly loopback-only;
- upcoming remote testing must use SSH/local port forwarding;
- documentation must say that local Admin trusts the OS account/host boundary;
- this is a GA blocker for broader browser/network deployment, not something to hide.

Test that:
- `0.0.0.0` Admin bind is refused;
- non-loopback bind is refused;
- malicious/non-loopback Origin is refused;
- SSH forwarding does not require changing bind.

---

# 22. COMMAND CENTER TRUST BOUNDARY

Command Center control UI remains loopback-local.

External intake remains separate.

Audit that:
- the public intake listener cannot reach Command Center read/credential/control APIs;
- credential issue/rotate/revoke remain loopback control only;
- aliases/tags remain local;
- report body cannot inject HTML/script into UI without escaping;
- imported strings render as text, not executable markup.

---

# 23. PEOPLE / PII AUDIT

Test with strong canaries:

- realistic name;
- mixed-case email;
- external_ref;
- team names;
- membership;
- access intent;
- fake password-like string;
- fake prompt/response/document content.

Search:

- operational report bytes;
- outbox DB;
- Command Center DB;
- support snapshot;
- analytics bundle;
- rejection logs;
- telemetry action files.

Expected:
- no People PII/vendor export;
- no prompt/response/document;
- no secrets.

Admin local People APIs may return People data because they are customer-local.

Directory audit should use IDs; friendly names can be joined locally for UI.

---

# 24. PACKAGE / RELEASE ARTIFACT — HARD SERVER-ACCEPTANCE REQUIREMENT

Build the release wheel/artifact from a clean commit.

Then create a completely fresh temporary Python environment with:

- no repository on PYTHONPATH;
- no source checkout dependency;
- no Node/npm requirement at runtime;
- no Vite dev server.

Install ONLY the built wheel and its declared dependencies.

From that environment prove:

## Customer side
- `python -m machi.main --help`;
- Admin service starts;
- packaged production Admin UI is served without repository-relative `ui/admin/dist`;
- People works;
- Settings works;
- monitoring agent works;
- static assets load.

## Business side
- Command Center starts;
- packaged production Command Center UI is served without repository-relative `ui/command-center/dist`;
- intake starts;
- credential CLI works;
- database initializes.

If current artifact does not package static assets, FIX THIS.

Node is a build-time dependency only.

The server acceptance playbook must use artifact-only commands.

No command in the real-server test may assume a repository checkout.

---

# 25. STATIC ASSET / BUILD VERSION COHERENCE

Packaged UI must identify/align with backend build.

Audit:
- stale UI bundle cannot silently be served with incompatible backend if avoidable;
- build/version visible in UI/support evidence;
- package contains the exact built assets tested;
- wheel hash/provenance recorded.

No rebuilding after the artifact is frozen for server acceptance.

---

# 26. MIGRATION / UPGRADE AUDIT

Test supported upgrade paths relevant to currently accepted canonical state.

At minimum:

## Command Center
- accepted v0.2 schema → current schema;
- v0.3 previous candidate schema(s) where migration code claims support;
- fresh database.

## Telemetry
- fresh;
- previous candidate schema if code will encounter it in developer/server state.

## Directory
- fresh schema;
- version mismatch fails clearly.

Migration requirements:
- transactional;
- idempotent;
- no silent destructive rebuild unless explicitly safe;
- failed migration leaves database recoverable;
- schema version updated only after successful migration.

Before destructive migration, create a bounded backup if appropriate and simple.

Do not invent migrations for versions never released unless current code explicitly supports them.

---

# 27. DISK FULL / PERMISSION / I/O FAILURE AUDIT

Simulate where practical:

- read-only data root;
- unwritable SQLite;
- disk-full style SQLite failure/mock;
- credential permission failure;
- certificate unreadable;
- journal unreadable;
- malformed/corrupt local DB.

Required behavior:

- inference should not fail merely because telemetry accounting/export failed;
- deployment authority remains local;
- Admin surfaces degraded monitoring/accounting truth;
- no crash loop;
- no silent claim of complete analytics.

People mutation should refuse safely if directory persistence fails.

---

# 28. PROCESS LIFECYCLE / SIGNAL / RESTART AUDIT

Test real processes:

- SIGINT;
- SIGTERM;
- clean DB close;
- restart Admin;
- restart Command Center;
- restart intake;
- queued report survives;
- next periodic schedule survives;
- People survives;
- Command Center summaries survive.

Also simulate abrupt kill where practical, then restart and run SQLite integrity checks.

No requirement to survive SIGKILL without losing the final uncommitted operation; committed state must remain coherent.

---

# 29. TELEMETRY AGENT HEALTH

The Admin must be able to tell whether its local TelemetryAgent is functioning.

Audit thread lifecycle:

- starts when expected;
- does not start duplicate workers;
- catches bounded operational exceptions and continues;
- records last tick / last internal error locally;
- stopping Admin stops worker;
- restart resumes.

Do not call this customer deployment Online/Healthy.

This is local component status.

---

# 30. API CONTRACT / UI COHERENCE AUDIT

For every visible button/control/card:

- name backend source;
- prove backend exists;
- prove state mutation is real;
- prove refusal/error displays;
- prove refresh updates UI;
- prove disabled state matches backend authority.

Remove or mark unavailable any UI functionality not backed by real code.

For every backend capability intended for current administrators:
- ensure the UI exposes it where product requirements say it should.

Specifically audit:

- Stop/Release;
- model operations;
- inference;
- monitoring config;
- test report;
- People mutations;
- access intent;
- Command Center credential management;
- alias/tag;
- report history.

No mock controls.

---

# 31. MODELS EXPERIENCE COHERENCE AUDIT

Preserve the streaming/Netflix-like visual direction but verify data truth.

For every model card/group:

- family source;
- generation source;
- exact variant identity;
- artifact/digest;
- quantization if known;
- runtime/format;
- qualification;
- installed/running state;
- context/resource facts.

Unknown remains unknown.

Do not parse marketing names into planning truth.

No Recommended row unless a real recommendation exists.

Test model grouping cannot merge distinct exact identities.

---

# 32. DEPLOYMENT / SERVE AUTHORITY AUDIT

Reconfirm UI/monitoring changes have not weakened Stage-1 invariants:

- Plan does not authorize execution;
- ResourceManager remains sole physical admission authority;
- one reservation ledger;
- STOP != RELEASE;
- browser cannot choose pid/port/runtime/provider;
- native process reattachment still validates identity;
- provider stop/release path still correct;
- telemetry does not mutate serving;
- Command Center cannot mutate customer host.

Run architecture nonedge tests.

---

# 33. REPORT RETENTION VS ACCOUNTABILITY

When adding retention, preserve enough evidence to answer:

- what reports were received;
- when;
- trigger;
- sequence/gap;
- version;
- model/runtime;
- usage aggregates;
- acceptance/rejection.

Raw full report bodies may have shorter retention than structured metadata if needed.

Document exactly what is retained for:
- customer Admin;
- Command Center.

Do not silently make historical analytics disappear.

---

# 34. SERVER ACCEPTANCE PREFLIGHT — HARDEN IT

Upgrade the existing non-mutating preflight.

It should check/document at minimum:

## Customer host
- supported Python/version;
- architecture/OS basic eligibility;
- accepted wheel accessible;
- state/data root writable;
- secure POSIX credential storage support for current telemetry envelope;
- Admin loopback port available;
- SSH tunnel prerequisites;
- no public Admin bind.

## Business host
- Command Center data dir writable;
- UI port available;
- intake port available;
- cert file readable;
- private key readable;
- cert/key can be loaded together by an SSLContext;
- configured endpoint uses HTTPS;
- packaged static assets present.

Output:
- human-readable result;
- machine-readable JSON if simple;
- PASS / BLOCKED with exact reason.

No paid provisioning.

---

# 35. REAL-SERVER ACCEPTANCE PLAYBOOK AUDIT

Update:

`docs/machi/RUKAN-REAL-USER-ACCEPTANCE-V0.3.md`

Make it artifact-only.

Daniel should not need to infer hidden steps.

Include:

1. freeze/record wheel hash;
2. fresh install on customer host;
3. fresh install/start on business host/PC;
4. Command Center data root;
5. TLS intake;
6. issue credential;
7. Admin SSH tunnel;
8. pair monitoring;
9. explicitly choose Development/120s for test;
10. deployment/model/inference;
11. usage/tokens/latency;
12. People/users/teams/access intent;
13. periodic reports;
14. event reports;
15. settings report;
16. outage/retry;
17. restart;
18. stop/release;
19. Command Center portfolio;
20. privacy checks;
21. evidence capture;
22. cleanup.

Include expected observations for every step, not just commands.

Do not run it in this instruction.

---

# 36. LOCAL PRODUCTION-LIKE ACCEPTANCE

Run the entire topology locally using actual processes and the built artifact where possible.

Not mocks.

Required:

- packaged Admin;
- packaged Command Center;
- intake with local TLS;
- real credential pairing;
- People mutations through HTTP;
- inference path fixture/real local supported seam as repository permits;
- usage persistence;
- event report;
- at least 3 periodic Development heartbeats;
- event report between heartbeats;
- intake outage spanning a periodic slot;
- recovery/ACK;
- process restart;
- report gap/late sequence scenario;
- credential rotate/revoke;
- People PII canary;
- stop/release where safe fixture permits.

Record evidence.

---

# 37. SOAK / STABILITY TEST

Run a longer bounded local soak than the previous 2-report proof.

Target:
- at least 15 minutes with Development cadence;
- enough for multiple periodic slots;
- inject event reports;
- temporarily stop intake;
- restart it;
- restart Admin once;
- restart Command Center/intake once.

Verify:
- cadence returns to correct epoch phase;
- no duplicate trigger storm;
- queue remains bounded;
- no missing ACK cursor;
- no SQLite corruption;
- no accumulating exceptions;
- storage growth matches retention policy.

No user-visible time estimate; simply run it within the current execution.

---

# 38. MINI-FLEET + SOAK PERFORMANCE BOUNDS

Do not benchmark for enterprise scale.

But record practical local bounds:

- DB size after mini-fleet test;
- report count;
- average/maximum local import latency if easy;
- UI/API query still responsive;
- no lock failures.

If a query is obviously O(N²) over report history, fix it now.

Add indexes required by current production queries.

---

# 39. DOCUMENTATION TRUTH AUDIT

Audit all current docs against repository truth.

Update at minimum:

- `docs/machi/RUKAN.md`
- `docs/machi/RUKAN-ADMIN.md`
- `docs/machi/RUKAN-COMMAND-CENTER.md`
- `docs/machi/RUKAN-ANALYTICS.md`
- `docs/machi/RUKAN-CONNECTED-MONITORING-V0.3.md`
- `docs/machi/RUKAN-PEOPLE-ACCESS-V0.1.md`
- `docs/machi/RUKAN-REAL-USER-ACCEPTANCE-V0.3.md`
- `docs/machi/TELEMETRY.md`
- `docs/machi/ARCHITECTURE.md`
- `docs/machi/ROADMAP.md`
- `docs/DEBT.md`

Remove stale claims such as browser-local Command Center storage if still present.

Preserve historical evidence docs.

---

# 40. DEBT / READINESS REGISTER

In the production-readiness audit, list every remaining gap with:

- ID;
- classification;
- impact;
- workaround;
- owner/domain;
- whether it blocks server acceptance;
- whether it blocks controlled pilot;
- whether it blocks GA.

Do not scatter speculative TODOs through code.

Expected known limitations may include:
- no human Admin auth;
- no employee auth/gateway;
- no Windows secure telemetry credential adapter;
- no remote control;
- no public intake endpoint yet;
- physical breadth pending.

Their exact classification must be reasoned.

---

# 41. FULL QA GATES

Run all existing and newly added tests.

## Python
- full `tests/machi`;
- `tests/acceptance_lab`;
- focused telemetry;
- focused People;
- persistence/migration;
- security;
- artifact-only acceptance;
- mini-fleet;
- production-like local topology.

## Static
- ruff;
- mypy strict.

## Admin frontend
- unit/component tests;
- People full workflow tests;
- monitoring workflow;
- error/refusal cases;
- tsc;
- production build.

## Command Center
- report portfolio;
- reporting;
- credentials;
- analytics;
- late/gap/clock skew;
- XSS/render safety;
- tsc;
- production build.

## Artifact
- wheel;
- SHA256;
- clean source;
- isolated fresh venv install;
- no repo;
- no Node at runtime;
- packaged UI;
- `verify_machi.py`.

---

# 42. NO SILENT SKIPS

If an important test cannot run because:
- OpenSSL absent;
- OS capability absent;
- no external endpoint;
- platform unsupported;

record exactly:
- test;
- reason;
- classification;
- whether it blocks current readiness.

Do not convert missing prerequisites into PASS.

Local self-signed TLS is still expected where OpenSSL/SSL tooling is available; another safe local TLS fixture may be used.

---

# 43. PRODUCTION-READINESS REVIEW BEFORE TERMINAL STATUS

Before declaring PASS, re-read your own audit and ask:

1. Can a fresh server install the artifact with no source repo?
2. Does Admin start and serve its UI?
3. Does Command Center start and serve its UI?
4. Does telemetry survive outage/restart without losing/doubling usage?
5. Can one report be replayed safely?
6. Can 10 deployments report without cross-contamination?
7. Can People be managed fully through Admin?
8. Is effective access logically consistent?
9. Can PII/content leak to Command Center?
10. Can an unauthenticated external caller mutate customer state?
11. Can a malicious web Origin drive loopback Admin?
12. Are all unbounded stores addressed?
13. Do schema upgrades fail safely?
14. Does 2-minute Development cadence remain only an explicit test/development choice?
15. Does Production remain 6h?
16. Can Daniel follow the server playbook without repository knowledge?
17. Are all visible UI controls real?
18. Are unresolved GA gaps plainly documented?

If any answer is materially "no" and it is a server/pilot blocker, fix it before PASS.

---

# 44. TERMINAL STATUS

Use exactly one:

## PASS

`RUKAN_V0_3_PRODUCTION_CANDIDATE_READY_FOR_SERVER_ACCEPTANCE`

Only if:
- no SERVER_ACCEPTANCE_BLOCKER remains;
- no unresolved PILOT_BLOCKER remains in the bounded supported envelope;
- full local production-like evidence passes;
- artifact-only fresh install passes;
- real-server playbook is ready.

## NOT READY

`RUKAN_V0_3_NOT_READY_FOR_SERVER_ACCEPTANCE`

Use if a blocker remains that cannot responsibly be fixed in this run.

Do not downgrade a blocker merely to obtain PASS.

No external/server acceptance is run here.

---

# 45. PASTE BACK

Return a comprehensive structured report:

A. exact terminal status  
B. executive TL;DR  
C. starting/final SHA  
D. branch/origin/worktree  
E. supported production-candidate envelope  
F. GA exclusions  
G. architecture audit summary  
H. authority/ownership graph findings  
I. all findings by classification  
J. known previous defects closure  
K. People UI completion  
L. access-policy semantic model  
M. per-capability provenance  
N. directory/install binding  
O. cadence/development-production default behavior  
P. scheduler clock-jump/missed-slot evidence  
Q. usage delivery cursor/race solution  
R. event journal delivery audit  
S. telemetry stream/reset semantics  
T. report duplicate/collision semantics  
U. clock-skew handling  
V. telemetry config authority/install binding  
W. usage-accounting degradation behavior  
X. outbox state-machine/crash evidence  
Y. retention/compaction policy  
Z. sensitive-file permissions  
AA. SQLite/concurrency findings  
AB. mini-fleet results  
AC. Admin security audit  
AD. intake/TLS/security audit  
AE. Command Center trust/render audit  
AF. PII/privacy audit  
AG. model/deployment authority audit  
AH. packaged UI/artifact-only install evidence  
AI. migration/upgrade evidence  
AJ. I/O/disk/permission failure evidence  
AK. process restart/signal evidence  
AL. telemetry agent health  
AM. UI/backend coherence audit  
AN. documentation truth audit  
AO. preflight improvements  
AP. real-server acceptance playbook readiness  
AQ. local production-like acceptance evidence  
AR. soak evidence  
AS. full backend QA  
AT. frontend QA/builds  
AU. wheel/hash/isolated verification  
AV. debt/readiness register  
AW. exact remaining GA blockers  
AX. recommended next action: server acceptance or blocker remediation  
AY. git state  
AZ. STOP

Then STOP for Lead review.

# END INSTRUCTION
