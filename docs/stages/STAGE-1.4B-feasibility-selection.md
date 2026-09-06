# Stage 1.4B — Feasibility + capacity-based selection

**Milestone 1 — Walking skeleton.**

Status: **CLOSED.** `L1`. One active `ModelRequirementEstimator`; SAFE
capacity remains the fit authority. Cross-provider comparison is
development-only.

This stage chooses a candidate against SAFE capacity. It does not
download, reserve, or infer.

## CURRENT STAGE

`ModelRequirementEstimator` port, Kultrun and llmfit adapters,
`ModelEstimationRequest`, `DeploymentCapacity`, `CapacityUtilization`,
20–100% preferred-band policy, deterministic ranking,
`SelectionRecommendation`, `DeploymentPlan` v0, `GET /v1/models/selection`,
`kultrun models recommend`, Prototype Console Model Selection panel.

## PREDECESSOR OUTPUTS

| Consumed | From |
|---|---|
| Catalog + `ModelRequirement` v0 | Stage 1.4A · `7e40c70` |
| SAFE `CapacityEnvelope` | Stage 1.2 |
| Runtime catalogue (names only; planning does not import `runtime`) | Stage 1.3 |
| Prototype Console | Stage 1.2A |
| One-active-estimator architecture | `1db2437` (docs) |

## THIS STAGE'S REQUIRED OUTPUT

Replaceable requirement estimators + SAFE-capacity selection + a
development-only comparison tool.

### Product path

```text
ModelSource → ModelMetadata
  → ModelRequirementEstimator (one configured adapter)
  → ModelRequirement
  → Kultrun SAFE DeploymentCapacity
  → feasibility → 20–100% preferred band
  → deterministic ranking
  → SelectionRecommendation → DeploymentPlan v0
```

Composition (`KULTRUN_MODEL_REQUIREMENT_ESTIMATOR`, default `kultrun`)
resolves the provider id to an adapter. Planning consumes only the port.
There is no production reconciler, no dual estimates, and no silent
fallback between providers.

### Contracts

| Kind | Role |
|---|---|
| `model.estimation_request@1` | Shared request: identity, quant, context, runtime, placement, offload, TP, batch |
| `model.requirement@1` | Additive: `estimator_provider`, `estimator_version`, `assumptions`, `measured` |
| `planning.deployment_capacity@1` | SAFE slice for the proposed placement |
| `planning.capacity_utilization@1` | `max(required/safe)` over memory only; storage excluded |
| `planning.selection_policy@1` | Preferred band defaults 0.20–1.00 |
| `planning.model_evaluation@1` | FeasibilityResult v0 (flattened; no nested `ModelRequirement`) |
| `planning.selection_recommendation@1` | Primary, alternatives, underutilized, rejected, active estimator |
| `planning.deployment_plan@1` | v0 plan; active estimator only |

Canonical units: bytes. Unknown is never zero. Silent substitution of
model, quantization, context, placement, or offload is unsupported.

### Adapters

| Adapter | Method | Notes |
|---|---|---|
| `KultrunRequirementEstimator` | `curated` (original six) / `formula_v0` (expanded) | Packaged lookup. Does not invent a host fit. |
| `LlmfitRequirementEstimator` | `llmfit-plan` | `llmfit --no-dashboard plan <ref> --context N --quant Q --json`. Host fit flags ignored. Optional extra `estimators` pins `llmfit==1.1.14` (MIT). |

llmfit `*_gb` fields are GiB (2^30). Missing binary with provider
`llmfit` → `provider-unavailable`. Default Kultrun path does not require
llmfit.

### Development comparison (not product)

`python tools/compare_model_estimators.py` (`--live` for a real
executable). Thresholds: GOOD ≤15% relative, WARNING ≤35%, else
`LARGE_DIFFERENCE`, where relative = `(max−min)/max`. Generated JSON is
gitignored (`validation/`). CI uses captured plan fixtures.

### Platform API / CLI / Console

| Surface | Behaviour |
|---|---|
| GET `/v1/models` | Catalog only. `ranking/selection/download: false` |
| GET `/v1/models/selection` | Active estimator + recommendation + plan |
| `kultrun models` | Catalog |
| `kultrun models recommend` | Configured estimator |
| Console **Model selection** | Active estimator, requirement, SAFE, utilization, fit, recommendation |

