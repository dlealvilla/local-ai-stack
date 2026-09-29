# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-FUNCTIONAL-PRODUCT-V0.3-FINISH-001`  
Status: `AUTHORIZED_IMPLEMENTATION_WITH_BOUNDED_ARCHITECTURE_REVIEW`  
Canonical baseline: `machi` at `d38a8e855f099f353e1ac090b990014eed67a826`  
Continue candidate branch: `rukan/connected-monitoring-v0.3`  
Current candidate source: `0e87b9cd80e52f2a0c0d528f41076b33f4c1ddf4`

This instruction supersedes `RUKAN-CONNECTED-MONITORING-V0.3-FIX-001`.

The goal is to **finish the connected-monitoring/product-cockpit section to a locally accepted, real-server-test-ready state**, while adding the customer-local People / Teams / future access foundation required by the Product Vision.

Do not perform paid or external server acceptance in this run.  
Do perform full local/internal integration testing and leave a precise real-server acceptance package ready for Daniel to execute later as the actual administrator/user.

The target product after this increment is:

```text
CUSTOMER RUKAN
├── Admin AI operations cockpit
│   ├── Overview
│   ├── Models
│   ├── Deployment
│   ├── Inference
│   ├── Analytics
│   ├── Activity
│   ├── People / Users & Teams
│   ├── System
│   └── Settings
│
├── local identity directory
│   ├── users
│   ├── teams
│   ├── memberships
│   └── future access intent
│
├── non-content usage accounting
├── material-change reporting
├── 2-minute DEVELOPMENT heartbeat
├── durable ACK-owned telemetry outbox
└── secure machine-authenticated upload
          |
          | one-way only
          v
RUKAN COMMAND CENTER
├── Overview
├── Deployments
├── Analytics
├── Model landscape
├── Reporting / Intake
├── Support
└── Settings
```

Future employee endpoint, authentication, chat, agent builder, LibreChat, Knowledge/RAG and remote control remain deferred.

---

# 0. REQUIRED ARCHITECTURE / PRODUCT REVIEW

Before code changes, re-read and reconcile:

- `docs/PRODUCT_VISION.md`
- `docs/machi/ARCHITECTURE.md`
- `docs/machi/ROADMAP.md`
- `docs/machi/TELEMETRY.md`
- `docs/machi/RUKAN.md`
- `docs/machi/RUKAN-ADMIN.md`
- `docs/machi/RUKAN-COMMAND-CENTER.md`
- `docs/machi/RUKAN-ANALYTICS.md`
- `docs/machi/RUKAN-CONNECTED-MONITORING-V0.3.md`
- `src/kultrun/identity/contracts.py` as historical design precedent only
- current Kernel/EventRecord/Store/ID patterns
- current Admin API/service composition
- current Command Center/intake
- current model catalog/warehouse/access seams
- current Plan/ResourceManager/Serve authority.

Extend the v0.3 design note with a section for:

- corrected telemetry state machine;
- cadence/profile architecture;
- development-vs-production heartbeat policy;
- People/Teams directory;
- access-intent semantics;
- future gateway seam;
- privacy/PII boundary;
- real-server acceptance topology.

## Cursor discretion

Cursor may challenge or modify exact Lead proposals where repository truth or a stronger product architecture supports it.

Material deviations must:
1. be written down;
2. state the alternatives considered;
3. explain Product Vision alignment;
4. preserve the required user-visible outcomes and invariants.

Do not use this discretion to remove:
- 2-minute development heartbeat;
- configurable cadence;
- independent periodic schedule;
- ACK-owned telemetry cursors;
- machine-authenticated upload;
- People/Teams backend;
- Admin management surfaces;
- test-readiness package.

---

# 1. FIRST CLOSE THE V0.3 TELEMETRY CORRECTION

Before broadening into People/Teams, close all issues identified by Lead review.

## 1.1 Periodic schedule independent of event reports

Current candidate incorrectly lets any report reset the periodic schedule.

Required:

- periodic reporting is an independent schedule;
- event-triggered reports do not postpone it;
- test reports do not postpone it;
- reporting-settings changes establish a new periodic schedule only when cadence/profile actually changes;
- periodic catch-up after an outage is bounded;
- no backfill storm.

## 1.2 Jitter/phase does not accumulate

Jitter establishes a stable per-install phase.

It must not be added again every interval.

For example, if the phase is +7 seconds:

```text
00:00:07
00:02:07
00:04:07
00:06:07
```

not:

```text
00:00:07
00:02:14
00:04:21
...
```

## 1.3 ACK owns delivery cursors

Composition persists a frozen report and proposed post-ACK state.

It does NOT advance authoritative delivery cursors.

Only a validated receiver ACK advances:

- next sequence;
- usage window cursor;
- journal cursor;
- last ACKed report id;
- last-ACKed model/runtime/version/SAFE baseline;
- periodic schedule if this report satisfied a periodic slot.

Send failure leaves these unchanged.

## 1.4 No silent unacknowledged report deletion

Prefer one outstanding frozen report.

While it is queued:
- new usage remains in the usage store;
- new journal events remain after the ACK cursor;
- new triggers remain pending.

After ACK, the next report picks them up.

Never silently delete an unacknowledged interval merely because a queue cap was reached.

## 1.5 ACK identity

A sender advances only after an ACK naming the exact report id sent.

Malformed/wrong-report acknowledgements leave the report queued.

## 1.6 Delivery timestamp

Persist/report:
- generated_at / created_at;
- delivered_at / acked_at.

Admin "Last successful report" means ACK time.

## 1.7 Command Center out-of-order semantics

Late reports are useful history but must not regress latest summary.

For sequence 1 → 3 → late 2:
- high/latest sequence remains 3;
- receipt time may update because a report arrived;
- report 2 remains marked out_of_order;
- current missing-sequence gap is recomputed and can resolve;
- latest trigger/latest-reported-state remains from the highest relevant report.

---

# 2. HEARTBEAT / OPERATIONAL REPORT CADENCE MUST BECOME PARAMETRIC

The current hours-only cadence is too rigid.

Create one authoritative typed telemetry cadence policy expressed internally in **seconds** or a similarly flexible duration unit.

Do not scatter values across:
- report contract;
- scheduler;
- Admin UI;
- Command Center;
- tests;
- CLI.

## Required profiles

### DEVELOPMENT — CURRENT DEFAULT DURING DEVELOPMENT

```text
profile: development
periodic interval: 120 seconds
stable jitter/phase: small, deterministic, test-friendly
```

A maximum phase around 0–10 seconds is reasonable.

The intent is that Daniel can observe repeated reports quickly when testing real deployments.

### PRODUCTION

```text
profile: production
periodic interval: 21,600 seconds (6 hours)
stable phase/jitter: up to the approved ~15 minutes
```

Production remains the eventual commercial default.

The **current development build/default must use the 2-minute profile**.

Admin and Command Center must make this visually explicit, for example:

> Development reporting cadence — every 2 minutes

not hide it as if this were the eventual production configuration.

## Custom cadence

Allow a bounded custom duration through one authoritative settings/API/CLI seam if it remains simple.

Suggested bounds:
- absolute technical minimum no lower than 30–60 seconds;
- normal customer UI should discourage very frequent production reporting;
- maximum 24 hours.

Cursor may refine bounds.

Do not require a contract/schema redesign to change from 2 minutes to 6 hours.

## Operational report contract

If the current `cadence_hours` field cannot accurately represent 120 seconds, correct it now.

Because v0.3 has not yet been promoted, it is acceptable to evolve the candidate contract/schema.

Prefer a field such as:
- cadence_seconds;
- cadence_profile;
or another explicit representation.

Preserve schema/version discipline and update golden fingerprints/tests.

---

# 3. DEVELOPMENT REAL-CLOCK LOCAL SOAK

In addition to deterministic fake-clock tests, run one local real-clock acceptance using the actual production service loop.

No paid server.

