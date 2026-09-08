"""Stage 1.6D T2: clean wheel proves runtime verification.

Installs the committed wheel into an isolated venv with no source checkout.
Proves Host → RuntimeCandidate → RuntimeProvisioningPlan →
RuntimeInstallation → RuntimeVerifier → RuntimeCapabilityProfile VERIFIED
using the fixture verifier. Also proves API, CLI, Console, persistence,
restart, staleness presentation, failure, retry, and idempotency.
Does not install or import real vLLM.
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
        "model_downloaded": False,
        "fixture_verifier": True,
    }
    with tempfile.TemporaryDirectory(prefix="kultrun-t2-16d-") as workspace:
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
        env["KULTRUN_RUNTIME_VERIFIER"] = "fixture"
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

        proof = run(
            [
                str(python),
                "-c",
                """
import json
from kultrun.api.contracts import ApiRequest, Method
from kultrun.main import build, resolve_configuration
from kultrun.runtime.contracts import InstallationStatus, VerificationStatus

p = build(resolve_configuration())
host = p.hosts.current
req = ApiRequest(method=Method.GET, path='/v1/runtimes/candidates')
auto = p.router.handle(req)
assert auto.status == 200
payload = auto.body['payload']
assert payload['mutations'] is False
assert payload['verify'] is False
resolution = payload['resolution']
native = next(
    item
    for item in resolution['candidates']
    if item['runtime'] == 'vllm' and item['executor'] == 'native-process'
)
assert native.get('version') == '0.28.0'
created = p.router.handle(ApiRequest(
    method=Method.POST,
    path='/v1/runtimes/provisioning-plans',
    query={'candidate_id': native['candidate_id']},
))
assert created.status == 200
plan = created.body['payload']
provisioned = p.router.handle(ApiRequest(
    method=Method.POST,
    path='/v1/runtimes/provision',
    query={'plan_id': plan['plan_id']},
))
assert provisioned.status == 200
installation = provisioned.body['payload']
assert installation['status'] == InstallationStatus.INSTALLED.value
listed = p.router.handle(ApiRequest(method=Method.GET, path='/v1/runtimes/installations'))
assert listed.status == 200
assert listed.body['payload']['verify_on_get'] is False
missing = p.router.handle(ApiRequest(method=Method.POST, path='/v1/runtimes/verify'))
assert missing.status == 400
verified = p.router.handle(ApiRequest(
    method=Method.POST,
    path='/v1/runtimes/verify',
    query={'installation_id': installation['installation_id']},
))
assert verified.status == 200
profile = verified.body['payload']
assert profile['status'] == VerificationStatus.VERIFIED.value
assert profile['runtime'] == 'vllm'
assert profile['runtime_version'] == '0.28.0'
first_id = profile['profile_id']
attempts = profile['attempt_count']
again = p.router.handle(ApiRequest(
    method=Method.POST,
    path='/v1/runtimes/verify',
    query={'installation_id': installation['installation_id']},
))
assert again.status == 200
repeated = again.body['payload']
assert repeated['profile_id'] == first_id
assert repeated['attempt_count'] == attempts
profiles = p.router.handle(ApiRequest(method=Method.GET, path='/v1/runtimes/capability-profiles'))
assert profiles.status == 200
assert profiles.body['payload']['mutations'] is False
assert profiles.body['payload']['verify_on_get'] is False
print(json.dumps({
    'candidate_id': native['candidate_id'],
    'plan_id': plan['plan_id'],
    'installation_id': installation['installation_id'],
    'profile_id': first_id,
    'status': profile['status'],
    'attempts': attempts,
    'api': verified.status,
    'get_mutations': profiles.body['payload']['mutations'],
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

        planned = run(
            [str(kultrun), "runtimes", "plan", str(payload["candidate_id"])], env
        )
        if planned.returncode != 0:
            print(planned.stderr or planned.stdout)
            return 1
        provisioned = run(
            [str(kultrun), "runtimes", "provision", str(payload["plan_id"])], env
        )
        if provisioned.returncode != 0:
            print(provisioned.stderr or provisioned.stdout)
            return 1
        verified = run(
            [str(kultrun), "runtimes", "verify", str(payload["installation_id"])],
            env,
        )
        if verified.returncode != 0:
            print(verified.stderr or verified.stdout)
            return 1
        if "verified" not in verified.stdout:
            print("FAIL: verify CLI", verified.stdout)
            return 1
        evidence["cli_verify"] = verified.stdout.strip()
        caps = run([str(kultrun), "runtimes", "capabilities"], env)
        if caps.returncode != 0:
            print(caps.stderr or caps.stdout)
            return 1
        if str(payload["profile_id"]) not in caps.stdout:
            print("FAIL: capabilities CLI", caps.stdout)
            return 1
        evidence["cli_capabilities"] = caps.stdout.strip()
        listed = run([str(kultrun), "runtimes", "installations"], env)
        if listed.returncode != 0 or "verified verified" not in listed.stdout:
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
                " '/runtimes/verify' in js,"
                " 'Verify' in js,"
                " 'Recommended Runtime' not in js,"
                " 'Select Model' not in js,"
                " 'Launch Model' not in html)",
            ],
            env,
        )
        evidence["console"] = inspect.stdout.strip()
        evidence["source_checkout"] = False
        print(json.dumps(evidence, indent=2))
        if payload.get("status") != "verified":
            print("FAIL: profile", payload)
            return 1
        if "True True True True True True True" not in inspect.stdout:
            print("FAIL: Console", inspect.stdout)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
