# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `MACHI-ADMIN-UI-DESIGN-001`
Status: `READ_ONLY_DESIGN_FEASIBILITY_REVIEW`
Accepted product baseline: `stage1/spine-closure` at `4cb89622a4cd3a1a37bf6ab44c4414e4287e8934`
Stage-1 status: `STAGE1_DEPLOYMENT_SPINE_IMPLEMENTATION_CLOSED_PHYSICAL_BREADTH_PENDING`

This instruction starts the first post-Stage-1 product-design loop.

Do **not** implement frontend code yet.
Do **not** create a new physical host.
Do **not** start Dynamo, Runtime Artifact Registry, remote auth, central command center, Knowledge/RAG, or another post-Stage-1 workstream.

The purpose of this run is to take a proposed simple Machi system-administrator UI, challenge it against repository truth, map every visible field/action to real backend capabilities, identify the minimum missing seams, and return an implementation-ready v0 design for Lead review.

---

# 1. PRODUCT INTENT

Machi now has a closed Stage-1 deployment spine. The next goal is to make that spine usable and understandable by a system administrator.

The UI must feel like a product, not a visualization of internal Python modules.

Ordinary operation should answer simple questions first:

- Is Machi healthy?
- What model is running?
- Which execution path is active?
- Can I test inference?
- What models do I have?
- What deployment is currently active?
- What host/capacity evidence is Machi using?
- Why is something refused, unsupported, incomplete, or contradictory?

Technical details should remain available through progressive disclosure for advanced administrators.

The product vision remains binding:

- non-technical administrators should not need CUDA/ROCm/vLLM/VRAM expertise for ordinary administration;
- core owns concepts and adapters own implementations;
- provider/runtime choices must not define the product ontology;
- privacy is local-by-default;
- unknown/unresolved/refused states remain truthful;
- explainability matters;
- self-hosted operation must not depend on vendor connectivity.

---

# 2. BINDING UI ARCHITECTURE DECISIONS

## 2.1 Local first

The first Admin UI is same-machine / loopback only.

It is not LAN Admin.
It is not remote Admin.
It is not the vendor/business command center.

A browser UI may call a local Machi control seam only if that seam remains loopback-bound and calls existing Machi services rather than duplicating their authority.

## 2.2 UI is not a control plane authority

The frontend must not own or recalculate:

- host observations;
- SAFE capacity;
- Foundation selection;
- model compatibility/qualification;
- Plan state;
- reservations;
- ServingInstance lifecycle;
- fallback policy;
- Witness verdicts.

It renders those concepts and invokes existing services.

The UI may aggregate them into a screen DTO/view model, but aggregation must not create new truth.

## 2.3 Two macropaths, one product

Native/vLLM and Ollama appear as execution paths under Machi.

The UI should not create separate “vLLM app” and “Ollama app” experiences.

Use language such as:

- Execution path: Native / vLLM
- Execution path: Ollama
- Selection mode: AUTO / VLLM / OLLAMA

Do not merge their model identity systems. Native warehouse artifacts and Ollama provider digests stay distinct.

## 2.4 Embedded inference tester is required

The first useful UI must include an embedded inference test experience for the current READY local instance.

The user should be able to enter a prompt and see the response.

This is not currently the same thing as the existing Stage-1 proof helper, which is an acceptance request path.

If an interactive request seam does not exist, identify the narrowest new local-only seam required.

Requirements:

- prompt and generated response stay local;
- prompt/response are not written into Witness;
- prompt/response are not added to operational telemetry or vendor export;
- request must target the current authorized READY ServingInstance;
- a UI must not bypass Machi lifecycle/admission semantics by talking to arbitrary runtime endpoints discovered outside Machi state;
- expose only request metadata that Machi genuinely knows/records.

## 2.5 Simple before broad

Do not build or design v0 around aspirational pages.

The first design target is exactly five core pages:

1. Overview
2. Inference
3. Models
4. Deployment
5. System

Future navigation may be mocked, but must be visually and architecturally labelled as later/deferred.

---

# 3. PROPOSED V0 MOCKUP TO REVIEW

