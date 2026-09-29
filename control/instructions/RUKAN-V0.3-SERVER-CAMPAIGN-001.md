# RUKAN v0.3 AUTONOMOUS SERVER CAMPAIGN

Instruction ID: `RUKAN-V0.3-SERVER-CAMPAIGN-001`
Status: `QUEUED_FOLLOW_UP`
Prerequisite terminal status:
`RUKAN_V0_3_PRODUCTION_CANDIDATE_READY_FOR_SERVER_ACCEPTANCE`

This instruction is authorized only after the post-audit accountability correction has been completed and independently re-proved by the executing Cursor run.

It performs a bounded, autonomous, evidence-driven real-server campaign intended to discover integration defects that local tests cannot expose, repair them through normal version-controlled engineering, and finish with three consecutive clean fresh-server confidence runs on one immutable release candidate.

No additional Daniel instruction is required unless a binding safety/authentication/hang gate requires it.

---

# 0. FIRST PRINCIPLE

The goal is NOT:

> make eight green runs.

The goal is:

> use real server evidence to make the bounded Rukan v0.3 product robust.

Every server failure or inconsistency is information.

Do not paper over it.

The campaign lifecycle is:

```text
candidate
   ↓
real server
   ↓
observe
   ↓
classify
   ↓
causal analysis
   ↓
design robust fix
   ↓
local regression
   ↓
version-controlled fix
   ↓
full relevant QA
   ↓
new immutable candidate
   ↓
real server again
```

Once robust:

```text
frozen candidate
   ↓
fresh server confidence 1
   ↓
fresh server confidence 2
   ↓
fresh server confidence 3
   ↓
campaign PASS
```

No accepted hot patches on the server.

---

# 1. CAMPAIGN ENTRY GATE

Before provisioning any server, verify:

- current source branch contains the completed requirements of:
  `RUKAN-V0.3-PRODUCTION-READINESS-FIX-001`;
- its terminal result is:
  `RUKAN_V0_3_PRODUCTION_CANDIDATE_READY_FOR_SERVER_ACCEPTANCE`;
- no SERVER_ACCEPTANCE_BLOCKER remains in the production-readiness audit;
- no PILOT_BLOCKER remains in the declared POSIX/NVIDIA pilot envelope;
- working tree is clean except explicitly approved evidence/proposal files;
- implementation is pushed;
- full local QA passed;
- exact wheel exists;
- SHA256 exists;
- artifact-only install proof passed;
- packaged Admin and Command Center UIs passed;
- server acceptance playbook is current.

If the prerequisite fix is NOT actually complete:
- do not provision;
- return to that correction;
- finish it;
- rerun its QA;
- only then enter this campaign.

---

# 2. CAMPAIGN BRANCH AND VERSION CONTROL

After entry gate succeeds:

Create or reset only from the accepted prerequisite commit:

`rukan/v0.3-server-campaign`

Do not move canonical `machi`.

Do not rewrite accepted history.

Create:

`docs/machi/RUKAN-V0.3-SERVER-CAMPAIGN.md`

and a sanitized evidence tree such as:

```text
evidence/
  rukan-v0.3-server-campaign/
    campaign.json
    iteration-01/
      run.json
      findings.md
      telemetry-summary.json
      system-summary.json
      privacy-check.json
      cost.json
    iteration-02/
    ...
    confidence-01/
    confidence-02/
    confidence-03/
```

If repository policy prefers evidence under docs or another existing location, follow repository truth.

Never commit:
- bearer secrets;
- TLS private keys;
- passwords;
- actual user/customer content;
- raw prompts;
- raw responses;
- provider API tokens;
- sensitive absolute operator paths.

Synthetic test email/name values may appear in sanitized evidence only if intentionally fake and clearly marked.

For every tested artifact record:
- source commit;
- build id;
- wheel filename;
- SHA256;
- clean-source result.

