from unittest import TestCase
from unittest.mock import patch

from core.health import check_service_health


def make_service(provider):
    return {
        "id": "health-test",
        "provider": provider,
        "enabled": True,
        "spec": {
            "network": {
                "host": "127.0.0.1",
                "port": 8000,
            },
        },
    }


def http_result(*, ok, status_code=200, body=b"", error=None):
    return {
        "ok": ok,
        "status_code": status_code,
        "body": body,
        "error": error,
    }


class ServiceHealthTests(TestCase):
    def test_vllm_is_healthy_when_models_are_returned(self):
        service = make_service("vllm")
        result = http_result(
            ok=True,
            body=b'{"data":[{"id":"local-llm"}]}',
        )

        with patch("core.health.http_get", return_value=result) as http_get:
            health = check_service_health(service)

        http_get.assert_called_once_with(
            "http://127.0.0.1:8000/v1/models",
        )
        self.assertEqual(
            health,
            {
                "service": "health-test",
                "provider": "vllm",
                "healthy": True,
                "detail": "OpenAI-compatible API ready; models: ['local-llm']",
            },
        )

    def test_vllm_is_unhealthy_when_http_get_fails(self):
        service = make_service("vllm")
        result = http_result(
            ok=False,
            status_code=None,
            error="connection refused",
        )

        with patch("core.health.http_get", return_value=result):
            health = check_service_health(service)

        self.assertFalse(health["healthy"])
        self.assertEqual(health["detail"], "connection refused")

    def test_vllm_is_unhealthy_when_model_response_is_invalid_json(self):
        service = make_service("vllm")
        result = http_result(ok=True, body=b"not-json")

        with patch("core.health.http_get", return_value=result):
            health = check_service_health(service)

        self.assertFalse(health["healthy"])
        self.assertEqual(
            health["detail"],
            "API responded but returned unexpected model data.",
        )

    def test_builtin_proxy_is_healthy_at_the_live_endpoint(self):
        service = make_service("builtin_proxy")

        with patch(
            "core.health.http_get",
            return_value=http_result(ok=True),
        ) as http_get:
            health = check_service_health(service)

        http_get.assert_called_once_with("http://127.0.0.1:8000/live")
        self.assertTrue(health["healthy"])
        self.assertEqual(health["detail"], "HTTP 200")

    def test_builtin_proxy_is_unhealthy_when_the_live_endpoint_fails(self):
        service = make_service("builtin_proxy")

        with patch(
            "core.health.http_get",
            return_value=http_result(
                ok=False,
                status_code=None,
                error="connection refused",
            ),
        ):
            health = check_service_health(service)

        self.assertFalse(health["healthy"])
        self.assertEqual(health["detail"], "connection refused")

    def test_builtin_http_is_healthy_at_the_live_endpoint(self):
        service = make_service("builtin_http")

        with patch(
            "core.health.http_get",
            return_value=http_result(ok=True),
        ) as http_get:
            health = check_service_health(service)

        http_get.assert_called_once_with("http://127.0.0.1:8000/live")
        self.assertTrue(health["healthy"])
        self.assertEqual(health["detail"], "HTTP 200")

    def test_builtin_http_is_unhealthy_when_the_live_endpoint_fails(self):
        service = make_service("builtin_http")

        with patch(
            "core.health.http_get",
            return_value=http_result(
                ok=False,
                status_code=None,
                error="connection refused",
            ),
        ):
            health = check_service_health(service)

        self.assertFalse(health["healthy"])
        self.assertEqual(health["detail"], "connection refused")

    def test_openwebui_is_healthy_at_the_base_url(self):
        service = make_service("openwebui")

        with patch(
            "core.health.http_get",
            return_value=http_result(ok=True),
        ) as http_get:
            health = check_service_health(service)

        http_get.assert_called_once_with("http://127.0.0.1:8000")
        self.assertTrue(health["healthy"])
        self.assertEqual(health["detail"], "HTTP 200")

    def test_openwebui_is_unhealthy_when_the_base_url_fails(self):
        service = make_service("openwebui")

        with patch(
            "core.health.http_get",
            return_value=http_result(
                ok=False,
                status_code=None,
                error="connection refused",
            ),
        ):
            health = check_service_health(service)

        self.assertFalse(health["healthy"])
        self.assertEqual(health["detail"], "connection refused")

    def test_unknown_provider_is_unhealthy_without_a_probe(self):
        service = make_service("unknown-provider")

        with patch("core.health.http_get") as http_get:
            health = check_service_health(service)

        http_get.assert_not_called()
        self.assertFalse(health["healthy"])
        self.assertEqual(
            health["detail"],
            "No health probe is defined for this provider yet.",
        )
