SERVER NEEDED NEXT: NO. Review this local candidate before any host. After that review, the physical order is N1 Ampere, then N2 Ada, one host at a time.

Instruction ID: MACHI-AMD-RUNTIME-NVIDIA-MATRIX-001

TL;DR

- Qualification reuse now requires an execution-environment fingerprint. The same compute capability is not enough.
- model.qualification version 1 stays readable and does not cover a new deployment. New evidence is version 2.
- A compatible AMD host with no ROCm userspace can use a managed prefix. An existing ROCm 7 tree is used only after the same recipe checks.
- amdgpu 6.1 is refused. Accepted lines are 6.2, 6.3, 6.4, and 30.10.
- The prefix is owned under foundation/environments/<id>. It does not overwrite a customer ROCm tree or run ldconfig.
- The pinned vLLM and HIP torch wheels need 16 external sonames, including versioned libamdhip64.so.7 and librocblas.so.5. Sizes are unmeasured, so realization refuses until they are measured.
- NVIDIA selection lives in the Acceptance Lab: N1 is A40, then RTX A6000; N2 is L40S, then L4, then RTX 4090. Blackwell stays deferred.
- Local gates passed. No physical host was created.
- Handoff bridge files were cherry-picked after the evidence commit and did not change product source.

ARCHITECTURE MAP

```text
model.qualification@2
  hardware_class                         grouping / matrix
  execution_environment_fingerprint      evidence boundary
foundation/recipe.py
  realize | verified | refuse            no driver-line list
adapters/foundation/rocm_userspace.py
  managed prefix | verified existing
  driver lines, license, ownership
tools/acceptance_lab/nvidia_matrix.py
  N1 Ampere, N2 Ada, N3 deferred
```

WHAT JUST HAPPENED

An A40 pass can no longer be reused for an RTX A6000, and an L40S pass can no longer be reused for an L4, merely because the compute capability matches. The fingerprint hashes vendor, normalized model, capability or gfx, runtime capability, and Foundation generation. It does not use a device UUID, and it does not name A40 or a driver build in Core.

The ROCm gate no longer means "/opt/rocm is already 7.0". A host that can realize the recipe is eligible for a Machi-owned prefix. A host that already has userspace must still show the version line, gfx, glibc, driver line, and the sonames the wheels actually link. Those sonames were read from the pinned vllm 0.18.0+rocm700 wheel and the HIP torch wheel torch 2.9.1+git8907517. libhiprtc.so.7 and libroctx64.so.4 are included because those wheels link them.

The GitHub handoff bridge was then cherry-picked onto m9/serve. That added only tools/machi_handoff.py, the Cursor rule, the agent shim, and a .machi-handoff/ gitignore entry. control/machi-handoff was not merged.

WHERE WE ARE

Local candidate 6a23a32cffcd1aa1bb51f44b9dcf1575b0a7fa2c, evidence fc57f24690904e9a9348b0c8f34b363e89b9addf, wheel SHA256 ac5f865af947bb11c9af582dd3fe85c375d60a6f4587ecc4dbbb14871cbe006a. Branch HEAD is 0700e669267fd0db3d642192050a8654c9beb96c, which is the handoff cache ignore on top of the evidence commit. The managed prefix footprint is still unmeasured, so a real install will not proceed on the size assumption of the old 12 GiB generation budget. AMD physical qualification and NVIDIA N1/N2 physical runs are not done.

WHAT'S NEXT

After lead-developer review: run N1 Ampere, A40 if available, otherwise RTX A6000, through qualification, Plan, Admit, Serve, one real inference, and teardown. Then run N2 Ada, L40S if available, otherwise the eligible fallback, and record that host's actual memory. One host at a time. No Blackwell.

HANDOFF

```text
PAST     hardware class reused qualification; ROCm had to exist already
PRESENT  fingerprint boundary; managed prefix; Ampere then Ada policy
NEXT     review, then N1, then N2
```

==================== BEGIN PASTE BACK — MACHI AMD RUNTIME + NVIDIA MATRIX IMPLEMENTATION ====================

## A. Exact Status

```text
STATUS=LOCAL_PASS
INSTRUCTION=MACHI-AMD-RUNTIME-NVIDIA-MATRIX-001
```

## B. Frozen Candidate