Use the development profile.

Required demonstration:

1. local customer-side Admin service/TelemetryAgent starts;
2. local Command Center + secure loopback HTTPS intake starts;
3. one credential is paired;
4. reporting is enabled;
5. one material/test report is sent;
6. then leave the processes running long enough to cross at least **two 2-minute periodic slots**;
7. prove those periodic reports arrive even if an event report occurred between them;
8. prove periodic phase does not drift;
9. show generated_at vs received_at/acked_at;
10. stop cleanly.

Do not use the browser as the scheduler.

Record bounded evidence in the paste-back and design/acceptance doc.

---

# 4. PREPARE REAL SERVER / REAL ADMINISTRATOR ACCEPTANCE — DO NOT RUN IT YET

Create:

`docs/machi/RUKAN-REAL-USER-ACCEPTANCE-V0.3.md`

This is an execution playbook for a later session where Daniel acts as the real customer administrator.

The playbook must be sufficiently complete that the next session can begin provisioning servers rather than redesigning the test.

## Test topology

At minimum document:

### Customer Rukan host
- real Rukan deployment;
- Admin backend/UI;
- model/runtime;
- telemetry agent;
- local user/team directory.

### Business side
- Rukan Command Center on Daniel's PC or dedicated operator host;
- persistent SQLite data;
- HTTPS telemetry intake reachable by the customer host.

## Admin access during test

Human authentication is not built.

Therefore do NOT expose Rukan Admin directly to the Internet.

Preferred test access:

```text
Daniel browser
   ↓
SSH local port forward
   ↓
127.0.0.1 Rukan Admin on customer server
```

Document exact generic SSH forwarding commands.

Alternative secure forwarding may be documented only if it does not weaken the no-auth boundary.

## Later test workflow

Prepare steps for Daniel to:

1. install/start Rukan from the accepted artifact;
2. open Admin through the tunnel;
3. inspect Overview/System;
4. browse Models;
5. select/deploy using only currently real controls;
6. run inference;
7. observe input/output token and latency analytics;
8. create users;
9. create teams;
10. assign memberships/access intent;
11. configure telemetry pairing;
12. observe event-trigger report in Command Center;
13. wait for 2-minute heartbeat reports;
14. change a permitted reporting/configuration setting;
15. observe settings-trigger report;
16. stop serving;
17. release reservation;
18. observe STOP/Release reports;
19. simulate telemetry outage;
20. verify queue/retry while inference/local Admin remain usable;
21. restore intake and verify delivery;
22. verify Command Center portfolio/history;
23. verify no employee PII/content was exported.

## Evidence checklist

Prepare an evidence template covering:

- artifact hash/build;
- host fingerprint without sensitive hostname/IP in committed docs;
- Admin screenshots/observations;
- model/runtime/deployment;
- usage counts/tokens/latency;
- report ids/sequences;
- generated/received/ACK time;
- heartbeat intervals;
- event triggers;
- retry;
- Command Center state;
- user/team directory behavior;
- privacy-negative checks;
- shutdown/cleanup.

Do not start RunPod or spend money in this run.

---

# 5. PEOPLE / USERS / TEAMS — PRODUCT FOUNDATION

The Product Vision explicitly requires employees, teams, permissions and identity.

We need the exoskeleton **before** building the employee chat/gateway.

Build a real customer-local People domain.

Do not treat this as a visual mock.

## Domain ownership

Rukan owns:
- user identity;
- team identity;
- membership meaning;
- access-policy intent;
- future access context semantics.

A future IdP/SSO provider will be an adapter, not the ontology.

## Historical precedent

`src/kultrun/identity/contracts.py` shows the old intent:
- platform-minted Subject;
- TeamId;
- AccessContext;
- applications/services can eventually be principals;
- team context travels with authorization.

Reuse the architectural lesson, not necessarily the exact code/schema.

---

# 6. USER CONTRACT

Create the smallest durable User concept appropriate for Rukan.

Required data:

- stable platform-minted `user_id`;
- canonical/normalized unique email for matching;
- display email;
- display name;
- status;
- created_at;
- updated_at;
- optional external identity reference seam;
- provenance/actor-origin metadata where appropriate.

## Status

Use honest local-directory semantics.

Candidate states:

- active;
- suspended;
- deactivated.

Do not use:
- invited;
- email_verified;
- logged_in;
- authenticated;
unless those actions genuinely exist.

An "active" directory user still cannot log in yet because employee authentication/gateway is deferred.

## Email

Email is required for this stage because it is the future provisioning/reconciliation handle.

Requirements:
- validate basic structure conservatively;
- normalize for uniqueness;
- preserve display/original form where useful;
- unique within a deployment;
- changing email is an audited/material directory change.

Do not send email in this increment.

Do not build invitation links.

Do not store passwords.

---

# 7. TEAM CONTRACT

Required:

- stable `team_id`;
- name;
- optional description;
- active/archived state;
- created_at;
- updated_at.

Team names are presentation/admin data and not authorization identifiers.

Team id is authoritative.

Support:
- create;
- rename/edit description;
- archive/reactivate where sensible;
- prevent destructive ambiguity.

If a team has members, archiving should preserve membership history rather than destructive delete.

---

# 8. MEMBERSHIP

Represent explicit user ↔ team membership.

Required:

- user id;
- team id;
- active relationship;
- created_at;
- actor/provenance.

Add/remove membership.

No hidden membership inferred from email/domain/name.

## Team role

Do not introduce a complex hierarchy.

If a simple role is genuinely useful now, keep it bounded (for example member / team_manager) and document future implications.

Otherwise defer team roles.

The key requirement now is membership, not RBAC depth.

---

# 9. ACCESS INTENT / FUTURE AUTHORIZATION SEED

We want administrators to begin expressing intended employee access before the actual employee endpoint exists.

Create a first-class access-intent contract/service.

It must be explicit that this is **configuration for future gateway enforcement**, not currently enforced employee authentication.

At minimum represent intent for:

- platform access enabled/disabled;
- future inference access allowed/denied;
- future user model-selection permission;
- future agent-builder opt-in/permission.

Cursor may adjust names after Product Vision review.

Do not add Knowledge/RAG permission controls before knowledge exists.

## Enforcement state

The backend/UI must expose something equivalent to:

```text
configured: true
enforcement: gateway_not_available
```

so an admin never believes a future employee can already log in/use inference.

## Team defaults + user override

Implement the smallest understandable model.

Recommended default:

- system default is deny for future end-user capability;
- active team can provide capability defaults/grants;
- user can have an explicit override;
- suspended/deactivated user always resolves to deny;
- platform access disabled always denies downstream future capabilities.

Do not create a generic ABAC/RBAC engine.

If multi-team composition becomes a real ambiguity, Cursor must explicitly document and choose a conservative deterministic rule.

A reasonable starting rule is:
- explicit user deny > explicit user allow > inherited team grant > default deny.

If Cursor prefers another rule, it must explain the security/product trade-off.

---

# 10. FUTURE ACCESS CONTEXT SEAM

We are deliberately preparing the future end-user gateway.

Add a pure/queryable resolver capable of producing a bounded future authorization context for a user:

- subject/user id;
- status;
- team ids;
- effective intended access;
- policy provenance;
- enforcement readiness.

This resolver does NOT authenticate the caller.

It does NOT expose an employee inference route.

It does NOT create a session/token.

Later gateway/auth can consume it after establishing who the user is.

Keep identity/access policy separate from vLLM/Ollama.

---

# 11. PEOPLE PERSISTENCE

Do not store People data in:
- telemetry SQLite;
- Command Center database;
- model store;
- browser localStorage.

Use a customer-local Rukan-owned persistence boundary.

Preferred architecture:

```text
People/Identity domain contracts
        ↓
Directory/People service
        ↓ persistence port
        ↓
SQLite local adapter (v0)
```

or another equally small repository-consistent adapter.

