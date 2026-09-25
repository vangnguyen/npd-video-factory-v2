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

REPOSITORY = "vangnguyen/npd-video-factory-v2"
LABELS = frozenset({"self-hosted", "linux", "npd-video-factory", "provider-execution"})
CONFIG = Path("/etc/npd-video-factory/executor.json")
GATES = tuple(f"E{i}" for i in range(1, 11))
ZERO = {"provider_calls": 0, "credential_reads": 0, "budget_reserved_vnd": "0",
        "operation_consumption": 0, "production_business_writes": 0, "actual_cost_vnd": "0"}


class Blocked(RuntimeError):
    """Only fixed, value-free codes may cross the log boundary."""


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
    repository: str
    runner_name: str
    labels: list[str]
    distro: str
    source: str
    source_commit: str
    evidence_root: str
    lock_path: str
    binding: str
    binding_sha256: str
    migration_head: str
    secret_source: str
    kill_switch: str
    executor_executable_tree_sha256: str = ""

    @classmethod
    def load(cls, path: Path = CONFIG) -> "Host":
        private_path(path, root_owned=True)
        private_path(path.parent, directory=True, root_owned=True)
        raw = path.read_bytes()
        secret_scan(raw)
        host = cls(**json.loads(raw))
        require(host.repository == REPOSITORY, "REPOSITORY_SCOPE_INVALID")
        require(LABELS <= {label.lower() for label in host.labels}, "RUNNER_LABELS_INVALID")
        require(bool(re.fullmatch(r"[a-f0-9]{40}", host.source_commit)), "SOURCE_COMMIT_INVALID")
        require(bool(re.fullmatch(r"[a-f0-9]{64}", host.binding_sha256)), "BINDING_HASH_INVALID")
        require(bool(re.fullmatch(r"[a-f0-9]{64}", host.executor_executable_tree_sha256)),
                "EXECUTOR_TREE_HASH_INVALID")
        return host


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


