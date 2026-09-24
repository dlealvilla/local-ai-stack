# Ollama Chunk 3 — Architecture / Industry Solution Decision Gate

**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Chunk:** 3 of 6 — Model + Specialist Feasibility Bridge  
**Gate status:** DECISION RESEARCH ONLY — NO IMPLEMENTATION  
**Accepted starting source:** `180a4e898c5fcd46ae54a6d1c8aa8acfe84c66e6`

## Why this gate exists

The current normal deployment chain is intentionally:

```text
DeployableModels
 -> ModelSelection
 -> PlanDecision
 -> ResourceManager admission
 -> Serve
```

Normal Plan requires qualification coverage.

Chunk 3 must empirically qualify a model before it may enter DeployableModels.
Therefore a qualification probe cannot simply use the existing normal Plan as if
the model were already deployable. Doing so is circular.

The accepted Chunk-1 architecture already requires:

```text
QualificationQueue
 -> bounded qualification ResourceRequest/Reservation
 -> acquisition/load/probe
 -> QualificationEvidence
 -> DeployableModels
```

ResourceManager must remain the single global resource authority.

This is a core control-plane decision, so Cursor must not choose the contract
shape silently.

## Frozen Ollama v0.34.3 facts to verify

Inspect the exact `ollama/ollama@v0.34.3` API/source, not current-main only.

Expected facts requiring confirmation:
- `POST /api/blobs/:digest` can place content-addressed file blobs;
- `HEAD /api/blobs/:digest` can test local blob presence;
- `POST /api/create` can create a model from safetensors file-name -> SHA256
  blob mappings;
- `GET /api/tags` returns local model name, size and digest;
- `GET /api/ps` returns loaded model name, digest, size, size_vram and expiry;
- an empty `/api/generate` can load a model and `keep_alive: 0` can unload;
- there is no accepted dry-run API that proves final specialist memory fit before
  load.

Confirm exact v0.34.3 behavior and identify any mismatch.

## Decision 1 — qualification resource admission shape (CORE)

Evaluate at least these options.

### Option A — generalized purpose-aware ResourceManager claim

Evolve the Admit ontology so the same ResourceManager can admit resource claims
for different workload purposes, initially:
- DEPLOYMENT;
- QUALIFICATION.

Normal Deployment still requires Plan/DeployableModels.
Qualification uses a qualification authority/request rather than pretending to
be a normal deployment.

One common ledger/accounting/atomicity path owns all reservations.

Assess whether this can be introduced as the smallest generic seam without
prematurely designing training/indexing/future workloads.

### Option B — separate QualificationReservation contract, same ResourceManager ledger

Add a bounded qualification-specific admission entry point and reservation
contract, but make ResourceManager aggregate both deployment and qualification
holds in one ledger and one fit/accounting authority.

This minimizes change to existing deployment contracts but creates two
reservation record shapes.

### Option C — synthetic/bypass PlanDecision

Construct a special PlanDecision or bypass qualification checks solely so
ResourceManager.admit can be reused.

Treat this as presumptively disfavored because Plan means deployment after
qualification and this risks circular/false semantics. Confirm whether any
clean formulation exists; do not implement it.

### Option D — runtime/Ollama implicit admission

Let Ollama load and discover fit without a Machi reservation.

Treat as structurally misaligned unless evidence overturns the accepted
architecture.

For A/B/C/D provide:
- exact repository changes required;
- ontology/control-boundary impact;
- migration/schema impact;
- atomic accounting behavior with existing reservations;
- crash/re-entry/release semantics;
- ability to remain single-host now and grow to later workload classes;
- test burden;
- Product Vision Alignment;
- reversibility.

Recommend one, but STOP for Daniel/Lead decision.

## Decision 2 — initial Ollama model representation/acquisition path

Evaluate these implementation paths against current M6 model truth.

### Path 1 — Machi ModelArtifact -> Ollama blobs + create (expected default)

- retain Machi ModelDefinition/ModelArtifact as source/provenance truth;
- push/check file blobs by their Machi SHA256;
- create a Machi-owned Ollama model binding from those blobs;
- record the resulting Ollama model digest;
- use an immutable Machi alias/binding derived from Machi model/artifact identity;
- never use a mutable tag alone as proof.

Assess:
- safetensors compatibility at v0.34.3;
- files needed beyond weight files (config/tokenizer/etc.);
- storage duplication/conversion behavior;
- offline/air-gap fit;
- license/provenance preservation;
- whether any additional model source ontology is needed (prefer NO).

