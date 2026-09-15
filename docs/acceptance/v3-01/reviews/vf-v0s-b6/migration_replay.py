"""Disposable 0001..0014/base/0014 replay against the private RC-19 cluster."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import asyncpg


TEST_DATABASE = "vf_v0s_b6_replay_5a72b3be"
EXPECTED_HEAD = "0014_v3_01_27"


def migration_environment(socket: str, port: int, role: str) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DATABASE_URL", "PGPASSWORD", "PGPASSFILE"}
    }
    encoded_socket = quote(socket, safe="")
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "DATABASE_URL": (
                f"postgresql+asyncpg://{role}:@/{TEST_DATABASE}"
                f"?host={encoded_socket}&port={port}"
            ),
        }
    )
    return env


def alembic(rc_source: Path, env: dict[str, str], *arguments: str) -> None:
    result = subprocess.run(
        [sys.executable, "-B", "-m", "alembic", *arguments],
        cwd=rc_source / "apps/api",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("ISOLATED_MIGRATION_REPLAY_FAILED")


async def revision(socket: str, port: int, role: str) -> list[str]:
    connection = await asyncpg.connect(
        host=socket, port=port, user=role, database=TEST_DATABASE, password=""
    )
    try:
        exists = await connection.fetchval(
            "SELECT to_regclass('public.alembic_version') IS NOT NULL"
        )
        if not exists:
            return []
        return sorted(
            row["version_num"]
            for row in await connection.fetch("SELECT version_num FROM alembic_version")
        )
    finally:
        await connection.close()


async def replay(args: argparse.Namespace) -> dict[str, object]:
    admin = await asyncpg.connect(
        host=args.socket, port=args.port, user=args.role, database="postgres", password=""
    )
    created = False
    steps: list[dict[str, object]] = []
    try:
        exists = await admin.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=$1)", TEST_DATABASE
        )
        if exists:
            raise RuntimeError("ISOLATED_REPLAY_DATABASE_ALREADY_EXISTS")
        await admin.execute(f'CREATE DATABASE "{TEST_DATABASE}"')
        created = True
        env = migration_environment(args.socket, args.port, args.role)

        alembic(args.rc_source, env, "upgrade", "head")
        first = await revision(args.socket, args.port, args.role)
        assert first == [EXPECTED_HEAD]
        steps.append({"action": "upgrade_head", "revision": first})

        alembic(args.rc_source, env, "downgrade", "base")
        base = await revision(args.socket, args.port, args.role)
        assert base == []
        steps.append({"action": "downgrade_base", "revision": base})

        alembic(args.rc_source, env, "upgrade", "head")
        second = await revision(args.socket, args.port, args.role)
        assert second == [EXPECTED_HEAD]
        steps.append({"action": "upgrade_head_again", "revision": second})
    finally:
        if created:
            await admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=$1 AND pid <> pg_backend_pid()",
                TEST_DATABASE,
            )
            await admin.execute(f'DROP DATABASE "{TEST_DATABASE}"')
        await admin.close()

    return {
        "task_id": "VF-V0S-B6",
        "result": "PASS",
        "database": TEST_DATABASE,
        "scope": "DISPOSABLE_MIGRATION_REPLAY_ONLY",
        "steps": steps,
        "database_removed_after_test": True,
        "ledger_bootstrap_writes": [
            "TEMP_DATABASE_CREATE",
            "CANONICAL_MIGRATIONS_0001_TO_0014",
            "DOWNGRADE_BASE",
            "CANONICAL_MIGRATIONS_0001_TO_0014_REPLAY",
            "TEMP_DATABASE_DROP",
        ],
        "provider_credential_reads": 0,
        "real_provider_calls": 0,
        "budget_reserved_vnd": "0",
        "production_business_writes": 0,
        "actual_cost_vnd": "0",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rc-source", type=Path, required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(replay(args))
    rendered = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
