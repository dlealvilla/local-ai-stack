# Native vLLM five-step program

Instruction: `MACHI-INFERENCE-EXEC-005-001`  
Status: `NATIVE_VLLM_PARTIAL_PHYSICAL_PASS`

N1 Ampere did not run. A40 and RTX A6000 stock were `NONE` on secure and community clouds. N2 ran on one exact Ada host. This is not class-wide Ada support and not vendor-wide NVIDIA support.

## Host

| Fact | Value |
|---|---|
| Provider | Runpod secure |
| Region | US-MO-1 |
| SKU | NVIDIA L40S |
| Reported VRAM | 46068 MiB |
| Compute capability | 8.9 |
| Driver | 580.178.04 |
| Host CUDA | 13.0 |
| Hourly price | $1.09 |
| Pod | `o2k1u11gp1fnuy` |
| Lifecycle | created `2026-09-23T23:42:31Z`, terminated after the campaign, subsequent get returned 404 |
| Foundation generation | `fgen_071b23a5b1db1192` |
| vLLM | 0.18.0 |
| Torch | 2.10.0+cu130 |
| Python | 3.12.3 |
| SAFE accelerator bytes | 48037363712 |
| Execution fingerprint | `exe_9fc7dd60f1cafcfdb9772ea9b755337f` |
| Wheel | `0.1.0+96bc4303c4b4` SHA256 `31c8059f47de7c44eeb59489afe9887309cc9fc2cec4a1acff54972e8371d8f4` |

The Runpod pool name `ADA_48_PRO` was not used as identity. `nvidia-smi` reported NVIDIA L40S, capability 8.9.

## Model matrix

| Role | Repository | Revision | License | Result |
|---|---|---|---|---|
| Positive small | HuggingFaceTB/SmolLM2-135M-Instruct | `12fd25f77366fa6b3b4b768ec3050bf629380bac` | apache-2.0 | qualification pass, user inference pass, restart inference pass |
| Positive representative | HuggingFaceTB/SmolLM2-360M-Instruct | `a10cc1512eabd3dde888204e902eca88bddb4951` | apache-2.0 | qualification pass, user inference pass, restart inference pass |
| Negative | hf-internal-testing/tiny-random-LlamaForCausalLM | `9fb191250dd56d0ba7ec9785a025ed29c03d5998` | absent | `attention_configuration_unsupported` before weight fetch |

Both positive models are LlamaForCausalLM, bfloat16, quantization none. Artifact ids: `mart_7ff1b147d6c56cd6` and `mart_8bd78c768970c14b`.

Measured on the qualification probe:

| Model | Load seconds | Tokens per second |
|---|---|---|
| SmolLM2-135M-Instruct | 39.86 | 16.47 |
| SmolLM2-360M-Instruct | 36.49 | 16.32 |

Readiness did not count as the inference proof. Each positive case then served a real request, stopped, was admitted again, restarted, and inferred again.

The first acquire of the two positive models did download weights. A following plan was refused with `stale_capacity_input` because the fresh capacity snapshot id did not match the foundation snapshot. That refusal is the product rule. The rerun reused the stored artifacts and a matching snapshot id. The negative model did not download `model.safetensors` on either attempt.

## N1

No Ampere pod was created. Secure and community availability for A40 and RTX A6000 was `NONE`. No other SKU was substituted. There is no cross-hardware comparison.

## Support that this evidence allows

- Native managed vLLM 0.18.0 on this exact L40S host completed real request inference for the two SmolLM2 revisions above.
- The head-dimension-4 Llama was excluded before ordinary weight acquisition.
- Selection outside the deployable set is refused, including an administrator choice.
- A plan without a qualification id is not started by Serve.

## Not claimed

- Ampere, Ada as a class, or NVIDIA as a vendor.
- A 24 GiB Ada envelope. This host reported 46068 MiB.
- Ollama, Dynamo, or a container executor.

## Lab

Acceptance-lab schema version 2 adds `empirical_case` and content-addressed raw artifacts under the gitignored lab directory. Unknown licenses and prompt or secret fields are refused.

## Next program

OllamaExecutionMacropath Provider Selection Gate. Do not start it from this report.
