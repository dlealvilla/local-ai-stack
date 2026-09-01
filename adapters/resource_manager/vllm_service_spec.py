"""vLLM ServiceSpec provider for Phase 9 ResourceManager.

AI_DEPLOYMENT_PHASE9_VLLM_SERVICE_SPEC_PROVIDER_V1

Exact dependencies:
- core.model_inventory.list_model_inventory()
    -> {"schema_version": 1, "models": [...]}
- adapters.inference.vllm.build_service_spec(plan, config)

This adapter performs translation only.

It does not own:
- resource admission;
- runtime sizing;
- hardware policy;
- model selection;
- process lifecycle;
- executor behavior.
"""

from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping
from typing import Any, Callable

from adapters.inference.vllm import (
    build_service_spec,
)
from core.model_inventory import (
    list_model_inventory,
)


class VllmServiceSpecError(RuntimeError):
    """The requested vLLM service specification cannot be built safely."""


InventoryProvider = Callable[[], Any]


def _inventory_models(
    payload: Any,
) -> list[Mapping[str, Any]]:
    """Consume the exact Model Inventory v1 public contract."""

    if not isinstance(payload, Mapping):
        raise VllmServiceSpecError(
            "Model Inventory must return a mapping"
        )

    schema_version = payload.get(
        "schema_version"
    )

    if schema_version != 1:
        raise VllmServiceSpecError(
            "unsupported Model Inventory schema_version: "
            f"{schema_version!r}"
        )

    models = payload.get(
        "models"
    )

    if not isinstance(models, list):
        raise VllmServiceSpecError(
            "Model Inventory v1 must contain a models list"
        )

    normalized: list[Mapping[str, Any]] = []

    for index, model in enumerate(models):
        if not isinstance(model, Mapping):
            raise VllmServiceSpecError(
                "Model Inventory contains a non-mapping model "
                f"at index {index}"
            )

        normalized.append(model)

    return normalized


class VllmInventoryServiceSpecProvider:
    """Resolve inventory model IDs into the existing vLLM ServiceSpec."""

    REQUIRED_PERFORMANCE_KEYS = (
        "context_length",
        "gpu_memory_utilization",
        "concurrency",
    )

    REQUIRED_INFERENCE_KEYS = (
        "served_model_name",
        "tool_calling",
    )

    REQUIRED_NETWORK_KEYS = (
        "inference_host",
        "inference_port",
    )

    def __init__(
        self,
        *,
        config: Mapping[str, Any],
        performance: Mapping[str, Any],
        inventory_provider: InventoryProvider = list_model_inventory,
    ) -> None:
        if not isinstance(config, Mapping):
            raise VllmServiceSpecError(
                "config must be a mapping"
            )

        if not isinstance(performance, Mapping):
            raise VllmServiceSpecError(
                "performance must be a mapping"
            )

        self._config = deepcopy(
            dict(config)
        )

        self._performance = deepcopy(
            dict(performance)
        )

        self._inventory_provider = (
            inventory_provider
        )

    def _record(
        self,
        model_id: str,
    ) -> Mapping[str, Any]:
        payload = self._inventory_provider()

        models = _inventory_models(
            payload
        )

        matches = [
            model
            for model in models
            if str(
                model.get("model_id", "")
            ).strip() == model_id
        ]

        if not matches:
            raise VllmServiceSpecError(
                "model is not present in Model Inventory: "
                f"{model_id}"
            )

        if len(matches) != 1:
            raise VllmServiceSpecError(
                "Model Inventory contains duplicate model_id: "
                f"{model_id}"
            )

        return matches[0]

    def _resolved_performance(
        self,
        metadata: Mapping[str, Any],
    ) -> dict[str, Any]:
        performance = deepcopy(
            self._performance
        )

        override = metadata.get(
            "performance"
        )

        if override is not None:
            if not isinstance(
                override,
                Mapping,
            ):
                raise VllmServiceSpecError(
                    "metadata.performance must be a mapping"
                )

            performance.update(
                dict(override)
            )

        missing = [
            key
            for key in self.REQUIRED_PERFORMANCE_KEYS
            if key not in performance
        ]

        if missing:
            raise VllmServiceSpecError(
                "missing required performance fields: "
                + ",".join(missing)
            )

        return performance

    def _resolved_config(
        self,
    ) -> dict[str, Any]:
        config = deepcopy(
            self._config
        )

        inference = config.get(
            "inference"
        )

        network = config.get(
            "network"
        )

        if not isinstance(
            inference,
            Mapping,
        ):
            raise VllmServiceSpecError(
                "config.inference must be a mapping"
            )

        if not isinstance(
            network,
            Mapping,
        ):
            raise VllmServiceSpecError(
                "config.network must be a mapping"
            )

        inference = dict(
            inference
        )

        network = dict(
            network
        )

        missing_inference = [
            key
            for key in self.REQUIRED_INFERENCE_KEYS
            if key not in inference
        ]

        if missing_inference:
            raise VllmServiceSpecError(
                "missing required inference fields: "
                + ",".join(missing_inference)
            )

        missing_network = [
            key
            for key in self.REQUIRED_NETWORK_KEYS
            if key not in network
        ]

        if missing_network:
            raise VllmServiceSpecError(
                "missing required network fields: "
                + ",".join(missing_network)
            )

        config["inference"] = inference
        config["network"] = network

        return config

    def build(
        self,
        *,
        model_id: str,
        metadata: Mapping[str, Any],
    ) -> dict[str, Any]:
        model_id = str(
            model_id
        ).strip()

        if not model_id:
            raise VllmServiceSpecError(
                "model_id cannot be empty"
            )

        if not isinstance(
            metadata,
            Mapping,
        ):
            raise VllmServiceSpecError(
                "metadata must be a mapping"
            )

        record = self._record(
            model_id
        )

        model_path = record.get(
            "path"
        )

        if (
            not isinstance(model_path, str)
            or not model_path.strip()
        ):
            raise VllmServiceSpecError(
                "inventory model has no usable path: "
                f"{model_id}"
            )

        performance = (
            self._resolved_performance(
                metadata
            )
        )

        config = (
            self._resolved_config()
        )

        plan = {
            "selected_model": {
                "name": model_id,
                "path": model_path.strip(),
            },
            "performance":
                performance,
        }

        return build_service_spec(
            plan,
            config,
        )
