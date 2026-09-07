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
            [str(kultrun), "models", "acquire", "--store-only", "tinyllama-1.1b-chat-q4"],
            env,
        )
        if stored.returncode != 0:
            print(stored.stderr or stored.stdout)
            return 1
        reserved = run([str(kultrun), "resources", "reserve", plan_id], env)
        if reserved.returncode != 0:
            print(reserved.stderr or reserved.stdout)
            return 1
        evidence["recommend"] = recommended.stdout
        evidence["acquire"] = acquired.stdout
        evidence["store_only"] = stored.stdout
        evidence["reserve"] = reserved.stdout
        print(json.dumps(evidence, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
