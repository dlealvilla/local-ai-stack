# CURRENT LEAD DEVELOPER INSTRUCTION

**Instruction ID:** `MACHI-OLLAMA-CHUNK-02-CLOSEOUT-002`  
**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Chunk:** 2 of 6 — CLOSEOUT  
**Mode:** LOCAL FIX / HARDEN / PACKAGE / PUSH / PUBLISH  
**Physical server:** NO  
**Model weights:** FORBIDDEN  
**Model load/inference:** FORBIDDEN  
**Chunk 3:** FORBIDDEN  
**Integration branch:** `automation/ollama-macropath`  
**Recovery checkpoint:** `checkpoint/native-vllm-partial-pass-2026-09-24`

Read first:
- `control/OLLAMA-MACROPATH-PROGRAM.md`
- `control/OLLAMA-CHUNK-01-DECISION.md`
- `control/RUNTIME-ARTIFACT-REGISTRY-VISION.md`
- canonical docs and current local Chunk-2 implementation

# 0. Why this closeout exists

The reported Chunk-2 implementation is directionally accepted but is NOT closed because:
1. the implementation commit reported as `073c5daf0baf319abc8b4d0f3f415999aeadf67f` was local-only and is not reviewable from canonical GitHub;
2. isolated-wheel verification failed because `tools/prove_serve_fixture.py` is stale against the accepted qualification requirement;
3. the managed Ollama archive path reportedly inflates the ~1.4 GB compressed archive fully into memory and the real `.tar.zst` path was not exercised.

Close these issues without widening scope.

# 1. Preserve accepted Chunk-2 architecture

Keep:
- `FoundationEngine.OLLAMA`;
- verified-existing local Ollama;
- Machi-owned managed-prefix Ollama;
- Linux/NVIDIA first;
- native process;
- loopback/private endpoint;
- cloud disabled;
- no `/usr` mutation;
- no global systemd;
- no model pull/load/inference;
- AUTO fallback disabled;
- explicit local-API bypass debt;
- Foundation readiness distinct from deployment readiness.

Do not redesign Foundation unless a real invariant is broken.

# 2. Fix the isolated-wheel verifier

The current Serve proof fixture predates the accepted rule that normal Serve requires qualification coverage.

Update the verifier/fixture to construct valid current qualification coverage:
- current `QualificationEvidence` PASS;
- current deployable membership/qualification identity as required by the real Plan/Serve contracts;
- Plan/configuration cites the valid qualification;
- Admit and Serve use that valid current identity.

Do NOT:
- remove the qualification requirement;
- special-case the verifier in product code;
- weaken Plan/Serve invariants;
- bypass ResourceManager.

Then rebuild and rerun isolated-wheel verification until the final output contains `verify_ok`.

# 3. Harden managed archive realization

Do not hold the fully decompressed Ollama tar archive in RAM.

Required transaction shape:

```text
approved compressed artifact
  -> Machi-owned download/staging file
  -> verify expected SHA-256
  -> read-only archive/preflight inspection where practical
  -> verify SAFE storage/extraction bound
  -> bounded streaming decompression + extraction
  -> owned temporary installation generation
  -> verify expected layout/binary/version
  -> promote verified generation
```

For this chunk the acquisition input may still be a local archive path supplied to the provisioner. Do not build a network downloader unless one already exists and is genuinely required.

Security requirements:
- verify compressed artifact digest before execution;
- no execution from partial/unverified bytes;
- reject absolute paths;
- reject `..` traversal;
- reject symlink/hardlink escape;
- reject unsafe special/device members;
- enforce cumulative declared/actual extraction bound;
- write only under positively owned staging/state;
- clean only positively owned failed staging;
- never mutate a verified active generation in place;
- checksum mismatch must not produce an installation.

Prefer a two-pass local archive approach where practical:
1. preflight member metadata/declared sizes;
2. stream extraction with the same bounds enforced again.

# 4. Exercise the real compressed path

Add a small synthetic `.tar.zst` fixture that goes through the same zstd decompression/extraction implementation used by the managed provider.

Test at least:
- valid archive PASS;
- checksum mismatch;
- traversal path;
- unsafe link;
- extraction-size bound;
- partial/staging cleanup;
- active generation untouched on failure.

The fixture should be small. Do NOT download the 1.4 GB official archive merely for this local unit test.

# 5. Future Runtime Artifact Registry compatibility — NO REGISTRY BUILD NOW

The accepted future vision is:
- after the inference spine, build a Runtime Artifact Registry / software supply chain;
- keep it separate from the Model Warehouse;
- later support mirrored artifacts, pinned upstream, customer mirrors/imports, and offline bundles through the same artifact/recipe identities.

Current Chunk-2 code should therefore preserve this consumer-side invariant:

```text
runtime recipe / artifact identity
        !=
one hard-coded byte-delivery location
```

