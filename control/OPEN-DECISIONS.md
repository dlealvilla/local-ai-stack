# Open Decisions

There are **no blocking Lead Developer decisions** for the current local implementation instruction.

Already decided:
- AMD managed native prefix: implement now.
- Verified existing/provider ROCm environment: preserve/implement verification now.
- OCI runtime image: preserve the seam, build later.
- ContainerExecutor: deferred.
- NVIDIA physical matrix: Ampere + Ada required next; Blackwell deferred.
- A40 is preferred but not mandatory.
- Qualification cache must not reuse evidence across materially different GPU environments solely by compute capability.

Future decision gates:
- Whether/when to build the OCI runtime image.
- Whether/when to add a Machi ContainerExecutor.
- Whether to add Blackwell as N3.
- Any new concrete provider not already accepted above.
