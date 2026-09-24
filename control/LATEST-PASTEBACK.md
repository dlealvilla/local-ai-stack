SERVER NEEDED NEXT: NO

Instruction: MACHI-OLLAMA-CHUNK-02-FINAL-005
Program: MACHI-OLLAMA-MACROPATH-001
Chunk: 2 of 6 — INDUSTRY-PATTERN FINAL HARDENING

STATUS=OLLAMA_CHUNK_2_INDUSTRY_FINAL_PASS

TL;DR

- No solution decision was required. Each hardening item had one accepted industry fit, and none was misaligned with the Product Vision.
- Provisioning now refuses when SAFE bytes are missing, and the peak covers the staged archive plus the extracted generation.
- Qualification identity no longer includes the loopback port. A partial executable hash cannot mint reusable qualification evidence.
- Isolated verification printed verify_ok. Origin matches local HEAD a71c78f46fc70265167d915a367e43105441b6c4.

ARCHITECTURE MAP

```text
explicit SAFE bytes
  -> stage and hash the local archive
  -> stream pass 1: preflight
  -> stream pass 2: extract
  -> fsync and rename the generation
  -> atomic registry update
```

WHAT JUST HAPPENED

The industry-pattern hardening is on origin/automation/ollama-macropath. The recovery checkpoint was not moved. Chunk 3 did not start.

WHERE WE ARE

Chunk 2 foundation identity and storage accounting are stable enough for a later qualification chunk to consume.

WHAT'S NEXT

Lead review.

HANDOFF

```text
PAST     closeout 45b1734
PRESENT  industry final a71c78f
NEXT     lead review before Chunk 3
```

==================== BEGIN PASTE BACK — OLLAMA CHUNK 2 INDUSTRY FINAL ====================

## A. STATUS

STATUS=OLLAMA_CHUNK_2_INDUSTRY_FINAL_PASS

NO_SOLUTION_DECISION_REQUIRED

No physical server was created. No model was pulled, loaded, or used for inference. AUTO fallback stayed inactive. Chunk 3 was not started.

## B. Industry-practice fit confirmation table

| Section | Fit | Ring | Product Vision Alignment | Decision |
|---|---|---|---|---|
| 1. Explicit persistent and transient storage | ALIGNS_WITH_BOUNDED_ADAPTATION | A commodity | ALIGNED | NO_SOLUTION_DECISION_REQUIRED |
| 2. Immutable generation and atomic index | ALIGNS | A commodity | ALIGNED | NO_SOLUTION_DECISION_REQUIRED |
| 3. Content-addressed qualification identity | ALIGNS_WITH_BOUNDED_ADAPTATION | C product core, mechanics only | ALIGNED | NO_SOLUTION_DECISION_REQUIRED |
| 4. Secure archive extraction | ALIGNS | A commodity | ALIGNED | NO_SOLUTION_DECISION_REQUIRED |
| 5. Explicit decompressor provider | ALIGNS_WITH_BOUNDED_ADAPTATION | A commodity, later Ring B delivery | ALIGNED_WITH_CONDITIONS | NO_SOLUTION_DECISION_REQUIRED |

Section 1 uses Machi SAFE capacity as the authority. Unknown capacity refuses. That is the bounded adaptation of the Kubernetes/TUF size pattern.

Section 3 keeps qualification meaning in Machi. The port is operational evidence. The identity formula was specified by the binding industry note, so it was not a new product choice.

Section 4 keeps a custom member allowlist. Python's tar extraction filter would not preserve the explicit declared-versus-written byte account this chunk requires. The instruction already treats that stricter allowlist as the appropriate fit.

Section 5 uses SystemZstdDecompressor as the first adapter, which the instruction named. It is aligned only while the host tool is preflighted, refused when missing, and recorded as debt until a pinned helper or an in-process decoder replaces it. An apt/dnf install and a silent in-process library choice were not taken. Both would have been a different product dependency.

TUF and SLSA were recorded as the future registry baseline only. They were not implemented. That documentation choice is ALIGNED_WITH_CONDITIONS: the standards fit provenance and rollback protection, and building them now would skip the spine.

No option was MISALIGNED. No Product Vision change is required.

## C. Starting/final SHA

- Start: 45b1734936164393c7434ddd09640c7c05e5fb7b
- Final local and origin: a71c78f46fc70265167d915a367e43105441b6c4
- Recovery checkpoint remains 6e17f4a817d1571e0a708decec405ceda0282c7f

## D. Peak transient-storage accounting and formula

Missing safe_bytes refuses with insufficient_capacity. There is no 8 GiB fallback.

```text
peak = staged_compressed_bytes
     + declared_extracted_bytes
     + 65536 metadata overhead
```

The overhead covers the cloud config, generation manifest, and registry transaction. Provisioning refuses before extraction when peak exceeds the supplied SAFE bound. After extraction, staged bytes plus the written generation must still fit that bound.

## E. Two-pass streaming implementation

Pass 1 stream-decompresses the verified staged artifact, or rereads a plain tar, and inspects members and declared sizes. Pass 2 opens that same staged artifact again and extracts. No payload.tar is written. A counting zstd provider observed two opens on the synthetic .tar.zst fixture.

## F. Secure extraction controls/limits

Extraction starts in a fresh owned directory. Only regular files and directories are accepted. Absolute paths, .., symlinks, hardlinks, and special members are refused. Destinations are resolved and must stay inside the prefix. Limits are 10000 members, 240-character names, and 2 GiB for one member, plus the SAFE aggregate. File modes are 0644, or 0755 for bin/ollama. Setuid, setgid, and ownership restoration are not applied. The bin/ollama and lib/ollama layout is required before promotion.

