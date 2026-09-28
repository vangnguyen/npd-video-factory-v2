#!/usr/bin/env python3
"""Exercise the immutable GHCR MinIO image used by Video Factory.

The harness is deliberately self-contained and disposable.  It anonymously
pulls one digest-only image, validates its identity, starts it only on loopback
with fixture credentials, exercises the consumed S3 behavior, proves named
volume persistence across clean restarts and container replacement, and removes
everything it created.  A sanitized JSON receipt is written on both success
and failure.

Only boto3 and botocore are required beyond the Python standard library.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn


TASK_ID = "VF-REGISTRY-01"
EXPECTED_ORG_PREFIX = "ghcr.io/npd-ai/"
IMAGE_REFERENCE_RE = re.compile(
    r"^ghcr\.io/npd-ai/[a-z0-9](?:[a-z0-9._/-]*[a-z0-9])?"
    r"@sha256:(?P<digest>[0-9a-f]{64})$"
)
RELEASE_RE = re.compile(
    r"^RELEASE\.\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
STARTUP_ARGUMENTS = ["server", "/data", "--console-address", ":9001"]
HEALTH_COMMAND = "curl -fsS http://localhost:9000/minio/health/live >/dev/null"
FIXTURE_PREFIX = b"VF-REGISTRY-01 MinIO compatibility fixture\n"
MAX_ERROR_CHARS = 8_000
SAFE_AMBIENT_ENVIRONMENT_KEYS = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "TMP",
    "TEMP",
    "USER",
    "LOGNAME",
    # These keys are needed when the static checks run on Windows.  They do
    # not contain registry, cloud, proxy, or provider credentials.
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
)


class HarnessFailure(RuntimeError):
    """A safe, user-facing compatibility failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Redactor:
    """Remove ephemeral credential values from every diagnostic boundary."""

    def __init__(self) -> None:
        self._values: list[str] = []

    def add(self, value: str) -> None:
        if value and value not in self._values:
            self._values.append(value)

    def redact(self, value: object) -> str:
        text = str(value)
        for secret_value in sorted(self._values, key=len, reverse=True):
            text = text.replace(secret_value, "[REDACTED]")
        return text


def emit(message: str) -> None:
    print(f"[minio-ghcr-compatibility] {message}", file=sys.stderr, flush=True)


def run_command(
    arguments: Sequence[str],
    *,
    description: str,
    environment: dict[str, str],
    redactor: Redactor,
    timeout_seconds: int = 300,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            list(arguments),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise HarnessFailure(f"{description}: executable was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise HarnessFailure(
            f"{description}: timed out after {timeout_seconds} seconds"
        ) from exc

    if check and completed.returncode != 0:
        diagnostic = completed.stderr.strip() or completed.stdout.strip()
        diagnostic = redactor.redact(diagnostic)[-MAX_ERROR_CHARS:]
        suffix = f": {diagnostic}" if diagnostic else ""
        raise HarnessFailure(
            f"{description}: exited with {completed.returncode}{suffix}"
        )
    return completed


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the immutable linux/amd64 MinIO image mirrored in GHCR."
    )
    parser.add_argument(
        "--image",
        required=True,
        help="Digest-only ghcr.io/npd-ai/...@sha256:... operative image reference.",
    )
    parser.add_argument(
        "--expected-release",
        required=True,
        help="Exact MinIO release, for example RELEASE.2025-09-07T16-13-09Z.",
    )
    parser.add_argument(
        "--expected-binary-sha256",
        required=True,
        help="Official SHA-256 of the linux/amd64 MinIO binary.",
    )
    parser.add_argument(
        "--artifact",
        required=True,
        type=Path,
        help="Destination for the PASS/FAIL JSON receipt.",
    )
    parser.add_argument(
        "--docker-bin",
        default="docker",
        help="Docker CLI executable (default: docker).",
    )
    parser.add_argument(
        "--binary-path",
        default="/usr/local/bin/minio",
        help="MinIO binary path inside the controlled image.",
    )
    parser.add_argument(
        "--startup-timeout-seconds",
        type=int,
        default=120,
        help="Maximum wait for each healthy start (default: 120).",
    )
    return parser.parse_args()


