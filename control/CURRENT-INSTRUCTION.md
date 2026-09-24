# CURRENT LEAD DEVELOPER INSTRUCTION

**Instruction ID:** `MACHI-OLLAMA-BUNDLE-06-CLOSURE-FALLBACK-001`  
**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Starting integration HEAD:** `ebfabe56b2ae09b916e5e70ea4d2b1c028f48af6`  
**Integration branch:** `automation/ollama-macropath`  
**Execution style:** PRODUCT-FIRST MULTI-SLICE BUNDLE  
**Physical server:** CONDITIONAL YES after local correction gates  
**AUTO fallback:** BOUNDED LOCAL CONTROL-PLANE IMPLEMENTATION ALLOWED  
**Physical AUTO fallback:** NOT REQUIRED / DO NOT OVERCLAIM  
**Multi-model/general production closure:** FORBIDDEN

Read first:
- `control/EXECUTION-BUNDLE-POLICY.md`
- `control/CORE-VS-COMMODITY-POLICY.md`
- `control/OLLAMA-BUNDLE-05-LEAD-REVIEW.md`
- `control/OLLAMA-SERVE-AUTH-DECISION.md`
- `control/OLLAMA-BUNDLE-06-CLOSURE-FALLBACK.md`
- `control/OLLAMA-MACROPATH-PROGRAM.md`
- authoritative Product Vision / Strategy / Machi Architecture / Contracts /
  Roadmap / Telemetry / Debt docs
- current Kernel schema/store implementation
- current native/vLLM Foundation/Plan/Admit/Serve path
- current Ollama Foundation/qualification/Plan/Admit/Serve path

======================================================================
DIRECTION LEVELS
======================================================================

BINDING:
- Product Vision;
- one global ResourceManager and one ResourceReservation ledger;
- native/vLLM remains primary in AUTO when healthy/supported;
- Ollama is compatibility/fallback in the current program;
- explicit VLLM and explicit OLLAMA selections fail closed and MUST NOT silently
  switch;
- AUTO fallback is a new valid Foundation -> model view/selection -> Plan ->
  Admit -> Serve path, never a hidden Serve retry;
- native and Ollama model catalogs remain separate;
- no implicit model equivalence/translation across catalogs;
- provider Serve must verify actual current Foundation identity;
- historical persisted evidence must not become unreadable or stronger through
  migration;
- customer content/privacy and evidence rules;
- existing physical-lab safety rules.

RECOMMENDED:
- pass the existing verified Ollama substrate/generation or a small derived
  runtime identity into Serve rather than adding another boolean;
- implement a small generic schema migration registry with per-kind sequential
  upgrades;
- use a small fallback decision/orchestration seam above Foundation selection
  rather than embedding fallback in Serve;
- keep fallback model/Plan resolution injected/delegated to the selected
  macropath so catalogs remain separate.

DELEGATED:
- exact class/module/helper decomposition;
- migration function representation;
- private orchestration/refactor structure;
- fixture shape;
- bounded polling/reconciliation mechanics;
- routine implementation details.

Cursor may choose a materially cleaner bounded technical realization if all
binding semantics remain true and the paste-back explains the deviation.

======================================================================
PRODUCT PURPOSE
======================================================================

This package is about **trustworthy continuity**, not merely adding more
branches.

Bundle 05 showed that the Ollama serving lifecycle works. Now Machi must prove
the complete chain:

```text
verified runtime realization
      ↓
verified hardware-bound Foundation generation
      ↓
qualified provider model/settings
      ↓
provider Plan
      ↓
ResourceManager reservation
      ↓
actual matching Foundation
      ↓
exact provider digest
      ↓
inference proof
```

At the same time, Kultrun needs the beginning of an availability policy:

```text
AUTO
  ↓
is primary native/vLLM Foundation healthy + supported?
  ├─ YES → use native/vLLM path
  └─ NO  → evaluate/select Ollama fallback path
```

This must be explainable and auditable. An administrator should later be able to
see:
- which mode was requested;
- which path was selected;
- why;
- what was invalidated/recomputed;
- which exact runtime/model served;
- whether fallback occurred.

