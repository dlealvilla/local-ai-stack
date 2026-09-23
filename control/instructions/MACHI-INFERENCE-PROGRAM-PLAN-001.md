# CURRENT LEAD DEVELOPER INSTRUCTION

**Instruction ID:** `MACHI-INFERENCE-PROGRAM-PLAN-001`  
**Mode:** PROGRAM PLANNING / ARCHITECTURE ALIGNMENT ONLY  
**Implementation:** FORBIDDEN IN THIS INSTRUCTION  
**Physical servers:** DO NOT CREATE  
**Scope horizon:** complete the deployment spine through real request inference, then extend the same governed semantics to the approved additional serving macropaths.

---

# 0. WHY THIS INSTRUCTION EXISTS

We are about to move from one-step-at-a-time development into a controlled multi-step automation program.

Before any automated sequence runs, design the next **exactly 30 bounded development steps** as one coherent end-to-end program.

This plan must derive from, in authority order:

1. `docs/STRATEGY.md` — strategic serving-path direction and product/lab split;
2. `docs/PRODUCT_VISION.md` — customer promise and product meaning;
3. `docs/machi/ARCHITECTURE.md` — active module boundaries and core pipeline;
4. `docs/machi/CONTRACTS.md` — contract semantics and invalidation;
5. `docs/machi/ROADMAP.md` — active build sequence and acceptance gates;
6. `docs/machi/TELEMETRY.md` — product event/provenance/privacy rules;
7. accepted evidence, debt, and current repository truth;
8. the Lead Developer principles in this instruction.

Do not let implementation convenience redefine a higher authority.

If these authorities currently disagree, identify the disagreement explicitly and propose the smallest canonical correction. Do not silently choose whichever document is easiest for implementation.

---

# 1. PRE-AUTOMATION RECOVERY POINT — VERIFY, DO NOT ALTER

Verify these Git branches exist:

```text
checkpoint/pre-automation-inference-2026-09-23
automation/inference-program
```

Both were created from the pre-automation `m9/serve` state.

Expected recovery lineage:

```text
implementation:
6a23a32cffcd1aa1bb51f44b9dcf1575b0a7fa2c

evidence:
fc57f24690904e9a9348b0c8f34b363e89b9addf

handoff-enabled HEAD:
0700e669267fd0db3d642192050a8654c9beb96c
```

The recovery branch is immutable operationally: do not force-update, rebase, delete, or repurpose it.

The automation program will branch from `automation/inference-program`.

No source changes in this planning instruction.

---

# 2. PROGRAM SCOPE — DECIDE AGAINST REPOSITORY TRUTH, THEN PLAN

The intended program scope is:

> Build and empirically prove everything required for Machi to take a supported host from host understanding through environment/runtime realization, feasible-model determination, model qualification, plan, admission, Serve, and a successful real request inference — with failures prevented as early as the responsible upstream domain can truthfully prevent them.

The first and primary implementation path is the **direct managed native vLLM path**.

After that path is proven end to end and diversified physically:

1. build/prove the **OllamaExecutionMacropath** as the compatibility/fallback serving path under the same Machi-owned global authority;
2. then investigate, gate, build, and empirically test the **NVIDIA Dynamo + NVIDIA Run:ai distributed-fabric path**, without making either system the product ontology or an unavoidable commercial dependency.

For this 30-step program, **physical GPU testing is NVIDIA-only**.

AMD physical qualification is NOT required in this program. However:
- the AMD managed-environment architecture already learned must remain correct;
- do not regress the managed ROCm userspace/provider seam;
- do not reintroduce a requirement that a provider image must already contain the exact runtime.

Out of scope for this 30-step program unless required solely to complete inference truth:
- Admin UI;
- Knowledge/RAG;
- identity/product user management;
- Team Brain;
- training/fine-tuning;
- marketplace;
- fleet control plane;
- licensing backend;
- public website;
- broad multi-host fleet scheduling unrelated to the explicit Dynamo/Run:ai experiment;
- general optimization/recommendation intelligence beyond what is needed to establish safe feasibility and qualification.

