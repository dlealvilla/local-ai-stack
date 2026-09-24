# Ollama Bundle 06 — Identity Closure + Recovery + AUTO Fallback Control

**Status:** APPROVED EXECUTION PACKAGE  
**Starting source:** `ebfabe56b2ae09b916e5e70ea4d2b1c028f48af6`  
**Prior review:** `control/OLLAMA-BUNDLE-05-LEAD-REVIEW.md`

## Product purpose

This package has two connected product goals.

First, **close the trust chain** for the Ollama serving path. Bundle 05 proved
the desired lifecycle physically, but the source still needs to prove that the
actual verified Ollama Foundation being used is the same Foundation the Plan
cited, and Machi must remain able to read historical persisted evidence after
schema evolution.

Second, begin the next Stage-1 capability: **bounded AUTO runtime fallback**.
The product should be able to prefer the primary native/vLLM path when it is
healthy/supported and choose Ollama only when the primary Foundation is
unavailable according to approved policy. Fallback must remain an explainable
new deployment path, not a hidden retry inside Serve.

The Company Brain / administrator promise this advances is:

> Kultrun can explain exactly which runtime/model path it authorized, why that
> path was selected, which verified runtime generation actually served the
> request, and whether a fallback was selected—without corrupting model
> identity, resource accounting, or historical evidence.

## Functional outcome

If this package succeeds:

1. Provider Serve refuses a runtime generation/environment that does not match
   the provider Plan.
2. Machi distinguishes the managed runtime realization (`renv`) from the
   verified hardware/environment-bound Foundation generation (`fgen`) in
   product evidence.
3. Historical Ollama qualification v1 records remain readable and migrate
   truthfully; they remain unable to authorize a context-bound provider Plan.
4. Kernel has a bounded real schema-evolution mechanism and K-03 is retired only
   if its stated migration obligations are genuinely satisfied.
5. A failed/lagging provider STOP can be reconciled safely without releasing
   resources or pretending success.
6. The corrected provider Serve identity chain is re-proven on real NVIDIA
   hardware.
7. Locally, AUTO policy prefers healthy/supported native/vLLM, falls back to
   independently valid Ollama only when the primary Foundation is
   unsupported/unhealthy by approved policy, and never silently switches when
   the administrator explicitly chose VLLM or OLLAMA.
8. An AUTO fallback creates a fresh valid downstream deployment path; it does
   not reuse a stale native model selection, Plan, ResourceReservation, or
   ServingInstance.

## Maximum support claim after this package

Physical:
- exact corrected Ollama Plan/Admit/Serve identity chain on the tested host.

Local/control-plane:
- bounded AUTO macropath selection/orchestration semantics.

Not yet claimed:
- production-grade automatic live failover after an arbitrary request failure;
- physical AUTO fallback across all NVIDIA hardware;
- cross-catalog automatic model equivalence;
- multi-model scheduling;
- fleet failover;
- fallback during active customer traffic.
