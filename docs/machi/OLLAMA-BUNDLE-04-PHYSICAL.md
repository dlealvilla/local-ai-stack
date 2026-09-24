# Ollama bundle 04 physical qualification

Historical provider-functional evidence. It is not exact context-2048
coverage: `num_ctx` was not sent, and the runner selected context 8192.
Bundle 05 requalifies at an explicit context of 2048 before Serve.

Instruction: `MACHI-OLLAMA-BUNDLE-04-PHYSICAL-AUTH-001`  
Status: one NVIDIA L40S host, two clean qualification passes, pod terminated.

This is one host. It does not qualify Ollama as a class, NVIDIA as a vendor, or long-lived Serve.

## Host

| Fact | Value |
|---|---|
| Provider | Runpod secure |
| Region | US-NC-1 |
| SKU | NVIDIA L40S |
| Compute capability | 8.9 |
| Driver | 570.124.06 |
| Host CUDA | 12.8 |
| Hourly price | $1.09 |
| Pod | `vlkwr10g1p9faj` |
| Image | `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404` |
| Lifecycle | created `2026-09-24T09:27:42Z`, terminated after evidence, subsequent get returned 404 |
| Device | `GPU-7b845265-a028-4a9f-8d6d-00489cc8e95d` |
| SAFE host bytes | 187463127040 |
| SAFE accelerator bytes | 48037363712 |
| Foundation | ready, generation `renv_ceedac1939fecd21`, version 0.34.3, cloud disabled |
| Execution fingerprint | `exe_687af32c8cf62fa273355f81bbc01589` |
| Wheel that ran | `0.1.0+e8bba2becd9b` SHA256 `907e42d9a61d98ca9bb330b7d3370154e483616206fbf2a18294ac2dc8d0415c` |
| Archive | `e83a089fd0cd2f79ee2933cca2085846a2065f497adbc6467c402177c68423f9` |
| System zstd | 1.5.5, already present. `M-5-OLLAMA-04` stays open |

No Runpod network volume was created. The managed prefix was realized on the container filesystem, not under `/usr`.

## Model

Preferred tag `smollm2:135m-instruct-q8_0`.  
Digest `2d470404841a51320639b2c2418c7ad8643cccbbcb88c2a242b211ae83bf46a9`.  
Size 144823793 bytes. Family `llama`, quantization `Q8_0`, format `gguf`.  
The digest was absent from `/api/ps` before the first qualification.

## Qualification

Both runs admitted the remaining SAFE host and accelerator bytes, with persistent storage 0. Shadow stayed `UNRESOLVED` (`attention_shape_not_exposed`) and did not veto the provider. Provider fit was `FIT`. Outcome was `PASS`. Classification was `MACHI_UNRESOLVED`. Cleanup returned the model to absence and then released the reservation. No reservation remained active.

| Run | Reservation | Output tokens | Generation seconds | Tokens/sec | size_vram | Journal |
|---|---|---|---|---|---|---|
| First | `rsv_2f420c9e817c52f7` | 8 | 0.079721 | 100.34997052219616 | 374614261 | `evt_9eec42f57c46c00c` |
| Second | `rsv_189c931a33925193` | 8 | 0.020248 | 395.10075069142636 | 374614261 | `evt_8e1968b307b58892` |

Input tokens were 35 on both runs. `size_vram` is runtime-reported from `ollama.api.ps`, not a measured peak. The two rates are both kept. They are not averaged.

`load_seconds` is `not_measured` on both journal records. The empty preload response did not include `load_duration`. The token request's load duration was not substituted.

The case requested context 2048 and concurrency 1. The runner log reported `n_ctx_slot = 8192`. Those are not the same number.

GPU discovery on the passing daemon reported CUDA compute 8.9, name NVIDIA L40S, driver 12.8.

## Same SKU class, different host

Native N2 (`docs/machi/INFERENCE-PROGRAM-005.md`) also used an NVIDIA L40S at $1.09/hour, SAFE accelerator bytes 48037363712, and SmolLM2-135M-Instruct. That host was US-MO-1, driver 580.178.04, CUDA 13.0, vLLM 0.18.0, bfloat16 weights, load 39.86 seconds, 16.47 tokens/sec. This host is US-NC-1 with the Ollama GGUF Q8_0 digest above.

The representations are not byte-identical. The memory figures are not the same metric: native load time is a vLLM qualification measurement, and Ollama `size_vram` is a provider-reported resident size. No runtime is selected from this table.
