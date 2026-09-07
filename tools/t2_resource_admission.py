"""Stage 1.5A T2: clean wheel, fixture inventory, reserve, release, restart.

Run from a committed tree after `tools/build_prototype.py`.
Installs the wheel into an isolated venv with no source checkout on path.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from venv import EnvBuilder

REPOSITORY = Path(__file__).resolve().parent.parent
DIST = REPOSITORY / "dist"
NEUTRAL = Path(tempfile.gettempdir())
TINY = "tinyllama-1.1b-chat-q4"
FOURTEEN = "qwen2.5-14b-instruct-q4"


def latest_wheel() -> Path:
    wheels = sorted(DIST.glob("*.whl"), key=lambda path: path.stat().st_mtime)
    if not wheels:
        raise SystemExit("no wheel in dist/; run tools/build_prototype.py first")
    return wheels[-1]


def run(
    argv: list[str], env: dict[str, str], cwd: Path = NEUTRAL
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, capture_output=True, text=True, check=False, cwd=str(cwd), env=env
    )


def main() -> int:
    wheel = latest_wheel()
    evidence: dict[str, object] = {"wheel": wheel.name}
    with tempfile.TemporaryDirectory(prefix="kultrun-t2-15a-") as workspace:
        root = Path(workspace)
        environment = root / "env"
        EnvBuilder(with_pip=True, system_site_packages=False).create(environment)
        python = environment / "bin" / "python"
        kultrun = environment / "bin" / "kultrun"
        state = root / "state"
        env = os.environ.copy()
        env["KULTRUN_STATE_ROOT"] = str(state)
        env["KULTRUN_FIXTURE"] = "linux-x86_64-nvidia-blackwell-rtxpro4500"
        env["KULTRUN_MODEL_ACQUISITION_PROVIDER"] = "fixture"
        env["PYTHONNOUSERSITE"] = "1"
        env.pop("PYTHONPATH", None)

        installed = run(
            [str(python), "-m", "pip", "install", "--quiet", str(wheel)], env
        )
        if installed.returncode != 0:
            print(installed.stderr)
            return 1
        spec = run(
            [
                str(python),
                "-c",
                "import kultrun; print(kultrun.__file__)",
            ],
            env,
        )
        origin = (spec.stdout or "").strip()
        evidence["install_origin"] = origin
        if str(REPOSITORY) in origin:
            print("FAIL: installed package resolved from the source checkout")
            return 1

        host = run([str(kultrun), "host"], env)
        for name in (TINY, FOURTEEN):
            acquired = run(
                [str(kultrun), "models", "acquire", "--store-only", name], env
            )
            if acquired.returncode != 0:
                print(acquired.stderr or acquired.stdout)
                return 1
        empty = run([str(kultrun), "resources"], env)
        ids = run(
            [
                str(python),
                "-c",
                "from kultrun.main import build, resolve_configuration;"
                "p=build(resolve_configuration());"
                "print('\\n'.join(str(a.logical_name)+' '+a.artifact_id.value"
                " for a in p.inventory.artifacts()))",
            ],
            env,
        )
        by_name = {}
        for line in ids.stdout.splitlines():
            name, token = line.split(None, 1)
            by_name[name] = token
        if len(by_name) < 2:
            print("FAIL: expected two stored artifacts", ids.stdout)
            return 1

        provisioned = run(
            [str(kultrun), "runtimes", "provision", "fixture-vllm"], env
        )
        if provisioned.returncode != 0:
            print(provisioned.stderr or provisioned.stdout)
            return 1
        installation_id = provisioned.stdout.split()[1]
        verified = run(
            [str(kultrun), "runtimes", "verify", installation_id], env
        )
        if verified.returncode != 0:
            print(verified.stderr or verified.stdout)
            return 1
        recommended = run([str(kultrun), "models", "recommend"], env)
        if recommended.returncode != 0 or "plan " not in recommended.stdout:
            print(recommended.stderr or recommended.stdout)
            return 1
        plan_id = next(
            line.split()[1]
            for line in recommended.stdout.splitlines()
            if line.startswith("plan ")
        )
        planned = run(
            [str(kultrun), "models", "acquire", "--plan", plan_id], env
        )
        if planned.returncode != 0:
            print(planned.stderr or planned.stdout)
            return 1
        first = run([str(kultrun), "resources", "reserve", plan_id], env)
        second = run([str(kultrun), "resources", "reserve", plan_id], env)
        denied = run([str(kultrun), "resources", "reserve", plan_id], env)
        listing = run([str(kultrun), "resources", "reservations"], env)
        fourteen_id = run(
            [
                str(python),
                "-c",
                "from kultrun.main import build, resolve_configuration;"
                "p=build(resolve_configuration());"
                "print('\\n'.join(r.reservation_id.value+' '+str(r.logical_name)"
                " for r in p.resources.reservations()))",
            ],
            env,
        )
        release_id = ""
        for line in fourteen_id.stdout.splitlines():
            token, _name = line.split(None, 1)
            release_id = token
            break
        released = run([str(kultrun), "resources", "release", release_id], env)
        later = run([str(kultrun), "resources", "reserve", plan_id], env)
        after = run([str(kultrun), "resources"], env)
        restart = run(
            [
                str(python),
                "-c",
                "from kultrun.main import build, resolve_configuration;"
                "from kultrun.resource.contracts import ReservationState;"
                "p=build(resolve_configuration());"
                "s=p.resources.summary(p.capacity.compute("
                "p.hosts.current, {}));"
                "active=list(p.resources.reservations());"
                "print(len(active), s.active_count, s.health.value,"
                " s.running_instances, s.serving,"
                " all(r.state is ReservationState.ACTIVE for r in active))",
            ],
            env,
        )
        api = run(
            [
                str(python),
                "-c",
                "from kultrun.api.contracts import ApiRequest, Method;"
                "from kultrun.main import build, resolve_configuration;"
                "p=build(resolve_configuration());"
                "r=p.router.handle(ApiRequest(Method.GET,'/v1/resources'));"
                "print(r.status, r.body['payload']['running_instances'],"
                " r.body['payload']['serving'],"
                " r.body['payload']['summary']['active_count'])",
            ],
            env,
        )
        console = run(
            [
                str(python),
                "-c",
                "from kultrun.adapters.http.console import ASSETS, read;"
                "html=read('index.html').decode(); js=read('app.js').decode();"
                "print(all(read(n) for n in ASSETS),"
                " 'Resource reservations' in html,"
                " 'Reserved resources are platform commitments' in html,"
                " '/resources' in js)",
            ],
            env,
        )
        executions = run(
            [
                str(python),
                "-c",
                "from kultrun.main import build, resolve_configuration;"
                "p=build(resolve_configuration());"
                "print(len(p.executions.list()), 0)",
            ],
            env,
        )
        evidence["host_ok"] = host.returncode == 0
        evidence["initial_summary"] = empty.stdout.strip()
        evidence["first_reservation"] = first.stdout.strip()
        evidence["second_reservation"] = second.stdout.strip()
        evidence["rejected_over_capacity"] = denied.stdout.strip()
        evidence["rejected_exit"] = denied.returncode
        evidence["listing"] = listing.stdout.strip()
        evidence["released"] = released.stdout.strip()
        evidence["subsequent_admission"] = later.stdout.strip()
        evidence["after_summary"] = after.stdout.strip()
        evidence["restart"] = restart.stdout.strip()
        evidence["api"] = api.stdout.strip()
        evidence["console"] = console.stdout.strip()
        evidence["executions"] = executions.stdout.strip()
        evidence["source_checkout"] = False
        print(json.dumps(evidence, indent=2))
        if first.returncode != 0 or second.returncode != 0:
            print(first.stderr, second.stderr)
            return 1
        if denied.returncode == 0:
            print("FAIL: over-capacity request was admitted")
            return 1
        if later.returncode != 0 or released.returncode != 0:
            print(later.stderr or released.stderr)
            return 1
        if "admitted" not in first.stdout or "rejected" not in denied.stdout:
            print("FAIL: expected admit then reject")
            return 1
        if restart.returncode != 0 or not restart.stdout.startswith("2 2"):
            print("FAIL: restart did not keep two ACTIVE reservations", restart.stdout)
            return 1
        if api.returncode != 0 or not api.stdout.startswith("200 0 False 2"):
            print("FAIL: API", api.stdout, api.stderr)
            return 1
        if "True True True True" not in console.stdout:
            print("FAIL: Console", console.stdout)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