SQLite is a reasonable v0 choice because:
- search/list/membership queries matter;
- future gateway reads need concurrency;
- migrations matter.

But Cursor may use an existing Rukan Store if it cleanly supports the access patterns without creating a second identity truth.

There must be exactly one local directory authority.

Version schema/migrations from the beginning.

---

# 12. PEOPLE PRIVACY

This is a hard boundary.

Names, emails, memberships and external identity refs are PII/restricted customer data.

They stay local.

They must NOT enter:
- operational reports;
- Command Center;
- analytics bundle;
- vendor telemetry;
- support snapshot;
- model usage rollups;
- raw logs.

Do not even export email hashes in this increment.

Command Center does not need people data.

Later aggregate counts require a separate explicit privacy/product decision.

Activity events intended for vendor export must use no employee PII.

Local Admin activity may reference safe local ids and display local directory details through local joins.

---

# 13. ADMIN API — PEOPLE

Add narrow loopback Admin API seams.

Exact REST style may follow existing conventions.

Needed capabilities:

## Users
- list/search;
- read detail;
- create;
- edit display name/email;
- suspend;
- reactivate;
- deactivate;
- update access intent.

## Teams
- list/search;
- read;
- create;
- edit;
- archive/reactivate.

## Memberships
- add user to team;
- remove;
- list by user/team.

## Access
- effective-access-intent projection;
- enforcement readiness.

Do not add:
- password reset;
- invite sending;
- login token;
- SSO;
- API key for end user.

All mutation routes remain loopback-only behind the existing Admin origin boundary.

---

# 14. ADMIN UI — ADD PEOPLE / USERS & TEAMS

Add a real customer-facing Admin surface.

Use the label **People** or **Users & Teams** after UX review.

Recommended navigation after this increment:

- Overview
- Models
- Deployment
- Inference
- Analytics
- Activity
- People
- System
- Settings

Do not put the entire user directory on Overview.

A small summary may be shown only if useful:
- active users;
- teams;
- access configuration readiness.

## People landing view

Business-friendly, not IAM jargon-first.

Provide:
- user count;
- active/suspended count;
- team count;
- search;
- Users / Teams tabs or equivalent;
- clear banner:
  > Employee login and chat endpoint are not enabled yet. Access settings here prepare future provisioning.

## User row/detail

Show:
- name;
- email;
- stable user id in technical details;
- status;
- teams;
- access intent;
- enforcement readiness;
- created/updated;
- recent local activity.

Actions:
- edit;
- suspend/reactivate;
- deactivate;
- manage teams;
- manage access intent.

Use confirmation for destructive/deactivation operations.

## Team view

Show:
- team name;
- member count;
- access defaults/intents where supported;
- active/archive;
- members.

## Access controls

Where contracts support them:

- Platform access
- Inference access
- User model selection
- Agent Builder

For future-only capabilities display:
**Configured — enforcement begins when the employee gateway/capability is enabled.**

Do not present them as working employee access today.

---

# 15. DIRECTORY ACCOUNTABILITY / AUDIT

Every meaningful mutation must create local accountability evidence.

Required events/actions:

- user.created;
- user.updated;
- user.status_changed;
- team.created;
- team.updated;
- team.archived / reactivated;
- membership.added;
- membership.removed;
- access_intent.changed.

Record:
- timestamp;
- actor origin;
- stable affected user/team id;
- action;
- outcome;
- safe before/after policy state where appropriate.

Do not put email/display name into vendor-exportable EventRecord payloads.

Prefer privacy `restricted` for directory-specific events.

Admin Activity should render friendly local details by joining the local directory.

These events must not trigger vendor telemetry in v0.3 unless they can be projected without PII and there is a clear product need.

Default: directory changes stay local only for this increment.

---

# 16. ADMIN OVERVIEW / PRODUCT COHERENCE PASS

Revisit Admin after adding People.

The goal is not more widgets.

Overview should remain the fast answer to:

1. Is AI ready?
2. What model/capability is active?
3. How much is it being used?
4. Is anything requiring attention?
5. What changed recently?
6. Is monitoring working?

