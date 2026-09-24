# CURRENT LEAD DEVELOPER INSTRUCTION

**Instruction ID:** `MACHI-OLLAMA-BUNDLE-07-NVIDIA-CLOSURE-001`  
**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Starting integration HEAD:** `92555da8e3465cd1596098eb33579d31e1a12ae6`  
**Integration branch:** `automation/ollama-macropath`  
**Execution style:** PRODUCT-FIRST MULTI-SLICE CLOSURE BUNDLE  
**Primary closure target:** NVIDIA  
**AMD:** OPPORTUNISTIC / NOT A CLOSURE GATE  
**Physical server:** YES after local gates  
**Physical live request-failure failover:** OUT OF SCOPE  
**Multi-model concurrent serving:** OUT OF SCOPE

Read first:
- `control/EXECUTION-BUNDLE-POLICY.md`
- `control/CORE-VS-COMMODITY-POLICY.md`
- `control/OLLAMA-BUNDLE-06-LEAD-REVIEW.md`
- `control/OLLAMA-NVIDIA-CLOSURE-AMD-OPTIONAL.md`
- `control/OLLAMA-SERVE-AUTH-DECISION.md`
- `control/OLLAMA-MACROPATH-PROGRAM.md`
- authoritative Product Vision / Strategy / Machi Architecture / Contracts /
  Roadmap / Telemetry / Debt docs
- exact current native-vLLM physical evidence
- exact current Ollama Bundle-04/05/06 physical evidence

======================================================================
DIRECTION LEVELS
======================================================================

BINDING:
- NVIDIA is sufficient for current Stage-1 Ollama closure if every NVIDIA
  closure criterion in this package passes;
- AMD preflight is required, AMD physical success is not;
- AMD-specific unavailability/failure does not block NVIDIA closure;
- vLLM remains primary under AUTO when healthy/supported;
- Ollama remains compatibility/fallback;
- explicit runtime choices never silently switch;
- fallback is a new Foundation -> model -> Plan -> Admit -> Serve chain;
- no cross-catalog model equivalence or conversion;
- one ResourceManager / one ResourceReservation ledger;
- historical evidence may be migrated only without strengthening it;
- runtime choice must be explainable and auditable;
- no customer prompt/response in durable evidence;
- do not overclaim physical live HA/failover.

RECOMMENDED:
- repair schema migration durability with a recoverable intent/receipt mechanism
  or another convergent design rather than pretending two independent writes are
  atomic;
- evolve RuntimeChoice evidence so the stronger decision cites concrete
  Foundation observations/selections/capacity evidence;
- if that changes persisted RuntimeChoice schema, use the now-existing schema
  migration mechanism and preserve older v1 readback truthfully;
- use one disposable NVIDIA host for the physical closure campaign where
  practical;
- use `smollm2:360m-instruct-q8_0` as the second positive Ollama case if the
  provider catalog still exposes it at runtime, because it is small and overlaps
  the native SmolLM2 family.

DELEGATED:
- exact persistence recovery design;
- exact RuntimeChoice/evidence contract shape;
- test fixture details;
- physical command mechanics;
- internal refactors;
- choice of a different small second positive Ollama model if repository/provider
  truth makes it more suitable, with explanation.

======================================================================
PRODUCT PURPOSE / CLOSURE OUTCOME
======================================================================

If this package closes successfully, the precise product-level statement should
be:

> On the bounded NVIDIA environments and exact runtime/model configurations
> physically qualified in the Stage-1 campaign, Machi has two working execution
> macropaths: native/vLLM as primary and Ollama as a separately qualified
> compatibility/fallback path. Machi preserves one global admission authority,
> keeps model catalogs separate, can explain AUTO runtime choice from concrete
> Foundation evidence, and can construct a fresh Ollama deployment chain when
> fallback is selected. AMD remains unqualified/open and production live
> request-failure failover is not claimed.

The macropath may be marked **CLOSED_NVIDIA_STAGE1** only if all mandatory
closure gates below pass.

======================================================================
SCOPE
======================================================================

IN SCOPE:
A. migration audit recoverability / K-03 functional closure;
B. stronger RuntimeChoice evidence binding;
C. local policy/regression QA;
D. standing AMD RunPod preflight, optional AMD attempt;
E. one bounded NVIDIA physical closure campaign;
F. physical healthy-primary AUTO evidence;
G. attempt one truthful physical fallback-selection scenario;
H. second positive Ollama model case;
I. meaningful negative/excluded case;
J. comparative native-vLLM vs Ollama closure summary;
K. exact support boundary and macropath closure decision.