Never rebuild a tested artifact after declaring its hash for that iteration.

A code change means a new commit and a new artifact identity.

---

# 3. CAMPAIGN BUDGET AND PROVIDER SAFETY

All existing RunPod policy remains binding.

Use only official:
- RunPod agent skill;
- RunPod MCP;
- runpodctl.

No custom RunPod client.

## Ownership

Cursor may manage only Pods created by Cursor for this exact campaign.

Never:
- stop;
- terminate;
- mutate;
- attach storage to

a pre-existing or ambiguously owned Pod.

Record owned Pod id immediately after creation.

## Limits

- one concurrent Pod maximum;
- NVIDIA only for this campaign unless an existing required test proves otherwise;
- maximum NVIDIA rate: $1.50/hour;
- maximum Pod lifetime: 90 minutes;
- maximum provisioning retries: 3;
- no network volume;
- session maximum: $40;
- daily maximum: $80;
- account balance floor: $0.50.

Before every Pod creation:
- query live balance;
- query live hourly price;
- identify other observed account burn if available;
- compute safe planned runtime;
- guarantee projected balance remains >= $0.50.

Additional campaign economy target:
- total campaign infrastructure spend <= $15.

If the next required Pod would exceed the $15 campaign target:
- do not create it;
- publish current evidence and why more spend is needed;
- return `RUKAN_V0_3_SERVER_CAMPAIGN_NOT_READY`.

## Hardware selection

Prefer the cheapest available previously proven/supported NVIDIA candidate with sufficient capacity.

Preferred order should be evidence-driven, not hardcoded, but:
- A40;
- L40S;
- another previously accepted NVIDIA family

are preferable to introducing unqualified breadth.

Use a very small known acceptance model to minimize download/runtime cost.

Do not use an expensive GPU to prove a software property that a cheaper supported GPU can prove.

## Pod lifecycle

On successful run:
- collect evidence;
- copy evidence off the Pod;
- terminate owned Pod.

On terminal product failure:
- collect evidence;
- terminate owned Pod.

On a hang:
- STOP the owned Pod;
- DO NOT terminate it;
- preserve evidence;
- ask Daniel before termination, per binding policy;
- campaign pauses.

---

# 4. TEST TOPOLOGY

Default minimal topology:

```text
ONE DISPOSABLE SERVER

Customer Rukan plane
  state root A
  Admin 127.0.0.1:<admin-port>
  runtime/model
  telemetry sender
  People directory

Business plane
  data root B
  Command Center 127.0.0.1:<cc-port>
  intake 127.0.0.1:<intake-port> with real TLS
  credentials DB

Telemetry:
Customer Rukan
  -> HTTPS
  -> machine credential
  -> Command Center intake
```

The two planes may share the OS host for campaign economy, but:

- they MUST use separate product data roots;
- the Customer side may never write Command Center SQLite directly;
- Command Center may never read/mutate ResourceManager state directly;
- communication for automatic reporting must use the actual telemetry HTTP path;
- Admin and Command Center remain separate local web services.

## TLS

Create a campaign-only CA and server certificate.

Certificate SAN must match the exact endpoint used by telemetry.

For the accepted test path:
- `local_test=false`;
- normal TLS verification enabled;
- hostname verification enabled;
- trust the campaign CA explicitly through standard client trust configuration;
- do not use `ssl._create_unverified_context()` as the acceptance proof;
- do not modify production telemetry code to trust arbitrary certs.

Local-test HTTP may still exist in unit tests, not as the campaign acceptance route.

---

# 5. DIAGNOSTIC PHASE — MAXIMUM FIVE ITERATIONS

Run at most five diagnostic iterations.

Number them:
- D1;
- D2;
- D3;
- D4;
- D5.

A diagnostic iteration is one complete evidence loop, not merely one test command.

## Reusing a Pod