- branch: m9/serve
- implementation SHA: 6a23a32cffcd1aa1bb51f44b9dcf1575b0a7fa2c
- evidence SHA: fc57f24690904e9a9348b0c8f34b363e89b9addf
- branch HEAD after handoff bridge: 0700e669267fd0db3d642192050a8654c9beb96c
- build: 0.1.0+6a23a32cffcd
- wheel: machi-0.1.0-py3-none-any.whl (271,731 bytes)
- SHA256: ac5f865af947bb11c9af582dd3fe85c375d60a6f4587ecc4dbbb14871cbe006a
- clean status: product tree clean at the evidence commit. Untracked docs/machi/proposals/ was not committed. Isolated verify returned verify_ok. Product/runtime source diff from the evidence commit to HEAD is empty except the four development handoff files.

## C. Architecture Map

```text
src/machi/model/environment.py
  execution_environment_fingerprint
src/machi/model/qualification.py
  model.qualification@1 historical, does not cover
  model.qualification@2 current evidence
src/machi/foundation/recipe.py
  rocm700_userspace: verified | realize | refuse
src/machi/adapters/foundation/rocm_userspace.py
  driver policy, owned prefix, license gate
tools/acceptance_lab/nvidia_matrix.py
  N1 / N2 selection, N3 refused
```

## D. TL;DR

- Same compute capability no longer reuses a qualification pass.
- Historical qualification records do not cover a new deployment.
- Managed native prefix is the default AMD userspace path.
- Verified existing ROCm remains, and it must pass the recipe.
- OCI is a manifest seam only. No container executor.
- Driver policy stays in the AMD adapter: 6.2, 6.3, 6.4, 30.10. 6.1 is refused.
- Wheel linkage replaced the old three unversioned sonames with 16 versioned sonames.
- Prefix bytes are unmeasured, so realization refuses rather than assuming 12 GiB.
- N1 prefers A40, then RTX A6000. Missing A40 is not by itself a block.
- N2 prefers L40S, then L4, then RTX 4090, and records the actual memory.
- Pool names do not override discovered GPU identity.
- Blackwell was not selected or launched.

## E. Starting Repository Truth

- Old runtime seam: native vLLM only, with ROCm userspace expected to exist before install.
- Old ROCm gate: missing /opt/rocm 7.0 was a hard refusal (HOST_ALREADY_HAS_ROCM_7).
- Old qualification identity: revision, generation, engine, backend, hardware_class, dtype, quantization, envelopes, tensor parallel, and policy. Compute capability alone could reuse a pass.
- Old NVIDIA acceptance assumption: the physical campaign treated A40 as the required Ampere host.

## F. Qualification Identity Fix

- Contract: model.qualification is now version 2. Version 1 remains HistoricalQualificationEvidence.
- Fingerprint fields: vendor, normalized accelerator model, capability or gfx, runtime capability, Foundation generation. The hash is exe_ plus 32 hex characters.
- Still generic: no A40, no driver build, and no ROCm token in the Core fingerprint function. hardware_class remains a separate grouping field.
- A40 and RTX A6000 can both be cc-8.6. Their normalized models differ, so the fingerprints differ and covers is false.
- L40S and L4 can both be cc-8.9. Their normalized models differ, so a pass does not transfer.
- Reuse still also requires model revision, Foundation generation, dtype, quantization, tensor parallel, qualification policy, and context/concurrency within the qualified envelopes.

## G. Qualification Migration

Version 1 records still load. They have no fingerprint. covers accepts only version 2, so a historical pass does not cover a new deployment. No inferred migration was applied.

## H. AMD Provider Selection Implemented

```text
managed native:        implemented, default
verified existing:     implemented, same recipe checks
OCI:                   manifest field future_image_input, debt M-5-AMD-02
ContainerExecutor:     not implemented
```

No Docker or Podman dependency was added.

## I. AMD Managed Prefix

- Contract/provider: assess and realize in adapters/foundation/rocm_userspace.py. Core decides verified, realize, or refuse without the driver matrix.
- Storage: <state-root>/foundation/environments/<environment-id>/, plus registry.json.
- Ownership: manifest owner=machi, owned=true. Cleanup deletes that directory only.
- Installation mechanism: an injected writer. The product default does not download packages in this local freeze. Provision refuses native_status=realize until a prefix exists.
- Version pin: recipe vllm-0.18.0-rocm700, ROCm line 7.0.
- Environment identity: renv_ plus a hash of the recipe and component name, version, and soname.

## J. AMD Host Prerequisites

