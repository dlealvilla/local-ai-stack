# Ollama Bundle 07 — Lead Review / NVIDIA Stage-1 Closure

**Reviewed final source:** `2c12f00286d6e7d6d524baa7a7787099e476bf08`  
**Physical passing source:** `fc216642cd6d3e2f77c8bbaa53f2fe22f6bb658a`  
**Recovery checkpoint:** `checkpoint/ollama-nvidia-stage1-2026-09-24`  
**Disposition:** ACCEPTED — `CLOSED_NVIDIA_STAGE1`

## Product outcome accepted

The Ollama execution macropath is closed for its bounded NVIDIA Stage-1 scope.

Accepted evidence across the campaign now demonstrates:

- managed/verified Ollama Foundation identity;
- separate `renv` runtime artifact identity and `fgen` Foundation generation;
- provider-owned catalog and exact digest identity;
- Ollama-authoritative qualification plus Machi shadow comparison;
- exact context-bound physical qualification;
- provider Plan using truthful provider identity rather than fake ModelArtifact
  fields;
- the same global ResourceManager / ResourceReservation ledger as native;
- generation-bound provider Serve with exact digest proof;
- STOP / reconciliation / explicit release semantics;
- two positive physical Ollama model cases on NVIDIA A40;
- a meaningful qualification-coverage negative case;
- AUTO policy that physically prefers a real READY native/vLLM Foundation;
- a safely induced, product-generated native provisioning failure in an isolated
  Machi-owned root;
- physical AUTO selection of Ollama from that approved unavailable-primary state;
- a fresh Ollama Plan / reservation / Serve chain rather than stale native state;
- durable RuntimeChoice evidence citing the concrete Foundation selections and
  capacity evidence it consumed;
- recoverable schema migration receipts and conservative historical migration;
- privacy-preserving operational evidence;
- exact final branch/checkpoint identity and terminated owned Pod.

## Physical AUTO fallback review

The fallback experiment is accepted.

The primary-unavailable state was not fabricated by manually writing a
SupportState and did not damage the healthy primary environment.

Cursor:
1. proved the normal native root reused a READY generation;
2. created a separate Machi-owned disposable root;
3. invoked the actual product provisioner with a deliberately unavailable
   Machi-managed `uv` path;
4. received a real typed `PROVISIONING_FAILED / PYTHON_PROVISION_FAILED`
   FoundationSelection from product code;
5. preserved the healthy native generation, host driver, GPU and system Python;
6. passed that real Foundation evidence into AUTO;
7. AUTO selected the already-valid Ollama Foundation;
8. the fallback path created a fresh provider Plan and ResourceReservation;
9. real Ollama inference completed and cleanup/release succeeded.

This proves the bounded Stage-1 fallback-selection semantics. It is not a claim
of automatic live failover after a user request fails.

## Migration / K-03 review

The intent -> record -> complete receipt design fixes the Bundle-06 durability
gap without claiming cross-file atomicity.

Accepted properties:
- intent failure leaves the historical record untouched;
- record-rewrite failure leaves a durable open intent;
- completion failure after record rewrite leaves a durable open intent;
- later read converges the record and receipt;
- complete receipt plus historical record fails closed;
- repeated successful reads are idempotent;
- receipt contains no record body/customer content;
- historical schemas remain weaker after migration.

K-03 may remain RETIRED with the historical missed timing explicitly preserved.

## RuntimeChoice v2 review

Accepted.

The persisted decision now identifies the concrete FoundationSelection and
capacity evidence consulted for primary and fallback sides where applicable.

Historical v1 migration uses `not_recorded` / `not_consulted` and does not
manufacture stronger evidence.

The decision remains a policy/evidence record above FoundationSelection. It does
not replace FoundationSelection and does not move fallback into Serve.

## Positive physical matrix

Accepted:
- `smollm2:135m-instruct-q8_0`
- `smollm2:360m-instruct-q8_0`

Both were resolved through the real Ollama catalog, bound to exact digests,
qualified at requested/observed context 2048, admitted through ResourceManager,
served real tokens, and cleaned up.