To minimize cost, a Pod may be reused between diagnostic iterations only if:
- the observed defect is not host-bootstrap/fresh-host related;
- fresh state can make the next run independent;
- there is no contamination risk;
- the server remains stable.

When reusing:
- new virtualenv;
- new Rukan state root;
- new Command Center data root;
- new InstallId;
- new telemetry stream;
- new machine credential;
- remove only campaign-owned prior test state after evidence is copied;
- install the new wheel from scratch.

Use a fresh Pod if:
- installation/bootstrap failed;
- dependency contamination is suspected;
- state leakage is suspected;
- process or driver state is suspicious;
- current Pod experienced a product/runtime hang;
- moving into confidence phase.

## Early diagnostic completion

Diagnostic phase may end before D5 only after:

**two consecutive clean diagnostic iterations**

with:
- no PRODUCT_DEFECT;
- no SERVER_ACCEPTANCE_BLOCKER;
- no PILOT_BLOCKER;
- no unexplained usage/report mismatch;
- no hidden manual recovery.

They may use the same code candidate.

If a code fix occurs after one clean diagnostic run:
- the clean streak resets.

---

# 6. EACH DIAGNOSTIC ITERATION — PRE-RUN

Before starting:

1. record run id;
2. record current source SHA;
3. record exact wheel SHA;
4. verify source branch pushed;
5. establish balance/rate;
6. provision or verify owned Pod;
7. capture provider/server facts;
8. create fresh acceptance directories;
9. install exact wheel into fresh venv;
10. confirm repository source is not required at runtime.

Capture at least:
- OS;
- architecture;
- CPU;
- RAM;
- GPU type/count;
- VRAM;
- NVIDIA driver;
- relevant CUDA/runtime facts;
- storage total/free;
- Python version;
- wheel/build identity.

Do not treat these observations as product authorization if another product domain owns that authority.

---

# 7. EACH DIAGNOSTIC ITERATION — START BUSINESS PLANE

Create fresh Command Center data root.

Start packaged Command Center from the wheel.

Verify:
- binds loopback;
- packaged UI returns HTML/JS/CSS;
- SQLite initializes/migrates;
- status endpoint works;
- data root is writable;
- files have secure supported-host permissions.

Create campaign TLS CA/cert.

Start telemetry intake with TLS.

Verify:
- GET is write-only/refused;
- bad bearer rejected;
- malformed report rejected;
- public/read/control Command Center APIs are not exposed by intake listener.

Issue one telemetry credential for the Customer InstallId only after the Customer InstallId is established.

If order requires Customer installation first, stage intake/cert now and issue credential after InstallId exists.

---

# 8. EACH DIAGNOSTIC ITERATION — START CUSTOMER PLANE

Install/start Rukan from wheel only.

No repo checkout.

No Node.

Admin:
- loopback only;
- packaged UI;
- normal service start.

Use the same commands that the server acceptance playbook will expose to Daniel.

Verify:
- Overview;
- System;
- Models;
- Deployment;
- Inference;
- Analytics;
- Activity;
- People;
- Settings

load from real APIs.

Where browser automation is unavailable, exercise the same backing HTTP APIs and static UI delivery; document the limitation.

---

# 9. PEOPLE WORKFLOW PER SERVER RUN

Use only synthetic campaign People.

Example domain:
`example.invalid` or `example.test`.

Exercise at least:
- create user A;
- create user B;
- create team;
- edit one user;
- suspend/reactivate one user;
- add membership;
- remove/re-add membership;
- set team access intent;
- set user override;
- inspect effective access;
- prove Platform deny closes subordinate capabilities.

At least one diagnostic iteration should also:
- archive/reactivate team;
- deactivate a user.

Verify:
- persisted after Admin restart;
- no PII in operational report bytes;
- no PII in Command Center DB;
- no People data in support snapshot/export bundle.

---

# 10. DEPLOYMENT / MODEL / INFERENCE WORKFLOW

Use the smallest accepted model/runtime combination practical for the selected host.

