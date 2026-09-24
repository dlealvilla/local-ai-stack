# Ollama Macropath — Chunk 2 Closed

**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Chunk:** 2 of 6 — Runtime Substrate / Foundation  
**Status:** CLOSED / LOCAL-PACKAGE ACCEPTED  
**Accepted source HEAD:** `180a4e898c5fcd46ae54a6d1c8aa8acfe84c66e6`  
**Accepted wheel:** `machi-0.1.0-py3-none-any.whl`  
**Build ID:** `0.1.0+180a4e898c5f`  
**Wheel SHA256:** `535a1b96485b47381ef14a78d2e527d4ef0a470b4e6c60fd13053f79f135e4be`

## Accepted

- `FoundationEngine.OLLAMA` exists as a separate direct/native engine;
- verified-existing and Machi-owned managed-prefix substrate paths exist;
- Ollama v0.34.3 Linux amd64 is frozen by exact version, artifact identity and digest;
- source URL is provenance, not artifact identity;
- no global `/usr` or systemd mutation;
- loopback/private endpoint and cloud-disabled semantics are enforced;
- no model pull/load/inference occurs in Foundation;
- SAFE capacity is explicit and authorizes staging plus peak owned provisioning bytes;
- archive realization uses verified two-pass streaming with bounded secure extraction;
- per-member security limits are distinct from aggregate SAFE capacity;
- immutable owned generations are promoted atomically and parent-directory fsynced;
- registry/index updates are atomic and corrupt state fails closed/requires reconciliation;
- positive ownership is parsed proof, not path/name/string heuristics;
- managed qualification identity is content-oriented and port-independent;
- verified-existing reusable qualification requires strong runtime-closure identity;
- zstd is an explicit provisional prerequisite/provider, with managed-helper debt retained;
- decompressor handling uses a progress/inactivity watchdog rather than a tiny total deadline;
- stderr is concurrently drained and bounded; non-zero exits remain typed failures;
- common Foundation analytics vocabulary remains reusable;
- Core-vs-Commodity, Industry Solution Selection and Product Vision Alignment governance is canonical.

## Gates

- 527 Machi tests passed;
- ruff passed;
- strict mypy passed across 161 files;
- architecture checks passed;
- clean wheel built;
- isolated-wheel verification ended in `verify_ok`;
- local HEAD == origin HEAD.

## Scope not claimed

This closure does **not** claim:
- physical execution of the official 1.4 GB Ollama Linux artifact;
- GPU qualification of the Ollama path;
- model pull, load, residency or inference;
- specialist Ollama model feasibility;
- model qualification;
- ResourceManager-wrapped Ollama deployment;
- AUTO fallback activation;
- commercial/production support.

Open debt remains `M-5-OLLAMA-01` through `M-5-OLLAMA-04`.

## Next chunk

Chunk 3 is Model + Specialist Feasibility Bridge.

It must consume the accepted Foundation generation identity and preserve the
qualification funnel:

```text
Machi model identity
 -> policy / coarse compatibility
 -> qualification queue
 -> qualification reservation
 -> Ollama model binding / digest
 -> specialist feasibility evidence
 -> bounded acquisition/load probe where authorized
 -> real qualification evidence
 -> DeployableModels
```

Chunk 3 has **not** started by this closeout.
