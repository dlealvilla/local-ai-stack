# CURRENT LEAD DEVELOPER INSTRUCTION

**Instruction ID:** `MACHI-OLLAMA-CHUNK-03-CORRECTION-003`  
**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Chunk:** 3 of 6 — DUAL QUALIFIER LOCAL CORRECTION  
**Starting HEAD:** `da54773ab34b8d4c159fd9427519577319b25821`  
**Server:** NO  
**Real model download/load/inference:** FORBIDDEN  
**Chunk 4:** FORBIDDEN

Read:
- `control/OLLAMA-CHUNK-03-LOCAL-LEAD-REVIEW.md`
- `control/OLLAMA-CHUNK-03-DUAL-QUALIFIER-DECISION.md`
- exact Ollama v0.34.3 public API/source
- current native Plan/Admit/Serve + Journal contracts

This is a bounded correctness correction. Preserve the accepted dual-evaluator
architecture.

# 1. Correct the v0.34.3 public API seam

Remove digest from `ShownModel`.

Catalog identity:
- `/api/tags` returns display name + immutable digest;
- candidate id derives from digest;
- `/api/show` provides metadata only.

Before preload, re-list/re-resolve the candidate display name:
- the same display name must still map to the expected digest;
- absent or changed mapping -> typed `catalog_identity_changed` refusal;
- no provider load/generate may occur after that refusal.

Tests must model tag drift using `/api/tags`, not fake `/api/show` digest.

# 2. Split preload from real token generation

Extend the bounded public adapter seam with separate fixture operations:
- `preload(name, ...)`: represents empty `POST /api/generate`;
- `generate_probe(name, ...)`: represents the real small inference;
- `running_models()`;
- `unload(name)`.

Required sequence:
1. resolve tag -> digest;
2. preload;
3. `/api/ps` requires **display name + expected digest**;
4. real token probe;
5. `/api/ps` again requires display name + expected digest;
6. cleanup.

Tests:
- pre-load resident digest mismatch refuses before real token;
- post-token digest/name mismatch refuses proof;
- readiness/load without token is not PASS.

# 3. Separate specialist fit verdict from overall qualification outcome

Add a small typed fit verdict, e.g.
`ProviderFitState.FIT | NO_FIT | UNRESOLVED`.

Semantics:
- explicit Ollama load/scheduler no-fit -> NO_FIT;
- successful preload + expected resident name/digest -> FIT;
- host failure before fit resolution -> UNRESOLVED;
- catalog identity drift -> UNRESOLVED;
- token-proof failure after successful fit -> FIT but overall qualification FAIL_MODEL;
- cleanup failure after successful fit/token -> FIT but overall case is not clean PASS.

Comparison classification uses provider fit verdict only.

Examples:
- shadow FIT + provider FIT -> AGREE_FIT even if later token proof fails; the
  qualification outcome separately records token failure;
- shadow NO_FIT + provider FIT -> MACHI_FALSE_NEGATIVE;
- shadow FIT + provider NO_FIT -> MACHI_FALSE_POSITIVE;
- provider UNRESOLVED -> MACHI_UNRESOLVED.

Do not infer provider NO_FIT from arbitrary `FAIL_MODEL`.

# 4. Make qualification admission authorize full remaining SAFE

Remove arbitrary caller-selected qualification memory bytes from the ordinary
case orchestration.

Under the ResourceManager lock:
- calculate currently active host-memory holds;
- calculate active holds for the selected accelerator;
- derive remaining SAFE host bytes and remaining SAFE accelerator bytes;
- qualification probe reservation must hold those exact remaining bytes;
- if either is unresolved/non-positive, refuse;
- existing deployment/probe holds continue to count from the same ledger.

Keep storage request zero for this local-existing-model qualification path.
Model pull/acquisition is separate.

The public probe contract may represent the intent/provider/candidate and the
materialized reservation may hold the computed bytes. Choose the smallest
backward-compatible implementation.

