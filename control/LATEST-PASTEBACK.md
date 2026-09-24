==================== BEGIN PASTE BACK — OLLAMA CHUNK 3 CORRECTION ====================

A. STATUS
PASS. Instruction `MACHI-OLLAMA-CHUNK-03-CORRECTION-003` executed. The accepted dual-evaluator architecture is unchanged. `NO_SOLUTION_DECISION_REQUIRED`.

B. Starting/final SHA
Starting `da54773ab34b8d4c159fd9427519577319b25821`
Final `4aa21ccabade398a8f931c5a231baed84bbf45f0`

C. Exact v0.34.3 API seam correction
`ShownModel` no longer has a digest. Digest is read from `GET /api/tags` and `GET /api/ps`. The fixture seam splits empty preload (`preload`) from the real token request (`generate_probe`). Both represent `POST /api/generate`. `/api/show` remains metadata only and is not used as identity proof.

D. Catalog identity drift handling
Before preload, the case re-lists `/api/tags` and requires the display name to still map to the candidate digest. Absence or a changed digest is `catalog_identity_changed`, provider fit `UNRESOLVED`, and preload/generate are not called.

E. Preload -> ps -> token -> ps identity proof
Required order on the clean path: tags, preload, `/api/ps` name+digest, generate_probe, `/api/ps` name+digest, unload, `/api/ps` absence. A resident digest mismatch after preload refuses before the token. A mismatch after the token refuses the proof. Load without an output token is not PASS.

F. Provider fit verdict vs qualification outcome
`ProviderFitState` is `FIT | NO_FIT | UNRESOLVED`. Explicit scheduler no-fit is `NO_FIT`. Preload plus the expected resident name and digest is `FIT`. Host failure, catalog drift, and a missing resident identity before that proof are `UNRESOLVED`. Token failure after fit stays `FIT` with overall `FAIL_MODEL`. Cleanup failure after fit stays `FIT` and the returned outcome is not a clean PASS. Comparison uses the fit verdict, not `QualificationOutcome`.

G. Full-remaining-SAFE qualification admission
`plan.qualification_probe` version 1 no longer accepts caller memory bytes. `admit_probe` computes remaining SAFE host bytes and remaining SAFE accelerator bytes from active holds on the same ledger, and the reservation stores those exact counts. Storage stays zero. Non-positive or unresolved SAFE refuses.

H. Shared ResourceManager reservation path/native regression
Deployment admission and probe admission both call `_place` for fit and reservation create. Deployment still reserves the plan's requested bytes. A normal plan with a mismatched revision still fails `QUALIFICATION_REQUIRED`. A native `probe=True` plan still succeeds when prior coverage is short. `execution_authorized` still requires a `DeploymentConfiguration` and does not accept the qualification hold.

I. Shadow authorized-envelope semantics
Order is admission, then shadow, then provider. Shadow compares its estimate with the admitted reservation's accelerator bytes, not the device's total SAFE bytes. An active deployment hold therefore shrinks the shadow ceiling. Shadow still cannot veto the provider. `refine_vllm` is not imported. Host-byte requirement stays unresolved because Ollama does not expose a public host estimate.

J. Cleanup/reservation-release invariant
Unload runs in case orchestration. The hold is released only after unload succeeds and `/api/ps` no longer shows the expected name and digest. Unload API failure keeps the hold and returns `cleanup_reconcile_required`. Unload success while `/api/ps` still shows the model also keeps the hold. Neither result is a clean PASS.

K. Durable comparison event/journal evidence
`model.qualification.compared` is an operational `EventRecord` whose payload is `model.qualification_comparison` version 1. Tests append it through `JsonlJournal` and read it back. A journal `PersistenceError` is `journal_append_failed` and does not change provider fit or the qualification outcome.

L. Comparative classification examples
Shadow FIT + provider FIT -> `AGREE_FIT`, including when the later token proof fails.
Shadow NO_FIT + provider FIT -> `MACHI_FALSE_NEGATIVE`, and the provider outcome can still be PASS.
Shadow FIT + provider NO_FIT -> `MACHI_FALSE_POSITIVE`, and Ollama still refuses.
Provider `UNRESOLVED` (catalog drift, host failure, or missing resident identity) -> `MACHI_UNRESOLVED`.
Shadow `UNRESOLVED` + either provider fit -> `MACHI_UNRESOLVED`.

M. Metrics/provenance changes
The fixture generate result now carries input tokens, and the comparison stores them when present. `size_vram` remains `OBSERVED` from `ollama.api.ps` with semantics `runtime_reported`. A VRAM delta is `DERIVED` and `estimate_vs_runtime_reported` only when both integers exist.

N. Tests/gates
`tests/machi`: 545 passed, including architecture, API-seam, cleanup/reservation, journal round-trip, and native plan/admit regressions.
`ruff check src/machi tests/machi`: pass.
`mypy --strict src/machi`: 169 files, success.

O. Wheel build ID/SHA256
build `0.1.0+4aa21ccabade`
sha256 `65db6874edea6ccce9aafc8455347815fc7bdd073d21c5069707be7a8f211df8`
size `306399`
clean_source `true`

P. Isolated verify_ok
`serve_ok sin_5c22adc1d8920043`
`verify_ok`

Q. Docs/debt changes
`docs/machi/TELEMETRY.md` catalogues `model.qualification.compared` as operational, without prompt, response, path, or user identity.
`docs/machi/ARCHITECTURE.md` names that event.
No new debt. `M-6-OLLAMA-01` remains the later Serve residency boundary. Native qualification schema and AUTO state were not changed.

R. Local/origin equality
`LOCAL 4aa21ccabade398a8f931c5a231baed84bbf45f0`
`ORIGIN 4aa21ccabade398a8f931c5a231baed84bbf45f0`
Recovery `checkpoint/native-vllm-partial-pass-2026-09-24` remains `6e17f4a817d1571e0a708decec405ceda0282c7f`.

S. Exact support claim
A fixture Ollama candidate is re-resolved from `/api/tags`, admitted for the full remaining SAFE envelope, shadow-evaluated against that hold, and qualified by a fake v0.34.3 preload/ps/token/ps/unload sequence. Ollama fit is authoritative. Comparison analytics are journaled. Native Plan, Admit, and Serve behavior is preserved. This is not a physical Ollama qualification.

T. Remaining physical qualification work
A live loopback daemon at the pinned Foundation generation, a real local digest from `/api/tags`, one ResourceManager hold of the remaining SAFE envelope, real preload, `/api/ps` name+digest and `size_vram`, a real output token, unload with absence on `/api/ps`, and the same comparison event from that run. No model download or Chunk 4 was started. `M-5-OLLAMA-03` and `M-6-03` remain open.

U. Final status
STOP — OLLAMA CHUNK 3 CORRECTION COMPLETE. WAIT FOR LEAD REVIEW.

==================== END PASTE BACK — OLLAMA CHUNK 3 CORRECTION ====================
