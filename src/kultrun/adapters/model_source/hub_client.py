"""Lazy Hugging Face Hub access for optional live discovery and metadata.

The Hub library is never a control-plane dependency. Callers treat ImportError
and Hub errors as typed provider failure. This module must not download
weight shards: no snapshot_download, no hf_hub_download.
"""

from __future__ import annotations

import inspect
import os
from collections.abc import Callable, Mapping
from typing import Any

_TOKEN_ENV = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")
SAFETENSORS_TIMEOUT_SECONDS = 30
LIST_TIMEOUT_NOTE = "bounded Hub listing; total Hub catalog size is not claimed"


def hub_token() -> str | None:
    """Optional Hub token from the process environment. Not persisted."""
    for name in _TOKEN_ENV:
        value = os.environ.get(name)
        if value:
            return value
    return None


def import_hub() -> Any:
    """Load huggingface_hub. Raises ImportError when the extra is absent."""
    import importlib

    return importlib.import_module("huggingface_hub")


def supported_kwargs(
    fn: Callable[..., Any], kwargs: Mapping[str, Any]
) -> dict[str, Any]:
    """Drop keys the installed callable does not accept."""
    params = inspect.signature(fn).parameters
    if any(item.kind is inspect.Parameter.VAR_KEYWORD for item in params.values()):
        return {key: value for key, value in kwargs.items() if value is not None}
    return {
        key: value
        for key, value in kwargs.items()
        if key in params and value is not None
    }


def call_supported(fn: Callable[..., Any], kwargs: Mapping[str, Any]) -> Any:
    """Invoke fn with the intersection of kwargs and its signature."""
    return fn(**supported_kwargs(fn, kwargs))


def list_model_infos(kwargs: Mapping[str, Any]) -> tuple[Any, ...]:
    """HfApi.list_models through the installed signature."""
    hub = import_hub()
    api_cls = hub.HfApi
    api_kwargs: dict[str, Any] = {"token": hub_token()}
    init_params = inspect.signature(api_cls).parameters
    if "timeout" in init_params:
        api_kwargs["timeout"] = SAFETENSORS_TIMEOUT_SECONDS
    api = api_cls(**api_kwargs)
    params = inspect.signature(api.list_models).parameters
    prepared = dict(kwargs)
    apps = prepared.get("apps")
    if apps and "apps" not in params:
        prepared.pop("apps", None)
        extra = list(apps) if not isinstance(apps, str) else [apps]
        if "filter" in params and not prepared.get("filter"):
            prepared["filter"] = extra
        elif "tags" in params:
            tags = list(prepared.get("tags") or [])
            prepared["tags"] = tags + [item for item in extra if item not in tags]
    listing = call_supported(api.list_models, prepared)
    limit = prepared.get("limit")
    bound = limit if isinstance(limit, int) and limit > 0 else 50
    capped: list[Any] = []
    for index, item in enumerate(listing):
        if index >= bound:
            break
        capped.append(item)
    return tuple(capped)


def safetensors_metadata(
    repo_id: str,
    *,
    revision: str | None = None,
    timeout: int = SAFETENSORS_TIMEOUT_SECONDS,
) -> Any:
    """Hub Safetensors metadata/header API. Does not fetch weight tensors."""
    hub = import_hub()
    getter = getattr(hub, "get_safetensors_metadata", None)
    if getter is None:
        raise ImportError("get_safetensors_metadata is not available")
    kwargs: dict[str, Any] = {
        "repo_id": repo_id,
        "revision": revision,
        "token": hub_token(),
        "timeout": timeout,
    }
    params = inspect.signature(getter).parameters
    if "repo_id" not in params and params:
        # Older positional form: get_safetensors_metadata(repo_id, ...)
        filtered = supported_kwargs(getter, kwargs)
        filtered.pop("repo_id", None)
        return getter(repo_id, **filtered)
    return call_supported(getter, kwargs)


def repo_metadata_payload(repo: Any) -> dict[str, Any]:
    """Normalize Hub SafetensorsRepoMetadata into offset-based JSON."""
    files: dict[str, Any] = {}
    files_metadata = getattr(repo, "files_metadata", None) or {}
    if isinstance(files_metadata, dict):
        for name, file_meta in files_metadata.items():
            tensors = getattr(file_meta, "tensors", None) or {}
            encoded: dict[str, Any] = {}
            if isinstance(tensors, dict):
                for tensor_name, info in tensors.items():
                    offsets = getattr(info, "data_offsets", None)
                    encoded[str(tensor_name)] = {
                        "dtype": getattr(info, "dtype", None),
                        "shape": list(getattr(info, "shape", None) or []),
                        "data_offsets": list(offsets) if offsets is not None else None,
                    }
            files[str(name)] = {"tensors": encoded}
    metadata = getattr(repo, "metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
    counts = getattr(repo, "parameter_count", None)
    parameter_count = dict(counts) if isinstance(counts, dict) else {}
    return {
        "metadata": metadata,
        "sharded": bool(getattr(repo, "sharded", False)),
        "parameter_count": {
            str(key): int(value) for key, value in parameter_count.items()
        },
        "files": files,
        "full_weight_download": False,
    }