---

# 3. THE MOST IMPORTANT PRODUCT LOGIC

Treat this as a governing invariant.

Machi is not supposed to discover at Serve that an obviously incompatible model cannot run.

The intended narrowing funnel is:

```text
HOST / STORAGE / ACCELERATOR TRUTH
        ↓
CAPACITY + PREREQUISITE TRUTH
        ↓
FOUNDATION CANDIDATES
        ↓
FOUNDATION FEASIBILITY
        ↓
SELECTED FOUNDATION
        ↓
PROVISIONED + VERIFIED RUNTIME CAPABILITY
        ↓
MODEL UNIVERSE / CATALOG
        ↓
CHEAP POLICY + FORMAT + ARCHITECTURE FILTERS
        ↓
STRUCTURAL RUNTIME COMPATIBILITY
        ↓
MODEL REQUIREMENT ESTIMATION
        ↓
CURRENT CAPACITY FEASIBILITY
        ↓
EMPIRICAL QUALIFICATION WHERE NEEDED
        ↓
DEPLOYABLE MODELS
        ↓
MODEL SELECTION
        ↓
MODEL ARTIFACT
        ↓
DEPLOYMENT CONFIGURATION
        ↓
RESOURCE REQUEST
        ↓
RESOURCE RESERVATION
        ↓
SERVE
        ↓
REAL REQUEST INFERENCE
```

Each downstream domain may consume only candidates that survived the upstream authority responsible for that question.

A failure such as:

> vLLM starts, health succeeds, but the first token fails because the model/backend/kernel combination was never actually compatible

must be treated as evidence that the compatibility/qualification funnel was insufficient.

The correct product response is normally:

> improve the earlier feasibility or empirical qualification gate so the model never becomes DeployableModels membership and is never selected/loaded.

Serve remains the final proof and can still expose genuinely unknowable runtime defects, but it must not be the normal compatibility filter.

Explicitly review every current M5→M9 boundary for ways a candidate can bypass this narrowing funnel.

---

# 4. LEAD-DEVELOPER PRINCIPLES EXTRACTED FROM PRIOR INTERVENTIONS

Treat the following as design principles to validate against repository truth and carry into the 30-step plan.

## 4.1 Capability-first, not vendor-first

The product understands generic capabilities.

Concrete implementations sit behind adapters/providers.

Examples:
- accelerator discovery is not NVIDIA discovery;
- runtime environment is not CUDA or ROCm;
- serving path is not vLLM;
- distributed inference fabric is not Dynamo;
- scheduler/orchestrator is not Run:ai.

Core owns concepts; adapters/providers own implementations.

## 4.2 The environment is part of the product

Do not assume the host/provider pre-installs the exact userspace needed.

The AMD lesson is general:

```text
host provides the hard host boundary
(kernel/driver/device visibility)
        ↓
Machi verifies or realizes the userspace environment it requires
        ↓
Machi provisions/verifies the runtime
```

The same principle must be examined for NVIDIA, Ollama, Dynamo, and future paths.

## 4.3 No sacred test SKU

A40 was useful historical evidence, not a product dependency.

Testing should cover materially different hardware classes/conditions rather than wait indefinitely for one SKU.

Exact observed evidence remains exact; one SKU PASS is not automatically a whole-class PASS.

## 4.4 Fail early, and fail in the right Block

A model that is:
- policy-disallowed;
- architecture-incompatible;
- quantization/dtype-incompatible;
- unsupported by the installed engine/backend;
- impossible within current RAM/VRAM/storage/context/concurrency;
- empirically known not to execute in the exact environment

must not progress to model load.

Likewise:
- an invalid Foundation must not reach Model;
- an invalid Plan must not reach Admit;
- an unreserved configuration must not reach Serve.

## 4.5 Unknown is not zero and is not permission

Unresolved capacity, storage, runtime support, licensing, environment compatibility, or model feasibility must never be converted into a silent optimistic PASS.

## 4.6 Recommendation is not authority