The Lead has prepared a visual mockup with the following design intent. Treat this as a proposal to challenge, not a command to implement unsupported functions.

Use three classifications for every field/action:

- `EXISTS_NOW` — backed by current Stage-1 contracts/services/persisted evidence;
- `THIN_SEAM_REQUIRED` — product capability exists but the UI needs a narrow loopback aggregation/action/inference seam;
- `DEFERRED` — backend/product capability is not ready and must not be faked.

Return this classification for every important element below.

---

# 4. PAGE 1 — OVERVIEW

## Product question

“Can I trust this deployment, and what is running right now?”

## Proposed core content

### Deployment status

Show the current `DeploymentWitness` verdict in simple language:

- Supported
- Incomplete
- Contradictory
- Failed

Advanced drill-down may expose cited identities and reason.

### Execution path

Show:

- Native / vLLM; or
- Ollama;
- selection mode/reason where persisted and useful.

Do not infer the path from process names when Machi has a Foundation/RuntimeChoice record.

### Running model

Show the actual current model identity in human-readable form where metadata exists.

Preserve identity type:

- native warehouse artifact;
- provider digest/Ollama identity.

Do not invent cross-catalog friendly aliases.

### Instance

Show:

- lifecycle state;
- health/readiness;
- whether the matching reservation remains held/released where repository truth supports it.

### Capacity summary

Show only SAFE/evidence-backed values Machi can currently produce.

Do not add GPU utilization, CPU utilization, free-memory gauges, temperatures, or live charts unless those facts genuinely exist in the current product contracts.

### Operator actions

Candidate actions:

- Test inference;
- Stop current instance;
- Release reservation after STOPPED.

Assess whether these are genuinely callable through existing composition/services and what minimum local control seam is required.

Do not add force-release, restart-all, kill, failover-now, scale-out, or arbitrary runtime buttons.

### Start/deploy action

Do not assume this belongs in the first increment.

Assess whether a guided “Deploy” action can safely compose the existing Foundation → Model → Plan → Admit → Serve chain without creating a new orchestration authority or duplicating application logic.

Return a recommendation:

- `V0_INCLUDE_GUIDED_DEPLOY`; or
- `V0_DEFER_GUIDED_DEPLOY`.

Explain why.

---

# 5. PAGE 2 — INFERENCE

## Product question

“Can I actually use the current deployment?”

## Proposed v0 interaction

A small embedded inference console:

- current ServingInstance / running model display;
- current execution path;
- readiness state;
- prompt text area;
- Send button;
- response area;
- Clear button if purely client-side;
- request proof metadata that actually exists.

Current Serve contracts record information such as:

- request kind;
- HTTP/protocol status;
- completion token count when reported;
- structural validity;
- typed failure.

Do not display latency, prompt tokens, cost, throughput, queue depth, or model quality unless the current product actually records them.

## Critical design question

Determine the correct boundary for an interactive request.

Evaluate at least:

A. Browser → runtime endpoint directly on loopback.
B. Browser → Machi-owned loopback inference/control endpoint → current READY ServingInstance/runtime.

Assess against:

- Machi ownership of meaning;
- future runtime replaceability;
- native vs Ollama path consistency;
- lifecycle authorization;
- privacy;
- future Gateway compatibility;
- implementation simplicity.

Recommend one.

Do not implement it yet.

---

# 6. PAGE 3 — MODELS

## Product question

“What models does Machi know about, what do I have, and can they run?”

The v0 model experience must reflect current reality, not the long-term marketplace vision.

Current repository truth includes operations around:

- model metadata inspection;
- local import into the owned warehouse;
- explicit hub repository/revision acquisition;
- native ModelArtifact/warehouse identity;
- compatibility/deployability/qualification semantics;
- separate Ollama provider catalog/digest identity.

## Proposed v0 content

List known/stored/provider model entries that the current product can actually enumerate.

Suggested columns/details only when backed by current contracts:

- display/model name or source reference;
- identity type;
- stored/provider state;
- compatibility/qualification state;
- execution path/runtime compatibility where truthful;
- source/revision if current metadata records it.

