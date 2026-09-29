"""Independent promotion of sealed zero-call qualification evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from . import executor_qualification as q
from .executor_security import HOSTILE_JOB_TESTS

PROMOTION_CONFIG = Path("/etc/npd-video-factory/qualification-promotion.json")
CONFIG_FIELDS = {
    "probe_receipt", "probe_receipt_sha256", "probe_manifest",
    "probe_manifest_sha256", "security_review", "security_review_sha256",
    "promotion_root",
}


def _trusted_json(path: Path, digest: str) -> dict:
    q.private_path(path, root_owned=True)
    raw = path.read_bytes()
    q.secret_scan(raw)
    q.require(hashlib.sha256(raw).hexdigest() == digest, "PROMOTION_ARTIFACT_HASH_MISMATCH")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        raise q.Blocked("PROMOTION_ARTIFACT_INVALID") from None
    q.require(type(value) is dict, "PROMOTION_ARTIFACT_INVALID")
    return value


def load_config(path: Path = PROMOTION_CONFIG) -> dict:
    q.private_path(path, root_owned=True)
    raw = path.read_bytes()
    q.secret_scan(raw)
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        raise q.Blocked("PROMOTION_CONFIG_INVALID") from None
    q.require(type(value) is dict and set(value) == CONFIG_FIELDS,
              "PROMOTION_CONFIG_INVALID")
    return value


def promote(host: q.Host, config: dict) -> dict:
    q.require(type(config) is dict and set(config) == CONFIG_FIELDS,
              "PROMOTION_CONFIG_INVALID")
    probe = _trusted_json(Path(config["probe_receipt"]), config["probe_receipt_sha256"])
    manifest = _trusted_json(Path(config["probe_manifest"]), config["probe_manifest_sha256"])
    security = _trusted_json(Path(config["security_review"]), config["security_review_sha256"])
    q.require_runner_identity(probe, host, "QUALIFICATION_PROBE_IDENTITY_MISMATCH")
    q.require_runner_identity(security, host, "QUALIFICATION_SECURITY_IDENTITY_MISMATCH")
    q.require(probe.get("verdict") == "CAPABILITY_PROBES_PASS"
              and probe.get("execution_plane_qualified") is False,
              "QUALIFICATION_PROBES_FAILED")
    q.require(all(probe.get("gates", {}).get(gate, {}).get("status") == "PASS" for gate in q.GATES)
              and all(probe.get(name) == value for name, value in q.ZERO.items())
              and probe["gates"]["E10"].get("KILL_SWITCH") == "ENGAGED"
              and probe["gates"]["E10"].get("ledger_unchanged") is True,
              "QUALIFICATION_PROBES_FAILED")
    current_secret = q.secret_presence(host)
    q.require(probe["gates"]["E7"].get("result")
              == "PASS_SECRET_SOURCE_PRESENT_NOT_RESOLVED"
              and probe["gates"]["E7"].get("binding_sha256")
              == current_secret["binding_sha256"]
              and probe["gates"]["E7"].get("PROVIDER_CREDENTIAL_READS") == 0
              and current_secret.get("PROVIDER_CREDENTIAL_READS") == 0,
              "QUALIFICATION_SECRET_BINDING_FAILED")
    secret_binding_sha256 = current_secret["binding_sha256"]
    q.require(manifest.get("qualification.json") == config["probe_receipt_sha256"],
              "QUALIFICATION_MANIFEST_MISMATCH")
    q.require(security.get("status") == "RUNNER_SECURITY_PASS"
              and security.get("quarantine") == "CLEARED_BY_VALIDATED_POLICY"
              and security.get("kill_switch") == "ENGAGED"
              and security.get("provider_execution_allowlist") == "EMPTY"
              and all(security.get(name) == value for name, value in q.ZERO.items())
              and all(security.get("hostile_job_tests", {}).get(name) == "PASS"
                      for name in HOSTILE_JOB_TESTS), "QUALIFICATION_SECURITY_REVIEW_FAILED")
    q.require(security.get("execution_workflow_commit") == host.execution_workflow_commit,
              "EXECUTION_WORKFLOW_PROVENANCE_MISMATCH")
    q.admission_manifest(host, "qualification")
    kill = Path(host.kill_switch)
    q.private_path(kill, root_owned=True)
    q.require(kill.read_bytes() == b"ENGAGED\n", "KILL_SWITCH_NOT_ENGAGED")
    root = Path(config["promotion_root"])
    q.private_path(root, directory=True, root_owned=True)
    evidence_manifest = {
        "version": 1,
        "task": "VF-SECRET-01",
        "runner_identity": q.expected_runner_identity(host),
        "execution_workflow_commit": host.execution_workflow_commit,
        "custody_binding_sha256": host.binding_sha256,
        "secret_binding_sha256": secret_binding_sha256,
        "artifacts": {
            "probe_receipt": config["probe_receipt_sha256"],
            "probe_manifest": config["probe_manifest_sha256"],
            "security_review": config["security_review_sha256"],
        },
        "kill_switch": "ENGAGED",
        **q.ZERO,
    }
    evidence_manifest_sha256 = q.persist(root, "evidence-manifest.json", evidence_manifest)
    receipt = {
        "status": "SELF_HOSTED_EXECUTION_PLANE_QUALIFIED",
        "task": "VF-SECRET-01",
        "runner_identity": q.expected_runner_identity(host),
        "execution_workflow_commit": host.execution_workflow_commit,
        "custody_binding_sha256": host.binding_sha256,
        "secret_binding_sha256": secret_binding_sha256,
        "gates": {gate: "PASS" for gate in q.GATES},
        "kill_switch": "ENGAGED",
        "probe_receipt": config["probe_receipt"],
        "probe_receipt_sha256": config["probe_receipt_sha256"],
        "probe_manifest": config["probe_manifest"],
        "probe_manifest_sha256": config["probe_manifest_sha256"],
        "security_review": config["security_review"],
        "security_review_sha256": config["security_review_sha256"],
        "evidence_manifest": str(root / "evidence-manifest.json"),
        "evidence_manifest_sha256": evidence_manifest_sha256,
        "authority_granted": False,
        "o2": "NO",
        **q.ZERO,
    }
    promotion_sha256 = q.persist(root, "qualification-promotion.json", receipt)
    return {"receipt": receipt, "promotion_sha256": promotion_sha256,
            "evidence_manifest_sha256": evidence_manifest_sha256}


def main() -> int:
    argparse.ArgumentParser(description="Promote sealed zero-call executor qualification").parse_args()
    try:
        host = q.Host.load()
        config = load_config()
        result = promote(host, config)
        print(json.dumps({"status": result["receipt"]["status"],
            "promotion_sha256": result["promotion_sha256"],
            "evidence_manifest_sha256": result["evidence_manifest_sha256"], **q.ZERO}, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"status": "BLOCKED", "code": "QUALIFICATION_PROMOTION_FAILED", **q.ZERO}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
