"""Install a Machi wheel into a throwaway environment and prove M0 through 2.4.1.

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


def load_registry(store: Path, marker_id: str) -> dict[str, object]:
    raw = (store / "local_ownership_registry_record" / f"{marker_id}.json").read_text(
        encoding="utf-8"
    )
    payload: object = json.loads(raw)
    if not isinstance(payload, dict):
        raise SystemExit("registry record is not a JSON object")
    return {str(key): value for key, value in payload.items()}


def load_install(store: Path, marker_id: str) -> dict[str, object]:
    raw = (store / "install_record" / f"{marker_id}.json").read_text(encoding="utf-8")
    payload: object = json.loads(raw)
    if not isinstance(payload, dict):
        raise SystemExit("install record is not a JSON object")
    return {str(key): value for key, value in payload.items()}


def load_run(store: Path, install_id: str) -> dict[str, object]:
    raw = (store / "install_run" / f"{install_id}.json").read_text(encoding="utf-8")
    payload: object = json.loads(raw)
    if not isinstance(payload, dict):
        raise SystemExit("install run is not a JSON object")
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

    store_a = root_a / "store"
    store_b = root_b / "store"
    put_a = run(
        [
            str(machi),
            "kernel",
            "store-put",
            "--store-dir",
            str(store_a),
            "--key",
            "proof-a",
            "--token",
            "alpha",
            "--journal-dir",
            str(root_a / "journal"),
        ],
        env=env,
    )
    print(put_a.stdout, end="")
    if '"kind": "kernel.store.proof"' not in put_a.stdout:
        raise SystemExit("store-put did not persist kernel.store.proof")
    if "kernel.store.proved" not in put_a.stdout:
        raise SystemExit("store-put did not emit kernel.store.proved")
    if '"privacy": "restricted"' not in put_a.stdout:
        raise SystemExit("store-proved was not restricted")
    event_at = put_a.stdout.find('"kind": "event_record"')
    if event_at < 0:
        raise SystemExit("store-put did not print an EventRecord")
    if str(store_a) in put_a.stdout[event_at:]:
        raise SystemExit("absolute store path leaked into the proof event")
    if "alpha" in put_a.stdout[event_at:]:
        raise SystemExit("proof token leaked into the proof event")

    got_a = run(
        [
            str(machi),
            "kernel",
            "store-get",
            "--store-dir",
            str(store_a),
            "--key",
            "proof-a",
        ],
        env=env,
    )
    print(got_a.stdout, end="")
    if '"token": "alpha"' not in got_a.stdout:
        raise SystemExit("fresh-process store-get did not return the proof token")

    again = run(
        [
            str(machi),
            "kernel",
            "store-put",
            "--store-dir",
            str(store_a),
            "--key",
            "proof-a",
            "--token",
            "alpha",
        ],
        env=env,
    )
    print(again.stdout, end="")
    if "created  false" not in again.stdout:
        raise SystemExit("identical store re-entry did not report created=false")

    conflict = run_expect_fail(
        [
            str(machi),
            "kernel",
            "store-put",
            "--store-dir",
            str(store_a),
            "--key",
            "proof-a",
            "--token",
            "other",
        ],
        env=env,
    )
    print(conflict.stderr, end="")
    if "does not match" not in conflict.stderr:
        raise SystemExit("conflicting store key did not fail closed")

    put_b = run(
        [
            str(machi),
            "kernel",
            "store-put",
            "--store-dir",
            str(store_b),
            "--key",
            "proof-a",
            "--token",
            "beta",
        ],
        env=env,
    )
    print(put_b.stdout, end="")
    if '"token": "beta"' not in put_b.stdout:
        raise SystemExit("store B did not accept the same logical key independently")
    got_b = run(
        [
            str(machi),
            "kernel",
            "store-get",
            "--store-dir",
            str(store_b),
            "--key",
            "proof-a",
        ],
        env=env,
    )
    if '"token": "alpha"' in got_b.stdout:
        raise SystemExit("store B read store A's token")

    kind_a = store_a / "kernel.store.proof"
    (kind_a / "b.json").write_text("{broken\n", encoding="utf-8")
    run(
        [
            str(machi),
            "kernel",
            "store-put",
            "--store-dir",
            str(store_a),
            "--key",
            "c",
            "--token",
            "charlie",
        ],
        env=env,
    )
    still_a = run(
        [
            str(machi),
            "kernel",
            "store-get",
            "--store-dir",
            str(store_a),
            "--key",
            "proof-a",
        ],
        env=env,
    )
    if '"token": "alpha"' not in still_a.stdout:
        raise SystemExit("corruption of B broke reading A")
    broken_b = run_expect_fail(
        [str(machi), "kernel", "store-get", "--store-dir", str(store_a), "--key", "b"],
        env=env,
    )
    print(broken_b.stderr, end="")
    if "malformed JSON" not in broken_b.stderr:
        raise SystemExit("malformed stored entity did not fail closed")
    still_c = run(
        [str(machi), "kernel", "store-get", "--store-dir", str(store_a), "--key", "c"],
        env=env,
    )
    if '"token": "charlie"' not in still_c.stdout:
        raise SystemExit("corruption of B broke reading C")

    unsafe = run_expect_fail(
        [
            str(machi),
            "kernel",
            "store-put",
            "--store-dir",
            str(store_a),
            "--key",
            "../escape",
            "--token",
            "nope",
        ],
        env=env,
    )
    print(unsafe.stderr, end="")
    if "record key" not in unsafe.stderr:
        raise SystemExit("unsafe store key was not refused")

    control_registry = root / "control-registry"
    root_c = root / "root-c"
    seed_a = run(
        [
            str(machi),
            "install",
            "seed-registry",
            "--state-root",
            str(root_a),
            "--registry-store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(seed_a.stdout, end="")
    if '"kind": "local_ownership_registry_record"' not in seed_a.stdout:
        raise SystemExit("seed-registry did not persist a registry record")
    if '"event_type": "install.ownership.registry_seeded"' not in seed_a.stdout:
        raise SystemExit("seed-registry did not emit install.ownership.registry_seeded")
    if '"privacy": "restricted"' not in seed_a.stdout:
        raise SystemExit("registry-seeded event was not restricted")
    if '"status": "registry_seed_present"' not in seed_a.stdout:
        raise SystemExit("seed-registry did not report registry_seed_present")
    if '"dual_ownership": true' in seed_a.stdout:
        raise SystemExit("1.3.2 claimed dual ownership")
    if '"destructive_authorization": true' in seed_a.stdout:
        raise SystemExit("1.3.2 claimed destructive authorization")
    seed_event_at = seed_a.stdout.find('"kind": "event_record"')
    if seed_event_at < 0:
        raise SystemExit("seed-registry did not print an EventRecord")
    if str(root_a) in seed_a.stdout[seed_event_at:]:
        raise SystemExit("absolute state root leaked into the registry event")
    if str(control_registry) in seed_a.stdout[seed_event_at:]:
        raise SystemExit("registry Store path leaked into the registry event")
    if (root_a / "local_ownership_registry_record").exists():
        raise SystemExit("registry record was written inside the claimed state root")
    marker_a = load_marker(root_a)
    record_a = load_registry(control_registry, str(marker_a["marker_id"]))
    if record_a["marker_id"] != marker_a["marker_id"]:
        raise SystemExit("registry marker_id did not cite the local marker")
    if record_a["root_fingerprint"] != marker_a["root_fingerprint"]:
        raise SystemExit("registry fingerprint did not match the local marker")

    seed_a_again = run(
        [
            str(machi),
            "install",
            "seed-registry",
            "--state-root",
            str(root_a),
            "--registry-store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(seed_a_again.stdout, end="")
    if "created  false" not in seed_a_again.stdout:
        raise SystemExit("registry re-entry did not report created=false")
    if (
        load_registry(control_registry, str(marker_a["marker_id"]))["created_at"]
        != record_a["created_at"]
    ):
        raise SystemExit("registry re-entry rewrote created_at")

    seed_b = run(
        [
            str(machi),
            "install",
            "seed-registry",
            "--state-root",
            str(root_b),
            "--registry-store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(seed_b.stdout, end="")
    marker_b = load_marker(root_b)
    record_b = load_registry(control_registry, str(marker_b["marker_id"]))
    if marker_a["marker_id"] == marker_b["marker_id"]:
        raise SystemExit("two roots shared a marker identity after registry seed")
    if record_a["marker_id"] == record_b["marker_id"]:
        raise SystemExit("two registry rows shared a marker identity")
    if record_a["root_fingerprint"] == record_b["root_fingerprint"]:
        raise SystemExit("two registry rows shared a root fingerprint")

    seed_c = run(
        [
            str(machi),
            "install",
            "seed-registry",
            "--state-root",
            str(root_c),
            "--registry-store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(seed_c.stdout, end="")
    marker_c = load_marker(root_c)

    establish_a = run(
        [
            str(machi),
            "install",
            "establish-record",
            "--state-root",
            str(root_a),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(establish_a.stdout, end="")
    if '"kind": "install_record"' not in establish_a.stdout:
        raise SystemExit("establish-record did not persist an InstallRecord")
    if '"event_type": "install.record.established"' not in establish_a.stdout:
        raise SystemExit("establish-record did not emit install.record.established")
    if '"privacy": "restricted"' not in establish_a.stdout:
        raise SystemExit("install-record event was not restricted")
    if '"status": "install_record_present"' not in establish_a.stdout:
        raise SystemExit("establish-record did not report install_record_present")
    if '"dual_ownership": true' in establish_a.stdout:
        raise SystemExit("1.1.1 claimed dual ownership")
    if '"destructive_authorization": true' in establish_a.stdout:
        raise SystemExit("1.1.1 claimed destructive authorization")
    establish_event_at = establish_a.stdout.find('"kind": "event_record"')
    if establish_event_at < 0:
        raise SystemExit("establish-record did not print an EventRecord")
    if str(root_a) in establish_a.stdout[establish_event_at:]:
        raise SystemExit("absolute state root leaked into the install-record event")
    if str(control_registry) in establish_a.stdout[establish_event_at:]:
        raise SystemExit("Store path leaked into the install-record event")
    if (root_a / "install_record").exists():
        raise SystemExit("InstallRecord was written inside the claimed state root")
    install_a = load_install(control_registry, str(marker_a["marker_id"]))
    if install_a["marker_id"] != marker_a["marker_id"]:
        raise SystemExit("InstallRecord marker_id did not cite the local marker")
    if install_a["root_fingerprint"] != marker_a["root_fingerprint"]:
        raise SystemExit("InstallRecord fingerprint did not match the local marker")
    if not str(install_a["install_id"]).startswith("inst_"):
        raise SystemExit("InstallRecord did not mint an InstallId")

    establish_a_again = run(
        [
            str(machi),
            "install",
            "establish-record",
            "--state-root",
            str(root_a),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(establish_a_again.stdout, end="")
    if "created  false" not in establish_a_again.stdout:
        raise SystemExit("InstallRecord re-entry did not report created=false")
    if (
        load_install(control_registry, str(marker_a["marker_id"]))["created_at"]
        != install_a["created_at"]
    ):
        raise SystemExit("InstallRecord re-entry rewrote created_at")
    if (
        load_install(control_registry, str(marker_a["marker_id"]))["install_id"]
        != install_a["install_id"]
    ):
        raise SystemExit("InstallRecord re-entry minted a new InstallId")

    establish_b = run(
        [
            str(machi),
            "install",
            "establish-record",
            "--state-root",
            str(root_b),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(establish_b.stdout, end="")
    install_b = load_install(control_registry, str(marker_b["marker_id"]))
    if install_a["install_id"] == install_b["install_id"]:
        raise SystemExit("two roots shared an InstallId")
    establish_c = run(
        [
            str(machi),
            "install",
            "establish-record",
            "--state-root",
            str(root_c),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(establish_c.stdout, end="")
    install_c = load_install(control_registry, str(marker_c["marker_id"]))
    if install_c["install_id"] in {install_a["install_id"], install_b["install_id"]}:
        raise SystemExit("root C collided with an existing InstallId")

    run_a = run(
        [
            str(machi),
            "install",
            "establish-run",
            "--state-root",
            str(root_a),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(run_a.stdout, end="")
    if '"kind": "install_run"' not in run_a.stdout:
        raise SystemExit("establish-run did not persist an InstallRun")
    if '"event_type": "install.bound"' not in run_a.stdout:
        raise SystemExit("establish-run did not emit install.bound")
    if '"privacy": "restricted"' not in run_a.stdout:
        raise SystemExit("install.bound was not restricted")
    if '"status": "install_run_present"' not in run_a.stdout:
        raise SystemExit("establish-run did not report install_run_present")
    if '"dual_ownership": true' in run_a.stdout:
        raise SystemExit("1.4.1 claimed dual ownership")
    if '"destructive_authorization": true' in run_a.stdout:
        raise SystemExit("1.4.1 claimed destructive authorization")
    run_event_at = run_a.stdout.find('"kind": "event_record"')
    if run_event_at < 0:
        raise SystemExit("establish-run did not print an EventRecord")
    if str(root_a) in run_a.stdout[run_event_at:]:
        raise SystemExit("absolute state root leaked into install.bound")
    if str(control_registry) in run_a.stdout[run_event_at:]:
        raise SystemExit("Store path leaked into install.bound")
    if (root_a / "install_run").exists():
        raise SystemExit("InstallRun was written inside the claimed state root")
    persisted_run_a = load_run(control_registry, str(install_a["install_id"]))
    if persisted_run_a["install_id"] != install_a["install_id"]:
        raise SystemExit("InstallRun did not cite InstallId A")
    if not str(persisted_run_a["install_run_id"]).startswith("irun_"):
        raise SystemExit("InstallRun did not mint an InstallRunId")
    journal_a = (root_a / "journal" / "events.jsonl").read_text(encoding="utf-8")
    journal_events = [json.loads(line) for line in journal_a.splitlines() if line]
    bound_events = [
        item for item in journal_events if item.get("event_type") == "install.bound"
    ]
    if not bound_events:
        raise SystemExit("journal is missing install.bound")
    first_bound = bound_events[0]
    if not str(first_bound["install_id"]).startswith("inst_"):
        raise SystemExit("install.bound did not resolve install_id")
    if not str(first_bound["install_run_id"]).startswith("irun_"):
        raise SystemExit("install.bound did not resolve install_run_id")
    if "$unresolved" not in json.dumps(first_bound["host_id"]):
        raise SystemExit("install.bound resolved host_id")
    established_events = [
        item
        for item in journal_events
        if item.get("event_type") == "install.record.established"
    ]
    if "$unresolved" not in json.dumps(established_events[0]["install_run_id"]):
        raise SystemExit("install.record.established was rewritten with a run id")

    run_a_again = run(
        [
            str(machi),
            "install",
            "establish-run",
            "--state-root",
            str(root_a),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(run_a_again.stdout, end="")
    if "created  false" not in run_a_again.stdout:
        raise SystemExit("InstallRun re-entry did not report created=false")
    if (
        load_run(control_registry, str(install_a["install_id"]))["created_at"]
        != persisted_run_a["created_at"]
    ):
        raise SystemExit("InstallRun re-entry rewrote created_at")
    if (
        load_run(control_registry, str(install_a["install_id"]))["install_run_id"]
        != persisted_run_a["install_run_id"]
    ):
        raise SystemExit("InstallRun re-entry minted a new InstallRunId")

    run_b = run(
        [
            str(machi),
            "install",
            "establish-run",
            "--state-root",
            str(root_b),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(run_b.stdout, end="")
    persisted_run_b = load_run(control_registry, str(install_b["install_id"]))
    if persisted_run_a["install_run_id"] == persisted_run_b["install_run_id"]:
        raise SystemExit("two roots shared an InstallRunId")
    run_c = run(
        [
            str(machi),
            "install",
            "establish-run",
            "--state-root",
            str(root_c),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(run_c.stdout, end="")
    persisted_run_c = load_run(control_registry, str(install_c["install_id"]))
    if persisted_run_c["install_run_id"] in {
        persisted_run_a["install_run_id"],
        persisted_run_b["install_run_id"],
    }:
        raise SystemExit("root C collided with an existing InstallRunId")

    run_kind = control_registry / "install_run"
    (run_kind / f"{install_b['install_id']}.json").write_text(
        "{broken\n", encoding="utf-8"
    )
    run_a_after = load_run(control_registry, str(install_a["install_id"]))
    if run_a_after["install_run_id"] != persisted_run_a["install_run_id"]:
        raise SystemExit("corruption of InstallRun B broke reading A")
    broken_run_b = run_expect_fail(
        [
            str(machi),
            "install",
            "establish-run",
            "--state-root",
            str(root_b),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(broken_run_b.stderr, end="")
    if "malformed JSON" not in broken_run_b.stderr:
        raise SystemExit("malformed InstallRun did not fail closed")
    run_c_after = load_run(control_registry, str(install_c["install_id"]))
    if run_c_after["install_run_id"] != persisted_run_c["install_run_id"]:
        raise SystemExit("corruption of InstallRun B broke reading C")

    install_kind = control_registry / "install_record"
    (install_kind / f"{marker_b['marker_id']}.json").write_text(
        "{broken\n", encoding="utf-8"
    )
    install_a_after = load_install(control_registry, str(marker_a["marker_id"]))
    if install_a_after["install_id"] != install_a["install_id"]:
        raise SystemExit("corruption of InstallRecord B broke reading A")
    broken_install_b = run_expect_fail(
        [
            str(machi),
            "install",
            "establish-record",
            "--state-root",
            str(root_b),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(broken_install_b.stderr, end="")
    if "malformed JSON" not in broken_install_b.stderr:
        raise SystemExit("malformed InstallRecord did not fail closed")
    install_c_after = load_install(control_registry, str(marker_c["marker_id"]))
    if install_c_after["install_id"] != install_c["install_id"]:
        raise SystemExit("corruption of InstallRecord B broke reading C")

    kind_dir = control_registry / "local_ownership_registry_record"
    (kind_dir / f"{marker_b['marker_id']}.json").write_text(
        "{broken\n", encoding="utf-8"
    )
    registry_a_after = load_registry(control_registry, str(marker_a["marker_id"]))
    if registry_a_after["marker_id"] != marker_a["marker_id"]:
        raise SystemExit("corruption of registry B broke reading A")
    broken_b = run_expect_fail(
        [
            str(machi),
            "install",
            "seed-registry",
            "--state-root",
            str(root_b),
            "--registry-store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(broken_b.stderr, end="")
    if "malformed JSON" not in broken_b.stderr:
        raise SystemExit("malformed registry record did not fail closed")
    registry_c_after = load_registry(control_registry, str(marker_c["marker_id"]))
    if registry_c_after["marker_id"] != marker_c["marker_id"]:
        raise SystemExit("corruption of registry B broke reading C")

    copied = root / "copied-root"
    shutil.copytree(root_a, copied)
    copied_fail = run_expect_fail(
        [
            str(machi),
            "install",
            "seed-registry",
            "--state-root",
            str(copied),
            "--registry-store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(copied_fail.stderr, end="")
    if "copied marker" not in copied_fail.stderr:
        raise SystemExit("copied state root was seeded as owned")
    if (
        load_registry(control_registry, str(marker_a["marker_id"]))["root_fingerprint"]
        != record_a["root_fingerprint"]
    ):
        raise SystemExit("copied-root attempt mutated registry A")

    copied_install = run_expect_fail(
        [
            str(machi),
            "install",
            "establish-record",
            "--state-root",
            str(copied),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(copied_install.stderr, end="")
    if "copied marker" not in copied_install.stderr:
        raise SystemExit("copied state root obtained an InstallRecord")
    if (
        load_install(control_registry, str(marker_a["marker_id"]))["install_id"]
        != install_a["install_id"]
    ):
        raise SystemExit("copied-root attempt mutated InstallRecord A")

    copied_run = run_expect_fail(
        [
            str(machi),
            "install",
            "establish-run",
            "--state-root",
            str(copied),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(copied_run.stderr, end="")
    if "copied marker" not in copied_run.stderr:
        raise SystemExit("copied state root obtained an InstallRun")
    if (
        load_run(control_registry, str(install_a["install_id"]))["install_run_id"]
        != persisted_run_a["install_run_id"]
    ):
        raise SystemExit("copied-root attempt mutated InstallRun A")

    journal_before_discover = (root_a / "journal" / "events.jsonl").read_text(
        encoding="utf-8"
    )
    bound_snapshot = next(
        json.loads(line)
        for line in journal_before_discover.splitlines()
        if json.loads(line).get("event_type") == "install.bound"
    )
    discover = run(
        [
            str(machi),
            "discover",
            "os-arch",
            "--state-root",
            str(root_a),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(discover.stdout, end="")
    if '"event_type": "discover.os_arch.observed"' not in discover.stdout:
        raise SystemExit("discover os-arch did not emit discover.os_arch.observed")
    if '"privacy": "public_ops"' not in discover.stdout:
        raise SystemExit("discover.os_arch.observed was not public_ops")
    if f"install  {install_a['install_id']}" not in discover.stdout:
        raise SystemExit("discover event lost InstallId correlation")
    if f"run      {persisted_run_a['install_run_id']}" not in discover.stdout:
        raise SystemExit("discover event lost InstallRunId correlation")
    if "host     unresolved(not_provided)" not in discover.stdout:
        raise SystemExit("discover os-arch minted or omitted host_id")
    discover_event_at = discover.stdout.find('"kind": "event_record"')
    if discover_event_at < 0:
        raise SystemExit("discover os-arch did not print an EventRecord")
    if str(root_a) in discover.stdout[discover_event_at:]:
        raise SystemExit("absolute state root leaked into discover event")
    if str(control_registry) in discover.stdout[discover_event_at:]:
        raise SystemExit("Store path leaked into discover event")
    if (control_registry / "os_architecture_observation").exists():
        raise SystemExit("OS/arch observation was persisted as Store state")
    journal_after = [
        json.loads(line)
        for line in (root_a / "journal" / "events.jsonl").read_text().splitlines()
        if line
    ]
    still_bound = next(
        item for item in journal_after if item["event_id"] == bound_snapshot["event_id"]
    )
    if still_bound != bound_snapshot:
        raise SystemExit("discover rewrote install.bound")
    observed_events = [
        item
        for item in journal_after
        if item.get("event_type") == "discover.os_arch.observed"
    ]
    if not observed_events:
        raise SystemExit("journal is missing discover.os_arch.observed")
    if observed_events[-1]["install_id"] != install_a["install_id"]:
        raise SystemExit("journaled discover event lost InstallId")
    if observed_events[-1]["install_run_id"] != persisted_run_a["install_run_id"]:
        raise SystemExit("journaled discover event lost InstallRunId")
    if "$unresolved" not in json.dumps(observed_events[-1]["host_id"]):
        raise SystemExit("discover event resolved host_id")

    os_arch_snapshot = observed_events[-1]
    bound_after_os = next(
        item for item in journal_after if item["event_id"] == bound_snapshot["event_id"]
    )
    memory = run(
        [
            str(machi),
            "discover",
            "memory",
            "--state-root",
            str(root_a),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(memory.stdout, end="")
    if '"event_type": "discover.memory.observed"' not in memory.stdout:
        raise SystemExit("discover memory did not emit discover.memory.observed")
    if '"privacy": "public_ops"' not in memory.stdout:
        raise SystemExit("discover.memory.observed was not public_ops")
    if f"install  {install_a['install_id']}" not in memory.stdout:
        raise SystemExit("memory event lost InstallId correlation")
    if f"run      {persisted_run_a['install_run_id']}" not in memory.stdout:
        raise SystemExit("memory event lost InstallRunId correlation")
    if "host     unresolved(not_provided)" not in memory.stdout:
        raise SystemExit("discover memory minted or omitted host_id")
    if '"physical_total_status": "normalized"' not in memory.stdout:
        raise SystemExit("discover memory did not normalize physical total")
    memory_event_at = memory.stdout.find('"kind": "event_record"')
    if memory_event_at < 0:
        raise SystemExit("discover memory did not print an EventRecord")
    if str(root_a) in memory.stdout[memory_event_at:]:
        raise SystemExit("absolute state root leaked into memory event")
    if str(control_registry) in memory.stdout[memory_event_at:]:
        raise SystemExit("Store path leaked into memory event")
    if (control_registry / "memory_observation").exists():
        raise SystemExit("memory observation was persisted as Store state")
    journal_after_memory = [
        json.loads(line)
        for line in (root_a / "journal" / "events.jsonl").read_text().splitlines()
        if line
    ]
    still_os_arch = next(
        item
        for item in journal_after_memory
        if item["event_id"] == os_arch_snapshot["event_id"]
    )
    if still_os_arch != os_arch_snapshot:
        raise SystemExit("memory observation rewrote discover.os_arch.observed")
    still_bound_memory = next(
        item
        for item in journal_after_memory
        if item["event_id"] == bound_after_os["event_id"]
    )
    if still_bound_memory != bound_after_os:
        raise SystemExit("memory observation rewrote install.bound")
    memory_events = [
        item
        for item in journal_after_memory
        if item.get("event_type") == "discover.memory.observed"
    ]
    if not memory_events:
        raise SystemExit("journal is missing discover.memory.observed")
    if memory_events[-1]["install_id"] != install_a["install_id"]:
        raise SystemExit("journaled memory event lost InstallId")
    if memory_events[-1]["install_run_id"] != persisted_run_a["install_run_id"]:
        raise SystemExit("journaled memory event lost InstallRunId")
    if "$unresolved" not in json.dumps(memory_events[-1]["host_id"]):
        raise SystemExit("memory event resolved host_id")

    memory_snapshot = memory_events[-1]
    accelerator = run(
        [
            str(machi),
            "discover",
            "accelerator",
            "--state-root",
            str(root_a),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(accelerator.stdout, end="")
    if '"event_type": "discover.accelerator.observed"' not in accelerator.stdout:
        raise SystemExit(
            "discover accelerator did not emit discover.accelerator.observed"
        )
    if '"privacy": "public_ops"' not in accelerator.stdout:
        raise SystemExit("discover.accelerator.observed was not public_ops")
    if f"install  {install_a['install_id']}" not in accelerator.stdout:
        raise SystemExit("accelerator event lost InstallId correlation")
    if f"run      {persisted_run_a['install_run_id']}" not in accelerator.stdout:
        raise SystemExit("accelerator event lost InstallRunId correlation")
    if "host     unresolved(not_provided)" not in accelerator.stdout:
        raise SystemExit("discover accelerator minted or omitted host_id")
    accelerator_event_at = accelerator.stdout.find('"kind": "event_record"')
    if accelerator_event_at < 0:
        raise SystemExit("discover accelerator did not print an EventRecord")
    if str(root_a) in accelerator.stdout[accelerator_event_at:]:
        raise SystemExit("absolute state root leaked into accelerator event")
    if str(control_registry) in accelerator.stdout[accelerator_event_at:]:
        raise SystemExit("Store path leaked into accelerator event")
    if (control_registry / "accelerator_observation").exists():
        raise SystemExit("accelerator observation was persisted as Store state")
    journal_after_accelerator = [
        json.loads(line)
        for line in (root_a / "journal" / "events.jsonl").read_text().splitlines()
        if line
    ]
    still_memory = next(
        item
        for item in journal_after_accelerator
        if item["event_id"] == memory_snapshot["event_id"]
    )
    if still_memory != memory_snapshot:
        raise SystemExit("accelerator observation rewrote discover.memory.observed")
    still_os_arch_acc = next(
        item
        for item in journal_after_accelerator
        if item["event_id"] == os_arch_snapshot["event_id"]
    )
    if still_os_arch_acc != os_arch_snapshot:
        raise SystemExit("accelerator observation rewrote discover.os_arch.observed")
    still_bound_acc = next(
        item
        for item in journal_after_accelerator
        if item["event_id"] == bound_after_os["event_id"]
    )
    if still_bound_acc != bound_after_os:
        raise SystemExit("accelerator observation rewrote install.bound")
    accelerator_events = [
        item
        for item in journal_after_accelerator
        if item.get("event_type") == "discover.accelerator.observed"
    ]
    if not accelerator_events:
        raise SystemExit("journal is missing discover.accelerator.observed")
    if accelerator_events[-1]["install_id"] != install_a["install_id"]:
        raise SystemExit("journaled accelerator event lost InstallId")
    if accelerator_events[-1]["install_run_id"] != persisted_run_a["install_run_id"]:
        raise SystemExit("journaled accelerator event lost InstallRunId")
    if "$unresolved" not in json.dumps(accelerator_events[-1]["host_id"]):
        raise SystemExit("accelerator event resolved host_id")

    accelerator_snapshot = accelerator_events[-1]
    mounts = run(
        [
            str(machi),
            "discover",
            "mounts",
            "--state-root",
            str(root_a),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(mounts.stdout, end="")
    if '"event_type": "discover.mounts.observed"' not in mounts.stdout:
        raise SystemExit("discover mounts did not emit discover.mounts.observed")
    if '"privacy": "operational"' not in mounts.stdout:
        raise SystemExit("discover.mounts.observed was not operational")
    if f"install  {install_a['install_id']}" not in mounts.stdout:
        raise SystemExit("mounts event lost InstallId correlation")
    if f"run      {persisted_run_a['install_run_id']}" not in mounts.stdout:
        raise SystemExit("mounts event lost InstallRunId correlation")
    if "host     unresolved(not_provided)" not in mounts.stdout:
        raise SystemExit("discover mounts minted or omitted host_id")
    if "safe_storage_bytes" in mounts.stdout:
        raise SystemExit("discover mounts computed SAFE storage")
    mounts_event_at = mounts.stdout.find('"event_type": "discover.mounts.observed"')
    if mounts_event_at < 0:
        raise SystemExit("discover mounts did not print an EventRecord")
    if str(root_a) in mounts.stdout[mounts_event_at:]:
        raise SystemExit("absolute state root leaked into mounts event")
    if str(control_registry) in mounts.stdout[mounts_event_at:]:
        raise SystemExit("Store path leaked into mounts event")
    if (control_registry / "mount_observation").exists():
        raise SystemExit("mount observation was persisted as Store state")
    journal_after_mounts = [
        json.loads(line)
        for line in (root_a / "journal" / "events.jsonl").read_text().splitlines()
        if line
    ]
    still_acc_mounts = next(
        item
        for item in journal_after_mounts
        if item["event_id"] == accelerator_snapshot["event_id"]
    )
    if still_acc_mounts != accelerator_snapshot:
        raise SystemExit("mount observation rewrote discover.accelerator.observed")
    mount_events = [
        item
        for item in journal_after_mounts
        if item.get("event_type") == "discover.mounts.observed"
    ]
    if not mount_events:
        raise SystemExit("journal is missing discover.mounts.observed")
    if mount_events[-1]["install_id"] != install_a["install_id"]:
        raise SystemExit("journaled mounts event lost InstallId")
    if mount_events[-1]["install_run_id"] != persisted_run_a["install_run_id"]:
        raise SystemExit("journaled mounts event lost InstallRunId")
    if "$unresolved" not in json.dumps(mount_events[-1]["host_id"]):
        raise SystemExit("mounts event resolved host_id")
    mount_payload = json.dumps(mount_events[-1]["payload"])
    if str(root_a) in mount_payload or str(control_registry) in mount_payload:
        raise SystemExit("absolute path leaked into mounts event payload")

    mount_snapshot = mount_events[-1]
    readiness = run(
        [
            str(machi),
            "prerequisites",
            "check",
            "--policy",
            "observe_only",
            "--state-root",
            str(root_a),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(readiness.stdout, end="")
    if '"kind": "prerequisite.readiness_report"' not in readiness.stdout:
        raise SystemExit("prerequisites check did not print a readiness report")
    if '"mutated": true' in readiness.stdout:
        raise SystemExit("observe_only prerequisites check mutated the host")
    if "prerequisite.remediation_started" in readiness.stdout:
        raise SystemExit("observe_only emitted a remediation start")
    journal_after_prereq = [
        json.loads(line)
        for line in (root_a / "journal" / "events.jsonl").read_text().splitlines()
        if line
    ]
    still_acc = next(
        item
        for item in journal_after_prereq
        if item["event_id"] == accelerator_events[-1]["event_id"]
    )
    if still_acc != accelerator_events[-1]:
        raise SystemExit("prerequisites check rewrote discover.accelerator.observed")
    still_mounts = next(
        item
        for item in journal_after_prereq
        if item["event_id"] == mount_snapshot["event_id"]
    )
    if still_mounts != mount_snapshot:
        raise SystemExit("prerequisites check rewrote discover.mounts.observed")
    inspected = [
        item
        for item in journal_after_prereq
        if item.get("event_type") == "prerequisite.inspected"
    ]
    if not inspected:
        raise SystemExit("journal is missing prerequisite.inspected")
    if inspected[-1]["install_id"] != install_a["install_id"]:
        raise SystemExit("journaled prerequisite event lost InstallId")
    payload = json.dumps(inspected[-1]["payload"])
    if str(root_a) in payload or str(control_registry) in payload:
        raise SystemExit("absolute path leaked into prerequisite event payload")

    steward = run(
        [
            str(machi),
            "steward",
            "assess",
            "--state-root",
            str(root_a),
            "--store-dir",
            str(control_registry),
        ],
        env=env,
    )
    print(steward.stdout, end="")
    if "verified_machi_owned" not in steward.stdout:
        raise SystemExit("steward did not verify agreeing marker and registry")
    if "delete   False" not in steward.stdout:
        raise SystemExit("steward authorized deletion")
    if "safe_storage_bytes" in steward.stdout:
        raise SystemExit("steward computed SAFE storage")
    if '"event_type": "steward.occupancy.observed"' not in steward.stdout:
        raise SystemExit("steward did not emit steward.occupancy.observed")
    if '"privacy": "operational"' not in steward.stdout:
        raise SystemExit("steward occupancy event was not operational")
    steward_at = steward.stdout.find('"event_type": "steward.resource.classified"')
    if steward_at < 0:
        raise SystemExit("steward did not print a classification event")
    if str(root_a) in steward.stdout[steward_at:]:
        raise SystemExit("absolute path leaked into steward events")
    journal_after_steward = [
        json.loads(line)
        for line in (root_a / "journal" / "events.jsonl").read_text().splitlines()
        if line
    ]
    still_mounts_after = next(
        item
        for item in journal_after_steward
        if item["event_id"] == mount_snapshot["event_id"]
    )
    if still_mounts_after != mount_snapshot:
        raise SystemExit("steward rewrote discover.mounts.observed")
    if not any(
        item.get("event_type") == "steward.occupancy.observed"
        for item in journal_after_steward
    ):
        raise SystemExit("journal is missing steward.occupancy.observed")

    print("verify_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
