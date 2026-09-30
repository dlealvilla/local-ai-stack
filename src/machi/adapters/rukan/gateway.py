"""Employee inference edge. Serve stays on loopback and is not a client URL."""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from machi.adapters.rukan.credentials import verify_credential
from machi.adapters.rukan.directory import Directory
from machi.adapters.rukan.gateway_store import GatewayLedger
from machi.adapters.rukan.mcp_policy import assert_endpoint, forward_json
from machi.adapters.rukan.oidc import OIDCBearerVerifier, OidcDiscoveryVerifier
from machi.adapters.rukan.project import project_admin
from machi.adapters.rukan.read import load_records
from machi.adapters.rukan.telemetry import TelemetryStore
from machi.kernel.build import BuildIdentity
from machi.kernel.errors import ValidationError
from machi.kernel.gateway import NOT_RECORDED, PrincipalUsage
from machi.kernel.usage import NOT_RECORDED as USAGE_UNRECORDED
from machi.kernel.usage import InferenceUsage
from machi.serve.native import NativeProcessEvidence

_MAX_MESSAGES = 32_000
_PUBLIC_ERRORS = {
    "authentication_required": 401,
    "identity_not_provisioned": 403,
    "identity_binding_conflict": 409,
    "user_suspended": 403,
    "platform_access_denied": 403,
    "inference_access_denied": 403,
    "model_not_allowed": 403,
    "no_ready_model": 409,
        "overloaded": 429,
        "upstream_failure": 502,
        "mcp_access_denied": 403,
        "mcp_target_denied": 403,
        "scope_denied": 403,
    }


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    auth_method: str
    scopes: tuple[str, ...]
    client_id: str


@dataclass(frozen=True, slots=True)
class UpstreamResult:
    outcome: str
    text: str
    input_tokens: int | None
    output_tokens: int | None
    chunks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StreamPiece:
    """One incremental upstream event. Text is not stored after it is forwarded."""

    kind: str
    text: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None


class StoreChat:
    """Call the authorised loopback runtime. The port never leaves this object."""

    def __init__(self, store_root: Path, build: BuildIdentity) -> None:
        self.store_root = store_root
        self.build = build
        self.model_id: str | None = None
        self.instance_id = NOT_RECORDED
        self.macropath = NOT_RECORDED
        self._port = 0

    def refresh(self) -> None:
        view = project_admin(self.store_root, self.build)
        chain = view.chain
        if chain.basis != "authorised_ready_instance" or chain.contradictory:
            self.model_id = None
            return
        evidence = next(
            (
                item
                for item in load_records(self.store_root, NativeProcessEvidence)
                if isinstance(item, NativeProcessEvidence)
                and item.instance_id == chain.instance_id
            ),
            None,
        )
        if not isinstance(evidence, NativeProcessEvidence):
            self.model_id = None
            return
        self.model_id = chain.model_identity
        self.instance_id = chain.instance_id
        self.macropath = chain.macropath
        self._port = evidence.port

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        stream: bool,
    ) -> UpstreamResult:
        self.refresh()
        if self.model_id is None or self._port < 1:
            raise ValidationError("no_ready_model")
        if model != self.model_id:
            raise ValidationError("model_not_allowed")
        del stream
        body = json.dumps(_chat_body(model, messages, max_tokens, False)).encode()
        request = _upstream_request(self._port, body)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ValidationError("upstream_failure") from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValidationError("upstream_failure") from exc
        text = _message_text(payload)
        prompt, completion = _usage_pair(payload)
        return UpstreamResult("completed", text, prompt, completion, (text,))

    def iter_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> Iterator[StreamPiece]:
        """Forward upstream SSE as it arrives. The socket closes with this generator."""
        self.refresh()
        if self.model_id is None or self._port < 1:
            raise ValidationError("no_ready_model")
        if model != self.model_id:
            raise ValidationError("model_not_allowed")
        body = json.dumps(_chat_body(model, messages, max_tokens, True)).encode()
        request = _upstream_request(self._port, body)
        try:
            response = urllib.request.urlopen(request, timeout=60)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ValidationError("upstream_failure") from exc
        try:
            for raw_line in response:
                piece = _sse_piece(raw_line.decode("utf-8", "replace"))
                if piece is not None:
                    yield piece
                    if piece.kind in {"done", "error"}:
                        break
        finally:
            response.close()


