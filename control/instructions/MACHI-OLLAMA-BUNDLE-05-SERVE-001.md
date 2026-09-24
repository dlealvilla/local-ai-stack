# CURRENT LEAD DEVELOPER INSTRUCTION

**Instruction ID:** `MACHI-OLLAMA-BUNDLE-05-SERVE-001`  
**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Starting integration HEAD:** `ea9cb26a6034eeaca1058d6635ee4008fc833bed`  
**Integration branch:** `automation/ollama-macropath`  
**Execution style:** PRODUCT-FIRST MULTI-SLICE BUNDLE  
**Physical server:** CONDITIONAL YES after local gates  
**AUTO fallback:** FORBIDDEN  
**General multi-model serving:** FORBIDDEN

Read first:
- `control/EXECUTION-BUNDLE-POLICY.md`
- `control/CORE-VS-COMMODITY-POLICY.md`
- `control/OLLAMA-SERVE-AUTH-DECISION.md`
- `control/OLLAMA-BUNDLE-04-LEAD-REVIEW.md`
- `control/OLLAMA-BUNDLE-05-SERVE.md`
- `control/OLLAMA-CHUNK-03-DUAL-QUALIFIER-DECISION.md`
- `control/OLLAMA-CHUNK-02-CLOSED.md`
- authoritative Product Vision / Strategy / Machi Architecture / Plan / Admit /
  Serve / Telemetry / Debt docs
- exact current native M7/M8/M9 implementation and tests
- exact Ollama v0.34.3 public API/provider behavior

======================================================================
DIRECTION LEVELS
======================================================================

BINDING:
- Product Vision and support boundaries;
- accepted Option A refined authorization decision;
- separate native/Ollama model catalogs;
- one ResourceManager and one ResourceReservation ledger;
- provider digest is immutable Ollama model identity;
- Ollama residency is evidence/mechanics, never resource authorization;
- qualification settings used for coverage must match the settings actually sent
  to Ollama;
- native/vLLM semantics and physical evidence remain valid;
- STOP and reservation release are separate lifecycle actions;
- privacy/evidence rules;
- physical-lab safety policy.

RECOMMENDED:
- sibling provider plan/configuration/request contracts rather than overloading
  native artifact fields;
- small shared admission/Serve internals where semantics genuinely match;
- provider-specific evidence contracts where native artifact identity cannot be
  represented truthfully.

Cursor may choose a materially cleaner bounded design if it preserves every
binding semantic and explains the difference.

DELEGATED:
- private code structure;
- helper/module decomposition;
- routine refactoring;
- fixture and test mechanics;
- internal naming and ordinary implementation technique.

======================================================================
PRODUCT PURPOSE
======================================================================

The goal is not merely to add an Ollama branch to ServeService.

The goal is to make Ollama a **first-class controlled execution macropath**
inside the same Kultrun/Machi product:

- Ollama keeps ownership of its own model catalog and execution mechanics.
- Machi knows what exact model/settings were qualified.
- Machi creates the serving intent.
- ResourceManager grants the physical resource authority.
- Ollama runs only as the provider implementation behind that product intent.
- Machi verifies the exact provider identity and records proof.
- Operators can stop/restart without losing or fabricating resource authority.

This directly advances the Stage-1 promise that Kultrun can safely and
explainably run AI across more than one runtime strategy while keeping one
product control model.

======================================================================
FUNCTIONAL OUTCOME / USER-ADMIN BEHAVIOR
======================================================================

When complete, the system should be able to demonstrate this bounded lifecycle:

1. An Ollama catalog model has exact provider identity and valid qualification
   evidence for the requested context/concurrency.
2. Machi creates a provider-backed model-serving Plan without manufacturing a
   ModelArtifact.
3. ResourceManager evaluates current Capacity and admits/refuses it through the
   same ledger used by native workloads.
4. An admitted Ollama deployment can establish expected residency.
5. Before inference, Machi verifies the expected provider digest.
6. A real inference request succeeds.
7. After inference, Machi verifies the same digest.
8. Machi persists a truthful Serve/Inference proof and normalized analytics.
9. STOP unloads and proves the expected model absent.
10. The reservation remains RESERVED after STOP.
11. The same still-current reservation can authorize a restart/re-entry.
12. Re-inference again proves exact identity.
13. A later explicit ResourceManager release returns resources.
14. Released reservation cannot authorize another start.
15. Existing native/vLLM Plan/Admit/Serve continues to pass unchanged.

