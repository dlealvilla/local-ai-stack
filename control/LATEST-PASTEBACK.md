SERVER NEEDED NEXT: NO

Instruction: MACHI-INFERENCE-EXEC-005-001
Program status: NATIVE_VLLM_PARTIAL_PHYSICAL_PASS

TL;DR

- The funnel now refuses a selection that is not in the current deployable set, including an administrator choice.
- Serve will not start a plan that has no qualification id. Readiness is not an inference proof.
- The empirical lab is schema version 2, with queryable cases and content-addressed raw artifacts.
- N1 Ampere was environment-blocked. A40 and RTX A6000 were NONE on secure and community. No substitute SKU was used. No Ampere pod was created.
- N2 ran on one exact NVIDIA L40S in US-MO-1 at $1.09/h. nvidia-smi reported 46068 MiB, compute capability 8.9, driver 580.178.04, CUDA 13.0.
- Two SmolLM2 instruct revisions completed qualification, a real request, stop, a new admission, restart, and a second inference.
- The tiny Llama with head dimension 4 was excluded as attention_configuration_unsupported before its weights were fetched.
- The L40S pod o2k1u11gp1fnuy was terminated. A later get returned 404.
- This is not Ada-wide or NVIDIA-wide support. Ollama was not started.

ARCHITECTURE MAP

```text
Step 1  model selection and plan/serve qualification gate
Step 2  acceptance lab empirical_case + raw sha256 artifacts
Step 3  N1 stock gate, no host
Step 4  N2 L40S native vLLM spine
Step 5  partial closure report
```

WHAT JUST HAPPENED

Steps 1 and 2 were already on automation/inference-program. This run continued at Step 4 because Step 3 was already environment-blocked. Secure L40S stock was LOW at $1.09/h, so that SKU was used instead of the 24 GiB fallbacks. The product wheel 0.1.0+96bc4303c4b4 was installed without editing it on the host. Foundation generation fgen_071b23a5b1db1192 verified vLLM 0.18.0 and CUDA 13.0. The first plan attempt correctly refused a mismatched capacity snapshot. The rerun used the matching snapshot and the already stored artifacts.

WHERE WE ARE

- Branch: automation/inference-program at 6e17f4a817d1571e0a708decec405ceda0282c7f
- Recovery branch checkpoint/pre-automation-inference-2026-09-23 remains 0700e669267fd0db3d642192050a8654c9beb96c
- Funnel implementation: 96bc4303c4b4af48cfb6326b89edd951fa043911
- Lab implementation: 765aab67208cd1fde399db83be0e4254308597e0
- Report: docs/machi/INFERENCE-PROGRAM-005.md
- Wheel SHA256: 31c8059f47de7c44eeb59489afe9887309cc9fc2cec4a1acff54972e8371d8f4

WHAT'S NEXT

Lead review of this partial closure. The following program, not started here, is the OllamaExecutionMacropath Provider Selection Gate.

HANDOFF

```text
PAST     N1 blocked, funnel and lab frozen
PRESENT  one L40S host, two served models, one upstream exclusion
NEXT     lead review, then Ollama provider selection
```

==================== BEGIN PASTE BACK — MACHI INFERENCE EXEC 005 ====================

## Program status

NATIVE_VLLM_PARTIAL_PHYSICAL_PASS

## Recovery

checkpoint/pre-automation-inference-2026-09-23 = 0700e669267fd0db3d642192050a8654c9beb96c
It was not moved.

## Steps

1. MACHI-INF-01-FUNNEL-INVARIANTS PASS
   End 96bc4303c4b4af48cfb6326b89edd951fa043911
   Build 0.1.0+96bc4303c4b4
   Wheel 31c8059f47de7c44eeb59489afe9887309cc9fc2cec4a1acff54972e8371d8f4
   Selection outside DeployableModels is refused. Serve requires qualification_id. Readiness is not InferenceProof. Head-dimension 4 does not fetch weights.

2. MACHI-INF-02-EMPIRICAL-LAB PASS
   End 765aab67208cd1fde399db83be0e4254308597e0
   Schema version 2. empirical_case plus sha256 raw artifacts. No new product dependency.

3. MACHI-INF-03-N1-AMPERE ENVIRONMENT_BLOCKED
   A40 NONE. RTX A6000 NONE. Secure and community. No pod.

4. MACHI-INF-04-N2-ADA PASS
   Pod o2k1u11gp1fnuy, NVIDIA L40S, US-MO-1, $1.09/h, 46068 MiB, cc 8.9, driver 580.178.04, CUDA 13.0.
   Generation fgen_071b23a5b1db1192
   Fingerprint exe_9fc7dd60f1cafcfdb9772ea9b755337f
   Terminated. Get returned 404.

5. MACHI-INF-05-NATIVE-VLLM-CLOSE PASS as a partial report
   End 6e17f4a817d1571e0a708decec405ceda0282c7f

## Model matrix

- HuggingFaceTB/SmolLM2-135M-Instruct 12fd25f77366fa6b3b4b768ec3050bf629380bac apache-2.0
  served, load 39.86s, 16.47 tok/s, restart inference pass, artifact mart_7ff1b147d6c56cd6
- HuggingFaceTB/SmolLM2-360M-Instruct a10cc1512eabd3dde888204e902eca88bddb4951 apache-2.0
  served, load 36.49s, 16.32 tok/s, restart inference pass, artifact mart_8bd78c768970c14b
- hf-internal-testing/tiny-random-LlamaForCausalLM 9fb191250dd56d0ba7ec9785a025ed29c03d5998
  license absent, attention_configuration_unsupported, weights_fetched false

## Comparison

No N1 measurements exist, so there is no Ampere-versus-Ada performance comparison. N2 used a 48 GiB-class L40S, not a 24 GiB fallback.

## Lab

Cases ecase_n2_135m, ecase_n2_360m, ecase_n2_tiny. Query by gpu_model NVIDIA L40S returned 3. Failure counts: none 2, attention_configuration_unsupported 1.

## Support claims

Exact L40S host plus the two SmolLM2 revisions above, on this wheel and generation. Nothing broader.

## Debt and blocks

- M-5-AMD-01, M-5-AMD-02, M-5-AMD-03 remain open.
- N1 Ampere physical qualification remains open because stock was empty.
- Cross-hardware comparison is absent.
- The campaign driver, not product source, aligned the capacity snapshot id after the product correctly returned stale_capacity_input.

## Next

OllamaExecutionMacropath Provider Selection Gate. Not started.

STOP — FIVE-STEP NATIVE vLLM PROGRAM COMPLETE. WAIT FOR LEAD REVIEW.

==================== END PASTE BACK — MACHI INFERENCE EXEC 005 ====================