Optional small People summary is secondary.

Keep detailed:
- analytics;
- user directory;
- system;
- settings;
off the main control pane.

Use progressive disclosure.

---

# 17. MODELS — PRESERVE THE STREAMING-LIBRARY DIRECTION

Do not regress the Netflix-like model browsing experience.

Keep:
- Family / Series;
- Generation;
- concrete Variant.

Variant may show:
- parameters/size where real;
- instruct/base;
- quantization;
- artifact/provider type;
- context;
- runtime;
- qualification;
- installed/running;
- SAFE resource fit;
- usage.

Do not invent metadata.

Exact artifact/digest remains authoritative.

Do not build employee model access enforcement yet, but the future People access-intent model should be compatible with:
- managed/default model;
- user may select from permitted models.

Do not prematurely add per-user model allowlists unless the Product Vision review shows a clear need in this increment.

---

# 18. ADMIN SETTINGS — CADENCE / MONITORING UPDATE

Monitoring Settings must now expose the parametric cadence cleanly.

Show:
- Reporting enabled;
- Profile: Development / Production / Custom;
- Current interval;
- Current stable phase/jitter;
- Next periodic report;
- Last successful ACK time;
- queued/unacknowledged report;
- endpoint;
- credential status/key id;
- privacy categories;
- Preview next report;
- Send test report.

In current development build:
- default profile = Development;
- interval = 2 minutes.

The UI should make it hard to mistake this for commercial production behavior.

Do not expose credential secret after initial configuration.

---

# 19. COMMAND CENTER — CADENCE / REPORTING UPDATE

Command Center should understand report cadence in seconds/duration, not hours-only.

For each deployment, show:
- configured profile/interval from latest report;
- Last report received;
- age;
- expected next-report window where meaningful;
- reporting later than expected based on latest configured cadence.

Still do NOT say Online/Offline.

During current development profile, a row can truthfully say:

> Development cadence: every 2 min  
> Last report received: 1m 12s ago

No production SLA inference.

---

# 20. COMMAND CENTER MUST NOT RECEIVE PEOPLE DATA

Explicitly test that the new directory never appears in:

- operational reports;
- report preview;
- Command Center reports;
- support snapshot;
- cross-deployment analytics;
- rejected request logs.

Search serialized report bodies for test names/emails and fail if present.

---

# 21. LOCAL END-TO-END FUNCTIONAL TESTING

Perform internal local integration tests only.

Required scenarios:

## Telemetry correctness
- independent 2-minute periodic schedule;
- event reports between periodic slots;
- stable phase;
- ACK-owned cursor;
- retry;
- restart;
- wrong ACK;
- out-of-order reports;
- late gap fill;
- delivered timestamp;
- no unacked deletion.

## Usage
- native parser;
- Ollama parser;
- missing token counts;
- latency;
- failure record;
- purpose separation;
- aggregation.

## People
- create two users;
- duplicate email refusal;
- edit email;
- suspend/reactivate;
- deactivate;
- create two teams;
- membership add/remove;
- team archive;
- access intent changes;
- deterministic effective policy;
- inactive user denies;
- persistence/restart;
- schema migration;
- concurrent safe reads if applicable;
- no password/auth data.

## Privacy
Create obvious canary:
- user name;
- employee email;
- fake prompt;
- fake response;
- fake secret.

Prove none appear in vendor operational report or Command Center database/report surfaces.

---

# 22. REAL-CLOCK 2-MINUTE SOAK

Run after deterministic tests.

Use actual service processes and local HTTPS.

Observe at least two periodic intervals.

Capture:

- periodic report 1;
- event-triggered report between intervals;
- periodic report 2 still arrives on original phase;
- period approximately 120 seconds;
- no cumulative phase drift;
- Command Center receives all;
- Admin shows correct last ACK and next due.

A total local soak around 5–7 minutes is acceptable.

This is local internal testing, not the later server campaign.

---

# 23. REAL-SERVER TEST READINESS ARTIFACTS

