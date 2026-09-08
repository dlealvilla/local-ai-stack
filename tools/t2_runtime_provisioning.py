"""Stage 1.6C T2: clean wheel proves runtime provisioning.

Installs the committed wheel into an isolated venv with no source checkout.
Proves Host → RuntimeResolver → RuntimeCandidate → ProvisioningPlan →
fixture Provision → RuntimeInstallation, plus API, CLI, Console assets,
persistence, idempotency, explicit retry, and the absence of a verify
route. Does not install or import real vLLM.
"""

# ruff: noqa: E501

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
    evidence: dict[str, object] = {
        "wheel": wheel.name,
        "real_llm": False,
        "prompt_inference": False,
        "vllm_imported": False,
        "engine_initialized": False,
        "verify": False,
        "fixture_provisioner": True,
    }
    with tempfile.TemporaryDirectory(prefix="kultrun-t2-16c-") as workspace:
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
        env["KULTRUN_RUNTIME_PROVISIONER"] = "fixture"
        env["PYTHONNOUSERSITE"] = "1"
        env.pop("PYTHONPATH", None)
        env.pop("KULTRUN_EXECUTOR", None)

        installed = run(
            [str(python), "-m", "pip", "install", "--quiet", str(wheel)], env
        )
        if installed.returncode != 0:
            print(installed.stderr)
            return 1
        origin = run(
            [str(python), "-c", "import kultrun; print(kultrun.__file__)"], env
        )
        evidence["install_origin"] = (origin.stdout or "").strip()
        if str(REPOSITORY) in (origin.stdout or ""):
            print("FAIL: installed package resolved from the source checkout")
            return 1

        version = run([str(kultrun), "version"], env)
        if version.returncode != 0:
            print(version.stderr or version.stdout)
            return 1
        evidence["version"] = version.stdout.strip()

        host = run([str(kultrun), "host"], env)
        if host.returncode != 0:
            print(host.stderr or host.stdout)
            return 1
        evidence["host"] = True

        proof = run(
            [
                str(python),
                "-c",
                """
import json
from kultrun.api.contracts import ApiRequest, Method
from kultrun.main import build, resolve_configuration
from kultrun.runtime.contracts import InstallationStatus

p = build(resolve_configuration())
host = p.hosts.current
req = ApiRequest(method=Method.GET, path='/v1/runtimes/candidates')
auto = p.router.handle(req)
assert auto.status == 200
payload = auto.body['payload']
assert payload['mutations'] is False
assert payload['install'] is False
assert payload['verify'] is False
resolution = payload['resolution']
native = next(
    item
    for item in resolution['candidates']
    if item['runtime'] == 'vllm' and item['executor'] == 'native-process'
)
assert native.get('version') == '0.28.0'
created = p.router.handle(
    ApiRequest(
        method=Method.POST,
        path='/v1/runtimes/provisioning-plans',
        query={'candidate_id': native['candidate_id']},
    )
)
assert created.status == 200
plan = created.body['payload']
assert plan['runtime'] == 'vllm'
assert plan['runtime_version'] == '0.28.0'
assert plan['executor'] == 'native-process'
assert plan['python_version'] == '3.12'
first = p.router.handle(
    ApiRequest(
        method=Method.POST,
        path='/v1/runtimes/provision',
        query={'plan_id': plan['plan_id']},
    )
)
assert first.status == 200
installation = first.body['payload']
assert installation['status'] == 'installed'
assert 'verified' not in installation
repeat = p.router.handle(
    ApiRequest(
        method=Method.POST,
        path='/v1/runtimes/provision',
        query={'plan_id': plan['plan_id']},
    )
)
assert repeat.status == 200
assert repeat.body['payload']['installation_id'] == installation['installation_id']
plans = p.router.handle(ApiRequest(method=Method.GET, path='/v1/runtimes/provisioning-plans'))
assert plans.status == 200
listed = p.router.handle(ApiRequest(method=Method.GET, path='/v1/runtimes/installations'))
assert listed.status == 200
assert listed.body['payload']['verified'] is False
verify = p.router.handle(ApiRequest(method=Method.POST, path='/v1/runtimes/verify'))
assert verify.status == 404
record = p.provisioning.get_installation(
    p.provisioning.installations()[0].installation_id
)
assert record.status is InstallationStatus.INSTALLED
print(json.dumps({
    'api': auto.status,
    'plan_id': plan['plan_id'],
    'installation_id': installation['installation_id'],
    'status': installation['status'],
    'runtime_version': plan['runtime_version'],
    'idempotent': True,
    'verify_status': verify.status,
}))
""",
            ],
            env,
        )
        if proof.returncode != 0:
            print(proof.stderr or proof.stdout)
            return 1
        try:
            payload = json.loads(proof.stdout.strip().splitlines()[-1])
        except json.JSONDecodeError:
            print("FAIL: proof output", proof.stdout)
            return 1
        evidence.update(payload)

        candidates = run([str(kultrun), "runtimes", "candidates"], env)
        if candidates.returncode != 0:
            print(candidates.stderr or candidates.stdout)
            return 1
        evidence["cli_candidates"] = True
        native_line = next(
            (
                line
                for line in candidates.stdout.splitlines()
                if "vllm" in line and "native-process" in line and "rcand_" in line
            ),
            "",
        )
        parts = native_line.split()
        candidate_id = next((part for part in parts if part.startswith("rcand_")), "")
        if not candidate_id:
            print("FAIL: CLI candidates", candidates.stdout)
            return 1
        planned = run([str(kultrun), "runtimes", "plan", candidate_id], env)
        if planned.returncode != 0:
            print(planned.stderr or planned.stdout)
            return 1
        if "vllm==0.28.0" not in planned.stdout:
            print("FAIL: plan CLI", planned.stdout)
            return 1
        evidence["cli_plan"] = planned.stdout.strip()

        provisioned = run(
            [str(kultrun), "runtimes", "provision", str(payload["plan_id"])], env
        )
        if provisioned.returncode != 0:
            print(provisioned.stderr or provisioned.stdout)
            return 1
        if "installed" not in provisioned.stdout:
            print("FAIL: provision CLI", provisioned.stdout)
            return 1
        evidence["cli_provision"] = provisioned.stdout.strip()

        listed = run([str(kultrun), "runtimes", "installations"], env)
        if listed.returncode != 0:
            print(listed.stderr or listed.stdout)
            return 1
        if "verified false" not in listed.stdout:
            print("FAIL: installations CLI", listed.stdout)
            return 1
        evidence["cli_installations"] = listed.stdout.strip()

        inspect = run(
            [
                str(python),
                "-c",
                "from kultrun.adapters.http.console import ASSETS, read;"
                "html=read('index.html').decode(); js=read('app.js').decode();"
                "panel=html.split('Runtime candidates',1)[1].split('<section',1)[0];"
                "print(all(read(n) for n in ASSETS),"
                " 'Runtime candidates' in html,"
                " '/runtimes/provisioning-plans' in js,"
                " 'Create plan' in js,"
                " 'Provision' in js,"
                " 'Verify' not in panel,"
                " 'Launch Model' not in html)",
            ],
            env,
        )
        evidence["console"] = inspect.stdout.strip()
        evidence["source_checkout"] = False
        print(json.dumps(evidence, indent=2))
        if payload.get("api") != 200 or payload.get("verify_status") != 404:
            print("FAIL: API", payload)
            return 1
        if "True True True True True True True" not in inspect.stdout:
            print("FAIL: Console", inspect.stdout)
            return 1
        probe = run([str(python), "-c", "import vllm"], env)
        if probe.returncode == 0:
            print("FAIL: vLLM importable in T2 environment")
            return 1
        evidence["vllm_imported"] = False
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