class GatewayService:
    """Authenticate, authorize, route, and account one employee request."""

    def __init__(
        self,
        store_root: Path,
        build: BuildIdentity,
        verifier: OIDCBearerVerifier | OidcDiscoveryVerifier,
        upstream: StoreChat,
        *,
        max_tokens: int = 256,
        max_global: int = 8,
        max_user: int = 2,
    ) -> None:
        self.store_root = Path(store_root)
        self.build = build
        self.verifier = verifier
        self.upstream = upstream
        self.max_tokens = max_tokens
        self.max_global = max_global
        self.max_user = max_user
        self.directory = Directory(self.store_root)
        self.ledger = GatewayLedger(self.store_root)
        self.telemetry = TelemetryStore(self.store_root, None, build)
        self._lock = threading.Lock()
        self._inflight = 0
        self._users: dict[str, int] = {}

    def close(self) -> None:
        self.directory.close()
        self.ledger.close()
        self.telemetry.close()

    def authenticate(self, header: str | None, *, client_id: str, now: datetime) -> Principal:  # noqa: E501
        if not header or not header.lower().startswith("bearer "):
            raise ValidationError("authentication_required")
        token = header.split(" ", 1)[1].strip()
        if token.startswith("rkey_"):
            found = verify_credential(self.directory, token, now)
            raw_scopes = found["scopes"]
            scopes = raw_scopes if isinstance(raw_scopes, tuple) else ()
            return Principal(str(found["user_id"]), "api_credential", scopes, client_id)
        claims = self.verifier.verify(token)
        bound = self.directory.resolve_oidc(
            issuer=claims["issuer"],
            subject=claims["subject"],
            email=claims["email"],
            now=now,
        )
        return Principal(str(bound["user_id"]), "oidc", ("inference", "models", "self_usage", "mcp"), client_id)  # noqa: E501

    def models(self, principal: Principal) -> dict[str, object]:
        self._require_scope(principal, "models")
        access = self._access(principal)
        self.upstream.refresh()
        if access["inference_access"] != "allow" or self.upstream.model_id is None:
            return {"object": "list", "data": []}
        return {
            "object": "list",
            "data": [{"id": self.upstream.model_id, "object": "model", "owned_by": "rukan"}],  # noqa: E501
        }

    def chat(self, principal: Principal, body: dict[str, object], *, now: datetime, stream: bool) -> dict[str, object]:  # noqa: E501
        messages, model, limit = self._prepare(principal, body)
        self._enter(principal.user_id)
        started = time.monotonic()
        try:
            result = self.upstream.complete(
                model=model, messages=messages, max_tokens=limit, stream=stream
            )
        except ValidationError as exc:
            self._leave(principal.user_id)
            if exc.message == "upstream_failure":
                self._account(
                    principal, model,
                    UpstreamResult("failed", "", None, None, ()),
                    max(0, int((time.monotonic() - started) * 1000)),
                    now, failed=True,
                )
            raise
        elapsed = max(0, int((time.monotonic() - started) * 1000))
        usage_id = self._account(principal, model, result, elapsed, now, failed=False)
        self._leave(principal.user_id)
        return _completion(usage_id, model, result)

    def stream(self, principal: Principal, body: dict[str, object], *, now: datetime) -> Iterator[bytes]:  # noqa: E501
        messages, model, limit = self._prepare(principal, body)
        self._enter(principal.user_id)
        started = time.monotonic()
        inputs: int | None = None
        outputs: int | None = None
        failed = False
        iterator = self.upstream.iter_stream(
            model=model, messages=messages, max_tokens=limit
        )
        try:
            for piece in iterator:
                if piece.kind == "delta" and piece.text:
                    yield _sse({"choices": [{"delta": {"content": piece.text}}]})
                elif piece.kind == "usage":
                    if piece.text:
                        yield _sse({"choices": [{"delta": {"content": piece.text}}]})
                    inputs = piece.input_tokens
                    outputs = piece.output_tokens
                elif piece.kind == "error":
                    failed = True
                    break
                elif piece.kind == "done":
                    break
            if not failed:
                yield _sse({"usage": _usage_json(UpstreamResult(
                    "completed", "", inputs, outputs, ()
                ))})
                yield b"data: [DONE]\n\n"
        except ValidationError:
            failed = True
            raise
        finally:
            close = getattr(iterator, "close", None)
            if close is not None:
                close()
            self._account(
                principal, model,
                UpstreamResult(
                    "failed" if failed else "completed", "", inputs, outputs, ()
                ),
                max(0, int((time.monotonic() - started) * 1000)),
                now,
                failed=failed,
            )
            self._leave(principal.user_id)

    def me(self, principal: Principal) -> dict[str, object]:
        access = self._access(principal)
        binding = self.directory.binding_state(principal.user_id)
        return {
            "user_id": principal.user_id,
            "client_id": principal.client_id,
            "auth_method": principal.auth_method,
            "inference_access": access["inference_access"],
            "model_selection": access["model_selection"],
            "workspace": access["workspace"],
            "mcp_use": access["mcp_use"],
            "mcp_connect": access["mcp_connect"],
            "agent_use": access["agent_use"],
            "agent_builder": access["agent_builder"],
            "api_credential": access["api_credential"],
            "binding_status": binding["status"],
            "accounting_team_id": access["accounting_team_id"],
        }

    def my_usage(self, principal: Principal, period: str, now: datetime) -> dict[str, object]:  # noqa: E501
        self._require_scope(principal, "self_usage")
        return self.ledger.user_usage(principal.user_id, period=period, now=now)

    def mcp_call(
        self,
        principal: Principal,
        server_id: str,
        payload: dict[str, object],
        *,
        now: datetime,
        upstream_authorization: str | None = None,
    ) -> dict[str, object]:
        self._require_scope(principal, "mcp")
        access = self._access(principal)
        if access["mcp_use"] != "allow":
            self.ledger.audit(now, "mcp.access_denied", principal.user_id, server_id)
            raise ValidationError("mcp_access_denied")
        server = self.ledger.server(server_id)
        if server is None:
            raise ValidationError("mcp_access_denied")
        endpoint = str(server["endpoint"])
        assert_endpoint(
            endpoint,
            approved_urls=frozenset({endpoint}),
            approved_authorities=frozenset(),
        )
        method = str(payload.get("method", ""))
        if method == "tools/call" and access["mcp_use"] != "allow":
            raise ValidationError("mcp_access_denied")
        try:
            return forward_json(endpoint, payload, upstream_authorization)
        except ValidationError as exc:
            self.ledger.audit(now, "mcp.access_denied", principal.user_id, exc.message)
            raise

    def _prepare(
        self, principal: Principal, body: dict[str, object]
    ) -> tuple[list[dict[str, str]], str, int]:
        access = self._access(principal)
        if access["platform_access"] != "allow":
            raise ValidationError("platform_access_denied")
        if access["inference_access"] != "allow":
            raise ValidationError("inference_access_denied")
        self._require_scope(principal, "inference")
        self.upstream.refresh()
        if self.upstream.model_id is None:
            raise ValidationError("no_ready_model")
        requested = body.get("model", self.upstream.model_id)
        if not isinstance(requested, str) or requested != self.upstream.model_id:
            raise ValidationError("model_not_allowed")
        messages = _messages(body)
        limit = body.get("max_tokens", 16)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValidationError("overloaded")
        if limit > self.max_tokens:
            limit = self.max_tokens
        return messages, requested, limit

    def _access(self, principal: Principal) -> dict[str, object]:
        access = self.directory.effective(principal.user_id)
        if access["status"] != "active":
            raise ValidationError("user_suspended")
        return access

    def _enter(self, user_id: str) -> None:
        with self._lock:
            if self._inflight >= self.max_global or self._users.get(user_id, 0) >= self.max_user:  # noqa: E501
                raise ValidationError("overloaded")
            self._inflight += 1
            self._users[user_id] = self._users.get(user_id, 0) + 1

    def _leave(self, user_id: str) -> None:
        with self._lock:
            self._inflight = max(0, self._inflight - 1)
            self._users[user_id] = max(0, self._users.get(user_id, 0) - 1)

    def _account(
        self,
        principal: Principal,
        model: str,
        result: UpstreamResult,
        elapsed: int,
        now: datetime,
        *,
        failed: bool,
    ) -> str:
        request_id = "greq_" + secrets.token_hex(8)
        usage_id = "usg_" + hashlib.sha256(request_id.encode()).hexdigest()[:16]
        outcome = "failed" if failed or result.outcome != "completed" else "completed"
        view = project_admin(self.store_root, self.build)
        chain = view.chain
        inference = InferenceUsage(
            usage_id=usage_id,
            request_id=request_id,
            occurred_at=now.isoformat(),
            purpose="user_request",
            install_id=view.install_id or USAGE_UNRECORDED,
            instance_id=self.upstream.instance_id,
            plan_id=chain.plan_id,
            reservation_id=chain.reservation_id,
            generation_id=chain.generation_id,
            model_identity=model,
            model_identity_kind="warehouse_artifact",
            macropath=self.upstream.macropath,
            outcome=outcome,
            failure="none" if outcome == "completed" else "upstream_failure",
            status_code=200 if outcome == "completed" else 502,
            input_tokens=_count(result.input_tokens),
            output_tokens=_count(result.output_tokens),
            latency_ms=str(elapsed),
            runtime_duration_ms=USAGE_UNRECORDED,
            version=self.build.version,
            build_id=self.build.build_id or USAGE_UNRECORDED,
        )
        canonical = PrincipalUsage(
            usage_id=usage_id,
            request_id=request_id,
            user_id=principal.user_id,
            accounting_team_id=str(
                self.directory.accounting_team(principal.user_id)
            ),
            client_id=principal.client_id,
            auth_method=principal.auth_method,
            model_identity=model,
            macropath=self.upstream.macropath,
            instance_id=self.upstream.instance_id,
            input_tokens=_count(result.input_tokens),
            output_tokens=_count(result.output_tokens),
            latency_ms=str(elapsed),
            outcome=outcome,
            occurred_at=now.isoformat(),
        )
        stored = self.ledger.append_canonical(
            canonical,
            install_id=inference.install_id,
            plan_id=inference.plan_id,
            reservation_id=inference.reservation_id,
            generation_id=inference.generation_id,
            failure=inference.failure,
            status_code=inference.status_code,
            version=inference.version,
            build_id=inference.build_id,
        )
        if stored:
            self._project_usage()
        self.ledger.audit(now, "user.inference_allowed", principal.user_id, outcome)
        return usage_id

    def _require_scope(self, principal: Principal, scope: str) -> None:
        if principal.auth_method != "api_credential":
            return
        if scope not in principal.scopes:
            raise ValidationError("scope_denied")

    def _project_usage(self) -> None:
        """Idempotent telemetry projection. A failed projection stays pending."""
        for row in self.ledger.unprojected():
            if self.ledger.fail_projection:
                return
            inference = InferenceUsage(
                usage_id=str(row["usage_id"]),
                request_id=str(row["request_id"]),
                occurred_at=str(row["occurred_at"]),
                purpose="user_request",
                install_id=str(row["install_id"]),
                instance_id=str(row["instance_id"]),
                plan_id=str(row["plan_id"]),
                reservation_id=str(row["reservation_id"]),
                generation_id=str(row["generation_id"]),
                model_identity=str(row["model_identity"]),
                model_identity_kind="warehouse_artifact",
                macropath=str(row["macropath"]),
                outcome=str(row["outcome"]),
                failure=str(row["failure"]),
                status_code=int(row["status_code"]),
                input_tokens=str(row["input_tokens"]),
                output_tokens=str(row["output_tokens"]),
                latency_ms=str(row["latency_ms"]),
                runtime_duration_ms=USAGE_UNRECORDED,
                version=str(row["version"]),
                build_id=str(row["build_id"]),
            )
            if not self.telemetry.record_usage(inference):
                return
            self.ledger.mark_projected(str(row["usage_id"]))