======================================================================
PRODUCT VISION ALIGNMENT
======================================================================

Preserve:
- self-hosted/local execution;
- customer control;
- local customer content by default;
- runtime/model-provider replaceability;
- one global resource authority;
- truthful provenance instead of fake cross-provider identities;
- explainable deployment state;
- durable evidence;
- offline/air-gap-compatible direction;
- low admin burden through safe defaults;
- future ability to compare runtimes empirically without forcing a common model
  store;
- ability to generalize later when product evidence justifies it.

Do not optimize for a theoretically universal resource/workload ontology now.
Complete the model-serving exoskeleton first.

======================================================================
SCOPE
======================================================================

IN SCOPE:
A. repair context-bound Ollama qualification;
B. local provider-backed Plan/Admit contracts and orchestration;
C. local Ollama Serve lifecycle;
D. exact provider digest proof around inference;
E. STOP/restart/re-entry/release lifecycle;
F. normalized/durable Serve proof and operational analytics;
G. physical requalification at explicit context;
H. physical one-model Ollama Serve + restart/re-infer proof;
I. native regression and support-claim documentation.

OUT OF SCOPE:
- AUTO fallback;
- routing between vLLM and Ollama;
- multiple concurrently served Ollama models;
- generic training/indexing claims;
- third runtime/provider;
- public/off-host Ollama API;
- authentication debt retirement;
- UI;
- cross-customer learning;
- general Ollama pull/acquisition productization;
- AMD qualification;
- Dynamo.

======================================================================
DELIVERY ACTIONS
======================================================================

Treat this as one coherent product delivery cycle.

### Action 1 — Reconcile repository truth

Before editing:
- inspect the accepted native Plan/Admit/Serve contracts and invariants;
- inspect the current Ollama qualification/residency contracts;
- identify exactly which concepts are native-artifact-specific versus genuinely
  model-serving-generic;
- preserve old decoding/evidence where required;
- do not redesign unrelated blocks.

### Action 2 — Correct qualification coverage truth

Make requested context material to actual Ollama execution.

Functional requirements:
- requested qualification context must be sent through public Ollama runner
  options on preload and token proof;
- the same requested context must remain material across the resident runner;
- qualification identity/fingerprint already citing context must now describe
  what was actually requested from the provider;
- if provider behavior makes the requested context unverifiable, evidence must
  be UNRESOLVED/refused rather than claiming exact coverage.

Concurrency remains 1 for this bounded stage unless repository truth already
has a truthful provider setting.

Do not rewrite Bundle-04 evidence. Mark it historical provider-functional
evidence, not exact 2048 coverage.

### Action 3 — Build truthful provider-backed serving intent

Implement the accepted Option A semantics.

Required functional information includes:
- immutable Plan identity/fingerprint;
- provider/model identity;
- display name separate from immutable digest;
- Foundation/generation identity;
- capacity evidence identity;
- accelerator identity;
- context/concurrency;
- provider qualification evidence identity;
- relevant serving settings/provenance;
- resource request.

Do not populate native artifact/revision/dtype fields with fabricated Ollama
values.

The exact contract/code shape is Cursor's implementation decision inside the
accepted architecture.

### Action 4 — Integrate with the existing ResourceManager ledger

A provider-backed model-serving request must:
- receive stale-Capacity protection;
- bind exact accelerator/resource bytes;
- use the same active-hold accounting as native;
- be idempotent/re-entry safe where native semantics require it;
- produce an existing `ResourceReservation` or a backward-compatible
  equivalent that is still one ledger and one accounting truth.

Do not create an Ollama-only ledger.

Recommended: share/refactor internal admission placement/accounting logic rather
than duplicating it.

### Action 5 — Build bounded Ollama Serve lifecycle

Create the smallest local Serve capability that realizes the product behavior.

It must:
- require a valid current provider deployment intent + ResourceReservation;
- require the verified managed Ollama Foundation/generation;
- establish/refresh expected residency;
- prove exact name+digest before inference;
- send the effective context setting required by the plan;
- issue one bounded synthetic inference in tests/acceptance;
- prove the same digest after inference;
- persist a provider-appropriate serving instance/proof without lying about
  ModelArtifact identity;
