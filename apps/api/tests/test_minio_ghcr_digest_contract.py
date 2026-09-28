from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
EXPECTED_IMAGE = (
    "ghcr.io/npd-ai/npd-minio@"
    "sha256:d37f79cb57ba531f92eeaf2a1a0e5f827dea982a429bb5a2903043c57ed04528"
)


def _compose_source() -> str:
    return (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def _minio_block() -> str:
    return _compose_source().split("\n  minio:\n", 1)[1].split("\n  migrate:\n", 1)[0]


def test_minio_reference_is_the_verified_immutable_ghcr_digest() -> None:
    block = _minio_block()
    assert f"    image: {EXPECTED_IMAGE}\n" in block
    assert "quay.io/minio/minio" not in _compose_source()
    assert ":latest" not in block
    assert "ghcr.io/npd-ai/npd-minio:" not in block
    assert "minio/minio:RELEASE" not in block


@pytest.mark.parametrize(
    "contract_line",
    [
        '    command: ["server", "/data", "--console-address", ":9001"]',
        "      - minio-data:/data",
        '      test: ["CMD-SHELL", "curl -fsS http://localhost:9000/minio/health/live >/dev/null"]',
        "      interval: 5s",
        "      timeout: 3s",
        "      retries: 20",
    ],
)
def test_minio_consumed_runtime_contract_is_preserved(contract_line: str) -> None:
    assert contract_line in _minio_block()


def test_production_overlay_does_not_override_image_or_storage_semantics() -> None:
    source = (
        ROOT / "deploy/production/docker-compose.production.yml"
    ).read_text(encoding="utf-8")
    block = source.split("\n  minio:\n", 1)[1].split("\n  migrate:\n", 1)[0]
    assert "networks: [video-factory-v2]" in block
    assert "image:" not in block
    assert "volumes:" not in block
    assert "command:" not in block