### Path 2 — Ollama library pull as source

Assess but do not automatically choose:
- simplicity;
- provenance and immutable revision implications;
- dependence on Ollama registry/library;
- offline/air-gap impact;
- relationship to current Model Warehouse;
- commercial/support implications.

Expected posture: useful future optional provider, not initial source authority,
unless repo/API evidence proves Path 1 infeasible.

### Path 3 — local path / direct import shortcut

Assess any v0.34.3 path-based import behavior, but reject if it weakens
content-addressed identity, owned storage, portability, or daemon/client
separation.

For this decision, Cursor may return `NO_SOLUTION_DECISION_REQUIRED` if one
path is clearly the bounded Product-Vision-aligned fit and alternatives are
future providers rather than competing architecture.

## Binding / identity design to propose

Without implementing, specify a bounded contract for something like:

```text
OllamaModelBinding
- binding_id
- machi_model_id
- artifact_id
- immutable_revision
- foundation_generation_id
- ollama_name / Machi-owned alias
- expected_ollama_digest
- representation_state
- source_file_digests or manifest identity
- created_at
```

Requirements:
- binding identity must not depend on mutable endpoint/port;
- expected digest is immutable once bound;
- mutable tag/name is location/reference, not proof;
- binding cannot mutate while any qualification/serving workload cites it;
- `/api/tags` proves local representation digest;
- later `/api/ps` proves resident digest;
- later inference proof verifies digest immediately before and after request.

Do not add these contracts yet; propose exact minimal fields and ownership.

## Specialist feasibility evidence proposal

Define what can be known before load:
- Machi policy/coarse compatibility;
- Machi source sizes and static estimates;
- Ollama representation existence/digest/size after import;
- `/api/show` details where useful.

Define what requires empirical qualification:
- actual successful load;
- loaded digest match;
- `size_vram` from `/api/ps` (runtime-reported loaded VRAM, not external peak);
- real token proof;
- load duration / generation metrics;
- externally observed peak VRAM/RAM only if a later observer supplies it.

Do not mislabel `size_vram` as peak VRAM.

## Storage/reservation sizing question

Ollama safetensors import may create its own representation/store bytes in
addition to the Machi warehouse artifact.

Research the exact v0.34.3 mechanics sufficiently to state:
- what bytes can be known before import;
- what output bytes remain unknown until import;
- whether blob reuse avoids duplicate input bytes;
- how a qualification reservation can conservatively authorize storage without
  inventing an arbitrary multiplier.

If exact sizing is unresolved, say so and propose a fail-closed/bounded empirical
strategy. Do not invent a 2x/3x multiplier without evidence.

## Product Vision Alignment

For every viable option assess:
- self-hosted/customer controlled;
- local-content/privacy;
- offline/air-gap;
- replaceability;
- provider-neutral core;
- Machi authority vs Ollama mechanics;
- truthful evidence/fail-closed behavior;
- ownership/reproducibility;
- admin simplicity;
- commercial/licensing;
- future Company Brain and multi-workload evolution.

Classify each: `ALIGNED`, `ALIGNED_WITH_CONDITIONS`, or `MISALIGNED`.

## Output only — no source implementation

Cursor may update only the handoff/analysis evidence needed to publish the
decision package. Do not modify product source, contracts, tests, docs, or the
integration branch.

Mandatory paste-back:

==================== BEGIN PASTE BACK — OLLAMA CHUNK 3 DECISION GATE ====================

A. STATUS  
B. Repository truth summary  
C. Exact v0.34.3 API/source facts  
D. Decision 1 options A/B/C/D comparison  
E. Decision 1 Product Vision Alignment  
F. Decision 1 recommendation  
G. Decision 1 irreversible/hard-to-change implications  
H. Decision 2 paths comparison  
I. Decision 2 Product Vision Alignment  
J. Decision 2 recommendation / whether decision required  
K. Proposed OllamaModelBinding minimal contract  
L. Specialist feasibility evidence split: pre-load vs empirical  
M. Storage/import sizing truth and unresolveds  
N. Proposed Chunk-3 implementation slices after decision  
O. Exact questions requiring Daniel/Lead decision  
P. Final status

End exactly:
`STOP — OLLAMA CHUNK 3 DECISION GATE COMPLETE. WAIT FOR LEAD DECISION.`

==================== END PASTE BACK — OLLAMA CHUNK 3 DECISION GATE ====================

No code. No model bytes. No physical server. No inference.
