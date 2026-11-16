import json
import os
import secrets
from pathlib import Path

from adapters.gateway import (
    resolve_gateway_endpoint,
)


def _openai_base_url(gateway_endpoint):
    base = gateway_endpoint.rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def render_librechat_yaml(
    gateway_endpoint,
    model_name="default",
):
    base_url = _openai_base_url(gateway_endpoint)
    return (
        "version: 1.2.1\n"
        "cache: true\n"
        "endpoints:\n"
        "  custom:\n"
        "    - name: \"Local AI Stack\"\n"
        "      apiKey: \"none\"\n"
        f"      baseURL: \"{base_url}\"\n"
        "      models:\n"
        "        default:\n"
        f"          - \"{model_name}\"\n"
        "        fetch: true\n"
        "      titleConvo: true\n"
        "      titleModel: \"current_model\"\n"
        "      modelDisplayLabel: \"Local AI Stack\"\n"
    )


def write_librechat_config(
    data_dir,
    gateway_endpoint,
    model_name="default",
):
    target_dir = Path(data_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    config_path = target_dir / "librechat.yaml"
    config_path.write_text(
        render_librechat_yaml(
            gateway_endpoint,
            model_name=model_name,
        ),
        encoding="utf-8",
    )
    return str(config_path)


def build_service_spec(plan, config):
    frontend = plan["frontend"]
    network = config["network"]

    if not frontend["enabled"]:
        return None

    gateway_endpoint = (
        resolve_gateway_endpoint(
            plan,
            config,
        )
    )

    data_root = config["platform"]["data_root"]
    data_dir = f"{data_root}/librechat-data"

    return {
        "role": "frontend",
        "provider": "librechat",
        "network": {
            "host": network["frontend_host"],
            "port": network["frontend_port"],
        },
        "upstream": gateway_endpoint,
        "data_dir": data_dir,
        "mongo_data_dir": f"{data_root}/librechat-mongo",
        "config_path": f"{data_dir}/librechat.yaml",
    }


def ensure_librechat_secrets(data_dir):
    target_dir = Path(data_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    secrets_path = target_dir / "librechat-secrets.json"
    if secrets_path.exists():
        return json.loads(secrets_path.read_text(encoding="utf-8"))
    generated = {
        "CREDS_KEY": secrets.token_hex(16),
        "CREDS_IV": secrets.token_hex(8),
        "JWT_SECRET": secrets.token_hex(32),
        "JWT_REFRESH_SECRET": secrets.token_hex(32),
    }
    secrets_path.write_text(json.dumps(generated, indent=2), encoding="utf-8")
    os.chmod(secrets_path, 0o600)
    return generated
    
