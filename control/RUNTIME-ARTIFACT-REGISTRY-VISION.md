# Runtime Artifact Registry / Software Supply Chain — Product Vision Decision

**Decision date:** 2026-09-24  
**Status:** ACCEPTED FUTURE PRODUCT CAPABILITY  
**Timing:** after the installation-to-inference spine; may proceed in parallel with Stage 2 lab work; should mature before scaled Stage 3 commercial deployment.

## Product decision

Kultrun should eventually provide a first-class **Runtime Artifact Registry / Software Supply Chain** for software artifacts it is responsible for provisioning.

This is separate from the Model Warehouse.

Examples:
- Machi/Kultrun release artifacts;
- Ollama/vLLM/other runtime binaries;
- managed interpreters;
- approved wheels/packages;
- runtime-owned native libraries;
- helper binaries;
- reproducible environment bundles;
- offline/air-gapped bundles.

## Delivery modes

Artifact recipes should be independent of byte-delivery location and later support:
- Kultrun-hosted mirrored artifacts where redistribution is permitted;
- pinned official upstream sources;
- customer-internal mirrors;
- customer-provided imports;
- offline bundles.

## Required artifact metadata

At minimum:
- stable artifact identity;
- exact version/revision;
- content digest and signature where available;
- source/provenance;
- platform/architecture;
- size metadata where known;
- license/attribution;
- redistribution policy;
- recipe/dependency relationship;
- lifecycle/support state;
- SBOM/supply-chain evidence where practical.

## Security principles

- never execute an unverified download;
- no runtime-time "latest" resolution for a frozen generation;
- stage downloads before use;
- verify digest/signature before execution;
- bounded extraction into positively owned storage;
- reject path traversal and unsafe links/device entries;
- do not mutate active generations in place;
- promote only after verification.

## Current-development constraint

Do **not** build the hosted registry during the Ollama macropath.

Current work should only establish reusable consumer-side contracts:
- exact artifact identity;
- provenance;
- checksums;
- runtime recipe identity;
- owned local staging;
- safe realization;
- verification;
- delivery-source independence where a concrete seam is already needed.

Do not create speculative registry services, package-manager frameworks, or generic dependency graphs merely for future-proofing.

## Canonical vision branch

The accepted documentation change is committed on:

`docs/post-spine-artifact-registry-vision`

It updates:
- `docs/PRODUCT_VISION.md`
- `docs/STRATEGY.md`
- `docs/machi/ROADMAP.md`
- `docs/machi/ARCHITECTURE.md`

The Ollama closeout must reconcile these accepted semantics into its final product branch without discarding Chunk-2 implementation documentation.
