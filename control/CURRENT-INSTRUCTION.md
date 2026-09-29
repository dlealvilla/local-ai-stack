# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-V0.3-DEPLOYMENT-CLOSURE-AND-CAMPAIGN-RESUME-001`
Status: `AUTHORIZED_PRODUCT_FIX_AND_AUTONOMOUS_CAMPAIGN_RESUME`
Starting campaign source: `7a17b3b346e7c36cdc087b206e34b6a3c86dc4e7`
Underlying corrected product source: `6dcc91239750e8390530963bb6508e79545a0798`
Working branch: `rukan/v0.3-server-campaign`
Canonical `machi` MUST NOT move in this instruction.

This instruction follows server diagnostic D1 of
`RUKAN-V0.3-CLOSURE-AND-SERVER-CAMPAIGN-001`.

D1 correctly returned:

`RUKAN_V0_3_SERVER_CAMPAIGN_NOT_READY`

because the real frozen wheel proved the product shell, telemetry, People,
Command Center and verified vLLM foundation, but did not complete the core
administrator workflow:

```text
choose/acquire model
      ↓
Plan
      ↓
ResourceManager admission
      ↓
Serve READY
      ↓
real inference
      ↓
STOP
      ↓
RELEASE
```

Two server-acceptance blockers are now binding:

1. clean HUB model acquisition depends on `huggingface_hub`, but the Rukan/Machi
   wheel declares no dependency and clean installation returns
   `source_unavailable`;
2. Plan/Admit/Serve capabilities exist internally, but the shipped product has
   no complete administrator-facing deployment orchestration seam.

The objective is:

1. design and implement those product fixes robustly;
2. prove the entire workflow locally from one clean release artifact;
3. build a new immutable RC;
4. resume the already-authorized server campaign at D2;
5. autonomously diagnose/fix/retest within the remaining diagnostic budget;
6. obtain two consecutive clean diagnostics;
7. run C1/C2/C3 on fresh servers with the exact same frozen final wheel;
8. return campaign PASS only with real inference and full evidence.

Do not ask Daniel for requirements already contained here or in the campaign
instruction.

All RunPod/cost/hang/safety rules from the existing campaign remain binding.

---

# 0. READ FIRST — ARCHITECTURE REVIEW

Before writing code, re-read repository truth for at least:

- `docs/PRODUCT_VISION.md`
- `docs/machi/ARCHITECTURE.md`
- `docs/machi/ROADMAP.md`
- `docs/machi/RUKAN.md`
- `docs/machi/RUKAN-ADMIN.md`
- `docs/machi/RUKAN-V0.3-PRODUCTION-READINESS-AUDIT.md`
- `docs/machi/RUKAN-V0.3-SERVER-CAMPAIGN.md`
- `control/instructions/RUKAN-V0.3-SERVER-CAMPAIGN-001.md`
- Model acquisition/source/warehouse adapters and contracts;
- Foundation selection/generation/provision/verification contracts;
- Model qualification and selection contracts;
- Plan composition contracts;
- ResourceManager/admission;
- Serve native/provider implementations;
- Admin application/server/lifecycle/completion paths;
- current UI Models/Deployment/Inference pages;
- telemetry/action/accountability paths.

Write a short design section into the campaign document before implementation:

`## D1 product-gap architecture review`

It must state:

- why the dependency omission happened;
- where deployment workflow coordination belongs;
- what remains authoritative in Model / Plan / ResourceManager / Serve;
- exact trusted inputs accepted from the browser;
- what is recomputed server-side;
- retry/idempotency model;
- failure-compensation model;
- restart/re-entry model;
- how native/vLLM and future/available Ollama/provider paths remain modular;
- what D2 must physically prove.

Cursor may challenge the exact proposed class/file naming below.

Cursor may NOT challenge away the required product outcomes.

---

# 1. FIX CLEAN MODEL ACQUISITION PACKAGING

D1 proved:

```text
clean Rukan wheel
  ↓
model acquire from supported HUB path
  ↓
source_unavailable
  ↓
manual test-only pip install huggingface_hub
  ↓
acquisition succeeds
```

That means the normal shipped product is incomplete.

## 1.1 Declare supported runtime dependency

Audit the current HUB adapter and its tested API usage.

Declare the required Hugging Face client in `pyproject.machi.toml` or the
authoritative Machi distribution metadata.

Use a tested bounded compatibility range, not accidental dependency availability.

Requirements:

- package name is correct for PyPI;
- version range supports methods currently used:
  - `HfApi.model_info`;
  - `hf_hub_download`;
  - `snapshot_download`;