Do not introduce a new large model just for testing.

Exercise:

1. inspect model state;
2. acquire/import only if required by the accepted real workflow;
3. select/deploy through current architecture;
4. ResourceManager admission;
5. Serve start;
6. readiness;
7. inference;
8. additional inference;
9. stop;
10. explicit release;
11. restart/redeploy at least where the run plan calls for it.

At least 3 real inference calls per server run.

Record:
- model identity;
- exact artifact/digest;
- runtime/macropath;
- request count;
- input tokens when runtime reports them;
- output tokens;
- latency;
- outcome/failure;
- ServingInstance;
- reservation;
- Witness.

Prompts should be synthetic and non-sensitive.

Do not store raw prompt text in campaign committed evidence.

---

# 11. AUTOMATIC TELEMETRY WORKFLOW

Configure:

`Development = 120 seconds`

explicitly.

Production default remains 21600 seconds.

Verify actual configured state.

For each diagnostic run collect at least:
- one initial/test/material report;
- three periodic heartbeats;
- one deployment READY report;
- one stop/release related report;
- one settings/configuration report where current product supports a material telemetry setting change.

Confirm:
- event report does not move periodic phase;
- generated_at;
- received_at;
- ACK time;
- sequence;
- stream id;
- usage cursor;
- report triggers;
- cumulative usage;
- incremental rollups.

At least one diagnostic run must verify:
- 33+ rollup grouping backlog handling if the final local fix added bounded batching;
- cumulative remains monotonic across retention/compaction test seam where practical;
- telemetry stream reset semantics through a controlled local telemetry DB reset on server, without deleting customer operational truth.

The stream-reset destructive action must touch only campaign telemetry state and must be explicitly planned/evidenced.

---

# 12. OUTAGE / RETRY / RESTART

At least one diagnostic iteration must execute:

1. intake running;
2. successful report;
3. stop intake cleanly;
4. cross one 120-second heartbeat slot;
5. perform inference while intake is unavailable;
6. verify inference remains functional;
7. verify frozen queued report;
8. restart intake;
9. verify automatic resend/ACK;
10. verify usage not lost or duplicated.

At least one diagnostic run:
- restart Admin;
- restart Command Center;
- restart intake.

Verify persistence and schedule recovery.

If same defect has already been proven and fixed in prior server iteration, later diagnostic iterations may use a smaller restart slice, but confidence phase still requires service restart evidence.

---

# 13. FAILURE AND DATA COHERENCE CHECKS

After each run reconcile source and receiver.

Compare:

Customer usage source:
- source usage sequences;
- requests;
- input/output tokens;
- success/failures.

Report stream:
- report sequence;
- rollups;
- cumulative.

Command Center:
- accepted reports;
- usage rollups;
- portfolio totals;
- model landscape totals.

Required:
- no lost usage;
- no duplicate usage;
- cumulative monotonic within stream;
- backlog drains;
- current stream correct;
- late historical stream does not regress current summary;
- no cross-install contamination.

Any unexplained mismatch is a PRODUCT_DEFECT until disproved.

Do not accept "close enough" for integer request/token accounting.

Latency may differ by defined aggregation semantics; explain expected difference.

---

# 14. PRIVACY / SECURITY CANARIES

Generate synthetic canaries:

- fake employee name;
- fake employee email;
- fake team name;
- fake prompt marker;
- fake response marker if a fixture needs one;
- fake bearer-like secret marker;
- fake document marker.

After server workflow, search:
- telemetry report documents;
- outbox;
- Command Center database;
- support snapshot;
- analytics bundle;
- intake rejection evidence;
- committed evidence output.

Expected:
- People/PROMPT/RESPONSE/DOCUMENT/SECRET canaries absent from vendor/Command Center reporting data;
- local customer directory may contain synthetic People canaries;
- local runtime may transiently process synthetic prompt; product operational stores must not persist it unless explicitly designed otherwise.

