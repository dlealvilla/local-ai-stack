# Stage-1 physical qualification backlog

**Status of every row below that is not Accepted:** `PHYSICAL_PENDING`.
No date is promised. One hardware family does not prove another.

This register is the place for later dedicated campaigns. It is not a
new evidence system. Accepted campaigns stay in their historical
records.

## Native / vLLM

### Accepted — one secure L40S

- Record: [INFERENCE-PROGRAM-005.md](INFERENCE-PROGRAM-005.md)
- Host class: NVIDIA L40S, compute capability 8.9, driver 580.178.04, CUDA 13.0
- Models: HuggingFaceTB/SmolLM2-135M-Instruct `12fd25f77366fa6b3b4b768ec3050bf629380bac`; HuggingFaceTB/SmolLM2-360M-Instruct `a10cc1512eabd3dde888204e902eca88bddb4951`
- Proved: managed native Foundation, qualification, request inference, stop, re-admission, restart, second request
- Negative: head-dimension-4 tiny Llama refused before normal weight acquisition
- Does not prove: Ada as a class, Ampere, Hopper, or AMD

### Pending — NVIDIA Ampere / N1 breadth

- Claim it would prove: the same native macropath on the Ampere/N1 host class named by the earlier failed campaign
- Prerequisites: a host in that class, the pinned vLLM generation, and a model the runtime can actually execute
- Macropath: native / vLLM
- Cannot reuse: the L40S pass, and the tiny Llama failure is not a substitute pass
- Status: `PHYSICAL_PENDING`

### Pending — AMD native / vLLM

- Claim it would prove: host prerequisites, then a Machi-managed ROCm userspace, then native qualification and one request on an approved AMD accelerator
- Prerequisites: stock host GPU, kernel, firmware, and devices; Machi does not replace those. See `M-5-AMD-01`
- Macropath: native / vLLM
- Cannot reuse: any NVIDIA campaign, including L40S and A40
- Status: `PHYSICAL_PENDING`
- Latest preflight in Bundle 07 found no approved AMD stock inside the cost cap. That preflight is historical, not a live stock claim

## Ollama

### Accepted — one secure A40

- Record: [OLLAMA-BUNDLE-07-PHYSICAL.md](OLLAMA-BUNDLE-07-PHYSICAL.md)
- Host class: NVIDIA A40, CUDA 13.0
- Proved: native Foundation READY, AUTO preference for vLLM while healthy, an isolated native provisioning failure, AUTO selection of Ollama, a fresh Foundation → model → Plan → Admit → Serve chain, two context-2048 request inferences, a context-bound refusal, STOP, and explicit release
- Does not prove: macOS, AMD, or live failover after a request failure

### Pending — macOS / Ollama

- Claim it would prove: the managed Ollama prefix and one context-bound request on macOS
- Prerequisites: a macOS host and the pinned artifact for that OS. The Linux `tar.zst` pin does not transfer
- Macropath: Ollama
- Cannot reuse: the A40 Linux proof (`M-5-OLLAMA-05`)
- Status: `PHYSICAL_PENDING`

### Not scheduled — AMD / Ollama

AMD/Ollama is not an accepted test plan. The open AMD item is native/vLLM qualification (`M-5-AMD-01`). Do not invent an AMD Ollama campaign from the NVIDIA fallback proof.

## Other open physical coverage already in repository truth

- Apple accelerator physical acceptance remains deferred from Discover 2.3. Memory and mount providers exist; Apple GPU inference does not.
- Windows mounts are unsupported, not zero. That is a platform gap, not a Stage-1 inference claim.
- Live request-failure failover is not physical evidence and is not claimed.