- STOP through public unload;
- prove expected digest absent;
- retain reservation after STOP;
- permit bounded restart under the still-current reservation;
- refuse restart after reservation release.

Do not make `/api/ps` or keep_alive the authorization check. They are provider
state/evidence after Machi authorization.

### Action 6 — Analytics and evidence

Normalize what is semantically comparable:
- provider/runtime/model identity;
- context/concurrency;
- reservation;
- request outcome;
- input/output token counts;
- generation duration/tokens per second;
- residency transitions;
- start/stop/restart outcome;
- provider-reported VRAM with explicit source;
- InferenceProof/result.

Raw provider facts remain distinct where meanings differ.

No prompt/response text in durable telemetry.

### Action 7 — Local QA and package candidate

Before physical server creation prove functionally:
- context is actually sent in preload and inference;
- qualification coverage mismatch is refused;
- native artifact-backed Plan is unchanged;
- provider Plan cannot fake artifact identity;
- provider Plan admission and native Plan admission share active accounting;
- stale capacity is refused;
- no admission -> no Serve;
- wrong/missing digest -> no inference proof;
- STOP proves absent but keeps reservation;
- restart works with valid reservation;
- released reservation cannot restart;
- unload failure does not release or misreport resources;
- provider daemon/API failure becomes typed failure;
- customer content is not persisted;
- native full Plan/Admit/Serve suite remains green.

Then:
- full tests;
- architecture checks;
- ruff;
- strict mypy;
- clean wheel;
- isolated-wheel `verify_ok`.

Build one immutable physical candidate.

======================================================================
PHYSICAL ACCEPTANCE
======================================================================

Only after local gates pass.

Follow the existing binding RunPod policy:
- official RunPod tooling only;
- only positively owned disposable Pod;
- one at a time;
- NVIDIA <= $1.50/hour;
- live balance >= $5 and known;
- $40/session / $80/day;
- <=90 minutes Pod lifetime;
- <=3 provisioning retries;
- no network volume;
- do not touch pre-existing Pods.

Prefer an L40S under the existing price limit to extend Bundle-04/native
evidence. If unavailable, use another eligible single NVIDIA host and narrow
support claims accordingly.

If authentication/connection/user permission is needed, STOP and ask Daniel.

Use the exact built wheel. No remote source patching.

### Physical Phase 1 — context-true requalification

Use the same small provider model if still appropriate:
`smollm2:135m-instruct-q8_0`.

Lab pull remains lab setup, not a product acquisition claim.

Run a clean cold qualification at explicit context **2048**, concurrency 1:
- expected digest absent before;
- ResourceManager qualification hold;
- Machi shadow;
- preload carrying num_ctx 2048;
- provider residency proof;
- token proof carrying num_ctx 2048;
- post-token digest proof;
- durable comparison event;
- unload;
- absence proof;
- release.

The physical evidence must establish that the provider was asked to use 2048.
If provider-observable effective context is available from bounded logs/evidence,
capture it. If the provider still internally chooses a different effective
context despite explicit num_ctx, do not claim exact coverage and STOP for
review.

### Physical Phase 2 — normal provider Plan/Admit/Serve

Only after Phase 1 exact-context qualification PASS.

Using current fresh capacity evidence:
- create provider-backed Plan for the same exact digest/context/concurrency;
- normal ResourceManager admission;
- start Ollama serving lifecycle;
- prove expected digest;
- real small inference;
- prove same digest;
- persist Serve/Inference proof.

This is normal deployment semantics, not qualification probe admission.

### Physical Phase 3 — STOP / restart / release

Prove the lifecycle distinction:

```text
Serve PASS
 -> STOP
 -> expected digest absent
 -> reservation still RESERVED
 -> restart using same still-current reservation
 -> inference PASS
 -> STOP
 -> expected digest absent
 -> explicit ResourceManager release
 -> subsequent restart REFUSED
```

If current capacity/foundation evidence becomes stale in a way that accepted
native semantics would require replanning/re-admission, follow the product rule
rather than forcing reuse.

======================================================================
FIX VS ARCHITECTURAL AMENDMENT
======================================================================

