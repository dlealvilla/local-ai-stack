"""
Runtime-specific evidence adapters.

These adapters extract implementation-specific runtime observations.

Core planning code should consume normalized evidence rather than
understanding provider-specific logs directly.
"""


def get_runtime_evidence_adapter(
    provider,
):
    if provider == "vllm":

        from adapters.runtime_evidence import (
            vllm,
        )

        return vllm


    raise ValueError(
        "Unsupported runtime evidence provider: "
        + repr(
            provider
        )
    )
