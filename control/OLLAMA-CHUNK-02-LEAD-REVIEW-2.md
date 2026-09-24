# Ollama Chunk 2 — Lead Review 2

**Reviewed HEAD:** `45b1734936164393c7434ddd09640c7c05e5fb7b`  
**Decision:** NOT CLOSED — FINAL BOUNDED HARDENING REQUIRED

## Accepted

- source is canonical on `origin/automation/ollama-macropath`;
- isolated wheel verification now reaches `verify_ok`;
- managed-prefix realization no longer buffers the decompressed tar in RAM;
- real synthetic `.tar.zst` path is tested;
- artifact identity is independent of delivery URL;
- future Runtime Artifact Registry vision is correctly reconciled;
- no model pull/load/inference/AUTO fallback occurred.

## Required final corrections

### 1. SAFE storage must cover peak provisioning footprint

Current `safe_bytes` bounds declared/extracted payload size, but provisioning may simultaneously hold:
- staged compressed artifact;
- materialized decompressed tar;
- extracted generation.

This can exceed SAFE storage even when the final prefix fits.

Foundation provisioning must not authorize from an arbitrary 8 GiB fallback.

Fix so the actual peak temporary + final owned footprint is covered by explicit Capacity authority. Prefer eliminating the decompressed `payload.tar` with a two-pass local stream over the already verified compressed archive:
- pass 1: stream-decompress and preflight tar members/declared sizes;
- pass 2: stream-decompress and extract under the same bound.

If a materialized tar is retained instead, compute and admit the full peak staging footprint truthfully.

No `safe_bytes=None -> 8 GiB` path may authorize provisioning. Missing capacity authority must refuse/UNRESOLVED.

### 2. Promotion and ownership-registry update must be transactional

Current manifest/registry update occurs before final generation rename. If promotion fails after registry update, the registry may cite a generation that does not exist.

Required:
- generation-local manifest may be written in staging;
- promote the positively owned generation;
- atomically update the central environment registry only after promotion;
- if the registry update fails, roll back only the newly promoted positively owned generation or leave a typed reconcile state with proof—do not leave silent registry/filesystem disagreement;
- add failure-injection tests for promotion/registry failure.

### 3. Qualification-stable Foundation identity

Current Ollama Foundation generation includes the exact endpoint/port. Port changes are operational and should not force model requalification.

Separate:
- qualification-material identity: exact runtime/version/artifact identity, execution-environment fingerprint, cloud/local security mode, provider material facts;
- operational endpoint: observed daemon address/port.

Use endpoint **class** (for example local-loopback/private) only if security class is material; do not hash an ephemeral port into qualification identity.

### 4. Verified-existing runtime identity must not be unresolved before qualification

A verified-existing Ollama binary may currently carry `artifact_sha256=unresolved`.

Before this path can produce qualification-reusable Foundation identity:
- hash the observed executable or establish another immutable trusted package identity;
- record it in the generation identity/provenance;
- if immutable runtime identity cannot be established, the substrate may be observed but must not authorize reusable model qualification.

Do not compare the executable hash to the archive hash—they are different concepts. Record the executable/content identity truthfully.

### 5. zstd prerequisite must be truthful

Official Ollama v0.34.3 Linux installation itself requires `zstd` for the `.tar.zst` path.

For this increment:
- explicitly preflight whether the configured decompressor is available;
- missing decompressor must be a typed prerequisite/unavailable refusal, not a mysterious package-install failure;
- add/retain explicit debt that the managed product path still depends on an external decompressor unless/until Kultrun manages that helper through the future artifact/prerequisite supply chain;
- do not ask the customer to install it as the final product experience;
- do not build the Artifact Registry now.

## Closure rule

These are pre-Chunk-3 corrections because Chunk 3 will persist model qualification against Foundation identity and Capacity evidence. Do not build qualification on top of unstable identity or incomplete storage authorization.
