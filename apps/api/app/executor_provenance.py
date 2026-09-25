"""Versioned executor tree binding without changing historical RC hashing."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import subprocess

from .provider_ci_provenance import EXECUTABLE_TREE_PATHS, executable_tree_sha256


def executor_tree_sha256(canonical_sha: str, workflow_object: str) -> str:
    if re.fullmatch(r"[a-f0-9]{64}", canonical_sha) is None or re.fullmatch(r"[a-f0-9]{40}", workflow_object) is None:
        raise ValueError("EXECUTOR_TREE_OBJECT_INVALID")
    payload = {"version": 1, "canonical_executable_tree_sha256": canonical_sha,
               "github_workflows_tree_object": workflow_object}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def collect_executor_tree(source: Path, commit: str) -> dict:
    if re.fullmatch(r"[a-f0-9]{40}", commit) is None:
        raise ValueError("EXECUTOR_COMMIT_INVALID")
    def object_id(path):
        result = subprocess.run(["git", "-C", str(source), "rev-parse", commit + ":" + path],
                                check=True, capture_output=True, text=True, timeout=20)
        return result.stdout.strip()
    objects = {path: object_id(path) for path in EXECUTABLE_TREE_PATHS}
    canonical = executable_tree_sha256(objects)
    workflow = object_id(".github/workflows")
    return {"version": 1, "commit": commit, "canonical_executable_tree_sha256": canonical,
            "github_workflows_tree_object": workflow,
            "executor_executable_tree_sha256": executor_tree_sha256(canonical, workflow)}