## G. Immutable-generation/atomic-index transaction

The generation manifest is written inside staging. Files and the generation directory are fsynced. Promotion is a same-filesystem rename into a new environment id. The registry is then written to a temp file, fsynced, replaced, and the parent directory is fsynced. An existing verified generation is not modified in place.

## H. Crash/failure-injection behavior

Promotion failure removes only the marked staging directory and does not create an environment. Registry temp, write, fsync, and replace failures return promoted_unregistered and reconcile_required. The new owned generation remains. unregistered_owned_generations reports it. A previously promoted generation is left intact.

## I. Managed qualification identity

The generation id hashes recipe id, provider mode, version, archive digest, identity strength archive, execution-environment fingerprint, and the security class loopback_cloud_disabled. It does not hash the port or the source URL. qualification_reusable is true for that archive identity.

## J. Verified-existing runtime-closure identity/evidence strength

When bin/ollama and an adjacent lib/ollama tree of regular files can be hashed, strength is runtime_closure and qualification_reusable is true. A lone executable is partial_executable and is not reusable qualification evidence. A missing file is absent and is not reusable. The executable hash is not stored as the archive digest. Two loopback ports for the same closure keep one generation id. Changing library bytes changes the digest.

## K. Decompressor provider/prerequisite behavior

SystemZstdDecompressor preflights zstd --version without a shell. A missing or unusable tool returns prerequisite_blocked. The tool name and version are manifest provenance, not qualification identity. Plain tar does not require zstd. Nothing is installed with a package manager.

## L. Future TUF/SLSA registry-documentation update and governance reconciliation

Product vision section 5.12.1 now says the future registry should use TUF-style signed target metadata, content-addressed artifacts, and SLSA or in-toto provenance where published. Mirrors do not become identity.

The accepted governance text from docs/core-vs-commodity-decision-policy is now in this branch:

- Product vision 5.2.1: Reuse the Industry; Own the Product, three rings, Product Vision Alignment, and the Industry Solution Selection Gate
- Strategy: Build versus integrate
- Architecture 4.1: the same gates, including the Provider Selection Gate relationship
- Roadmap: research before invention

Newer Ollama status text was kept.

## M. Files changed

- src/machi/adapters/foundation/ollama_archive.py
- src/machi/adapters/foundation/ollama_runtime.py
- src/machi/foundation/ollama.py
- src/machi/foundation/contracts.py
- tests/machi/test_ollama_foundation.py
- tests/machi/golden/schema_fingerprint.json
- docs/PRODUCT_VISION.md
- docs/STRATEGY.md
- docs/machi/ARCHITECTURE.md
- docs/machi/ROADMAP.md
- docs/machi/M5.md
- docs/DEBT.md

## N. Tests/gates

- tests/machi/test_ollama_foundation.py passed, including peak, two-pass, security, transaction, identity, and decompressor cases
- tests/machi: exit 0, 514 tests
- ruff check src/machi tests/machi: passed
- mypy --strict src/machi: 161 files, no issues
- Architecture checks passed inside the suite

## O. Wheel build ID/SHA256

- artifact: dist/machi/machi-0.1.0-py3-none-any.whl
- build id: 0.1.0+a71c78f46fc7
- commit: a71c78f46fc70265167d915a367e43105441b6c4
- clean_source: true
- size: 287989
- sha256: d3a0a5a756ff2d8f8f7b070467c9e6fa3d2f1764721d36e0d8548ff49bbc2b84

## P. Isolated verify_ok

tools/verify_machi.py exited 0. The final lines were:

```text
serve_ok sin_5c22adc1d8920043
verify_ok
```

## Q. Debts

Still open: M-5-OLLAMA-01 local API bypass, M-5-OLLAMA-02 capability wording, M-5-OLLAMA-03 official Linux binary not executed.

Added: M-5-OLLAMA-04. The system zstd helper is not yet a pinned Machi artifact. It authorizes nothing.

## R. Exact support claim

This is a local package hardening of the Ollama foundation substrate. SAFE capacity must be explicit. Qualification identity is content-addressed and port-independent. Partial verified-existing identity is not reusable qualification evidence. This is not a GPU qualification, not an execution of the official 1.4 GB archive, and not inference.

## S. Local/origin equality

After push and fetch:

- LOCAL=a71c78f46fc70265167d915a367e43105441b6c4
- ORIGIN=a71c78f46fc70265167d915a367e43105441b6c4

The push was 45b1734..a71c78f. The working tree is clean except untracked docs/machi/proposals/.

## T. Proposed Chunk-3 start

Do not start it from this result. If accepted, Chunk 3 binds a Machi model identity to an Ollama digest, applies coarse filters before pull, and records specialist evidence only under a qualification reservation. It must consume this generation id and must not treat a partial executable hash as reusable coverage.

## U. Final status

OLLAMA_CHUNK_2_INDUSTRY_FINAL_PASS

NO_MODEL_WEIGHTS_DOWNLOADED
NO_MODEL_LOADED
NO_INFERENCE_RUN
NO_SERVER_CREATED
AUTO_FALLBACK_NOT_ACTIVATED
CHUNK_3_NOT_STARTED

STOP — OLLAMA CHUNK 2 INDUSTRY FINAL COMPLETE. WAIT FOR LEAD REVIEW.

==================== END PASTE BACK — OLLAMA CHUNK 2 INDUSTRY FINAL ====================
