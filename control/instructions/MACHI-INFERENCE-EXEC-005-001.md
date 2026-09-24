# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: MACHI-INFERENCE-EXEC-005-001
Mode: EXECUTE FIVE BOUNDED STEPS SEQUENTIALLY
Automation: ALLOWED ONLY WITHIN THE RULES BELOW
Physical servers: ALLOWED ONLY IN STEPS 3 AND 4, under existing RunPod ownership/budget rules
Recovery branch: checkpoint/pre-automation-inference-2026-09-23
Automation integration branch: automation/inference-program

# 0. OBJECTIVE

Execute the next five bounded steps toward a production-quality native-vLLM inference spine.

This is not "make five commits". The five steps are outcome gates:

1. Harden the M5 to M9 narrowing funnel.
2. Build durable empirical-lab evidence storage before more physical testing.
3. Prove N1 Ampere with multiple positive model cases plus an upstream-rejected negative case.
4. Prove N2 Ada with multiple model cases and cross-hardware comparison.
5. Close the native-vLLM production-inference baseline and write the evidence-backed report.

Do not begin the Ollama macropath in this instruction. Ollama is expected immediately after Lead review of Step 5.

The governing product invariant is:

Host truth
  -> capacity/prerequisite truth
  -> Foundation feasibility
  -> selected/provisioned/verified runtime
  -> model catalog
  -> cheap policy/license/format filters
  -> structural runtime compatibility
  -> model requirement estimation
  -> current capacity feasibility
  -> empirical qualification where needed
  -> DeployableModels
  -> ModelSelection
  -> ModelArtifact
  -> CURRENT DeploymentConfiguration
  -> ResourceRequest
  -> ResourceReservation
  -> Serve
  -> ReadinessProof
  -> real request InferenceProof

A known-incompatible model should normally never reach ordinary Serve. If Serve exposes a failure that earlier facts could have prevented, fix the earlier owning Block rather than teaching Serve to tolerate the bad state.

# 1. AUTHORITIES

Before work, sync and inspect:
- docs/STRATEGY.md
- docs/PRODUCT_VISION.md
- docs/machi/ARCHITECTURE.md
- docs/machi/CONTRACTS.md
- docs/machi/ROADMAP.md
- docs/machi/TELEMETRY.md
- accepted evidence/debt
- current repository truth

Higher-level product meaning wins over local implementation convenience.

# 2. VERSION-CONTROL SAFETY

Verify the immutable recovery branch and automation root exist:
- checkpoint/pre-automation-inference-2026-09-23
- automation/inference-program

Never force-move, rebase away, delete, or repurpose the recovery branch.

Work on automation/inference-program, using bounded task branches only where they materially improve isolation.

For a material decision with two credible paths, fork bounded decision branches from the nearest accepted checkpoint. Do not silently choose the higher-coupling option because it is quicker.

Never rewrite accepted evidence.

# 3. GLOBAL FAILURE POLICY

Classify failures before acting.

A. UPSTREAM PRODUCT/FUNNEL DEFECT
Example: incompatible model reaches Serve, stale qualification survives, wrong served-model identity is accepted, or OOM is discovered only at Serve when capacity evidence should have excluded the model.

Action:
- identify the earliest truthful owning Block;
- capture evidence;
- fix locally in that owning Block;
- new SHA;
- rerun all affected local gates;
- rebuild exact artifact;
- rerun the affected scenario.

Do NOT patch Serve to accept an impossible state.
Do NOT patch source on the physical host.

B. MODEL-SPECIFIC FAILURE
The exact model/config fails while the host/Foundation remains healthy.

Action:
- persist exact model/environment failure;
- exclude that model from DeployableModels for that environment when warranted;
- advance to the next approved qualification candidate if campaign policy permits.

Do NOT mark the Foundation failed.
Do NOT repeatedly retry the same model without a new evidence-bearing change.

C. ENVIRONMENT OR PROVIDER FAILURE
Examples: no stock, provider outage, broken image, host driver incompatible, network/service fault.

