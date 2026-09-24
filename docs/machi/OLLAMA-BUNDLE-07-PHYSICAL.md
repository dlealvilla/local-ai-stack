# Ollama bundle 07 NVIDIA Stage-1 closure

One secure NVIDIA A40. Native vLLM was verified and remained the AUTO
choice while that foundation was ready. A separate owned root produced
a real provisioning failure, and AUTO then selected a fresh Ollama
plan and reservation. AMD was not tested: secure MI300X stock was
`NONE`.

Instruction: `MACHI-OLLAMA-BUNDLE-07-NVIDIA-CLOSURE-001`  
Closure: `CLOSED_NVIDIA_STAGE1`  
Pod terminated.

## Host

| Fact | Value |
|---|---|
| Provider | Runpod secure |
| Region | EU-SE-1 |
| SKU | NVIDIA A40 |
| Compute capability | 8.6 |
| Driver | 580.159.04 |
| Host CUDA | 13.0 |
| Hourly price | $0.49 |
| Pod | `5vckhyhjmjht55` |
| Lifecycle | created `2026-09-24T13:57:37.59Z`, terminate returned 204, subsequent get returned 404 |
| SAFE host bytes | 49463128064 |
| SAFE accelerator bytes | 48037363712 |
| Wheel that ran | `0.1.0+fc216642cd6d` SHA256 `f88725b7c87e8a3a10c8eb0f13d696c2116d92a98a2b9e1047943834e103e536` |
| Source that ran | `fc216642cd6d3e2f77c8bbaa53f2fe22f6bb658a` |

## Native foundation

Product provision reported ready. Generation `fgen_6e4c419798416a74`.
Selection `fsel_17d3aa41babb8ffa`. Capacity evidence `cap_ollama_b07`.
Manifest: vLLM `0.18.0`, Python `3.12.3`, torch `2.10.0+cu130`,
backend runtime `13.0`. No native model was served on this host.

## Ollama foundation

Runtime environment `renv_ceedac1939fecd21`. Foundation generation
`fgen_66a0af2ac4ba618c`. Selection `fsel_66a0af2ac4ba618c`. Fingerprint
`exe_7efc404ce831bb9bbfa4606bcfbfe224`. Support ready.

## AUTO while native vLLM was ready

Decision `fbk_fa5314e89fc227d3` selected `vllm`. It cited primary
selection `fsel_17d3aa41babb8ffa` and fallback selection
`fsel_66a0af2ac4ba618c`. No reservation was created.

## Isolated primary failure

A second apply on the healthy root reused the verified generation, so
that attempt did not make vLLM unavailable. A separate owned root, with
the managed `uv` path pointed at a file that was not there, returned
selection `fsel_9a7247e225d0d653`, support `provisioning_failed`,
failure `python_provision_failed`. The healthy generation was still
present. Host drivers, the GPU, and system Python were not changed.

AUTO decision `fbk_d83226b96d76d7e2` selected `ollama` because native
vLLM was unavailable and Ollama was ready. Recompute was
`foundation,model,plan,admit,serve`.

Fresh chain for `smollm2:135m-instruct-q8_0`, digest
`2d470404841a51320639b2c2418c7ad8643cccbbcb88c2a242b211ae83bf46a9`,
generation `fgen_66a0af2ac4ba618c`: plan `plan_d24362279180c37c`,
reservation `rsv_35c15204781dc933`, proof proven, 8 output tokens,
stop stopped, release released, active reservations empty. That plan
and reservation are not the ones from the earlier serves on this host.

## Two positive Ollama cases

Both used context 2048, binding `requested`, provider fit `FIT`,
outcome `PASS`. Shadow stayed unresolved. Classification
`MACHI_UNRESOLVED`. The runner log showed `-c 2048` and
`n_ctx_slot` 2048.

| Case | Digest | Plan | Reservation | Tokens | Seconds | Tokens/sec | size_vram |
|---|---|---|---|---|---|---|---|
| `smollm2:135m-instruct-q8_0` | `2d470404841a51320639b2c2418c7ad8643cccbbcb88c2a242b211ae83bf46a9` | `plan_bd9c83c38656c40d` | `rsv_fb869dbd283770ee` | 8 | 0.070258 | 113.86603660793077 | 205384580 |
| `smollm2:360m-instruct-q8_0` | `dfd48b1fa28f91f94d51037458e22eb461591d2f2f92bb44b115c86ac11b560f` | `plan_9bbf3fa49c0ff004` | `rsv_7854c1b5344d8896` | 8 | 0.059204 | 135.12600499966217 | 492254002 |

`size_vram` is runtime-reported. Each serve was stopped and the
reservation released. Active reservations were empty afterward.

## Negative

A plan for the 360m qualification at context 4096 was refused
`qualification_does_not_cover` before any serve.

## Comparison

These observations are not a ranking.

| | Native N2 | Ollama on this A40 |
|---|---|---|
| SKU | NVIDIA L40S, US-MO-1 | NVIDIA A40, EU-SE-1 |
| Runtime | vLLM 0.18.0 | Ollama 0.34.3 |
| Model | SmolLM2-135M-Instruct, bfloat16 | SmolLM2 family, GGUF Q8_0, two sizes |
| Context | historical qualification | 2048 requested and observed |
| Load | 39.86 seconds | not measured on this run |
| Rate | 16.47 tokens/sec | 113.87 and 135.13 tokens/sec on single 8-token proofs |
| Memory | historical SAFE accelerator ceiling 48037363712 | `size_vram` 205384580 and 492254002, runtime-reported |

The L40S and A40 runs are different SKUs and different weight
representations. The two A40 rates are single short proofs, not a
throughput study. Later cross-macropath work still has to hold SKU,
representation, context, and memory semantics fixed before any
comparison is more than a record of what happened.

## AMD

Live secure MI300X availability was `NONE` at $2.39 per hour, inside
the $4 AMD cap. MI350 was `NONE` and $5.49 per hour, outside that cap.
Balance was $15.4042087098. No AMD pod was created. `M-5-AMD-01`
stays open.
