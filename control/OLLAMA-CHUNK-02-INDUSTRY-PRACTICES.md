# Ollama Chunk 2 — Industry Practice Basis

**Status:** BINDING ENGINEERING BASIS FOR FINAL HARDENING  
**Date:** 2026-09-24

The final Chunk-2 fixes are common software packaging/update problems. Prefer established patterns over bespoke Machi mechanisms.

## 1. Provisioning storage: explicit persistent + transient accounting

Industry analogue:
- Kubernetes accounts scratch, image, writable-layer and log use as local ephemeral storage with explicit requests/limits.
- TUF target metadata carries expected size as well as hashes to bound downloads.

Machi application:
- Capacity authority must cover all Machi-owned bytes created by provisioning, including transient staging.
- Do not use an arbitrary fallback capacity ceiling as authorization.
- Prefer a pipeline that avoids duplicate temporary representations.
- For Ollama, keep one verified compressed artifact plus one staged generation; avoid materializing a complete decompressed tar.
- Preflight the verified archive in a first streaming pass, then extract in a second streaming pass.
- Admission formula must conservatively cover staged compressed bytes + extracted generation bytes + bounded metadata/transaction overhead.
- Missing SAFE capacity is unresolved/refused, not guessed.

## 2. Immutable generation + atomic activation/index update

Industry analogue:
- OSTree uses parallel immutable deployments identified by checksums.
- Nix uses unique immutable store objects and changes references/profiles rather than mutating packages in place.
- POSIX same-filesystem rename/replace is atomic; durable commit patterns fsync files and containing directories.

Machi application:
- Build a new owned generation in staging.
- Verify it completely.
- Promote with same-filesystem atomic rename into a unique immutable generation path.
- Never mutate an active verified generation in place.
- Update the registry/index using write-temp -> fsync -> atomic replace -> fsync parent directory.
- If generation promotion succeeds but registry activation fails, do not pretend success and do not risk deleting unrelated/pre-existing data.
- Prefer a typed PROMOTED_UNREGISTERED / RECONCILE_REQUIRED state for the newly promoted positively owned generation, which later reconciliation/GC can resolve. This mirrors immutable-store practice better than destructive rollback.
- The registry is an index/reference, not the identity or source of truth for generation bytes.

## 3. Content-addressed runtime identity; operational location is not identity

Industry analogue:
- OCI/Docker distinguish mutable tags from immutable content digests.
- Nix store identities are derived from immutable inputs/content rather than runtime location.
- SLSA provenance records where/how an artifact was produced without making a download URL its identity.

Machi application:
- Qualification identity includes only material execution inputs:
  exact runtime/version/content identity, execution-environment fingerprint, material provider/runtime mode and security class.
- Ephemeral loopback port is operational evidence and must not invalidate qualification.
- Source URL is provenance, not identity.
- Managed runtime identity may rely on the frozen archive digest because the archive defines the full managed bundle.
- Verified-existing identity must use immutable observed runtime evidence. Prefer a trustworthy package/bundle identity or a content digest over the relevant runtime closure. If only the executable can be hashed, record the evidence strength honestly and do not claim it covers mutable sidecar libraries.
- If a sufficient immutable runtime identity cannot be established, verified-existing may be observed/usable only under a non-reusable qualification state; do not mint reusable qualification evidence.

## 4. Secure archive extraction

Industry analogue:
- GNU tar recommends extracting untrusted archives only into separate empty protected directories.
- Python tarfile recommends prior inspection, data-oriented extraction filters, rejecting risky features, and enforcing limits on count, size, names, CPU/disk.

Machi application:
- Extract only into a fresh positively owned empty staging directory.
- Regular files/directories only unless a reviewed runtime genuinely requires more.
- Refuse absolute paths, traversal, symlink/hardlink entries, devices/FIFOs/specials.
- Enforce destination containment after path resolution.
- Bound file count, member-name length, individual file size where useful, declared aggregate bytes, and actual written bytes.
- Do not restore arbitrary ownership/setuid/setgid/special permission metadata.
- Verify required runtime layout after extraction before promotion.
- Failed extraction never mutates an active generation.

## 5. Helper/decompressor prerequisites: explicit adapter, eventually managed artifact

Industry analogue:
- Package systems declare dependencies rather than discovering them midway through mutation.
- Homebrew bottles encode platform compatibility, checksum and relocation requirements.
- Supply-chain systems distinguish the artifact from its delivery/tooling provenance.

Machi application:
- No hidden `zstd` shell assumption.
- Represent decompression behind the smallest provider/port needed by the Ollama provisioner.
- Initial adapter may use an existing system `zstd`, but must preflight path/capability/version and return a typed prerequisite state if unavailable.
- Do not invoke apt/dnf or ask the customer to manually install it as the final product model.
- Future preferred path is a Kultrun-managed, pinned helper artifact delivered through the Runtime Artifact Registry/managed-prerequisite supply chain.
- Do not build that registry in Chunk 2.

## 6. Future artifact registry security baseline

When the Runtime Artifact Registry is built after the spine:
- use content-addressed immutable artifacts;
- use TUF-style signed target metadata containing hashes/sizes and rollback/freeze protections rather than inventing an updater security model;
- retain SLSA/in-toto-style provenance/attestations where available;
- keep artifact identity independent of mirror/delivery endpoint;
- permit mirrors/offline bundles to deliver the same verified target.

Chunk 2 only prepares the consumer-side contracts; it does not implement TUF, SLSA services, or a hosted registry.

## Cursor confirmation rule

Before code changes, Cursor must compare these patterns against actual repository contracts and state:

- ALIGNS — apply the industry pattern;
- ALIGNS_WITH_BOUNDED_ADAPTATION — explain the small Machi-specific adaptation, then apply it;
- CONFLICTS_WITH_ACCEPTED_ARCHITECTURE — STOP and publish DECISION_REQUIRED with exact conflict.

Do not reject an industry pattern merely because current code differs from it. Current code is what is being hardened.
