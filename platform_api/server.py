import json
from urllib.parse import parse_qs, urlsplit
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)

from core.config import load_config
from core.models import list_local_models
from core.model_catalog import list_catalog_models
from core.model_inventory import list_model_inventory
from core.platform_state import build_platform_state
from core.analytics import filter_usage_events, summarize_usage
from adapters.usage_store import get_usage_store_adapter
from core.control import (
    restart_workload,
    download_inventory_model,
    import_inventory_model,
    delete_inventory_model,
    update_inventory_model,
)


def build_response(path, query=None):
    query = query or {}

    """
    Read-only Platform API v1.

    PROVISIONAL TRANSPORT:
    Uses Python's built-in HTTP server for the first vertical slice.

    The API concept and resource boundaries should remain stable even
    if the HTTP framework is replaced later.
    """

    # This endpoint intentionally does NOT build platform state.
    # It is used by the platform to check the API itself without
    # recursively probing /health.
    if path == "/live":
        return {
            "status": "ok",
        }

    if path == "/analytics/summary":
        config = load_config()

        analytics = config.get(
            "analytics",
            {},
        )

        if not analytics.get(
            "enabled",
            False,
        ):
            return {
                "enabled": False,
                "summary": None,
            }

        usage_store = (
            get_usage_store_adapter(
                analytics["provider"]
            )
        )

        events = (
            usage_store.list_events(
                config
            )
        )

        def first(name):
            values = query.get(
                name,
                [],
            )

            return (
                values[0]
                if values
                else None
            )

        filters = {
            "start": first("start"),
            "end": first("end"),
            "model": first("model"),
            "provider": first(
                "provider"
            ),
        }

        filtered_events = (
            filter_usage_events(
                events,
                **filters,
            )
        )

        return {
            "enabled": True,

            "provider": analytics[
                "provider"
            ],

            "filters": filters,

            "matched_events": len(
                filtered_events
            ),

            "summary": summarize_usage(
                filtered_events
            ),
        }

    state = build_platform_state()

    if path == "/health":
        services = state["deployment"]["services"]

        unhealthy = [
            service
            for service in services
            if (
                service["enabled"]
                and service["health"]["healthy"] is not True
            )
        ]

        return {
            "platform_api": "ok",
            "deployment_healthy": not unhealthy,
        }

    if path == "/state":
        return state

    if path == "/hardware":
        return state["hardware"]

    if path == "/inventory/models":
        return list_model_inventory()

    if path == "/catalog/models":
        config = load_config()

        def catalog_first(name):
            values = query.get(
                name,
                [],
            )

            return (
                values[0]
                if values
                else None
            )

        return list_catalog_models(
            config,
            search=(
                catalog_first(
                    "search"
                )
            ),
            source=(
                catalog_first(
                    "source"
                )
            ),
            limit=(
                catalog_first(
                    "limit"
                )
            ),
        )

    if path == "/models":
        return {
            "models": list_local_models(),
        }

    if path == "/deployment":
        return state["deployment"]

    return None


class PlatformAPIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlsplit(
            self.path
        )

        path = parsed.path

        query = parse_qs(
            parsed.query
        )

        try:
            payload = build_response(
                path,
                query=query,
            )

            if payload is None:
                self.send_json(
                    404,
                    {
                        "error": "not_found",
                        "path": path,
                    },
                )
                return

            self.send_json(
                200,
                payload,
            )

        except Exception as exc:
            self.send_json(
                500,
                {
                    "error": "internal_error",
                    "detail": str(exc),
                },
            )


    def read_json_body(self):
        """
        Read one small JSON request body.

        PROVISIONAL:
        The built-in HTTP server remains our transport layer.
        """

        raw_length = self.headers.get(
            "Content-Length",
            "0",
        )

        try:
            length = int(
                raw_length
            )
        except ValueError as exc:
            raise ValueError(
                "Invalid Content-Length."
            ) from exc

        if length <= 0:
            raise ValueError(
                "JSON request body is required."
            )

        if length > 65536:
            raise ValueError(
                "Request body is too large."
            )

        raw = self.rfile.read(
            length
        )

        try:
            payload = json.loads(
                raw.decode("utf-8")
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise ValueError(
                "Request body must be valid JSON."
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise ValueError(
                "JSON body must be an object."
            )

        return payload


    def do_POST(self):
        path = self.path.split("?", 1)[0]

        try:
            # PHASE8_CAPACITY_PLANNER_V1_ROUTE
            if path == "/capacity/models/feasibility":
                try:
                    request = (
                        self.read_json_body()
                    )

                except ValueError as exc:
                    self.send_json(
                        400,
                        {
                            "error": (
                                "invalid_request"
                            ),

                            "detail": (
                                str(
                                    exc
                                )
                            ),
                        },
                    )
                    return


                model_id = (
                    request.get(
                        "model_id"
                    )
                )


                if not model_id:
                    self.send_json(
                        400,
                        {
                            "error": (
                                "invalid_request"
                            ),

                            "detail": (
                                "Missing required field: model_id"
                            ),
                        },
                    )
                    return


                from core.model_feasibility import (
                    evaluate_inventory_model_feasibility,
                )


                result = (
                    evaluate_inventory_model_feasibility(
                        model_id=(
                            model_id
                        )
                    )
                )


                if result[
                    "ok"
                ]:
                    self.send_json(
                        200,
                        result,
                    )
                    return


                code = (
                    result[
                        "error"
                    ][
                        "code"
                    ]
                )


                status = {
                    "not_found": 404,
                    "feasibility_failed": 500,
                }.get(
                    code,
                    500,
                )


                self.send_json(
                    status,
                    result,
                )

                return


            if path == "/inventory/models/update":
                try:
                    request = self.read_json_body()

                except ValueError as exc:
                    self.send_json(
                        400,
                        {
                            "error": "invalid_request",
                            "detail": str(exc),
                        },
                    )
                    return

                model_id = request.get(
                    "model_id"
                )

                revision = (
                    request.get(
                        "revision"
                    )
                    or "main"
                )

                if not model_id:
                    self.send_json(
                        400,
                        {
                            "error": "invalid_request",
                            "detail": (
                                "Missing required field: model_id"
                            ),
                        },
                    )
                    return

                result = update_inventory_model(
                    model_id=model_id,
                    revision=revision,
                )

                if result["ok"]:
                    self.send_json(
                        200,
                        result,
                    )
                    return

                code = result[
                    "error"
                ][
                    "code"
                ]

                status = {
                    "not_found": 404,
                    "unmanaged_model": 409,
                    "model_selected": 409,
                    "model_running": 409,
                    "model_loaded": 409,
                    "update_not_supported": 409,
                    "source_missing": 409,
                    "transfer_disabled": 409,
                    "provider_not_enabled": 400,
                    "unsafe_path": 409,
                    "artifact_missing": 409,
                    "invalid_artifact": 409,
                    "metadata_missing": 409,
                    "update_failed": 500,

                    # Capacity/serialization/preflight failures.
                    "storage_admission_denied": 507,
                    "storage_operation_busy": 409,
                    "storage_preflight_failed": 503,
                }.get(
                    code,
                    500,
                )

                self.send_json(
                    status,
                    result,
                )
                return

            if path == "/inventory/models/delete":
                try:
                    request = self.read_json_body()

                except ValueError as exc:
                    self.send_json(
                        400,
                        {
                            "error": "invalid_request",
                            "detail": str(exc),
                        },
                    )
                    return

                model_id = request.get(
                    "model_id"
                )

                if not model_id:
                    self.send_json(
                        400,
                        {
                            "error": "invalid_request",
                            "detail": (
                                "Missing required field: model_id"
                            ),
                        },
                    )
                    return

                result = delete_inventory_model(
                    model_id=model_id
                )

                if result["ok"]:
                    self.send_json(
                        200,
                        result,
                    )
                    return

                code = (
                    result[
                        "error"
                    ][
                        "code"
                    ]
                )

                status = {
                    "not_found": 404,
                    "unmanaged_model": 409,
                    "model_selected": 409,
                    "model_running": 409,
                    "model_loaded": 409,
                    "unsafe_path": 409,
                    "artifact_missing": 409,

                    # Delete frees capacity but still participates in
                    # the shared storage serialization boundary.
                    "storage_operation_busy": 409,
                }.get(
                    code,
                    500,
                )

                self.send_json(
                    status,
                    result,
                )
                return

            if path == "/inventory/models/import":
                try:
                    request = self.read_json_body()

                except ValueError as exc:
                    self.send_json(
                        400,
                        {
                            "error": "invalid_request",
                            "detail": str(exc),
                        },
                    )
                    return

                source_path = request.get(
                    "source_path"
                )

                target_name = request.get(
                    "target_name"
                )

                missing = []

                if not source_path:
                    missing.append(
                        "source_path"
                    )

                if not target_name:
                    missing.append(
                        "target_name"
                    )

                if missing:
                    self.send_json(
                        400,
                        {
                            "error": "invalid_request",
                            "detail": (
                                "Missing required fields: "
                                + ", ".join(missing)
                            ),
                        },
                    )
                    return

                result = import_inventory_model(
                    source_path=source_path,
                    target_name=target_name,
                )

                if result["ok"]:
                    self.send_json(
                        201,
                        result,
                    )
                else:
                    error_code = (
                        result[
                            "error"
                        ][
                            "code"
                        ]
                    )

                    status = {
                        "already_exists": 409,

                        # Storage capacity is known or currently
                        # unresolved and the mutation was refused.
                        "storage_admission_denied": 507,

                        # Another maintenance/storage mutation owns
                        # the shared serialization boundary.
                        "storage_operation_busy": 409,
                    }.get(
                        error_code,
                        500,
                    )

                    self.send_json(
                        status,
                        result,
                    )

                return

            if path == "/inventory/models/download":
                try:
                    request = (
                        self.read_json_body()
                    )

                except ValueError as exc:
                    self.send_json(
                        400,
                        {
                            "error": "invalid_request",
                            "detail": str(exc),
                        },
                    )
                    return

                provider = request.get(
                    "provider"
                )

                source_model_id = (
                    request.get(
                        "source_model_id"
                    )
                )

                revision = (
                    request.get(
                        "revision"
                    )
                    or "main"
                )

                target_name = (
                    request.get(
                        "target_name"
                    )
                )

                missing = []

                if not provider:
                    missing.append(
                        "provider"
                    )

                if not source_model_id:
                    missing.append(
                        "source_model_id"
                    )

                if missing:
                    self.send_json(
                        400,
                        {
                            "error": "invalid_request",

                            "detail": (
                                "Missing required fields: "
                                + ", ".join(
                                    missing
                                )
                            ),
                        },
                    )
                    return

                result = (
                    download_inventory_model(
                        provider=provider,
                        source_model_id=(
                            source_model_id
                        ),
                        revision=revision,
                        target_name=target_name,
                    )
                )

                if result["ok"]:
                    self.send_json(
                        201,
                        result,
                    )

                else:
                    error_code = (
                        result[
                            "error"
                        ][
                            "code"
                        ]
                    )

                    status = {
                        "already_exists": 409,
                        "provider_not_enabled": 400,

                        # Safe capacity refusal.
                        "storage_admission_denied": 507,

                        # Shared storage/maintenance lock conflict.
                        "storage_operation_busy": 409,

                        # Remote metadata/manifest could not provide
                        # commit-safe sizing.
                        "storage_preflight_failed": 503,

                        # Provider exists but has no explicit
                        # storage-safety implementation yet.
                        "storage_safety_not_implemented": 501,
                    }.get(
                        error_code,
                        500,
                    )

                    self.send_json(
                        status,
                        result,
                    )

                return

            if path == "/deployment/restart":
                result = restart_workload()

                self.send_json(
                    200 if result["ok"] else 500,
                    result,
                )
                return

            self.send_json(
                404,
                {
                    "error": "not_found",
                    "path": path,
                },
            )

        except Exception as exc:
            self.send_json(
                500,
                {
                    "error": "internal_error",
                    "detail": str(exc),
                },
            )


    def send_json(self, status, payload):
        body = json.dumps(
            payload,
            indent=2,
        ).encode("utf-8")

        self.send_response(status)
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


    def log_message(self, format, *args):
        # PROVISIONAL:
        # Keep API test output quiet for now.
        return


def run_server():
    config = load_config()

    api_config = config["platform_api"]

    host = api_config["host"]
    port = api_config["port"]

    server = ThreadingHTTPServer(
        (host, port),
        PlatformAPIHandler,
    )

    print(
        f"Platform API listening on "
        f"http://{host}:{port}"
    )

    server.serve_forever()


if __name__ == "__main__":
    run_server()