def status_for(code: str) -> int:
    return _PUBLIC_ERRORS.get(code, 400)


def _upstream_request(port: int, body: bytes) -> urllib.request.Request:
    return urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )


def _sse_piece(line: str) -> StreamPiece | None:
    text = line.strip()
    if not text.startswith("data:"):
        return None
    payload = text[5:].strip()
    if payload == "[DONE]":
        return StreamPiece("done")
    try:
        document = json.loads(payload)
    except json.JSONDecodeError:
        return StreamPiece("error")
    if not isinstance(document, dict):
        return StreamPiece("error")
    if document.get("error"):
        return StreamPiece("error")
    prompt, completion = _usage_pair(document)
    delta = ""
    choices = document.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        item = choices[0].get("delta")
        if isinstance(item, dict) and isinstance(item.get("content"), str):
            delta = str(item["content"])
    if prompt is not None or completion is not None:
        return StreamPiece("usage", delta, prompt, completion)
    if delta:
        return StreamPiece("delta", delta)
    return None


def _chat_body(
    model: str, messages: list[dict[str, str]], max_tokens: int, stream: bool
) -> dict[str, object]:
    """vLLM rejects stream_options unless the request is actually streaming."""
    payload: dict[str, object] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if stream:
        payload["stream_options"] = {"include_usage": True}
    return payload


