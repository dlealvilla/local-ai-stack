# CURRENT LEAD DEVELOPER INSTRUCTION

**Instruction ID:** `MACHI-AMD-RUNTIME-NVIDIA-MATRIX-001`  
**Status:** READY  
**Server needed now:** NO

## Goal

Implement the accepted local architecture change before the next physical campaign:

1. tighten empirical qualification reuse so compute capability alone cannot authorize reuse across materially different GPU environments;
2. implement the AMD managed ROCm userspace-prefix provider behind the existing Foundation seam;
3. preserve verified-existing ROCm as a shortcut;
4. preserve an OCI delivery seam but do not build an OCI image or ContainerExecutor yet;
5. update Acceptance Lab / development policy for sequential NVIDIA Ampere + Ada qualification.

## Mandatory repository truth

Inspect the current implementation branch first. Do not assume the remote `machi` branch is current. Preserve current repository conventions and accepted historical evidence.

## Qualification evidence scope

Keep `hardware_class` as grouping/planning metadata.

Introduce or reuse the smallest generic **execution-environment fingerprint** required to prevent unsafe cache reuse. It should be based on normalized, load-bearing host/Foundation facts rather than marketing assumptions or physical GPU UUID.

Qualification reuse must remain bound to:
- exact model artifact/revision;
- Foundation/runtime identity;
- execution-environment fingerprint;
- dtype;
- quantization;
- tensor parallelism;
- qualification policy;
- context envelope;
- concurrency envelope.

Required regression:
- same compute capability + materially different normalized GPU environment → cached qualification NOT reused;
- same material environment fingerprint → reuse may occur;
- changed Foundation generation or other load-bearing identity → not reused.

Historical records lacking the stronger evidence must not silently become current authorization.

## AMD provider decision — accepted

Generic capability: realize the userspace required by the pinned AMD/vLLM Foundation on a compatible Linux AMD host.

### Implement now
A. **Managed native prefix** — default.
C. **Verified existing/provider environment** — shortcut after exact recipe verification.

### Preserve seam only
B. **OCI image** — later packaging of the same runtime manifest.

### Defer
- ContainerExecutor;
- kernel/firmware installation;
- AOCC;
- debuggers/profilers;
- arbitrary system-wide ROCm mutation.

## AMD host boundary

Host must provide:
- Linux kernel;
- firmware;
- compatible `amdgpu` kernel driver;
- GPU visibility;
- `/dev/kfd`;
- `/dev/dri`;
- compatible base/glibc.

Machi may provide, under Machi ownership:
- ROCm userspace required by the exact RuntimeRecipe;
- HIP/CLR runtime;
- rocBLAS;
- runtime libraries actually required by the pinned wheel;
- managed Python/PyTorch/vLLM generation.

Never overwrite customer `/opt/rocm`, change global `ldconfig`, replace kernel modules, or install firmware silently.

## AMD current pinned line

Current recipe remains the exact pinned `vllm 0.18.0+rocm700` path unless repository truth has changed.

Keep AMD-specific driver/version compatibility policy in the AMD provider/adapter, not Core.

Use repository-truth and verified linkage to define the minimum redistributed userspace manifest. Do not blindly install a full SDK.

For every redistributed component capture:
- name/version;
- provenance;
- license;
- commercial classification;
- integrity/hash where available;
- why required.

Unknown material license is not silently Green.

## Ownership / isolation

Managed ROCm must live under Machi-owned storage using existing ownership mechanisms.

Require:
- local ownership marker/manifest as appropriate;
- central ownership registry where current architecture requires it;
- versioned environment identity;
- rollback deleting only Machi-owned files;
- loader isolation to the relevant Foundation generation/process;
- no global linker mutation;
- system/customer ROCm untouched.

Measure persistent, transient and peak storage instead of assuming the historical Foundation budget is sufficient.

## Existing ROCm shortcut

A provider image or existing host ROCm is accepted only when the same RuntimeRecipe checks pass. Labels/tags are not authority.

