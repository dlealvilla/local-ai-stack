# Ollama Chunk 3 — Dual Qualifier / Comparative Analytics Decision

**Status:** ACCEPTED PRODUCT / ARCHITECTURE DIRECTION  
**Date:** 2026-09-24  
**Applies to:** Chunk 3 and later qualification analytics

## 1. Model catalogs remain separate by macropath

Native/vLLM macropath:
- Machi model catalog / Model Warehouse is authoritative.

Ollama macropath:
- Ollama local model catalog/store is authoritative.
- `/api/tags`, `/api/show`, `/api/pull`, model digest and Ollama
  representation semantics remain provider-owned.

A shared UI may normalize views, but must not imply one common underlying model
warehouse or force Machi artifacts into Ollama.

## 2. Both qualification paths must run

For an Ollama candidate, two evaluators execute over the same qualification
case:

### Ollama authoritative specialist evaluator
Ollama decides technical fit for the Ollama macropath using its own scheduler,
memory prediction, placement/offload, load, eviction and OOM behavior.

Its result is authoritative for whether the Ollama macropath proceeds.

### Machi shadow evaluator
Machi also evaluates the candidate using Machi-owned generic/coarse capacity and
qualification logic that can truthfully consume normalized Ollama metadata.

The Machi result is **shadow-only** for the Ollama macropath:
- it must not veto an Ollama PASS;
- it must not turn an Ollama FAIL into PASS;
- it must not cause a second model load;
- it must not duplicate or reimplement Ollama private scheduler algorithms;
- it must not mutate Ollama placement/scheduling;
- it must not consume a second independent resource reservation.

The purpose is learning, comparison and future improvement of Machi's generic
qualifier, not control of the current Ollama path.

## 3. Authority rule

```text
Native/vLLM macropath:
Machi/native qualification result -> authoritative

Ollama macropath:
Ollama specialist result -> authoritative
Machi result             -> shadow/analytics only
```

The product-level ResourceManager remains the global authorization authority
for the qualification attempt. Provider fit logic does not authorize physical
resource use by itself.

## 4. What "run Machi's version" means in Ollama

Do not launch vLLM or convert the Ollama model into a Machi warehouse artifact
just to obtain the shadow result.

Instead:
- normalize only provider facts Ollama publicly exposes and whose meaning is
  understood (digest, size, format, family, quantization, context-related model
  metadata/capabilities where available);
- combine them with the same Machi CapacityEnvelope/current reservations and
  qualification settings;
- run the reusable Machi coarse/deep estimate/evaluation logic;
- provider-specific vLLM refiners such as `refine_vllm` are not applicable to
  Ollama shadow evaluation;
- unknown inputs remain UNRESOLVED, never guessed.

If a generic Machi estimator currently requires fields Ollama cannot truthfully
supply, record the shadow result as partial/unresolved rather than inventing
values.

## 5. Qualification execution

One authorized qualification case should conceptually be:

```text
Ollama candidate from Ollama catalog
        |
        +--> normalize public model facts
        |        |
        |        +--> Machi shadow estimate/classification
        |
        +--> Machi qualification probe Plan / ResourceManager reservation
                 |
                 +--> Ollama load request
                         |
                         +--> Ollama scheduler/fit/placement (AUTHORITATIVE)
                         |
                         +--> /api/ps digest + size_vram
                         |
                         +--> real small inference
                         |
                         +--> unload
                 |
                 +--> release reservation
        |
        +--> durable authoritative QualificationEvidence
        |
        +--> durable shadow evidence
        |
        +--> comparative analytics record
```

The shadow calculation should occur before the real load where possible so it
cannot be contaminated by knowing the answer.

## 6. Comparative analytics

Create a first-class local operational comparison record, not an unstructured
log.

Minimum identity/dimensions:
- comparison_id;
- macropath/runtime = ollama;
- Ollama version + Foundation generation;
- Ollama model name and immutable digest;
- Machi normalized candidate identity;
- capacity evidence id;
- hardware class + execution environment fingerprint;
- context/concurrency;
- Machi qualification/estimator policy version;
- observed_at.

Machi shadow fields:
- predicted/estimated fit outcome: FIT / NO_FIT / UNRESOLVED;
- estimated total required accelerator bytes where resolved;
- estimated host-memory bytes where resolved;
- estimated incremental storage where resolved;
- exclusion/failure reason where applicable;
- availability/provenance per figure.

Ollama authoritative fields:
- load success/failure;
- provider failure class;
- provider-reported loaded model size;
- `size_vram` with source clearly labeled `ollama.api.ps`;
- selected/observed digest;
- load duration where reported;
- real-token success;
- input/output token counts where exposed;
- generation duration / tokens-per-second where derivable;
- unload result.

Comparison fields:
- decision_agreement: AGREE_FIT / AGREE_NO_FIT / MACHII_FALSE_NEGATIVE /
  MACHI_FALSE_POSITIVE / MACHI_UNRESOLVED;
- estimated_vs_reported_vram_delta_bytes when both exist;
- estimated_vs_reported_vram_ratio when safe to derive;
- notes must be typed/bounded, no prompt or response content.

Use a correctly spelled enum identifier in source, e.g.
`MACHI_FALSE_NEGATIVE`; the label above is semantic, not a mandated typo.

Do not call Ollama `size_vram` peak VRAM. External peak observers, if added
later, remain a distinct measurement.

## 7. Learning objective

The comparison dataset exists to answer questions such as:
- Does Machi systematically overestimate/underestimate Ollama workloads?
- Which model families/quantizations create the largest estimation errors?
- Which hardware classes produce disagreement?
- Are Machi false negatives excluding models Ollama runs successfully?
- Are Machi false positives associated with provider load failures?
- Can future generic Machi estimation improve without copying Ollama internals?
- How do native/vLLM and Ollama compare on load time, memory and throughput for
  genuinely comparable workloads?

Do not automatically change Machi policy from this data in Stage 1.
Learning/retuning requires a later governed change with reproducible evidence.

## 8. Cross-macropath analytics

Native and Ollama evidence should normalize into comparable metric names where
semantics truly match:
- load_seconds;
- input_tokens / output_tokens;
- generation_seconds;
- tokens_per_second;
- model/runtime/hardware identity;
- context/concurrency;
- success/failure;
- reported/observed memory with explicit measurement source and availability.

Provider-native raw evidence remains separate.

Never force false comparability:
- Ollama `size_vram` is not the same as externally measured peak VRAM;
- runtime schedulers may use different placement/offload policies;
- model catalogs/representations may not be byte-identical.

## 9. Probe Plan

The existing native `probe=True` mechanism is accepted precedent and may be
enhanced for clarity as long as:
- native behavior remains unchanged;
- native physical evidence is not invalidated;
- Plan fingerprints remain purpose-sensitive;
- normal deployment still requires prior qualification;
- one ResourceManager ledger remains authoritative.

A small typed `PlanPurpose.DEPLOYMENT | QUALIFICATION` evolution is allowed if
repository review shows it is a clean backwards-compatible replacement for the
boolean. It is not required merely for naming aesthetics.

## 10. Deferred Serve boundary

Ollama automatic residency/eviction under long-lived serving reservations is a
later Chunk-4/Serve authorization problem.

Chunk 3 must record the debt but must not redesign Ollama scheduling or
multi-model serving policy.
