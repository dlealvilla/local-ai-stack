import json
import time
import urllib.error
import urllib.request

from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)

from core.config import load_config
from core.identity import build_model_identity
from core.planner import build_initial_plan
from core.usage_pipeline import UsagePipeline
from core.usage import (
    build_usage_event,
    new_usage_event_id,
    utc_now,
)

from adapters.usage_export import get_usage_export_adapter
from adapters.usage_store import (
    get_usage_store_adapter,
)


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


class GatewayHandler(BaseHTTPRequestHandler):
    gateway_config = None
    model_identity = None
    usage_store = None
    usage_pipeline = None


    def do_GET(self):
        if self.path.split(
            "?",
            1,
        )[0] == "/live":

            body = b'{"status":"ok"}'

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "application/json",
            )

            self.send_header(
                "Content-Length",
                str(len(body)),
            )

            self.end_headers()
            self.wfile.write(body)

            return

        self.proxy_request()


    def do_POST(self):
        self.proxy_request()


    def record_event(
        self,
        **values,
    ):
        """
        Analytics failure must not break AI inference.
        """

        config = self.gateway_config

        if not config[
            "analytics"
        ]["enabled"]:
            return

        try:
            event = build_usage_event(
                **values
            )

            self.usage_pipeline.record(
                event
            )

        except Exception as exc:
            print(
                "Usage event recording failed:",
                exc,
                flush=True,
            )


    def proxy_request(self):
        config = self.gateway_config
        identity = self.model_identity

        event_id = new_usage_event_id()
        started_at = utc_now()
        timer_started = time.perf_counter()

        path = self.path.split(
            "?",
            1,
        )[0]

        network = config["network"]

        upstream = (
            f"http://{network['inference_host']}:"
            f"{network['inference_port']}"
            f"{self.path}"
        )

        content_length = int(
            self.headers.get(
                "Content-Length",
                "0",
            )
        )

        body = (
            self.rfile.read(
                content_length
            )
            if content_length
            else None
        )

        request_payload = {}

        if body:
            try:
                request_payload = json.loads(
                    body.decode("utf-8")
                )
            except Exception:
                request_payload = {}

        requested_model = (
            request_payload.get(
                "model"
            )
        )

        streaming = bool(
            request_payload.get(
                "stream",
                False,
            )
        )

        headers = {}

        for name, value in self.headers.items():
            if (
                name.lower()
                in HOP_BY_HOP_HEADERS
            ):
                continue

            headers[name] = value

        request = urllib.request.Request(
            upstream,
            data=body,
            headers=headers,
            method=self.command,
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=360,
            ) as response:

                status_code = response.status

                self.send_response(
                    status_code
                )

                self.send_header(
                    "X-AI-Stack-Request-ID",
                    event_id,
                )

                content_type = (
                    response.headers.get(
                        "Content-Type",
                        ""
                    )
                )

                for (
                    name,
                    value,
                ) in response.headers.items():

                    if (
                        name.lower()
                        in HOP_BY_HOP_HEADERS
                    ):
                        continue

                    self.send_header(
                        name,
                        value,
                    )

                self.end_headers()

                captured = bytearray()

                while True:
                    chunk = response.read(
                        8192
                    )

                    if not chunk:
                        break

                    self.wfile.write(
                        chunk
                    )

                    self.wfile.flush()

                    if (
                        "application/json"
                        in content_type
                        and len(captured)
                        < 10_000_000
                    ):
                        captured.extend(
                            chunk
                        )

                input_tokens = None
                output_tokens = None
                total_tokens = None

                if captured:
                    try:
                        response_payload = (
                            json.loads(
                                captured.decode(
                                    "utf-8"
                                )
                            )
                        )

                        usage = (
                            response_payload.get(
                                "usage"
                            )
                            or {}
                        )

                        input_tokens = (
                            usage.get(
                                "prompt_tokens"
                            )
                        )

                        output_tokens = (
                            usage.get(
                                "completion_tokens"
                            )
                        )

                        total_tokens = (
                            usage.get(
                                "total_tokens"
                            )
                        )

                    except Exception:
                        pass

                latency_ms = (
                    time.perf_counter()
                    - timer_started
                ) * 1000

                self.record_event(
                    event_id=event_id,
                    started_at=started_at,
                    method=self.command,
                    path=path,
                    requested_model=(
                        requested_model
                    ),
                    actual_model=(
                        identity.get(
                            "model_id"
                        )
                        if identity
                        else None
                    ),
                    logical_model=(
                        identity.get(
                            "logical_name"
                        )
                        if identity
                        else None
                    ),
                    provider=(
                        identity.get(
                            "provider"
                        )
                        if identity
                        else None
                    ),
                    service_id="gateway",
                    status_code=status_code,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    streaming=streaming,
                    error=None,
                )

        except urllib.error.HTTPError as exc:
            payload = exc.read()

            latency_ms = (
                time.perf_counter()
                - timer_started
            ) * 1000

            self.send_response(
                exc.code
            )

            self.send_header(
                "X-AI-Stack-Request-ID",
                event_id,
            )

            self.send_header(
                "Content-Type",
                exc.headers.get(
                    "Content-Type",
                    "application/json",
                ),
            )

            self.send_header(
                "Content-Length",
                str(len(payload)),
            )

            self.end_headers()
            self.wfile.write(payload)

            self.record_event(
                event_id=event_id,
                started_at=started_at,
                method=self.command,
                path=path,
                requested_model=(
                    requested_model
                ),
                actual_model=(
                    identity.get(
                        "model_id"
                    )
                    if identity
                    else None
                ),
                logical_model=(
                    identity.get(
                        "logical_name"
                    )
                    if identity
                    else None
                ),
                provider=(
                    identity.get(
                        "provider"
                    )
                    if identity
                    else None
                ),
                service_id="gateway",
                status_code=exc.code,
                latency_ms=latency_ms,
                streaming=streaming,
                error="upstream_http_error",
            )

        except Exception as exc:
            latency_ms = (
                time.perf_counter()
                - timer_started
            ) * 1000

            payload = json.dumps({
                "error": (
                    "gateway_upstream_error"
                ),
                "detail": str(exc),
            }).encode("utf-8")

            self.send_response(502)

            self.send_header(
                "X-AI-Stack-Request-ID",
                event_id,
            )

            self.send_header(
                "Content-Type",
                "application/json",
            )

            self.send_header(
                "Content-Length",
                str(len(payload)),
            )

            self.end_headers()
            self.wfile.write(payload)

            self.record_event(
                event_id=event_id,
                started_at=started_at,
                method=self.command,
                path=path,
                requested_model=(
                    requested_model
                ),
                actual_model=(
                    identity.get(
                        "model_id"
                    )
                    if identity
                    else None
                ),
                logical_model=(
                    identity.get(
                        "logical_name"
                    )
                    if identity
                    else None
                ),
                provider=(
                    identity.get(
                        "provider"
                    )
                    if identity
                    else None
                ),
                service_id="gateway",
                status_code=502,
                latency_ms=latency_ms,
                streaming=streaming,
                error=str(exc),
            )


    def log_message(
        self,
        format,
        *args,
    ):
        return


