"""LibreChat workspace adapter. Rukan does not import LibreChat or its database."""

from __future__ import annotations

from pathlib import Path

from machi.kernel.errors import ValidationError

LIBRECHAT_VERSION = "v0.8.8-rc4"
LIBRECHAT_COMMIT = "361553f3322d7b9bb547d0a9c2c5aaefc2934901"
LIBRECHAT_IMAGE = "ghcr.io/danny-avila/librechat"
LIBRECHAT_DIGEST = (
    "sha256:929f4491cb9a87d6beb02e9e9ce9a54d4ee05bc56b65b1debe5b1f28a327a4fb"
)
MONGO_IMAGE = "mongo:8.0.20"
_CAPABILITIES = {
    "chat": True,
    "streaming": True,
    "openai_usage_fields": True,
    "model_list_from_gateway": True,
    "oidc_access_token_header": True,
    "direct_serve_endpoint": False,
    "per_user_mcp_menu": False,
    "per_user_agent_acl": False,
    "agents": "client_local",
    "mcp_execution": "librechat_native_through_rukan_broker",
    "identity_authority": "rukan_gateway",
}


def capability_profile() -> dict[str, object]:
    """What this pinned release actually does. Unsupported items stay false."""
    return {
        "adapter": "librechat",
        "version": LIBRECHAT_VERSION,
        "commit": LIBRECHAT_COMMIT,
        "image": f"{LIBRECHAT_IMAGE}@{LIBRECHAT_DIGEST}",
        "capabilities": dict(_CAPABILITIES),
        "degraded": [
            "LibreChat cannot hide MCP servers per Rukan user without its database.",
            "The Rukan broker enforces MCP policy. The menu is not per-user.",
            "LibreChat agents stay in the workspace database and are not Rukan agents.",
        ],
    }


def require_supported(version: str, digest: str) -> None:
    if version != LIBRECHAT_VERSION or digest != LIBRECHAT_DIGEST:
        raise ValidationError("librechat version is not the pinned adapter release")


def render_config(
    *,
    gateway_url: str,
    mcp_servers: tuple[dict[str, str], ...] = (),
) -> str:
    """YAML that points LibreChat at the gateway and never at Serve."""
    if not gateway_url.startswith(("http://", "https://")):
        raise ValidationError("librechat gateway url is not absolute")
    if ":11434" in gateway_url or "vllm" in gateway_url.lower():
        raise ValidationError("librechat must not target a runtime endpoint")
    lines = [
        "version: 1.3.6",
        "cache: true",
        "interface:",
        "  modelSelect: true",
        "  agents:",
        "    use: true",
        "    create: true",
        "    share: false",
        "    public: false",
        "  mcpServers:",
        "    use: true",
        "    create: false",
        "    share: false",
        "    public: false",
        "endpoints:",
        "  custom:",
        "    - name: Rukan",
        "      apiKey: '${RUKAN_GATEWAY_PLACEHOLDER}'",
        f"      baseURL: '{gateway_url.rstrip('/')}/v1'",
        "      directEndpoint: true",
        "      models:",
        "        default: ['rukan']",
        "        fetch: true",
        "      titleConvo: false",
        "      headers:",
        "        Authorization: 'Bearer {{LIBRECHAT_OPENID_ACCESS_TOKEN}}'",
        "mcpServers:",
    ]
    if not mcp_servers:
        lines.append("  {}")
    for item in mcp_servers:
        lines.extend(
            [
                f"  {item['server_id']}:",
                "    type: streamable-http",
                f"    url: '{item['broker_url']}'",
                "    headers:",
                "      Authorization: 'Bearer {{LIBRECHAT_OPENID_ACCESS_TOKEN}}'",
            ]
        )
    return "\n".join(lines) + "\n"


def render_compose(*, config_dir: Path, gateway_url: str) -> str:
    """Managed pilot compose. The image is digest-pinned. Secrets stay in env files."""
    require_supported(LIBRECHAT_VERSION, LIBRECHAT_DIGEST)
    image = f"{LIBRECHAT_IMAGE}@{LIBRECHAT_DIGEST}"
    quoted = str(config_dir)
    return "\n".join(
        [
            "services:",
            "  librechat:",
            f"    image: {image}",
            "    env_file:",
            "      - .env",
            "    volumes:",
            f"      - {quoted}/librechat.yaml:/app/librechat.yaml:ro",
            "    depends_on:",
            "      - mongodb",
            "  mongodb:",
            f"    image: {MONGO_IMAGE}",
            f"# gateway: {gateway_url}",
            "",
        ]
    )
