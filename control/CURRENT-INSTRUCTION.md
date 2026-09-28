# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-DUAL-UI-V0-001`
Status: `AUTHORIZED_IMPLEMENTATION`
Accepted product baseline: `stage1/spine-closure` at `4cb89622a4cd3a1a37bf6ab44c4414e4287e8934`
Stage-1 status: `STAGE1_DEPLOYMENT_SPINE_IMPLEMENTATION_CLOSED_PHYSICAL_BREADTH_PENDING`

This instruction supersedes `MACHI-ADMIN-UI-DESIGN-001`.

The product is now **Rukan**.

This bundle authorizes the first post-Stage-1 productization implementation: two separate visual applications built over the existing deployment spine.

1. **Rukan Admin** — customer-facing, deployment-local, loopback-only v0.
2. **Rukan Command Center** — business/vendor-facing, initially local on the operator PC, using imported non-content deployment/support snapshots rather than invented live fleet connectivity.

Do not implement Dynamo, Knowledge/RAG, remote Admin, connected fleet telemetry, Runtime Artifact Registry, physical qualification campaigns, or unrelated later-stage work in this bundle.

---

# 1. PRODUCT OUTCOME

At completion, a developer/operator should be able to stand up both applications locally and see real Rukan state without driving internal Python test tools.

## Rukan Admin

A customer administrator can:

- open a local Rukan Admin web UI;
- see whether the current deployment evidence is supported/incomplete/contradictory/failed;
- see the active execution macropath;
- see the current model identity and ServingInstance state;
- see truthful host and SAFE capacity information that the current contracts expose;
- inspect the Foundation → Model → Plan → Reservation → Instance → Witness chain;
- inspect/import/acquire models only through existing model operations that are actually implemented;
- send a real local inference test request to the current authorised READY instance through a Rukan-owned loopback API/control seam;
- stop/release only where existing lifecycle semantics already permit those actions;
- receive typed refusals instead of UI-invented success.

## Rukan Command Center

The business operator can:

- open a separate local Command Center application on their PC;
- import one or more Rukan Deployment Summary / Support Snapshot files;
- see a list of imported deployments;
- open one deployment detail view;
- inspect real non-content deployment metadata derived from Rukan evidence;
- inspect safe operational/support event information included in the snapshot;
- distinguish accepted physical evidence from PHYSICAL_PENDING qualification;
- never receive customer prompt/response/document content through this export.

The Command Center v0 is not live fleet management. It is a truthful first business dashboard built around imported evidence.

---

# 2. PRODUCT RENAME — BINDING

Use **Rukan** in all new customer-facing and business-facing product UI, new post-Stage-1 docs, UI titles, web assets and new feature names.

Do **not** rename the Python package/module namespace `machi`, persisted contract kinds, ids, environment variables, state-root names, historical checkpoint paths, GitHub handoff branch, or historical evidence inside this bundle.

Reason: Stage-1 persisted evidence and schema identity already depend on those internal names. A full technical namespace migration is a separate compatibility/migration workstream.

Where useful, current technical docs may say:

> Rukan is the product name. `machi` remains the internal package/control namespace pending a dedicated migration.

Historical docs should remain historically truthful.

---

# 3. STARTING STATE / BRANCH

Before changing source:

1. sync `control/machi-handoff`;
2. confirm this instruction id;
3. inspect current refs and working tree;
4. confirm the Stage-1 closure tip remains `4cb89622a4cd3a1a37bf6ab44c4414e4287e8934` or identify an explicitly promoted equivalent;
5. inspect whether `machi` has now been fast-forwarded to the closure tip;
6. inspect repository frontend/package tooling and any prior UI code before choosing structure.

If canonical `machi` equals the closure tip, branch from it.
If `machi` is still stale, branch from the exact closure tip and report the discrepancy.

Recommended implementation branch:

`rukan/dual-ui-v0`

Do not use the control branch as product history.

---

# 4. INDUSTRY SOLUTION / FRONTEND SELECTION GATE

Inspect the repository for an existing authoritative frontend stack.

If no frontend stack is already binding, compare only the smallest credible options for two local web applications.

The Lead's current preferred default is:

- TypeScript;
- React;
- Vite;
- static build output;
- minimal CSS/design-system dependencies;
- a shared small typed Rukan UI/client package only where useful.

