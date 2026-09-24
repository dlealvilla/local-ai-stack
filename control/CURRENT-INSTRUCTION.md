# CURRENT LEAD DEVELOPER INSTRUCTION

**Instruction ID:** `MACHI-OLLAMA-CHUNK-01-001`  
**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Chunk:** 1 of 6 — Tunnel Boundary + Provider/Analytics Architecture Gate  
**Mode:** ARCHITECTURE / PROVIDER SELECTION / REPOSITORY AUDIT  
**Product source implementation:** FORBIDDEN in this chunk  
**Physical server:** NO  
**Model downloads:** NO  
**Canonical doc edits:** NO — recommend changes only  
**Integration branch:** `automation/ollama-macropath`  
**Recovery checkpoint:** `checkpoint/native-vllm-partial-pass-2026-09-24`

# Objective

Design the Ollama macropath against actual repository truth before implementation.

The target is a **continuous Ollama execution tunnel** that preserves Machi's filtering/governance/admission/proof semantics while delegating Ollama's genuine integrated-platform capabilities rather than rebuilding them.

Read `control/OLLAMA-MACROPATH-PROGRAM.md` first. It defines the six-chunk destination.

Then inspect:
- docs/STRATEGY.md
- docs/PRODUCT_VISION.md
- docs/machi/ARCHITECTURE.md
- docs/machi/CONTRACTS.md
- docs/machi/ROADMAP.md
- docs/machi/TELEMETRY.md
- docs/machi/INFERENCE-PROGRAM-005.md
- empirical lab implementation/schema
- current Foundation, Model, Plan, Admit, Serve implementation
- native-vLLM analytics/evidence surfaces
- current debt

Research current Ollama official documentation and repository truth at execution time. Prefer official Ollama docs/repository/release information.

# Required architectural questions

## A. Continuous tunnel boundary

Produce a responsibility matrix for every material responsibility from Block 4 output through InferenceProof:

- SAFE Capacity
- Foundation candidate/selection
- runtime installation
- runtime environment
- service lifecycle
- model identity/provenance/license
- model representation/store
- cheap eligibility filters
- exact/specialist model fit
- runner/backend selection
- GPU/CPU placement
- acquisition/pull
- load/unload/residency
- context/concurrency
- scheduling
- DeploymentConfiguration
- ResourceRequest
- global admission
- ResourceReservation
- serving
- request inference
- served-model identity verification
- readiness/inference proof
- normalized analytics
- empirical evidence
- support claims

For each responsibility classify:
- MACHI_AUTHORITY
- OLLAMA_DELEGATED
- OLLAMA_SPECIALIST_EVIDENCE_MACHI_DECIDES
- SHARED_WITH_EXPLICIT_BOUNDARY
- NOT_APPLICABLE

Do not produce an alternating Machi→Ollama→Machi→Ollama execution design unless the actual contracts require a control-plane checkpoint. Prefer one contiguous execution tunnel wrapped by stable Machi control.

## B. What must remain Machi

Confirm whether these remain globally authoritative and identify any repository conflicts:
- host facts;
- storage/ownership;
- SAFE capacity;
- model policy/provenance;
- global resource authorization;
- deployment identity;
- proof semantics;
- evidence/support claims;
- normalized analytics schema.

If any should change, that is a DECISION_REQUIRED item, not an autonomous correction.

## C. What Ollama should be allowed to own

Verify current Ollama capabilities and recommend what to delegate:
- local runtime/service;
- model store/representation;
- exact/specialist fit evaluation where exposed;
- runner/backend;
- GPU/CPU placement;
- load/unload/residency;
- local scheduling;
- serving.

Do not duplicate mature Ollama behavior merely to keep native-vLLM implementation symmetry.

## D. Foundation/provider policy

Recommend exact first implementation coverage:
- verified-existing local Ollama;
- Machi-managed local Ollama installation;
- or both.

Evaluate:
- Linux/NVIDIA first coverage;
- package/binary provenance and version pinning;
- installation ownership;
- upgrades;
- air-gap/offline implications;
- native vs container;
- local API binding/security;
- local vs Ollama cloud separation.

Current product intent is local self-hosted Ollama only. Any cloud dependency in the happy path is DECISION_REQUIRED.

## E. Model identity and provenance

Design the exact binding between:
- Machi model identity/source/revision/provenance/license;
- Ollama model/tag/manifest/digest/blob identity.

No mutable tag alone may silently authorize a different artifact.

Determine which metadata can be checked before pull and which becomes available only after Ollama realizes the model.

Preserve the early-filter principle without demanding that Machi reimplement Ollama's exact runtime-specific fit logic.

## F. Specialist fit / DeployableModels

Design how Ollama fit evidence participates in the funnel.