def runtime(host: Host) -> dict:
    require(sys.platform == "linux" and "microsoft" in platform.release().lower(), "WSL_RUNTIME_UNAVAILABLE")
    require(os.environ.get("WSL_DISTRO_NAME") == host.distro, "WSL_DISTRO_MISMATCH")
    require(sys.version_info >= (3, 12), "PYTHON_VERSION_INVALID")
    require(os.environ.get("RUNNER_NAME") == host.runner_name, "RUNNER_NAME_MISMATCH")
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY, "REPOSITORY_SCOPE_INVALID")
    require(os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch", "UNTRUSTED_EVENT")
    require(os.environ.get("GITHUB_REF") == "refs/heads/main", "UNTRUSTED_REF")
    require(LABELS <= {label.lower() for label in host.labels}, "RUNNER_LABELS_INVALID")
    source = Path(host.source)
    private_path(source, directory=True, root_owned=True)
    private_path(Path(__file__).resolve(), root_owned=True)
    require(Path(__file__).resolve() == source / "apps/api/app/executor_qualification.py", "RUNTIME_SOURCE_MISMATCH")
    def git(*args):
        return subprocess.run(["git", "-C", str(source), *args], check=True,
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
            "executor_executable_tree_sha256": tree["executor_executable_tree_sha256"]}


async def custody(host: Host) -> dict:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from .provider_runtime_bootstrap import load_binding, verify_socket_custody, ledger_url, read_custody
    binding = load_binding(Path(host.binding), host.binding_sha256)
    verify_socket_custody(binding)
    engine = create_async_engine(ledger_url(binding), echo=False,
        connect_args={"password": "", "server_settings": {"default_transaction_read_only": "on"}})
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        result = await read_custody(factory, binding, require_virgin_namespace=True)
        require(result["control_present"], "CONTROL_NOT_INITIALIZED")
        async with factory() as session, session.begin():
            await session.execute(text("SET TRANSACTION READ ONLY"))
            migration = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
            require(migration == [host.migration_head], "MIGRATION_HEAD_MISMATCH")
            # Read the dispatch-marker and request-receipt columns as well as
            # the canonical custody helper's operation/reservation snapshot.
            await session.execute(text("SELECT dispatch_started_at, dispatch_request_sha256, dispatch_client_request_id FROM provider_safety_operations LIMIT 0"))
            await session.execute(text("SELECT error_evidence FROM provider_safety_attempts LIMIT 0"))
            tables = ("provider_safety_control", "provider_safety_operations", "provider_safety_attempts",
                      "provider_safety_budget_days", "provider_safety_circuits", "provider_safety_budget_alerts")
            privileges = []
            for table in tables:
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    privileges.append(await session.scalar(text("SELECT has_table_privilege(current_user, :table, :privilege)"),
                        {"table": "public." + table, "privilege": privilege}))
            result["reservation_privileges"] = all(privileges)
        result["migration_head"] = migration[0]
        return result
    finally:
        await engine.dispose()


def github(host: Host) -> dict:
    result = subprocess.run(["git", "ls-remote", "--exit-code",
        "https://github.com/" + REPOSITORY + ".git", "refs/heads/main"],
        capture_output=True, text=True, timeout=30, check=True)
    require(bool(re.fullmatch(r"[a-f0-9]{40}\s+refs/heads/main\s*", result.stdout)), "GITHUB_PROVENANCE_UNAVAILABLE")
    return {"GITHUB_ACCESS": "VERIFIED", "observed_main": result.stdout.split()[0]}


def provider_network() -> dict:
    # TLS handshake only. No HTTP request, authorization header or model API.
    with socket.create_connection(("api.openai.com", 443), timeout=10) as tcp:
        with ssl.create_default_context().wrap_socket(tcp, server_hostname="api.openai.com") as tls:
            require(bool(tls.getpeercert()), "PROVIDER_TLS_UNVERIFIED")
    return {"PROVIDER_NETWORK": "VERIFIED", "probe": "TLS_HANDSHAKE_ONLY", "http_requests": 0}


def secret_presence(host: Host) -> dict:
    path = Path(host.secret_source)
    private_path(path)
    require(path.stat().st_size > 0 and os.access(path, os.R_OK), "SECRET_SOURCE_MISSING")
    # Never open/read the file, even for redaction setup.
    return {"SECRET_SOURCE": "PRESENT", "plaintext_read": False}


def fixture_mount(root: Path) -> dict:
    from .provider_gate_loader import load_verified_provider_gate_bundle
    # Runtime bundle mounts are private staged files, not privileged OS mounts.
    # This fixture cannot contain an Owner approval or an active operation.
    with tempfile.TemporaryDirectory(prefix="fixture-mount-", dir=root) as directory:
        mount = Path(directory)
        raw = (Path(__file__).parent / "data/executor/expired-loader-fixture.json").read_bytes()
        require(sha(raw) == "58d7298b2e69f63494070e30c7dba235f83c1337001af2ea8a839a47cf654e02",
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
                "operation_state": ledger["operation_state"], "reserved_vnd": ledger["reserved_vnd"]}
            results["E8"] = ({"status": "PASS", "RESERVATION_CAPABILITY": "VERIFIED",
                "probe": "READ_ONLY_BACKEND_AND_PRIVILEGES_NOT_RESERVATION", "BUDGET_RESERVED": "0"}
                if ledger["reservation_privileges"] else
                {"status": "BLOCKED", "code": "RESERVATION_BACKEND_PRIVILEGES_MISSING", "BUDGET_RESERVED": "0"})
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
    report = {"task": "VF-EXECUTOR-02", "gates": results, **ZERO,
        "verdict": "CAPABILITY_PROBES_PASS" if all(v["status"] == "PASS" for v in results.values()) else "BLOCKED",
        "execution_plane_qualified": False,
        "source_commit": host.source_commit, "runner_name": host.runner_name,
        "runner_id": 21,
        "executor_executable_tree_sha256": host.executor_executable_tree_sha256,
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
            root = Path(host.evidence_root) / ("vf-executor-02-" + uuid.uuid4().hex)
            root.mkdir(mode=0o700)
            report = asyncio.run(qualify(host, root))
        print(json.dumps({"verdict": report["verdict"], "gates": report["gates"], **ZERO}, sort_keys=True))
        return 0 if report["verdict"] == "CAPABILITY_PROBES_PASS" else 2
    except Exception:
        print(json.dumps({"verdict": "BLOCKED", "code": "HOST_OR_EVIDENCE_UNAVAILABLE", **ZERO}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