Recommendations may rank.

They do not admit resources, create availability, or override feasibility.

ResourceManager remains the only authority that says a current DeploymentConfiguration may consume resources now.

## 4.7 Qualification and recommendation are different

Qualification queue:
> what candidate should we prove next?

Model selection/recommendation:
> among already deployable candidates, what should the administrator use?

Do not make “smallest/easiest to qualify first” synonymous with “best model”.

## 4.8 Acquire/load as late as practical

Use remote metadata/config/safetensors metadata to reject impossible candidates before downloading full weights.

Do not fully acquire every candidate merely to discover feasibility.

Do not load a model merely to discover something a cheaper earlier gate could prove.

## 4.9 Real inference is the final deployment proof

Readiness/health is not request inference.

A valid proof requires a structurally valid response with real generated token output and exact served-model identity.

## 4.10 Evidence claims must not outrun observations

Exact host/SKU/environment/model evidence is preserved.

Promotion to family/class/vendor support requires an explicit support rule and evidence.

## 4.11 Physical acceptance is product acceptance, not remote development

Build locally.
Freeze exact SHA/wheel.
Install exact artifact on a disposable host.
Run.
Capture evidence.
If a genuine product defect appears, fix locally, rebuild a new candidate, rerun.

Never patch source on the physical server and call it accepted.

## 4.12 Evidence is a strategic asset

All meaningful empirical work must be reproducible and queryable later.

A console log disappearing after a Pod is destroyed is not acceptable evidence.

## 4.13 Exoskeleton first

Do not turn this inference-completion program into a general scheduler, optimizer, fleet system, benchmark warehouse, enterprise UI, or deep intelligence program.

Add only the schemas/seams needed to keep future paths possible.

## 4.14 Version control is part of safety

Before large automated/risky increments:
- preserve a recovery point;
- keep the automation integration line separate;
- fork decision branches when credible architectural alternatives exist;
- never rewrite accepted evidence to make a later design look cleaner.

---

# 5. NATIVE vLLM PROGRAM — PRIMARY PATH

Plan the native direct vLLM path all the way to dependable inference first.

The plan should include any upstream correction required so that the following is true:

```text
supported host
→ correct managed environment
→ verified vLLM runtime
→ truthful feasible model set
→ empirically qualified DeployableModels
→ selected model
→ acquired/reused artifact
→ CURRENT Plan
→ ADMITTED reservation
→ ServingInstance
→ readiness
→ real request inference
→ stop/restart/re-infer
→ witness/evidence
```

Do not preserve M5/M6/M7/M8/M9 implementation merely because it exists if repository evidence shows a boundary allows impossible states.

Prefer bounded corrections to wholesale redesign.

---

# 6. NVIDIA PHYSICAL TEST STRATEGY

The 30-step plan must include a deliberate, coverage-driven physical campaign.

## Required hardware diversity

At minimum plan:
- one Ampere-class NVIDIA host;
- one Ada-class NVIDIA host.

A third NVIDIA class is allowed only if it adds meaningful information per dollar/hour, such as a new generation or materially different memory/capability boundary.

Do not run a third server merely to increase a count.

Current N1/N2 preferences may be used as starting policy:
- Ampere: A40 preferred, RTX A6000 allowed fallback;
- Ada: L40S preferred, then eligible fallback with exact memory envelope recorded.

But re-check live availability when the physical step actually runs.

## Model diversity

Plan **several model cases per physical host**, but do not run a Cartesian product.

The matrix should intentionally cover different failure surfaces.

Propose a small set such as:
- a known-good small baseline;
- a representative realistic model that comfortably fits;
- a different architecture and/or quantization/dtype path;
- a boundary/near-capacity model where useful;
- at least one deliberately incompatible catalog candidate that must be excluded **before acquisition/load**, proving the funnel.

An intentionally incompatible candidate is a negative qualification test, not permission to load a model expected to fail.

Where possible, reuse at least one common positive model across hardware classes for comparability.

## Metrics/evidence