- dependency installs through ordinary wheel installation;
- no reliance on the managed vLLM environment;
- no manual post-install `pip install`;
- no source checkout requirement;
- adapter still reports typed model-source failures.

If the project strongly prefers optional extras, an extra is acceptable ONLY if
the default Rukan product artifact / installer path used by Admin model
acquisition installs that extra automatically. A normal customer must not have to
know they need an optional Python extra before clicking Acquire.

## 1.2 Dependency isolation

Do not import vLLM/torch into the customer control-plane Python solely because
model acquisition needs a client library.

Keep:
- Rukan control-plane dependency;
- managed inference runtime dependencies

separate.

## 1.3 Acquisition error quality

Improve error mapping if needed so:
- dependency truly unavailable -> product packaging/configuration failure;
- repository missing -> repository_not_found;
- gated model -> gated_access_required;
- auth required -> authentication_required;
- storage/capacity issue -> its own typed failure.

Do not expose raw bearer/token data.

## 1.4 Clean-wheel proof

From a fresh venv containing only the new wheel and declared dependencies:

- inspect the public small campaign model;
- acquire it;
- verify immutable revision;
- verify warehouse hashes;
- restart the process;
- verify stored artifact;
- no test-only pip install.

This is a hard pre-server gate.

---

# 2. INTRODUCE A RUKAN-OWNED DEPLOYMENT ORCHESTRATION SEAM

Do NOT put the workflow directly into React.

Do NOT make the browser construct Plans, Reservations, ServingInstances, ports,
PIDs, runtime providers, fingerprints or capacity facts.

Introduce one customer-local Rukan deployment workflow service/coordinator.

Suggested conceptual name:

`DeploymentOrchestrator`
or
`DeploymentCoordinator`

Choose repository-consistent naming.

This is workflow coordination, not a new authority.

## 2.1 Authority boundaries

Preserve:

```text
Model
  owns stored artifact / compatibility / qualification facts

Foundation
  owns verified runtime/foundation state

Capacity
  owns current capacity evidence

Plan
  owns DeploymentConfiguration

ResourceManager
  owns physical admission/reservation

Serve
  owns runtime process lifecycle / READY / STOP

Rukan Deployment Orchestrator
  coordinates the sequence
  persists workflow status/references
  maps domain outcomes to product/API outcomes
```

Never let the orchestrator directly:
- fabricate capacity;
- manufacture reservation state;
- launch vLLM outside Serve;
- release resources without ResourceManager;
- mutate artifact identity;
- pick arbitrary device/port/pid from browser values.

---

# 3. ADMIN DEPLOY REQUEST — TRUST BOUNDARY

The browser may send only bounded product intent.

Minimum acceptable request:

- exact selected `artifact_id`;
- optional bounded deploy settings that already have a platform feasibility seam,
  such as context/concurrency only if supported;
- optional idempotency/request key;
- actor origin implied by local_admin_ui.

The browser must NOT send authoritative:

- FoundationSelection object;
- ManagedGeneration object;
- CapacityEnvelope;
- Plan id;
- plan fingerprint;
- reservation id;
- ServingInstance id;
- PID;
- port;
- provider endpoint;
- arbitrary executable path;
- GPU identity;
- SAFE memory bytes.

The backend reconstructs/recomputes those from local truth.

---

# 4. RECOMPUTE BEFORE DEPLOY

A Deploy call must not trust the stale state shown on the Models page.

At operation start:

1. resolve/re-enter the current local Install/state root;
2. observe/recompute the current host facts needed by the existing architecture;
3. recompute Capacity;
4. resolve current feasible Foundation/runtime path;
5. use verified/provisioned generation evidence;
6. load exact stored model artifact by `artifact_id`;
7. verify artifact integrity;
8. recompute model/runtime compatibility and requirements;
9. require qualification evidence appropriate to the selected path;
10. compose a fresh DeploymentConfiguration/Plan;
11. run full plan validation;
12. submit that exact plan to ResourceManager;
13. only after RESERVED, pass the exact admitted configuration/reservation to Serve;
14. wait for current Serve semantics to produce READY or typed failure;
15. return persisted operation state.

Do not generate or execute a Plan containing hidden stale assumptions.

If changing model/foundation/runtime/resource inputs invalidates current Plan, create
a new Plan.

Do not reuse an old reservation for a different fingerprint.

---

# 5. FOUNDATION / RUNTIME SELECTION

The UI should not expose "start vLLM on this port."

