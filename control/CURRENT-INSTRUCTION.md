# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-DUAL-UI-V0.1-001`  
Status: `AUTHORIZED_IMPLEMENTATION`  
Canonical baseline: `machi` at `7ff3dff6972f69ba38214a6d30f7a19f272318e0`  
Predecessor: `RUKAN-DUAL-UI-V0-001` / implementation `cd14b3ed8490f7ceb64db50b17646acc4b18eaa1`

This is the second bounded Rukan UI iteration.

The goal is to turn the already-running Rukan Admin and Rukan Command Center v0 into a more usable local product without opening new platform domains.

No physical server is required for this instruction.

Do not start remote fleet connectivity, identity, licensing, Knowledge/RAG, Runtime Artifact Registry, Dynamo, or physical qualification.

---

# 1. STARTING TRUTH

Rukan dual UI v0 is accepted.

## Rukan Admin already exists

- Overview
- Inference
- Models
- Deployment
- System
- loopback-only `rukan.admin.v1`
- snapshot export
- Rukan-native inference seam
- truthful typed refusals
- no prompt/response persistence
- no LibreChat dependency

## Rukan Command Center already exists

- Deployments
- Deployment Detail
- Support Evidence
- Import
- Settings
- imported `rukan.support_snapshot`
- local browser storage only
- no remote control
- no live fleet claims
- no customer content export

## Known usability/operational gap

Admin exposes Stop and Release semantics, but the CLI-launched Admin process does not currently attach the lifecycle runtime/process owner. The UI therefore correctly returns `lifecycle runtime is not attached`.

This iteration should close that gap if repository truth permits a safe bounded solution.

---

# 2. RUNPOD POLICY — CURRENT BINDING TRUTH

No RunPod use is authorized by this instruction.

For future physical work, preserve the current policy:

- NVIDIA hourly ceiling: `≤ $1.50/hour`
- AMD hourly ceiling: `≤ $4.00/hour`
- remaining RunPod account-balance floor: `$0.50`
- one owned Pod at a time
- max Pod lifetime: 90 minutes
- max 3 provisioning retries
- no network volume
- hang: stop-and-ask
- existing session/day spend caps remain in force

Do not alter these limits in this UI package.

---

# 3. BRANCH

Sync control and fetch origin.

Confirm canonical `machi` is:

`7ff3dff6972f69ba38214a6d30f7a19f272318e0`

Create:

`rukan/dual-ui-v0.1`

from that exact canonical baseline.

Do not branch from the old `rukan/dual-ui-v0` tip directly unless it is ancestry-equivalent to canonical after the integration merge.

---

# 4. PRIMARY OUTCOME

At completion:

## Rukan Admin

A local administrator should be able to:

1. open Rukan Admin;
2. immediately understand whether the deployment is usable;
3. run a real inference test with clear in-progress/success/refusal/error feedback;
4. inspect the active model and execution path;
5. inspect the deployment chain without reading raw ids by default;
6. safely stop the current managed serving instance;
7. release its reservation only after Rukan proves release eligibility;
8. see the resulting state update in the UI;
9. inspect technical evidence only through progressive disclosure.

## Rukan Command Center

A business operator should be able to:

1. import support snapshots;
2. find a deployment quickly;
3. see when the imported evidence was exported;
4. inspect version/host/stack/model/qualification/Witness information;
5. inspect structured support evidence;
6. see snapshot history where multiple snapshots for one installation exist;
7. remove local imported data;
8. never confuse imported evidence with live connectivity.

---

# 5. LIFECYCLE WIRING — MAIN ENGINEERING TASK

First inspect repository truth around:

- `ServeService`
- current Native/vLLM process ownership/evidence
- Ollama provider lifecycle ownership
- ResourceManager
- Admin composition
- CLI process lifetime
- re-entry/reconciliation semantics

The objective is **not** merely to make the buttons clickable.

The objective is:

> Rukan Admin can invoke the existing authoritative lifecycle services for the current managed instance without bypassing process identity, reservation authority, STOP != RELEASE, or provider-specific ownership.

## Required invariant

Browser
→ Rukan loopback API
→ Rukan lifecycle application service/composition
→ existing Serve/provider lifecycle semantics
→ ResourceManager release only after eligibility

Never:

Browser
→ arbitrary PID kill

Never:

Browser
→ direct Ollama/vLLM lifecycle endpoint bypass

Never adopt a process by PID alone.

## Preferred implementation shape

Use the smallest safe composition seam that allows the Admin-serving process to access/reconstruct the existing lifecycle authority.

Possible repository-consistent implementations may include:

- running Admin within an existing long-lived local Rukan supervisor/composition;
- reconstructing lifecycle services from persisted Rukan evidence only where current identity/re-entry contracts explicitly permit it;
- a narrow local lifecycle-owner service if an owner process already conceptually exists.