Candidate actions:

- Inspect local model;
- Import local artifact;
- Acquire explicit hub repository + revision.

Do not call the v0 page a “Marketplace” if there is no real browse/search/recommendation service.

## Extended mock only

The product vision supports a future curated, Netflix-like discovery surface of models vetted for current hardware/runtime.

Do not implement that now unless repository truth already provides a real AvailableModels/catalog query suitable for a UI.

If a small real “Available Models” view exists, describe exactly what it can safely show and how it differs from the future catalog UX.

---

# 7. PAGE 4 — DEPLOYMENT

## Product question

“How did this model become a running service?”

The proposed screen visualises the chain:

Foundation
→ Model / qualification
→ Plan
→ Reservation
→ ServingInstance
→ Witness

For each layer, show simple status first and technical identifiers in an advanced drawer/details panel.

Candidate lifecycle actions:

- Test;
- Stop;
- Release after confirmed STOPPED.

Preserve:

- STOP != RELEASE;
- one ResourceManager ledger;
- no hidden failover inside Serve;
- no arbitrary reservation mutation;
- no provider residency as admission authority.

Assess whether any “Restart” control is currently valid or should remain deferred under open Serve debt.

Do not invent it.

---

# 8. PAGE 5 — SYSTEM

## Product question

“What machine does Machi think it is running on, and what can it safely use?”

Proposed v0 content:

- OS / architecture observations;
- memory observation / SAFE memory capacity where currently available;
- accelerator observation / exact identity where available;
- SAFE accelerator memory evidence;
- storage/mount/SAFE capacity evidence;
- Foundation/path status;
- current physical qualification/support note where useful.

Show business-readable labels first.

Advanced drawer may expose evidence/provider details.

Do not turn raw Discover facts into authorization; the screen must distinguish observation from SAFE capacity where needed.

A small “Execution preference” display may show AUTO/VLLM/OLLAMA only if current persisted/request semantics make that meaningful for an admin UI. Assess whether this is a persistent setting, a per-deployment intent, or something else. Do not fake a global setting.

---

# 9. FUTURE MOCK NAVIGATION — NOT V0 FUNCTIONALITY

The mockup reserves future information architecture for:

- Analytics;
- Logs / Diagnostics;
- Runtime Artifact Registry / Updates;
- Remote Admin;
- Central Command Center;
- Knowledge;
- Users / Teams / Permissions;
- Licensing / entitlements.

For each, state:

- whether any current data exists that could be shown honestly today;
- why it should or should not appear in v0 navigation;
- prerequisite backend work before it becomes a real product page.

Do not wire a page to placeholder/fake data.

---

# 10. LOCAL ADMIN VS CENTRAL COMMAND CENTER

Treat them as separate planes.

Local plane:

- owns no new domain truth;
- reads/calls the local Machi control plane;
- can work fully offline;
- can show customer-local content where appropriate because it never leaves the host.

Future business/vendor command center:

- deployment inventory;
- version/support/qualification summaries;
- health/support signals;
- permitted non-content operational metadata;
- optional/consented connectivity.

It must not own:

- customer host truth;
- ResourceManager;
- prompts/responses/files;
- local inference availability.

Do not design the command center implementation in this run beyond interface implications the local UI must avoid baking in.

---

# 11. REQUIRED REPOSITORY TRUTH REVIEW

Before proposing architecture, inspect at minimum:

- `docs/PRODUCT_VISION.md`;
- `docs/STRATEGY.md`;
- `docs/machi/ARCHITECTURE.md`;
- `docs/machi/ROADMAP.md`;
- `docs/machi/STAGE1-SPINE-CLOSURE.md`;
- `docs/machi/STAGE1-NEXT-OPTIONS.md`;
- `docs/machi/STAGE1-PHYSICAL-BACKLOG.md`;
- `docs/machi/CONTRACTS.md`;
- `docs/machi/TELEMETRY.md`;
- `docs/DEBT.md`;
- current composition root / CLI;
- Kernel Witness contracts;
- Capacity contracts;
- Foundation selection/runtime choice;
- Model contracts/services/adapters;
- Plan contracts/services;
- Admit/ResourceManager;
- Serve contracts/services/native/Ollama provider path;
- current tests that prove lifecycle and fallback semantics;
- packaging/dependency files to determine whether a frontend stack already exists.