Use existing Foundation/runtime selection policy.

For this v0.3 server campaign:

- native/vLLM remains the primary expected path on the qualified NVIDIA host;
- existing approved Ollama fallback semantics must not be broken;
- the orchestrator API should not hard-code product identity to vLLM even if D2
  physically proves the vLLM path;
- the result should expose selected macropath/runtime truthfully.

If current architecture cannot yet compose both paths from one coordinator without
large scope expansion:
- build the v0.3 coordinator around the selected Foundation abstraction;
- physically prove native/vLLM now;
- preserve a typed adapter/seam for provider paths;
- do not fake provider support.

---

# 6. MODEL QUALIFICATION / DEPLOYABILITY

A stored artifact is not automatically deployable.

The orchestrator must require/recompute the evidence the current Stage-1 Plan/Serve
contracts already expect.

Audit how `qualification_id` currently reaches plan settings.

Use the existing qualification subsystem rather than bypassing it.

For the tiny public acceptance model, ensure the product has a real path to:

```text
stored artifact
  ↓
qualification / deployability evidence
  ↓
eligible Plan
```

If current qualification necessarily launches a reserved transient proof before
final deployment, preserve the authority and lifecycle semantics.

Do not insert a fake qualification id merely to satisfy Serve checks.

Any missing product orchestration around qualification discovered here is part of
this closure scope.

---

# 7. PERSIST A DEPLOYMENT OPERATION / WORKFLOW RECORD

HTTP request lifetime is not sufficient authority for a multi-step local operation.

If repository truth does not already contain an equivalent, add a small persisted
workflow projection.

It should be Rukan-owned and reference authoritative domain records.

Suggested fields:

- `operation_id`;
- `request_key` / idempotency key;
- `artifact_id`;
- requested bounded settings;
- state;
- started_at;
- updated_at;
- selected foundation id/path;
- generation id;
- qualification id;
- plan id;
- plan fingerprint;
- reservation id;
- instance id;
- failure code/reason;
- actor origin.

Suggested states, refined to repository conventions:

- requested;
- evaluating;
- planned;
- admitted;
- starting;
- ready;
- failed;
- stopped;
- released.

Do not create a second copy of authoritative Plan/Reservation/ServingInstance
documents.

References may be unresolved until the step exists.

Persist with safe crash semantics.

---

# 8. IDEMPOTENCY

This is mandatory before another server campaign.

The following must converge safely:

## Duplicate browser request before operation starts

Same idempotency/request key + same intent:
- return/re-enter same operation.

Same key + different intent:
- refuse conflict.

## Retry while operation is PLANNED/ADMITTED/STARTING

Do not create a second Plan/reservation/server merely because the HTTP client
retried.

Return current operation/progress or resume safely.

## Retry after READY

Return the same READY instance when the requested desired deployment is exactly
the already-active compatible operation.

Do not silently create a second replica in v0.3.

## Retry after terminal failure

Define explicit behavior:
- same request key returns failure record;
- a new retry attempt requires a new operation/request key, or an explicit
  retry action that creates a new operation lineage.

Document the choice.

---

# 9. PARTIAL FAILURE / COMPENSATION

Model the workflow explicitly.

## Before admission
Failure:
- no reservation;
- no process.

## Admission rejected
- no Serve start;
- show rejection;
- no fake cleanup.

## Reservation succeeded, Serve not started
If backend can prove no managed process exists:
- release the reservation if this is explicitly owned by the failed operation
  and ResourceManager allows it;
- record release evidence.

If proof is insufficient:
- retain reservation;
- expose "requires recovery/release";
- do not guess.

## Serve launch/start failure
- reconcile Serve evidence;
- prove whether a process exists;
- stop it only through Serve if necessary;
- release only after stop/death is confirmed.

## Client disconnect
The backend operation continues or converges independently of the browser
connection.

Do not roll back a legitimate READY deployment because the browser disappeared.

---

# 10. RESTART / RE-ENTRY

Test process restart at meaningful workflow boundaries.

At minimum:

- after model acquired, before deploy;
- after plan persisted, before admission;
- after reservation, before Serve;
- while STARTING where practical;
- after READY;
- after STOPPED before RELEASE.

On Rukan Admin/backend restart:
- reconstruct operation state from authoritative Plan/Reservation/Serve stores;
- never create duplicate instance merely because in-memory operation context is gone;
- reconcile process identity through existing Serve rules;
- show the truthful state.