======================================================================
SCOPE / NON-SCOPE
======================================================================

IN SCOPE:
A. actual Foundation-generation/environment verification at provider Serve;
B. renv-vs-fgen identity/evidence repair;
C. bounded Kernel schema migration/readback mechanism;
D. truthful migration of historical Ollama qualification v1;
E. K-03 retirement if all stated requirements are met;
F. provider Serve STOP/reconciliation hardening;
G. local/full regression/package gates;
H. one short physical corrected Ollama identity-chain reproof;
I. local AUTO macropath decision/orchestration semantics;
J. local proof that fallback recomputes downstream and uses a new reservation.

OUT OF SCOPE:
- physical production-grade automatic live failover;
- fallback after arbitrary request/token failure;
- automatic semantic matching of a native model to an Ollama model;
- multi-model Ollama policy;
- cross-host/fleet failover;
- UI;
- public Ollama API;
- AMD;
- Dynamo;
- training/indexing workload abstraction;
- changing vLLM-primary / Ollama-fallback policy.

======================================================================
ACTION 1 — RECONCILE IDENTITY TRUTH
======================================================================

Inspect repository and retained physical/lab evidence and establish the exact
meaning of every identifier used in Bundle 05.

Binding meanings:
- `renv_...` = managed runtime-environment / realized artifact identity;
- `fgen_...` = verified Ollama Foundation generation identity;
- execution-environment fingerprint = material accelerator/runtime environment;
- provider digest = immutable Ollama model identity.

Determine whether Bundle-05 qualification and Plan actually cited a real
`fgen_...` or incorrectly used `renv_...`.

Do NOT infer the answer from the prose report.

Use raw stored/lab evidence where available.

Disposition:
- if source behavior was correct and only documentation/paste-back labels were
  wrong: repair docs/evidence labels; preserve the A40 physical result;
- if qualification/Plan used the wrong identity class: correct source and mark
  the old deployment evidence as provider-functional but not generation-bound.

Every final evidence record should display `renv` and `fgen` separately when
both matter.

======================================================================
ACTION 2 — BIND PROVIDER SERVE TO THE ACTUAL VERIFIED FOUNDATION
======================================================================

Provider Serve must no longer trust a caller-supplied `foundation_ready: bool`
as sufficient runtime identity.

Functional requirements before residency/inference:
- current provider is the expected provider;
- current verified Foundation generation id equals the Plan generation id;
- current execution-environment fingerprint equals the Plan fingerprint input;
- runtime/Foundation support is READY/verified;
- qualification still covers the Plan;
- ResourceReservation still authorizes the Plan.

A stale, different, unresolved, or unverified Foundation must refuse before
preload/residency/inference.

Do not duplicate Ollama Foundation verification logic inside Serve. Consume the
already verified result/identity.

Native Serve semantics must remain unchanged.

QA must include:
- correct generation accepted;
- wrong generation refused;
- correct generation + wrong execution fingerprint refused;
- unresolved/unready Foundation refused;
- same model digest on the wrong Foundation does not bypass refusal.

======================================================================
ACTION 3 — COMPLETE KERNEL SCHEMA EVOLUTION / K-03
======================================================================

Product purpose:
Machi must remain able to explain historical state after software upgrades.
Schema evolution may make old evidence safer or more explicit, but may never
silently erase it, misread it, or strengthen what it proved.

Implement the bounded mechanism required by K-03.

Functional behavior:
- a known older persisted contract version can be read through a registered
  deterministic upgrade path;
- upgrades are sequential and explicit per kind/version;
- unknown kinds/versions still fail closed;
- migration never invents evidence that was not present;
- Store readback can return the current contract after migration;
- where K-03 requires rewrite-on-read, the upgraded current record is persisted
  safely and the migration is durably recorded;
- repeated reads converge/idempotently do not create migration churn.

Historical Ollama qualification v1 MUST migrate truthfully:
- preserve digest/provider/outcome/etc. supported by v1;
- represent context binding as **not_sent** because v1 did not prove num_ctx was
  supplied;