def run_server():
    config = load_config()
    plan = build_initial_plan()

    model_identity = build_model_identity(
        plan,
        config,
    )

    analytics = config["analytics"]

    usage_store = get_usage_store_adapter(
        analytics["provider"]
    )

    usage_exporter = (
        get_usage_export_adapter(
            analytics.get(
                "export_provider",
                "disabled",
            )
        )
    )

    usage_pipeline = UsagePipeline(
        config=config,
        usage_store=usage_store,
        usage_exporter=usage_exporter,
    )

    retention_result = (
        usage_pipeline.apply_retention_if_due(
            force=True
        )
    )

    print(
        "Analytics retention:",
        retention_result,
        flush=True,
    )

    GatewayHandler.gateway_config = config
    GatewayHandler.model_identity = (
        model_identity
    )
    GatewayHandler.usage_store = (
        usage_store
    )

    GatewayHandler.usage_pipeline = (
        usage_pipeline
    )

    network = config["network"]

    host = network["api_host"]
    port = network["api_port"]

    server = ThreadingHTTPServer(
        (host, port),
        GatewayHandler,
    )

    print(
        f"AI Gateway listening on "
        f"http://{host}:{port}",
        flush=True,
    )

    print(
        "Usage analytics:",
        (
            analytics["provider"]
            if analytics["enabled"]
            else "disabled"
        ),
        flush=True,
    )

    server.serve_forever()


if __name__ == "__main__":
    run_server()