Where measurable, capture:
- startup/provision duration;
- model acquisition/reuse duration;
- qualification duration;
- time to readiness;
- TTFT;
- tokens/sec or inter-token latency;
- request latency;
- input/output tokens;
- peak accelerator memory;
- peak RAM;
- reservation vs observed use;
- errors/retries;
- exact context/concurrency/configuration;
- cost and runtime;
- stop/restart behavior.

Do not invent arbitrary quality/performance PASS thresholds unless the product policy actually defines them.

Compatibility PASS and performance ranking are distinct.

---

# 7. OLLAMA EXECUTION MACROPATH — AFTER DIRECT vLLM

The strategy already names:

```text
VllmExecutionMacropath = PRIMARY
OllamaExecutionMacropath = COMPATIBILITY / FALLBACK
```

The 30-step plan should include the bounded provider-selection/design/implementation/testing sequence required to make Ollama a real fallback path.

Important:

Ollama may own local runner/model-store/load-unload mechanics that are legitimately part of Ollama.

Machi must still own global truth for:
- host/capabilities;
- capacity;
- policy;
- model catalog intent;
- eligibility;
- global admission;
- deployment identity;
- provenance/evidence;
- support claims.

Do not build a second incompatible control plane merely because Ollama has its own local management concepts.

The Ollama path must terminate in a real request inference proof through Machi semantics.

Plan physical testing on the NVIDIA lab hosts where practical, with several representative models, but use information gain rather than exhaustive combinations.

Provider Selection Gate requirements still apply before implementing a new concrete adapter, even when strategy has already approved the high-level path.

---

# 8. NVIDIA DYNAMO + RUN:AI MACROPATH — AFTER vLLM AND OLLAMA

The user explicitly wants this program to proceed next into a NVIDIA Dynamo + Run:ai serving/fabric path.

Treat this as a **distributed inference fabric / scheduler integration**, not as a replacement ontology for Foundation, Model, Plan, Admit, or Serve.

Before implementation, the plan must include a formal Provider Selection Gate and current upstream verification.

Research current official sources at execution time.

At minimum verify:
- current Dynamo stable release and supported backends;
- supported NVIDIA hardware/driver/CUDA combinations;
- local vs Kubernetes deployment options;
- how vLLM participates as a Dynamo backend;
- Run:ai version/support for Dynamo;
- Kubernetes/container/runtime requirements;
- topology/gang-scheduling requirements;
- licensing/entitlement/commercial restrictions;
- whether the planned lab environment can meaningfully test the integration.

Do not assume a 2025/early-2026 integration shape is still current.

Commercialization constraint:
- Dynamo may be a permissive/open component;
- Run:ai is an NVIDIA enterprise product and must be treated as a potentially commercial/entitled dependency.
- Therefore Run:ai must remain optional and replaceable behind a generic Machi scheduler/fabric provider boundary.
- Do not make Machi commercial viability depend on Run:ai.

The 30-step plan must identify the smallest meaningful physical acceptance:
- what can be proven on one host;
- what genuinely requires multi-node/Kubernetes;
- what evidence would justify paying for the larger experiment.

Do not jump into a multi-node cluster before the direct path and fallback path are dependable.

---

# 9. EMPIRICAL LAB DATA — FIRST-CLASS DEVELOPMENT INFRASTRUCTURE

The user requires all test metadata, raw/direct evidence, and logs to be retained and analyzable for future reference.

Design this as a **development/lab evidence system separate from Machi product state**.

Do not turn the product event journal into the lab database.

Propose a bounded implementation, preferably compatible with the existing Acceptance Lab and existing development conventions.

Default design hypothesis to evaluate:

## Structured index

A versioned SQLite empirical database with explicit schema migrations.