If current process-bound architecture makes a given intermediate crash point
impossible to resume safely, fail closed with a typed recovery-required state and
document it. Do not fabricate continuity.

---

# 11. ADMIN API

Add the smallest real loopback API required for current product operations.

Likely concepts:

- POST deploy selected artifact;
- GET deployment operation/status;
- POST stop active deployment;
- POST release stopped deployment;
- possibly POST retry/recover where genuinely required.

Follow existing API conventions.

Do not expose a generic arbitrary orchestration API.

Responses must include:
- operation id;
- current workflow state;
- selected artifact/model display identity;
- actual runtime/macropath;
- Plan/reservation/instance references where useful;
- safe failure code/reason;
- next legal actions.

Do not include secrets, absolute executable paths, bearer credentials, raw logs.

---

# 12. ADMIN UI — COMPLETE THE CUSTOMER JOURNEY

The user should no longer need internal CLI knowledge.

## Models

On an exact model variant detail/card:
- Acquire if not stored and action is genuinely supported;
- once stored and compatible/qualified, show Deploy;
- if not deployable, show the real reason.

Do not show Deploy on a family-level grouping if no exact artifact is selected.

## Deployment page

Make this the lifecycle/control surface.

Show:

```text
Selected model
Current stage
Host/runtime
Plan
Resource admission
Serving state
Relevant resource requirements/headroom
Failure/recovery action
```

Business-readable first.

Technical ids/details under disclosure.

## Progress

A deployment may take time.

Display real persisted stages, not a frontend animation disconnected from state.

Example:

```text
Preparing
✓ Model verified
✓ Runtime verified
✓ Capacity evaluated
✓ Plan created
✓ Resources reserved
… Starting model server
```

Then:

`READY`

## Actions

When READY:
- Test inference;
- STOP.

When STOPPED:
- RELEASE.

STOP must not automatically become RELEASE in UI semantics.

If STOP succeeded but release failed:
- show reservation still held.

---

# 13. ADMIN INFERENCE

After READY, the existing Rukan inference tester must route to the exact active
authorized ServingInstance.

No arbitrary runtime endpoint selection.

Run at least 3 requests in local acceptance and server D2.

Usage recorder must capture:
- operator_test purpose;
- input tokens if runtime reports;
- output tokens;
- latency;
- result/failure;
- exact model/runtime.

Prompt/response remains unstored in operational analytics.

---

# 14. ACTIVITY / TELEMETRY INTEGRATION

The new lifecycle should generate/account for existing domain events and operational
reports.

Material reporting should include, from real domain evidence:

- Plan/deployment created where current event model supports it;
- admission success/rejection;
- Serve READY;
- Serve failure;
- STOPPED;
- RELEASED;
- active model/runtime change.

Do not invent duplicate vendor event payloads if the underlying domain event already
exists.

Admin Activity should render useful lifecycle changes.

The event-trigger report must still not shift periodic phase.

---

# 15. COMMAND CENTER EXPECTATIONS

No remote control.

The Command Center only receives telemetry evidence.

After D2 it should show, from automatic reports:

- latest reported model;
- macropath/runtime;
- latest reported deployment/serving state;
- deployment/start/stop failures where available;
- requests;
- input/output tokens;
- latency samples;
- lifecycle/activity timeline;
- report sequence/trigger.

It may not expose a Deploy/Stop button.

---

# 16. PACKAGE / ARTIFACT

Build the production UI and Python artifact.

The new wheel must:

- include packaged Admin assets;
- include packaged Command Center assets;
- declare the HUB acquisition dependency;
- install into a fresh venv from wheel only;
- require no Node at runtime;
- require no repo;
- identify exact source build.

Freeze SHA256.

Do not rebuild after the hash is selected for a server diagnostic run.

---

# 17. LOCAL END-TO-END ACCEPTANCE BEFORE D2

Do not spend on another server until this passes.

Use a production-like local topology as far as current host/fixtures permit.

Required path:

```text
fresh wheel install
  ↓
Install/state root
  ↓
model HUB inspect/acquire
  ↓
exact stored artifact
  ↓
Deploy API
  ↓
recompute
  ↓
Plan
  ↓
Admission
  ↓
Serve READY
  ↓
3 inference requests
  ↓
usage record
  ↓
STOP
  ↓
RELEASE
```

When a real GPU is unavailable locally, use the repository's accepted deterministic
runtime/admission fixture at the narrow physical boundary, but:
- everything above that boundary must use the actual production coordinator/API;
- do not mock the whole workflow.

