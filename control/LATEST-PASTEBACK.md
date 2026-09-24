==================== BEGIN PASTE BACK — OLLAMA CHUNK 3 DUAL QUALIFIER ====================

A. STATUS
PASS. Instruction `MACHI-OLLAMA-CHUNK-03-DUAL-QUALIFIER-002` executed as a local fixture control plane. `NO_SOLUTION_DECISION_REQUIRED`. No new dependency, no Ollama private scheduler import, no second resource ledger, no catalog merge, and the shadow result is not authoritative.

B. Starting/final SHA
Starting `180a4e898c5fcd46ae54a6d1c8aa8acfe84c66e6`
Final `da54773ab34b8d4c159fd9427519577319b25821`

C. Separate catalog implementation
Native/vLLM still uses `ModelArtifact` and warehouse qualification. An Ollama entry is `model.ollama_candidate` version 1, built only from public facts. `public_candidate` does not construct a `ModelArtifact`.

D. Ollama candidate identity contract
Identity is `ocand_` plus a hash of the canonical sha256 digest. A `sha256:` prefix is stripped. The display name is not an input. Two tags with one digest share one candidate id. A tag alone is rejected.

E. Machi shadow evaluator behavior
`evaluate_shadow` runs before the provider call. It uses `estimate_serving` only when explicit public dtype, layer count, kv heads, and head dimension are present. A published size that already exceeds SAFE accelerator bytes is `NO_FIT`. Otherwise missing shape stays `UNRESOLVED`. Family labels are not turned into architecture or parameter counts. `refine_vllm` is not imported. Host bytes stay unresolved. Policy `m6.shadow.1`.

F. Ollama authoritative qualifier adapter behavior
`qualify_ollama` does not take a shadow result. The fixture API covers `/api/tags`, `/api/show`, `/api/ps`, `/api/generate`, and unload. Provider `PASS` requires a counted output token and the expected digest in `/api/ps`. Digest mismatch, missing `/api/ps` entry, missing token, provider no-fit, and host failure are typed refusals. Unload failure is stored on `unload_failure` and does not rewrite a pass. No socket is opened.

G. Qualification identity/schema treatment
`QualificationEvidence` version 2 still requires a warehouse artifact id, and `covers()` accepts only schema version 2. Putting an Ollama digest into that field would invent a warehouse identity. The smallest compatible record is the companion `model.ollama_qualification` version 1. Native version 2 evidence is unchanged and still decodes.

H. Probe Plan / ResourceManager treatment + native regression result
`PlanInputs.probe` remains the native boolean. A normal plan with a mismatched revision still fails `QUALIFICATION_REQUIRED`. A probe plan whose evidence context is too small still succeeds. Ollama uses `plan.qualification_probe` version 1, purpose `qualification`, admitted by `ResourceManager.admit_probe` on the same reservation log. A probe hold counts against SAFE capacity, so a later deployment that no longer fits is refused. `execution_authorized` stays bound to a `DeploymentConfiguration` and does not accept the probe hold. 537 `tests/machi` passed, including architecture.

I. Comparative analytics contract
`model.qualification_comparison` version 1 records both evaluators for one case: digest, display name, candidate id, capacity evidence, hardware class, execution-environment fingerprint, context, concurrency, shadow policy and fit, provider outcome, `size_vram` source `ollama.api.ps`, and load/token metrics as Maybe values. No prompt, response, or filesystem path is stored.

J. Agreement/disagreement classification examples
Shadow FIT + Ollama PASS -> `AGREE_FIT`, and Ollama's outcome is PASS.
Shadow NO_FIT + Ollama PASS -> `MACHI_FALSE_NEGATIVE`, and Ollama's outcome stays PASS.
Shadow FIT + Ollama NO_FIT -> `MACHI_FALSE_POSITIVE`, and Ollama still refuses.
Shadow UNRESOLVED + Ollama PASS, and shadow UNRESOLVED + Ollama NO_FIT -> `MACHI_UNRESOLVED`.
A provider host failure is `MACHI_UNRESOLVED` because it is not a fit verdict.

K. Metric provenance/availability treatment
Shadow accelerator bytes are `ESTIMATED` with provenance `machi.formula` when resolved, otherwise `UNRESOLVED`. Host bytes are `NOT_EXPOSED`. `size_vram` is `OBSERVED` from `ollama.api.ps` and labeled `runtime_reported`. A VRAM delta or ratio is `DERIVED` only when both integers exist, with semantics `estimate_vs_runtime_reported`. Missing operands are `not_comparable`.

L. Tests/gates
`tests/machi`: 537 passed, including architecture, native plan/admit/serve regressions, and the Chunk 3 cases above.
`ruff check src/machi tests/machi`: pass.
`mypy --strict src/machi`: 169 files, success.

M. Wheel build ID/SHA256
build `0.1.0+da54773ab34b`
sha256 `b2781f38e3a77829ec7b0e45096f80e18fb196e4d1a75417a0e792c75761b184`
size `304840`
clean_source `true`

N. Isolated verify_ok
`serve_ok sin_5c22adc1d8920043`
`verify_ok`

O. Docs/debt changes
`docs/machi/ARCHITECTURE.md` and `docs/machi/M6.md` record catalog separation, Ollama authority, shadow comparison, and no Stage 1 retune.
`docs/DEBT.md` adds `M-6-OLLAMA-01` for Ollama residency/eviction under a later Serve hold. Authorizes NO.
Native qualification schema and AUTO state were not changed.

P. Local/origin equality
`LOCAL da54773ab34b8d4c159fd9427519577319b25821`
`ORIGIN da54773ab34b8d4c159fd9427519577319b25821`
Recovery `checkpoint/native-vllm-partial-pass-2026-09-24` remains `6e17f4a817d1571e0a708decec405ceda0282c7f`.

Q. Exact support claim
A fixture Ollama candidate can be normalized, shadow-evaluated, authorized on the existing ResourceManager, qualified by a fake Ollama adapter, and stored as comparison analytics. Ollama's result is the only fit authority on that macropath. Native Plan, Admit, and Serve behavior is preserved. This does not claim a physical Ollama qualification, a real model load, or Serve for Ollama.

R. What remains for physical Ollama qualification
A live loopback daemon at the pinned Foundation generation, a real local model digest from `/api/tags` and `/api/show`, one ResourceManager-authorized load, `/api/ps` `size_vram`, a real output token, unload, and the same comparison record filled from that run. No model download or Chunk 4 was started in this increment. `M-5-OLLAMA-03` and `M-6-03` remain open.

S. Final status
STOP — OLLAMA CHUNK 3 DUAL QUALIFIER LOCAL COMPLETE. WAIT FOR LEAD REVIEW.

==================== END PASTE BACK — OLLAMA CHUNK 3 DUAL QUALIFIER ====================