This preference is not permission to add a large framework stack blindly.

Evaluate alternatives on:

- simplicity;
- static/offline deployment;
- packaging with a Python product;
- no required cloud service;
- accessibility;
- maintainability;
- security surface;
- developer experience;
- suitability for a future richer Admin UI and Command Center.

If React + Vite is clearly the smallest aligned choice, state `No solution decision required` and proceed.

Do not introduce Next.js, a Node server dependency, Electron, Tauri, or another heavyweight framework unless repository truth demonstrates a concrete v0 requirement.

---

# 5. TWO PLANES — ARCHITECTURAL BOUNDARY

These are two visual products, not one application with two routes.

## Customer plane

`Rukan Admin`

Runs with the local Rukan deployment.

Authority remains local:

- Discover owns host observations;
- Capacity owns SAFE ceilings;
- Foundation owns execution-path selection;
- Model owns model identity/qualification;
- Plan owns deployment configuration;
- ResourceManager owns admission;
- Serve owns execution/lifecycle/inference proof;
- Witness projects persisted evidence.

The UI only renders and invokes those services through bounded control seams.

## Business plane

`Rukan Command Center`

Runs separately on the business operator PC for v0.

It consumes imported summaries/snapshots.

It must not:

- become an admission authority;
- become a Serve authority;
- infer live host truth from stale imported data;
- claim live online/offline state unless a future connected telemetry contract exists;
- receive prompts/responses/files;
- mutate customer deployments remotely.

The two applications may share visual primitives and typed summary models, but not authority.

---

# 6. MINIMUM LOCAL RUKAN CONTROL / READ API

The current CLI/composition root is not a browser API. Build the thinnest local API/service boundary needed by Rukan Admin.

Requirements:

- bind to loopback only by default;
- no generic shell/CLI passthrough endpoint;
- no arbitrary command execution;
- call existing domain/application services rather than reimplementing their rules;
- JSON responses should preserve typed Rukan outcomes and unresolved/refusal states;
- browser UI must not infer success from HTTP 200 alone;
- state mutations must flow through existing service boundaries;
- no browser-direct vLLM/Ollama lifecycle control as normal architecture;
- customer prompt/response content must not be written to operational journal/Witness/vendor export by this API.

Define only endpoints actually needed by v0.

A likely minimum surface includes concepts equivalent to:

- deployment/admin summary;
- Witness view;
- current Foundation/runtime choice;
- current model/instance view;
- host/capacity summary;
- model inspect/import/acquire actions where current services can safely support them;
- safe lifecycle actions already supported;
- interactive inference request for the current READY instance;
- deployment/support snapshot export.

Do not copy these endpoint names blindly. Choose a coherent minimal API from repository truth.

Add clear API versioning from the beginning, even if only `v1`.

---

# 7. EMBEDDED INFERENCE — BINDING DESIGN

Rukan Admin v0 must include an embedded inference tester.

Do **not** use LibreChat as the Admin inference UI.

Preferred architecture:

Browser
→ Rukan local loopback API
→ current authorised READY ServingInstance / serving provider abstraction
→ vLLM or Ollama

The browser must not decide which runtime to call.

The Admin inference screen is an operational test surface, not the employee chat product.

Minimum behaviour:

- one prompt input;
- one response display;
- current model identity;
- current macropath/runtime provider;
- status/proof result;
- completion token count only when current runtime/proof reports it;
- typed error/refusal;
- no conversation memory requirement;
- no file upload;
- no tools/agents;
- no RAG;
- no Markdown/plugin complexity unless already needed for plain model text.

If Serve's existing proof API cannot accept an arbitrary operator prompt cleanly, add the smallest new interactive inference seam adjacent to Serve that preserves existing authorization and instance identity.

Do not weaken the current InferenceProof privacy rule.

LibreChat/Open WebUI integration is explicitly deferred as a replaceable employee/end-user client workstream.

---

# 8. RUKAN ADMIN V0 — REQUIRED SCREENS

Keep the first UI simple and functional.

## A. Overview

Show only truth-backed fields:

- Rukan build/version;
- Witness verdict and concise reason;
- active macropath / Foundation family;
- current model identity;
- current ServingInstance state/health;
- Reservation state where available;
- SAFE capacity summary;
- typed warning/refusal/pending qualification state.