def validate_arguments(arguments: argparse.Namespace) -> str:
    match = IMAGE_REFERENCE_RE.fullmatch(arguments.image)
    if match is None or not arguments.image.startswith(EXPECTED_ORG_PREFIX):
        raise HarnessFailure(
            "--image must be a lowercase digest-only reference beneath "
            f"{EXPECTED_ORG_PREFIX}"
        )
    if RELEASE_RE.fullmatch(arguments.expected_release) is None:
        raise HarnessFailure("--expected-release is not an exact MinIO RELEASE timestamp")
    if SHA256_RE.fullmatch(arguments.expected_binary_sha256) is None:
        raise HarnessFailure("--expected-binary-sha256 must be 64 lowercase hex characters")
    if arguments.startup_timeout_seconds < 10:
        raise HarnessFailure("--startup-timeout-seconds must be at least 10")
    if not arguments.binary_path.startswith("/"):
        raise HarnessFailure("--binary-path must be an absolute container path")
    return match.group("digest")


def write_receipt(path: Path, receipt: dict[str, Any], redactor: Redactor) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False)
    serialized = redactor.redact(serialized) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def build_subprocess_environment(docker_config: str) -> dict[str, str]:
    """Build a minimal environment without inheriting ambient credentials.

    In particular, Docker auth, cloud/provider credentials, registry tokens,
    and HTTP(S)/ALL proxy variables are not copied from the harness process.
    Docker receives a task-local empty config and all runtime traffic after the
    registry pull is explicitly constrained to loopback.
    """

    environment = {
        key: os.environ[key]
        for key in SAFE_AMBIENT_ENVIRONMENT_KEYS
        if key in os.environ
    }
    environment.update(
        {
            "DOCKER_CONFIG": docker_config,
            "AWS_EC2_METADATA_DISABLED": "true",
            "AWS_DEFAULT_REGION": "us-east-1",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        }
    )
    return environment


def docker_json(
    docker_bin: str,
    docker_environment: dict[str, str],
    redactor: Redactor,
    object_kind: str,
    object_name: str,
    template: str,
    description: str,
) -> Any:
    completed = run_command(
        [docker_bin, object_kind, "inspect", "--format", template, object_name],
        description=description,
        environment=docker_environment,
        redactor=redactor,
    )
    try:
        return json.loads(completed.stdout.strip())
    except json.JSONDecodeError as exc:
        raise HarnessFailure(f"{description}: Docker returned invalid JSON") from exc


def image_metadata(
    docker_bin: str,
    image: str,
    docker_environment: dict[str, str],
    redactor: Redactor,
) -> dict[str, Any]:
    value = docker_json(
        docker_bin,
        docker_environment,
        redactor,
        "image",
        image,
        "{{json .}}",
        "inspect pulled image",
    )
    config = value.get("Config") or {}
    return {
        "id": value.get("Id"),
        "repo_digests": value.get("RepoDigests") or [],
        "os": value.get("Os"),
        "architecture": value.get("Architecture"),
        "exposed_ports": sorted((config.get("ExposedPorts") or {}).keys()),
    }


def wait_for_healthy(
    docker_bin: str,
    container_name: str,
    docker_environment: dict[str, str],
    redactor: Redactor,
    timeout_seconds: int,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_state = "unknown"
    while time.monotonic() < deadline:
        completed = run_command(
            [
                docker_bin,
                "container",
                "inspect",
                "--format",
                "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}",
                container_name,
            ],
            description="inspect MinIO health state",
            environment=docker_environment,
            redactor=redactor,
            timeout_seconds=20,
        )
        last_state = completed.stdout.strip()
        status, _, health = last_state.partition("|")
        if status == "running" and health == "healthy":
            return
        if status in {"dead", "exited", "removing"} or health == "unhealthy":
            raise HarnessFailure(f"MinIO failed health transition: {last_state}")
        time.sleep(1)
    raise HarnessFailure(
        f"MinIO did not become healthy within {timeout_seconds} seconds "
        f"(last state: {last_state})"
    )


def published_port(
    docker_bin: str,
    container_name: str,
    container_port: int,
    docker_environment: dict[str, str],
    redactor: Redactor,
) -> int:
    completed = run_command(
        [docker_bin, "port", container_name, f"{container_port}/tcp"],
        description=f"resolve loopback mapping for port {container_port}",
        environment=docker_environment,
        redactor=redactor,
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    expected_prefix = "127.0.0.1:"
    candidates = [line for line in lines if line.startswith(expected_prefix)]
    if len(candidates) != 1:
        raise HarnessFailure(
            f"port {container_port} must have exactly one IPv4 loopback mapping"
        )
    try:
        return int(candidates[0][len(expected_prefix) :])
    except ValueError as exc:
        raise HarnessFailure(f"port {container_port} mapping is malformed") from exc


def http_status(port: int, path: str) -> int:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path, headers={"Connection": "close"})
        response = connection.getresponse()
        response.read()
        return response.status
    except OSError as exc:
        raise HarnessFailure(
            f"loopback HTTP probe failed for port {port}{path}: {exc}"
        ) from exc
    finally:
        connection.close()


def create_s3_client(port: int, access_key: str, secret_key: str) -> Any:
    try:
        import boto3  # type: ignore[import-not-found]
        from botocore.config import Config  # type: ignore[import-not-found]
    except ImportError as exc:
        raise HarnessFailure(
            "boto3 and botocore are required; install boto3 before running the harness"
        ) from exc

    return boto3.client(
        "s3",
        endpoint_url=f"http://127.0.0.1:{port}",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        use_ssl=False,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 5, "mode": "standard"},
            connect_timeout=5,
            read_timeout=10,
            proxies={},
        ),
    )