Also test:
- duplicate Deploy request;
- browser/client timeout + retry;
- admission rejection;
- Serve failure;
- restart/re-entry;
- STOP without RELEASE;
- RELEASE after STOP;
- telemetry event triggers;
- usage accounting.

Hard gate:
- clean wheel acquisition cannot require manual pip installation.

---

# 18. TESTS

Add focused tests for:

## Packaging
- built metadata includes supported HUB client dependency;
- isolated wheel install imports the adapter dependency;
- clean public model inspect/acquire.

## Coordinator
- exact artifact required;
- missing artifact;
- corrupt artifact;
- stale/unqualified artifact;
- capacity insufficient;
- foundation not ready;
- Plan rejected;
- admission rejected;
- READY success;
- Serve failure;
- proper compensation;
- retry/idempotency;
- conflict idempotency key;
- restart/re-entry.

## Authority
- browser cannot submit plan id/fingerprint/reservation/pid/port/provider;
- ResourceManager still gates Serve;
- STOP != RELEASE;
- Command Center cannot invoke coordinator.

## API/UI
- Deploy from exact variant;
- progress;
- READY;
- inference;
- STOP;
- RELEASE;
- error/refusal presentation;
- no fake Deploy button for unsupported state.

## Telemetry
- READY trigger;
- STOP trigger;
- release trigger;
- failures;
- periodic phase unchanged.

Then run full:
- `tests/machi`;
- `tests/acceptance_lab`;
- ruff;
- mypy strict;
- Admin Vitest/tsc/build;
- Command Center Vitest/tsc/build;
- wheel build;
- isolated verify.

---

# 19. NEW RC / VERSION CONTROL

Continue on:

`rukan/v0.3-server-campaign`

D1 evidence commit remains history.

Do not rewrite it.

Suggested commit sequence:

1. `server-campaign(d1-fix): declare supported hub acquisition dependency`
2. `server-campaign(d1-fix): add Rukan deployment orchestrator`
3. `server-campaign(d1-fix): expose deploy lifecycle in Admin`
4. `server-campaign(d1-fix): add deployment regression and artifact acceptance`

Exact grouping may differ.

Each meaningful fix should have tests in the same or preceding commit.

After full local PASS:
- branch clean;
- push;
- build immutable D2 RC;
- record wheel SHA in campaign doc.

Do not merge canonical `machi`.

---

# 20. RESUME SERVER CAMPAIGN AUTOMATICALLY AT D2

After local product closure succeeds, immediately resume the already-authorized
campaign.

Do not stop for Lead review between local closure and D2.

Read/continue obeying:

`control/instructions/RUKAN-V0.3-SERVER-CAMPAIGN-001.md`

Campaign state:

- D1 = completed, found product blockers;
- clean diagnostic streak = 0;
- remaining diagnostic budget = D2, D3, D4, D5;
- confidence = 0/3.

All existing RunPod rules remain.

---

# 21. D2 — MUST PROVE THE FULL PRODUCT CHAIN

D2 cannot be called clean unless it physically proves from the new frozen wheel:

## Artifact
- no repo;
- no Node runtime;
- no manual dependency install.

## Model
- inspect/acquire the public small test model from the supported HUB path;
- exact immutable revision;
- warehouse integrity.

## Deployment product flow

Through the actual shipped product API / Admin-backed coordinator:

```text
artifact
→ Deploy
→ recompute current state
→ Plan
→ ResourceManager RESERVED
→ Serve READY
```

No test script directly calls `compose_plan()`, `ResourceManager.admit()` and
`ServeService.start()` as a substitute for the product path.

The campaign harness may call the Admin HTTP API, because that is the real product
surface.

## Inference
- at least 3 real requests through Rukan Admin's authorized inference seam;
- real model output structurally valid;
- usage recorded;
- input/output tokens where vLLM reports them;
- latency recorded.

## Lifecycle
- STOP through product API;
- confirm process death;
- reservation still held;
- RELEASE through product API;
- confirm ResourceManager released.

## Telemetry
- development 120s;
- >=3 periodic reports;
- READY material report;
- STOP/RELEASE reporting;
- usage reaches Command Center;
- no PII/prompt/response.

## Restart
At least:
- restart Admin after READY and prove it reconstructs the same active instance,
  then continue to inference/STOP; or
- if current accepted lifecycle requires a different safe order, prove the strongest
  supported restart/re-entry scenario and record the limitation.

No hidden manual database repair.

---

# 22. D2 FAILURE HANDLING

If D2 exposes a new PRODUCT_DEFECT:

Do NOT stop merely because it is new.