Cursor SHOULD fix and continue when:
- implementation doesn't send context correctly;
- contract wiring/fingerprints are wrong but semantics are clear;
- provider adapter/lifecycle behavior has a coding defect;
- tests expose persistence/idempotency/cleanup bugs;
- a bounded refactor is needed to reuse admission/Serve internals;
- physical packaging has the same class of implementation defect as Bundle 04.

Cursor MAY make a technical recommendation/choice and continue when:
- two internal code organizations preserve the same accepted semantics;
- a sibling provider contract can be located in more than one sensible module;
- a small generic helper improves native/provider code reuse without changing
  public meaning.

Cursor MUST STOP for architecture amendment if work would:
- change Option A semantics;
- redefine existing native artifact fields;
- make ResourceReservation provider-specific;
- create a second ledger;
- make Ollama residency authoritative;
- change STOP-vs-release semantics;
- change privacy/security posture;
- require a new mandatory dependency/provider;
- generalize into a training/indexing workload ontology;
- materially alter Product Vision or native support semantics.

======================================================================
SUPPORT CLAIM IF ALL PHYSICAL GATES PASS
======================================================================

The maximum claim from this package is intentionally narrow:

> On the exact qualified NVIDIA host/environment and exact Ollama 0.34.3
> generation/model digest/context tested, Machi can create a provider-backed
> model-serving Plan, admit it through the same global ResourceManager ledger as
> native workloads, serve real Ollama inference with exact digest proof,
> stop/restart under a valid held reservation, and release resources explicitly.

Do NOT claim:
- Ollama generally supported across NVIDIA;
- all contexts/models;
- multi-model scheduling under Machi;
- malicious-local-process enforcement;
- AUTO fallback;
- cross-runtime winner;
- AMD;
- production UI readiness.

======================================================================
FINAL GATES / CLOSURE
======================================================================

After physical work:
- fix any product-code defect locally;
- rebuild immutable candidate;
- rerun affected physical acceptance as required;
- run final targeted + full local gates;
- build clean final wheel and isolated `verify_ok`;
- update canonical docs/debt/evidence;
- distinguish physical passing wheel SHA from later docs-only/source HEAD;
- push clean exact HEAD to `origin/automation/ollama-macropath`;
- prove local == origin.

If all gates pass, create a recovery checkpoint for the accepted Ollama
authorized-Serve state.

Do not begin AUTO fallback or the next package.

======================================================================
MANDATORY PASTE-BACK
======================================================================

==================== BEGIN PASTE BACK — OLLAMA BUNDLE 05 SERVE ====================

A. STATUS / slices completed  
B. Starting/final source SHA  
C. Product outcome achieved  
D. Accepted Option-A implementation shape and any deviation from recommendation  
E. Context-truth correction  
F. Qualification coverage semantics / old Bundle-04 evidence treatment  
G. Provider-backed Plan/configuration identity  
H. ResourceRequest / one-ledger admission behavior  
I. Native Plan/Admit regression proof  
J. Ollama Serve lifecycle implementation  
K. Provider identity proof before/after inference  
L. STOP vs reservation-release behavior  
M. Restart/re-entry behavior  
N. Durable Serve/Inference proof and analytics  
O. Local QA / functional acceptance  
P. Candidate build ID/SHA256 / isolated verify_ok  
Q. RunPod preflight / owned Pod  
R. Physical host identity / managed Foundation  
S. Context-2048 physical requalification  
T. Normal provider Plan/Admit physical result  
U. Real Serve inference proof  
V. STOP -> restart -> re-infer -> STOP -> release -> refusal proof  
W. Physical analytics / residency / VRAM provenance  
X. Implementation defects found/fixed during run  
Y. Architecture amendments encountered, if any  
Z. Exact support claim earned  
AA. Remaining debt / non-scope  
AB. Pod termination proof  
AC. Final tests/package gates  
AD. Local/origin equality / checkpoint  
AE. Final status

End exactly one of:

`STOP — OLLAMA BUNDLE 05 SERVE COMPLETE. WAIT FOR LEAD REVIEW.`

`DECISION_REQUIRED_OLLAMA_SERVE_AMENDMENT — WAIT FOR LEAD DECISION.`

`ENVIRONMENT_BLOCKED — WAIT FOR LEAD REVIEW.`

`PRODUCT_FAILURE — WAIT FOR LEAD REVIEW.`

==================== END PASTE BACK — OLLAMA BUNDLE 05 SERVE ====================

Do not continue beyond this package.