OUT OF SCOPE:
- requiring AMD success;
- multi-host/fleet fallback;
- automatic runtime switch after a user inference failure;
- cross-catalog equivalent-model mapping;
- multiple simultaneous Ollama models;
- UI;
- customer workload benchmarking;
- Dynamo;
- training/indexing;
- general production HA;
- changing the primary/fallback product policy.

======================================================================
ACTION 1 — MAKE SCHEMA MIGRATION DURABLY RECOVERABLE
======================================================================

### Product purpose

When Machi upgrades historical persisted state, a crash or filesystem error must
not leave the system unable to explain whether a migration occurred.

The current Bundle-06 behavior has a narrow gap:
record rewrite can succeed before migration-audit persistence fails.

### Required functional behavior

After this action:
- old known records still upgrade conservatively;
- unknown kinds/versions fail closed;
- if migration data write fails before completion, a later read/recovery can
  deterministically converge;
- if audit/receipt persistence fails, the fact that bookkeeping is incomplete
  remains recoverable rather than disappearing because the main record is now
  current;
- repeated recovery is idempotent;
- no receipt can falsely claim a completed migration when the current record was
  not durably written;
- no customer content is copied into migration metadata;
- journal history is not rewritten.

Do not claim cross-file atomicity unless the implementation truly provides it.

RECOMMENDED technical direction:
a durable small migration intent/sidecar or phased receipt that allows a later
read/recovery to determine incomplete vs complete migration. Cursor may choose a
better bounded design.

### QA

Inject failures around:
- intent/audit write;
- migrated record write/replace/fsync;
- completion bookkeeping;
- recovery after each interruption.

Prove convergence.

### K-03 Lead authorization

If the final implementation satisfies the functional and durability
requirements:
- K-03 may be marked RETIRED;
- preserve in its history/text that the migration infrastructure landed after
  the first schema bumps and therefore the original timing gate was missed;
- do not invent a new global debt-status taxonomy solely for this item.

If durability remains incomplete, keep K-03 OPEN and the overall NVIDIA Ollama
closure may still proceed only if no current physical acceptance depends on
unsafe migration behavior. State that debt explicitly.

======================================================================
ACTION 2 — BIND AUTO RUNTIME CHOICE TO CONCRETE FOUNDATION EVIDENCE
======================================================================

### Product purpose

An administrator should be able to answer:

> Why did AUTO choose this runtime, and what exact Foundation observations did
> that decision consume?

Current RuntimeChoice records support states and policy reasoning. That is
sufficient for local policy logic but not the strongest physical audit trail.

### Required functional outcome

For a new RuntimeChoice decision, persist enough immutable references to identify
the concrete primary and fallback Foundation evidence/selection inputs that were
actually consulted, where available.

The exact contract is delegated, but the evidence should be able to distinguish:
- requested mode;
- primary engine;
- primary support/failure;
- primary Foundation selection/evidence identity;
- primary capacity evidence where material;
- fallback engine;
- fallback support/failure;
- fallback Foundation selection/evidence identity where consulted;
- selected engine;
- decision/reason/policy;
- recomputation requirement;
- observation time/provenance where consistent with existing contracts.

Do not copy entire Foundation objects into RuntimeChoice if references are
sufficient.

If RuntimeChoice requires a schema bump:
- preserve v1 readback through explicit migration;
- migrated v1 must say missing concrete evidence is `not_recorded` or the
  equivalent truthful sentinel;
- old v1 must not be upgraded into stronger physical evidence than it contained.

### QA

Prove:
- healthy primary choice cites the primary observation actually consumed;
- fallback cites both the primary unavailability evidence and the fallback
  validity evidence;
- explicit modes cite only what they truly consult;
- stale/mismatched evidence cannot be substituted after decision creation;
- customer content absent.

======================================================================
ACTION 3 — LOCAL CLOSURE REGRESSION
======================================================================

Before physical work, run a broad functional closure suite.

Prove at least:
- native/vLLM happy path remains unchanged;
- explicit vLLM and Ollama fail closed;
- AUTO healthy primary selects vLLM;
- AUTO unresolved primary refuses rather than falling back optimistically;
- AUTO approved primary-unavailable state selects Ollama;
- fallback reconstructs downstream and does not reuse model/Plan/reservation/
  instance identities;
