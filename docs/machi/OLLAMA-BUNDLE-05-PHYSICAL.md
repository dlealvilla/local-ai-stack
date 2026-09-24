# Ollama bundle 05 physical serve

Instruction: `MACHI-OLLAMA-BUNDLE-05-SERVE-001`  
Status: one NVIDIA A40 host, exact context 2048 qualification, and one authorized Serve lifecycle. Pod terminated.

This is one host. It does not qualify Ollama across NVIDIA, every context, or more than one resident model.

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
| Pod | `tt6xs8su1zhn9o` |
| Lifecycle | created `2026-09-24T11:14:34Z`, terminated after evidence, subsequent get returned 404 |
| SAFE host bytes | 49463128064 |
| SAFE accelerator bytes | 48037363712 |
| Foundation | ready, generation `renv_ceedac1939fecd21`, version 0.34.3, cloud disabled |
| Execution fingerprint | `exe_7efc404ce831bb9bbfa4606bcfbfe224` |
| Wheel | `0.1.0+9285af1057de` SHA256 `40fb7420db7687a24a13f5ce1883582270e7cadbac4b78af809cd66e7b06e2a4` |

Secure L40S stock was out at CUDA 12.8 and 13.0. Community L40S at $0.79 did not place. This A40 is a different SKU from the Bundle 04 L40S, so the two runs are not a same-host comparison.

## Context-2048 qualification

Tag `smollm2:135m-instruct-q8_0`.  
Digest `2d470404841a51320639b2c2418c7ad8643cccbbcb88c2a242b211ae83bf46a9`.  
The digest was absent before the run. Context binding was `requested`. Provider fit `FIT`. Outcome `PASS`. Shadow stayed unresolved and did not veto. Classification `MACHI_UNRESOLVED`.

The runner command contained `-c 2048`. The log recorded `n_ctx_slot = 2048`. Qualification reservation `rsv_2c21fafbb163b1e5` was released only after unload. Comparison event `evt_fbaa03f0eae61dee`.

`load_seconds` stayed `not_measured` because the empty preload response still omitted `load_duration`.

## Authorized Serve

Provider plan `plan_2484830f9776b44b` was admitted as `rsv_c35b573fb7806719` for the full cited SAFE host and accelerator bytes, persistent bytes 0. That is the same ledger as the qualification hold, and it is not a qualification probe.

| Step | Result |
|---|---|
| Start | ready |
| Inference | proven, same digest, 8 output tokens, 0.057342 seconds, 139.5137944264239 tokens/sec |
| size_vram | 205384580, runtime-reported |
| STOP | stopped, digest absent, reservation still reserved |
| Restart | ready |
| Re-inference | proven |
| STOP | stopped |
| Release | `rel_72cfb9f0e2dc0a74` |
| Later start | refused, `reservation_released` |

No prompt or response text was stored.