Do **not** invent a new daemon architecture unless current contracts genuinely require one.

If safe cross-process reattachment is not possible under existing contracts, do not weaken the identity rules. Implement the safe subset, document the exact architectural blocker, and return `DECISION_REQUIRED` for that subpart while completing the rest of the bounded UI iteration.

## Tests required

At minimum:

- stop current READY native instance via Admin seam;
- second stop converges/idempotent according to existing semantics;
- stop wrong/mismatched instance refused;
- release while STARTING/READY/STOPPING refused;
- release after confirmed STOPPED/dead succeeds through ResourceManager;
- second release converges/refuses consistently with M8 contract;
- reservation remains held when stop fails;
- process identity mismatch refuses;
- provider/Ollama path follows its existing provider lifecycle semantics where current architecture supports it;
- UI refresh reflects changed state;
- browser cannot supply arbitrary runtime/provider/PID to override the current chain.

Do not create fake unit-only semantics that differ from current Serve/Admit behavior.

---

# 6. ADMIN OVERVIEW — USABILITY PASS

Rework hierarchy, not truth.

The first screen should answer, in this order:

1. **Can I use this deployment?**
2. **What model is active?**
3. **How is it running?**
4. **Is anything requiring attention?**
5. **What resources are safely available/allocated?**

Use existing fields only.

Recommended presentation:

- top deployment state derived from Witness + current chain;
- active model;
- macropath/runtime;
- instance state;
- reservation state;
- concise capacity;
- warnings/pending physical coverage;
- build/version in secondary detail.

Do not create a synthetic health score.

Do not label imported/stored evidence as current utilization.

Use plain-language labels with exact technical ids behind expandable detail.

---

# 7. ADMIN INFERENCE — USABILITY PASS

Keep this an operational inference tester, not a full chat product.

Add only useful bounded UX:

- clear model and macropath context;
- multiline prompt;
- configurable `max_tokens` within the existing 1..64 API bound;
- Send button;
- in-flight state;
- disable duplicate sends while a request is active;
- response text;
- completion tokens when reported;
- elapsed request duration measured for the actual request if implemented truthfully;
- clear typed refusal/error reason;
- Clear action;
- local privacy note: response is not stored by the Rukan operational store.

Do not add:

- conversation history;
- saved chats;
- RAG;
- file upload;
- tools;
- agents;
- Markdown plugins;
- model switching;
- direct runtime endpoint selection.

The Admin tester should remain obviously different from a future employee chat client.

---

# 8. ADMIN DEPLOYMENT — PRODUCTIZE THE BLOCK CHAIN

The current ordered list is truthful but too implementation-shaped.

Create a clearer deployment journey view:

Foundation
→ Model
→ Plan
→ Reservation
→ Instance
→ Inference Evidence
→ Witness

For each step:

- human-readable status;
- concise meaning;
- relevant current value;
- technical id/details behind disclosure.

The screen should make Block 5–9 semantics understandable without exposing internal jargon first.

Lifecycle actions:

- Stop when applicable and attached;
- Release only when eligible;
- disable/refuse honestly otherwise;
- show operation outcome immediately.

Do not add Start/Deploy unless there is already a complete truthful action seam backing it in this baseline.

---

# 9. ADMIN MODELS / SYSTEM — SMALL REFINEMENT ONLY

Do not expand scope into a marketplace.

Models:

- improve labels around warehouse artifact vs provider digest;
- make unavailable operations visibly disabled with a reason;
- preserve explicit local inspect/import/hub acquire semantics;
- show qualification/deployability only where actually present.

System:

- improve formatting of bytes into human-readable values while retaining exact bytes in detail;
- distinguish observed hardware from SAFE capacity;
- preserve unresolved/not_recorded;
- show physical qualification/pending coverage clearly.

No utilization graphs unless real utilization evidence exists.

---

# 10. COMMAND CENTER — V0.1 USABILITY

Do not add network connectivity.

Improve the existing local imported-evidence workflow.

## Deployments list

Add bounded local-only features:

- search/filter by install id, version, OS/accelerator, macropath, model, Witness;
- sort by latest snapshot export time;
- show number of imported snapshots per deployment;
- show latest evidence timestamp as **Evidence exported** or **Snapshot age**, never Last Seen/Online.

If computing snapshot age, derive it from local current time and `exported_at` and label it explicitly as snapshot age.

## Deployment detail

Improve hierarchy:

- identity/version;
- hardware;
- execution stack;
- model/qualification;
- Witness;
- capacity;
- evidence timestamps;
- pending physical coverage.

Add a visible banner:

`Imported evidence — not live deployment status`

## Snapshot history

Where multiple snapshots are already retained for the same install id:

- show their exported timestamps;
- schema/build/version;
- Witness verdict;
- model/macropath summary;
- allow selecting an older snapshot for inspection.

Do not invent diff semantics unless you implement a deterministic field-by-field local comparison.

## Support evidence

Keep structured event envelopes only.

No raw log ingestion in this iteration.

---

# 11. VISUAL / ACCESSIBILITY PASS

Keep the implementation lightweight.

No redesign framework migration.

Improve:

- spacing and hierarchy;
- consistent status treatments;
- table readability;
- responsive layout at normal desktop widths;
- keyboard focus visibility;
- accessible labels;
- semantic headings;
- loading/empty/error states.

Use the existing shared theme; do not introduce a large design-system dependency.

Rukan Admin and Command Center may visually relate but must remain clearly distinct products.

---

# 12. LOCAL STAND-UP / VISUAL EVIDENCE

Run both applications locally against deterministic test/demo evidence.

Create a reproducible local demonstration method that does **not** fake backend capabilities.

Acceptable:

- test fixtures that are explicitly labelled fixture/demo evidence;
- a temporary local state root populated through current contracts/test helpers;
- a snapshot fixture derived from the real SupportSnapshot contract.

Capture screenshots of:

## Admin

- Overview
- Inference
- Deployment

## Command Center

- Deployments
- Deployment Detail
- Support Evidence or Snapshot History

If the repository environment lacks a safe screenshot mechanism, document exact local commands and DOM/test evidence instead. Do not introduce a browser automation framework only for screenshots unless it is already available or trivially justified.

No physical inference host is required.

---

# 13. TEST / QA GATES

Run:

Backend:
- full `tests/machi`
- `tests/acceptance_lab`
- new Admin lifecycle/API tests
- snapshot/privacy tests
- architecture tests
- ruff
- mypy --strict

Admin:
- unit/component tests
- TypeScript no-emit check
- production Vite build

Command Center:
- store/import/history/search tests
- TypeScript no-emit check
- production Vite build

Packaging:
- repository-owned wheel build if Python changed
- isolated verification if Python changed

Regression:

- Stage-1 native/vLLM primary semantics unchanged;
- Ollama fallback semantics unchanged;
- one ResourceManager authority unchanged;
- STOP != RELEASE unchanged;
- no prompt/response persistence/export;
- Command Center still non-authoritative/import-only.

---

# 14. NON-GOALS

Do not implement:

- remote Admin;
- connected fleet heartbeat;
- cloud Command Center;
- authentication/tenancy;
- users/teams;
- licensing;
- Runtime Artifact Registry;
- Knowledge/RAG;
- employee chat application;
- LibreChat/Open WebUI integration;
- Dynamo;
- new runtime providers;
- physical AMD/macOS/Ampere testing;
- new RunPod Pods;
- usage analytics dashboard unless current real data contracts already make a tiny display trivial and directly relevant — default is defer;
- model marketplace/recommendation.

---

# 15. DOCUMENTATION

Update current Rukan UI docs with:

- exact run commands;
- architecture boundary;
- lifecycle attachment behavior;
- local security model;
- inference privacy;
- Command Center import semantics;
- screenshot/demo workflow;
- deferred features.

Do not rewrite historical Machi evidence.

---

# 16. ACCEPTANCE

PASS requires:

- both UIs still run locally;
- lifecycle wiring is safe and functional, OR an exact genuine architecture blocker is reported without weakening invariants;
- Admin inference UX improved;
- Admin Overview/Deployment clarity improved;
- Command Center search/history/evidence usability improved;
- no live-fleet claim introduced;
- no customer content exported;
- all relevant tests/builds pass;
- clean pushed branch.

Preferred terminal status when lifecycle is fully closed:

`RUKAN_DUAL_UI_V0_1_LOCAL_PASS`

If the only unresolved item is a genuine lifecycle ownership architecture decision:

`DECISION_REQUIRED_LIFECYCLE_ATTACHMENT`

Do not use PASS if Stop/Release are visually presented as functional when they are not.

---

# 17. PASTE BACK

Return:

A. exact status  
B. TL;DR  
C. starting/final SHA  
D. branch/worktree/origin  
E. lifecycle ownership analysis  
F. Stop implementation  
G. Release implementation  
H. native lifecycle tests  
I. Ollama lifecycle disposition  
J. Admin Overview changes  
K. Admin Inference changes  
L. Admin Deployment changes  
M. Models/System refinement  
N. Command Center Deployments changes  
O. snapshot history  
P. Support evidence changes  
Q. visual/accessibility changes  
R. screenshots/demo evidence  
S. security/privacy review  
T. full QA  
U. build artifacts  
V. remaining limitations  
W. recommended next UI iteration  
X. git state  
Y. STOP

Then STOP for Lead review.

# END INSTRUCTION
