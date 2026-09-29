"""Host-only, zero-call execution-plane probes. Never a dispatch engine.

Configuration is installed by the host administrator after source review. No
workflow input can choose a command, Python module, endpoint or configuration.
An offline/mock test of this module is never a host qualification receipt.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone

REPOSITORY = "npd-ai/npd-video-factory-executor"
EXECUTION_ORGANIZATION = "npd-ai"
RUNNER_GROUP = "vf-provider-execution"
QUALIFICATION_WORKFLOW_REF = (
    REPOSITORY
    + "/.github/workflows/video-factory-executor-qualification.yml@refs/heads/main"
)
EXECUTION_WORKFLOW_REF = (
    REPOSITORY
    + "/.github/workflows/video-factory-provider-execution.yml@refs/heads/main"
)
LABELS = frozenset({"self-hosted", "linux", "x64", "npd-video-factory", "provider-execution"})
CONFIG = Path("/etc/npd-video-factory/executor.json")
PROVIDER_SECRET_BINDING = Path("/etc/npd-video-factory/provider-secret-binding.json")
CANONICAL_CREDENTIAL_ALIAS = "secret://openai/codex-video"
SYSTEMD_CREDENTIAL_ID = "openai-codex-video"
SYSTEMD_ENCRYPTED_SOURCE = Path("/etc/credstore.encrypted/openai-codex-video")
SYSTEMD_HOST_KEY = Path("/var/lib/systemd/credential.secret")
SYSTEMD_BACKEND_RECEIPT = Path(
    "/etc/npd-video-factory/systemd-credential-backend-qualification.json"
)
SECRET_BINDING_FIELDS = {
    "version", "credential_alias", "provider", "capability_scope",
    "source_type", "source_locator", "owner", "expected_owner_uid",
    "expected_owner_gid", "expected_mode", "state", "created_for",
    "authority_granted", "secret_source_present", "systemd_credential_id",
    "encryption_key_type", "provider_runtime_reads",
    "backend_qualification_receipt_sha256",
}
SYSTEMD_BACKEND_RECEIPT_FIELDS = {
    "version", "task", "status", "systemd_version", "host_key_present",
    "host_key_owner", "host_key_mode", "credential_mechanism",
    "systemd_credential_id", "encryption_key_type", "synthetic_encrypt",
    "name_binding", "controlled_service_receive", "access_isolation",
    "cleanup", "actual_provider_credential_decrypted",
    "provider_runtime_reads", "provider_calls",
}
ADMISSION_MANIFEST_FIELDS = {
    "version", "mode", "approved_qualification_workflows",
    "approved_execution_workflows",
}
EXECUTION_PROVENANCE_FIELDS = {
    "version", "source", "execution_organization", "execution_repository",
    "runner_group", "repository_access", "selected_repositories",
    "selected_workflows", "public_repositories_allowed",
    "execution_workflow_commit",
}
GATES = tuple(f"E{i}" for i in range(1, 11))
RUNNER_IDENTITY_FIELDS = (
    "runner_id", "runner_name", "execution_organization", "runner_group",
    "execution_repository", "source_commit", "executor_executable_tree_sha256",
)
ZERO = {"provider_calls": 0, "credential_reads": 0, "budget_reserved_vnd": "0",
        "operation_consumption": 0, "production_business_writes": 0, "actual_cost_vnd": "0"}


class Blocked(RuntimeError):
    """Only fixed, value-free codes may cross the log boundary."""


class ProbeBlocked(Blocked):
    """A blocked probe with an explicitly non-secret evidence payload."""

    def __init__(self, code: str, evidence: dict | None = None) -> None:
        super().__init__(code)
        self.evidence = evidence or {}


def require(condition: bool, code: str) -> None:
    if not condition:
        raise Blocked(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def secret_scan(raw: bytes) -> None:
    require(not re.search(rb"(?i)(sk-[a-z0-9_-]{8,}|bearer\s+\S+|-----BEGIN .*PRIVATE KEY|OPENAI_API_KEY\s*[:=])", raw),
            "SECRET_SCAN_FAILED")


def private_path(path: Path, *, directory: bool = False, root_owned: bool = False) -> None:
    require(path.is_absolute(), "PATH_NOT_ABSOLUTE")
    for part in (path, *path.parents):
        require(not part.is_symlink(), "SYMLINK_BLOCKED")
        if root_owned:
            ancestor = part.stat()
            require(ancestor.st_uid == 0 and not stat.S_IMODE(ancestor.st_mode) & 0o022,
                    "TRUSTED_PATH_ANCESTOR_WRITABLE")
    info = path.stat()
    require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode), "PATH_TYPE_INVALID")
    require(info.st_uid == (0 if root_owned else os.getuid()), "PATH_OWNER_INVALID")
    require(not stat.S_IMODE(info.st_mode) & (0o022 if root_owned else 0o077), "PATH_PERMISSIONS_INVALID")


@dataclass(frozen=True)
class Host:
    runner_id: int
    runner_name: str
    execution_organization: str
    runner_group: str
    execution_repository: str
    execution_workflow_commit: str
    workflow_allowlist: str
    labels: list[str]
    distro: str
    source: str
    source_commit: str
    evidence_root: str
    lock_path: str
    binding: str
    binding_sha256: str
    migration_head: str
    secret_binding: str
    kill_switch: str
    executor_executable_tree_sha256: str = ""
    execution_provenance: str = "/etc/npd-video-factory/execution-workflow-provenance.json"

    @classmethod
    def load(cls, path: Path = CONFIG) -> "Host":
        private_path(path, root_owned=True)
        private_path(path.parent, directory=True, root_owned=True)
        raw = path.read_bytes()
        secret_scan(raw)
        try:
            value = json.loads(raw)
            require(isinstance(value, dict), "HOST_CONFIG_SCHEMA_INVALID")
            host = cls(**value)
        except Blocked:
            raise
        except (TypeError, ValueError):
            raise Blocked("HOST_CONFIG_SCHEMA_INVALID") from None
        expected_runner_identity(host)
        require(isinstance(host.execution_workflow_commit, str)
                and re.fullmatch(r"[a-f0-9]{40}", host.execution_workflow_commit) is not None,
                "EXECUTION_WORKFLOW_COMMIT_INVALID")
        require(isinstance(host.labels, list) and all(isinstance(label, str) for label in host.labels)
                and LABELS <= {label.lower() for label in host.labels}, "RUNNER_LABELS_INVALID")
        require(bool(re.fullmatch(r"[a-f0-9]{64}", host.binding_sha256)), "BINDING_HASH_INVALID")
        require(isinstance(host.execution_provenance, str)
                and Path(host.execution_provenance).is_absolute(),
                "EXECUTION_PROVENANCE_PATH_INVALID")
        require(host.secret_binding == str(PROVIDER_SECRET_BINDING),
                "SECRET_BINDING_PATH_INVALID")
        return host


def expected_runner_identity(host: Host) -> dict[str, int | str]:
    """Canonical identity sourced only from the root-owned host binding."""
    runner_id = getattr(host, "runner_id", None)
    runner_name = getattr(host, "runner_name", None)
    organization = getattr(host, "execution_organization", None)
    runner_group = getattr(host, "runner_group", None)
    repository = getattr(host, "execution_repository", None)
    source_commit = getattr(host, "source_commit", None)
    executable_tree = getattr(host, "executor_executable_tree_sha256", None)
    require(type(runner_id) is int and runner_id > 0, "RUNNER_ID_INVALID")
    require(isinstance(runner_name, str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", runner_name) is not None,
            "RUNNER_NAME_INVALID")
    require(organization == EXECUTION_ORGANIZATION, "EXECUTION_ORGANIZATION_INVALID")
    require(runner_group == RUNNER_GROUP, "RUNNER_GROUP_INVALID")
    require(repository == REPOSITORY and repository.split("/", 1)[0] == organization,
            "REPOSITORY_SCOPE_INVALID")
    require(isinstance(source_commit, str)
            and re.fullmatch(r"[a-f0-9]{40}", source_commit) is not None,
            "SOURCE_COMMIT_INVALID")
    require(isinstance(executable_tree, str)
            and re.fullmatch(r"[a-f0-9]{64}", executable_tree) is not None,
            "EXECUTOR_TREE_HASH_INVALID")
    return {
        "runner_id": runner_id,
        "runner_name": runner_name,
        "execution_organization": organization,
        "runner_group": runner_group,
        "execution_repository": repository,
        "source_commit": source_commit,
        "executor_executable_tree_sha256": executable_tree,
    }


def require_runner_identity(document: dict, host: Host, code: str) -> None:
    """Reject missing, partial, extended, or cross-runner identity evidence."""
    expected = expected_runner_identity(host)
    actual = document.get("runner_identity") if isinstance(document, dict) else None
    require(isinstance(actual, dict)
            and not set(RUNNER_IDENTITY_FIELDS).intersection(document)
            and set(actual) == set(expected)
            and all(type(actual[field]) is type(value) and actual[field] == value
                    for field, value in expected.items()), code)


@contextmanager
def plane_lock(path: Path):
    import fcntl  # Linux only; Windows tests do not pretend to qualify flock.
    private_path(path.parent, directory=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        require(os.fstat(descriptor).st_uid == os.getuid(), "LOCK_OWNER_INVALID")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Blocked("CONCURRENT_EXECUTION_BLOCKED") from None
        yield
    finally:
        # Never unlink the inode: another process might already hold it open.
        os.close(descriptor)


def persist(directory: Path, name: str, payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    secret_scan(raw)
    private_path(directory, directory=True)
    require(bool(re.fullmatch(r"[a-z0-9-]+\.json", name)), "EVIDENCE_NAME_INVALID")
    path = directory / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    # Fresh isolated interpreter: no in-process cache counts as persistence.
    result = subprocess.run([sys.executable, "-I", "-c",
        "import hashlib,pathlib,sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())",
        str(path)], capture_output=True, timeout=20, check=True)
    require(result.stdout.decode().strip() == sha(raw), "EVIDENCE_PROCESS_BOUNDARY_FAILED")
    return sha(raw)


def admission_manifest(host: Host, workflow_kind: str) -> dict:
    path = Path(host.workflow_allowlist)
    private_path(path, root_owned=True)
    raw = path.read_bytes()
    secret_scan(raw)
    try:
        manifest = json.loads(raw)
    except (TypeError, ValueError):
        raise Blocked("ADMISSION_MANIFEST_INVALID") from None
    require(type(manifest) is dict and set(manifest) == ADMISSION_MANIFEST_FIELDS
            and manifest.get("version") == 1, "ADMISSION_MANIFEST_INVALID")
    expected = {
        "workflow_ref": (
            QUALIFICATION_WORKFLOW_REF if workflow_kind == "qualification"
            else EXECUTION_WORKFLOW_REF
        ),
        "workflow_sha": host.execution_workflow_commit,
    }
    if workflow_kind == "qualification":
        require(manifest.get("mode") == "ZERO_CALL_QUALIFICATION"
                and manifest.get("approved_qualification_workflows") == [expected]
                and manifest.get("approved_execution_workflows") == [],
                "QUALIFICATION_ADMISSION_NOT_EXACT")
    elif workflow_kind == "execution":
        require(manifest.get("mode") == "GOVERNED_EXECUTION"
                and expected in manifest.get("approved_execution_workflows", []),
                "EXECUTION_ADMISSION_NOT_EXACT")
    else:
        raise Blocked("WORKFLOW_KIND_INVALID")
    return manifest


def runtime(host: Host, workflow_kind: str = "qualification") -> dict:
    require(sys.platform == "linux" and "microsoft" in platform.release().lower(), "WSL_RUNTIME_UNAVAILABLE")
    require(os.environ.get("WSL_DISTRO_NAME") == host.distro, "WSL_DISTRO_MISMATCH")
    require(sys.version_info >= (3, 12), "PYTHON_VERSION_INVALID")
    require(os.environ.get("RUNNER_NAME") == host.runner_name, "RUNNER_NAME_MISMATCH")
    require(os.environ.get("GITHUB_REPOSITORY_OWNER") == host.execution_organization,
            "EXECUTION_ORGANIZATION_MISMATCH")
    require(os.environ.get("GITHUB_REPOSITORY") == host.execution_repository,
            "REPOSITORY_SCOPE_INVALID")
    require(os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch", "UNTRUSTED_EVENT")
    require(os.environ.get("GITHUB_REF") == "refs/heads/main", "UNTRUSTED_REF")
    expected_workflow = (
        QUALIFICATION_WORKFLOW_REF if workflow_kind == "qualification" else EXECUTION_WORKFLOW_REF
    )
    require(os.environ.get("GITHUB_WORKFLOW_REF") == expected_workflow, "UNTRUSTED_WORKFLOW")
    require(os.environ.get("GITHUB_WORKFLOW_SHA") == host.execution_workflow_commit,
            "EXECUTION_WORKFLOW_COMMIT_MISMATCH")
    admission_manifest(host, workflow_kind)
    require(LABELS <= {label.lower() for label in host.labels}, "RUNNER_LABELS_INVALID")
    source = Path(host.source)
    private_path(source, directory=True, root_owned=True)
    private_path(Path(__file__).resolve(), root_owned=True)
    require(Path(__file__).resolve() == source / "apps/api/app/executor_qualification.py", "RUNTIME_SOURCE_MISMATCH")
    def git(*args):
        return subprocess.run(["git", "-c", f"safe.directory={source}",
                               "-C", str(source), *args], check=True,
                              capture_output=True, text=True, timeout=30).stdout.strip()
    require(git("rev-parse", "HEAD") == host.source_commit, "RUNTIME_COMMIT_MISMATCH")
    require(not git("status", "--porcelain"), "RUNTIME_SOURCE_DIRTY")
    from .executor_provenance import collect_executor_tree
    tree = collect_executor_tree(source, host.source_commit)
    require(tree["executor_executable_tree_sha256"] == host.executor_executable_tree_sha256,
            "EXECUTOR_TREE_HASH_MISMATCH")
    with tempfile.TemporaryDirectory(prefix="vf-socket-") as directory:
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(Path(directory) / "probe.sock"))
            server.listen(1)
            with socket.socket(socket.AF_UNIX) as client:
                client.settimeout(5)
                client.connect(str(Path(directory) / "probe.sock"))
                connection, _ = server.accept()
                connection.close()
    return {"WSL_RUNTIME": "VERIFIED", "python": platform.python_version(), "distro": host.distro,
            "executor_executable_tree_sha256": tree["executor_executable_tree_sha256"],
            "execution_workflow_commit": host.execution_workflow_commit,
            "workflow_ref": expected_workflow}


async def custody(host: Host) -> dict:
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from .provider_custody import (
        custody_url, load_custody_binding, read_custody, verify_socket_custody,
    )
    binding = load_custody_binding(Path(host.binding), host.binding_sha256)
    verify_socket_custody(binding)
    engine = create_async_engine(custody_url(binding), echo=False,
        connect_args={"password": "", "server_settings": {"default_transaction_read_only": "on"}})
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        result = await read_custody(factory, binding)
        require(result["migration_head"] == host.migration_head, "MIGRATION_HEAD_MISMATCH")
        return result
    finally:
        await engine.dispose()


def github(host: Host) -> dict:
    # The execution repository is private. Qualification receives no GitHub
    # credential, so operator-observed topology is sealed into this root-owned
    # artifact rather than weakening isolation or reusing runner registration.
    path = Path(host.execution_provenance)
    private_path(path, root_owned=True)
    raw = path.read_bytes()
    secret_scan(raw)
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        raise Blocked("GITHUB_PROVENANCE_INVALID") from None
    require(type(value) is dict and set(value) == EXECUTION_PROVENANCE_FIELDS
            and value.get("version") == 1
            and value.get("source") == "GITHUB_OPERATOR_VERIFIED"
            and value.get("execution_organization") == host.execution_organization
            and value.get("execution_repository") == host.execution_repository
            and value.get("runner_group") == host.runner_group
            and value.get("repository_access") == "SELECTED_REPOSITORIES"
            and value.get("selected_repositories") == [host.execution_repository]
            and value.get("selected_workflows") == [
                QUALIFICATION_WORKFLOW_REF, EXECUTION_WORKFLOW_REF,
            ]
            and value.get("public_repositories_allowed") is False,
            "GITHUB_PROVENANCE_INVALID")
    observed = value.get("execution_workflow_commit")
    require(observed == host.execution_workflow_commit,
            "EXECUTION_WORKFLOW_PROVENANCE_MISMATCH")
    return {"GITHUB_ACCESS": "VERIFIED_BY_ROOT_OWNED_OPERATOR_EVIDENCE",
            "observed_main": observed,
            "execution_workflow_commit": host.execution_workflow_commit,
            "operator_provenance_sha256": sha(raw)}


def provider_network() -> dict:
    # TLS handshake only. No HTTP request, authorization header or model API.
    with socket.create_connection(("api.openai.com", 443), timeout=10) as tcp:
        with ssl.create_default_context().wrap_socket(tcp, server_hostname="api.openai.com") as tls:
            require(bool(tls.getpeercert()), "PROVIDER_TLS_UNVERIFIED")
    return {"PROVIDER_NETWORK": "VERIFIED", "probe": "TLS_HANDSHAKE_ONLY", "http_requests": 0}


def load_secret_binding(host: Host) -> tuple[dict, bytes]:
    """Load strict non-secret metadata; never touch provider credential bytes."""
    path = Path(host.secret_binding)
    private_path(path, root_owned=True)
    raw = path.read_bytes()
    secret_scan(raw)
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        raise Blocked("SECRET_BINDING_SCHEMA_INVALID") from None
    require(type(value) is dict and set(value) == SECRET_BINDING_FIELDS,
            "SECRET_BINDING_SCHEMA_INVALID")
    require(value.get("version") == 1
            and value.get("credential_alias") == CANONICAL_CREDENTIAL_ALIAS
            and value.get("provider") == "openai"
            and value.get("capability_scope") == ["asr"]
            and value.get("owner") == "root"
            and type(value.get("expected_owner_uid")) is int
            and value.get("expected_owner_uid") == 0
            and type(value.get("expected_owner_gid")) is int
            and value.get("expected_owner_gid") == 0
            and value.get("expected_mode") == "0400"
            and value.get("authority_granted") is False
            and value.get("provider_runtime_reads") == 0,
            "SECRET_BINDING_POLICY_INVALID")
    state = value.get("state")
    if state == "UNBOUND_APPROVED_SLOT":
        require(value.get("source_type") == "UNBOUND"
                and value.get("source_locator") is None
                and value.get("secret_source_present") is False
                and value.get("systemd_credential_id") is None
                and value.get("encryption_key_type") is None
                and value.get("backend_qualification_receipt_sha256") is None
                and value.get("created_for") == "VF-EXECUTOR-05C",
                "SECRET_BINDING_UNBOUND_STATE_INVALID")
    elif state == "BOUND_ENCRYPTED_SOURCE_PRESENT":
        locator = value.get("source_locator")
        require(value.get("source_type") == "SYSTEMD_ENCRYPTED_CREDENTIAL"
                and locator == str(SYSTEMD_ENCRYPTED_SOURCE)
                and Path(locator).is_absolute() and ".." not in Path(locator).parts
                and value.get("systemd_credential_id") == SYSTEMD_CREDENTIAL_ID
                and value.get("encryption_key_type") == "HOST"
                and value.get("secret_source_present") is True
                and value.get("created_for") == "VF-SECRET-01"
                and isinstance(value.get("backend_qualification_receipt_sha256"), str)
                and re.fullmatch(r"[a-f0-9]{64}",
                                 value["backend_qualification_receipt_sha256"]) is not None,
                "SECRET_BINDING_BOUND_STATE_INVALID")
    else:
        raise Blocked("SECRET_BINDING_STATE_INVALID")
    return value, raw


def load_systemd_backend_receipt(expected_sha256: str) -> dict:
    """Validate sealed synthetic backend evidence without touching provider bytes."""
    private_path(SYSTEMD_BACKEND_RECEIPT, root_owned=True)
    raw = SYSTEMD_BACKEND_RECEIPT.read_bytes()
    secret_scan(raw)
    require(sha(raw) == expected_sha256, "SYSTEMD_BACKEND_RECEIPT_HASH_MISMATCH")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        raise Blocked("SYSTEMD_BACKEND_RECEIPT_INVALID") from None
    require(type(value) is dict and set(value) == SYSTEMD_BACKEND_RECEIPT_FIELDS,
            "SYSTEMD_BACKEND_RECEIPT_INVALID")
    require(value == {
        "version": 1,
        "task": "VF-SECRET-01",
        "status": "PASS",
        "systemd_version": "255 (255.4-1ubuntu8.17)",
        "host_key_present": True,
        "host_key_owner": "root:root",
        "host_key_mode": "0400",
        "credential_mechanism": "LoadCredentialEncrypted",
        "systemd_credential_id": SYSTEMD_CREDENTIAL_ID,
        "encryption_key_type": "HOST",
        "synthetic_encrypt": "PASS",
        "name_binding": "PASS",
        "controlled_service_receive": "PASS",
        "access_isolation": "PASS",
        "cleanup": "PASS",
        "actual_provider_credential_decrypted": False,
        "provider_runtime_reads": 0,
        "provider_calls": 0,
    }, "SYSTEMD_BACKEND_RECEIPT_INVALID")
    return value


def secret_presence(host: Host) -> dict:
    binding, raw = load_secret_binding(host)
    common = {
        "SECRET_BINDING_METADATA_PRESENT": True,
        "credential_alias": CANONICAL_CREDENTIAL_ALIAS,
        "binding_sha256": sha(raw),
        "PROVIDER_CREDENTIAL_READS": 0,
        "plaintext_read": False,
    }
    if binding["state"] == "UNBOUND_APPROVED_SLOT":
        raise ProbeBlocked("BLOCKED_SECRET_SOURCE_NOT_INSTALLED", {
            **common,
            "SECRET_BINDING_STATE": "UNBOUND_APPROVED_SLOT",
            "SECRET_SOURCE_PRESENT": False,
        })

    # Presence verification is metadata-only: lstat/stat/ownership/mode/size.
    # The credential bytes are never opened by qualification.
    source = Path(binding["source_locator"])
    private_path(source, root_owned=True)
    info = source.stat()
    require(info.st_uid == binding["expected_owner_uid"]
            and info.st_gid == binding["expected_owner_gid"]
            and stat.S_IMODE(info.st_mode) == int(binding["expected_mode"], 8),
            "SECRET_SOURCE_POLICY_INVALID")
    require(info.st_size > 0, "SECRET_SOURCE_EMPTY_OR_PLACEHOLDER")
    private_path(SYSTEMD_HOST_KEY, root_owned=True)
    key_info = SYSTEMD_HOST_KEY.stat()
    require(key_info.st_uid == 0 and key_info.st_gid == 0
            and stat.S_IMODE(key_info.st_mode) == 0o400
            and key_info.st_size > 0,
            "SYSTEMD_HOST_KEY_CUSTODY_INVALID")
    load_systemd_backend_receipt(binding["backend_qualification_receipt_sha256"])
    return {
        **common,
        "result": "PASS_SECRET_SOURCE_PRESENT_NOT_RESOLVED",
        "SECRET_BINDING_STATE": "BOUND_ENCRYPTED_SOURCE_PRESENT",
        "SECRET_SOURCE_PRESENT": True,
        "source_type": binding["source_type"],
        "systemd_credential_id": SYSTEMD_CREDENTIAL_ID,
        "encryption_key_type": "HOST",
        "host_key_custody": "PASS",
        "synthetic_backend_test": "PASS",
        "future_privileged_resolver_reachable": True,
    }


def fixture_mount(root: Path) -> dict:
    from .provider_gate_loader import load_verified_provider_gate_bundle
    # Runtime bundle mounts are private staged files, not privileged OS mounts.
    # This fixture cannot contain an Owner approval or an active operation.
    with tempfile.TemporaryDirectory(prefix="fixture-mount-", dir=root) as directory:
        mount = Path(directory)
        raw = (Path(__file__).parent / "data/executor/expired-loader-fixture.json").read_bytes()
        require(sha(raw) == "ed8fd22961d171cfb63ab8a273ec7824eef6369bf25af9eff7c8661dba740c0f",
                "FIXTURE_HASH_MISMATCH")
        fixture = mount / "bundle.json"
        fixture.write_bytes(raw)
        scope = load_verified_provider_gate_bundle(fixture, expected_bundle_sha256=sha(raw),
            expected_rc_commit="f" * 40, expected_rc_tag="vf-v3-01-rc999999")
        require(scope.expires_at_utc < datetime(2026, 9, 1, tzinfo=timezone.utc)
                and not scope.active(datetime.now(timezone.utc)), "FIXTURE_MUST_BE_EXPIRED")
    require(not mount.exists(), "BUNDLE_CLEANUP_FAILED")
    return {"BUNDLE_MOUNT_CAPABILITY": "VERIFIED", "loader_probe": "VALID_EXPIRED_SYNTHETIC_FIXTURE_LOADED",
            "active_bundle_mounted": False, "cleanup": "VERIFIED"}


async def check_only(host: Host, root: Path) -> dict:
    from .provider_single_dispatch import SingleDispatchPaths, validate_single_dispatch
    from .provider_safety import ProviderSafetyPolicy
    kill = Path(host.kill_switch)
    private_path(kill, root_owned=True)
    require(kill.read_bytes() == b"ENGAGED\n", "KILL_SWITCH_NOT_ENGAGED")
    # Deliberately absent binding: executes the canonical check-only entrypoint
    # without mounting an operation package or requiring/creating O2 authority.
    absent = root / "not-an-operation"
    require(not absent.exists(), "CHECK_ONLY_FIXTURE_COLLISION")
    paths = SingleDispatchPaths(rc_source=Path(host.source), binding=absent,
        binding_sha256="0" * 64, bundle=absent, authority=absent,
        authority_sha256="0" * 64, provenance=absent, provenance_sha256="0" * 64,
        operation_manifest=absent, asset=absent, reference_transcript=absent,
        rights_record=absent, evidence_directory=root)
    result = await validate_single_dispatch(paths, runtime_policy=ProviderSafetyPolicy())
    require(result.code == "CHECK_ONLY_VALIDATION_FAILED" and
        not result.provider_call_performed and not result.credential_read_performed and
        not result.ready_for_provider_dispatch and not result.ready_for_execution_preflight,
        "CHECK_ONLY_SIDE_EFFECT_OR_AUTHORITY")
    require(kill.read_bytes() == b"ENGAGED\n", "KILL_SWITCH_CHANGED")
    return {"KILL_SWITCH": "ENGAGED", "CHECK_ONLY_RUNNER": "VERIFIED",
            "check_only_probe": "ABSENT_FIXTURE_FAIL_CLOSED_NOT_OPERATION_READINESS"}


async def qualify(host: Host, root: Path) -> dict:
    results = {gate: {"status": "NOT_TESTED"} for gate in GATES}
    ledger = None
    async def gate(name, action):
        try:
            data = action()
            if hasattr(data, "__await__"):
                data = await data
            results[name] = {"status": "PASS", **data}
            return data
        except ProbeBlocked as exc:
            # ProbeBlocked carries only a fixed code and explicit non-secret metadata.
            results[name] = {"status": "BLOCKED", "code": str(exc), **exc.evidence}
            return None
        except Exception:
            # No exception text, path, connection URL, credential or provider body.
            results[name] = {"status": "BLOCKED", "code": name + "_PROBE_FAILED"}
            return None

    # Keep the probe independent from the final receipt/manifest sealing.
    await gate("E1", lambda: {"EVIDENCE_FILESYSTEM": "VERIFIED",
        "probe_sha256": persist(root, "process-boundary.json", {"fixture": True, **ZERO})})
    environment = await gate("E2", lambda: runtime(host))
    if environment is not None:
        ledger = await gate("E3", lambda: custody(host))
        if ledger is not None:
            results["E3"] = {"status": "PASS", "POSTGRES_CUSTODY": "VERIFIED",
                "identity": ledger["identity"], "migration_head": ledger["migration_head"]}
            results["E4"] = {"status": "PASS", "LEDGER_READ_CAPABILITY": "VERIFIED",
                "baseline_counts": ledger["counts"], "reserved_vnd": "0"}
            results["E8"] = ({"status": "PASS", "QUALIFICATION_ACCESS": "SELECT_ONLY",
                "probe": "REPEATABLE_READ_READ_ONLY_WITH_WRITE_REJECTION", "BUDGET_RESERVED": "0"}
                if ledger["qualification_access"] == "SELECT_ONLY" else
                {"status": "BLOCKED", "code": "QUALIFICATION_ACCESS_NOT_SELECT_ONLY", "BUDGET_RESERVED": "0"})
        await gate("E5", lambda: github(host))
        await gate("E6", provider_network)
        await gate("E7", lambda: secret_presence(host))
        await gate("E9", lambda: fixture_mount(root))
        await gate("E10", lambda: check_only(host, root))
        if ledger is not None and results["E10"]["status"] == "PASS":
            try:
                require(await custody(host) == ledger, "LEDGER_CHANGED_DURING_QUALIFICATION")
                results["E10"]["ledger_unchanged"] = True
            except Exception:
                results["E10"] = {"status": "BLOCKED", "code": "LEDGER_RECHECK_FAILED"}
    report = {"task": "VF-SECRET-01", "gates": results, **ZERO,
        "verdict": "CAPABILITY_PROBES_PASS" if all(v["status"] == "PASS" for v in results.values()) else "BLOCKED",
        "execution_plane_qualified": False,
        "runner_identity": expected_runner_identity(host),
        "security_and_dispatch_integration": "SEPARATE_REVIEW_REQUIRED"}
    if results["E10"]["status"] == "PASS":
        results["E10"]["EVIDENCE_RECORDER"] = "VERIFIED"
    digest = persist(root, "qualification.json", report)
    manifest = {"qualification.json": digest}
    if results["E1"]["status"] == "PASS":
        manifest["process-boundary.json"] = results["E1"]["probe_sha256"]
    persist(root, "manifest.json", manifest)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Video Factory zero-call executor qualification")
    parser.parse_args()  # No user-selected paths, commands or configuration.
    try:
        host = Host.load()
        private_path(Path(host.evidence_root), directory=True)
        with plane_lock(Path(host.lock_path)):
            root = Path(host.evidence_root) / ("vf-secret-01-" + uuid.uuid4().hex)
            root.mkdir(mode=0o700)
            report = asyncio.run(qualify(host, root))
        print(json.dumps({"verdict": report["verdict"], "gates": report["gates"],
            "evidence_directory": root.name,
            "qualification_sha256": sha((root / "qualification.json").read_bytes()),
            "manifest_sha256": sha((root / "manifest.json").read_bytes()), **ZERO}, sort_keys=True))
        return 0 if report["verdict"] == "CAPABILITY_PROBES_PASS" else 2
    except Exception:
        print(json.dumps({"verdict": "BLOCKED", "code": "HOST_OR_EVIDENCE_UNAVAILABLE", **ZERO}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