- migrated v1 evidence MUST NOT cover a provider Plan;
- current v2 context-bound evidence still covers when otherwise valid.

Before retiring K-03:
- inventory every current contract kind with schema_version > 1;
- for each, establish whether an older version was actually persisted/shipped;
- if historical persisted records exist, provide the required upgrade path;
- if an older shape never shipped/persisted, document that evidence rather than
  inventing a fake migration;
- prove nested/store/journal behavior is not silently broken by the mechanism.

Do not turn this into a general database framework.

Cursor owns the smallest correct Kernel implementation.

Update K-03 only if its stated retirement condition is genuinely satisfied.

======================================================================
ACTION 4 — PROVIDER SERVE RECONCILIATION / RECOVERY
======================================================================

The previous run showed provider unload can lag.

Add bounded recovery semantics so a STOP that initially fails to prove absence
does not strand product state indefinitely or release resources incorrectly.

Product behavior:
- STOP requests unload and waits only a bounded period;
- if absence is proved, instance becomes STOPPED;
- if absence is not proved, reservation remains held and success is not claimed;
- a later reconciliation action may re-observe provider state;
- if the expected digest is now absent, reconciliation may converge the
  instance to STOPPED without releasing the reservation;
- if expected digest remains resident or provider state is unresolved, report
  that truth and keep the hold;
- wrong identity must never be normalized into STOPPED/READY success;
- release remains an explicit ResourceManager action.

RECOMMENDED:
provide a small provider Serve reconcile operation/report rather than embedding
an unbounded wait into STOP.

Do not attempt to control Ollama's scheduler or invent lease/preemption policy.

======================================================================
ACTION 5 — LOCAL QA / IMMUTABLE CANDIDATE
======================================================================

Before server creation, prove the product behavior—not only green tests.

Required functional QA:
- provider Serve generation/environment mismatch refusals;
- v1 Ollama qualification read/upgrade and no coverage;
- v2 qualification current coverage;
- migration idempotence and unknown-version fail-closed behavior;
- K-03 inventory/retirement evidence;
- renv/fgen kept distinct;
- STOP lag then reconciliation to STOPPED;
- STOP failure never releases the hold;
- native Plan/Admit/Serve regression;
- provider Plan/Admit/Serve regression;
- no customer prompt/response persisted;
- one-ledger accounting remains intact.

Then run:
- targeted tests;
- full `tests/machi`;
- architecture checks;
- ruff;
- strict mypy;
- clean wheel;
- isolated-wheel `verify_ok`.

Build one exact candidate for physical reproof.

======================================================================
ACTION 6 — PHYSICAL CORRECTED IDENTITY-CHAIN REPROOF
======================================================================

Only after Action 5 passes.

Follow the existing RunPod policy exactly:
- official tooling;
- positively owned disposable Pod only;
- one Pod at a time;
- NVIDIA <= $1.50/hour;
- live known balance >= $5;
- $40/session / $80/day;
- <=90 minutes;
- <=3 provisioning retries;
- no network volumes;
- never touch pre-existing/ambiguous Pods.

Prefer A40 or L40S where available within policy. This is a correction/reproof,
not a breadth campaign.

Use the exact built wheel; no remote source edits.

Reproduce one compact chain using the small accepted Ollama model and context
2048:

1. Discover/Capacity.
2. Realize/verify managed Ollama Foundation.
3. Print/store both:
   - runtime environment id `renv_...`;
   - verified Foundation generation id `fgen_...`;
   - execution-environment fingerprint.
4. Qualify exact digest at num_ctx 2048.
5. Compose provider Plan using the real `fgen`.
6. Admit through normal ResourceManager.
7. Start Serve with the **actual verified current Foundation object/identity**.
8. Prove exact digest + real token.
9. STOP; prove absent.
10. Explicit release.
11. Prove wrong/stale Foundation identity is refused locally/physically where
    safe without mutating the real daemon.

If the old Bundle-05 run already used the correct fgen and only its document
label was wrong, this physical run still serves as acceptance of the new Serve
generation verification source code.

Capture no prompt/response text.

On product defect:
- fix locally;
- rebuild;
- redeploy exact new wheel;
- rerun affected proof.

