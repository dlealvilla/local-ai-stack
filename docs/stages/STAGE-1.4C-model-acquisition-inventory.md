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

T0: 34 focused acquisition tests. T1: architecture 61, full suite 619,
ruff clean, mypy strict 153 files. Local Prototype Console on
`127.0.0.1:8420/prototype` acquired then deleted the fixture acceptance
artifact; inventory showed stored artifacts 1 → 0, running instances 0,
stored implies running no.

### T2 clean wheel

Source commit `6a2f7872219334afa3c54fde93810b2c626ef92b`.
Artifact `kultrun-0.1.0-py3-none-any.whl`.
SHA-256 `1657a46f24c6b4a24c166047b5a2e7f7183505ed2e665b0b2d3ccedd90bc101d`.
Build `0.1.0+6a2f78722193`. Installed with extra `acquisition` into an
isolated venv; `kultrun.__file__` was not the source checkout.

| Proof | Result |
|---|---|
| Catalog / recommend | 19 candidates; recommend does not download |
| Empty inventory | `empty inventory` |
| Fixture acquire ×2 | acceptance + tinyllama stored |
| Delete one | remaining `tinyllama-1.1b-chat-q4` |
| Real Hub acquire | `huggingface_hub` 0.36.2; `snapshot_download` |
| Source | `hf-internal-testing/tiny-random-gpt2` |
| Requested / resolved | `main` / `71034c5d8bde858ff824298bdedc65515b97d2b9` |
| Bytes / files | 12512611 / 10 |
| Verification | required files + readable + pinned revision + safetensors header |
| Artifact | `artifact_7a01cf58000f8295` STORED; serving false |
| API | GET inventory `200 2 False` |
| Console assets | shipped in wheel |

## Debt

K-39 scheduler/resume; K-40 warehouse/dedup; K-41 conversion/quant;
K-42 gated UX / license engine; K-43 optional `huggingface_hub` extra.

## Not begun

Stage 1.5A ResourceReservation. Stage 1.5B InferenceInstance. Runtime
loading, vLLM, llama.cpp inference, prompt execution, large production
downloads.

## Checkpoint

`checkpoints/STAGE-1.4C-model-acquisition-inventory.json`
