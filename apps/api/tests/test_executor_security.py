from types import SimpleNamespace

from app import executor_qualification as q
from app import executor_security as security


def test_hostile_review_requires_all_denials(tmp_path, monkeypatch):
    host = q.Host(
        runner_id=6, runner_name="npd-vf-executor-ubuntu-02",
        execution_organization=q.EXECUTION_ORGANIZATION, runner_group=q.RUNNER_GROUP,
        execution_repository=q.REPOSITORY, execution_workflow_commit="a" * 40,
        workflow_allowlist=str(tmp_path / "allowlist"), labels=sorted(q.LABELS),
        distro="Ubuntu", source=str(tmp_path), source_commit="b" * 40,
        evidence_root=str(tmp_path), lock_path=str(tmp_path / "lock"),
        binding=str(tmp_path / "binding"), binding_sha256="c" * 64,
        migration_head="0015_v3_01_dispatch", secret_binding=str(q.PROVIDER_SECRET_BINDING),
        kill_switch=str(tmp_path / "kill"), executor_executable_tree_sha256="d" * 64,
    )
    manifest = {"version": 1, "mode": "ZERO_CALL_QUALIFICATION",
        "approved_qualification_workflows": [{"workflow_ref": q.QUALIFICATION_WORKFLOW_REF,
            "workflow_sha": host.execution_workflow_commit}], "approved_execution_workflows": []}
    monkeypatch.setattr(q, "admission_manifest", lambda *a: manifest)
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    (tmp_path / "kill").write_bytes(b"ENGAGED\n")
    tmp_path.chmod(0o700)

    def allowed(env, value):
        return (env == {"GITHUB_REPOSITORY": q.REPOSITORY,
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
            "GITHUB_WORKFLOW_SHA": "a" * 40, "GITHUB_WORKFLOW_REF": q.QUALIFICATION_WORKFLOW_REF}
            and value == manifest)

    review_root = tmp_path / "review"
    review_root.mkdir(mode=0o700)
    result = security.review(host, review_root, hook=SimpleNamespace(allowed=allowed))
    assert result["report"]["status"] == "RUNNER_SECURITY_PASS"
    assert result["report"]["hostile_job_tests"] == {
        name: "PASS" for name in security.HOSTILE_JOB_TESTS}
    assert result["report"]["provider_execution_allowlist"] == "EMPTY"


def test_security_case_set_matches_owner_gate():
    assert set(security.HOSTILE_JOB_TESTS) == {
        "unapproved_repository", "unapproved_workflow", "unapproved_ref",
        "modified_workflow", "pr_triggered_workflow", "command_injection",
        "environment_injection", "stale_source_commit",
        "incorrect_executable_tree_sha", "cross_runner_receipt",
        "concurrent_execution_attempt",
    }