The user explicitly authorized iterative fixes.

Follow the server campaign defect loop:

```text
evidence
→ classify
→ root cause
→ violated invariant
→ local regression
→ robust design
→ code fix
→ QA
→ new wheel
→ D3
```

Continue autonomously within:
- remaining diagnostic budget;
- cost cap;
- safety rules.

Only ask Daniel if a binding safety/hang/authentication/external-input gate requires
it.

---

# 23. DIAGNOSTIC CLEAN-STREAK RULE

D1 was not clean.

Therefore:

- D2 clean → streak 1
- D3 clean → streak 2 → freeze confidence candidate

If D3 finds a bug:
- streak resets;
- fix;
- D4.

Maximum D5 remains binding.

No confidence phase until two consecutive clean diagnostics on the same behavioral
candidate line with no unresolved server/pilot blocker.

---

# 24. CONFIDENCE C1/C2/C3

Once robustness gate passes:

- freeze exact source SHA;
- freeze exact wheel SHA;
- no code change;
- C1 fresh server;
- C2 fresh server;
- C3 fresh server.

Each must prove:
- clean artifact install;
- clean model acquisition;
- product Deploy path;
- real READY;
- >=3 inference;
- telemetry;
- service restart;
- STOP;
- RELEASE;
- privacy evidence;
- exported support/analytics evidence;
- clean teardown.

At least one:
- intake outage/retry.

Any PRODUCT_DEFECT:
- confidence streak resets;
- return to diagnostic if budget remains.

Terminal campaign PASS still requires all three identical-artifact confidence runs.

---

# 25. PERSIST CAMPAIGN DATA

Continue the existing campaign requirement.

For D2 onward preserve:

- InstallId;
- model/artifact;
- Plan;
- reservation;
- ServingInstance;
- requests;
- input/output tokens;
- latency;
- reports;
- lifecycle;
- support snapshot;
- analytics bundle;
- defect/fix evidence;
- cost.

Import privacy-safe analytics/support artifacts into persistent local campaign
Command Center where the existing product supports this.

No real People data, prompts, responses, credentials or private keys.

---

# 26. UPDATE SERVER CAMPAIGN DOCUMENT

Update:

`docs/machi/RUKAN-V0.3-SERVER-CAMPAIGN.md`

D1 should remain historically truthful.

Add:
- D1 findings;
- missing dependency classification = PRODUCT_DEFECT;
- missing deployment product seam classification = PRODUCT_DEFECT;
- local architectural fix;
- D2 candidate source/wheel;
- later D2-D5/C1-C3 outcomes.

Do not rewrite D1 as if it passed.

---

# 27. SUCCESS / FAILURE STATUS

Final PASS only:

`RUKAN_V0_3_SERVER_CAMPAIGN_PASS`

Required:
- dependency fixed in shipped artifact;
- real Admin/product Deploy flow;
- real model acquired;
- real Plan/ResourceManager/Serve chain;
- real inference;
- STOP/RELEASE;
- two consecutive clean diagnostics;
- C1/C2/C3 on one identical artifact;
- data/evidence preserved;
- all owned Pods terminated;
- no server/pilot blockers.

Otherwise:

`RUKAN_V0_3_SERVER_CAMPAIGN_NOT_READY`

Do not promote canonical `machi` in this instruction.

---

# 28. FINAL PASTE BACK

Return:

A. terminal campaign status  
B. starting D1 campaign SHA  
C. dependency root cause/fix  
D. final dependency declaration/version  
E. deployment-orchestrator architecture  
F. authority-boundary proof  
G. deploy request trust boundary  
H. recomputation sequence  
I. operation persistence/idempotency  
J. failure compensation/recovery  
K. restart/re-entry evidence  
L. Admin Models/Deployment UX changes  
M. local full-chain acceptance  
N. D2 result  
O. later diagnostic runs if any  
P. defects discovered/fixed per run  
Q. clean diagnostic streak  
R. final confidence candidate SHA/wheel  
S. C1  
T. C2  
U. C3  
V. model acquisition evidence  
W. Plan/admission/Serve evidence  
X. inference/token/latency totals  
Y. STOP/RELEASE evidence  
Z. telemetry/report totals  
AA. persistent campaign Command Center data  
AB. privacy/security evidence  
AC. total campaign spend  
AD. final QA/build evidence  
AE. remaining GA blockers  
AF. branch/git state  
AG. Pod cleanup  
AH. recommended next action  
AI. STOP

Then STOP for Lead review.

# END INSTRUCTION
