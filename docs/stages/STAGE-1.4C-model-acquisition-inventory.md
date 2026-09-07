# Stage 1.4C — Model acquisition + plural Model Inventory

**Milestone 1 — Walking skeleton.**

Status: **CLOSED.** `L1`. Replaceable acquisition, verified stored
artifacts, plural inventory. Stored is not running.

This stage answers which model artifacts are stored and usable. It does
not answer which stored model is currently running.

## CURRENT STAGE

`ModelAcquisitionProvider` port, Hugging Face and fixture adapters,
staged/verified `ModelArtifact`, Kultrun-owned manifest, plural
`ModelInventory`, safe delete, API/CLI/Console inventory.

## PREDECESSOR OUTPUTS

| Consumed | From |
|---|---|
| Catalog + `ModelRequirement` v0 | Stage 1.4A |
| Selection + `DeploymentPlan` v0 | Stage 1.4B |
| SAFE `CapacityEnvelope` | Stage 1.2 |
| Prototype Console | Stage 1.2A |

The existing pipeline is unchanged through Planning. Acquisition begins
after a known candidate identity exists.

## THIS STAGE'S REQUIRED OUTPUT

```text
SelectionRecommendation / catalog identity
  → ModelAcquisitionRequest
  → SAFE storage preflight
  → ModelAcquisitionProvider (staging only)
  → verify + ArtifactManifest
  → promote → ModelArtifact STORED
  → plural ModelInventory
```

`ModelSource` still does not download. `HuggingFaceSource` remains
identity/metadata. Acquisition is a separate adapter family.

## Contracts

| Kind | Role |
|---|---|
| `model.acquisition_request@1` | Known candidate; no caller destination path |
| `model.acquisition_receipt@1` | stored / reused / failed; `serving` always false |
| `model.artifact_manifest@1` | Kultrun lifecycle evidence |
| `model.artifact@1` | Additive storage/provenance/verification fields |
| `config.platform@1` | Additive `model_acquisition_provider` |

`ArtifactState`: remote, acquiring, stored, invalid, deleted. No
RUNNING / STARTING / STOPPING.

## Adapters

| Adapter | Role |
|---|---|
| `FixtureAcquisitionProvider` | Tiny deterministic files. Offline T0/T1. |
| `HuggingFaceAcquisitionProvider` | `huggingface_hub` `model_info` + `snapshot_download`. Optional extra `acquisition` (`huggingface_hub>=0.23,<1`, Apache-2.0). |

Tokens from `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` or a named env ref.
Never persisted.

Bounded T2 target: `kultrun-hf-acceptance-tiny` →
`hf-internal-testing/tiny-random-gpt2`. Not a recommendation and not in
the 19-candidate catalog.

## Platform API / CLI / Console

| Surface | Behaviour |
|---|---|
| GET `/v1/models` | Catalog. Unchanged. |
| GET `/v1/models/selection` | Recommendation. Still does not download. |
| GET `/v1/models/inventory` | Plural artifacts. `serving: false`. |
| POST `/v1/models/acquire` | Known `candidate` or `recommended`. No URL/path. |
| DELETE `/v1/models/artifact` | Exact `artifact_id`. Not stop/unload. |
| `kultrun models inventory` | Plural stored artifacts |
| `kultrun models acquire` | Explicit mutation |
| `kultrun models delete` | Safe delete |
| Console **Model inventory** | After selection. Acquire/Delete. Stored ≠ running. |

Acquisition is synchronous in v0.

## Persistence / reconciliation

Records: `model.artifact` and `model.inventory_record` keyed by
`artifact_id`. Files: `{state_root}/models/{staging,artifacts,locks}`.
Deleted records remain tombstones. A STORED record whose manifest is
missing is observed as INVALID.

## Cancellation / cleanup

Failed or interrupted fetch cleans staging. Partial weights are never
promoted. No download scheduler.

## Acceptance

T0/T1 fixture lifecycle, SAFE preflight, catalog/selection regressions
(19 candidates, AUTO estimator). T2 from a clean wheel: empty inventory,
two fixture artifacts, delete one, bounded real Hugging Face acquisition,
API, CLI, Console assets. T3 not required.

## Debt

K-39 scheduler/resume; K-40 warehouse/dedup; K-41 conversion/quant;
K-42 gated UX / license engine; K-43 optional `huggingface_hub` extra.

## Not in this stage

ResourceReservation, InferenceInstance, runtime loading, vLLM,
llama.cpp inference, prompt execution, large production downloads.