A canary leak is a PILOT_BLOCKER.

---

# 15. FINDING CLASSIFICATION

Every deviation gets one:

## PRODUCT_DEFECT
Rukan code/contract/state semantics wrong.

## TEST_HARNESS_DEFECT
Campaign orchestration/evidence/test tooling wrong.

## PROVIDER_ENVIRONMENT_DEFECT
RunPod/provider-specific availability/network/storage failure not caused by Rukan.

## UNSUPPORTED_HOST
Host outside declared support envelope.

## EXPECTED_LIMITATION
Known documented bounded product limitation.

## OPERATOR_ERROR
Campaign command/config error.

For each finding record:
- run id;
- timestamp;
- symptom;
- exact evidence;
- classification;
- affected invariant;
- reproducibility;
- severity;
- proposed next step.

Do not relabel a PRODUCT_DEFECT as provider noise without causal evidence.

---

# 16. PRODUCT DEFECT CORRECTION LOOP

For every PRODUCT_DEFECT:

## A. Reproduce

Attempt the smallest local reproduction.

If server-only:
- create the smallest deterministic server reproduction script/test;
- preserve the failing evidence.

## B. Invariant

Write:
- what invariant failed;
- why existing tests missed it;
- correct domain owner.

## C. Design

Before modifying code, choose the robust solution.

Reject:
- UI-only workaround for backend state bug;
- test-specific branch;
- hardcoded Pod/GPU id;
- arbitrary sleep as correctness;
- swallowing exception;
- resetting DB to hide migration issue;
- disabling TLS/auth/safety.

Prefer:
- typed state;
- durable cursor;
- transaction;
- explicit lifecycle;
- domain-owned policy;
- idempotent operation;
- bounded retry.

## D. Regression first

Add a failing test before or with the fix where feasible.

The regression must reproduce the actual semantic bug, not merely assert the final screenshot.

## E. Fix

Commit code on campaign branch.

Use iteration-aware commit message.

## F. Local proof

Run targeted tests then all required affected regression.

If core state/telemetry/resource architecture changed:
- run full `tests/machi`;
- acceptance_lab;
- ruff;
- mypy;
- frontend builds where affected;
- wheel verify.

## G. Freeze new RC

Build once from clean commit.

Record SHA.

## H. Server retest

Next diagnostic iteration uses the new RC.

Never patch the already-running server and call that acceptance.

---

# 17. TEST HARNESS DEFECT

Fix campaign tooling separately.

Do not change product behavior just to satisfy a broken campaign script.

Re-run the same tested product artifact if product code did not change.

The run may be repeated without incrementing product RC, but it still counts as a server diagnostic attempt unless the failure occurred before Rukan actually started.

Record this distinction.

---

# 18. PROVIDER DEFECT / PROVISIONING

If Pod provisioning fails:
- use maximum 3 retries total;
- choose another eligible low-cost supported NVIDIA candidate if evidence indicates provider availability, not product compatibility;
- record attempts.

A provider allocation failure before product installation does not count as a Rukan diagnostic iteration.

If provider networking/storage is unstable after product starts:
- collect evidence;
- classify;
- determine whether product needs graceful handling;
- if Rukan mishandles the provider condition, that secondary behavior can be a PRODUCT_DEFECT.

---

# 19. ROBUSTNESS GATE TO EXIT DIAGNOSTIC PHASE

Two consecutive diagnostic iterations must satisfy all:

- exact artifact-only install;
- no repo runtime dependency;
- no Node runtime;
- packaged Admin;
- packaged Command Center;
- People workflows;
- deployment workflow;
- model start;
- >=3 inference calls;
- usage reconciles exactly;
- >=3 periodic reports;
- material event report;
- event does not shift periodic schedule;
- machine auth;
- verified TLS;
- restart persistence;
- outage/retry on at least one of the two runs;
- stop/release;
- privacy canaries clean;
- no SQLite lock corruption;
- no migration issue;
- no unexplained stream issue;
- no manual DB edit;
- no product hot patch;
- no SERVER_ACCEPTANCE_BLOCKER;
- no PILOT_BLOCKER.