Minimum expected behavior:
- recipe identifies exact version/revision and checksum/provenance;
- realization can consume an already-present verified artifact/local archive input;
- source URL may be provenance, but must not become the identity;
- installation/verification logic must not require GitHub specifically;
- local staging and realization remain usable later with a vendor registry, customer mirror or offline bundle.

Do NOT create:
- a hosted registry service;
- a generic package manager;
- a broad artifact-catalog domain;
- speculative dependency resolution;
- new networking infrastructure.

Only add a small source/acquisition port if the current implementation is otherwise concretely coupled to GitHub and a seam is required now.

# 6. Canonical product documentation

The accepted future vision is committed on:

`docs/post-spine-artifact-registry-vision`

It updates:
- `docs/PRODUCT_VISION.md`
- `docs/STRATEGY.md`
- `docs/machi/ROADMAP.md`
- `docs/machi/ARCHITECTURE.md`

Before final push, reconcile those accepted semantics into the final
`automation/ollama-macropath` branch.

Because Chunk 2 already modified some of the same docs, do not blindly overwrite them.
Merge/reconcile the meaning:
- post-spine Runtime Artifact Registry;
- separate from Model Warehouse;
- artifact identity independent of delivery provider;
- build after spine, may run in parallel with Stage 2 lab;
- mature before scaled Stage 3 / strong air-gap productization;
- hosted registry remains outside Machi core.

Also keep the truthful Chunk-2 Ollama status/debt/doc changes already made locally.

# 7. Generic Foundation wording audit

Now that `FoundationEngine.OLLAMA` exists, review generic contracts/comments/docstrings for stale statements that say generic Foundation concepts are inherently vLLM-only.

Correct wording only when the concept is truly generic.

Do not generalize vLLM-specific contracts such as Python/vLLM recipes merely for cosmetic symmetry.

Keep Ollama-specific fields in Ollama contracts/adapters.

# 8. Analytics audit

Confirm that `foundation.metric` is a reusable normalized metric representation rather than a one-off ontology that would force Model/Serve to invent incompatible availability semantics later.

It is acceptable for Foundation to own Foundation-level observations. The shared vocabulary should remain:
- metric name;
- value;
- unit;
- availability;
- source/provenance;
- privacy.

Do not build the full analytics warehouse.

# 9. Local gates

Required:
- targeted Ollama/Foundation tests;
- new compressed-archive tests;
- updated isolated Serve fixture tests;
- full `tests/machi`;
- architecture boundary tests;
- ruff;
- strict scoped mypy;
- clean wheel build;
- isolated-wheel verification ending in `verify_ok`.

Max three same-root fix iterations.

# 10. Source-control closure

After all gates pass:
- create a clean final implementation commit;
- push exact final HEAD to `origin/automation/ollama-macropath`;
- verify local HEAD == origin HEAD;
- working tree clean except explicitly excluded local notes;
- do not move the recovery checkpoint.

The canonical remote source must be reviewable before this closeout can PASS.

# 11. PASS criteria

`OLLAMA_CHUNK_2_CLOSEOUT_PASS` requires:
- all accepted Chunk-2 functionality remains;
- no model weights/load/inference/server;
- stable Ollama version/checksum provenance retained;
- no unbounded full-tar-in-RAM decompression;
- real `.tar.zst` code path locally tested;
- stale Serve verifier fixed without weakening product rules;
- all local/package gates green including `verify_ok`;
- future artifact-registry vision reconciled into canonical product docs;
- artifact identity not coupled to one delivery source;
- exact final source pushed to origin;
- origin HEAD equality proven.

# 12. Mandatory paste-back

Bound exactly:

==================== BEGIN PASTE BACK — OLLAMA CHUNK 2 CLOSEOUT ====================

A. STATUS  
B. Starting local/origin SHA and recovery checkpoint  
C. Changes since prior Chunk-2 paste-back  
D. Serve verifier qualification fix  
E. Archive realization design before/after  
F. Streaming/preflight security controls  
G. Real `.tar.zst` fixture evidence  
H. Artifact identity vs delivery-source audit  
I. Future Runtime Artifact Registry compatibility result  
J. Canonical Product Vision/Strategy/Roadmap/Architecture reconciliation  
K. Foundation generic-wording audit  
L. Analytics vocabulary audit  
M. Targeted/full test results  
N. Ruff/mypy/architecture results  
O. Clean wheel build ID + SHA256  
P. Isolated-wheel `verify_ok` evidence  
Q. Debts retained/added/closed  
R. Exact support claim after closeout  
S. Final local HEAD  
T. Final origin HEAD and equality proof  
U. Working-tree state  
V. Exact proposed Chunk-3 scope  
W. Final status

End with exactly:

`STOP — OLLAMA CHUNK 2 CLOSEOUT COMPLETE. WAIT FOR LEAD REVIEW.`

or a typed DECISION_REQUIRED/FAIL equivalent.

==================== END PASTE BACK — OLLAMA CHUNK 2 CLOSEOUT ====================

Publish through the existing GitHub handoff.

Do not begin Chunk 3.
