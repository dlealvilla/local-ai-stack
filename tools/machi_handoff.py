#!/usr/bin/env python3
"""Development-only Git handoff helper for Machi Lead Developer ↔ Cursor.

This tool never changes product runtime state. It reads a dedicated remote
control branch and publishes Cursor's completed paste-back back to that branch
without switching or modifying the current implementation branch.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

CONTROL_BRANCH = "control/machi-handoff"
REMOTE = "origin"
CACHE = Path(".machi-handoff")
CONTROL_FILES = (
    "control/CURRENT-INSTRUCTION.md",
    "control/STATE.json",
    "control/ARCHITECTURE-STATE.md",
    "control/OPEN-DECISIONS.md",
)


def run(*args: str, cwd: Path | None = None, capture: bool = False) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    return result.stdout if capture else ""


def fetch_control() -> None:
    run("git", "fetch", REMOTE, CONTROL_BRANCH)


def show_remote(path: str) -> str:
    return run(
        "git",
        "show",
        f"{REMOTE}/{CONTROL_BRANCH}:{path}",
        capture=True,
    )


def sync() -> None:
    fetch_control()
    CACHE.mkdir(exist_ok=True)
    for remote_path in CONTROL_FILES:
        target = CACHE / Path(remote_path).name
        target.write_text(show_remote(remote_path), encoding="utf-8")
    state = json.loads((CACHE / "STATE.json").read_text(encoding="utf-8"))
    print(f"instruction_id={state['instruction_id']}")
    print(f"status={state['status']}")
    print(f"instruction={CACHE / 'CURRENT-INSTRUCTION.md'}")
    print(f"architecture={CACHE / 'ARCHITECTURE-STATE.md'}")
    print(f"decisions={CACHE / 'OPEN-DECISIONS.md'}")


def status() -> None:
    sync()
    print((CACHE / "STATE.json").read_text(encoding="utf-8"))


def publish_step(source: Path) -> None:
    """Publish development-only step progress. Does not change the instruction."""
    if not source.is_file():
        raise SystemExit(f"step status file not found: {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload.get("step_id"):
        raise SystemExit("step status must be an object with step_id")
    fetch_control()
    with tempfile.TemporaryDirectory(prefix="machi-handoff-") as tmp:
        worktree = Path(tmp) / "control"
        run(
            "git",
            "worktree",
            "add",
            "--detach",
            str(worktree),
            f"{REMOTE}/{CONTROL_BRANCH}",
        )
        try:
            target = worktree / "control" / "STEP-STATUS.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            run("git", "add", "control/STEP-STATUS.json", cwd=worktree)
            changed = run("git", "status", "--porcelain", cwd=worktree, capture=True)
            if not changed.strip():
                print("step status unchanged; nothing to publish")
                return
            run(
                "git",
                "-c",
                "user.name=Machi Cursor Handoff",
                "-c",
                "user.email=machi-handoff@local.invalid",
                "commit",
                "-m",
                f"control: step {payload['step_id']} {payload.get('status', '')}",
                cwd=worktree,
            )
            run("git", "push", REMOTE, f"HEAD:{CONTROL_BRANCH}", cwd=worktree)
            print(f"published_step={payload['step_id']} status={payload.get('status')}")
        finally:
            run("git", "worktree", "remove", "--force", str(worktree))


def publish_pasteback(source: Path) -> None:
    if not source.is_file():
        raise SystemExit(f"paste-back file not found: {source}")
    fetch_control()
    state = json.loads(show_remote("control/STATE.json"))
    instruction_id = state["instruction_id"]

    with tempfile.TemporaryDirectory(prefix="machi-handoff-") as tmp:
        worktree = Path(tmp) / "control"
        run(
            "git",
            "worktree",
            "add",
            "--detach",
            str(worktree),
            f"{REMOTE}/{CONTROL_BRANCH}",
        )
        try:
            target = worktree / "control" / "LATEST-PASTEBACK.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

            state["status"] = "PASTEBACK_PUBLISHED"
            state["published_instruction_id"] = instruction_id
            (worktree / "control" / "STATE.json").write_text(
                json.dumps(state, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            run(
                "git",
                "add",
                "control/LATEST-PASTEBACK.md",
                "control/STATE.json",
                cwd=worktree,
            )
            changed = run("git", "status", "--porcelain", cwd=worktree, capture=True)
            if not changed.strip():
                print("paste-back unchanged; nothing to publish")
                return
            run(
                "git",
                "-c",
                "user.name=Machi Cursor Handoff",
                "-c",
                "user.email=machi-handoff@local.invalid",
                "commit",
                "-m",
                f"control: publish paste-back for {instruction_id}",
                cwd=worktree,
            )
            run(
                "git",
                "push",
                REMOTE,
                f"HEAD:{CONTROL_BRANCH}",
                cwd=worktree,
            )
            print(f"published_instruction_id={instruction_id}")
        finally:
            run("git", "worktree", "remove", "--force", str(worktree))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync")
    sub.add_parser("status")
    pub = sub.add_parser("publish-pasteback")
    pub.add_argument("path", type=Path)
    step = sub.add_parser("publish-step")
    step.add_argument("path", type=Path)
    args = parser.parse_args()

    if args.command == "sync":
        sync()
    elif args.command == "status":
        status()
    elif args.command == "publish-pasteback":
        publish_pasteback(args.path)
    elif args.command == "publish-step":
        publish_step(args.path)


if __name__ == "__main__":
    main()
