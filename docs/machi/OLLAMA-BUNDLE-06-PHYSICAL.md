# Ollama bundle 06 physical identity reproof

One NVIDIA A40. The provider Plan and Serve cited the verified
foundation generation `fgen_66a0af2ac4ba618c` and the exact model
digest. This is not NVIDIA-wide support, not physical live failover,
and not a claim that the Ollama macropath is fully closed.

Instruction: `MACHI-OLLAMA-BUNDLE-06-CLOSURE-FALLBACK-001`  
Pod terminated.

## Host

| Fact | Value |
|---|---|
| Provider | Runpod secure |
| Region | EU-SE-1 |
| SKU | NVIDIA A40 |
| Compute capability | 8.6 |
| Driver | 580.159.03 |
| Host CUDA | 13.0 |
| Hourly price | $0.49 |
| Pod | `34kxih08i7lo5x` |
| Lifecycle | created `2026-09-24T13:06:19.912Z`, terminate returned 204, subsequent get returned 404 |
| SAFE host bytes | 49463128064 |
| SAFE accelerator bytes | 48037363712 |
| Runtime environment | `renv_ceedac1939fecd21` |
| Foundation generation | `fgen_66a0af2ac4ba618c` |
| Foundation selection | `fsel_66a0af2ac4ba618c` |
| Execution fingerprint | `exe_7efc404ce831bb9bbfa4606bcfbfe224` |
| Wheel that ran | `0.1.0+9813f7279787` SHA256 `6e8068c81eeb2c3e124487c568c468c1d599d7948990403654a5594df1e1461b` |
| Source that ran | `9813f72797875f21eaf68e43bb570784d8c37580` |

The execution fingerprint matches the Bundle 05 hash because it is
still computed from the runtime-environment id and the same accelerator
facts. It is not the foundation generation. Bundle 05 cited
`renv_ceedac1939fecd21` as the generation. This run cited
`fgen_66a0af2ac4ba618c`.

## Context-2048 qualification

Tag `smollm2:135m-instruct-q8_0`.  
Digest `2d470404841a51320639b2c2418c7ad8643cccbbcb88c2a242b211ae83bf46a9`.  
Generation `fgen_66a0af2ac4ba618c`. Context binding `requested`. Provider
fit `FIT`. Outcome `PASS`. Shadow stayed unresolved. Classification
`MACHI_UNRESOLVED`.

The runner command contained `-c 2048`. The log recorded
`n_ctx_slot = 2048`. Qualification reservation
`rsv_6c5fd204aba3b7f0` (probe `qprb_8b4816fb997f0e11`) was released as
`rel_394957677b8c7802`. Comparison event `evt_7a6e415a54a6d523`.

`load_seconds` stayed unresolved because the empty preload omitted
`load_duration`.

## Authorized Serve

Provider plan `plan_c84309834a08c096` used foundation generation
`fgen_66a0af2ac4ba618c` and was admitted as `rsv_bc98167eb167e0b5` for
the full cited SAFE host and accelerator bytes, persistent bytes 0.

| Step | Result |
|---|---|
| Start | ready, instance `pin_e4aba1a070c2a081` |
| Inference | proven, proof `pprf_ca1bffebb777028f`, same digest, 8 output tokens, 0.031081 seconds, 257.3919758051543 tokens/sec |
| size_vram | 205384580, runtime-reported |
| STOP | stopped, reservation still reserved |
| Stale generation | refused, `foundation_mismatch`, daemon not edited |
| Release | `rel_38c15f1aa140926c` |
| Later start | refused, `reservation_released` |
| Active reservations | empty |

No prompt or response text was stored.
