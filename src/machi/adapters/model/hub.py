"""Explicit hub repository access. Not a catalog crawl."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from machi.kernel.errors import ValidationError
from machi.model.source import SourceFileInfo, SourceView


def inspect_repository(repository: str, revision: str, *, cache: Path) -> SourceView:
    """Resolve one repo revision and read metadata. Weights stay remote."""
    api, hf_hub = _client()
    token = _token()
    cache.mkdir(parents=True, exist_ok=True)
    try:
        info = _model_info(api, repository, revision, token)
    except Exception as exc:
        raise ValidationError(_classify(exc)) from None
    commit = str(getattr(info, "sha", "") or "")
    if not commit:
        raise ValidationError("revision_not_found")
    siblings = getattr(info, "siblings", None) or []
    files: list[SourceFileInfo] = []
    for sibling in siblings:
        name = str(getattr(sibling, "rfilename", "") or "")
        if not name:
            continue
        size = getattr(sibling, "size", None)
        files.append(
            SourceFileInfo(
                relative_path=name,
                size_bytes=size if isinstance(size, int) else None,
            )
        )
    config_text = _small_text(hf_hub, repository, commit, "config.json", token, cache)
    index_text = None
    if any(item.relative_path == "model.safetensors.index.json" for item in files):
        index_text = _small_text(
            hf_hub,
            repository,
            commit,
            "model.safetensors.index.json",
            token,
            cache,
        )
    card = getattr(info, "card_data", None)
    license_id = getattr(card, "license", None) if card is not None else None
    gated = bool(getattr(info, "gated", False))
    private = bool(getattr(info, "private", False))
    return SourceView(
        repository=repository,
        requested_revision=revision,
        immutable_revision=commit,
        files=tuple(files),
        config_text=config_text,
        index_text=index_text,
        license_id=license_id if isinstance(license_id, str) else None,
        gated=gated,
        private=private,
    )


def fetch_files(
    view: SourceView,
    destination: Path,
    relative_paths: tuple[str, ...],
    *,
    cache: Path,
    timeout_seconds: int,
) -> None:
    """Download planned files into staging. The hub cache is not the warehouse."""
    _api, hf_hub = _client()
    token = _token()
    destination.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    scratch = destination / ".fetch"
    scratch.mkdir(parents=True, exist_ok=True)
    try:
        _snapshot(
            hf_hub,
            view,
            scratch,
            relative_paths,
            token,
            cache,
            timeout_seconds,
        )
        for relative in relative_paths:
            source = scratch / relative
            if source.is_symlink() or not source.is_file():
                raise ValidationError("download_failed")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    except ValidationError:
        raise
    except Exception:
        raise ValidationError("download_failed") from None
    finally:
        if scratch.exists():
            shutil.rmtree(scratch)


def _model_info(api: Any, repository: str, revision: str, token: str | None) -> Any:
    """Ask for file sizes. Without them the requirement stays unresolved."""
    try:
        return api.model_info(
            repository,
            revision=revision,
            token=token,
            files_metadata=True,
        )
    except TypeError:
        return api.model_info(repository, revision=revision, token=token)


def _client() -> tuple[Any, Any]:
    try:
        import huggingface_hub  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ValidationError("packaging_incomplete") from exc
    return huggingface_hub.HfApi(), huggingface_hub


def credential_supplied() -> bool:
    """True when an external token is present. The token is not returned."""
    return _token() is not None


def _token() -> str | None:
    value = os.environ.get("HF_TOKEN", "").strip()
    return value or None


def _snapshot(
    hf_hub: Any,
    view: SourceView,
    scratch: Path,
    relative_paths: tuple[str, ...],
    token: str | None,
    cache: Path,
    timeout_seconds: int,
) -> None:
    kwargs = {
        "repo_id": view.repository,
        "revision": view.immutable_revision,
        "allow_patterns": list(relative_paths),
        "local_dir": str(scratch),
        "cache_dir": str(cache),
        "token": token,
    }
    try:
        hf_hub.snapshot_download(etag_timeout=timeout_seconds, **kwargs)
    except TypeError:
        hf_hub.snapshot_download(**kwargs)


def _small_text(
    hf_hub: Any,
    repository: str,
    revision: str,
    filename: str,
    token: str | None,
    cache: Path,
) -> str | None:
    try:
        path = hf_hub.hf_hub_download(
            repository,
            filename,
            revision=revision,
            token=token,
            cache_dir=str(cache),
        )
    except Exception:
        return None
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _classify(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "gated" in text or "gated" in name:
        return "gated_access_required"
    if "401" in text or "unauthorized" in text:
        return "authentication_required"
    if "403" in text or "forbidden" in text:
        return "access_denied"
    if "404" in text or "not found" in text or "repositorynotfound" in name:
        return "repository_not_found"
    if "revision" in text:
        return "revision_not_found"
    return "source_unavailable"