Capture at minimum:
- experiment/campaign/run/attempt IDs;
- task/instruction ID;
- branch;
- implementation SHA;
- evidence SHA;
- build identity;
- wheel/image digest;
- provider/region;
- server/Pod identity where safe;
- GPU vendor/model/count/memory/capability/topology;
- CPU/RAM/storage/mount/filesystem facts;
- OS/kernel;
- driver/CUDA/ROCm;
- Python/runtime/engine/executor versions;
- Foundation generation/environment fingerprint;
- model source/revision/digest/architecture/quantization/dtype;
- context/concurrency/tensor parallel/runtime config;
- Capacity/Plan/Reservation IDs;
- commands/probes/test scenario;
- expected vs actual;
- typed outcome/failure;
- readiness/inference proof IDs;
- timing/performance/resource metrics;
- cost/rate/duration;
- provisioning/teardown state;
- code-fix iteration lineage;
- artifact/log references.

## Raw evidence artifacts

Do not stuff arbitrary raw logs into relational columns.

Store raw stdout/stderr, command output, provider snapshots, manifests, benchmark data, and machine-readable evidence as immutable/content-addressed artifacts or an equivalent bounded artifact store.

The SQLite record references:
- content hash;
- media/type;
- path/object key;
- size;
- producer;
- capture timestamp;
- privacy classification.

Compress where useful.

## Analysis

Every material campaign should generate:
- per-run summary;
- comparison with previous relevant runs;
- estimated vs measured comparison;
- compatibility/feasibility conclusions;
- regressions/new coverage;
- cost;
- unresolved uncertainty.

Make accumulated evidence queryable for future architecture/model/runtime decisions.

## Privacy/security

Never store:
- API keys;
- passwords;
- private SSH keys;
- OAuth tokens;
- customer prompts/responses/files;
- proprietary customer content.

Lab data is development evidence, not customer telemetry.

---

# 10. VERSION-CONTROL / BRANCHING STRATEGY FOR AUTOMATED DEVELOPMENT

Design a branching protocol for the 30-step program.

The required concepts are:

```text
checkpoint/pre-automation-inference-2026-09-23
        immutable recovery point

automation/inference-program
        reviewed integration line for this program

automation/decision/<step>-<option>
        bounded branches for material alternatives

automation/task/<nn>-<slug>
        optional bounded work branches if useful
```

Do not generate branches mechanically when a simple linear safe step needs none.

Use a decision branch when:
- two credible architecture shapes exist;
- a provider integration has meaningful coupling risk;
- an external dependency may be rejected;
- a migration could invalidate accepted evidence;
- a deeper implementation may be valuable but is not obviously the right default.

Each major accepted transition should leave a recoverable commit/checkpoint.

Never force-push accepted integration history merely to make automation neat.

---

# 11. OVERNIGHT / SEQUENTIAL AUTOMATION POLICY

The next 30 steps are intended to become executable sequentially after Lead Developer review.

For every step classify:

```text
AUTO_SAFE
BOUNDED_ENGINEERING
DECISION_GATE
PHYSICAL_GATE
```

## AUTO_SAFE

May automatically continue when all acceptance checks pass.

Examples:
- implementing an already-approved contract;
- deterministic refactor within a fixed boundary;
- regression tests;
- packaging;
- evidence capture;
- documentation/evidence synchronization.

## BOUNDED_ENGINEERING

Cursor may use engineering judgement without waking Daniel, provided it does not alter accepted product/architecture semantics.

Examples:
- internal factoring;
- naming/helper choice;
- test fixture design;
- choosing a standard data structure;
- correcting an obvious local defect inside the accepted boundary.

Record the choice.

## DECISION_GATE

Automation must stop.

Examples:
- changing product promise;
- changing Block/Capability ownership;
- new provider not already selected;
- new mandatory external dependency;
- Amber/Red/unknown commercial dependency;
- unsafe migration of evidence/state;
- deleting accepted semantics;
- widening a support claim;
- reordering the roadmap materially;
- a credible competing architecture path with meaningful tradeoffs.

## PHYSICAL_GATE

May run automatically only when all pre-approved safety/budget/ownership rules are satisfied.

The existing RunPod ownership/budget rules remain in force.