Action:
- persist provider/environment evidence;
- use only an already-approved fallback in the same hardware class;
- otherwise mark ENVIRONMENT_BLOCKED.

Do NOT weaken product policy to make the provider pass.
Do NOT burn through model candidates when the runtime environment itself is invalid.

D. ARCHITECTURE / PRODUCT / COMMERCIAL DECISION
Examples:
- changes Product Vision semantics;
- moves Block ownership;
- introduces a mandatory new provider/dependency;
- weakens privacy/safety/ownership;
- widens a support claim;
- embeds vendor logic in Core;
- requires an Amber/Red/unknown commercial dependency;
- materially reorders the roadmap.

Action:
- publish STATUS=DECISION_REQUIRED;
- preserve the branch and evidence;
- STOP the whole five-step program.

Do NOT make this decision autonomously.

E. UNKNOWN
Unknown is never optimistic PASS. Preserve UNRESOLVED/BLOCKED/refusal.

Repair budget:
- maximum 3 local product-fix iterations for the same root defect per step;
- after that STOP with typed failure and evidence.
- physical provisioning retries remain governed by existing RunPod limits.

# 4. LIVE STEP STATUS

At the start and end of every step, make progress externally visible through development-only handoff state.

Persist at minimum:
- instruction ID;
- step ID/name;
- RUNNING/PASS/BLOCKED/FAIL/DECISION_REQUIRED;
- branch;
- start/end SHA;
- attempt number;
- latest gate;
- physical run IDs if any;
- lab run IDs if any.

Do not place secrets in control state.

If the current helper cannot represent step status cleanly, add the smallest development-only extension in Step 1. Do not make this product runtime state.

# STEP 1 — HARDEN THE M5→M9 NARROWING FUNNEL

Task ID: MACHI-INF-01-FUNNEL-INVARIANTS
Server: NO
Autonomy: BOUNDED_ENGINEERING
Auto-advance: YES only on PASS

Inspect actual code and test these invariants:

1. ModelSelection cannot be created outside current DeployableModels.
2. MANUAL selection cannot bypass DeployableModels.
3. Plan cannot accept a model unless qualification covers the exact execution environment/runtime recipe.
4. Foundation-generation change invalidates qualification coverage.
5. Material GPU-environment change invalidates qualification coverage.
6. Model revision/dtype/quantization/TP change cannot reuse the wrong qualification.
7. Capacity/environment changes invalidate stale model availability/Plan as required.
8. Full acquisition does not happen before cheaper policy/format/structural/resource gates have had the chance to reject.
9. Plan becomes STALE when any load-bearing upstream identity changes.
10. Admit uses a current capacity snapshot and matching request/configuration.
11. Serve requires exact CURRENT Plan + matching reservation + exact artifact + exact runtime qualification coverage.
12. Readiness cannot satisfy request InferenceProof.
13. Runtime-served model identity must match Machi selection/artifact identity.
14. Engine/backend/runtime changes cannot evade invalidation.
15. The historical tiny-head-dimension/kernel incompatibility is rejected before ordinary deployment Serve.
16. Negative candidates can be rejected without full weight acquisition when metadata is sufficient.

For every unsafe YES:
- fix the earliest truthful owning domain;
- add typed refusal/invalidation;
- add regression tests.

Do not wholesale redesign accepted Blocks.

Failure rule:
- if enforcing an invariant requires changing canonical Block ownership: DECISION_REQUIRED and STOP.
- local product defects: fix up to 3 iterations.
- pre-existing unrelated failures may be recorded only with exact proof of unrelated scope; do not call a required gate green if it is not.

PASS output:
- Step-1 implementation/evidence SHA;
- tests;
- exact unsafe paths corrected;
- exact downstream failures prevented.

# STEP 2 — BUILD THE EMPIRICAL LAB EVIDENCE SPINE

Task ID: MACHI-INF-02-EMPIRICAL-LAB
Server: NO
Autonomy: BOUNDED_ENGINEERING
Auto-advance: YES only on PASS

