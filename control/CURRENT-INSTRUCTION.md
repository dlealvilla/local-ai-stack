# CURRENT LEAD DEVELOPER INSTRUCTION

**Instruction ID:** `MACHI-OLLAMA-CHUNK-02-FINAL-005`  
**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Chunk:** 2 of 6 — INDUSTRY-PATTERN FINAL HARDENING  
**Starting canonical HEAD:** `45b1734936164393c7434ddd09640c7c05e5fb7b`  
**Physical server:** NO  
**Model pull/load/inference:** FORBIDDEN  
**Chunk 3:** FORBIDDEN

Read first:
- `control/CORE-VS-COMMODITY-POLICY.md`
- `control/OLLAMA-CHUNK-02-INDUSTRY-PRACTICES.md`
- `control/OLLAMA-CHUNK-02-LEAD-REVIEW-2.md`
- `control/OLLAMA-CHUNK-01-DECISION.md`
- `control/RUNTIME-ARTIFACT-REGISTRY-VISION.md`
- current repository source/tests/docs

# 0. Governing solution-selection rule

Apply `control/CORE-VS-COMMODITY-POLICY.md` before implementation.

For each problem in this instruction:
1. classify it as Ring A commodity, Ring B enabling infrastructure, or Ring C product core;
2. research established standards/libraries/projects where relevant;
3. if one clear industry fit exists with no material product consequence, record `NO_SOLUTION_DECISION_REQUIRED` and use/adapt it;
4. if 2+ materially credible alternatives remain, or the choice changes a core contract/authority boundary/strategic dependency, STOP with `DECISION_REQUIRED_INDUSTRY_SOLUTION_SELECTION` and present the decision package required by the policy.

Do not silently choose between competing credible solutions merely to complete this chunk.

# 0A. Mandatory Product Vision Alignment

For every material standard/library/project/provider/build-vs-integrate option
considered under this instruction, add a Product Vision Alignment assessment:
- `ALIGNED`
- `ALIGNED_WITH_CONDITIONS`
- `MISALIGNED`

Explicitly test the option against the current Kultrun constitution, including
self-hosting, privacy/local content, offline/air-gap, replaceability,
provider-neutral core contracts, owned authority boundaries, safety/evidence,
administrator simplicity, enterprise governance, commercial/licensing direction,
and long-term Company Brain evolution.

A technically good but structurally MISALIGNED option is not an automatic
implementation. If adopting it would require changing the Product Vision, STOP
with `DECISION_REQUIRED_PRODUCT_VISION_ALIGNMENT`.

# 1. Confirm industry-practice fit BEFORE editing

For each section 1–5 of `OLLAMA-CHUNK-02-INDUSTRY-PRACTICES.md`, inspect actual repository contracts and report one of:

- `ALIGNS`
- `ALIGNS_WITH_BOUNDED_ADAPTATION`
- `CONFLICTS_WITH_ACCEPTED_ARCHITECTURE`

If any item genuinely conflicts with accepted product architecture, publish a bounded DECISION_REQUIRED paste-back and STOP before implementation.

Otherwise implement the industry pattern. Current code differing from the pattern is not a conflict.

# 2. Provisioning storage — use explicit transient accounting

Adopt the established resource-management pattern:
- no arbitrary `safe_bytes=None -> 8 GiB` authorization;
- missing SAFE capacity refuses/unresolved;
- all Machi-owned staging bytes count;
- avoid full decompressed tar materialization.

Preferred transaction:
1. validate an explicit SAFE bound exists and can at least cover the known compressed artifact;
2. copy/hash the caller-supplied artifact into owned staging;
3. verify exact digest before trusting its contents;
4. first pass: stream-decompress the verified staged artifact directly into tar parsing for security/preflight and declared extracted-size computation;
5. compute conservative peak owned requirement:
   `staged_compressed_bytes + extracted_generation_bytes + bounded_metadata_transaction_overhead`;
6. refuse before extraction if SAFE does not cover that peak;
7. second pass: stream-decompress the same verified staged artifact directly into bounded extraction;
8. verify actual written bytes never exceed the admitted peak/bounds.

Do not create `payload.tar`.

For a plain tar fixture, apply the same two-pass semantics without decompression.

# 3. Immutable generation and atomic index update

Use immutable-generation practice:
- build/verify in a fresh owned stage;
- generation-local manifest first;
- fsync material files/manifest as appropriate;
- same-filesystem atomic rename to unique final generation;
- fsync the containing generation directory;
- central registry/index update uses temp file -> fsync -> `os.replace` -> fsync parent directory;
- never mutate active generations in place.

If promotion succeeds but registry/index update fails:
- return typed `PROMOTED_UNREGISTERED` / `RECONCILE_REQUIRED` semantics;
- leave the positively owned immutable generation intact for bounded reconciliation/GC;
- do not report successful installation;
- do not delete a prior generation;
- do not leave an untyped silent mismatch.

Add failure-injection tests for:
- promotion failure;
- registry temp/write/fsync/replace failure;
- promoted-unregistered reconciliation or truthful detection.

# 4. Qualification-stable content identity

Refactor Ollama qualification-material identity to follow content-addressed practice.

Managed prefix:
- exact pinned recipe/version;
- archive digest/content identity;
- execution-environment fingerprint;
- material provider/security class;
- no endpoint port.

