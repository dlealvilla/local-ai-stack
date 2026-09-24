"""Loopback HTTP client for the public Ollama API. No new dependency."""

from __future__ import annotations

import http.client
import json
from urllib.parse import urlparse

from machi.adapters.model.ollama_api import (
    GENERATE_PATH,
    PS_PATH,
    SHOW_PATH,
    TAGS_PATH,
    GenerateResult,
    ListedModel,
    OllamaApiError,
    PreloadResult,
    RunningModel,
    ShownModel,
    UnloadResult,
)
from machi.foundation.ollama import private_endpoint
from machi.model.provider_candidate import (
    OllamaCatalogCandidate,
    public_candidate,
)

_MAX_BODY = 1_048_576
_CONNECT_TIMEOUT = 5.0
_READ_TIMEOUT = 180.0
_PROBE_PROMPT = "Reply with ok."
_PREDICT = 8
_NS = 1_000_000_000
_NO_FIT = ("memory", "vram", "gpu", "system ram", "insufficient")


class LoopbackOllamaClient:
    """Calls one verified loopback daemon. Response text is not retained."""

    def __init__(
        self,
        endpoint: str,
        *,
        connect_timeout: float = _CONNECT_TIMEOUT,
        read_timeout: float = _READ_TIMEOUT,
        max_body: int = _MAX_BODY,
    ) -> None:
        parsed = urlparse(endpoint)
        if (
            private_endpoint(endpoint) is None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise OllamaApiError("endpoint")
        host, port = private_endpoint(endpoint) or ("", 0)
        self._host = host
        self._port = port
        self._connect = connect_timeout
        self._read = read_timeout
        self._max_body = max_body

    def list_models(self) -> tuple[ListedModel, ...]:
        payload = self._call("GET", TAGS_PATH, None, self._read)
        models = payload.get("models")
        if not isinstance(models, list):
            raise OllamaApiError("shape")
        found: list[ListedModel] = []
        for item in models:
            if not isinstance(item, dict):
                raise OllamaApiError("shape")
            name = item.get("name")
            digest = item.get("digest")
            if not isinstance(name, str) or not isinstance(digest, str):
                raise OllamaApiError("shape")
            size = item.get("size")
            found.append(
                ListedModel(
                    name=name,
                    digest=digest,
                    size_bytes=size if isinstance(size, int) and size >= 0 else None,
                )
            )
        return tuple(found)

    def show_model(self, name: str) -> ShownModel | None:
        try:
            payload = self._call(
                "POST", SHOW_PATH, {"name": name}, self._read
            )
        except OllamaApiError as exc:
            if exc.code == "http":
                return None
            raise
        details = payload.get("details")
        block = details if isinstance(details, dict) else {}
        return ShownModel(
            name=name,
            size_bytes=None,
            family=_text(block.get("family")),
            quantization=_text(block.get("quantization_level")),
            format_label=_text(block.get("format")),
        )

    def preload(self, name: str) -> PreloadResult:
        try:
            payload = self._generate(name, prompt="", keep_alive=-1, predict=0)
        except OllamaApiError as exc:
            if exc.code == "no_fit":
                return PreloadResult("no_fit")
            if exc.code in {"timeout", "transport", "malformed", "shape", "bounded"}:
                return PreloadResult(exc.code)
            return PreloadResult("host")
        loaded = _seconds(payload.get("load_duration"))
        return PreloadResult("none", load_seconds=loaded)

    def running_models(self) -> tuple[RunningModel, ...]:
        payload = self._call("GET", PS_PATH, None, self._read)
        models = payload.get("models")
        if not isinstance(models, list):
            raise OllamaApiError("shape")
        found: list[RunningModel] = []
        for item in models:
            if not isinstance(item, dict):
                raise OllamaApiError("shape")
            name = item.get("name")
            digest = item.get("digest")
            if not isinstance(name, str) or not isinstance(digest, str):
                raise OllamaApiError("shape")
            size = item.get("size")
            vram = item.get("size_vram")
            found.append(
                RunningModel(
                    name=name,
                    digest=digest,
                    size_bytes=size if isinstance(size, int) and size >= 0 else None,
                    size_vram_bytes=(
                        vram if isinstance(vram, int) and vram >= 0 else None
                    ),
                    expires_at=_expires(item.get("expires_at")),
                )
            )
        return tuple(found)

    def generate_probe(self, name: str) -> GenerateResult:
        try:
            payload = self._generate(
                name, prompt=_PROBE_PROMPT, keep_alive=-1, predict=_PREDICT
            )
        except OllamaApiError as exc:
            if exc.code == "no_fit":
                return GenerateResult("no_fit", 0, 0, None)
            if exc.code in {"timeout", "transport", "malformed", "shape", "bounded"}:
                return GenerateResult(exc.code, 0, 0, None)
            return GenerateResult("host", 0, 0, None)
        payload.pop("response", None)
        inputs = payload.get("prompt_eval_count")
        outputs = payload.get("eval_count")
        return GenerateResult(
            failure="none",
            input_tokens=inputs if isinstance(inputs, int) and inputs >= 0 else 0,
            output_tokens=outputs if isinstance(outputs, int) and outputs >= 0 else 0,
            generation_seconds=_seconds(payload.get("eval_duration")),
        )

    def unload(self, name: str) -> UnloadResult:
        try:
            self._generate(name, prompt="", keep_alive=0, predict=0)
        except OllamaApiError:
            return UnloadResult("unload_failed")
        return UnloadResult("none")

    def _generate(
        self, name: str, *, prompt: str, keep_alive: int, predict: int
    ) -> dict[str, object]:
        body = {
            "model": name,
            "prompt": prompt,
            "stream": False,
            "keep_alive": keep_alive,
        }
        if predict:
            body["options"] = {"num_predict": predict}
        return self._call("POST", GENERATE_PATH, body, self._read)

    def _call(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None,
        read_timeout: float,
    ) -> dict[str, object]:
        raw_body = None if payload is None else json.dumps(payload).encode("utf-8")
        connection = http.client.HTTPConnection(
            self._host, self._port, timeout=self._connect
        )
        try:
            headers = {"Accept": "application/json"}
            if raw_body is not None:
                headers["Content-Type"] = "application/json"
            connection.request(method, path, body=raw_body, headers=headers)
            if connection.sock is not None:
                connection.sock.settimeout(read_timeout)
            response = connection.getresponse()
            raw = response.read(self._max_body + 1)
            status = response.status
        except TimeoutError as exc:
            raise OllamaApiError("timeout") from exc
        except OSError as exc:
            raise OllamaApiError("transport") from exc
        finally:
            connection.close()
        if len(raw) > self._max_body:
            raise OllamaApiError("bounded")
        if status >= 400:
            raise OllamaApiError(_http_code(raw))
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OllamaApiError("malformed") from exc
        if not isinstance(parsed, dict):
            raise OllamaApiError("shape")
        return parsed


def candidate_from_catalog(
    listed: ListedModel, shown: ShownModel | None
) -> OllamaCatalogCandidate:
    """Public tags plus show metadata. Dimensions are not inferred."""
    return public_candidate(
        display_name=listed.name,
        digest=listed.digest,
        size_bytes=listed.size_bytes,
        family=shown.family if shown is not None else None,
        quantization_label=shown.quantization if shown is not None else None,
        format_label=shown.format_label if shown is not None else None,
    )


def _seconds(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value / _NS


def _text(value: object) -> str | None:
    if isinstance(value, str) and value and len(value) <= 80:
        return value
    return None


def _expires(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 40 or "/" in value:
        return None
    return value


def _http_code(raw: bytes) -> str:
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "http"
    if not isinstance(parsed, dict):
        return "http"
    error = parsed.get("error")
    if not isinstance(error, str):
        return "http"
    lowered = error.lower()
    if any(marker in lowered for marker in _NO_FIT):
        return "no_fit"
    return "http"