Purpose: every subsequent server/model run must leave durable, structured, queryable evidence.

This is development/lab infrastructure, separate from Machi product state and customer telemetry.

Default bounded design:
- versioned SQLite database with explicit migrations;
- immutable/content-addressed raw artifact storage;
- generated per-run/campaign summaries.

Store structured records for:
- program/task/instruction/campaign/run/attempt IDs;
- branch, implementation SHA, evidence SHA, build, wheel/image digest;
- provider/region/rate/cost/duration;
- host/GPU vendor/model/count/VRAM/capability/topology;
- CPU/RAM/storage/filesystem;
- OS/kernel/driver/CUDA/runtime;
- Foundation/environment fingerprint/generation;
- model source/revision/digest/license/architecture/dtype/quantization/context;
- funnel decision/exclusion stage;
- requirement estimates;
- Capacity/Plan/Reservation/ServingInstance/Proof IDs;
- runtime configuration;
- expected vs actual;
- typed failure;
- readiness/inference performance;
- peak RAM/VRAM when measurable;
- TTFT/tokens-sec/request latency when measurable;
- stop/restart evidence;
- code-fix lineage;
- raw artifact references.

Raw artifacts may include:
- provider inventory snapshots;
- sanitized stdout/stderr;
- machine-readable probe outputs;
- manifests;
- runtime logs;
- structured command specs;
- benchmark/result JSON;
- sanitized traces.

Never store:
- API keys/passwords;
- private SSH keys;
- OAuth tokens;
- customer prompts/responses/files;
- proprietary customer content.

Prefer fixture IDs/hashes to prompt text.

Provide reusable analysis for:
- hardware/model/environment outcomes;
- estimated vs measured resources;
- failure taxonomy;
- performance;
- regressions across SHAs;
- campaign cost.

Failure policy:
- if SQLite is only hypothetically insufficient at future scale, KEEP SQLite.
- prefer stdlib sqlite3/existing dependencies.
- if a material new dependency is unavoidable, classify it; ambiguous/Amber/Red => DECISION_REQUIRED.
- never store this DB as Machi product operational state.

PASS:
- schema/version frozen;
- synthetic local scenario writes/reads/queries correctly;
- raw artifact integrity verified.

# STEP 3 — N1 AMPERE MULTI-MODEL PHYSICAL QUALIFICATION

Task ID: MACHI-INF-03-N1-AMPERE
Server: YES
Autonomy: PHYSICAL_GATE
Preconditions: Steps 1 and 2 PASS

Existing RunPod rules remain authoritative:
- only positively owned disposable Machi Pods;
- one Pod at a time;
- NVIDIA <= $1.50/hour;
- existing session/day/balance floors;
- no network volumes;
- max Pod life 90 minutes;
- max 3 provisioning retries;
- evidence before teardown;
- never remote-patch source.

Host:
N1 = Ampere cc-8.6 with 48 GiB continuity envelope.
Preference:
1. A40
2. RTX A6000

If A40 absent and A6000 eligible, use A6000.
If neither available, record N1_ENVIRONMENT_BLOCKED. Do not invent another SKU. Step 4 may still proceed because Ada is an independent class, but Step 5 cannot claim diversified closure.

Before host creation, select a high-information model matrix using metadata only:
1. positive small baseline;
2. positive representative realistic model comfortably feasible;
3. positive diversity model exercising a different architecture and/or quantization/dtype path supported by the current Foundation;
4. negative candidate expected to be excluded upstream before ordinary acquisition/load.

At least one positive model must also be used on N2 for cross-hardware comparison.

For every candidate capture immutable revision, license/commercial status, architecture/config, estimated artifact/requirements, expected gate, and why it is included.

Funnel each candidate through:
catalog
-> policy/license/format
-> structural compatibility
-> requirement estimate
-> current capacity
-> qualification queue if required
-> empirical qualification
-> DeployableModels.

Negative candidate:
- exclude at earliest truthful gate;
- do NOT ordinary-load it merely to prove failure.