Actions only if current services support them safely.

No invented uptime %, utilisation chart, SLA, cost, savings or health score.

## B. Inference

As defined above.

## C. Models

Expose only current real operations and state.

At minimum, evaluate current support for:

- inspect local metadata;
- local import into warehouse;
- explicit hub acquire by repository/revision;
- stored artifact identity;
- provider digest identity where appropriate;
- compatibility/qualification/deployability state.

Do not call this Marketplace.

Do not add ratings, recommended/popular lists, installation counts, model quality ranks or cross-catalog equivalence.

## D. Deployment

Visualise the current chain:

Foundation
→ Model
→ Plan
→ Reservation
→ ServingInstance
→ InferenceProof/Witness

Default view should be simple.

Provide an advanced detail drawer/section for exact ids/fingerprints/evidence.

Only expose lifecycle actions supported by current services and bindings.

## E. System

Show current observed/derived facts that already exist:

- OS/architecture;
- memory evidence;
- accelerator observations;
- mount/storage evidence;
- SAFE capacity;
- runtime/Foundation readiness;
- physical qualification state/pending coverage where current records support it.

Progressive disclosure: business/simple wording first, technical evidence second.

---

# 9. RUKAN COMMAND CENTER V0 — REQUIRED DESIGN

Build a separate web application.

For this bundle it runs locally on the business operator PC and uses imported snapshots.

## A. Deployment Summary / Support Snapshot contract

First inspect whether an existing Rukan/Machi support/evidence export contract can be reused.

If not, introduce the smallest Rukan-owned, versioned, non-authoritative export model needed by the Command Center.

It must be a projection from persisted product truth, not a second truth source.

The snapshot should include only fields backed by current evidence, for example where available:

- export schema version;
- deployment/install identity;
- Rukan build identity;
- snapshot/export timestamp;
- install/deployment/first-serve timestamp only if current evidence provides a truthful semantic; otherwise omit it or use a clearly named observed timestamp;
- OS/architecture;
- accelerator summary;
- SAFE capacity summary if appropriate for support;
- selected Foundation/macropath/runtime generation identity;
- model identity and model identity kind;
- qualification/evidence scope;
- Plan / Reservation / ServingInstance identifiers or safe summaries;
- Witness verdict/reason;
- physical qualification status/pending coverage;
- bounded non-content operational event/support evidence;
- privacy classification / redaction version if useful.

Do not export absolute customer file paths if they are not already safe for support export.
Do not export prompts, responses, documents, RAG data, API keys, secrets, credentials or proprietary file names.

Make snapshot generation deterministic where practical and testable.

## B. Local Command Center store

Use a simple local persistence option appropriate to the selected frontend/backend shape.

The store only needs to support:

- import snapshot file;
- deduplicate/update by deployment identity + snapshot identity/version;
- list deployments;
- retain imported snapshot history if cheap and useful;
- open deployment detail;
- remove local imported copy.

Do not build cloud sync.

## C. Deployments screen

Columns should be limited to real imported fields, such as:

- deployment identity / display label if supplied;
- first observed/deployed timestamp with exact meaning;
- Rukan version;
- OS / accelerator summary;
- selected macropath/runtime;
- current/imported model identity;
- Witness status;
- snapshot age/time.

Do not label imported snapshot state as `Live`, `Online`, `Offline`, or `Healthy now`.

## D. Deployment detail

Show:

- deployment identity;
- Rukan version/build;
- host/stack summary;
- macropath/Foundation/runtime;
- model + qualification;
- Witness;
- capacity summary;
- physical qualification/pending coverage;
- imported operational/support evidence/log timeline;
- snapshot provenance/time.

## E. Support evidence / logs

This view is for safe operational evidence, not customer content.

Prefer structured EventRecord/support evidence where possible.

If raw runtime logs are included, classify/redact them and prove they do not leak prompt/response/customer content before export.

When uncertain, omit raw logs from v0 and expose structured operational events instead.

---

# 10. SHARED DESIGN SYSTEM

Both products should visibly belong to Rukan while remaining distinct planes.

Use a simple dark/light-neutral professional admin style with:

- strong status colours only for typed state;
- simple cards/tables;
- progressive disclosure;
- accessible contrast;
- keyboard-accessible controls;
- responsive enough for normal laptop/desktop use;
- no decorative complexity that slows implementation.

Suggested product labels:

- `Rukan Admin`
- `Rukan Command Center`

Do not create a consumer-chat aesthetic for Admin.

A small shared component/theme package is allowed if it reduces duplication without coupling authority.

---

# 11. FRAMEWORK / PROJECT STRUCTURE

Choose repository structure that keeps both apps clearly separate.

One reasonable shape, subject to repository/tooling reality:

- `ui/admin/`
- `ui/command-center/`
- `ui/shared/`

or an equivalent small workspace.

Do not create a monorepo build system solely for these two small apps unless the repository already uses one.

Static assets should be buildable reproducibly.

Document how the local Admin assets are served and how the Command Center is started locally.

No CDN dependency should be required at runtime.

---

# 12. SECURITY / PRIVACY

## Rukan Admin

- loopback only;
- browser same-machine assumption explicit;
- no CORS wildcard for arbitrary origins;
- mutations call bounded service methods;
- no generic command endpoint;
- no prompt/response operational telemetry;
- no secrets returned to browser;
- no remote admin claim.

## Rukan Command Center

- local-only v0;
- imported snapshots are untrusted input and must be schema-validated;
- no execution of imported content;
- no customer-content fields in schema;
- local deletion supported;
- no vendor network service required;
- no automatic file watching or exfiltration unless explicitly implemented and documented locally.

Add tests for malformed/unsupported snapshot versions and oversize/untrusted input where appropriate.

---

# 13. TESTING

Add meaningful tests at all applicable layers.

## Backend/API

- loopback binding/policy;
- summary endpoints reflect service truth;
- unsupported/unresolved states preserved;
- no direct runtime authority bypass;
- inference request requires current authorised READY instance;
- vLLM and Ollama provider paths are presented under one Rukan interface;
- explicit typed failure handling;
- model operations call current services;
- snapshot export excludes prohibited fields;
- snapshot import validates schema and does not execute input;
- Command Center dedup/update semantics.

## Frontend

At minimum test:

- loading/error/empty states;
- typed Witness states;
- Inference send/result/failure state;
- Models actions only enabled when supported;
- stop/release state sequencing;
- snapshot import/list/detail/remove;
- no fake live badge in Command Center;
- accessibility basics for navigation/forms/buttons.

## Regression

Run existing Stage-1 suites so the UI/API work does not weaken the deployment spine.

---

# 14. DOCUMENTATION

Update current product-facing docs to use **Rukan** for the product.

At minimum add/update:

- a short Rukan product naming note;
- Rukan Admin v0 architecture/readme;
- Rukan Command Center v0 architecture/readme;
- local run/build instructions;
- the two-plane trust model;
- inference exposure decision;
- snapshot/export privacy boundary;
- current functionality vs deferred functionality.

Do not rewrite historical evidence records to pretend they were originally called Rukan.

---

# 15. LIBRECHAT DECISION — RECORD EXPLICITLY

Record this product decision:

- LibreChat is **not** used as the embedded Rukan Admin inference UI in v0.
- Rukan Admin owns its small operational inference tester.
- The test request travels through a Rukan-owned local API/control seam and the current authorised Rukan serving instance.
- LibreChat may later be integrated as an optional replaceable employee-facing chat client through an appropriate standard endpoint/gateway.
- That future client must not own Rukan deployment/admin semantics.

Do not add LibreChat as a dependency in this bundle.

---

# 16. NON-GOALS / FORBIDDEN SHORTCUTS

Do not implement:

- fake KPIs or dashboards;
- model marketplace rankings;
- remote customer control;
- central live telemetry;
- tenant/user identity;
- licensing;
- Knowledge/RAG;
- Team Brain;
- agents;
- Dynamo;
- Runtime Artifact Registry;
- physical GPU/macOS campaigns;
- Electron/Tauri desktop packaging unless genuinely required by the chosen v0 design;
- direct browser calls that bypass Rukan lifecycle/admission semantics;
- arbitrary shell command API;
- prompt/response export to Command Center.

Do not overbuild visual polish before both products can run and show real data.