The second positive case satisfies the Stage-1 requirement for more than one
repeated physical run of the same provider model.

## Negative physical case

Accepted:
- the 360m qualification at context 2048 did not cover a requested context 4096;
- Plan composition refused with `QUALIFICATION_DOES_NOT_COVER`;
- no Serve occurred.

This is a meaningful product-protection negative even though it is not a
provider NO_FIT case.

## Comparative evidence

Accepted only as descriptive evidence, not a performance ranking.

The native evidence and Ollama evidence use different GPU SKUs and different
model representations. Cursor correctly did not average rates or treat Ollama
`size_vram` as an external measured peak.

Later matched-hardware/representation testing remains a separate empirical
program.

## Support-claim refinement

The paste-back wording is slightly broader than the evidence if read as saying
both complete inference paths were proven on the same A40.

The truthful support statement is:

> Across the bounded NVIDIA Stage-1 evidence set, Machi has two working
> execution macropaths: native/vLLM as primary (end-to-end inference previously
> physically proven on the accepted L40S path) and Ollama as a separately
> qualified compatibility/fallback path (end-to-end physically proven on the
> A40). On Bundle 07's A40 specifically, Machi physically proved native/vLLM
> Foundation readiness and AUTO primary selection, plus physical AUTO fallback
> selection into a fresh Ollama Plan -> Admit -> Serve chain when a real
> isolated native provisioning failure was produced.

Do NOT claim native model inference on the Bundle-07 A40.

This wording refinement does not block closure because the Bundle-07 mandatory
criterion was physical healthy-primary AUTO evidence, not a second native
inference acceptance on the same host.

## AMD review and corrected future acceptance model

Bundle 07 did not create an AMD Pod because secure MI300X stock was `NONE`.
That is a valid `NO_STOCK` result and does not block NVIDIA closure.

Important clarification for the future AMD lane:

A prebuilt cloud "ROCm 7 userspace image" is NOT inherently required.

Machi's native AMD architecture already intends to provision its owned managed
ROCm-compatible vLLM/PyTorch userspace generation.

Future AMD preflight must separate:

### Host/provider prerequisites
- supported AMD GPU;
- host kernel/driver/device access sufficient to expose the GPU;
- usable vendor/device inspection path such as amd-smi where required;
- compatible OS/glibc;
- native shared libraries that the pinned Machi runtime recipe genuinely cannot
  provide itself.

### Machi-managed userspace
- managed Python;
- pinned vLLM;
- ROCm-compatible torch/vLLM packages;
- Machi-owned cache/generation;
- runtime verification and Foundation identity.

Therefore:
- "no prebuilt ROCm userspace image" alone is not an AMD support failure;
- when stock is available, prefer testing whether Machi can provision its own
  managed ROCm userspace on a minimally AMD-capable host;
- missing native sonames should be classified empirically as either legitimate
  host prerequisites or dependencies Machi should provision;
- AMD remains an open cross-macropath hardware qualification lane and is not
  part of this NVIDIA closure.

## Remaining boundaries

Still unclaimed/open:
- AMD / ROCm physical support;
- NVIDIA-wide Ollama support;
- automatic live runtime switch after arbitrary inference failure;
- production HA/fleet failover;
- cross-catalog model equivalence;
- concurrent multi-model policy;
- local malicious-process enforcement around the unauthenticated Ollama loopback
  API;
- productized Ollama model acquisition;
- broader matched cross-runtime benchmarking.

These do not invalidate `CLOSED_NVIDIA_STAGE1`.

## Final Lead disposition

ACCEPT `CLOSED_NVIDIA_STAGE1`.

The exact recovery point is:
`checkpoint/ollama-nvidia-stage1-2026-09-24`
at
`2c12f00286d6e7d6d524baa7a7787099e476bf08`.

The Ollama Stage-1 construction program should now stop.

Do not continue adding depth to this macropath merely because open future debt
exists.

Next work should transition back to the broader Company Brain roadmap / next
product workstream, while preserving:
- the standing AMD cross-macropath qualification lane;
- the accepted NVIDIA runtime evidence;
- the ability to revisit matched runtime comparisons later.