In addition to the playbook, leave:

## A. Preconditions checker

Add a small non-mutating command/script that can verify a candidate test setup has:
- compatible Rukan artifact;
- required local ports available;
- SSH access/tunnel prerequisites described;
- Command Center data root writable;
- telemetry HTTPS endpoint configuration placeholders;
- certificate/key paths when later supplied;
- no need to expose Admin publicly.

It must not provision paid infrastructure.

## B. Evidence directory/template

Provide a gitignored or documented operator evidence layout such as:

```text
acceptance-evidence/
  customer-host/
  command-center/
  screenshots/
  report-ids.txt
  usage-summary.json
  checklist.md
```

Do not commit customer/server secrets.

## C. Exact run commands

Document:
- customer Admin service;
- Command Center service;
- telemetry intake;
- credential issue;
- customer pairing;
- SSH tunnel;
- test-report;
- stop/restart;
- evidence queries.

## D. Cleanup

Document safe cleanup of only explicitly test-owned state.

Do not conflate with product Steward cleanup.

---

# 24. SERVICE / ALWAYS-ON READINESS

For testing, the following must be capable of long-running foreground operation:

Customer side:
- Rukan Admin/backend;
- TelemetryAgent as composed by it.

Business side:
- Command Center;
- telemetry intake.

Ensure:
- SIGINT/SIGTERM or normal process stop closes DBs cleanly where current architecture supports it;
- restart resumes outbox/scheduler;
- data roots explicit;
- logs/output bounded.

Do not build full OS installers/service registration unless trivially supported.

If useful, provide Linux `systemd` example units in the acceptance doc **as examples only**, not product ontology, and do not install them.

Cross-platform service packaging remains later.

---

# 25. SECURITY / PRIVACY INVARIANTS

Preserve all:

- Admin loopback-only;
- Admin not exposed unauthenticated;
- external intake write-only;
- non-loopback intake requires TLS;
- per-deployment machine credential;
- credential bound to install id;
- secret hashed on receiver;
- customer secret local and protected;
- no remote control;
- telemetry failure never blocks inference/deployment;
- no prompt/response export;
- no People PII export;
- no passwords;
- no fake login/session;
- no raw logs shipped.

Document current POSIX-only secure credential-file limitation.

Do not weaken it for Windows.

---

# 26. FUTURE END-USER / GATEWAY BOUNDARY

Do not build it now, but explicitly document what this increment hands to the next stage.

The future employee path should conceptually be:

```text
employee identity/auth provider
        ↓ establishes user
Rukan AccessContext / directory resolver
        ↓ authorization
Rukan gateway
        ↓
model/routing policy
        ↓
authorized ServingInstance
        ↓
usage record with user/team attribution
        ↓
employee chat / LibreChat / first-party client
```

The gateway must later enforce:
- active user;
- team membership;
- inference access;
- model-selection permission;
- knowledge/tool policy;
- rate/quota where introduced.

LibreChat/Open WebUI must remain clients behind Rukan policy/gateway, not the identity authority.

Agent Builder later consumes the same subject/team/access foundation.

---

# 27. NON-GOALS

Do NOT implement:

- employee login;
- passwords;
- email sending/invite links;
- OIDC/SAML/LDAP;
- end-user bearer tokens;
- employee inference gateway;
- employee chat;
- LibreChat/Open WebUI integration;
- Agent Builder;
- Knowledge/RAG;
- per-document permissions;
- user/team inference attribution in production traffic before gateway exists;
- general RBAC/ABAC framework;
- licensing;
- billing;
- remote customer control;
- remote model selection;
- online/offline semantics;
- public server test;
- RunPod spend;
- physical GPU qualification.

---

# 28. DOCUMENTATION

Update:

- `docs/machi/RUKAN-CONNECTED-MONITORING-V0.3.md`
- `docs/machi/RUKAN.md`
- `docs/machi/RUKAN-ADMIN.md`
- `docs/machi/RUKAN-COMMAND-CENTER.md`
- `docs/machi/TELEMETRY.md`
- `docs/machi/ARCHITECTURE.md`
- `docs/machi/ROADMAP.md`
- `docs/DEBT.md`