---

# 17. ACCEPTANCE — RUKAN ADMIN

Admin v0 is PASS only if:

- it launches locally;
- it visibly uses the Rukan name;
- Overview reads real deployment state;
- Witness state is rendered truthfully;
- active macropath/model/instance can be inspected;
- Inference can perform a real request through the Rukan-owned seam when a READY instance exists, and shows a typed refusal otherwise;
- Models exposes only implemented operations;
- Deployment shows the real chain;
- System shows real host/capacity state;
- stop/release ordering remains correct;
- no browser-side runtime selection bypass exists;
- no fake KPI/marketplace data exists;
- loopback-only boundary is preserved.

Physical GPU proof is not required in this bundle. Use deterministic/local integration tests and accepted Stage-1 evidence where live accelerator state is unavailable.

---

# 18. ACCEPTANCE — RUKAN COMMAND CENTER

Command Center v0 is PASS only if:

- it launches as a separate local application;
- it visibly uses the Rukan name;
- a valid exported snapshot can be imported;
- one or more imported deployments can be listed;
- deployment detail renders only supported snapshot fields;
- snapshot provenance/time is visible;
- safe operational/support evidence is visible;
- imported data is clearly not labelled live;
- malformed/unsupported snapshots fail closed;
- customer content/secrets are absent from the export schema;
- Command Center has no remote execution authority;
- local imported records can be removed.

---

# 19. FULL QUALITY GATES

Run:

- existing `tests/machi`;
- existing acceptance-lab tests applicable locally;
- new API tests;
- new snapshot tests;
- new frontend tests;
- architecture/import-boundary tests;
- Python ruff;
- Python strict mypy;
- frontend lint/typecheck/build/test for both apps;
- clean production builds of both frontends;
- Python wheel build/isolated verify if Python source/package changes;
- no unexpected network access for local UI tests.

Fix ordinary implementation defects autonomously and continue.

Return `DECISION_REQUIRED` only for a genuine product/architecture choice that conflicts with this instruction.

---

# 20. FINAL PASTE BACK

Return one complete packet with:

A. EXACT STATUS
B. EXECUTIVE TL;DR
C. STARTING / FINAL SHA
D. BRANCH / ORIGIN / WORKTREE
E. RUKAN NAMING CHANGES
F. INTERNAL `machi` NAMESPACE DEFERRED MIGRATION BOUNDARY
G. FRONTEND SOLUTION GATE / CHOSEN STACK
H. TWO-PLANE ARCHITECTURE
I. LOCAL RUKAN API / CONTROL SEAM
J. EMBEDDED INFERENCE IMPLEMENTATION
K. LIBRECHAT DECISION
L. RUKAN ADMIN — OVERVIEW
M. RUKAN ADMIN — INFERENCE
N. RUKAN ADMIN — MODELS
O. RUKAN ADMIN — DEPLOYMENT
P. RUKAN ADMIN — SYSTEM
Q. DEPLOYMENT SUMMARY / SUPPORT SNAPSHOT CONTRACT
R. SNAPSHOT PRIVACY / REDACTION
S. COMMAND CENTER LOCAL STORE
T. COMMAND CENTER — DEPLOYMENTS
U. COMMAND CENTER — DEPLOYMENT DETAIL
V. COMMAND CENTER — SUPPORT EVIDENCE / LOGS
W. SECURITY REVIEW
X. TESTS / QA
Y. FRONTEND BUILDS / ARTIFACTS
Z. PYTHON BUILD / VERIFY IF CHANGED
AA. CURRENT FUNCTIONALITY VS DEFERRED MOCKS
AB. STAGE-1 REGRESSION
AC. OPEN DEBT / RISKS
AD. EXACT NEXT RECOMMENDED UI ITERATION
AE. GIT STATE
AF. STOP

On full success use exact status:

`RUKAN_DUAL_UI_V0_LOCAL_PASS`

If one application passes but the other does not, do not report full success. State the exact partial failure.

---

# 21. STOP

After publishing the complete paste-back through the GitHub handoff protocol:

STOP.

Do not start a connected Command Center, remote Admin, Runtime Artifact Registry, Dynamo, Knowledge, identity, licensing, or physical qualification campaign.

Wait for Lead review and the next UI iteration.
