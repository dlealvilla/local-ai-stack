# Machi Architecture State

## Current focus

Block 5 Foundation + Block 6 Model Qualification.

## Accepted direction

### AMD
- Host provides kernel, firmware, compatible `amdgpu`, GPU devices, `/dev/kfd`, and `/dev/dri`.
- Machi should be able to realize the required ROCm 7.0-compatible userspace itself.
- Managed native ROCm prefix is the default provider.
- Verified existing/provider ROCm environment is an allowed shortcut only after the same recipe verification.
- OCI is an optional future delivery form of the same managed runtime manifest.
- Do not implement `ContainerExecutor` in the current increment.
- Do not silently install/replace kernel modules or firmware.

### NVIDIA
- A40 is preferred historical Ampere continuity, not a hard dependency.
- Current required physical matrix: one Ampere class host, then one Ada class host, sequentially.
- Ampere preference: A40 → RTX A6000, with canonical campaign memory floor 48 GB.
- Ada preference: L40S → L4 → RTX 4090, recording the exact memory envelope used.
- Blackwell is deferred.

### Qualification evidence
- `hardware_class` remains a planning/grouping concept.
- Cached empirical qualification must additionally bind to a material execution-environment fingerprint.
- One A40 pass must not automatically authorize RTX A6000 merely because both are `cc-8.6`.
- One L40S pass must not automatically authorize L4 merely because both are `cc-8.9`.
- Exact observed SKU/environment stays in acceptance evidence.

## Current physical state

- NVIDIA empirical model qualification / M9 L5 remains open.
- Historical A40 attempts exposed the original model-compatibility false positive.
- Model compatibility/qualification funnel has been redesigned locally.
- AMD physical Foundation remains open.
- Historical ROCm 6.1 provider images are not considered sufficient for the pinned `vllm 0.18.0+rocm700` path.

## Governing principle

Core owns concepts; adapters/providers own implementations.