Positive candidate physical proof:
- Foundation VERIFIED;
- empirical qualification with real generated token, not health alone;
- DeployableModels membership;
- selection;
- artifact;
- CURRENT Plan;
- matching reservation;
- Serve;
- readiness;
- real bounded request inference;
- exact served identity;
- stop;
- prove lifecycle/resource release behavior;
- restart under correct reservation semantics;
- re-infer;
- clean stop/release.

Persist all evidence/metrics in the Step-2 lab store.

Model-specific failure:
- record and exclude exact model/environment;
- advance candidate if policy allows;
- do not mutate runtime merely to rescue it.

Product defect:
- capture evidence, tear down owned host, fix locally, new SHA, gates, new wheel, rerun; max 3 same-root iterations.

Environment/provider failure:
- approved same-class fallback only; otherwise N1_ENVIRONMENT_BLOCKED; do not burn model queue.

N1 PASS requires:
- at least 2 positive model cases reach real request inference;
- 1 negative candidate excluded before ordinary Serve/load;
- stop/restart/re-infer proven on at least one positive;
- exact evidence retained.

If licensing/availability makes the "2 positive" criterion genuinely impossible, STOP for Lead review rather than silently weakening it.

Allowed transition:
- PASS -> Step 4
- ENVIRONMENT_BLOCKED -> Step 4 allowed, diversification incomplete
- PRODUCT FAIL after repair budget -> STOP
- DECISION_REQUIRED -> STOP

# STEP 4 — N2 ADA MULTI-MODEL PHYSICAL QUALIFICATION

Task ID: MACHI-INF-04-N2-ADA
Server: YES
Autonomy: PHYSICAL_GATE

Host:
N2 = Ada cc-8.9.
Preference:
1. L40S
2. L4
3. RTX 4090

Prefer L40S to keep 48 GiB and isolate architecture as the main changed variable.
If 24 GiB fallback is used, record exact 24 GiB envelope and never claim 48 GiB Ada coverage.
If none available: N2_ENVIRONMENT_BLOCKED; Step 5 may write a partial report only.

Model matrix:
- reuse at least one unchanged N1 positive for cross-hardware comparison;
- add at least one Ada-informative supported case where useful;
- keep a negative upstream-exclusion case only if it adds information not already proven.

No Cartesian product.

Physical proof is the same end-to-end chain as N1.

Compare:
- qualification;
- startup/readiness;
- TTFT;
- throughput;
- request latency;
- peak VRAM/RAM;
- reservation vs observed;
- cost/time;
- backend/kernel differences;
- stop/restart.

Failure rules:
- model passes N1 but fails N2: record exact environment failure; do not generalize to model-wide failure.
- model fails because a 24 GiB fallback cannot fit: Capacity/Model feasibility should reject before load. If Serve discovers OOM, treat as product funnel defect and fix upstream.
- product/environment/decision failures follow global policy.

Allowed transition:
- PASS -> Step 5
- ENVIRONMENT_BLOCKED -> Step 5 partial report
- PRODUCT FAIL after repair budget -> STOP
- DECISION_REQUIRED -> STOP

# STEP 5 — NATIVE vLLM PRODUCTION-INFERENCE CLOSURE + REPORT

Task ID: MACHI-INF-05-NATIVE-VLLM-CLOSE
Server: normally NO; one final rerun may be used only if required to close already-defined missing evidence and existing physical policy permits
Autonomy: BOUNDED_ENGINEERING, PHYSICAL_GATE only for that bounded rerun
Auto-advance: NO. STOP FOR LEAD REVIEW.

Decide from evidence whether the direct managed native-vLLM path is actually closed.

Required end-to-end spine:
Install
-> Discover
-> PrerequisiteReadiness
-> Steward
-> Capacity
-> Foundation
-> Model funnel
-> DeployableModels
-> ModelSelection
-> ModelArtifact
-> Plan CURRENT
-> Admit
-> Serve
-> ReadinessProof
-> request InferenceProof
-> stop/restart/re-infer
-> release.