On environment block:
- record typed block;
- do not fabricate PASS.

Terminate the owned Pod on success or terminal product failure.

======================================================================
ACTION 7 — BOUNDED AUTO FALLBACK CONTROL-PLANE SEAM
======================================================================

Execute this action only after the local correction gates pass. Physical
identity-chain reproof may run before or after this local slice as practical,
but no physical AUTO claim is required.

### Product policy already accepted

Current program policy:
- AUTO prefers healthy/supported native/vLLM;
- AUTO may choose Ollama only when native/vLLM is unsupported/unhealthy by
  approved Foundation policy;
- explicit VLLM fails closed if VLLM is unavailable;
- explicit OLLAMA fails closed if Ollama is unavailable;
- fallback is a **new valid deployment path**, not a hidden Serve retry.

### Functional scope

Implement the smallest control-plane seam that can make and explain that
decision.

The result should record at least:
- requested mode: AUTO / explicit VLLM / explicit OLLAMA;
- primary Foundation state;
- fallback Foundation state where relevant;
- selected path or typed refusal;
- reason;
- what downstream state must be invalidated/recomputed;
- policy version/provenance.

For AUTO:
- healthy/supported vLLM -> select vLLM; do not touch Ollama deployment state;
- vLLM typed unsupported/unhealthy + valid Ollama Foundation -> select Ollama
  fallback;
- neither valid -> typed refusal;
- unknown/unresolved must not optimistically fall back unless approved policy
  explicitly classifies it as unavailable.

For explicit modes:
- no silent switch.

### Separate catalogs remain binding

AUTO selection of Ollama does NOT mean:
"convert the selected Machi/native model into an Ollama model."

When Foundation/macropath changes:
- invalidate the old downstream model view/selection;
- derive/use the Ollama-owned catalog and provider candidate path;
- obtain an independently valid Ollama qualification;
- compose a provider Plan;
- obtain a **new** ResourceReservation;
- Serve through the Ollama path.

The fallback seam may delegate those downstream operations to existing
macropath-specific services/factories. Do not create cross-catalog model
equivalence in this bundle.

### Local end-to-end fallback QA

Prove with fixtures/controlled local services:
1. AUTO + healthy vLLM -> native path selected, no Ollama plan/admission.
2. AUTO + vLLM unsupported/unhealthy + qualified Ollama candidate -> Ollama
   path selected.
3. Fallback does not reuse native Plan/reservation/ServingInstance identities.
4. New Ollama Plan -> normal ResourceManager admission -> provider Serve works.
5. Explicit VLLM failure does not switch.
6. Explicit OLLAMA failure does not switch.
7. Neither available -> typed failure.
8. Decision/evidence contains no customer content.
9. Existing native and explicit Ollama paths work unchanged.

Do not implement automatic fallback after an active user request fails.
Do not add retries between runtimes inside Serve.

======================================================================
FIX VS ARCHITECTURAL AMENDMENT
======================================================================

Cursor SHOULD fix and continue when:
- migration/readback code has an implementation defect;
- current runtime identity is wired incorrectly;
- docs confuse renv/fgen;
- reconcile state transitions are wrong;
- fallback decision code violates the already-set policy;
- tests/physical packaging reveal ordinary defects.

Cursor MAY choose and explain:
- the internal migration registry design;
- exact provider-runtime identity value object;
- exact fallback decision class/module;
- refactors that share logic while preserving meanings.

Cursor MUST STOP if work would:
- change vLLM-primary/Ollama-fallback policy;
- introduce cross-catalog model equivalence/automatic conversion;
- make Serve itself switch runtimes;
- weaken Foundation identity verification;
- create a second resource ledger;
- change explicit-mode fail-closed behavior;
- change privacy/security posture;
- introduce a new mandatory provider/dependency;
- broaden fallback to training/indexing/fleet orchestration;
- materially revise Product Vision.

======================================================================
QA / ACCEPTANCE INTENT
======================================================================

This package is accepted only if we can say:

