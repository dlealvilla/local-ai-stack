# Stage 1.4A — Model sources / catalog + metadata

**Milestone 1 — Walking skeleton.**

Status: **CLOSED.** `L1`. Packaged curated catalog; no live Hub fetch.

This stage lists candidates. It does not choose a model, download one,
rank, or admit resources.

## CURRENT STAGE

`ModelSource` port, one Hugging Face–identity adapter, six curated
variants, normalized `ModelMetadata` + host-independent
`ModelRequirement` v0, `GET /v1/models`, Prototype Console Model Catalog
panel.

## PREDECESSOR OUTPUTS

| Consumed | From |
|---|---|
| Runtime / executor closed at L2 | Stage 1.3 · `9fb01d3` |
| Capacity envelope (SAFE layers unused here) | Stage 1.2 |
| Prototype Console | Stage 1.2A |
| Capacity-based selection architecture | `1c7223c` (docs only; 1.4B not begun) |
| Model-lifecycle sequence | `WORKFLOW-model-lifecycle-roadmap` |

## THIS STAGE'S REQUIRED OUTPUT

`ModelSource` + `ModelMetadata v1` + `ModelRequirement v0` + catalog API
+ Prototype Console catalog panel.

### Contracts

| Kind | Role |
|---|---|
| `model.metadata@1` | Additive fields: architecture, display_name, supported_runtimes |
| `model.requirement@1` | Additive fields: unified_memory, activations, estimated_vram, assumed context, runtimes, estimation_method |
| `model.catalog_entry@1` | Metadata + requirement. Not a recommendation |

A requirement never names a host. Unknown stays unresolved (TinyLlama KV
and unified memory are deliberately unresolved). Estimated VRAM is
deployed-memory, not parameter count and not artifact size.

### Adapter

`adapters/model_source/huggingface.py` — Hub **identity** (`source_ref`)
and a packaged set of six variants. Does not import `huggingface_hub`,
does not search the Hub, does not download. Live fetch is `docs/DEBT.md`
K-35. Estimates are `curated-conservative-v0` (K-36).

### Platform API / CLI

| Method | Path | Effect |
|---|---|---|
| GET | `/v1/models` | `{source, candidates, ranking: false, selection: false, download: false}` |
| POST | `/v1/models` | 404/405 — not a mutation |

`kultrun models` prints the same catalog. GET is idempotent.

### Prototype Console

**Model Catalog** panel: source, live-fetch no, ranking/selection/download
no, six cards with parameters, quantization, artifact, peak acquisition,
estimated RAM/VRAM, unified memory (unresolved where unstated), context,
runtime, license, confidence, method.

**Model selection** is listed as not implemented · stage 1.4B.

Opportunistic fix: unresolved wire values (`$unresolved`) no longer
render as `[object Object]` (pid / exit code after exit; unified memory
"not provided"). Regression covered in `tests/test_model_catalog.py`.

## Candidate set (consume; do not rediscover)

Six variants, Hub identity, packaged estimates. Quantized siblings are
distinct candidates.

| logical_name | source_ref | params | quant | artifact | peak | RAM | VRAM | context | confidence | notes |
|---|---|---|---|---|---|---|---|---|---|---|
| tinyllama-1.1b-chat-q4 | TinyLlama/TinyLlama-1.1B-Chat-v1.0 | 1.1B | q4_k | 0.7 GiB | 1.5 GiB | 2.5 GiB | 1.2 GiB | 2048 | low | KV unresolved |
| qwen2.5-3b-instruct-q4 | Qwen/Qwen2.5-3B-Instruct | 3.1B | q4_k | 2.0 GiB | 4.5 GiB | 6.0 GiB | 3.2 GiB | 32K | medium | |
| qwen2.5-7b-instruct-awq | Qwen/Qwen2.5-7B-Instruct-AWQ | 7.6B | awq | 5.4 GiB | 12 GiB | 10 GiB | 8.0 GiB | 32K | medium | |
| llama-3.1-8b-instruct-fp16 | meta-llama/Llama-3.1-8B-Instruct | 8.0B | fp16 | 16 GiB | 33 GiB | 20 GiB | 19.5 GiB | 131K | medium | commercial unknown |
| qwen2.5-14b-instruct-awq | Qwen/Qwen2.5-14B-Instruct-AWQ | 14.7B | awq | 10 GiB | 22 GiB | 16 GiB | 14.5 GiB | 32K | medium | |
| qwen2.5-72b-instruct-awq | Qwen/Qwen2.5-72B-Instruct-AWQ | 72.7B | awq | 40 GiB | 82 GiB | 48 GiB | 48 GiB | 32K | low | over a 24 GiB SAFE GPU |

On a 24 GiB SAFE VRAM envelope (1.4B fixture work): TinyLlama and 3B
fall below a 20% preferred band; 7B / 8B / 14B sit inside it; 72B
exceeds SAFE. That spread is why these six exist. 1.4B must compute it;
1.4A does not.

## Persistence / reconciliation

None. Catalog is packaged evidence, not inventory. Inventory is 1.4C.

## Cancellation / cleanup

No mutation, no orphans.

## Acceptance

| Layer | Result |
|---|---|
| T0 focused | 14 tests in `tests/test_model_catalog.py` |
| T1 | architecture 61 + full suite 508, ruff clean, mypy strict 127 files |
| T2 | Clean installed wheel, 10/10 |
| T3 | not required (no live source fetch claimed) |

Artifact: `kultrun-0.1.0-py3-none-any.whl`  
SHA-256: `42791d75551d58c0b2f61b151148b8c8f3a449c7027917b6a5a7cd7a60d3c125`  
Build: `0.1.0+e4a6d5d013d8` from `e4a6d5d013d8fbdb1325a29542c7b2278737e272`

Local console (installed wheel, `KULTRUN_FIXTURE=default`): Model Catalog
WORKING; six cards; ranking/selection/download no; Model selection not
implemented; `$unresolved` pid after exit reads "not measured", not
`[object Object]`.

Checkpoint: `checkpoints/STAGE-1.4A-model-catalog.json`.

## Debt

K-35 (live Hub fetch deferred), K-36 (curated conservative estimates).
Neither authorizes a mutation.

## Not begun

Stage 1.4B (feasibility, utilization, ranking, `SelectionRecommendation`,
`DeploymentPlan`). Stage 1.4C (download / inventory). Resource admission.
Inference. Whole-Hub search. Learned ranking. Portfolio optimizer.