Add:

- `docs/machi/RUKAN-PEOPLE-ACCESS-V0.1.md`
- `docs/machi/RUKAN-REAL-USER-ACCEPTANCE-V0.3.md`

Keep Product Vision semantics authoritative.

Do not rewrite historical evidence.

---

# 29. QA

Run all prior v0.3 QA plus:

## Telemetry correction suite
- independent schedule;
- 2-minute dev profile;
- production 6-hour profile;
- custom cadence;
- stable phase;
- cadence-change reschedule;
- event/test reports do not move periodic;
- ACK-owned cursor;
- restart before/after ACK;
- wrong ACK;
- gap reconciliation;
- delivery timestamps;
- no unacknowledged deletion.

## Directory suite
- IDs;
- unique normalized email;
- CRUD;
- status transitions;
- teams;
- membership;
- access intent;
- effective resolution;
- persistence/migrations;
- restricted privacy;
- activity/audit;
- no People export.

## API/UI
- People list/create/edit/status/team/access flows;
- Admin cadence/profile UI;
- current monitoring data;
- accessibility/empty/error states;
- Command Center cadence/report-age display.

## Full
- `tests/machi`;
- `tests/acceptance_lab`;
- ruff;
- mypy strict;
- Admin Vitest/TypeScript/build;
- Command Center Vitest/TypeScript/build;
- wheel build;
- isolated wheel verification.

---

# 30. ACCEPTANCE

Pass requires:

### Telemetry
- correction items are closed;
- development default cadence is 120 seconds;
- production profile remains 6 hours;
- one central parametric cadence seam;
- local real-clock soak proves repeated periodic reporting;
- event reports do not postpone heartbeat;
- ACK owns source cursors;
- delivery timestamps truthful.

### Usage
- input/output tokens captured where runtimes report;
- latency persisted;
- no content persisted/exported.

### People
- real persisted User/Team/Membership domain;
- email/stable ids;
- real Admin CRUD;
- access-intent configuration;
- effective future-access resolver;
- enforcement-readiness explicit;
- PII remains local;
- activity/audit exists.

### Product
- Admin coherent with People added;
- Models library remains strong;
- Command Center coherent;
- no fake functionality.

### Test readiness
- server acceptance playbook complete;
- preconditions/evidence/commands prepared;
- no external/paid test performed.

Terminal status on success:

`RUKAN_V0_3_FUNCTIONAL_LOCAL_PASS_SERVER_TEST_READY`

Do not claim external connected acceptance.

---

# 31. PASTE BACK

Return:

A. exact status  
B. TL;DR  
C. starting/final SHA  
D. branch/worktree  
E. architecture review/deviations  
F. telemetry correction state machine  
G. cadence policy/profile design  
H. 2-minute dev heartbeat evidence  
I. 6-hour production profile preservation  
J. ACK/cursor semantics  
K. out-of-order/gap semantics  
L. usage accounting  
M. People domain contracts  
N. People persistence/schema  
O. Users API  
P. Teams/membership API  
Q. access-intent/effective resolver  
R. People privacy  
S. People/Admin activity auditing  
T. Admin navigation/Overview  
U. Admin Models experience  
V. Admin People experience  
W. Admin Analytics/Activity  
X. Admin Settings/Monitoring  
Y. Command Center cadence/reporting changes  
Z. Command Center portfolio/analytics/model state  
AA. local real-clock soak  
AB. real-server acceptance playbook  
AC. preconditions checker/evidence layout  
AD. exact later server test commands/topology  
AE. privacy/security review  
AF. frontend QA  
AG. backend QA  
AH. build/wheel evidence  
AI. schema migrations  
AJ. known limitations/debt  
AK. precise next stage handoff for employee gateway/chat/agent builder  
AL. git state  
AM. STOP

Then STOP for Lead review.

# END INSTRUCTION
