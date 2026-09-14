"""Install a Machi wheel into a throwaway environment and prove M0, 1.2.1, 1.3.1.

python tools/verify_machi.py dist/machi/machi-0.1.0-py3-none-any.whl
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def isolated_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.pop("MACHI_STATE_ROOT", None)
    env.pop("KULTRUN_STATE_ROOT", None)
    return env


def run(command: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    finished = subprocess.run(
        command, capture_output=True, text=True, check=False, env=env
    )
    if finished.returncode != 0:
        sys.stderr.write(finished.stdout + finished.stderr)
        raise SystemExit(f"command failed: {' '.join(command)}")
    return finished


def run_expect_fail(
    command: list[str], *, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    finished = subprocess.run(
        command, capture_output=True, text=True, check=False, env=env
    )
    if finished.returncode == 0:
        sys.stderr.write(finished.stdout + finished.stderr)
        raise SystemExit(f"command unexpectedly succeeded: {' '.join(command)}")
    return finished


def load_marker(root: Path) -> dict[str, object]:
    raw = (root / ".machi-owner.json").read_text(encoding="utf-8")
    payload: object = json.loads(raw)
    if not isinstance(payload, dict):
        raise SystemExit("marker is not a JSON object")
    return {str(key): value for key, value in payload.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    options = parser.parse_args()
    wheel = options.wheel.resolve()
    if not wheel.is_file():
        raise SystemExit(f"no wheel at {wheel}")

    root = Path(tempfile.mkdtemp(prefix="machi-verify-"))
    venv_dir = root / "venv"
    kernel_journal = root / "kernel-journal"
    root_a = root / "root-a"
    root_b = root / "root-b"
    env_root = root / "root-env"
    occupied = root / "occupied"
    kultrun_tree = root / "kultrun-tree"
    copied_into = root / "copied-into"
    venv.create(venv_dir, with_pip=True, symlinks=True)
    python = venv_dir / "bin/python"
    machi = venv_dir / "bin/machi"
    env = isolated_env()
    run([str(python), "-m", "pip", "install", "--upgrade", "pip"], env=env)
    run([str(python), "-m", "pip", "install", str(wheel)], env=env)
    check = run(
        [
            str(python),
            "-c",
            "import machi, importlib.util as u; "
            "assert u.find_spec('kultrun') is None; "
            "print('machi_ok'); print('kultrun_absent')",
        ],
        env=env,
    )
    print(check.stdout, end="")
    print(run([str(machi), "version"], env=env).stdout, end="")
    prove = run(
        [str(machi), "kernel", "prove", "--journal-dir", str(kernel_journal)],
        env=env,
    )
    print(prove.stdout, end="")
    if '"event_type": "kernel.alive"' not in prove.stdout:
        raise SystemExit("first prove did not emit kernel.alive")
    if '"privacy": "public_ops"' not in prove.stdout:
        raise SystemExit("kernel.alive was not public_ops")
    run([str(machi), "kernel", "prove", "--journal-dir", str(kernel_journal)], env=env)
    listed = run(
        [str(machi), "kernel", "events", "--journal-dir", str(kernel_journal)], env=env
    )
    print(listed.stdout, end="")
    if "records  2" not in listed.stdout:
        raise SystemExit("expected two kernel.alive records after a second prove")

    bind_a = run(
        [str(machi), "install", "bind-root", "--state-root", str(root_a)], env=env
    )
    print(bind_a.stdout, end="")
    if '"event_type": "install.state_root.bound"' not in bind_a.stdout:
        raise SystemExit("bind-root did not emit install.state_root.bound")
    if '"privacy": "restricted"' not in bind_a.stdout:
        raise SystemExit("state-root event was not restricted")
    event_at = bind_a.stdout.find('"kind": "event_record"')
    if event_at < 0:
        raise SystemExit("bind-root did not print an EventRecord")
    if str(root_a) in bind_a.stdout[event_at:]:
        raise SystemExit("absolute state root leaked into the event document")
    if not (root_a / "journal" / "events.jsonl").is_file():
        raise SystemExit("bound root did not persist a Kernel journal")
    if (root_a / ".machi-owner.json").exists():
        raise SystemExit("bind-root must not write the ownership marker")

    reentry = run(
        [str(machi), "install", "bind-root", "--state-root", str(root_a)], env=env
    )
    print(reentry.stdout, end="")
    if '"existed": true' not in reentry.stdout:
        raise SystemExit("same-root re-entry did not report existed=true")
    if '"created": false' not in reentry.stdout:
        raise SystemExit("same-root re-entry did not report created=false")

    bind_b = run(
        [str(machi), "install", "bind-root", "--state-root", str(root_b)], env=env
    )
    print(bind_b.stdout, end="")
    if not root_b.is_dir():
        raise SystemExit("second root was not created")
    env_bind = env.copy()
    env_bind["MACHI_STATE_ROOT"] = str(env_root)
    env_bind.pop("KULTRUN_STATE_ROOT", None)
    bound_env = run([str(machi), "install", "bind-root"], env=env_bind)
    print(bound_env.stdout, end="")
    if '"selection_source": "environment"' not in bound_env.stdout:
        raise SystemExit("MACHI_STATE_ROOT did not win as environment source")
    if not env_root.is_dir():
        raise SystemExit("environment override did not create its root")

    mark_a = run(
        [str(machi), "install", "mark-local", "--state-root", str(root_a)], env=env
    )
    print(mark_a.stdout, end="")
    if '"event_type": "install.ownership.local_marked"' not in mark_a.stdout:
        raise SystemExit("mark-local did not emit install.ownership.local_marked")
    if '"privacy": "restricted"' not in mark_a.stdout:
        raise SystemExit("local-mark event was not restricted")
    if '"status": "local_marker_present"' not in mark_a.stdout:
        raise SystemExit("mark-local did not report local_marker_present")
    if '"dual_ownership": true' in mark_a.stdout:
        raise SystemExit("1.3.1 claimed dual ownership")
    if '"destructive_authorization": true' in mark_a.stdout:
        raise SystemExit("1.3.1 claimed destructive authorization")
    mark_event_at = mark_a.stdout.find('"kind": "event_record"')
    if mark_event_at < 0:
        raise SystemExit("mark-local did not print an EventRecord")
    if str(root_a) in mark_a.stdout[mark_event_at:]:
        raise SystemExit("absolute state root leaked into the mark event")
    marker_a = load_marker(root_a)
    if marker_a.get("kind") != "local_ownership_marker":
        raise SystemExit("marker kind is not local_ownership_marker")
    if marker_a.get("product") != "machi":
        raise SystemExit("marker product is not machi")
    if str(root_a) in json.dumps(marker_a):
        raise SystemExit("absolute path stored in the marker")

    mark_a_again = run(
        [str(machi), "install", "mark-local", "--state-root", str(root_a)], env=env
    )
    print(mark_a_again.stdout, end="")
    if '"existed": true' not in mark_a_again.stdout:
        raise SystemExit("marker re-entry did not report existed=true")
    if '"created": false' not in mark_a_again.stdout:
        raise SystemExit("marker re-entry did not report created=false")
    if load_marker(root_a)["marker_id"] != marker_a["marker_id"]:
        raise SystemExit("re-entry minted a new marker identity")

    mark_b = run(
        [str(machi), "install", "mark-local", "--state-root", str(root_b)], env=env
    )
    print(mark_b.stdout, end="")
    marker_b = load_marker(root_b)
    if marker_a["marker_id"] == marker_b["marker_id"]:
        raise SystemExit("two roots shared a marker identity")
    if marker_a["root_fingerprint"] == marker_b["root_fingerprint"]:
        raise SystemExit("two roots shared a root fingerprint")

    copied_into.mkdir(parents=True)
    run(
        [str(machi), "install", "bind-root", "--state-root", str(copied_into)],
        env=env,
    )
    shutil.copy2(root_a / ".machi-owner.json", copied_into / ".machi-owner.json")
    copied_before = (copied_into / ".machi-owner.json").read_text(encoding="utf-8")
    copied_fail = run_expect_fail(
        [str(machi), "install", "mark-local", "--state-root", str(copied_into)],
        env=env,
    )
    print(copied_fail.stderr, end="")
    if "copied marker" not in copied_fail.stderr:
        raise SystemExit("copied marker did not fail closed")
    if (copied_into / ".machi-owner.json").read_text(encoding="utf-8") != copied_before:
        raise SystemExit("copied marker was rewritten")

    occupied.mkdir()
    (occupied / "notes.txt").write_text("customer notes\n", encoding="utf-8")
    unknown = run_expect_fail(
        [str(machi), "install", "mark-local", "--state-root", str(occupied)],
        env=env,
    )
    print(unknown.stderr, end="")
    if "unknown pre-existing" not in unknown.stderr:
        raise SystemExit("unknown content was not refused")
    if (occupied / ".machi-owner.json").exists():
        raise SystemExit("unknown content was claimed")
    if (occupied / "journal" / "events.jsonl").exists():
        raise SystemExit("refused claim wrote a journal into unknown content")

    kultrun_tree.mkdir()
    (kultrun_tree / ".kultrun-owner.json").write_text(
        '{"created_by":"kultrun"}\n', encoding="utf-8"
    )
    kultrun_cli = run_expect_fail(
        [str(machi), "install", "mark-local", "--state-root", str(kultrun_tree)],
        env=env,
    )
    print(kultrun_cli.stderr, end="")
    if (kultrun_tree / ".machi-owner.json").exists():
        raise SystemExit("Kultrun tree was claimed as Machi-owned")
    if (kultrun_tree / ".kultrun-owner.json").read_text(encoding="utf-8") != (
        '{"created_by":"kultrun"}\n'
    ):
        raise SystemExit("Kultrun marker was modified")
    bypass = run(
        [
            str(python),
            "-c",
            (
                "import datetime as dt\n"
                "from pathlib import Path\n"
                "from machi.install.contracts import (\n"
                "    SelectionSource, StateRootBinding)\n"
                "from machi.install.marker import SelfOwnershipMarker\n"
                "from machi.kernel.errors import ConflictError\n"
                f"root = Path({str(kultrun_tree)!r})\n"
                "binding = StateRootBinding(\n"
                "    root=str(root.resolve()),\n"
                "    selection_source=SelectionSource.EXPLICIT,\n"
                "    existed=True,\n"
                "    created=True,\n"
                "    bound_at=dt.datetime.now(dt.UTC),\n"
                ")\n"
                "try:\n"
                "    SelfOwnershipMarker().establish(binding)\n"
                "except ConflictError as exc:\n"
                "    print('kultrun_conflict')\n"
                "    print(exc.message)\n"
                "else:\n"
                "    raise SystemExit('1.3.1 claimed a Kultrun tree')\n"
            ),
        ],
        env=env,
    )
    print(bypass.stdout, end="")
    if "kultrun_conflict" not in bypass.stdout:
        raise SystemExit("bypassed binder still failed to refuse Kultrun")

    broken = root_a / ".machi-owner.json"
    original = broken.read_text(encoding="utf-8")
    broken.write_text("{not-json\n", encoding="utf-8")
    malformed = run_expect_fail(
        [str(machi), "install", "mark-local", "--state-root", str(root_a)],
        env=env,
    )
    print(malformed.stderr, end="")
    if "malformed JSON" not in malformed.stderr:
        raise SystemExit("malformed marker did not fail closed")
    if broken.read_text(encoding="utf-8") != "{not-json\n":
        raise SystemExit("malformed marker was rewritten")
    broken.write_text(original, encoding="utf-8")
    restored = run(
        [str(machi), "install", "mark-local", "--state-root", str(root_a)], env=env
    )
    print(restored.stdout, end="")
    if load_marker(root_a)["marker_id"] != marker_a["marker_id"]:
        raise SystemExit("restored marker identity changed")

    print("verify_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