- provider Plan uses fgen + exact provider digest;
- Ollama context qualification remains exact;
- STOP/reconcile/release remain truthful;
- schema recovery tests pass;
- v1 historical evidence remains readable but weaker;
- one-ledger accounting still holds.

Then:
- full `tests/machi`;
- architecture checks;
- ruff;
- strict mypy;
- clean wheel;
- isolated `verify_ok`.

Build one immutable physical candidate.

======================================================================
ACTION 4 — AMD RUNPOD PREFLIGHT — REQUIRED CHECK, OPTIONAL QUALIFICATION
======================================================================

Run the standing AMD preflight before or during the physical campaign.

Use existing AMD policy and exact current live facts.

Check:
- live balance;
- MI300X/approved AMD stock;
- hourly price;
- suitable ROCm image/tooling availability;
- safe runtime preserving the account floor;
- minimum 45 minutes meaningful qualification;
- one-owned-Pod rule and current account burn.

### If any gate fails

Record exact disposition, for example:
- NO_STOCK;
- NO_APPROVED_ROCM_IMAGE;
- INSUFFICIENT_SAFE_BALANCE/RUNTIME;
- PRICE_CAP;
- OTHER_ENVIRONMENT_BLOCK.

Then CONTINUE the NVIDIA closure package.

No AMD Pod is required.

### If all gates pass

Cursor MAY run one bounded AMD qualification under the existing lab policy.

Any AMD result is supplemental coverage.

If it exposes:
- an AMD-specific defect/environment gap: record it and keep AMD open; continue
  NVIDIA closure;
- a provider-neutral/core defect that invalidates shared Machi semantics: fix
  or stop according to normal architecture rules.

Never claim AMD support merely because preflight succeeds.

======================================================================
ACTION 5 — NVIDIA PHYSICAL CLOSURE CAMPAIGN
======================================================================

Follow all existing RunPod safety rules:
- official tooling only;
- owned disposable Pod only;
- one Pod at a time;
- NVIDIA <= $1.50/hour;
- known balance >= $5;
- $40/session / $80/day;
- <=90 minutes per Pod;
- <=3 provisioning retries;
- no network volume;
- no remote source patching.

Prefer an NVIDIA SKU already represented in current evidence (A40 or L40S).
Do not require the exact same SKU if stock prevents it; narrow claims.

### Phase A — establish both real Foundation observations

On the same host if feasible:
- derive current Capacity;
- establish/verify the native vLLM Foundation state using normal product code;
- establish/verify the managed Ollama Foundation state using normal product code;
- record exact FoundationSelection/evidence/capacity identities used by AUTO.

Do not use hand-authored support states for the healthy-primary case.

### Phase B — physical AUTO healthy-primary proof

With both paths genuinely available/verified:
- request AUTO;
- prove RuntimeChoice consumes the concrete Foundation evidence;
- prove native/vLLM is selected;
- prove no Ollama provider Plan/admission/Serve is created as a side effect.

If safe and practical within the same candidate/host, continue through one
bounded native model Plan -> Admit -> Serve inference using the selected native
path. Reuse existing accepted native semantics rather than building new ones.

This is a runtime-selection proof, not a benchmark.

### Phase C — truthful physical fallback-selection attempt

Attempt to create one bounded, reversible, product-generated primary-unavailable
state **without**:
- uninstalling/changing host-global drivers;
- corrupting accepted native artifacts;
- changing system Python;
- disabling the GPU;
- falsifying SupportState by hand;
- patching source on the host.

Acceptable examples may include an isolated Machi-owned disposable Foundation
generation/candidate that truthfully fails verification, or another bounded
provider-neutral test condition that existing Foundation code classifies into an
approved unavailable state.

RECOMMENDED only: use isolated Machi-owned state rather than damaging a valid
primary environment.

Then:
- record the concrete primary-unavailability evidence;
- keep the real Ollama Foundation valid;
- request AUTO;
- prove Ollama is selected for the documented approved reason;
- prove downstream native model/Plan/reservation/instance state is invalidated
  or not reused;
- use the Ollama-owned catalog;
- qualify exact provider digest if needed;
- create a new provider Plan;
- obtain a new ResourceReservation;
- Serve one real inference;
- prove exact digest/runtime identity;
- STOP and release truthfully.

