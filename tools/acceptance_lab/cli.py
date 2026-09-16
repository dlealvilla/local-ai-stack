"""Development-only acceptance lab CLI. No Pod mutation commands."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

from tools.acceptance_lab.db import initialize, schema_version
from tools.acceptance_lab.ids import stable_id
from tools.acceptance_lab.import_historical import import_historical_nvidia
from tools.acceptance_lab.import_preflight import import_control_plane_preflight
from tools.acceptance_lab.paths import default_db_path, repository_root
from tools.acceptance_lab.policy import CURRENT_POLICY
from tools.acceptance_lab.recording import record_campaign, record_policy
from tools.acceptance_lab.register_candidate import (
    NVIDIA_AMD_SETTINGS,
    record_checkpoint,
    record_local_gate_run,
    register_candidate,
)
from tools.acceptance_lab.report import campaign_report, dump_json, render_markdown
from tools.acceptance_lab.store import fetch_all, fetch_one
from tools.acceptance_lab.timeutil import UTC, format_utc

_POD_VERBS = frozenset(
    {"create-pod", "start-pod", "stop-pod", "terminate-pod", "pod-create"}
)


def _db(args: argparse.Namespace) -> sqlite3.Connection:
    path = Path(args.db) if args.db else default_db_path()
    return initialize(path)


def cmd_init(args: argparse.Namespace) -> int:
    connection = _db(args)
    version = schema_version(connection)
    row = connection.execute("PRAGMA database_list").fetchone()
    path = row["file"] if row is not None else ""
    sys.stdout.write(f"initialized schema_version={version} path={path}\n")
    return 0


def cmd_schema_version(args: argparse.Namespace) -> int:
    connection = _db(args)
    sys.stdout.write(f"{schema_version(connection)}\n")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    root = repository_root()
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    connection = _db(args)
    version = schema_version(connection)
    enabled = connection.execute("PRAGMA foreign_keys").fetchone()
    problems: list[str] = []
    if ".local/machi-acceptance/" not in gitignore:
        problems.append("gitignore missing .local/machi-acceptance/")
    if int(enabled[0]) != 1:
        problems.append("foreign_keys pragma is not ON")
    machi_hits = []
    for path in (root / "src" / "machi").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "acceptance_lab" in text:
            machi_hits.append(str(path.relative_to(root)))
    if machi_hits:
        problems.append("src/machi references acceptance_lab: " + ", ".join(machi_hits))
    if problems:
        sys.stderr.write("doctor FAIL\n")
        for item in problems:
            sys.stderr.write(f"- {item}\n")
        return 1
    sys.stdout.write(
        f"doctor OK schema_version={version} foreign_keys=ON "
        f"product_boundary=clean gitignore=ok sqlite={sqlite3.sqlite_version}\n"
    )
    return 0


def cmd_import_historical(args: argparse.Namespace) -> int:
    connection = _db(args)
    nvidia = import_historical_nvidia(connection)
    preflight = import_control_plane_preflight(connection)
    payload = json.dumps({"nvidia": nvidia, "preflight": preflight}, indent=2)
    sys.stdout.write(payload + "\n")
    return 0


def cmd_campaign_create(args: argparse.Namespace) -> int:
    connection = _db(args)
    when = dt.datetime.now(UTC)
    campaign_id = stable_id("camp", args.name, format_utc(when))
    record_campaign(
        connection,
        campaign_id=campaign_id,
        name=args.name,
        purpose=args.purpose,
        status="planned",
        when=when,
        provider_scope={
            "nvidia": "ACTIVE",
            "amd": "ACTIVE",
            "intel": "OUT",
            "apple": "CODE_RETAINED_NOT_ACCEPTED_PHYSICAL_DEFERRED",
        },
        notes=args.notes or "",
        historical_import=False,
    )
    policy_id = record_policy(
        connection, campaign_id=campaign_id, policy=CURRENT_POLICY, when=when
    )
    connection.commit()
    sys.stdout.write(f"{campaign_id} policy={policy_id}\n")
    return 0


def cmd_policy_show(args: argparse.Namespace) -> int:
    connection = _db(args)
    if args.campaign:
        row = fetch_one(
            connection,
            "SELECT * FROM policy_snapshot WHERE campaign_id = ? "
            "ORDER BY created_at_utc DESC LIMIT 1",
            (args.campaign,),
        )
        if row is None:
            sys.stderr.write("no policy snapshot\n")
            return 1
        sys.stdout.write(json.dumps(dict(row), indent=2) + "\n")
        return 0
    sys.stdout.write(json.dumps(CURRENT_POLICY, indent=2, sort_keys=True) + "\n")
    return 0


def cmd_candidate_register(args: argparse.Namespace) -> int:
    connection = _db(args)
    when = dt.datetime.now(UTC)
    implemented = [item.strip() for item in args.implemented.split(",") if item.strip()]
    accepted = [item.strip() for item in args.accepted.split(",") if item.strip()]
    candidate_id = register_candidate(
        connection,
        wheel=Path(args.wheel),
        implementation_commit=args.implementation_commit,
        evidence_commit=args.evidence_commit,
        branch=args.branch,
        package_version=args.package_version,
        build_id=args.build_id,
        qualification_state=args.qualification_state,
        provider_set=implemented,
        accepted_provider_target=accepted,
        notes=args.notes,
        settings=NVIDIA_AMD_SETTINGS,
        when=when,
        artifact_path=args.artifact_path,
    )
    connection.commit()
    sys.stdout.write(f"{candidate_id}\n")
    return 0


def cmd_record_local_run(args: argparse.Namespace) -> int:
    connection = _db(args)
    gates = json.loads(Path(args.gates_json).read_text(encoding="utf-8"))
    if not isinstance(gates, list):
        sys.stderr.write("gates JSON must be an array\n")
        return 1
    run_id = record_local_gate_run(
        connection,
        campaign_id=args.campaign,
        candidate_id=args.candidate,
        scenario_name=args.scenario,
        status=args.status,
        gates=gates,
        notes=args.notes or "",
    )
    connection.commit()
    sys.stdout.write(f"{run_id}\n")
    return 0


def cmd_checkpoint_record(args: argparse.Namespace) -> int:
    connection = _db(args)
    checkpoint_id = record_checkpoint(
        connection,
        campaign_id=args.campaign,
        candidate_id=args.candidate,
        name=args.name,
        git_tag=args.git_tag,
        git_commit=args.git_commit,
        semantic_meaning=args.meaning,
        notes=args.notes or "",
    )
    connection.commit()
    sys.stdout.write(f"{checkpoint_id}\n")
    return 0


def cmd_candidate_show(args: argparse.Namespace) -> int:
    connection = _db(args)
    if args.sha:
        row = fetch_one(
            connection,
            "SELECT * FROM candidate WHERE artifact_sha256 = ?",
            (args.sha,),
        )
    else:
        row = fetch_one(
            connection,
            "SELECT * FROM candidate WHERE candidate_id = ?",
            (args.id,),
        )
    if row is None:
        sys.stderr.write("candidate not found\n")
        return 1
    settings = fetch_all(
        connection,
        "SELECT setting_namespace, setting_key, value_json, source "
        "FROM candidate_setting WHERE candidate_id = ? "
        "ORDER BY setting_namespace, setting_key",
        (row["candidate_id"],),
    )
    payload = dict(row)
    payload["settings"] = [dict(item) for item in settings]
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    connection = _db(args)
    payload = campaign_report(
        connection,
        args.campaign,
        generated_at=args.generated_at,
    )
    if args.format == "json":
        sys.stdout.write(dump_json(payload))
    else:
        sys.stdout.write(render_markdown(payload))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.acceptance_lab",
        description="Machi development acceptance lab (no Pod mutation).",
    )
    parser.add_argument("--db", default=None, help="SQLite path (default .local/...)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create or migrate the lab database")
    sub.add_parser("doctor", help="check schema, gitignore, product boundary")
    sub.add_parser("import-historical", help="import NVIDIA evidence and preflight")
    sub.add_parser("schema-version")
    create = sub.add_parser("campaign-create")
    create.add_argument("--name", required=True)
    create.add_argument("--purpose", required=True)
    create.add_argument("--notes", default="")
    register = sub.add_parser("candidate-register")
    register.add_argument("--wheel", required=True)
    register.add_argument("--implementation-commit", required=True)
    register.add_argument("--evidence-commit", default=None)
    register.add_argument("--branch", required=True)
    register.add_argument("--package-version", default="0.1.0")
    register.add_argument("--build-id", required=True)
    register.add_argument(
        "--qualification-state", default="local_candidate_ready_nvidia_amd"
    )
    register.add_argument("--implemented", default="nvidia,amd,apple")
    register.add_argument("--accepted", default="nvidia,amd")
    register.add_argument("--artifact-path", default=None)
    register.add_argument("--notes", default="")
    local_run = sub.add_parser("record-local-run")
    local_run.add_argument("--campaign", required=True)
    local_run.add_argument("--candidate", required=True)
    local_run.add_argument("--scenario", required=True)
    local_run.add_argument("--status", default="pass")
    local_run.add_argument("--gates-json", required=True)
    local_run.add_argument("--notes", default="")
    checkpoint = sub.add_parser("checkpoint-record")
    checkpoint.add_argument("--campaign", required=True)
    checkpoint.add_argument("--candidate", required=True)
    checkpoint.add_argument("--name", required=True)
    checkpoint.add_argument("--git-tag", required=True)
    checkpoint.add_argument("--git-commit", required=True)
    checkpoint.add_argument("--meaning", required=True)
    checkpoint.add_argument("--notes", default="")
    policy = sub.add_parser("policy-show")
    policy.add_argument("--campaign", default=None)
    candidate = sub.add_parser("candidate-show")
    candidate.add_argument("--sha", default=None)
    candidate.add_argument("--id", default=None)
    report = sub.add_parser("report")
    report.add_argument("--campaign", required=True)
    report.add_argument("--format", choices=("markdown", "json"), default="markdown")
    report.add_argument("--generated-at", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    for token in raw:
        if token.lstrip("-") in _POD_VERBS or token in _POD_VERBS:
            sys.stderr.write("Pod mutation commands are not implemented.\n")
            return 2
    parser = build_parser()
    args = parser.parse_args(raw)
    if args.command == "candidate-show" and not args.sha and not args.id:
        parser.error("candidate-show requires --sha or --id")
    handlers = {
        "init": cmd_init,
        "doctor": cmd_doctor,
        "import-historical": cmd_import_historical,
        "schema-version": cmd_schema_version,
        "campaign-create": cmd_campaign_create,
        "candidate-register": cmd_candidate_register,
        "record-local-run": cmd_record_local_run,
        "checkpoint-record": cmd_checkpoint_record,
        "policy-show": cmd_policy_show,
        "candidate-show": cmd_candidate_show,
        "report": cmd_report,
    }
    return handlers[args.command](args)
