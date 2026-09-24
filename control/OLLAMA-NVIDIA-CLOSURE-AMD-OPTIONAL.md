# Ollama Stage-1 Closure Scope — NVIDIA Primary, AMD Opportunistic

**Status:** LEAD/PRODUCT DECISION  
**Date:** 2026-09-24

## Decision

AMD physical qualification is **not a closure gate** for the current Ollama
Stage-1 macropath.

The supported closure target for this campaign is bounded NVIDIA evidence.

Cursor must still run the standing AMD RunPod preflight during the closure
bundle. AMD physical testing may proceed only if all existing gates pass:
- MI300X (or the explicitly approved AMD target) is actually available;
- a suitable approved ROCm image is available;
- price is within the AMD cap;
- live balance is known and the safe-runtime calculation preserves the balance
  floor;
- at least 45 minutes of meaningful qualification can be completed safely;
- all existing ownership/lifecycle rules can be obeyed.

If any AMD gate fails, record the exact reason and continue the NVIDIA closure
campaign. Do not treat lack of AMD stock/image as an Ollama product failure.

If an AMD Pod is successfully created but an AMD-specific product/environment
failure occurs, preserve the evidence and keep the AMD lane open. It does not
block a truthful **NVIDIA-scoped** macropath closure unless the failure exposes
a provider-neutral/core defect that also invalidates the NVIDIA architecture.

Later, when a more reliable AMD provider is available, native/vLLM and Ollama
AMD coverage should be bundled into one cross-macropath hardware qualification
campaign rather than forcing today's closure to wait on scarce infrastructure.

## Support wording

Closure may claim only the exact NVIDIA support boundary actually proved.

Do not convert NVIDIA closure into:
- all-accelerator support;
- AMD support;
- ROCm support;
- vendor-neutral physical support.

AMD remains an explicit open coverage lane.


## Post-closure clarification — managed ROCm userspace

The AMD acceptance lane must not require a prebuilt cloud ROCm userspace image
as a blanket prerequisite.

Machi's native AMD Foundation is intended to provision the pinned
ROCm-compatible vLLM/PyTorch userspace inside a Machi-owned managed generation.

Future AMD preflight should require only genuine host/provider prerequisites
such as supported AMD hardware, usable host driver/kernel/device access,
compatible OS/glibc, vendor visibility/inspection where required, and native
shared-library prerequisites that the current pinned recipe cannot itself
supply.

Once those are present, acceptance should exercise Machi's own managed ROCm
provisioner.

A missing prebuilt "ROCm 7 image" by itself is therefore not a valid AMD product
failure or support refusal.

If provisioning reveals missing native libraries, classify each one explicitly
as:
1. a legitimate host-owned prerequisite; or
2. a dependency Machi should own/provision.

This clarification does not alter the Bundle-07 `NO_STOCK` outcome because no
AMD Pod was available or created.