- Accepted amdgpu lines: 6.2.x, 6.3.x, 6.4.x, 30.10.x. Unknown and 6.1 are refused.
- Devices required by the adapter gate: kernel module, GPU, /dev/kfd, /dev/dri. Machi does not install them.
- glibc: at least 2.35.
- gfx: the existing rocm700 architecture set, including gfx942.

## K. AMD Minimal Runtime Manifest

Required because the pinned wheels' DT_NEEDED entries name them. Torch-bundled libraries such as libtorch_hip.so are not in the prefix.

- libamdhip64.so.7
- libhiprtc.so.7
- librocblas.so.5
- librocsolver.so.0
- libMIOpen.so.1
- libhipblas.so.3
- libhipfft.so.0
- libhiprand.so.1
- libhipsparse.so.4
- libhipsolver.so.1
- libhipsparselt.so.0
- libhipblaslt.so.1
- librccl.so.1
- libroctx64.so.4
- libmpi.so.40
- libmpi_cxx.so.40

libhiprtc is the runtime compiler library the torch wheel links, not the compiler SDK. libroctx64 is linked by libtorch_python.so, so it is not an optional profiler bundle. AOCC, ROCgdb, kernel driver, firmware, and model weights are absent.

## L. AMD Licensing

- hip-runtime 7.0 MIT green — CLR; wheel DT_NEEDED; required
- hiprtc 7.0 MIT green — CLR; libtorch_hip.so; required
- rocblas 7.0 MIT green — rocBLAS license; libtorch_hip.so; required
- rocsolver 7.0 BSD-3-Clause green — rocSOLVER license; libtorch_hip.so; required
- miopen 7.0 MIT green — MIOpen license; libtorch_hip.so; required
- hipblas 7.0 MIT green — hipBLAS license, BSD notices; vLLM and torch; required
- hipfft 7.0 MIT green — hipFFT license; libtorch_hip.so; required
- hiprand 7.0 MIT green — hipRAND license; libtorch_hip.so; required
- hipsparse 7.0 MIT green — hipSPARSE license; libtorch_hip.so; required
- hipsolver 7.0 MIT green — hipSOLVER license; libtorch_hip.so; required
- hipsparselt 7.0 MIT green — hipSPARSELt license; libtorch_hip.so; required
- hipblaslt 7.0 MIT green — hipBLASLt license; vLLM and torch; required
- rccl 7.0 BSD-3-Clause green — RCCL license; libtorch_hip.so; required
- roctx 7.0 MIT green — roctracer MIT; libtorch_python.so; required
- openmpi abi-40 BSD-3-Clause green — libtorch_global_deps.so; required
- openmpi-cxx abi-40 BSD-3-Clause green — libtorch_python.so; required

ROCm component versions are the 7.0 recipe line, not per-package build numbers. Open MPI is recorded by ABI. A required component with an unknown license or a non-green classification is refused and is not silently marked green.

## M. Loader Isolation

The generation environment sets LD_LIBRARY_PATH to the owned lib directory. An unrelated process environment does not. The provider does not call ldconfig and does not change the current process environment. The fixture test keeps a customer tree byte-for-byte unchanged.

## N. Existing ROCm Verification

Verified-existing requires the driver line, gfx, glibc, ROCm version line 7.0, and every required soname. An image label, a container tag, or the mere presence of a ROCm directory is not accepted. A missing soname is a refusal.

## O. AMD Storage Footprint

```text
persistent:       unmeasured for the prefix; generation budget remains 12 GiB
transient:        8 GiB generation staging budget; prefix staging unmeasured
peak:             unmeasured
old budget:       12 GiB persistent + 8 GiB transient for the Python generation
new requirement:  realization refuses while any required size is unknown (M-5-AMD-03)
```

## P. OCI Future Seam

The owned manifest sets future_image_input so a later image builder can package the same components. Debt M-5-AMD-02. No image was built. No container runtime dependency was added.

## Q. NVIDIA Matrix Policy

N1 is Ampere, compute capability 8.6, at least 48 GiB, preference A40 then RTX A6000, under the hourly cap and Foundation compatibility. N2 is Ada, compute capability 8.9, preference L40S then L4 then RTX 4090. N3 is deferred. The SKU list is in the Acceptance Lab, not product Core.

## R. N1 Selection Tests

A40 available selects A40. A40 absent and RTX A6000 eligible selects RTX A6000. Both absent blocks N1. Missing A40 alone does not block N1 when A6000 is eligible.