Only then freeze the confidence candidate.

---

# 20. CONFIDENCE PHASE — THREE FRESH SERVERS

Run C1, C2, C3.

Each confidence run:
- new disposable Pod;
- fresh provider state;
- fresh venv;
- fresh state/data roots;
- install exact same frozen wheel;
- same source SHA;
- same wheel SHA.

No code changes between C1/C2/C3.

Minimum each:
- preflight;
- wheel install;
- packaged Admin;
- packaged Command Center;
- secure TLS intake;
- credential pair;
- People smoke;
- model deploy;
- >=3 inference requests;
- >=3 periodic 120-second reports;
- >=1 material report;
- service restart;
- stop/release;
- privacy check;
- support/analytics export;
- evidence copy;
- Pod termination.

At least one confidence run must execute a short intake outage/recovery.

At least one confidence run should perform controlled telemetry stream reset if not already thoroughly proven by diagnostics and doing so is safe within test-owned telemetry state.

Do not vary code to fix confidence failures.

## Confidence failure

If a PRODUCT_DEFECT appears in C1/C2/C3:
- stop confidence sequence;
- evidence;
- fix through diagnostic process;
- confidence count resets to zero;
- if diagnostic iteration budget remains, resume diagnostics;
- if D5 budget exhausted, return NOT_READY.

A provider allocation failure before product starts:
- does not invalidate candidate;
- retry within provisioning policy.

An UNSUPPORTED_HOST accidental allocation:
- terminate after evidence;
- does not count as product confidence run;
- select eligible host.

---

# 21. CROSS-HARDWARE USE

This campaign is primarily software robustness, not hardware breadth.

Prefer consistency.

However, after at least one proven confidence run on a previously accepted hardware type, Cursor may choose a second previously accepted NVIDIA type for one later confidence run if:
- hourly cost remains low;
- no new runtime/provider support work is required;
- this improves reproducibility evidence.

Do not turn the campaign into AMD/macOS breadth.

All three confidence runs must stay within already supported/qualified NVIDIA pilot envelope.

---

# 22. CAMPAIGN DATA COLLECTION

Maintain:

`campaign.json`

with:
- campaign id;
- start source;
- current candidate;
- diagnostic run count;
- confidence run count;
- total spend estimate;
- total requests;
- total input tokens;
- total output tokens;
- total reports;
- defect count;
- closed product defects;
- active blockers;
- final wheel.

Each run `run.json`:
- run id;
- phase;
- source SHA;
- wheel SHA;
- Pod id;
- GPU;
- hourly rate;
- start/end;
- cost estimate;
- InstallId;
- stream IDs;
- model;
- runtime;
- Rukan version;
- report count;
- request count;
- tokens;
- latency summary;
- People operations count;
- restarts;
- outage test;
- result;
- findings.

Use `not_recorded` where unavailable.

Do not fabricate.

---

# 23. PERSISTENT LOCAL CAMPAIGN COMMAND CENTER

The user wants real accumulated data at the end.

Maintain a persistent operator-side campaign Command Center data root outside disposable Pods.

After every completed server run, export the existing privacy-safe:
- support snapshot;
- analytics bundle

from that deployment where current product supports it.

Copy those files back to the operator machine.

Place them in the persistent campaign Command Center inbox.

Run Refresh/import.

Verify:
- deployment appears;
- version/hardware/model/runtime facts appear;
- usage/inference data appears where existing bundle supports it;
- no People PII;
- repeated import is idempotent.

This persistent local Command Center is for cross-run campaign history.

The automatic heartbeat path is still proven separately on the server through real TLS/machine-auth intake.

