"""Loopback people actions. The directory stays on the customer host."""

from __future__ import annotations

from datetime import datetime

from machi.adapters.rukan.directory import Directory
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
                    "enforcement": "gateway_not_available",
                    "banner": "Employee login and chat are not enabled yet.",
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
                actor="local_admin_ui",
                now=now,
            ))
        if action == "effective":
            return ("ok", "effective access", directory.effective(str(payload.get("user_id", ""))))  # noqa: E501
    except ValidationError as exc:
        return ("refused", exc.message, {})
    return ("refused", "people action is unknown", {})