## S. N2 Selection Tests

L40S available selects L40S and records 48 GiB. L40S absent and L4 eligible selects L4 and records 24 GiB. RTX 4090 is the next preference. A 24 GiB host is not reported as a 48 GiB Ada envelope.

## T. Evidence Semantics

N1 evidence is the exact observed Ampere SKU. N2 evidence is the exact observed Ada SKU. One RTX A6000 pass is not "Ampere qualified". There is no support-promotion rule in this stage.

## U. Blackwell

Deferred. The N3 selector returns blocked and does not choose RTX PRO 4500 or any other offer. No Blackwell host was launched.

## V. Tests

- Machi suite: 493 passed.
- Acceptance Lab: 48 passed.
- Architecture boundary tests: 26 passed, inside the Machi suite.
- Qualification, ROCm fixture, and NVIDIA matrix tests are inside those suites.
- ruff check .: passed.
- strict mypy on src/machi, the new tests, and the Acceptance Lab: 193 files, no issues.
- Isolated wheel: verify_ok, including plan, admit, and serve.
- Privacy: existing event privacy assertions passed inside the Machi suite.
- License gate: an unknown license on a required component refuses realization.

## W. Packaging

Wheel dist/machi/machi-0.1.0-py3-none-any.whl, also copied to dist/machi/candidates/6a23a32cffcd1aa1bb51f44b9dcf1575b0a7fa2c/. Build 0.1.0+6a23a32cffcd. SHA256 ac5f865af947bb11c9af582dd3fe85c375d60a6f4587ecc4dbbb14871cbe006a. Clean source at build time. The later handoff commits do not change that wheel.

## X. Architecture Boundaries

Core owns the fingerprint and the verified/realize/refuse split. The AMD adapter owns driver lines, the prefix, and licenses. The Acceptance Lab owns N1/N2/N3 selection. Product code does not import the lab. No container executor was added. The handoff helper does not change product runtime state.

## Y. Problems / Corrections

- The old three sonames did not match the wheels. Direct linkage is 16 versioned sonames. That is a product correction, not a fixture shortcut.
- Prefix size is unknown. Realization fails closed. Debt M-5-AMD-03. This is not a measured footprint.
- Whole-repository mypy reports 410 pre-existing errors in Kultrun tests and older Machi tests (test_capacity.py, test_steward.py). src/machi is clean. Those older test annotations were not rewritten in this change.
- Cherry-pick of the handoff gitignore commit conflicted with the acceptance-lab ignore block. Both were kept, and .machi-handoff/ was added. .idea/ and .vscode/ were not reintroduced.

## Z. Where We Are

```text
Block:       Foundation userspace and qualification evidence
Capability:  managed rocm700 prefix, verified existing userspace, N1/N2 selection
Input:       host facts, driver line, devices, component manifest, accelerator offers
Output:      owned environment manifest, or a typed refusal; one SKU selection
Boundary:    no kernel install, no global loader, no container runtime, no physical host
```

## AA. What's Next

Run N1 Ampere first using A40 if available, otherwise RTX A6000. After teardown, run N2 Ada using L40S if available and the appropriate fallback otherwise.

## AB. Handoff

```text
PAST
  class-level qualification reuse
  host already had to contain ROCm 7
  ↓
PRESENT
  environment fingerprint
  managed prefix plus verified existing path
  Ampere then Ada selection
  GitHub handoff bridge on the implementation branch
  ↓
NEXT
  lead review
  then N1
  then N2
```

## AC. Exact Final State

Local candidate frozen on m9/serve. Evidence commit fc57f24690904e9a9348b0c8f34b363e89b9addf. Current HEAD 0700e669267fd0db3d642192050a8654c9beb96c is the development handoff only. Lab campaign camp_b6c239bfa93de6fe, candidate cand_a7ff6d5b50bb42ae, local run erun_2df77ee0b0a4005c, checkpoint chk_c3742630acadb777. No server was created. The implementation branch was not pushed.

STOP — LOCAL AMD RUNTIME AND NVIDIA MATRIX IMPLEMENTATION COMPLETE. DO NOT CREATE A PHYSICAL SERVER UNTIL LEAD DEVELOPER REVIEW.

==================== END PASTE BACK — MACHI AMD RUNTIME + NVIDIA MATRIX IMPLEMENTATION ====================
