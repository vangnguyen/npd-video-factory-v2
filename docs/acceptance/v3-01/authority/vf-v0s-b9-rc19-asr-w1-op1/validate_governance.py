"""Validate B9 governance/evidence without activating any runtime boundary."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
EVIDENCE = REPO / "evidence/v3-01/vf-v0s-b9-20260915-final-authority"
BASE_HEAD = "2a160e314a45928eadeef4dffafeb45d8c718ded"
sys.path.insert(0, str(REPO / "apps/api"))
sys.path.insert(0, str(REPO / "scripts"))

from app.provider_ci_provenance import executable_tree_sha256  # noqa: E402
from v3_01_ci_provenance import _git_object_map  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, check=True, capture_output=True, text=True
    ).stdout


def no_network(*args: object, **kwargs: object) -> None:
    raise AssertionError("VF_V0S_B9_GOVERNANCE_VALIDATION_FORBIDS_NETWORK")


def validate(final: bool = False) -> dict:
    spec = importlib.util.spec_from_file_location("vf_v0s_b9", HERE / "materialize_and_validate.py")
    assert spec is not None and spec.loader is not None
    materializer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(materializer)
    generated = materializer.validate_materials()
    assert generated["status"] == "PASS"

    handoff_json = REPO / "docs/acceptance/v3-01/handoff.json"
    handoff_md = REPO / "docs/acceptance/v3-01/HANDOFF.md"
    handoff = json.loads(handoff_json.read_text(encoding="utf-8"))
    markdown = handoff_md.read_text(encoding="utf-8")
    assert handoff["task_id"] == "VF-V0S-B9" and handoff["verdict"] == "PASS"
    assert handoff["authority"]["status"] == "GRANTED_NOT_CONSUMED"
    assert handoff["authority"]["operation_1_consumed"] is False
    assert handoff["authority"]["operation_2"] == "NOT_APPROVED / LOCKED / NOT_TRANSFERRED"
    assert handoff["gate"]["gate_loader"] == "PASS / VALID_IN_MEMORY_NOT_MOUNTED"
    assert handoff["ledger"]["mutations"] == 0
    assert handoff["ledger"]["operation_record_exists"] is False
    assert handoff["ledger"]["provider_request_receipt"] == "NONE"
    assert handoff["ledger"]["active_reservation"] is False
    for value in (
        handoff["baseline"]["governance_main_sha"],
        handoff["baseline"]["rc_commit"],
        handoff["baseline"]["executable_tree_sha256"],
        handoff["baseline"]["dual_ci_provenance_sha256"],
        handoff["operation"]["id"],
        handoff["operation"]["execution_scope_sha256"],
        handoff["operation"]["prepared_scope_sha256"],
        handoff["operation"]["operation_manifest_sha256"],
        handoff["operation"]["preparation_template_sha256"],
        handoff["gate"]["final_runtime_bundle_sha256"],
        handoff["gate"]["loaded_runtime_scope_sha256"],
        handoff["authority"]["receipt_sha256"],
    ):
        assert value in markdown
    for item in handoff["gate"]["approvals"].values():
        assert item["record_sha256"] in markdown
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

    changed = sorted(
        set(git("diff", "--name-only", BASE_HEAD).splitlines())
        | set(git("ls-files", "--others", "--exclude-standard").splitlines())
    )
    allowed = (
        "apps/api/tests/test_vf_v0s_b9_",
        "docs/acceptance/v3-01/",
        "evidence/v3-01/vf-v0s-b9-",
    )
    assert all(path.startswith(allowed) for path in changed), changed
    assert not git("diff", "--name-only", BASE_HEAD, "--", "docs/acceptance/v3-01/prepared/").strip()
    assert subprocess.run(
        ["git", "diff", "--check", BASE_HEAD], cwd=REPO, capture_output=True
    ).returncode == 0
    tree = executable_tree_sha256(_git_object_map(REPO, "HEAD"))
    assert tree == handoff["baseline"]["executable_tree_sha256"]
    assert _git_object_map(REPO, "HEAD") == _git_object_map(REPO, handoff["baseline"]["governance_main_sha"])

    files = sorted(
        {
            handoff_json,
            handoff_md,
            REPO / "apps/api/tests/test_vf_v0s_b9_final_authority.py",
            REPO / handoff["gate"]["final_runtime_bundle_path"],
            *HERE.rglob("*"),
            *EVIDENCE.rglob("*"),
            *(
                REPO / f"docs/acceptance/v3-01/approvals/{item['approval_id']}.json"
                for item in handoff["gate"]["approvals"].values()
            ),
        }
    )
    files = [
        path
        for path in files
        if path.is_file() and path.suffix.lower() in {".json", ".md", ".py", ".txt"}
    ]
    patterns = [
        re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{16,}"),
        re.compile(
            r"(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*[\"']?[A-Za-z0-9._-]{20,}"
        ),
    ]
    json_files = 0
    links = 0
    pending = []
    planned = {
        EVIDENCE / "tests.json",
        EVIDENCE / "handoff-checksums.json",
        EVIDENCE / "SHA256SUMS.txt",
    }
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not any(pattern.search(text) for pattern in patterns), path
        if path.suffix == ".json":
            json.loads(text)
            json_files += 1
        if path.suffix == ".md":
            for _, target in re.findall(r"\[([^]\n]+)\]\(([^)\n]+)\)", text):
                if target.startswith(("https://", "http://", "#", "mailto:")):
                    continue
                resolved = (path.parent / unquote(target.split("#", 1)[0]).strip("<>")).resolve()
                assert resolved.is_relative_to(REPO)
                if not resolved.is_file() and not final and resolved in planned:
                    pending.append(resolved.relative_to(REPO).as_posix())
                else:
                    assert resolved.is_file(), (path, target)
                links += 1

    seals = []
    if final:
        for folder in (HERE, EVIDENCE):
            manifest_path = folder / "SHA256SUMS.txt"
            listed = set()
            for line in manifest_path.read_text(encoding="utf-8").splitlines():
                expected, name = re.split(r"\s+", line, maxsplit=1)
                name = name.lstrip("*")
                assert sha(folder / name) == expected
                listed.add(name)
            assert listed == {
                item.name for item in folder.iterdir() if item.is_file() and item.name != "SHA256SUMS.txt"
            }
            seals.append(
                {
                    "folder": folder.relative_to(REPO).as_posix(),
                    "entries": len(listed),
                    "manifest_sha256": sha(manifest_path),
                }
            )
        expected_handoff = {
            handoff_md.relative_to(REPO).as_posix(): sha(handoff_md),
            handoff_json.relative_to(REPO).as_posix(): sha(handoff_json),
        }
        assert json.loads((EVIDENCE / "handoff-checksums.json").read_text(encoding="utf-8"))[
            "hashes"
        ] == expected_handoff
        assert not pending

    return {
        "actual_cost_vnd": "0",
        "authority_status": "GRANTED_NOT_CONSUMED",
        "budget_reserved_vnd": "0",
        "bundle_mounted": False,
        "changed_files": changed,
        "credential_reads": 0,
        "executable_tree_changed": False,
        "executable_tree_sha256": tree,
        "gate_loader": generated["gate_loader"],
        "git_diff_check": "PASS",
        "handoff_md_json_semantic_parity": "PASS",
        "json_files_parsed": json_files,
        "kill_switch": "ENGAGED",
        "links_checked": links,
        "manifest_verification": seals,
        "pending_generated_links": sorted(set(pending)),
        "production_business_writes": 0,
        "provider_calls": 0,
        "scope_drift": "PASS",
        "secret_scan": "PASS",
        "status": "PASS",
        "task_id": "VF-V0S-B9",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    socket.create_connection = no_network
    socket.socket.connect = no_network
    print(json.dumps(validate(final=args.final), ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
