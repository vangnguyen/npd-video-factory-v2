from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shlex
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[3]
WRAPPER = ROOT / "scripts/provider-execution-wrapper.sh"


@dataclass(frozen=True)
class WrapperResult:
    process: subprocess.CompletedProcess[str]
    systemctl_log: str
    child_log: str
    cleanup_log: str


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _run_wrapper(
    tmp_path: Path,
    *,
    systemctl_status: int = 0,
    role_state: str = "LOGIN",
    child_status: int = 0,
    cleanup_status: int = 0,
) -> WrapperResult:
    systemctl_log = tmp_path / "systemctl.log"
    child_log = tmp_path / "child.log"
    cleanup_log = tmp_path / "cleanup.log"
    activation = tmp_path / "runtime-activation.py"
    request = tmp_path / "request.py"
    activation.write_text("synthetic activation target\n", encoding="utf-8")
    request.write_text("synthetic request target\n", encoding="utf-8")

    systemctl = tmp_path / "systemctl"
    _write_executable(
        systemctl,
        "#!/usr/bin/env bash\n"
        "set -u\n"
        f"printf '%s\\n' \"$*\" >> {shlex.quote(str(systemctl_log))}\n"
        f"exit {systemctl_status}\n",
    )

    python = tmp_path / "python"
    _write_executable(
        python,
        "#!/usr/bin/env bash\n"
        "set -u\n"
        "target=${2:-}\n"
        "action=${3:-}\n"
        f"if test \"$target\" = {shlex.quote(str(activation))}; then\n"
        "  case \"$action\" in\n"
        "    verify-nologin)\n"
        f"      printf '%s\\n' {shlex.quote('RUNTIME_ROLE_' + role_state + '_VERIFIED')}\n"
        "      exit 0\n"
        "      ;;\n"
        "    deactivate)\n"
        f"      printf '%s\\n' cleanup >> {shlex.quote(str(cleanup_log))}\n"
        f"      exit {cleanup_status}\n"
        "      ;;\n"
        "  esac\n"
        "fi\n"
        f"if test \"$target\" = {shlex.quote(str(request))}; then\n"
        f"  printf '%s\\n' child >> {shlex.quote(str(child_log))}\n"
        f"  exit {child_status}\n"
        "fi\n"
        "exit 90\n",
    )

    source = WRAPPER.read_text(encoding="utf-8")
    replacements = {
        "/usr/bin/systemctl": str(systemctl),
        "activation=/opt/npd-video-factory/runtime/runtime-activation.py": (
            f"activation={shlex.quote(str(activation))}"
        ),
        "python=/opt/npd-video-factory/runtime/venv/bin/python": (
            f"python={shlex.quote(str(python))}"
        ),
        "request=/opt/npd-video-factory/runtime/request.py": (
            f"request={shlex.quote(str(request))}"
        ),
        'test "$(id -u)" = 0 || { echo RUNTIME_WRAPPER_ROOT_REQUIRED; exit 2; }': "true",
        "runuser -u vf-executor -- env -i \\": "env -i \\",
    }
    for old, new in replacements.items():
        assert old in source
        source = source.replace(old, new, 1)

    harness = tmp_path / "provider-execution-wrapper.sh"
    _write_executable(harness, source)
    process = subprocess.run(
        ["bash", str(harness)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**os.environ, "VF_REQUEST_JSON": "{}"},
        check=False,
    )
    return WrapperResult(
        process=process,
        systemctl_log=systemctl_log.read_text(encoding="utf-8") if systemctl_log.exists() else "",
        child_log=child_log.read_text(encoding="utf-8") if child_log.exists() else "",
        cleanup_log=cleanup_log.read_text(encoding="utf-8") if cleanup_log.exists() else "",
    )


@pytest.mark.skipif(os.name == "nt", reason="wrapper behavior requires a POSIX shell")
def test_failsafe_failure_blocks_before_child_and_cleans_up(tmp_path):
    result = _run_wrapper(tmp_path, systemctl_status=1)
    assert result.process.returncode == 2
    assert result.process.stdout.splitlines() == ["RUNTIME_FAILSAFE_PREFLIGHT_FAILED"]
    assert result.systemctl_log == "start npd-vf-runtime-role-failsafe.service\n"
    assert result.child_log == ""
    assert result.cleanup_log == "cleanup\n"


@pytest.mark.skipif(os.name == "nt", reason="wrapper behavior requires a POSIX shell")
def test_nologin_after_failsafe_blocks_before_child_and_cleans_up(tmp_path):
    result = _run_wrapper(tmp_path, role_state="NOLOGIN")
    assert result.process.returncode == 2
    assert result.process.stdout.splitlines() == ["RUNTIME_ACTIVATION_REQUIRED"]
    assert result.child_log == ""
    assert result.cleanup_log == "cleanup\n"


@pytest.mark.skipif(os.name == "nt", reason="wrapper behavior requires a POSIX shell")
def test_valid_login_window_reaches_synthetic_child_and_cleans_up(tmp_path):
    result = _run_wrapper(tmp_path, role_state="LOGIN")
    assert result.process.returncode == 0
    assert result.child_log == "child\n"
    assert result.cleanup_log == "cleanup\n"


@pytest.mark.skipif(os.name == "nt", reason="wrapper behavior requires a POSIX shell")
def test_child_failure_is_preserved_after_cleanup(tmp_path):
    result = _run_wrapper(tmp_path, role_state="LOGIN", child_status=41)
    assert result.process.returncode == 41
    assert result.child_log == "child\n"
    assert result.cleanup_log == "cleanup\n"


@pytest.mark.skipif(os.name == "nt", reason="wrapper behavior requires a POSIX shell")
def test_cleanup_failure_overrides_child_result_and_fails_closed(tmp_path):
    result = _run_wrapper(tmp_path, role_state="LOGIN", cleanup_status=1)
    assert result.process.returncode == 70
    assert result.process.stdout.splitlines() == ["REVIEW_REQUIRED_RUNTIME_ROLE_STILL_ACTIVE"]
    assert result.child_log == "child\n"
    assert result.cleanup_log == "cleanup\n"


def test_preflight_has_no_provider_secret_budget_or_transport_boundary():
    source = WRAPPER.read_text(encoding="utf-8")
    preflight = source.split("runuser -u vf-executor", 1)[0]
    assert "VF_REQUEST_JSON" not in preflight
    assert "credential" not in preflight.lower()
    assert "budget" not in preflight.lower()
    assert "provider call" not in preflight.lower()
