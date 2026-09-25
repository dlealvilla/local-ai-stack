# Open Decisions

There are **no blocking Lead Developer decisions** for the Stage-1 deployment-spine closure instruction.

## Binding decisions for Stage-1 closure

- **No new physical acceptance campaign is required for this closure bundle.**
- Existing accepted physical evidence is sufficient to close the **Stage-1 deployment-spine capability** at its currently proven scope:
  - native/vLLM real qualification + request inference + restart inference on the accepted NVIDIA L40S campaign;
  - Ollama real Serve/fallback on the accepted NVIDIA A40 Bundle-07 campaign.
- Remaining hardware/platform breadth is **deferred qualification**, not a Stage-1 closure blocker.
- NVIDIA Ampere/N1 qualification remains useful future coverage, but it is no longer required merely to close Stage-1.
- AMD native/vLLM Foundation and downstream execution qualification remain **OPEN / PHYSICAL_PENDING**. Do not claim AMD support from NVIDIA evidence.
- macOS/Ollama physical qualification remains **OPEN / PHYSICAL_PENDING**. Do not claim macOS Ollama support until a dedicated test is run.
- Any other currently pending physical proof that is not already supported by accepted evidence should remain explicitly pending rather than being manufactured, inferred, or silently marked PASS.
- Stage-1 closure must therefore distinguish:
  - **implementation / architecture / control-path closure**, from
  - **hardware/provider qualification breadth**.
- Ollama remains the compatibility/fallback macropath. Native/vLLM remains primary where supported.
- One ResourceManager ledger remains authoritative across macropaths.
- Native and Ollama model catalogs remain separate.
- AUTO fallback remains a control-plane recomputation, not a hidden Serve retry and not live request-failure failover.
- The tiny-Llama NVIDIA-N1 failure remains valid historical negative evidence. Do not erase it merely because SmolLM2 succeeded elsewhere.
- The next stage/workstream is **not yet selected**. Cursor must finish Stage-1 closure and return a decision memo comparing sensible post-spine options before implementation continues.

## Previously decided and still valid

- AMD managed native prefix/userspace is Machi-owned; host kernel/driver/device prerequisites remain host-owned.
- Verified existing/provider ROCm userspace may be verified/reused when it matches the approved recipe.
- OCI runtime image: preserve the seam, build later unless a future decision opens it.
- ContainerExecutor: deferred.
- Qualification evidence must not be reused across materially different GPU environments merely by compute capability.

## Superseded prior guidance

The earlier statement that **Ampere + Ada are required next** is superseded for Stage-1 closure. Ada/L40S evidence may satisfy the native Stage-1 capability proof; Ampere remains a later hardware-breadth qualification target.

The earlier pattern of treating the absence of a prebuilt ROCm image as an AMD blocker is superseded. Future AMD testing should begin from host-level prerequisites and allow Machi to provision its owned ROCm-compatible userspace.

## Future decision gates

- Which post-Stage-1 workstream to open:
  - simple local operator/admin frontend;
  - central deployment command center / fleet-facing business control plane;
  - Runtime Artifact Registry / software supply chain;
  - NVIDIA Dynamo macropath / Stage-2 empirical infrastructure lab;
  - another roadmap-aligned option identified by the Stage-1 closure review.
- Whether a simple frontend and command-center workstream should be one bounded product increment or two planes with separate security/identity boundaries.
- Whether/when to build the OCI runtime image.
- Whether/when to add a Machi ContainerExecutor.
- Whether/when to add broader NVIDIA hardware qualification, AMD qualification, and macOS/Ollama qualification campaigns.
- Any new concrete provider not already accepted.