A product defect discovered physically:
- capture evidence;
- terminate the owned disposable host where policy permits;
- fix locally on a new SHA;
- rerun required local gates;
- then rerun the relevant physical scenario.

Never remote-patch.

## Repair budget

Propose a bounded automatic repair policy, for example:
- up to 3 local fix/test iterations for one task;
- then STOP with typed failure/decision request.

Do not let an agent thrash indefinitely overnight.

---

# 12. THE EXACT 30-STEP PLAN — REQUIRED OUTPUT

Return **exactly 30 development steps**.

They must be genuine bounded steps, not filler and not 30 restatements of one component.

The sequence must form one coherent program from the current state through:
1. hardened native vLLM inference;
2. diversified NVIDIA physical proof with multiple model cases;
3. Ollama fallback inference;
4. Dynamo + Run:ai provider gate and, if the gate/required infrastructure is approved, bounded implementation and empirical inference proof.

If 30 is too few to finish every deep distributed-fabric feature, keep the program scoped to the smallest meaningful Dynamo/Run:ai inference vertical and explicitly defer optimization depth.

Do not steal steps from native correctness merely to reach Dynamo.

For each of the 30 steps provide:

- Step number and stable proposed task ID;
- Block / Capability / Component affected;
- plain-language purpose;
- exact problem being solved;
- why it follows from Product Vision / Architecture / Roadmap;
- inputs;
- expected outputs/contracts;
- files/modules likely involved;
- dependencies on earlier step numbers;
- local tests;
- physical test, if any;
- server class/model cases, if physical;
- evidence that must be stored;
- telemetry/events affected;
- branch/checkpoint strategy;
- autonomy classification;
- `auto_advance: yes/no`;
- stop conditions;
- estimated complexity: S/M/L;
- whether a Provider Selection Gate is required;
- what downstream failure this step prevents.

Explicitly mark which steps can run unattended overnight after approval.

---

# 13. REQUIRE A PIPELINE INVARIANT REVIEW BEFORE WRITING THE 30 STEPS

Before proposing the task list, inspect the actual current M5→M9 implementation and answer:

1. Can any ModelSelection be created outside DeployableModels?
2. Can Plan accept a model whose runtime qualification does not cover the exact recipe?
3. Can acquisition happen before cheap feasibility has enough evidence?
4. Can Serve start with stale qualification or stale Foundation environment?
5. Can hardware/environment changes reuse qualification incorrectly?
6. Can Capacity/Reservation facts be stale at Admit?
7. Can runtime readiness become mistaken for inference proof?
8. Can a provider-local model name diverge from Machi's selected model identity?
9. Can runtime/backend changes evade invalidation?
10. Can a previously qualified model remain selectable after capacity/environment changes?
11. Can a path-specific runtime become global authority accidentally?
12. Are there failures currently discovered at Serve that should be moved earlier?

For every YES:
- point to repository evidence;
- identify the owning earlier Block;
- include a corrective task in the 30-step program.

This review is mandatory.

---

# 14. MODEL-TEST DESIGN REVIEW

Design a small model qualification matrix that tells us more than repeatedly serving one tiny model.

Do not pick final models casually.

For every proposed test model report:
- source;
- immutable revision;
- license/commercial-use status;
- architecture;
- parameter/artifact size;
- dtype/quantization;
- context;
- expected runtime/backend;
- what unique compatibility boundary it exercises;
- expected feasibility on each test host;
- whether full acquisition is needed;
- whether it should be a positive DeployableModels member or an intentionally excluded negative candidate.

Do not download weights in this planning instruction.

Use product-relevant, redistributable/commercially acceptable models where possible.

---

# 15. SERVER-TEST DESIGN REVIEW

Propose a physical test matrix optimized for information gain.

At minimum:
- Ampere;
- Ada.

For an optional third server, compare candidate classes and explain what unique uncertainty it reduces.

Do not simply say “three is better than two.”

For each class define:
- required capability;
- preferred/fallback SKUs;
- minimum VRAM;
- expected Foundation;
- model cases;
- scenario;
- evidence;
- estimated run time/cost method;
- exact support claim allowed after PASS.

