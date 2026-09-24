SERVER NEEDED NEXT: NO

Instruction: MACHI-OLLAMA-CHUNK-02-CORRECTION-006
Program: MACHI-OLLAMA-MACROPATH-001
Chunk: 2 of 6 — SURGICAL CORRECTION

STATUS=OLLAMA_CHUNK_2_CORRECTION_PASS

TL;DR

- Aggregate archive size is no longer judged against the 2 GiB per-member ceiling.
- The SAFE peak now includes the real projected registry temp file, not a 64 KiB guess.
- A decompressor that exits non-zero fails provisioning after the process is reaped.
- A corrupt environment index is a typed reconcile refusal and is not rewritten.

ARCHITECTURE MAP

```text
per-member ceiling
        !=
SAFE peak
  staged archive
  + declared extraction
  + manifest and config budget
  + projected registry temp
```

WHAT JUST HAPPENED

The correction is on origin/automation/ollama-macropath at 31dca110271805545cc2ba60c9095c25f357b27d. The recovery checkpoint was not moved.

WHERE WE ARE

Chunk 2 correctness items from the final review are fixed. Chunk 3 has not started.

WHAT'S NEXT

Lead review.

HANDOFF

```text
PAST     industry final a71c78f
PRESENT  correction 31dca11
NEXT     lead review
```

==================== BEGIN PASTE BACK — OLLAMA CHUNK 2 CORRECTION ====================

## A. STATUS

STATUS=OLLAMA_CHUNK_2_CORRECTION_PASS

No physical server was created. No model was pulled, loaded, or used for inference. AUTO fallback stayed inactive. Chunk 3 was not started. No archive-wide anti-bomb byte ceiling was added.

## B. Starting/final SHA

- Start: a71c78f46fc70265167d915a367e43105441b6c4
- Final local and origin: 31dca110271805545cc2ba60c9095c25f357b27d
- Recovery checkpoint remains 6e17f4a817d1571e0a708decec405ceda0282c7f

## C. Aggregate-vs-member bug before/after

Before, preflight refused when the running sum of member sizes exceeded the 2 GiB per-member ceiling, and it reported that as a member-count error.

After, each regular file is refused only when that file's own size exceeds 2 GiB. Two members that are each legal, but together larger than 2 GiB, are not refused by that ceiling. Their sum is refused only when the SAFE peak does not cover it. The proof uses the accounting helpers with those sizes and does not allocate multi-gigabyte payloads.

## D. Exact peak-storage formula after correction

```text
peak = staged_compressed_bytes
     + aggregate_declared_extraction_bytes
     + generated_metadata_budget
     + projected_registry_temp_bytes
```

generated_metadata_budget is the two cloud-config files plus a 4096-byte manifest budget. The manifest writer refuses if the manifest exceeds that budget. There is no separate archive-wide size ceiling.

## E. Registry transaction byte accounting

projected_registry_temp_bytes is the exact UTF-8 length of the next registry JSON, including the new environment id. That temp file exists beside the current index during the atomic replace, so its full size is in the peak. A test built an index larger than 64 KiB, refused a SAFE value one byte below the peak, left that index unchanged, and accepted the same archive when SAFE equalled the peak.

## F. Decompressor exit-status handling

The zstd child uses a pipe for stderr, not a shell. After the tar stream is closed, the implementation drains stderr, waits, and kills the process on timeout. A non-zero exit is a package-install failure whose reason includes "zstd decompressor exited without success" and a bounded stderr excerpt. A fake decompressor that emitted a complete layout tar and then exited 1 failed provisioning and left no environment.

## G. Corrupt-registry behavior

Malformed JSON and a non-list JSON object both return verification_failed with reconcile_required and the reason "environment index is corrupt". The corrupt bytes are not replaced. An existing owned generation manifest is unchanged. inspect_environment_index reports corrupt without raising. A valid index still lists unregistered owned generations.

## H. Tests/gates

- tests/machi/test_ollama_foundation.py passed, including the four new correction cases
- tests/machi: exit 0, 518 tests
- ruff check src/machi tests/machi: passed
- mypy --strict src/machi: 161 files, no issues
- Architecture checks passed inside the suite

## I. Wheel build ID/SHA256

- artifact: dist/machi/machi-0.1.0-py3-none-any.whl
- build id: 0.1.0+31dca1102718
- commit: 31dca110271805545cc2ba60c9095c25f357b27d
- clean_source: true
- size: 288925
- sha256: a4a754b912668640cdf41704420932d559f8492cb2b71adab510e1d04935f168

## J. Isolated verify_ok

tools/verify_machi.py exited 0. The final lines were:

```text
serve_ok sin_5c22adc1d8920043
verify_ok
```

## K. Debts changed

No debt entry was added or closed. M-5-OLLAMA-01 through M-5-OLLAMA-04 stay open.

## L. Local/origin equality

After push and fetch:

- LOCAL=31dca110271805545cc2ba60c9095c25f357b27d
- ORIGIN=31dca110271805545cc2ba60c9095c25f357b27d

The push was a71c78f..31dca11. The working tree is clean except untracked docs/machi/proposals/.

## M. Exact support claim

This is a local correctness patch on the accepted Ollama foundation substrate. Aggregate archive size is governed by the explicit SAFE peak. A corrupt environment index is refused instead of being treated as empty. This is not a GPU qualification, not model inference, and not AUTO fallback.

## N. Final status

OLLAMA_CHUNK_2_CORRECTION_PASS

NO_MODEL_WEIGHTS_DOWNLOADED
NO_MODEL_LOADED
NO_INFERENCE_RUN
NO_SERVER_CREATED
AUTO_FALLBACK_NOT_ACTIVATED
CHUNK_3_NOT_STARTED

STOP — OLLAMA CHUNK 2 CORRECTION COMPLETE. WAIT FOR LEAD REVIEW.

==================== END PASTE BACK — OLLAMA CHUNK 2 CORRECTION ====================