def client_error_status(error: BaseException) -> int | None:
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return None
    metadata = response.get("ResponseMetadata")
    if not isinstance(metadata, dict):
        return None
    status = metadata.get("HTTPStatusCode")
    return status if isinstance(status, int) else None


def assert_s3_missing(action: Callable[[], Any], description: str) -> None:
    try:
        from botocore.exceptions import ClientError  # type: ignore[import-not-found]
    except ImportError as exc:
        raise HarnessFailure(
            "botocore is required to verify an absent S3 resource"
        ) from exc

    try:
        action()
    except ClientError as exc:
        if client_error_status(exc) == 404:
            return
        raise HarnessFailure(
            f"{description}: expected HTTP 404, got {client_error_status(exc)!r}"
        ) from exc
    raise HarnessFailure(f"{description}: resource unexpectedly still exists")


def get_object_bytes(client: Any, bucket: str, key: str) -> bytes:
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    try:
        return body.read()
    finally:
        body.close()


def verify_persisted_object(
    client: Any,
    bucket: str,
    key: str,
    expected_bytes: bytes,
    expected_sha256: str,
) -> None:
    client.head_bucket(Bucket=bucket)
    head = client.head_object(Bucket=bucket, Key=key)
    if head.get("ContentLength") != len(expected_bytes):
        raise HarnessFailure("persisted object length changed")
    metadata = head.get("Metadata") or {}
    if metadata.get("sha256") != expected_sha256:
        raise HarnessFailure("persisted object SHA-256 metadata changed")
    actual_bytes = get_object_bytes(client, bucket, key)
    if hashlib.sha256(actual_bytes).hexdigest() != expected_sha256:
        raise HarnessFailure("persisted object bytes changed")