Model-safety closure:
- known incompatible candidate did not ordinary-load;
- no selection outside DeployableModels;
- exact environment qualification coverage;
- stale upstream state invalidates downstream authorization.

Physical diversity:
- report exact N1 SKU PASS/BLOCKED;
- report exact N2 SKU PASS/BLOCKED;
- never promote one SKU automatically to whole-class or vendor-wide support.

Model diversity:
For every exact host/model pair report:
- excluded/qualified/deployable/served;
- why;
- metrics/resources;
- failure code;
- exact environment fingerprint.

Witness:
If DeploymentWitness remains incomplete in a way that prevents the architecture's own M9 completion definition, implement only the smallest bounded Witness completion needed to compose the journey from stored contracts/events without live re-resolution.
If that becomes a large new architecture project => DECISION_REQUIRED, not hidden debt.

Produce:
1. Native-vLLM inference qualification report.
2. N1 vs N2 comparative empirical report.
3. Model funnel/exclusion/qualification report.
4. Failure/fix lineage report.
5. Lab DB schema/version + raw artifact index + sample queries.
6. Exact support claims allowed.
7. Known gaps/debt.
8. Next-provider handoff for OllamaExecutionMacropath Provider Selection Gate.

Completion status must be one of:

NATIVE_VLLM_PRODUCTION_INFERENCE_PASS
Only if:
- funnel invariants pass;
- evidence is durable/queryable;
- at least one exact N1 host PASS and one exact N2 host PASS;
- multiple positive model cases proven across the program;
- negative case excluded upstream;
- real request inference proven;
- stop/restart/re-infer proven;
- required M9/Witness acceptance satisfied.

NATIVE_VLLM_PARTIAL_PHYSICAL_PASS
Product behavior correct but one required hardware class externally blocked. Do not call diversified program closed.

NATIVE_VLLM_FAIL
Unresolved product defect.

DECISION_REQUIRED
Genuine architecture/product/provider/commercial boundary.

Do not weaken acceptance criteria to manufacture PASS.
Do not begin Ollama implementation.

# 5-STEP DEPENDENCY

Step 1 -> Step 2 -> Step 3 -> Step 4 -> Step 5 -> STOP

Exceptions:
- Step 3 ENVIRONMENT_BLOCKED may continue to Step 4.
- Step 4 ENVIRONMENT_BLOCKED may continue to Step 5 for partial reporting.
- PRODUCT FAIL after repair budget or DECISION_REQUIRED stops the entire program.

# REQUIRED CHECKPOINT AFTER EVERY STEP

Persist/publish:
STEP_ID
STATUS
BRANCH
START_SHA
END_SHA
BUILD
WHEEL_SHA256
LOCAL_GATES
PHYSICAL_RUN_IDS
LAB_DB_RUN_IDS
FIX_ITERATIONS
DECISIONS_MADE
DEBT_ADDED
NEXT_TRANSITION

Do not wait until Step 5 to preserve intermediate truth.

# FINAL PASTE-BACK

Publish one complete result using the existing GitHub handoff helper.

It must include:
- program status;
- recovery/checkpoint integrity;
- each step result;
- all implementation/evidence SHAs;
- wheel/image hashes;
- physical server identities/classes/lifecycle;
- complete model matrix and immutable revisions;
- DeployableModels and exclusion evidence;
- empirical DB schema/version/path;
- raw artifact index;
- performance/resource/cost comparison;
- failure/fix lineage;
- support claims allowed;
- open debt/external blocks;
- canonical docs now stale;
- next program: Ollama Provider Selection Gate;
- exact final state.

End with either:

STOP — FIVE-STEP NATIVE vLLM PROGRAM COMPLETE. WAIT FOR LEAD REVIEW.

or

STOP — FIVE-STEP PROGRAM HALTED AT <STEP_ID>: <TYPED_REASON>. WAIT FOR LEAD REVIEW.

Do not start Ollama automatically.