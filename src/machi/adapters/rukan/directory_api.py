"""Loopback people actions. The directory stays on the customer host."""

from __future__ import annotations

from datetime import datetime

from machi.adapters.rukan.credentials import (
    issue_credential,
    list_credentials,
    revoke_credential,
)
from machi.adapters.rukan.directory import Directory
from machi.adapters.rukan.gateway_store import GatewayLedger
from machi.kernel.errors import ValidationError


def _text(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    return None


def people_action(
    directory: Directory, body: dict[str, object] | None, now: datetime
) -> tuple[str, str, dict[str, object]]:
    payload = body or {}
    action = str(payload.get("action", "list"))
    try:
        if action == "list":
            query = "" if body is None else str(payload.get("query", ""))
            return (
                "ok",
                "people",
                {
                    "users": directory.list_users(query),
                    "teams": directory.list_teams(query),
                    "enforcement": "rukan_user_gateway",
                    "banner": "The User Gateway enforces employee access. LibreChat is a replaceable workspace.",  # noqa: E501
                },
            )
        if action == "create_user":
            return ("ok", "user created", directory.create_user(
                email=str(payload.get("email", "")),
                display_name=str(payload.get("display_name", "")),
                actor="local_admin_ui",
                now=now,
            ))
        if action == "update_user":
            return ("ok", "user updated", directory.update_user(
                str(payload.get("user_id", "")),
                email=_text(payload, "email"),
                display_name=_text(payload, "display_name"),
                actor="local_admin_ui",
                now=now,
            ))
        if action == "set_status":
            return ("ok", "user status changed", directory.set_status(
                str(payload.get("user_id", "")),
                str(payload.get("status", "")),
                actor="local_admin_ui",
                now=now,
            ))
        if action == "create_team":
            return ("ok", "team created", directory.create_team(
                name=str(payload.get("name", "")),
                description=str(payload.get("description", "")),
                actor="local_admin_ui",
                now=now,
            ))
        if action == "update_team":
            return ("ok", "team updated", directory.update_team(
                str(payload.get("team_id", "")),
                name=_text(payload, "name"),
                description=_text(payload, "description"),
                actor="local_admin_ui",
                now=now,
            ))
        if action == "set_team_status":
            return ("ok", "team status changed", directory.set_team_status(
                str(payload.get("team_id", "")),
                str(payload.get("status", "")),
                actor="local_admin_ui",
                now=now,
            ))
        if action == "add_membership":
            return ("ok", "membership added", directory.add_membership(
                str(payload.get("user_id", "")),
                str(payload.get("team_id", "")),
                actor="local_admin_ui",
                now=now,
            ))
        if action == "remove_membership":
            return ("ok", "membership removed", directory.remove_membership(
                str(payload.get("user_id", "")),
                str(payload.get("team_id", "")),
                actor="local_admin_ui",
                now=now,
            ))
        if action == "set_intent":
            kind = str(payload.get("subject_kind", "user"))
            fallback = "inherit" if kind == "user" else "deny"
            return ("ok", "access intent saved", directory.set_intent(
                subject_kind=kind,
                subject_id=str(payload.get("subject_id", "")),
                platform_access=str(payload.get("platform_access", fallback)),
                inference_access=str(payload.get("inference_access", fallback)),
                model_selection=str(payload.get("model_selection", fallback)),
                agent_builder=str(payload.get("agent_builder", fallback)),
                agent_use=_text(payload, "agent_use"),
                api_credential=_text(payload, "api_credential"),
                workspace=_text(payload, "workspace"),
                mcp_use=_text(payload, "mcp_use"),
                mcp_connect=_text(payload, "mcp_connect"),
                actor="local_admin_ui",
                now=now,
            ))
        if action == "reset_binding":
            reset = directory.reset_binding(
                str(payload.get("user_id", "")),
                actor="local_admin_ui",
                now=now,
            )
            return ("ok", "identity binding reset", dict(reset))
        if action == "issue_credential":
            raw_scopes = payload.get("scopes", ["inference", "models", "self_usage"])
            scopes = tuple(
                item for item in raw_scopes if isinstance(item, str)
            ) if isinstance(raw_scopes, list) else ()
            ttl = payload.get("ttl_seconds", 86400)
            if isinstance(ttl, bool) or not isinstance(ttl, int):
                ttl = 86400
            issued = issue_credential(
                directory,
                user_id=str(payload.get("user_id", "")),
                label=str(payload.get("client_label", "generic")),
                scopes=scopes,
                ttl_seconds=ttl,
                now=now,
                actor="local_admin_ui",
            )
            return ("ok", "credential issued", issued)
        if action == "revoke_credential":
            revoked = revoke_credential(
                directory,
                user_id=str(payload.get("user_id", "")),
                key_id=str(payload.get("key_id", "")),
                now=now,
                actor="local_admin_ui",
            )
            return ("ok", "credential revoked", dict(revoked))
        if action == "list_credentials":
            user_id = str(payload.get("user_id", ""))
            return ("ok", "credentials", {
                "credentials": list_credentials(directory, user_id),
            })
        if action == "approve_mcp":
            ledger = GatewayLedger(directory.store_root)
            try:
                saved = ledger.approve_server(
                    server_id=str(payload.get("server_id", "")),
                    display_name=str(payload.get("display_name", "")),
                    endpoint=str(payload.get("endpoint", "")),
                    auth_method=str(payload.get("auth_method", "none")),
                    sensitivity=str(payload.get("sensitivity", "internal")),
                    now=now,
                )
            finally:
                ledger.close()
            return ("ok", "mcp server approved", saved)
        if action == "effective":
            return ("ok", "effective access", directory.effective(str(payload.get("user_id", ""))))  # noqa: E501
    except ValidationError as exc:
        return ("refused", exc.message, {})
    return ("refused", "people action is unknown", {})