### If a truthful physical primary-unavailable condition cannot be produced safely

Do NOT fabricate it and do NOT sabotage the host.

Record:
`PHYSICAL_AUTO_FALLBACK_NOT_SAFELY_INDUCED`.

Continue the rest of the NVIDIA closure.

The Ollama macropath may still close as **CLOSED_NVIDIA_STAGE1** if all other
macropath criteria pass, because the fallback policy and fresh-chain behavior
are already locally proven. The exact support claim must then say physical AUTO
fallback selection remains unproven and tracked separately.

Do not call that production failover.

======================================================================
ACTION 6 — SECOND POSITIVE OLLAMA MODEL
======================================================================

The Stage-1 physical matrix should contain more than repeated runs of one
provider model.

Preferred second case:
`smollm2:360m-instruct-q8_0`

At runtime:
- confirm the tag exists in the real Ollama provider catalog;
- use the real digest discovered from `/api/tags`;
- do not hard-code a historical digest as authority;
- lab pull remains operator test setup, not product acquisition.

Use a bounded context (prefer 2048 unless a stronger reason exists).

Prove at least:
- catalog identity;
- qualification FIT/PASS;
- generation/context binding;
- one ResourceManager-authorized Serve inference;
- exact digest proof;
- cleanup/release;
- comparison event/normalized metrics.

If the preferred tag is unavailable, choose another small distinct Ollama model
or materially different SmolLM2 size/representation and explain why.

Do not turn this into a benchmark sweep.

======================================================================
ACTION 7 — MEANINGFUL NEGATIVE / EXCLUDED CASE
======================================================================

Prove at least one meaningful exclusion/refusal that protects a product
invariant and does not require huge downloads.

Preferred classes, in order:
1. qualification/context coverage mismatch refused before Serve;
2. exact provider digest/catalog drift refused before inference;
3. stale/wrong Foundation generation refused;
4. model-specific provider NO_FIT if a small truthful case is naturally
   available without forcing large downloads.

At least one negative must be tied to a real physical/provider fact where safe,
not only a mocked unit test.

Do not manufacture a false no-fit result.

======================================================================
ACTION 8 — COMPARATIVE CLOSURE
======================================================================

Produce a bounded Stage-1 comparison using existing accepted native-vLLM and
Ollama evidence.

Compare only metrics whose semantics are sufficiently aligned:
- hardware/SKU and environment;
- runtime family/version;
- model logical family and exact representation;
- context/concurrency;
- qualification result;
- load timing where actually measured;
- tokens/sec;
- input/output tokens;
- runtime-reported/observed memory with provenance;
- start/stop/restart behavior;
- failure/refusal cases.

Do NOT:
- rank a runtime winner;
- average incomparable hardware/representations;
- call Ollama `size_vram` an external peak;
- infer general performance from one host.

State what empirical questions remain for the later cross-macropath lab.

======================================================================
ACTION 9 — MACROPATH CLOSURE DECISION
======================================================================

After evidence is complete, evaluate the six program chunks against their
bounded Stage-1 exits.

### Mandatory NVIDIA closure criteria

To mark `CLOSED_NVIDIA_STAGE1`, require:
- managed/verified Ollama Foundation semantics accepted;
- truthful provider catalog/digest path;
- dual qualifier semantics accepted;
- exact context/generation qualification physical PASS;
- one global ResourceManager authorization;
- provider Plan/Admit/Serve physical PASS;
- STOP/reconcile/release semantics;
- at least two positive physical Ollama model cases across the campaign;
- at least one meaningful negative/excluded case;
- normalized comparative analytics/evidence;
- AUTO healthy-primary policy physically evidenced;
- AUTO fallback fresh-chain behavior locally evidenced;
- all final local gates green;
- no open blocker that invalidates the stated NVIDIA support claim.

### Physical fallback nuance

A physical induced fallback PASS strengthens closure evidence but is not a
mandatory NVIDIA macropath closure condition if it cannot be produced safely.

If physical fallback is not proven, record it as an explicit remaining
integration/HA evidence item.

### AMD nuance — binding

AMD PASS is NOT required.

AMD stock/image/environment failure MUST NOT prevent
`CLOSED_NVIDIA_STAGE1`.

### Closure outcomes