class Harness:
    def __init__(
        self,
        arguments: argparse.Namespace,
        expected_digest: str,
        receipt: dict[str, Any],
        redactor: Redactor,
        docker_environment: dict[str, str],
    ) -> None:
        self.arguments = arguments
        self.expected_digest = expected_digest
        self.receipt = receipt
        self.redactor = redactor
        self.docker_environment = docker_environment
        self.container_names: list[str] = []
        self.volume_names: list[str] = []
        self.image_pulled = False
        self.image_pull_attempted = False

        suffix_source = "-".join(
            filter(
                None,
                [
                    os.environ.get("GITHUB_RUN_ID", "local"),
                    os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
                    uuid.uuid4().hex[:8],
                ],
            )
        ).lower()
        suffix = re.sub(r"[^a-z0-9-]", "-", suffix_source)[:36].strip("-")
        self.first_container = f"vf-registry-minio-a-{suffix}"
        self.second_container = f"vf-registry-minio-b-{suffix}"
        self.inspect_container = f"vf-registry-minio-inspect-{suffix}"
        self.volume_name = f"vf-registry-minio-data-{suffix}"
        bucket_suffix = re.sub(r"[^a-z0-9-]", "-", suffix)[:40].strip("-")
        self.bucket = f"vf-registry-{bucket_suffix}"[:63].rstrip("-")
        self.object_key = "compatibility/fixture.bin"
        self.access_key = f"vfci{secrets.token_hex(8)}"
        self.secret_key = secrets.token_urlsafe(32)
        self.redactor.add(self.access_key)
        self.redactor.add(self.secret_key)
        self.fixture_bytes = FIXTURE_PREFIX + arguments.expected_release.encode("ascii") + b"\n"
        self.fixture_sha256 = hashlib.sha256(self.fixture_bytes).hexdigest()

    def stage(self, name: str) -> None:
        self.receipt["stage"] = name
        emit(name.replace("_", " "))

    def command(
        self,
        arguments: Sequence[str],
        *,
        description: str,
        timeout_seconds: int = 300,
        check: bool = True,
        extra_environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = self.docker_environment.copy()
        if extra_environment:
            environment.update(extra_environment)
        return run_command(
            arguments,
            description=description,
            environment=environment,
            redactor=self.redactor,
            timeout_seconds=timeout_seconds,
            check=check,
        )

    def docker(self, *arguments: str, description: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return self.command(
            [self.arguments.docker_bin, *arguments],
            description=description,
            **kwargs,
        )

    def preflight_and_pull(self) -> None:
        self.stage("fresh_anonymous_pull")
        version = self.docker(
            "version",
            "--format",
            "{{.Server.Os}}/{{.Server.Arch}}",
            description="inspect Docker server platform",
        ).stdout.strip()
        if version != "linux/amd64":
            raise HarnessFailure(
                f"Docker server must be linux/amd64 for this gate, got {version!r}"
            )

        self.docker(
            "image",
            "rm",
            "--force",
            self.arguments.image,
            description="remove any cached operative image reference",
            check=False,
        )
        cached = self.docker(
            "image",
            "inspect",
            self.arguments.image,
            description="verify operative reference is absent before pull",
            check=False,
        )
        if cached.returncode == 0:
            raise HarnessFailure("operative image reference remained cached before fresh pull")

        self.image_pull_attempted = True
        self.docker(
            "pull",
            "--platform",
            "linux/amd64",
            self.arguments.image,
            description="fresh anonymous GHCR pull",
            timeout_seconds=600,
        )
        self.image_pulled = True
        metadata = image_metadata(
            self.arguments.docker_bin,
            self.arguments.image,
            self.docker_environment,
            self.redactor,
        )
        if self.arguments.image not in metadata["repo_digests"]:
            raise HarnessFailure("pulled RepoDigests do not contain the operative reference")
        if (metadata["os"], metadata["architecture"]) != ("linux", "amd64"):
            raise HarnessFailure(
                "pulled image platform is not exactly linux/amd64: "
                f"{metadata['os']}/{metadata['architecture']}"
            )
        required_ports = {"9000/tcp", "9001/tcp"}
        if not required_ports.issubset(set(metadata["exposed_ports"])):
            raise HarnessFailure("controlled image does not expose both 9000/tcp and 9001/tcp")
        self.receipt["image"].update(metadata)
        self.receipt["image"]["pull"] = "PASS"

    def verify_binary_identity(self) -> None:
        self.stage("binary_and_release_identity")
        self.container_names.append(self.inspect_container)
        self.docker(
            "create",
            "--name",
            self.inspect_container,
            self.arguments.image,
            *STARTUP_ARGUMENTS,
            description="create binary-inspection container",
        )
        with tempfile.TemporaryDirectory(prefix="vf-registry-minio-binary-") as directory:
            destination = Path(directory) / "minio"
            self.docker(
                "cp",
                f"{self.inspect_container}:{self.arguments.binary_path}",
                str(destination),
                description="extract MinIO binary for SHA-256 verification",
            )
            observed_sha256 = hashlib.sha256(destination.read_bytes()).hexdigest()
        if observed_sha256 != self.arguments.expected_binary_sha256:
            raise HarnessFailure(
                "MinIO binary SHA-256 mismatch: "
                f"expected {self.arguments.expected_binary_sha256}, got {observed_sha256}"
            )

        observed_version = self.docker(
            "run",
            "--rm",
            "--entrypoint",
            self.arguments.binary_path,
            self.arguments.image,
            "--version",
            description="read MinIO version",
        ).stdout.strip()
        release_line = re.compile(
            rf"^minio version {re.escape(self.arguments.expected_release)}(?:\s|$)",
            re.MULTILINE,
        )
        if release_line.search(observed_version) is None:
            raise HarnessFailure(
                "MinIO version output does not identify the expected exact release"
            )
        self.receipt["identity"].update(
            {
                "binary_sha256": observed_sha256,
                "binary_sha256_verification": "PASS",
                "observed_version": observed_version,
                "release_verification": "PASS",
            }
        )
        self.docker(
            "rm",
            "--force",
            self.inspect_container,
            description="remove binary-inspection container",
        )

    def create_volume(self) -> None:
        self.stage("create_disposable_volume")
        self.volume_names.append(self.volume_name)
        self.docker(
            "volume",
            "create",
            self.volume_name,
            description="create disposable MinIO volume",
        )

    def start_new_container(self, name: str) -> tuple[int, int, int]:
        if name not in self.container_names:
            self.container_names.append(name)
        self.docker(
            "run",
            "--detach",
            "--name",
            name,
            "--env",
            "MINIO_ROOT_USER",
            "--env",
            "MINIO_ROOT_PASSWORD",
            "--volume",
            f"{self.volume_name}:/data",
            "--publish",
            "127.0.0.1::9000",
            "--publish",
            "127.0.0.1::9001",
            "--health-cmd",
            HEALTH_COMMAND,
            "--health-interval",
            "5s",
            "--health-timeout",
            "3s",
            "--health-retries",
            "20",
            self.arguments.image,
            *STARTUP_ARGUMENTS,
            description="start disposable MinIO container",
            extra_environment={
                "MINIO_ROOT_USER": self.access_key,
                "MINIO_ROOT_PASSWORD": self.secret_key,
            },
        )
        wait_for_healthy(
            self.arguments.docker_bin,
            name,
            self.docker_environment,
            self.redactor,
            self.arguments.startup_timeout_seconds,
        )
        api_port = published_port(
            self.arguments.docker_bin,
            name,
            9000,
            self.docker_environment,
            self.redactor,
        )
        console_port = published_port(
            self.arguments.docker_bin,
            name,
            9001,
            self.docker_environment,
            self.redactor,
        )
        self.verify_runtime_contract(name)
        health_status = http_status(api_port, "/minio/health/live")
        if health_status != 200:
            raise HarnessFailure(f"MinIO live health returned HTTP {health_status}")
        console_status = http_status(console_port, "/")
        if not 200 <= console_status < 400:
            raise HarnessFailure(f"MinIO console returned HTTP {console_status}")
        return api_port, console_port, console_status

    def verify_runtime_contract(self, name: str) -> None:
        value = docker_json(
            self.arguments.docker_bin,
            self.docker_environment,
            self.redactor,
            "container",
            name,
            "{{json .}}",
            "inspect disposable MinIO runtime contract",
        )
        if value.get("Args") != STARTUP_ARGUMENTS:
            raise HarnessFailure("MinIO startup arguments changed")
        mounts = value.get("Mounts") or []
        matching_mounts = [
            mount
            for mount in mounts
            if mount.get("Destination") == "/data"
            and mount.get("Type") == "volume"
            and mount.get("Name") == self.volume_name
            and mount.get("RW") is True
        ]
        if len(matching_mounts) != 1:
            raise HarnessFailure("MinIO /data mount is not the expected writable named volume")
        healthcheck = ((value.get("Config") or {}).get("Healthcheck") or {})
        if healthcheck.get("Test") != ["CMD-SHELL", HEALTH_COMMAND]:
            raise HarnessFailure("MinIO health command changed")
        if healthcheck.get("Interval") != 5_000_000_000:
            raise HarnessFailure("MinIO health interval is not 5 seconds")
        if healthcheck.get("Timeout") != 3_000_000_000:
            raise HarnessFailure("MinIO health timeout is not 3 seconds")
        if healthcheck.get("Retries") != 20:
            raise HarnessFailure("MinIO health retries is not 20")

    def clean_stop(self, name: str, cycle: str) -> None:
        self.docker(
            "stop",
            "--time",
            "20",
            name,
            description=f"cleanly stop MinIO ({cycle})",
            timeout_seconds=40,
        )
        state = docker_json(
            self.arguments.docker_bin,
            self.docker_environment,
            self.redactor,
            "container",
            name,
            "{{json .State}}",
            f"inspect stopped MinIO state ({cycle})",
        )
        if state.get("Status") != "exited":
            raise HarnessFailure(f"MinIO did not reach exited state during {cycle}")
        if state.get("OOMKilled") is not False:
            raise HarnessFailure(f"MinIO was OOM-killed during {cycle}")
        if state.get("ExitCode") != 0:
            raise HarnessFailure(
                f"MinIO clean stop returned exit code {state.get('ExitCode')!r} during {cycle}"
            )
        self.receipt["persistence"]["clean_shutdowns"].append(
            {"cycle": cycle, "exit_code": 0, "oom_killed": False, "status": "PASS"}
        )

    def restart_container(self, name: str) -> int:
        self.docker("start", name, description="restart disposable MinIO container")
        wait_for_healthy(
            self.arguments.docker_bin,
            name,
            self.docker_environment,
            self.redactor,
            self.arguments.startup_timeout_seconds,
        )
        api_port = published_port(
            self.arguments.docker_bin,
            name,
            9000,
            self.docker_environment,
            self.redactor,
        )
        if http_status(api_port, "/minio/health/live") != 200:
            raise HarnessFailure("restarted MinIO live health did not return HTTP 200")
        return api_port

    def s3_client(self, api_port: int) -> Any:
        return create_s3_client(api_port, self.access_key, self.secret_key)

    def exercise_s3_and_persistence(self) -> None:
        self.stage("startup_health_and_s3_crud")
        api_port, console_port, console_status = self.start_new_container(
            self.first_container
        )
        self.receipt["runtime"].update(
            {
                "startup": "PASS",
                "startup_arguments": STARTUP_ARGUMENTS,
                "data_mount": "NAMED_VOLUME_RW_AT_/data",
                "health": "PASS",
                "health_http_status": 200,
                "console": "PASS",
                "console_http_status": console_status,
                "container_ports": {"api": 9000, "console": 9001},
                "host_bind": "127.0.0.1 ephemeral",
            }
        )
        del console_port

        client = self.s3_client(api_port)
        client.create_bucket(Bucket=self.bucket)
        self.receipt["s3"]["bucket_create"] = "PASS"
        client.head_bucket(Bucket=self.bucket)
        self.receipt["s3"]["bucket_head"] = "PASS"
        bucket_names = {item["Name"] for item in client.list_buckets().get("Buckets", [])}
        if self.bucket not in bucket_names:
            raise HarnessFailure("created bucket is absent from list_buckets")
        self.receipt["s3"]["bucket_list"] = "PASS"

        client.put_object(
            Bucket=self.bucket,
            Key=self.object_key,
            Body=self.fixture_bytes,
            ContentType="application/octet-stream",
            Metadata={"sha256": self.fixture_sha256},
        )
        self.receipt["s3"]["object_put"] = "PASS"
        verify_persisted_object(
            client,
            self.bucket,
            self.object_key,
            self.fixture_bytes,
            self.fixture_sha256,
        )
        self.receipt["s3"]["object_head"] = "PASS"
        self.receipt["s3"]["object_get_sha256"] = "PASS"
        listed_keys = {
            item["Key"]
            for item in client.list_objects_v2(Bucket=self.bucket).get("Contents", [])
        }
        if self.object_key not in listed_keys:
            raise HarnessFailure("created object is absent from list_objects_v2")
        self.receipt["s3"]["object_list"] = "PASS"

        self.stage("same_container_clean_restart")
        self.clean_stop(self.first_container, "same_container_before_restart")
        api_port = self.restart_container(self.first_container)
        client = self.s3_client(api_port)
        verify_persisted_object(
            client,
            self.bucket,
            self.object_key,
            self.fixture_bytes,
            self.fixture_sha256,
        )
        self.receipt["persistence"]["same_container_restart"] = "PASS"

        self.stage("replacement_container_persistence")
        self.clean_stop(self.first_container, "before_container_replacement")
        self.docker(
            "rm",
            self.first_container,
            description="remove first MinIO container",
        )
        api_port, _, _ = self.start_new_container(self.second_container)
        client = self.s3_client(api_port)
        verify_persisted_object(
            client,
            self.bucket,
            self.object_key,
            self.fixture_bytes,
            self.fixture_sha256,
        )
        self.receipt["persistence"]["replacement_container_same_volume"] = "PASS"

        self.stage("s3_delete_and_clean_restart")
        client.delete_object(Bucket=self.bucket, Key=self.object_key)
        assert_s3_missing(
            lambda: client.head_object(Bucket=self.bucket, Key=self.object_key),
            "verify object deletion",
        )
        remaining = client.list_objects_v2(Bucket=self.bucket).get("Contents", [])
        if any(item.get("Key") == self.object_key for item in remaining):
            raise HarnessFailure("deleted object is still listed")
        self.receipt["s3"]["object_delete"] = "PASS"

        client.delete_bucket(Bucket=self.bucket)
        assert_s3_missing(
            lambda: client.head_bucket(Bucket=self.bucket),
            "verify bucket deletion",
        )
        remaining_buckets = {
            item["Name"] for item in client.list_buckets().get("Buckets", [])
        }
        if self.bucket in remaining_buckets:
            raise HarnessFailure("deleted bucket is still listed")
        self.receipt["s3"]["bucket_delete"] = "PASS"

        self.clean_stop(self.second_container, "after_crud_cleanup")
        api_port = self.restart_container(self.second_container)
        client = self.s3_client(api_port)
        assert_s3_missing(
            lambda: client.head_bucket(Bucket=self.bucket),
            "verify bucket deletion persisted after restart",
        )
        self.receipt["persistence"]["deletion_after_restart"] = "PASS"
        self.clean_stop(self.second_container, "final_clean_shutdown")

    def collect_logs(self) -> str | None:
        for name in reversed(self.container_names):
            completed = self.docker(
                "logs",
                "--tail",
                "200",
                name,
                description="collect sanitized failure logs",
                check=False,
                timeout_seconds=20,
            )
            if completed.returncode == 0:
                combined = "\n".join(
                    part for part in (completed.stdout.strip(), completed.stderr.strip()) if part
                )
                if combined:
                    return self.redactor.redact(combined)[-MAX_ERROR_CHARS:]
        return None

    def cleanup(self) -> list[str]:
        errors: list[str] = []
        cleanup_receipt = self.receipt["cleanup"]
        removed_containers: list[str] = []
        removed_volumes: list[str] = []

        for name in reversed(self.container_names):
            completed = self.docker(
                "rm",
                "--force",
                name,
                description=f"remove disposable container {name}",
                check=False,
                timeout_seconds=30,
            )
            diagnostic = f"{completed.stdout}\n{completed.stderr}"
            if completed.returncode == 0 or "No such container" in diagnostic:
                removed_containers.append(name)
            else:
                errors.append(f"failed to remove disposable container {name}")

        for name in reversed(self.volume_names):
            completed = self.docker(
                "volume",
                "rm",
                "--force",
                name,
                description=f"remove disposable volume {name}",
                check=False,
                timeout_seconds=30,
            )
            diagnostic = f"{completed.stdout}\n{completed.stderr}"
            if completed.returncode == 0 or "No such volume" in diagnostic:
                removed_volumes.append(name)
            else:
                errors.append(f"failed to remove disposable volume {name}")

        if self.image_pull_attempted:
            completed = self.docker(
                "image",
                "rm",
                "--force",
                self.arguments.image,
                description="remove pulled operative image reference",
                check=False,
                timeout_seconds=60,
            )
            diagnostic = f"{completed.stdout}\n{completed.stderr}"
            image_removed = completed.returncode == 0 or "No such image" in diagnostic
            if not image_removed:
                errors.append("failed to remove pulled operative image reference")
        else:
            image_removed = True

        cleanup_receipt.update(
            {
                "containers_removed": sorted(set(removed_containers)),
                "volumes_removed": sorted(set(removed_volumes)),
                "operative_image_reference_removed": image_removed,
                "status": "PASS" if not errors else "FAIL",
            }
        )
        return errors


def make_receipt(arguments: argparse.Namespace) -> dict[str, Any]:
    return {
        "task_id": TASK_ID,
        "status": "RUNNING",
        "stage": "initialization",
        "started_at": utc_now(),
        "finished_at": None,
        "image": {
            "operative_reference": arguments.image,
            "expected_digest": arguments.image.rsplit("@sha256:", 1)[-1],
            "pull_authentication": "ANONYMOUS_EMPTY_DOCKER_CONFIG",
            "required_platform": "linux/amd64",
        },
        "identity": {
            "expected_release": arguments.expected_release,
            "expected_binary_sha256": arguments.expected_binary_sha256,
            "binary_path": arguments.binary_path,
        },
        "runtime": {},
        "s3": {},
        "persistence": {"clean_shutdowns": []},
        "cleanup": {"status": "PENDING"},
        "safety": {
            "network_scope": "127.0.0.1_ONLY_AFTER_GHCR_PULL",
            "fixture_credentials_only": True,
            "provider_calls": 0,
            "provider_credential_reads": 0,
            "owned_credentials_read": 0,
            "production_writes": 0,
        },
        "failure": None,
    }


def interrupted(signum: int, _frame: object) -> NoReturn:
    raise InterruptedError(f"received signal {signum}")


def main() -> int:
    arguments = parse_arguments()
    redactor = Redactor()
    receipt = make_receipt(arguments)
    harness: Harness | None = None
    failure: BaseException | None = None
    cleanup_errors: list[str] = []

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)

    with tempfile.TemporaryDirectory(prefix="vf-registry-docker-config-") as docker_config:
        docker_environment = build_subprocess_environment(docker_config)
        receipt["safety"].update(
            {
                "ambient_environment_policy": "EXPLICIT_ALLOWLIST_NO_AUTH_OR_PROXY",
                "subprocess_environment_forwarded_keys": sorted(
                    docker_environment.keys()
                ),
                "fixture_environment_keys": [
                    "MINIO_ROOT_PASSWORD",
                    "MINIO_ROOT_USER",
                ],
            }
        )
        try:
            expected_digest = validate_arguments(arguments)
            if receipt["image"]["expected_digest"] != expected_digest:
                raise HarnessFailure("internal digest parsing mismatch")
            harness = Harness(
                arguments,
                expected_digest,
                receipt,
                redactor,
                docker_environment,
            )
            harness.preflight_and_pull()
            harness.verify_binary_identity()
            harness.create_volume()
            harness.exercise_s3_and_persistence()
        except BaseException as exc:
            failure = exc
            if harness is not None:
                try:
                    logs = harness.collect_logs()
                except BaseException as log_exc:
                    receipt["failure_log_collection"] = {
                        "status": "FAIL",
                        "message": redactor.redact(log_exc)[-MAX_ERROR_CHARS:],
                    }
                else:
                    if logs:
                        receipt["failure_logs"] = logs
        finally:
            if harness is not None:
                try:
                    cleanup_errors = harness.cleanup()
                except BaseException as cleanup_exc:
                    cleanup_errors = [
                        "cleanup raised unexpectedly: "
                        + redactor.redact(cleanup_exc)[-MAX_ERROR_CHARS:]
                    ]
                    receipt["cleanup"]["status"] = "FAIL"
            else:
                receipt["cleanup"].update(
                    {
                        "containers_removed": [],
                        "volumes_removed": [],
                        "operative_image_reference_removed": True,
                        "status": "PASS",
                    }
                )

    if failure is not None or cleanup_errors:
        receipt["status"] = "FAIL"
        if failure is not None:
            failure_message = redactor.redact(failure)[-MAX_ERROR_CHARS:]
            receipt["failure"] = {
                "type": type(failure).__name__,
                "message": failure_message,
                "stage": receipt["stage"],
            }
            emit(f"FAIL at {receipt['stage']}: {failure_message}")
        if cleanup_errors:
            receipt["cleanup"]["errors"] = cleanup_errors
            if receipt["failure"] is None:
                receipt["failure"] = {
                    "type": "CleanupFailure",
                    "message": "; ".join(cleanup_errors),
                    "stage": "cleanup",
                }
                receipt["stage"] = "cleanup"
            emit("FAIL during cleanup: " + "; ".join(cleanup_errors))
        exit_code = 1
    else:
        receipt["status"] = "PASS"
        receipt["stage"] = "complete"
        emit("PASS")
        exit_code = 0

    receipt["finished_at"] = utc_now()
    try:
        write_receipt(arguments.artifact, receipt, redactor)
    except BaseException as exc:
        emit(f"could not write receipt: {redactor.redact(exc)}")
        return 1
    emit(f"receipt: {arguments.artifact}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