No Kultrun-vs-llmfit columns anywhere on the product path.

## Candidate set (consume; do not rediscover)

19 packaged variants. Original six remain 1.4A regression fixtures
(`curated`). Expanded set is `formula_v0`. All 19 overlap both
estimators.

Families: TinyLlama, Qwen2.5, Llama 3.1, Llama 3.2, Phi, Mistral,
Gemma 2, Mixtral (MoE). Size bands: sub-2B, 2–4B, 7–9B, 12–16B, 20–35B,
60–80B. Quantizations: `q4_k`, `awq`, `fp16` as representative
deployment options, not a full matrix.

## Persistence / reconciliation

Recommendations are recomputed, not stored as truth. Comparison reports
are not customer runtime state.

## Cancellation / cleanup

No mutation, no orphans.

## Internal comparison (development)

Live `llmfit` 1.1.14 vs Kultrun 1.4B.0, 19 identical requests:

| Overall (VRAM-led) | Count |
|---|---|
| GOOD | 8 |
| WARNING | 9 |
| LARGE_DIFFERENCE | 2 |

VRAM LARGE_DIFFERENCE: Qwen 2.5 7B AWQ (40.7%), Qwen 2.5 14B AWQ
(35.3%). Kultrun is conservative. RAM LARGE_DIFFERENCE on small models
is llmfit's 8 GiB `ram_gb` floor (K-38), not a unit mismatch. No
assumption substitution. Live TinyLlama VRAM matched the captured
fixture (1.181 GiB) — not host-sensitive.

24 GiB SAFE VRAM fixture crossings (engineering only):

- Qwen 7B AWQ: Kultrun preferred 33.3% / llmfit underutilized 19.8%
- Phi-3.5 Mini: Kultrun underutilized 16.7% / llmfit preferred 23.8%
- Qwen 32B Q4: Kultrun exceeds 108.3% / llmfit preferred 89.6%

Do not rewrite production estimates to match. Recorded as K-36.

On the default RTX Pro 4500 fixture (~23.9 GiB SAFE VRAM):

- Kultrun-active primary: `qwen2.5-14b-instruct-q4` at 58.6%
- llmfit-active primary: `qwen2.5-32b-instruct-q4` at 90.0%

llmfit does not supply peak-acquisition storage; unknown storage is not
treated as zero, so storage does not reject that 32B candidate. Kultrun
does supply storage and rejects it. Same Planning, different
`ModelRequirement` evidence.

## Acceptance

| Layer | Result |
|---|---|
| T0 focused | 39 tests (`test_estimators` 17, `test_planning_selection` 16, `test_estimator_comparison` 6) |
| T1 | architecture 61 + full suite 560, ruff clean, mypy strict 143 files |
| T2 | Clean installed wheel 10/10; real `llmfit plan` from the artifact; both estimators on the original six; product recommend + API + Console with each provider |
| T3 | not required (live llmfit `minimum` matched captured fixtures) |

Artifact: `kultrun-0.1.0-py3-none-any.whl`  
SHA-256: `4fd948d152a75f6225614ca9cd183c11eed520bcac8a0a024b2397d0aed169c8`  
Build: `0.1.0+d63f986c0db8` from `d63f986c0db83f499c22f49fbcf3caa8efd6014b`  
`clean_source: true`

llmfit: 1.1.14, MIT, subprocess CLI, optional extra. Six original-fixture
raw plans hashed under `/tmp/kultrun-t2-14b/raw/` (T2 workspace, not
committed). Live comparison report sha256
`9e96397cc9e7bb9c51c8ca3b1fa8294486662e899b898866273a18bad509cb11`.

Checkpoint: `checkpoints/STAGE-1.4B-feasibility-selection.json`.

## Debt

K-36 (curated / formula_v0 estimates; documented band crossings),
K-37 (llmfit optional extra; operator runbook still open), K-38 (llmfit
RAM floor). None authorize a mutation.

## Not begun

Stage 1.4C (acquisition / inventory). Resource admission. Inference.
Learned ranking. Production estimator reconciliation. Live Hub fetch.
