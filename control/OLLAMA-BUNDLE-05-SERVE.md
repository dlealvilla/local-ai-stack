# Ollama Bundle 05 — Context-True Qualification + Authorized Serve

**Status:** APPROVED EXECUTION PACKAGE  
**Starting source:** `ea9cb26a6034eeaca1058d6635ee4008fc833bed`  
**Decision:** `control/OLLAMA-SERVE-AUTH-DECISION.md`

## Product purpose

This package turns the physically proven Ollama qualification path into the
first **normal Machi-authorized Ollama serving deployment**.

The product capability we are trying to create is:

> An administrator/platform can select an already qualified Ollama-owned model,
> create a truthful Machi model-serving plan for that provider model, reserve
> resources through the same global ResourceManager used by native/vLLM, serve
> real inference from the exact expected digest, stop and restart it safely,
> and retain trustworthy proof/analytics without pretending the Ollama model is
> a Machi warehouse artifact.

This is a key Stage-1 exoskeleton milestone: two different runtime/model
ownership paths should now be able to enter the same product control loop.

## Product promise after success

On the exact physically qualified host/model/settings, Kultrun should be able to
truthfully demonstrate:

```text
qualified provider model
 -> provider-owned Machi Plan
 -> global ResourceManager admission
 -> one ResourceReservation
 -> Ollama residency under that authorization
 -> exact digest verified
 -> real inference
 -> exact digest verified again
 -> durable Serve proof/analytics
 -> STOP proves model absent
 -> reservation remains held
 -> restart/re-infer under same valid reservation
 -> STOP
 -> explicit reservation release
```

## What this package is NOT

It does not:
- enable AUTO fallback;
- declare Ollama generally production-qualified;
- merge model catalogs;
- add general training/indexing workload claims;
- add multi-model serving policy;
- expose Ollama publicly off-host;
- solve local malicious-process bypass;
- build UI;
- implement hosted telemetry;
- declare a runtime winner.