- historical evidence survives upgrades truthfully;
- the serving runtime identity is as trustworthy as the model identity;
- renv and fgen are distinguishable in evidence;
- failed STOP/reconciliation never fabricates free resources;
- corrected Ollama Serve is re-proven physically;
- AUTO selection is explainable and deterministic locally;
- AUTO fallback creates a fresh downstream deployment chain;
- explicit choices never silently switch;
- native/vLLM remains unaffected.

Green unit tests alone are insufficient.

======================================================================
SUPPORT CLAIM
======================================================================

If every executed gate passes, the allowed new claim is:

> Machi can physically bind an Ollama provider Plan/Serve deployment to the
> actual verified Foundation generation and exact model digest on the tested
> NVIDIA environment, preserve historical provider qualification evidence
> across schema evolution without strengthening it, and locally enforce a
> deterministic AUTO policy that prefers healthy/supported native-vLLM and
> selects an independently valid Ollama fallback path only when the primary
> Foundation is unavailable by policy.

Do NOT claim:
- physical automatic live failover;
- runtime switching after arbitrary inference failure;
- automatic equivalent-model translation;
- NVIDIA-wide Ollama support;
- production HA;
- multi-host/fleet fallback.

======================================================================
FINAL GATES / CLOSURE
======================================================================

After all executed work:
- rerun targeted + full local tests;
- architecture checks;
- ruff;
- strict mypy;
- clean final wheel;
- isolated `verify_ok`;
- update canonical docs, debt, schema fingerprint/evolution evidence, physical
  evidence and program status;
- distinguish physical passing source/wheel from docs-only final HEAD if needed;
- push clean exact HEAD;
- prove local == origin.

If Bundle-05 corrections are genuinely closed, create a new recovery checkpoint
for corrected authorized Ollama Serve.

Do NOT mark the Ollama macropath fully closed unless all remaining Chunk-6
closure requirements in the program are actually satisfied.

Do not begin physical AUTO-fallback breadth work beyond this package.

======================================================================
MANDATORY PASTE-BACK
======================================================================

==================== BEGIN PASTE BACK — OLLAMA BUNDLE 06 ====================

A. STATUS / actions executed  
B. Starting SHA / physical passing SHA / final SHA  
C. Product outcome achieved  
D. renv vs fgen reconciliation result  
E. Bundle-05 evidence disposition  
F. Serve actual-Foundation binding implementation  
G. Wrong/stale Foundation refusal QA  
H. Schema migration mechanism / Kernel behavior  
I. Ollama qualification v1 -> current migration truth  
J. Inventory of all current versioned contract bumps  
K. K-03 disposition and evidence  
L. Provider STOP/reconciliation behavior  
M. Local functional QA  
N. Candidate wheel build/SHA/isolated verify  
O. RunPod preflight / owned Pod  
P. Physical host / renv / fgen / execution fingerprint  
Q. Context-2048 qualification result  
R. Corrected provider Plan/Admit result  
S. Corrected Serve exact runtime+digest proof  
T. STOP / absence / release proof  
U. Pod termination proof  
V. AUTO fallback control-plane design  
W. AUTO healthy-vLLM preference proof  
X. AUTO vLLM-unavailable -> Ollama fresh-chain proof  
Y. Explicit VLLM/OLLAMA fail-closed proof  
Z. Proof fallback does not reuse stale model/Plan/reservation/instance  
AA. Decisions/deviations from recommendations  
AB. Architecture amendments encountered, if any  
AC. Exact support claim earned  
AD. Remaining debt / Chunk-6 work not yet closed  
AE. Full final gates / local==origin / checkpoint  
AF. Final status

End exactly one of:

`STOP — OLLAMA BUNDLE 06 COMPLETE. WAIT FOR LEAD REVIEW.`

`DECISION_REQUIRED_OLLAMA_FALLBACK_AMENDMENT — WAIT FOR LEAD DECISION.`

`ENVIRONMENT_BLOCKED — WAIT FOR LEAD REVIEW.`

`PRODUCT_FAILURE — WAIT FOR LEAD REVIEW.`

==================== END PASTE BACK — OLLAMA BUNDLE 06 ====================

Do not continue beyond this package.