Verified existing:
- do not use version text alone;
- establish the strongest immutable runtime identity available without host mutation;
- inspect whether executable + runtime library tree/package identity is required to represent the actual Ollama runtime closure;
- hash/capture that immutable evidence in a bounded way;
- record evidence strength/provenance;
- if only partial identity can be established, the substrate may be observed but must not create reusable qualification evidence.

Same material runtime on two different loopback ports must retain qualification identity.

Changed runtime bytes at the same reported version must change qualification identity.

Operational endpoint remains raw/operational evidence.

# 5. Secure extraction — align with standard archive guidance

Keep the existing strict extraction philosophy and complete standard protections:
- fresh empty owned directory;
- regular files/directories only;
- reject absolute/traversal/link/special members;
- resolved destination containment;
- explicit member-count limit;
- explicit member-name/path-length limit;
- aggregate declared-size and actual-write limits;
- bounded individual-member size if useful;
- no arbitrary uid/gid restoration;
- no setuid/setgid/device semantics;
- required Ollama layout verification before promotion.

Use Python tar extraction-filter primitives only if they improve the implementation without losing explicit byte accounting; a stricter custom allowlist is acceptable and likely appropriate.

# 6. Explicit decompressor provider

Do not let `subprocess ["zstd", ...]` be an undeclared host assumption.

Introduce only the smallest concrete seam needed, e.g. an Ollama/archive decompressor port or provider:
- `SystemZstdDecompressor` may be the first adapter;
- preflight executable presence;
- observe version/capability;
- invoke without shell;
- typed prerequisite refusal if missing/incompatible;
- include decompressor evidence in provisioning provenance, not model qualification identity unless evidence proves it materially changes realized bytes.

Do not apt/dnf install it.

Record debt that final plug-and-play productization should deliver/manage a pinned helper via the future Runtime Artifact Registry or replace the helper with an approved in-process implementation.

# 7. Future registry baseline — documentation only

Reconcile into the accepted Runtime Artifact Registry vision that the future hosted registry/update plane should adopt rather than reinvent:
- TUF-style signed target metadata, target hashes/sizes, freshness/rollback protections;
- content-addressed immutable artifacts;
- SLSA/in-toto-compatible provenance/attestations where available;
- mirror/delivery endpoint independent of target identity.

Do not implement TUF/SLSA/registry services now.

# 7A. Reconcile governance documentation into the product branch

The accepted governance wording currently lives on:
`docs/core-vs-commodity-decision-policy`.

Before final push, reconcile that branch's accepted changes into
`automation/ollama-macropath` without overwriting newer Ollama-specific
documentation.

Required canonical documents:
- `docs/PRODUCT_VISION.md`
- `docs/STRATEGY.md`
- `docs/machi/ARCHITECTURE.md`
- `docs/machi/ROADMAP.md`

The final product branch must contain:
- Reuse the Industry; Own the Product;
- the three-ring Core-vs-Commodity classification;
- Industry Solution Selection Gate;
- Provider Selection Gate relationship;
- mandatory Product Vision Alignment;
- ALIGNED / ALIGNED_WITH_CONDITIONS / MISALIGNED semantics.

Do not merge the side branch mechanically if it would revert newer product
truth. Reconcile meaning, then test the resulting branch.

# 8. Preserve accepted scope

No change to:
- Ollama v0.34.3 frozen stable artifact;
- verified-existing + managed-prefix strategy;
- loopback/cloud-off;
- no /usr/global systemd mutation;
- AUTO disabled;
- no model weights/load/inference;
- no physical server;
- normalized analytics seam.

# 9. Gates

Run:
- targeted Ollama/Foundation tests;
- peak transient-storage tests;
- two-pass streaming archive tests;
- archive limits/security tests;
- transaction/failure-injection tests;
- identity tests;
- decompressor-provider tests;
- full tests/machi;
- architecture tests;
- ruff;
- strict mypy;
- clean wheel;
- isolated-wheel verification ending `verify_ok`.

Then push exact clean HEAD to `origin/automation/ollama-macropath` and prove local == origin.

# 10. Mandatory paste-back

==================== BEGIN PASTE BACK — OLLAMA CHUNK 2 INDUSTRY FINAL ====================

A. STATUS  
B. Industry-practice fit confirmation table (sections 1–5), including Ring classification and Product Vision Alignment for each material option  
C. Starting/final SHA  
D. Peak transient-storage accounting and formula  
E. Two-pass streaming implementation  
F. Secure extraction controls/limits  
G. Immutable-generation/atomic-index transaction  
H. Crash/failure-injection behavior  
I. Managed qualification identity  
J. Verified-existing runtime-closure identity/evidence strength  
K. Decompressor provider/prerequisite behavior  
L. Future TUF/SLSA registry-documentation update + canonical Core-vs-Commodity/Product-Vision governance reconciliation  
M. Files changed  
N. Tests/gates  
O. Wheel build ID/SHA256  
P. Isolated `verify_ok`  
Q. Debts  
R. Exact support claim  
S. Local/origin equality  
T. Proposed Chunk-3 start  
U. Final status

End:
`STOP — OLLAMA CHUNK 2 INDUSTRY FINAL COMPLETE. WAIT FOR LEAD REVIEW.`

or typed DECISION_REQUIRED/FAIL.

==================== END PASTE BACK — OLLAMA CHUNK 2 INDUSTRY FINAL ====================

Do not begin Chunk 3.
