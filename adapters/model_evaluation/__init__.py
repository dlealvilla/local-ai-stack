from adapters.model_evaluation import llmfit


MODEL_EVALUATION_ADAPTERS = {
    "llmfit": llmfit,
}


def get_model_evaluation_adapter(
    provider,
):
    adapter = (
        MODEL_EVALUATION_ADAPTERS.get(
            provider
        )
    )

    if adapter is None:
        raise ValueError(
            f"Unsupported ModelEvaluation provider: {provider}"
        )

    return adapter
