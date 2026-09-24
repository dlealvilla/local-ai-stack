# Ollama Chunk 2 — Lead Final Review

**Reviewed HEAD:** `a71c78f46fc70265167d915a367e43105441b6c4`  
**Disposition:** CORRECTION REQUIRED BEFORE CLOSURE  
**Scope:** surgical correctness only; architecture accepted.

## Accepted

- Core-vs-Commodity and Product Vision Alignment governance is canonical.
- Industry-practice fit assessment is accepted.
- Explicit SAFE capacity is required; no arbitrary 8 GiB authorization remains.
- Two-pass compressed archive flow removes full decompressed-tar materialization.
- Immutable generation / promoted-unregistered reconciliation model is accepted.
- Qualification identity is port-independent and content-oriented.
- Partial verified-existing identity is non-reusable.
- zstd is explicit and typed as a provisional prerequisite.
- Full suite, packaging and isolated `verify_ok` passed.
- No physical server/model/inference/AUTO work occurred.

## Blocking correctness defect

In `ollama_archive._preflight`, aggregate declared bytes are compared to
`_MAX_MEMBER = 2 GiB`:

`if count > _MAX_MEMBERS or declared > _MAX_MEMBER`

But `_MAX_MEMBER` is also the per-file limit enforced by `_reject_member`.
The paste-back and accepted design say aggregate extracted size is governed by
explicit SAFE capacity, not by the single-member ceiling.

This can reject a valid runtime archive whose total extracted payload exceeds
2 GiB even when no individual member exceeds 2 GiB and SAFE capacity is
sufficient. The current small fixtures do not exercise this case.

Fix:
- keep a separate per-member ceiling if justified;
- do not reuse it as aggregate archive authority;
- preflight aggregate against the actual remaining SAFE provisioning allowance:
  staged compressed bytes + declared extracted bytes + generated metadata +
  registry transaction temp bytes;
- avoid allocating multi-GiB test data; factor the accounting/member validation
  so synthetic TarInfo/metadata fixtures can prove aggregate > 2 GiB is allowed
  when SAFE covers it and refused only when SAFE does not.

## Bounded robustness corrections in the same patch

1. **Decompressor exit status**
   - `_close_tar` currently waits for zstd but does not require a zero exit code.
   - A non-zero decompressor result must be a typed provisioning failure even
     if some bytes were emitted.
   - capture only bounded diagnostic stderr; do not leak arbitrary output.

2. **Registry corruption / reconciliation**
   - `_read_registry` currently lets malformed JSON raise outside the typed
     Foundation failure model.
   - malformed/invalid registry state must return a typed
     `RECONCILE_REQUIRED` / verification refusal and must not be silently
     treated as an empty registry.
   - `unregistered_owned_generations` must remain usable or fail in a typed
     way when registry state is corrupt.

3. **Metadata peak truth**
   - the fixed 64 KiB overhead may remain only for bounded internally generated
     manifest/config metadata whose maximum is actually bounded by contracts.
   - the projected registry temp payload must be counted separately from that
     fixed overhead, because registry size is not currently capped at 64 KiB.
   - SAFE capacity must cover the additional transaction bytes that Machi will
     create at peak.

## Closure

No new provider, library, architecture, product, or solution-selection decision
is expected. If implementation reveals one, trigger the existing decision gate.

After this patch, rerun all Chunk-2 gates and stop. Do not start Chunk 3.
