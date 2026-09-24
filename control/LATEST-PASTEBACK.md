SERVER NEEDED NEXT: NO

Instruction: MACHI-OLLAMA-CHUNK-02-CLOSEOUT-002
Program: MACHI-OLLAMA-MACROPATH-001
Chunk: 2 of 6 — CLOSEOUT

STATUS=OLLAMA_CHUNK_2_CLOSEOUT_PASS

TL;DR

- The review gaps are closed: the source is on GitHub, isolated verification prints verify_ok, and archive realization streams to disk.
- The frozen pin is still Ollama 0.34.3, sha256 e83a089fd0cd2f79ee2933cca2085846a2065f497adbc6467c402177c68423f9.
- A recipe checksum identifies the artifact. The source URL is provenance and is not required to realize a local archive.
- The hosted Runtime Artifact Registry is documented as post-spine work and was not built.
- AUTO fallback, model pull, load, and inference were not started.

ARCHITECTURE MAP

```text
local archive path
  -> owned staging file
  -> SHA-256
  -> streamed decompress
  -> preflight, then bounded extract
  -> promote a new generation
```

WHAT JUST HAPPENED

Closeout commit 45b1734936164393c7434ddd09640c7c05e5fb7b was pushed to origin/automation/ollama-macropath. The recovery checkpoint was not moved.

WHERE WE ARE

Chunk 2 can be reviewed from GitHub. Chunk 3 has not started.

WHAT'S NEXT

Lead review before any model-binding work.

HANDOFF

```text
PAST     local-only substrate at 073c5da
PRESENT  pushed closeout with verify_ok
NEXT     lead review
```

==================== BEGIN PASTE BACK — OLLAMA CHUNK 2 CLOSEOUT ====================

## A. STATUS

STATUS=OLLAMA_CHUNK_2_CLOSEOUT_PASS

No physical server was created. No model weights were downloaded. No model was loaded. No inference was run. Chunk 3 was not started. AUTO fallback stays inactive.

## B. Starting local/origin SHA and recovery checkpoint

- Local start: 073c5daf0baf319abc8b4d0f3f415999aeadf67f on automation/ollama-macropath
- Origin start: 6e17f4a817d1571e0a708decec405ceda0282c7f
- Recovery checkpoint origin/checkpoint/native-vllm-partial-pass-2026-09-24 remains 6e17f4a817d1571e0a708decec405ceda0282c7f

## C. Changes since prior Chunk-2 paste-back

- Serve fixture now carries real qualification coverage.
- Managed archive realization stages, hashes, streams, bounds, and promotes.
- A small .tar.zst fixture exercises that path.
- Runtime environment id ignores the delivery URL.
- Foundation metrics live in a reusable contract module.
- Product vision, strategy, roadmap, and architecture include the accepted post-spine registry wording without dropping the Chunk-2 Ollama status.

## D. Serve verifier qualification fix

tools/prove_serve_fixture.py builds a QualificationEvidence PASS whose id comes from qualification_identity, plus a DeployableModels member for mdl_serve at rev-serve. It refuses to continue unless covers() is true for the fixture context and concurrency. The plan settings include that qualification_id. Admit and Serve then use that same configuration. The product check that a plan without qualification_id is refused was not removed, and Serve was not given a verifier exception.

The fixture completed with serve_ok sin_5c22adc1d8920043 inside the isolated wheel run.

## E. Archive realization design before/after

Before: install accepted bytes, and zstd decompression returned the whole tar in memory through the process stdout buffer.

After:

```text
caller-supplied local archive
  -> copy into foundation/staging/<attempt>/artifact.bin while hashing
  -> refuse on checksum mismatch before any install directory is created
  -> stream zstd -d into payload.tar, or copy a plain tar
  -> preflight member metadata and declared sizes
  -> stream extraction under the same byte bound
  -> write the owned generation only inside staging
  -> rename that generation into foundation/environments/<id>
```

A verified generation that already exists is reused or refused from its manifest. It is not extracted over. Failed staging is removed only when it carries the Machi ownership marker and sits under foundation/staging.

## F. Streaming/preflight security controls

- Digest is checked on the staged file before decompression or execution.
- Absolute members and .. are refused.
- Symlinks and hardlinks are refused.
- Members that are neither files nor directories are refused.
- Declared size and bytes actually written are both capped.
- The caller-supplied safe_bytes value is that cap. When it is absent, an 8 GiB safety ceiling applies. That ceiling does not authorize capacity.
- Cleanup deletes only a marked staging directory.
- Checksum mismatch leaves no environment directory.

## G. Real .tar.zst fixture evidence

tests/machi/test_ollama_foundation.py compresses a small layout archive with the zstd tool and passes that file through OllamaRuntime.install. The same test covers checksum mismatch, a ../ member, a symlink member, a 1-byte extraction bound, staging removal, and an already promoted generation whose marker file is unchanged. The official 1.4 GB archive was not downloaded.

## H. Artifact identity vs delivery-source audit

runtime_environment_id hashes recipe id, version, and sha256. It does not hash source_url or checksum_url. A test realizes a recipe whose source URL is offline-bundle:customer and gets the same environment id as the upstream URL. install reads a local path. It does not fetch a URL.