def _messages(body: dict[str, object]) -> list[dict[str, str]]:
    raw = body.get("messages")
    if not isinstance(raw, list) or not raw:
        raise ValidationError("overloaded")
    messages: list[dict[str, str]] = []
    size = 0
    for item in raw:
        if not isinstance(item, dict):
            raise ValidationError("overloaded")
        role = item.get("role")
        content = item.get("content")
        if role not in {"system", "user", "assistant"} or not isinstance(content, str):
            raise ValidationError("overloaded")
        size += len(content)
        if size > _MAX_MESSAGES:
            raise ValidationError("overloaded")
        messages.append({"role": role, "content": content})
    return messages


def _count(value: int | None) -> str:
    if value is None or value < 0:
        return USAGE_UNRECORDED
    return str(value)


def _completion(usage_id: str, model: str, result: UpstreamResult) -> dict[str, object]:
    return {
        "id": usage_id,
        "object": "chat.completion",
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": result.text}}],
        "usage": _usage_json(result),
    }


def _usage_json(result: UpstreamResult) -> dict[str, int | None]:
    prompt = result.input_tokens
    completion = result.output_tokens
    total = None
    if prompt is not None and completion is not None:
        total = prompt + completion
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def _sse(payload: dict[str, object]) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def _message_text(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ValidationError("upstream_failure")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValidationError("upstream_failure")
    message = choices[0].get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise ValidationError("upstream_failure")
    return str(message["content"])


def _usage_pair(payload: object) -> tuple[int | None, int | None]:
    if not isinstance(payload, dict) or not isinstance(payload.get("usage"), dict):
        return None, None
    usage = payload["usage"]
    return _optional_int(usage.get("prompt_tokens")), _optional_int(usage.get("completion_tokens"))  # noqa: E501


def _optional_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _parse_sse(raw: bytes) -> UpstreamResult:
    pieces: list[str] = []
    prompt: int | None = None
    completion: int | None = None
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line.startswith("data:") or line.strip() == "data: [DONE]":
            continue
        try:
            payload = json.loads(line[5:].strip())
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        usage = payload.get("usage")
        if isinstance(usage, dict):
            prompt = _optional_int(usage.get("prompt_tokens")) or prompt
            completion = _optional_int(usage.get("completion_tokens")) or completion
        choices = payload.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            delta = choices[0].get("delta")
            if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                pieces.append(str(delta["content"]))
    return UpstreamResult("completed", "".join(pieces), prompt, completion, tuple(pieces))  # noqa: E501
