SERVER NEEDED NEXT: NO

Instruction: MACHI-OLLAMA-CHUNK-02-FREEZE-007
Program: MACHI-OLLAMA-MACROPATH-001
Chunk: 2 of 6 — FINAL FREEZE PATCH

STATUS=OLLAMA_CHUNK_2_FREEZE_PASS

TL;DR

- Staging is refused before any owned directory exists when SAFE cannot hold the frozen artifact, or the observed length does not match the recipe.
- The copy itself stops if the source grows past that authorized length, and the staged byte count must still match the recipe before the digest is accepted.
- Parent-directory fsync now happens immediately after promotion and before the registry update.
- Invalid UTF-8 is corrupt registry state. A hung decompressor is killed on a deadline. Reconciliation ownership is parsed JSON, not a substring.

ARCHITECTURE MAP

```text
SAFE covers frozen artifact length
  -> bounded copy and digest
  -> extract and promote
  -> fsync parent directory
  -> registry update
```

WHAT JUST HAPPENED

The freeze patch is on origin/automation/ollama-macropath at 919ab7e547967d6f552507fea617646410b3f0bd. The recovery checkpoint was not moved.

WHERE WE ARE

The accepted Chunk-2 architecture is unchanged. These are the last freeze blockers from the review.

WHAT'S NEXT

Lead review. Chunk 3 has not started.

HANDOFF

```text
PAST     correction 31dca11
PRESENT  freeze 919ab7e
NEXT     lead review
```

==================== BEGIN PASTE BACK — OLLAMA CHUNK 2 FREEZE ====================

## A. STATUS

STATUS=OLLAMA_CHUNK_2_FREEZE_PASS

No physical server was created. No model was pulled, loaded, or used for inference. AUTO fallback stayed inactive. Chunk 3 was not started.

## B. Starting/final SHA

- Start: 31dca110271805545cc2ba60c9095c25f357b27d
- Final local and origin: 919ab7e547967d6f552507fea617646410b3f0bd
- Recovery checkpoint remains 6e17f4a817d1571e0a708decec405ceda0282c7f

## C. Pre-stage SAFE authorization and bounded copy

Before any staging directory or marker is created, the source length is compared with the recipe artifact size and with SAFE capacity. If SAFE is smaller than that frozen length, the result is insufficient_capacity and no staging path is created. During the copy, bytes past the authorized length abort the copy. A test seam that delivers extra bytes after a correctly sized stat is refused with "archive copy exceeded the authorized length", and no environment is created.

## D. Artifact length + digest verification

A source whose stat length differs from recipe.artifact_bytes is refused before staging, even when the digest of the real bytes would otherwise match. After the copy, the staged byte count must equal that frozen length, and the SHA-256 must still match. The stat result is not the only check.

## E. Promotion durability ordering

After generation.replace, the parent directory is fsynced, and only then does the registry transaction start. A recorded seam shows the order rename, parent_fsync, registry. If that parent fsync fails, the result is promoted_unregistered, not a successful install, and the generation is not in the registry.

## F. Invalid-UTF8 registry behavior

Invalid UTF-8 is caught with invalid JSON and wrong-shaped JSON. Provisioning returns verification_failed and reconcile_required with the reason "environment index is corrupt". The registry bytes are unchanged. inspect_environment_index reports corrupt without raising.

## G. Deadlock-safe decompressor timeout behavior

A deadline timer kills the child even while tar parsing is blocked on its stdout. Stderr is drained on a side thread with a bounded join, so an open stderr pipe cannot postpone the wait. Timeout and non-zero exit are both package-install failures. The successful zstd path and the non-zero diagnostic path still pass. A child that writes a tar header and then sleeps with stderr open fails with "timed out" in well under three seconds.

## H. Positive ownership-proof behavior

unregistered_owned_generations now requires parsed JSON with owner machi, owned true, and environment_id equal to the directory name. A spoofed note containing the old substring, a wrong owner, a mismatched id, and malformed JSON are not treated as owned. No cleanup was added.

## I. Tests/gates

- tests/machi/test_ollama_foundation.py passed, including the freeze cases
- tests/machi: exit 0, 525 tests
- ruff check src/machi tests/machi: passed
- mypy --strict src/machi: 161 files, no issues
- Architecture checks passed inside the suite

## J. Wheel build ID/SHA256

- artifact: dist/machi/machi-0.1.0-py3-none-any.whl
- build id: 0.1.0+919ab7e54796
- commit: 919ab7e547967d6f552507fea617646410b3f0bd
- clean_source: true
- size: 289800
- sha256: e827153c52ef3914f968bdc84193fb2993bba47cd111ded4c85404e3b016e1b1

## K. Isolated verify_ok

tools/verify_machi.py exited 0. The final lines were:

```text
serve_ok sin_5c22adc1d8920043
verify_ok
```

## L. Local/origin equality

After push and fetch:

- LOCAL=919ab7e547967d6f552507fea617646410b3f0bd
- ORIGIN=919ab7e547967d6f552507fea617646410b3f0bd

The push was 31dca11..919ab7e. The working tree is clean except untracked docs/machi/proposals/.

## M. Exact Chunk-2 support claim

This is the local freeze patch on the accepted Ollama foundation substrate. Staging is authorized before it is created. Promotion is fsynced before the index update. Corrupt indexes, including invalid UTF-8, stay untouched. This is not a GPU qualification, not model inference, and not AUTO fallback.

## N. Final status

OLLAMA_CHUNK_2_FREEZE_PASS

NO_MODEL_WEIGHTS_DOWNLOADED
NO_MODEL_LOADED
NO_INFERENCE_RUN
NO_SERVER_CREATED
AUTO_FALLBACK_NOT_ACTIVATED
CHUNK_3_NOT_STARTED

STOP — OLLAMA CHUNK 2 FREEZE PATCH COMPLETE. WAIT FOR LEAD REVIEW.

==================== END PASTE BACK — OLLAMA CHUNK 2 FREEZE ====================