Never claim class-wide support from one SKU unless an explicit support-promotion rule exists.

---

# 16. DYNAMO / RUN:AI COMMERCIALIZATION AND PROVIDER RISK REVIEW

This is mandatory before planning implementation steps for that path.

Classify:
- Dynamo;
- Run:ai;
- Kubernetes/container-runtime dependencies;
- any NGC-only artifacts;
- GPU Operator / scheduler dependencies;
- backend engine dependencies.

For each:
- license/entitlement;
- redistribution implications;
- hosted-service restrictions;
- air-gap implications;
- whether it would become mandatory or optional;
- replacement boundary.

If Run:ai requires an enterprise entitlement, design the Machi seam so the direct path and Ollama path remain commercially usable without it.

Do not embed entitlement/licensing logic in ResourceManager or generic Foundation contracts.

---

# 17. REQUIRED PROGRAM DOCUMENTS IN THE PASTE-BACK

Return these sections in this order.

## A. Status

Expected:
`STATUS=PLAN_READY_FOR_LEAD_REVIEW`

No implementation status.

## B. Authority Review

Summarize Strategy → Product Vision → Architecture → Contracts → Roadmap.

List any contradictions/stale statements found.

## C. Product Principles Extracted

List the durable product/engineering principles from Section 4 and any additional ones repository history proves.

For each:
- principle;
- concrete historical failure/intervention that motivated it;
- architectural consequence;
- roadmap consequence.

## D. Program Scope

IN / OUT / DEFERRED.

## E. Recovery / Branching Plan

Include the immutable pre-automation checkpoint and automation root.

## F. Current Pipeline Invariant Audit

Answer all 12 questions from Section 13 with repository evidence.

## G. Target End-to-End Pipeline

One concise text diagram showing every gate from host facts through request inference.

## H. Native vLLM Completion Strategy

Local + physical.

## I. NVIDIA Server Matrix

2 required classes + optional third analysis.

## J. Model Matrix

Positive and negative candidates, no downloads.

## K. Empirical Lab Evidence Architecture

SQLite/index + raw artifacts + summaries + privacy.

## L. Ollama Macropath Strategy

Same Machi authority, fallback semantics, provider gate, physical proof.

## M. Dynamo + Run:ai Strategy

Provider gate, licensing, infrastructure, smallest meaningful physical inference proof.

## N. Automation State Machine

Task statuses, auto-advance, stop/repair rules.

## O. Exact 30-Step Plan

Exactly 30 rows/items with all required fields.

## P. Dependency DAG

Show the 30-step dependency chain/branches.

## Q. Overnight-Safe Subsequence

Identify the longest contiguous or dependency-safe set that could run unattended after Lead approval.

Do not execute it.

## R. Decision Gates

List only decisions Daniel/Lead must make before automation can proceed.

## S. Canonical Documentation Changes Recommended

Identify product/architecture/roadmap/strategy docs that should be changed before execution.

Do not edit them now.

## T. Definition of Program Completion

State what evidence means:
- direct native vLLM path is proven;
- model funnel prevents known incompatible candidates from load;
- diversified NVIDIA evidence exists;
- Ollama fallback produces real inference;
- bounded Dynamo/Run:ai vertical is either proven or truthfully stopped at an explicit external/provider gate;
- evidence is retained and queryable.

## U. What Should Run First After Approval

Name Step 1 only.

## V. Exact Final State

End with:

`NO_IMPLEMENTATION_PERFORMED`

`NO_SERVER_CREATED`

`AUTOMATION_NOT_STARTED`

`STOP — WAIT FOR LEAD DEVELOPER REVIEW OF THE 30-STEP INFERENCE PROGRAM.`

---

# 18. PUBLISH

Publish the complete planning result through the existing GitHub handoff:

```bash
python tools/machi_handoff.py publish-pasteback <complete-plan-file>
```

Then STOP.

Do not implement Step 1.
Do not create a Pod.
Do not alter canonical docs.
Do not download model weights.