Distinguish:
1. Machi coarse policy/storage/capacity eligibility;
2. Ollama specialist/exact compatibility/fit evidence;
3. Machi decision about DeployableModels membership within the globally approved resource envelope;
4. ResourceManager admission at execution time.

Answer:
- Can Ollama provide a fit verdict without ordinary model load?
- Does that require pull/acquisition first?
- What exact memory/resource data is exposed?
- How should hidden internals be represented?
- How do runtime/version/model changes invalidate the fit evidence?
- How can Machi avoid duplicate estimators where Ollama has stronger exact evidence?
- What happens for models not using Ollama's newest scheduling/measurement path?

Unknown is not PASS.

## G. Plan / Admit semantics

Audit whether current Blocks 7 and 8 can wrap the Ollama tunnel without semantic changes.

The desired result is:
- DeploymentConfiguration remains Machi;
- ResourceRequest remains Machi;
- ResourceManager remains global admission authority;
- Ollama local scheduler operates within the selected/authorized path and does not become global authority.

If supporting Ollama requires major new Plan or ResourceManager semantics, explain why and stop for Lead review rather than implementing.

## H. Serve / lifecycle semantics

Define:
- what START means for Ollama;
- whether the Ollama service and model residency are separate lifecycle layers;
- what STOP means;
- whether STOP unloads the model, stops only a serving binding, or stops the Ollama daemon;
- restart behavior;
- reservation behavior across stop/restart;
- exact served-model identity proof;
- readiness vs real request inference.

Do not let "Ollama API healthy" count as InferenceProof.

## I. Common analytics contract

Design the smallest common macropath analytics seam needed now.

Compare with existing native-vLLM empirical fields. Do not create a parallel Ollama warehouse.

For each proposed normalized metric define:
- canonical name;
- semantic definition;
- unit;
- collection layer;
- provenance/source;
- availability state;
- whether comparable across vLLM/Ollama;
- whether observed/derived/estimated;
- privacy classification.

Availability states must distinguish at least:
OBSERVED, DERIVED, ESTIMATED, HIDDEN_INTERNAL, NOT_EXPOSED, NOT_APPLICABLE, UNSUPPORTED, UNRESOLVED.

Audit current Ollama APIs for available request/model/runtime metrics and identify exact gaps.

Minimum comparison candidates:
- runtime version;
- install footprint/time;
- model acquisition bytes/time;
- model identity/digest;
- quantization/format/family;
- fit verdict;
- estimated requirement;
- macropath-specialist required memory if exposed;
- requested/reserved resources;
- observed RAM/VRAM;
- context/concurrency;
- startup/load/readiness;
- input tokens;
- output tokens;
- prompt-evaluation duration/rate;
- generation duration/rate;
- TTFT where truthfully observable;
- total request latency;
- errors;
- unload/reload/restart;
- cost/run duration.

A hidden internal detail must be recorded explicitly, not silently null.

## J. Security/privacy/licensing

Verify:
- Ollama software license;
- model-license handling;
- local API authentication/binding behavior;
- cloud model/API separation;
- update/download behavior;
- redistribution implications for managed installation;
- whether any optional component has a different commercial/license state.

Customer prompts/responses remain outside lab analytics by default.

## K. Future Dynamo test

Review the proposed Ollama boundary as a stress test for the future distributed macropath.

Identify any abstraction that would unnecessarily assume:
- one local process;
- one local model store;
- one GPU host;
- one runtime-owned scheduler;
- one backend.

Do not redesign for Dynamo now. Only prevent obviously vLLM/Ollama-specific semantics from entering generic Core.

# Required output

Publish one complete paste-back with these sections:

A. STATUS — expected `STATUS=OLLAMA_CHUNK_1_READY_FOR_LEAD_REVIEW`
B. Repository truth / starting point
C. Native-vLLM lessons being transferred
D. Ollama current-capability findings from official sources
E. Layer responsibility matrix
F. Continuous tunnel diagram
G. Exact Foundation/provider decision recommendation
H. Model identity/provenance binding
I. Specialist-fit / DeployableModels design
J. Plan/ResourceManager boundary audit
K. Serve/lifecycle design
L. Common Macropath Analytics contract
M. Metric availability matrix: native-vLLM vs Ollama
N. Empirical-lab changes required
O. Security/privacy/license findings
P. Canonical docs that are stale or contradictory
Q. Exact proposed Chunk-2 implementation scope
R. Provider Selection Gate decision(s) requiring Daniel/Lead
S. Architecture risks / credible alternatives
T. Future Dynamo compatibility check
U. Branch/checkpoint status
V. Exact final state

End with:

`NO_PRODUCT_IMPLEMENTATION_PERFORMED`
`NO_SERVER_CREATED`
`STOP — OLLAMA CHUNK 1 ARCHITECTURE GATE COMPLETE. WAIT FOR LEAD REVIEW.`

Publish via the existing GitHub handoff helper.

Do not begin Chunk 2.
