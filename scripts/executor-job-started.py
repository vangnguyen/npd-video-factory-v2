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

def allowed(environ, manifest):
    repo = "vangnguyen/npd-video-factory-v2"
    workflows = {"video-factory-executor-qualification.yml", "video-factory-provider-execution.yml"}
    return (
        environ.get("GITHUB_REPOSITORY") == repo
        and environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and environ.get("GITHUB_REF") == "refs/heads/main"
        and environ.get("GITHUB_WORKFLOW_REF") in {
            f"{repo}/.github/workflows/{name}@refs/heads/main" for name in workflows}
        and bool(re.fullmatch(r"[a-f0-9]{40}", environ.get("GITHUB_WORKFLOW_SHA", "")))
        and environ.get("GITHUB_WORKFLOW_SHA") in manifest.get("approved_workflow_commits", [])
    )

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
