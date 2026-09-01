from adapters.inference import vllm


INFERENCE_ADAPTERS = {
    "vllm": vllm,
}


def get_inference_adapter(provider):
    adapter = INFERENCE_ADAPTERS.get(provider)

    if adapter is None:
        raise ValueError(
            f"Unsupported inference provider: {provider}"
        )

    return adapter