Do not infer capabilities from old Kultrun code or untracked proposals.

---

# 12. SCREEN-TO-CONTRACT MATRIX — REQUIRED

Return a table/matrix for every v0 page with columns:

- Page
- UI element / action
- User purpose
- Current Machi source of truth
- Exact contract/service/file
- Classification: `EXISTS_NOW`, `THIN_SEAM_REQUIRED`, `DEFERRED`
- Read or mutation
- Security/privacy concern
- Notes / refusal states

This matrix is the primary acceptance artifact for the design review.

Anything that cannot be mapped must be removed from v0 or explicitly marked deferred.

---

# 13. MINIMUM LOCAL API / CONTROL SEAM

Machi currently has a CLI/composition root, but no operator HTTP control API according to the Stage-1 closure review.

Design the thinnest loopback seam needed by the v0 UI.

Do not build it.

Prefer a small Machi-owned API/view layer over duplicating domain behavior in the frontend.

Propose only endpoints/actions justified by the v0 screens.

For each proposed endpoint provide:

- method;
- path;
- read/mutation;
- request shape;
- response shape;
- exact existing service(s) called;
- possible typed refusal states;
- whether response contains customer content;
- whether it is safe only on loopback.

Candidate categories to evaluate, not mandatory paths:

- overview snapshot;
- deployment detail / Witness;
- system/capacity snapshot;
- models list/detail;
- inspect/import/acquire model;
- current instance state;
- interactive inference request;
- stop instance;
- release reservation after stop.

Do not expose generic “execute command” or “run arbitrary CLI” endpoints.

---

# 14. FRONTEND TECHNOLOGY — INDUSTRY SOLUTION SELECTION GATE

Inspect the repository first for any existing frontend/web stack or packaging assumptions.

If no frontend technology is already authoritative, present the smallest credible options for a same-machine Admin UI.

Evaluate them against:

- simplicity;
- static build / easy bundling;
- offline operation;
- dependency footprint;
- security surface;
- accessibility;
- long-term maintainability;
- ability to grow into the product vision;
- separation from the future central command center;
- ease of packaging with Machi;
- license/redistribution implications.

Do not choose a complex framework merely because it is popular.

Run the Industry Solution Selection Gate if two or more materially credible options remain.

Return:

- options;
- trade-offs;
- recommended default;
- Product Vision Alignment: ALIGNED / ALIGNED_WITH_CONDITIONS / MISALIGNED;
- what becomes difficult to change later.

No implementation in this run.

---

# 15. V0 VISUAL / INTERACTION PRINCIPLES

Use these design principles when reviewing the mockup:

- dark, calm operations UI is acceptable, but visual style is secondary to truth;
- simple status first, technical IDs second;
- green is not “good” unless Machi has a positive state to support it;
- typed refusals should be readable in plain language;
- unsupported and pending are not errors;
- advanced detail should preserve exact identifiers and provenance;
- destructive actions require clear state-dependent enablement;
- no “force” actions in v0;
- no fake charts;
- no KPI cards without a real metric source;
- no empty future pages in the runnable build.

---

# 16. V0 ACCEPTANCE DEFINITION — DESIGN ONLY

The design review should finish with an implementation-ready definition of the smallest useful v0.

The target should likely allow an operator to:

1. open Machi locally in a browser;
2. see whether the current deployment evidence is supported/incomplete/failed;
3. see the active execution path and current model/instance;
4. inspect SAFE host/capacity information;
5. send an interactive prompt to the current READY instance and see the response locally;
6. inspect known/stored model entries and qualification state;
7. perform only the model operations genuinely supported by current services;
8. inspect the Foundation → Model → Plan → Reservation → Instance → Witness chain;
9. stop the current instance safely;
10. release the reservation only after stop when permitted;
11. understand typed refusals and pending physical qualification.

