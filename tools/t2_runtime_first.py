"""Stage 1.6 T2: clean wheel, runtime-first funnel, STORE_ONLY, stale profile.

Run from a committed tree after `tools/build_prototype.py`.
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
    evidence: dict[str, object] = {"wheel": wheel.name, "real_llm": False}
    with tempfile.TemporaryDirectory(prefix="kultrun-t2-16-") as workspace:
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
        origin = run(
            [str(python), "-c", "import kultrun; print(kultrun.__file__)"], env
        )
        if str(REPOSITORY) in (origin.stdout or ""):
            print("FAIL: installed package resolved from the source checkout")
            return 1

        blocked = run([str(kultrun), "models", "recommend"], env)
        if "runtime_not_verified" not in (blocked.stdout + blocked.stderr):
            print("FAIL: recommendation was not blocked before verification")
            print(blocked.stdout, blocked.stderr)
            return 1

        provisioned = run([str(kultrun), "runtimes", "provision", "fixture-vllm"], env)
        if provisioned.returncode != 0:
            print(provisioned.stderr or provisioned.stdout)
            return 1
        installation_id = provisioned.stdout.split()[1]
        verified = run(
            [str(kultrun), "runtimes", "verify", installation_id], env
        )
        if verified.returncode != 0 or "verified" not in verified.stdout:
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
        acquired = run(
            [str(kultrun), "models", "acquire", "--plan", plan_id], env
        )
        if acquired.returncode != 0:
            print(acquired.stderr or acquired.stdout)
            return 1
        stored = run(
            [
                str(kultrun),
                "models",
                "acquire",
                "--store-only",
                "tinyllama-1.1b-chat-q4",
            ],
            env,
        )
        if stored.returncode != 0:
            print(stored.stderr or stored.stdout)
            return 1
        reserved = run([str(kultrun), "resources", "reserve", plan_id], env)
        if reserved.returncode != 0:
            print(reserved.stderr or reserved.stdout)
            return 1
        reservation_id = reserved.stdout.split()[1]
        created = run(
            [str(kultrun), "instances", "create", reservation_id], env
        )
        if created.returncode != 0:
            print(created.stderr or created.stdout)
            return 1
        instance_id = created.stdout.split()[0]
        started = run([str(kultrun), "instances", "start", instance_id], env)
        if started.returncode != 0:
            print(started.stderr or started.stdout)
            return 1
        stopped = run([str(kultrun), "instances", "stop", instance_id], env)
        if stopped.returncode != 0:
            print(stopped.stderr or stopped.stdout)
            return 1
        released = run(
            [str(kultrun), "resources", "release", reservation_id], env
        )
        if released.returncode != 0:
            print(released.stderr or released.stdout)
            return 1

        stale = run(
            [
                str(python),
                "-c",
                "from dataclasses import replace;"
                "from kultrun.main import build, resolve_configuration;"
                "from kultrun.runtime.contracts import VerificationStatus;"
                "p=build(resolve_configuration());"
                "host=p.hosts.current;"
                "profile=p.runtime_setup.verified(host)[0];"
                "p.runtime_setup.evidence.put_profile("
                "replace(profile, status=VerificationStatus.STALE));"
                "state=p.deployment.recommend(host, {})['state'];"
                "print(state)",
            ],
            env,
        )
        if stale.stdout.strip() != "runtime_not_verified":
            print("FAIL: stale profile still recommended", stale.stdout, stale.stderr)
            return 1
        rejected = run(
            [str(kultrun), "models", "acquire", "--plan", plan_id], env
        )
        if rejected.returncode == 0:
            print("FAIL: stale plan acquired")
            return 1

        api = run(
            [
                str(python),
                "-c",
                "from kultrun.adapters.http.console import ASSETS, read;"
                "from kultrun.api.contracts import ApiRequest, Method;"
                "from kultrun.main import build, resolve_configuration;"
                "html=read('index.html').decode(); js=read('app.js').decode();"
                "print(all(read(n) for n in ASSETS),"
                " 'Runtime setup' in html,"
                " 'Store Only' in js,"
                " 'Acquire from plan' in js,"
                " 'does not recommend' in html)",
            ],
            env,
        )
        candidates = run([str(kultrun), "runtimes", "candidates"], env)
        evidence["recommend"] = recommended.stdout
        evidence["acquire"] = acquired.stdout
        evidence["store_only"] = stored.stdout
        evidence["reserve"] = reserved.stdout
        evidence["instance"] = started.stdout
        evidence["stop"] = stopped.stdout
        evidence["release"] = released.stdout
        evidence["stale_recommend"] = stale.stdout.strip()
        evidence["stale_acquire_exit"] = rejected.returncode
        evidence["console"] = api.stdout.strip()
        evidence["candidates"] = candidates.stdout.strip().splitlines()[:6]
        evidence["source_checkout"] = False
        print(json.dumps(evidence, indent=2))
        if started.returncode != 0 or "running" not in started.stdout:
            print("FAIL: instance did not start", started.stdout)
            return 1
        if "True True True True True" not in api.stdout:
            print("FAIL: Console", api.stdout)
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
