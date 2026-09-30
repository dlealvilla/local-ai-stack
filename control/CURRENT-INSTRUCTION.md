# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-V0.4-RESUME-ALL-PENDING-EMPLOYEE-ACCESS-001`
Status: `AUTHORIZED_CONTINUE_ALL_PENDING_PRODUCT_AND_PHYSICAL_WORK`

Read and execute completely:

`control/instructions/RUKAN-V0.4-RESUME-ALL-PENDING-EMPLOYEE-ACCESS-001.md`

Current branch:
`rukan/user-access-gateway-v0.4`

Current evidence tip:
`b2cc72610a081c92558201e67889bd220a5216c2`

Current hardened product source:
`cae6a352717b8717ec96d840eb45ab17fd080bca`

Canonical:
`machi@16084a5b21a0cca25bfe60070ad862832c80fb51`

The previous run correctly hardened:
- true streaming;
- production OIDC discovery/JWKS rotation;
- complete route/scope enforcement;
- crash-consistent Gateway usage accounting.

It stopped because the selected GPU host could not run the pinned LibreChat container.

That environment limitation no longer blocks the remaining product development.

Required execution:

1. re-verify the four hardened Gateway fixes;
2. attempt the new split LibreChat topology:
   - GPU host for Rukan/inference;
   - operator/CPU container environment for LibreChat/Mongo/test IdP/MCP;
3. whether or not physical LibreChat is immediately available, implement ALL remaining v0.4 Employee Access product-closure requirements;
4. complete local security/privacy/migration/backup/failure/load QA;
5. return to physical testing;
6. physically run the exact pinned LibreChat artifact;
7. run iterative full-stack diagnostics and robustly fix discovered product defects;
8. obtain two consecutive clean full-stack diagnostics;
9. freeze one candidate;
10. run C1/C2/C3 fresh confidence environments;
11. preserve evidence;
12. STOP for Lead review.

Do not begin first-party Rukan Workspace yet.

Do not stop after:
- design;
- documentation;
- local implementation;
- the first clean server run;
- a fixable product defect;
- an unavailable Docker engine on one GPU image.

Final PASS only:

`RUKAN_V0_4_EMPLOYEE_ACCESS_PRODUCT_CLOSED`

Otherwise:

`RUKAN_V0_4_EMPLOYEE_ACCESS_PRODUCT_NOT_READY`

Do not merge v0.4 canonical.

All existing RunPod/safety/cost/hang rules remain binding.

# END MASTER INSTRUCTION