## I. Future Runtime Artifact Registry compatibility result

The hosted registry was not built. No package manager, catalog domain, or network downloader was added. The consumer-side split is in place: recipe identity and checksum are independent of the byte-delivery location, and realization consumes an already-present local archive. A later mirror, customer import, or offline bundle can supply that file without changing the generation id.

## J. Canonical Product Vision/Strategy/Roadmap/Architecture reconciliation

Reconciled from docs/post-spine-artifact-registry-vision into this branch without reverting Chunk-2 text:

- docs/PRODUCT_VISION.md section 5.12.1: registry after the spine, separate from the Model Warehouse, three delivery modes, identity independent of location, hosted service outside the current spine.
- docs/STRATEGY.md: post-spine workstream, parallel with Stage 2, gate before scaled Stage 3, not a dependency of current Ollama work.
- docs/machi/ARCHITECTURE.md: hosted registry is out of core; core may consume identities, recipes, provenance, and local staging.
- docs/machi/ROADMAP.md: registry row is DEFER. The Ollama row still says the substrate is local and AUTO fallback is not implemented.
- docs/machi/M5.md: checksum and version are the artifact identity; the source URL is provenance.

## K. Foundation generic-wording audit

FoundationSelection's description now says family plus engine. The vLLM settings, recipe, and resolver text stay vLLM-specific. RuntimeCapability version 1 field meanings still say vLLM; that remains M-5-OLLAMA-02. Ollama recipe, cloud mode, and endpoint stay on the Ollama contracts.

## L. Analytics vocabulary audit

foundation.metric and foundation.metric_set moved to src/machi/foundation/metrics.py. Each metric still has name, value, unit, availability, source, and privacy. Availability still distinguishes observed, derived, estimated, hidden_internal, not_exposed, not_applicable, unsupported, and unresolved. No analytics warehouse was added.

## M. Targeted/full test results

- tests/machi/test_ollama_foundation.py: 11 passed, including the zstd cases and the daemon restart fixture
- tools/prove_serve_fixture.py: serve_ok
- tests/machi: exit 0, 508 tests

## N. Ruff/mypy/architecture results

- ruff check src/machi tests/machi tools/prove_serve_fixture.py: passed
- mypy --strict src/machi: 160 files, no issues
- Architecture checks ran inside tests/machi and passed

## O. Clean wheel build ID + SHA256

Built from clean commit 45b1734936164393c7434ddd09640c7c05e5fb7b.

- artifact: dist/machi/machi-0.1.0-py3-none-any.whl
- build id: 0.1.0+45b173493616
- clean_source: true
- size: 284675
- sha256: d82d6196b27b3f8820c303cc22518dd1368e4e93c916b4c8c85c7588f72b729b

## P. Isolated-wheel verify_ok evidence

.venv/bin/python tools/verify_machi.py dist/machi/machi-0.1.0-py3-none-any.whl exited 0. The final lines were:

```text
serve_ok sin_5c22adc1d8920043
verify_ok
```

## Q. Debts retained/added/closed

Retained and still open:

- M-5-OLLAMA-01 local API bypass
- M-5-OLLAMA-02 RuntimeCapability v1 wording
- M-5-OLLAMA-03 official Linux binary not executed from the owned prefix

No debt was closed. The synthetic zstd test does not execute the published 1.4 GB archive, so M-5-OLLAMA-03 stays open. No new debt entry was required.

## R. Exact support claim after closeout

This closeout is a local package pass for the Ollama foundation substrate. Verified-existing and the owned prefix are implemented. Archive realization streams and enforces checksum, path, link, and size limits. Isolated wheel verification passed. This is not a GPU qualification, not an execution of the official Linux archive, not model inference, and not AUTO fallback.

## S. Final local HEAD

45b1734936164393c7434ddd09640c7c05e5fb7b on automation/ollama-macropath

## T. Final origin HEAD and equality proof

After git push and git fetch:

- LOCAL=45b1734936164393c7434ddd09640c7c05e5fb7b
- ORIGIN=45b1734936164393c7434ddd09640c7c05e5fb7b

origin/automation/ollama-macropath moved 6e17f4a..45b1734. The recovery checkpoint was not updated.

## U. Working-tree state

Clean except untracked docs/machi/proposals/, which was not committed.

## V. Exact proposed Chunk-3 scope

Do not start it from this result. If accepted, Chunk 3 binds a Machi model identity to an Ollama digest, applies coarse filters before any pull, and records specialist fit evidence only under a future qualification reservation. Normal DeployableModels membership stays after that evidence. No ordinary deployment load, no inference path, and no AUTO activation.

## W. Final status

OLLAMA_CHUNK_2_CLOSEOUT_PASS

NO_MODEL_WEIGHTS_DOWNLOADED
NO_MODEL_LOADED
NO_INFERENCE_RUN
NO_SERVER_CREATED
AUTO_FALLBACK_NOT_ACTIVATED
CHUNK_3_NOT_STARTED

STOP — OLLAMA CHUNK 2 CLOSEOUT COMPLETE. WAIT FOR LEAD REVIEW.

==================== END PASTE BACK — OLLAMA CHUNK 2 CLOSEOUT ====================
