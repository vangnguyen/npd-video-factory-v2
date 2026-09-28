#!/usr/bin/env python3
"""Root-owned host admission; empty allowlist rejects ALL jobs at provisioning.

Defense in depth, not a substitute for GitHub runner-group restrictions.
"""
import json
import os
from pathlib import Path
import re
import stat
import sys

REPOSITORY = "npd-ai/npd-video-factory-executor"
QUALIFICATION_WORKFLOW = (
    REPOSITORY
    + "/.github/workflows/video-factory-executor-qualification.yml@refs/heads/main"
)
EXECUTION_WORKFLOW = (
    REPOSITORY
    + "/.github/workflows/video-factory-provider-execution.yml@refs/heads/main"
)
MANIFEST_FIELDS = {
    "version", "mode", "approved_qualification_workflows",
    "approved_execution_workflows",
}


def _approved(entries, workflow_ref, workflow_sha):
    if not isinstance(entries, list):
        return False
    expected = {"workflow_ref": workflow_ref, "workflow_sha": workflow_sha}
    return any(type(entry) is dict and entry == expected for entry in entries)

def allowed(environ, manifest):
    if type(manifest) is not dict or set(manifest) != MANIFEST_FIELDS or manifest.get("version") != 1:
        return False
    workflow_ref = environ.get("GITHUB_WORKFLOW_REF")
    workflow_sha = environ.get("GITHUB_WORKFLOW_SHA", "")
    common = (
        environ.get("GITHUB_REPOSITORY") == REPOSITORY
        and environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and environ.get("GITHUB_REF") == "refs/heads/main"
        and bool(re.fullmatch(r"[a-f0-9]{40}", workflow_sha))
        and "VF_REQUEST_JSON" not in environ
        and not any(name.startswith("INPUT_") for name in environ)
    )
    if not common:
        return False
    if workflow_ref == QUALIFICATION_WORKFLOW:
        return (
            manifest.get("mode") == "ZERO_CALL_QUALIFICATION"
            and manifest.get("approved_execution_workflows") == []
            and _approved(manifest.get("approved_qualification_workflows"), workflow_ref, workflow_sha)
        )
    if workflow_ref == EXECUTION_WORKFLOW:
        return (
            manifest.get("mode") == "GOVERNED_EXECUTION"
            and _approved(manifest.get("approved_execution_workflows"), workflow_ref, workflow_sha)
        )
    return False

def main():
    try:
        path = Path("/etc/npd-video-factory/workflow-allowlist.json")
        for item in (path, path.parent):
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
                return 1
        return 0 if allowed(os.environ, json.loads(path.read_bytes())) else 1
    except Exception:
        return 1

if __name__ == "__main__":
    result = main()
    if result:
        print("BLOCKED_PRE_CALL: runner admission denied")
    sys.exit(result)
