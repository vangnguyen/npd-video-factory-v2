"""Validate VF-V0S-B10 evidence without entering an execution boundary."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
AUTHORITY_DIR = REPO / "docs/acceptance/v3-01/authority/vf-v0s-b9-rc19-asr-w1-op1"
BASE_HEAD = "7ad25cb039c712d450486778d2981d9ef8175385"

sys.path.insert(0, str(REPO / "apps/api"))
sys.path.insert(0, str(REPO / "scripts"))

from app.provider_ci_provenance import executable_tree_sha256  # noqa: E402
from app.provider_gate_loader import canonical_sha256  # noqa: E402
from v3_01_ci_provenance import _git_object_map  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, check=True, capture_output=True, text=True
    ).stdout


def validate(final: bool = False) -> dict:
    spec = importlib.util.spec_from_file_location(
        "vf_v0s_b9_materializer", AUTHORITY_DIR / "materialize_and_validate.py"
    )
    assert spec is not None and spec.loader is not None
    materializer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(materializer)
    bundle_result = materializer.validate_materials()
    assert bundle_result["status"] == "PASS"

    handoff_json_path = REPO / "docs/acceptance/v3-01/handoff.json"
    handoff_md_path = REPO / "docs/acceptance/v3-01/HANDOFF.md"
    handoff = read_json(handoff_json_path)
    markdown = handoff_md_path.read_text(encoding="utf-8")
    bootstrap = read_json(HERE / "bootstrap-cli-result.json")
    ledger = read_json(HERE / "ledger-readback.json")
    task = read_json(HERE / "task-result.json")
    final_bundle = read_json(HERE / "final-bundle-validation.json")

    assert handoff["task_id"] == task["task_id"] == "VF-V0S-B10"
    assert handoff["verdict"] == task["verdict"] == "PASS"
    assert handoff["bootstrap"]["result"] == task["bootstrap_result"] == "BOOTSTRAP_BINDING_VALID"
    assert handoff["bootstrap"]["rc19_operation_bound_bootstrap"] == "VERIFIED"
    assert handoff["bootstrap"]["ready_state"] == task["ready_state"] == "READY_FOR_EXECUTION_PREFLIGHT"
    assert handoff["bootstrap"]["provider_dispatch_ready"] is task["provider_dispatch_ready"] is False
    assert bootstrap["exit_code"] == 0
    assert bootstrap["output"]["result"] == "CUSTODY_VERIFIED_NOT_EXECUTION_AUTHORIZED"
    assert ledger["readback_result"] == "PASS / VIRGIN / READ_ONLY"
    assert ledger["operation_record_exists"] is ledger["operation_consumed"] is False
    assert ledger["provider_request_receipt"] == "NONE"
    assert ledger["active_reservation"] is ledger["duplicate_or_idempotency_collision"] is False
    assert final_bundle["gate_loader"] == "PASS / VALID_IN_MEMORY_NOT_MOUNTED"
    assert final_bundle["bundle_mounted"] is False

    manifest = read_json(AUTHORITY_DIR / "manifest.json")
    assert sha(REPO / manifest["final_bundle_path"]) == manifest["final_runtime_bundle_sha256"]
    assert sha(AUTHORITY_DIR / "operation-1-authority.json") == manifest["authority_receipt_raw_sha256"]
    assert sha(AUTHORITY_DIR / "bootstrap-binding.json") == bootstrap["binding_sha256"]
    for gate, item in manifest["approval_records"].items():
        record = read_json(REPO / item["record_path"])
        assert canonical_sha256(record) == item["canonical_record_sha256"], gate

    safety = handoff["safety"]
    assert safety == {
        "actual_cost_vnd": "0",
        "budget_reserved_vnd": "0",
        "bundle_mounted": False,
        "credential_reads": 0,
        "kill_switch": "ENGAGED",
        "production_business_writes": 0,
        "real_provider_calls": 0,
    }
    assert handoff["authority"]["operation_1_consumed"] is False
    assert handoff["authority"]["operation_2"] == "NOT_APPROVED / LOCKED / NOT_TRANSFERRED"

    for value in (
        handoff["baseline"]["governance_main_sha"],
        handoff["baseline"]["rc_commit"],
        handoff["baseline"]["executable_tree_sha256"],
        handoff["baseline"]["dual_ci_provenance_sha256"],
        handoff["operation"]["id"],
        handoff["gate"]["final_runtime_bundle_sha256"],
        handoff["gate"]["loaded_runtime_scope_sha256"],
        handoff["authority"]["receipt_sha256"],
        handoff["bootstrap"]["binding_sha256"],
        handoff["bootstrap"]["ready_state"],
        handoff["ledger"]["identity"],
    ):
        assert str(value) in markdown

    changed = sorted(
        set(git("diff", "--name-only", BASE_HEAD).splitlines())
        | set(git("ls-files", "--others", "--exclude-standard").splitlines())
    )
    allowed_tests = {
        "apps/api/tests/test_rc19_asr_w1_prepared_rebind.py",
        "apps/api/tests/test_vf_v0s_b8_operation_bootstrap_qualification.py",
        "apps/api/tests/test_vf_v0s_b9_final_authority.py",
        "apps/api/tests/test_vf_v0s_b10_final_bootstrap_qualification.py",
    }
    assert all(
        path in allowed_tests
        or path.startswith("docs/acceptance/v3-01/")
        or path.startswith("evidence/v3-01/vf-v0s-b7-")
        or path.startswith("evidence/v3-01/vf-v0s-b8-")
        or path.startswith("evidence/v3-01/vf-v0s-b9-")
        or path.startswith("evidence/v3-01/vf-v0s-b10-")
        for path in changed
    ), changed

    tree = executable_tree_sha256(_git_object_map(REPO, "HEAD"))
    assert tree == "432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502"
    assert _git_object_map(REPO, "HEAD") == _git_object_map(REPO, BASE_HEAD)
    assert subprocess.run(
        ["git", "diff", "--check", BASE_HEAD], cwd=REPO, capture_output=True
    ).returncode == 0

    files = sorted(
        {
            handoff_json_path,
            handoff_md_path,
            REPO / "apps/api/tests/test_vf_v0s_b10_final_bootstrap_qualification.py",
            *HERE.rglob("*"),
        }
    )
    files = [
        path
        for path in files
        if path.is_file() and path.suffix.lower() in {".json", ".md", ".py", ".txt"}
    ]
    secret_patterns = [
        re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{16,}"),
        re.compile(
            r"(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*[\"']?[A-Za-z0-9._-]{20,}"
        ),
    ]
    json_files = 0
    links = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not any(pattern.search(text) for pattern in secret_patterns), path
        if path.suffix == ".json":
            json.loads(text)
            json_files += 1
        if path.suffix == ".md":
            for _, target in re.findall(r"\[([^]\n]+)\]\(([^)\n]+)\)", text):
                if target.startswith(("https://", "http://", "#", "mailto:")):
                    continue
                resolved = (path.parent / unquote(target.split("#", 1)[0]).strip("<>")).resolve()
                assert resolved.is_relative_to(REPO) and resolved.is_file(), (path, target)
                links += 1

    seals = []
    if final:
        manifest_path = HERE / "SHA256SUMS.txt"
        listed = set()
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            expected, name = re.split(r"\s+", line, maxsplit=1)
            name = name.lstrip("*")
            assert sha(HERE / name) == expected
            listed.add(name)
        assert listed == {
            path.name for path in HERE.iterdir() if path.is_file() and path.name != "SHA256SUMS.txt"
        }
        expected_handoff = {
            handoff_md_path.relative_to(REPO).as_posix(): sha(handoff_md_path),
            handoff_json_path.relative_to(REPO).as_posix(): sha(handoff_json_path),
        }
        assert read_json(HERE / "handoff-checksums.json")["hashes"] == expected_handoff
        seals.append({"entries": len(listed), "manifest_sha256": sha(manifest_path)})

    return {
        "actual_cost_vnd": "0",
        "authority_status": "GRANTED_NOT_CONSUMED",
        "bootstrap_result": "BOOTSTRAP_BINDING_VALID",
        "budget_reserved_vnd": "0",
        "bundle_mounted": False,
        "changed_files": changed,
        "credential_reads": 0,
        "executable_tree_changed": False,
        "executable_tree_sha256": tree,
        "gate_loader": bundle_result["gate_loader"],
        "git_diff_check": "PASS",
        "json_files_parsed": json_files,
        "kill_switch": "ENGAGED",
        "links_checked": links,
        "manifest_verification": seals,
        "operation_1_consumed": False,
        "production_business_writes": 0,
        "provider_calls": 0,
        "ready_state": "READY_FOR_EXECUTION_PREFLIGHT",
        "rc19_operation_bound_bootstrap": "VERIFIED",
        "scope_drift": "PASS",
        "secret_scan": "PASS",
        "status": "PASS",
        "task_id": "VF-V0S-B10",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    print(json.dumps(validate(final=args.final), ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