Refactor duplicated `_admit` / `_admit_probe` fit-and-create logic into one
private reservation path where practical. Public deployment behavior must not
change.

Regression tests:
- caller cannot under-reserve a qualification case;
- active deployment holds reduce the qualification reservation;
- qualification hold blocks later admissions from the remaining SAFE pool;
- release restores capacity;
- native Admit/Serve behavior unchanged.

# 5. Run shadow against the admitted authorization envelope

Order:
`catalog candidate -> qualification admission -> shadow evaluation -> provider`.

Shadow uses the exact qualification reservation accelerator/host authorization,
not total physical SAFE capacity.

Shadow still cannot veto provider execution.

No vLLM-specific refinement may enter the Ollama shadow path.

# 6. Cleanup gates reservation release

Move cleanup responsibility to case orchestration if needed.

After the qualification attempt:
- request unload;
- inspect `/api/ps`;
- require the qualified display name + digest to be absent;
- only then release ResourceManager reservation.

If unload fails or expected residency remains:
- reservation stays RESERVED;
- case returns typed `cleanup_reconcile_required` / host-failure status;
- comparative evidence may still be recorded;
- the qualification must not be returned as a clean deployable PASS.

Add tests for:
- successful unload -> hold released;
- unload API failure -> hold retained;
- unload says success but /api/ps still shows expected model -> hold retained.

# 7. Persist comparative analytics

Add a Block-6 operational EventRecord for the comparison, e.g.
`model.qualification.compared`.

Use existing Journal port / JsonlJournal in tests.

Requirements:
- payload is the versioned QualificationComparison;
- privacy OPERATIONAL;
- no prompt/response/model-content/path/user identity;
- append/read round-trip proves durability;
- journal failure is reported separately and does not rewrite the Ollama
  specialist fit verdict;
- update TELEMETRY.md event catalogue and semantics.

If useful, return both in-memory comparison and journaled event identity.

# 8. Metrics

Add provider input-token count when exposed by the fixture/public result so the
comparison schema can exercise both input and output tokens.

Preserve:
- `size_vram` = runtime-reported;
- no external peak claim;
- availability/provenance on normalized figures.

# 9. Gates

Run:
- targeted Chunk-3 tests;
- exact API-seam tests;
- cleanup/reservation tests;
- Journal round-trip tests;
- full `tests/machi`;
- architecture checks;
- ruff;
- strict mypy;
- clean wheel;
- isolated wheel verification ending `verify_ok`.

Push exact clean HEAD to `origin/automation/ollama-macropath`.
Prove local == origin.

No physical server/model work. Do not begin Chunk 4.

# 10. Paste-back

==================== BEGIN PASTE BACK — OLLAMA CHUNK 3 CORRECTION ====================

A. STATUS  
B. Starting/final SHA  
C. Exact v0.34.3 API seam correction  
D. Catalog identity drift handling  
E. Preload -> ps -> token -> ps identity proof  
F. Provider fit verdict vs qualification outcome  
G. Full-remaining-SAFE qualification admission  
H. Shared ResourceManager reservation path/native regression  
I. Shadow authorized-envelope semantics  
J. Cleanup/reservation-release invariant  
K. Durable comparison event/journal evidence  
L. Comparative classification examples  
M. Metrics/provenance changes  
N. Tests/gates  
O. Wheel build ID/SHA256  
P. Isolated verify_ok  
Q. Docs/debt changes  
R. Local/origin equality  
S. Exact support claim  
T. Remaining physical qualification work  
U. Final status

End exactly:
`STOP — OLLAMA CHUNK 3 CORRECTION COMPLETE. WAIT FOR LEAD REVIEW.`

or typed FAIL / DECISION_REQUIRED.

==================== END PASTE BACK — OLLAMA CHUNK 3 CORRECTION ====================

Do not begin Chunk 4.
