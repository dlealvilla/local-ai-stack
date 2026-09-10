# Kultrun storage footprint

Stage 1.6L working estimates. These are **sanity ranges and catalog facts**,
not universal constants. Admission uses the conservative supported bound on
the **destination pool**, never a host-wide first-pool shortcut.

Pip policy for managed runtime install: **`--no-cache-dir`**. Kultrun does
not delete `~/.cache/pip` or other global user caches.

Reserve used in v1 estimates: 5 GiB (`LOW_SPACE_THRESHOLD_BYTES`). After Step 0
and truthful characterization, authorizing storage below this threshold
asks the administrator to clear space **before** 30% deployment reductions.

Confidence: LOW for formula/estimated rows; MEDIUM when catalog metadata is
curated; HIGH only when an artifact’s stored size is measured.

---

## Base without model

| Component | Persistent | Peak / transient | Source | Confidence |
|---|---|---|---|---|
| Kultrun package / state | 0.1–0.5 GiB (v1 default 0.3 GiB) | included | estimate | LOW |
| Managed vLLM runtime (isolated venv) | 8–15 GiB (v1 default 12 GiB) | ~same again while staging | prior physical run + estimate | LOW–MEDIUM |
| Runtime metadata | small (MiB) | — | estimate | LOW |
| Install cache | **0** (`--no-cache-dir`) | 0 | policy | HIGH (policy) |
| Staging / transient | 0 after success | ~runtime size during provision | estimate | LOW |
| Temp | disposable | small | policy | LOW |
| Telemetry / log baseline | 64 MiB baseline | — | estimate | LOW |
| Reserve (not consumed, must remain free) | — | 5 GiB | policy | — |
| **Base persistent total** | **~9–17 GiB** (v1 ~12.4 GiB) | | | LOW |
| **Base peak provisioning** | | **~15–25 GiB** (v1 admitting peak = persistent + staging ≈ 24 GiB; operator `df` needs ~29 GiB before Capacity's 5 GiB withhold) | estimate | LOW |

Capacity owns headroom. `runtime_provisioning_requirement.required_peak_free_bytes`
is persistent + staging + cache (v1 24 GiB). ResourceManager admits that against
**SAFE**, which already withheld 5 GiB. The 5 GiB reserve is reported on the
requirement but is not added a second time. A later measured install may replace
the estimate (`measured=True`).

---

## Model artifact ranges (disk, not VRAM)

Exact catalog metadata overrides these. Disk footprint is distinct from VRAM.

| Class | Approximate persistent | Typical acquisition peak |
|---|---|---|
| 0.5–3B | 0.5–3 GiB | persistent + staging |
| 7–8B | 4–8 GiB | ~2× persistent (download + staging) |
| 12–14B | 8–15 GiB | ~2× |
| 30–32B | 18–25 GiB | ~2× |
| 70B | 35–50+ GiB | ~2× |

### Catalog examples (current packaged set)

| Candidate | Persistent (catalog) | Peak additional (catalog) | Notes |
|---|---|---|---|
| TinyLlama 1.1B Chat Q4 | 0.7 GiB | 1.5 GiB | small |
| Qwen2.5 7B-class (5.4 GiB row) | 5.4 GiB | 12.0 GiB | 7–8B-class |
| Llama 3.1 8B Instruct Q4 | ~4.9 GiB | catalog peak | 7–8B |
| 12–14B-class packaged rows | ~9 GiB | catalog peak | 12–14B |
| Mixtral 8x7B Instruct Q4 | 26.0 GiB | 54.0 GiB | 30–32B-class MoE |

Use `ModelRequirement.storage_bytes` and `peak_additional_bytes` at
admission. Unknown is not zero.

---

## Combined examples (same pool)

Assume v1 base persistent ≈ 12.4 GiB, runtime admitting peak ≈ 24 GiB
against SAFE (operator disk free ≈ 29 GiB before withhold), then
model persistent + acquisition peak on the **model** pool. If runtime and
model share one quota, peaks must not be admitted as independent budgets
that double-count the same bytes; reservations are per pool.

| Scenario | Persistent (base + model) | Peak during materialization | Confidence |
|---|---|---|---|
| Base + small (TinyLlama 0.7 + 1.5 peak) | ~13 GiB | sequential: runtime ~24 GiB SAFE then model ~2 GiB | LOW |
| Base + 7–8B (~5–8 GiB + ~12 GiB peak) | ~18–20 GiB | runtime first ~24 GiB SAFE; model acquisition ~12 GiB | LOW |
| Base + 12–14B (~9–15 GiB) | ~22–27 GiB | runtime ~24 GiB SAFE then model peak | LOW |
| Base + 30–32B (Mixtral 26 + 54 peak) | ~38 GiB | model peak 54 GiB may exceed runtime peak; destination pool must have that SAFE | LOW |

Administrators should eventually see:

```
Kultrun/runtime persistent: 9–17 GiB
Selected model persistent: A GiB (catalog or measured)
Peak provisioning/acquisition: B GiB
Expected final persistent total: C GiB
Required safe free space before action: D GiB (conservative peak + reserve)
```

---

## What this is not

- Not VRAM / RAM / unified memory.
- Not “available = 25 GiB” because Sonar’s exploration ceiling is 25 GiB.
- Not a license to wipe unrelated files or global pip caches.