If repository truth shows that one of these cannot be achieved without a substantial new product subsystem, mark it deferred and explain.

---

# 17. TEST STRATEGY PROPOSAL

Do not write tests yet.

Propose the future implementation test layers:

- frontend unit/component tests;
- local API contract tests;
- domain/service reuse tests;
- architecture tests proving UI/API do not become new authorities;
- privacy tests for prompt/response handling;
- end-to-end local browser test using deterministic/fake backends where appropriate;
- one later physical acceptance that loads a real accepted deployment and proves the Inference screen, but not in this design run.

Keep physical breadth campaigns separate.

---

# 18. MOCKUP CRITIQUE

Do not simply approve the proposal.

Explicitly identify:

- fields that are not backed by current contracts;
- actions that are too ambitious for v0;
- terminology that exposes implementation detail unnecessarily;
- missing operator-critical state;
- places where the mockup risks combining native and Ollama identities incorrectly;
- places where progressive disclosure should replace a main-screen technical field;
- security risks;
- future-command-center concerns the local UI should avoid baking in.

Recommend concrete revisions.

---

# 19. BRANCH / PROMOTION RECOMMENDATION

Stage-1 closure tip is `4cb89622a4cd3a1a37bf6ab44c4414e4287e8934`.

`machi` was still stale at the Stage-1 close.

For the future implementation, recommend the clean Git sequence:

- whether to fast-forward `machi` first;
- what branch name should carry the first frontend implementation;
- what exact predecessor SHA should be used.

Do not move refs in this design review.

---

# 20. NON-GOALS

Do not implement:

- React/Vue/Svelte/etc. code;
- local HTTP API code;
- CSS/design system;
- interactive inference seam;
- central command center;
- authentication;
- analytics;
- Knowledge/RAG;
- users/teams;
- entitlements;
- update manager;
- Runtime Artifact Registry;
- Dynamo;
- new physical campaigns;
- new model-runtime provider;
- live request-failure failover;
- multi-model scheduling depth;
- remote access.

This is a design/feasibility loop only.

---

# 21. FINAL PASTE-BACK FORMAT

Return one structured packet:

A. EXACT STATUS
B. EXECUTIVE TL;DR
C. REPOSITORY / BASELINE TRUTH
D. PRODUCT-VISION ALIGNMENT
E. V0 INFORMATION ARCHITECTURE
F. OVERVIEW PAGE REVIEW
G. INFERENCE PAGE REVIEW
H. MODELS PAGE REVIEW
I. DEPLOYMENT PAGE REVIEW
J. SYSTEM PAGE REVIEW
K. SCREEN-TO-CONTRACT MATRIX
L. INTERACTIVE INFERENCE BOUNDARY DECISION
M. MINIMUM LOOPBACK API / CONTROL SEAM
N. FRONTEND TECHNOLOGY OPTIONS
O. INDUSTRY SOLUTION SELECTION GATE RESULT
P. V0 INCLUDE / DEFER LIST
Q. MOCKUP CHANGES RECOMMENDED
R. SECURITY / PRIVACY BOUNDARY
S. TEST STRATEGY
T. FUTURE NAV / EXTENDED MOCK DEPENDENCIES
U. LOCAL ADMIN VS COMMAND CENTER SEPARATION
V. BRANCH / PROMOTION RECOMMENDATION
W. PROPOSED FIRST IMPLEMENTATION BUNDLE
X. EXACT LEAD DECISIONS STILL REQUIRED
Y. EXACT NEXT ACTION
Z. STOP

Success status:

`PASS_ADMIN_UI_V0_DESIGN_READY_FOR_LEAD_REVIEW`

If repository truth makes the proposal materially inconsistent with current architecture:

`DECISION_REQUIRED`

If required source evidence is unavailable:

`AWAITING_REPOSITORY_EVIDENCE`

---

# 22. PUBLISH / STOP

Publish the complete paste-back through the existing Machi GitHub handoff protocol.

Then STOP.

Do not start frontend implementation until Lead review.

# END INSTRUCTION
