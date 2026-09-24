# Ollama Bundle 07 — NVIDIA Closure + Physical AUTO Evidence

**Status:** APPROVED EXECUTION PACKAGE  
**Starting source:** `92555da8e3465cd1596098eb33579d31e1a12ae6`  
**Prior review:** `control/OLLAMA-BUNDLE-06-LEAD-REVIEW.md`  
**Closure scope:** `control/OLLAMA-NVIDIA-CLOSURE-AMD-OPTIONAL.md`

## Product purpose

This package should finish the bounded Stage-1 Ollama macropath for NVIDIA if
the evidence supports doing so.

The product question is no longer "can Ollama run?"

That is already proven.

The remaining questions are:

1. Can Machi preserve trustworthy schema/evidence history across upgrades?
2. Can an administrator trust AUTO runtime selection to cite the real
   Foundation observations it used?
3. Can we physically show that healthy native/vLLM remains primary while an
   independently valid Ollama path is available?
4. Can we exercise a truthful fallback-selection path without hidden Serve
   retry, stale downstream state, or catalog translation?
5. Does the Ollama path work on more than one small positive provider model?
6. Do we have a meaningful negative/exclusion case?
7. Can we state the exact NVIDIA support boundary and close this macropath
   without waiting for scarce AMD infrastructure?

The intended product outcome is an explainable, bounded dual-macropath Stage-1
spine:

```text
AUTO
  -> observe real Foundation states
  -> prefer healthy/supported native vLLM
  -> if primary unavailable by policy:
       invalidate downstream
       select valid Ollama Foundation
       use Ollama catalog
       qualify exact provider digest
       new Plan
       new ResourceReservation
       Serve
  -> retain evidence of why and what ran
```

This is selection/fallback orchestration, not live HA.