Use exactly one:
- `CLOSED_NVIDIA_STAGE1`
- `PARTIAL_NVIDIA_BLOCKED`
- `DECISION_REQUIRED`

If closed:
- create a recovery checkpoint;
- update program/roadmap/debt with exact support boundary;
- keep AMD lane open;
- keep physical live-failover/general HA work separate;
- do not mark all-vendor or production-HA support.

======================================================================
FIX VS ARCHITECTURAL AMENDMENT
======================================================================

Cursor SHOULD fix autonomously:
- migration durability implementation defects;
- runtime evidence reference wiring;
- physical packaging/lifecycle issues;
- provider API races;
- test/evidence bugs;
- bounded failures inside already accepted AUTO policy.

Cursor MAY choose and explain:
- migration recovery mechanics;
- RuntimeChoice evidence contract structure;
- safe physical primary-unavailable test technique;
- second small Ollama model;
- internal refactors.

Cursor MUST STOP if work would:
- change vLLM-primary/Ollama-fallback policy;
- require cross-catalog model translation/equivalence;
- put fallback inside Serve;
- weaken exact Foundation/model identity;
- create a second ResourceManager ledger;
- require unsafe host-global sabotage to prove fallback;
- change privacy/security policy;
- add a new mandatory runtime/provider/dependency;
- broaden closure to HA/fleet/multi-model semantics.

======================================================================
FINAL GATES
======================================================================

After all executed actions:
- targeted tests;
- full `tests/machi`;
- architecture checks;
- ruff;
- strict mypy;
- clean final wheel;
- isolated `verify_ok`;
- canonical docs/debt/evidence updates;
- exact physical candidate identity;
- exact clean final HEAD pushed;
- local == origin.

If closed, checkpoint the exact final accepted NVIDIA Stage-1 state.

Do not start a new macropath, UI work, Dynamo, or broad hardware campaign.

======================================================================
MANDATORY PASTE-BACK
======================================================================

==================== BEGIN PASTE BACK — OLLAMA BUNDLE 07 CLOSURE ====================

A. STATUS / closure outcome  
B. Starting SHA / physical passing SHA / final SHA  
C. Product capability closed  
D. Migration durability design and recovery proof  
E. K-03 final disposition  
F. RuntimeChoice concrete Foundation evidence design  
G. RuntimeChoice schema compatibility if changed  
H. Local AUTO/regression closure QA  
I. Candidate wheel / SHA256 / isolated verify  
J. AMD RunPod preflight facts  
K. AMD optional attempt/result, or exact reason not attempted/successful  
L. NVIDIA host ownership/price/lifecycle  
M. Real native Foundation observation  
N. Real Ollama Foundation observation  
O. Physical AUTO healthy-primary decision evidence  
P. Optional native selected-path inference result  
Q. Physical fallback-selection attempt method and safety rationale  
R. Physical fallback result, or PHYSICAL_AUTO_FALLBACK_NOT_SAFELY_INDUCED  
S. Proof of fresh Ollama fallback chain if physically executed  
T. Second positive Ollama model tag/digest/qualification/Serve result  
U. Meaningful negative/excluded case  
V. Comparative native-vLLM vs Ollama closure summary  
W. Provider/resource/privacy invariants rechecked  
X. Implementation defects found/fixed  
Y. Architecture amendments/decision gates encountered  
Z. Exact NVIDIA support claim  
AA. Explicitly unclaimed capabilities  
AB. Remaining AMD/fallback/HA debt  
AC. Pod termination proof(s)  
AD. Full final gates / local==origin  
AE. Recovery checkpoint / program status  
AF. Final status

Final status exactly one of:

`STOP — OLLAMA MACROPATH CLOSED_NVIDIA_STAGE1. WAIT FOR LEAD REVIEW.`

`STOP — OLLAMA BUNDLE 07 PARTIAL_NVIDIA_BLOCKED. WAIT FOR LEAD REVIEW.`

`DECISION_REQUIRED_OLLAMA_CLOSURE — WAIT FOR LEAD DECISION.`

`ENVIRONMENT_BLOCKED_NVIDIA — WAIT FOR LEAD REVIEW.`

`PRODUCT_FAILURE — WAIT FOR LEAD REVIEW.`

==================== END PASTE BACK — OLLAMA BUNDLE 07 CLOSURE ====================

Do not continue beyond this package.