Do not invent a new vendor export schema solely for campaign aggregation.

If current analytics bundle lacks a newly important fact, record it as a product-data gap and decide whether it is a PILOT_BLOCKER or future analytics enhancement.

---

# 24. EVIDENCE BEFORE POD TERMINATION

Hard rule:

Before successful/failed Pod termination:
- flush logs/evidence;
- save sanitized system summary;
- save sanitized test result;
- save report ids;
- save usage reconciliation;
- save support/analytics exports;
- record Pod cost/runtime;
- copy required evidence to operator machine;
- verify copied files exist and are readable.

Only then terminate.

No critical campaign evidence may exist only on an ephemeral Pod at termination.

---

# 25. CLEANUP

Customer test state:
- only campaign-owned directories;
- product-owned cleanup rules remain separate.

Provider:
- terminate owned Pod after evidence.

Local:
- preserve persistent campaign Command Center;
- preserve sanitized evidence;
- preserve frozen wheels/manifests as needed;
- remove temporary secrets/CA private keys when no longer needed;
- keep no plaintext bearer secrets in repository.

---

# 26. FINAL RELEASE-CANDIDATE FREEZE

After C3 passes:

Verify:
- C1/C2/C3 exact same source SHA;
- exact same wheel SHA;
- branch clean;
- branch pushed;
- all local QA corresponding to that commit still green;
- no later code/docs change that changes artifact;
- all campaign product defects closed;
- no open server/pilot blocker.

Create final campaign record:

`docs/machi/RUKAN-V0.3-SERVER-CAMPAIGN-RESULT.md`

Include:
- final source SHA;
- final wheel SHA;
- supported pilot envelope;
- diagnostic history;
- defect/fix history;
- three confidence run summaries;
- total server spend;
- accumulated request/token/report counts;
- remaining GA blockers;
- exact next recommendation.

Do not promote canonical `machi` unless the master instruction explicitly authorizes that later step.

---

# 27. FINAL TERMINAL STATUS

## PASS

Return exactly:

`RUKAN_V0_3_SERVER_CAMPAIGN_PASS`

Only if:
- prerequisite accountability fix passed;
- diagnostic robustness gate passed;
- three consecutive fresh confidence runs passed;
- same source SHA and wheel SHA across all three confidence runs;
- no server/pilot blockers;
- evidence preserved;
- persistent campaign Command Center has imported cross-run support/analytics data;
- all owned Pods terminated;
- campaign spend within authorized limits.

## NOT READY

Return:

`RUKAN_V0_3_SERVER_CAMPAIGN_NOT_READY`

if:
- D5 still exposes product blocker;
- confidence cannot obtain 3 consecutive clean runs;
- cost guard stops campaign;
- provider availability prevents sufficient evidence;
- evidence contradictory;
- hang requires Daniel;
- credential/provider action requires user input;
- any safety policy blocks continuation.

Do not call a partial campaign PASS.

---

# 28. PASTE BACK

Return:

A. terminal status  
B. final source SHA  
C. final wheel SHA  
D. total diagnostic iterations  
E. diagnostic run table  
F. product defects discovered  
G. robust fixes made  
H. regression tests added  
I. provider/harness defects  
J. confidence C1  
K. confidence C2  
L. confidence C3  
M. hardware/server matrix  
N. install/artifact evidence  
O. deployment/serve evidence  
P. usage reconciliation totals  
Q. input/output token totals  
R. report/heartbeat evidence  
S. outage/retry evidence  
T. restart evidence  
U. telemetry stream/reset evidence  
V. People workflow evidence  
W. privacy evidence  
X. persistent Command Center aggregation evidence  
Y. campaign total spend  
Z. remaining GA blockers  
AA. campaign docs/evidence locations  
AB. git history/branch state  
AC. Pod cleanup confirmation  
AD. recommended next action  
AE. STOP

Then STOP for Lead review.

# END SERVER CAMPAIGN
