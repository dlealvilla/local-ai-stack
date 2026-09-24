# Ollama Chunk 3 — Lead Review of Dual Qualifier Local Run

**Reviewed HEAD:** `da54773ab34b8d4c159fd9427519577319b25821`  
**Assigned local implementation:** PARTIAL PASS  
**Physical qualification:** BLOCKED pending bounded correction  
**Architecture direction:** ACCEPTED

## Accepted

- native/vLLM and Ollama model catalogs remain separate;
- Ollama candidate identity is digest-based, tag is not immutable proof;
- Machi shadow cannot veto Ollama;
- no `refine_vllm` or Ollama private scheduler logic is copied;
- Ollama uses a companion provider qualification contract rather than fake
  ModelArtifact identity;
- native Plan/Admit/Serve regression suite remains green;
- qualification probe holds share the existing ResourceManager reservation log;
- normalized comparison analytics distinguishes estimated vs runtime-reported
  VRAM semantics;
- full local/package gates passed.

## Blocking corrections before physical qualification

### 1. The fake /api/show contract contains a digest v0.34.3 does not expose

Exact Ollama v0.34.3 `api.ShowResponse` has no digest field. The immutable
digest is exposed by the local model list (`GET /api/tags`) and running-model
list (`GET /api/ps`).

Current `ShownModel.digest` and the digest-mismatch test at `/api/show` model
a provider API that does not exist.

Required:
- candidate is minted from `/api/tags` name + digest;
- `/api/show` supplies metadata/capabilities only;
- immediately before qualification, re-resolve the display name through
  `/api/tags` and require it still maps to the candidate digest;
- tag drift is a typed identity refusal.

### 2. Qualification identity proof order must be load -> ps -> token -> ps

Current flow is effectively:
`show -> generate token -> /api/ps -> unload`.

Accepted Ollama identity semantics require:
```text
preload expected model
 -> /api/ps requires expected name + digest
 -> real token request
 -> /api/ps again requires expected name + digest
 -> cleanup/unload
```

Ollama publicly supports preload with an empty `/api/generate` request.
The adapter seam must represent preload separately from real token generation.

A mutable tag/reference is never sufficient proof.

### 3. Fit comparison currently mislabels non-fit failures

`ComparisonClass.classify` treats every `FAIL_MODEL` as Ollama NO_FIT.
That makes digest mismatch, missing resident identity, or missing-token proof
look like Machi false positives.

This would poison the learning dataset.

Required:
- add a distinct provider specialist fit verdict:
  `FIT | NO_FIT | UNRESOLVED`;
- provider NO_FIT is set only when Ollama's load/scheduler outcome truthfully
  indicates no-fit;
- successful preload + expected resident digest establishes provider FIT;
- identity failure, token failure, host failure, and cleanup failure do not
  become a fit verdict unless the provider explicitly supplied one;
- agreement/false-positive/false-negative classification compares
  Machi shadow fit to provider specialist fit, not to overall QualificationOutcome.

Overall qualification outcome remains separate because a model can FIT but fail
identity/token/cleanup proof.

### 4. Probe reservation must authorize the actual bounded qualification envelope

Current case accepts caller-supplied
`accelerator_memory_bytes` / `host_memory_bytes`. Tests demonstrate a probe
can reserve 100 bytes while the fake provider reports 800 bytes of loaded VRAM.

That is incompatible with ResourceManager remaining the global authorization
authority.

Ollama v0.34.3 does not expose its private pre-load VRAM prediction through the
public API. For Stage-1 qualification use the conservative policy:

- qualification reserves **all currently remaining SAFE accelerator bytes on
  the selected device** after existing active holds;
- qualification reserves **all currently remaining SAFE host-memory bytes**
  after existing active holds;
- model acquisition/pull storage is not part of this qualification reservation;
  a candidate must already be local for the physical qualification increment;
- compute/validate this remaining-SAFE envelope atomically inside
  ResourceManager admission so callers cannot understate it;
- the reservation record stores the exact authorized bytes.

This is temporary, bounded qualification exclusivity, not the later serving
policy.

Refactor the duplicated internal admission mechanics so deployment and probe
entry points validate their own inputs but use one shared private
fit/create-reservation path.

### 5. Machi shadow must evaluate the same authorized/current envelope

Current shadow compares against total device SAFE bytes and ignores active
reservations.

Required:
- run shadow after the qualification hold is admitted but before provider load;
- evaluate against the exact authorized qualification reservation envelope;
- the provider result remains independent and authoritative;
- no shadow result can change admission or provider behavior.

This keeps the two evaluators on the same resource case.

### 6. Unload failure must not release the ResourceManager hold

Current orchestration releases the reservation in `finally` even when
`unload_failure` is recorded.

If Ollama remains resident, that makes reserved capacity appear free while it
may still be consumed.

Required cleanup order:
```text
qualification attempt
 -> request unload
 -> verify expected name/digest is absent from /api/ps
 -> only then ResourceManager.release
```

If unload fails or residency remains:
- do NOT release the reservation;
- return a typed host/reconciliation-required case status;
- preserve qualification/analytics evidence;
- do not promote the case as a clean qualification PASS.

Tests must prove the hold remains active after cleanup failure.

### 7. Comparative analytics must actually be durable

Current `QualificationComparison` is returned in memory but is not appended to
the local Event journal or another durable analytics store.

The learning objective requires durable local evidence.

Required:
- add an operational event such as `model.qualification.compared` whose
  versioned payload is the comparison contract;
- append through the existing Journal port / JsonlJournal adapter in the local
  orchestration seam or an injected evidence sink;
- verify JSONL round-trip in tests;
- analytics persistence failure must not be confused with provider fit truth;
  expose/report it separately;
- update `docs/machi/TELEMETRY.md` with the new local operational event and
  privacy semantics.

No prompt/response content, model bytes, filesystem paths, or user identity in
the comparison payload.

## Scope

No physical server, no model download/load, no real inference, no Chunk 4.
No model-catalog merge and no Ollama-private scheduler import.
