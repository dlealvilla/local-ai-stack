# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-V0.5-LEAD-CLOSURE-CORRECTION-001`
Status: `AUTHORIZED_CORRECT_PRELIMINARY_CLOSURE_AND_RE-EARN_PASS`

Read and execute completely:

`control/instructions/RUKAN-V0.5-LEAD-CLOSURE-CORRECTION-001.md`

Repository truth:

- canonical: `machi@124a1424ab20e6fd3e2ca96ee7fedb0cef539198`
- preliminary closure PR: #6
- preliminary tested source: `8c68bdedb71f0faeec957bc14eb8b5062f9807fb`
- historical preliminary tag:
  `checkpoint/rukan-core-product-closed-nvidia-vllm-124a142`

Lead review accepts the substantial implementation but WITHHOLDS final product
closure.

Do not revert the product wholesale.

Create:
`rukan/v0.5-lead-closure-correction`

from current canonical and close the Lead blockers in the referenced instruction.

The existing merge/tag remain historical and must not be deleted.

Required sequence:

1. correct Workspace model selection;
2. complete the minimum real Agent Builder;
3. wire production OpenAI/vLLM tool calling;
4. complete useful MCP tools/resources/prompts support;
5. fix browser OIDC nonce / ID-token semantics;
6. fix reverse-proxy Secure-cookie behavior;
7. fix static path containment;
8. link per-message usage to canonical usage ids;
9. add Workspace schema migration;
10. run full local security/functional/load QA;
11. run two consecutive corrected clean diagnostics;
12. freeze exact candidate;
13. run C1/C2/C3;
14. physically prove Command Center privacy delivery and backup/restore;
15. if all pass, merge correction PR to `machi`;
16. create a new corrected closure checkpoint;
17. mark the historical preliminary tag as superseded in docs/control;
18. publish paste-back and STOP.

Do not start Git Brain yet.

Terminal PASS:

`RUKAN_V0_5_CORE_PRODUCT_LEAD_CORRECTED_CLOSED`

Terminal NOT READY:

`RUKAN_V0_5_CORE_PRODUCT_LEAD_CORRECTION_NOT_READY`

# END MASTER INSTRUCTION