Verify actual relevant facts such as:
- version line;
- compatible driver;
- gfx/device;
- glibc;
- required sonames;
- HIP import/runtime verification.

## OCI seam

Do not build an image in this increment.

The native managed runtime must produce a versioned manifest/recipe that can later be packaged into a pinned OCI image with SBOM/license manifest. No Docker Desktop or container runtime dependency is added now.

## NVIDIA qualification matrix policy

This is Acceptance Lab/development policy, not generic Foundation Core.

### N1 — Ampere
Canonical class requirement for the next campaign:
- `cc-8.6`;
- 48 GB minimum for continuity.

Preference:
1. A40
2. RTX A6000

A40 absence alone must not block N1.

### N2 — Ada
- `cc-8.9`.

Preference:
1. L40S
2. L4
3. RTX 4090

If a 24 GB fallback is used, record that smaller memory envelope explicitly.

Actual GPU identity wins over misleading provider pool names.

### N3
Blackwell remains deferred.

## Evidence semantics

Every physical run later must record exact provider, region, SKU/model, VRAM, compute capability/architecture, driver/runtime facts, Foundation generation and execution-environment fingerprint.

Do not convert one exact SKU pass into vendor-wide or class-wide certification without a separate explicit promotion rule.

## Required local tests

At minimum cover:

### Qualification
- same cc, different material GPU environment → no cache reuse;
- same material fingerprint → reuse;
- changed Foundation generation → no reuse;
- changed model revision/dtype/quantization/TP → no reuse;
- context/concurrency beyond qualified envelope → no reuse.

### AMD
- compatible driver + no ROCm → managed prefix provider applicable;
- incompatible 6.1-style driver for rocm700 policy → refused;
- compatible existing ROCm → verified-existing path usable;
- customer `/opt/rocm` never overwritten;
- managed prefix isolated from unrelated processes;
- missing required soname → verification failure;
- unknown license on required dependency → no silent approval;
- ownership manifest/evidence present;
- cleanup touches owned files only.

### NVIDIA matrix policy
- A40 available → select A40 for N1;
- A40 absent + eligible RTX A6000 → select A6000;
- both absent → N1 environment-blocked;
- L40S available → select L40S for N2;
- L40S absent + eligible 24 GB fallback → select fallback and record smaller envelope;
- misleading provider pool label → discovered GPU identity wins.

## Gates

Run focused tests, full Machi suite, Acceptance Lab suite, architecture boundaries, strict mypy, ruff, packaging, isolated-wheel verification, privacy checks where relevant, and dependency/license-manifest checks.

No server in this task.

## Freeze

On local PASS, produce the exact implementation/evidence/build/wheel identities according to current repository conventions and STOP.

Do not start Ampere, Ada, AMD, or Blackwell physical hosts in this instruction.

## Required final paste-back

The final response must include:
- SERVER NEEDED NEXT
- TL;DR
- ARCHITECTURE MAP
- WHAT JUST HAPPENED
- WHERE WE ARE
- WHAT'S NEXT
- HANDOFF

Then include a complete structured paste-back containing at minimum:
- exact status;
- branch/implementation/evidence/build/wheel/SHA256;
- qualification fingerprint design and migration;
- AMD provider implementation and boundaries;
- exact managed runtime manifest + license classifications;
- storage footprint;
- loader isolation/ownership evidence;
- existing-environment verification;
- OCI future seam;
- N1/N2 policy and selection tests;
- exact test counts/gates;
- deviations/problems;
- exact next physical sequence.

End with:

`STOP — LOCAL AMD RUNTIME AND NVIDIA MATRIX IMPLEMENTATION COMPLETE. DO NOT CREATE A PHYSICAL SERVER UNTIL LEAD DEVELOPER REVIEW.`

## Publish

After committing/pushing implementation evidence, save the full final paste-back to a file and run:

`python tools/machi_handoff.py publish-pasteback <pasteback-file>`

Then STOP.
