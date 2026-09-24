# Ollama Chunk 3 — Model Catalog + Specialist Qualification Boundary

**Status:** PRODUCT DIRECTION ACCEPTED / QUALIFIER BOUNDARY DECISION PENDING
**Date:** 2026-09-24

## Accepted model-catalog separation

Do not force Machi/native model artifacts into Ollama's model store as the
default Ollama macropath design.

When the active macropath is native/vLLM:
- use the Machi model catalog / Model Warehouse and its provenance model.

When the active macropath is Ollama:
- use Ollama's model catalog/store/API semantics;
- local models come from Ollama's own model inventory;
- acquisition uses Ollama mechanisms/providers where product policy permits.

Shared product concepts may normalize a view for policy/UI, but the underlying
catalogs remain separate and provider-owned. A normalized view must not imply
artifact conversion or make one catalog the source of truth for the other.

## Verified Ollama v0.34.3 specialist layer

Exact v0.34.3 source contains an internal scheduler/fit layer that:
- loads model metadata;
- predicts VRAM with `llm.PredictServerVRAM`;
- selects GPU placement/offload;
- derives automatic context/batch behavior;
- compares predicted load with available GPU/system memory;
- uses headroom before admitting an additional resident model;
- evicts resident models to make room;
- handles load/OOM retry;
- owns runner residency and keep-alive scheduling.

Public v0.34.3 API exposes:
- `GET /api/tags` local model inventory with size/digest/details;
- `POST /api/show` model metadata/capabilities;
- `POST /api/pull` Ollama-native acquisition;
- `GET /api/ps` loaded model digest, total size and `size_vram`;
- generate/chat load and inference timing/token metrics.

There is no public v0.34.3 dry-run qualification endpoint that returns the
internal `PredictServerVRAM`/placement decision as a durable external
qualification record.

## Boundary decision

Three approaches remain:

### A — duplicate Ollama specialist fit logic in Machi
Disfavored. Version-coupled duplication and violates reuse-industry principle.

### B — let Ollama replace Machi qualification entirely
Ollama owns fit/load/scheduling, but it does not provide Machi's durable,
identity-scoped qualification evidence or product-level policy/ResourceManager
authority. This would remove an accepted Machi layer and risks authority
inversion.

### C — integrate Ollama specialist fit *inside* Machi qualification
Recommended.

Machi remains responsible for:
- coarse product/policy filtering;
- global ResourceManager authorization;
- qualification campaign policy;
- exact qualification identity;
- durable QualificationEvidence;
- DeployableModels/product meaning;
- cross-runtime normalized evidence.

Ollama remains responsible for:
- Ollama model representation/catalog mechanics;
- Ollama-specific metadata interpretation;
- exact specialist memory/placement logic;
- partial offload behavior;
- runner load/unload/residency;
- internal scheduler decisions and OOM retry.

Qualification flow:
```text
Ollama model candidate
 -> Machi coarse policy/capacity gate
 -> Machi probe Plan / ResourceManager reservation
 -> ask Ollama to load using bounded explicit product-level settings
 -> Ollama scheduler performs specialist fit/placement
 -> inspect /api/ps digest + size_vram
 -> real token probe
 -> map outcome/metrics to Machi QualificationEvidence
 -> unload/release
 -> DeployableModels
```

Do not copy/reimplement `PredictServerVRAM` or other Ollama-private scheduler
logic into Machi.

`size_vram` is runtime-reported loaded VRAM, not an external peak-memory
measurement.

## Open question

Whether the existing native `probe=True` should remain a boolean or be
formalized as a typed plan purpose is independent of Ollama. Any enhancement
must preserve native behavior and tests.

## Later boundary

Ollama's automatic model eviction/residency can conflict with long-lived Machi
deployment reservations if not constrained. That is a later authorization /
Serve boundary and must not be silently solved inside Chunk 3.
