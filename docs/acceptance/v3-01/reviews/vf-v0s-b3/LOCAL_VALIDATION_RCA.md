# Local validation environment RCA — VF-V0S-B3

No failed sweep is reclassified as a clean source sweep. Each result is retained
separately in [tests.json](../../../../../evidence/v3-01/vf-v0s-b3-20260914-bootstrap-candidate/tests.json).

## Full-suite / E2E interference

The post-hardening sweep returned 1047 PASS and 1 FAIL (257.01s):
`test_capabilities_report_no_agent_hub_or_publishing_runtime` observed
`agent_hub_bridge_enabled=True`. The unchanged E2E script writes a disposable
.env fixture containing `AGENT_HUB_BRIDGE_ENABLED=true` (line 125) and removes it
in its EXIT cleanup. The unchanged Settings contract reads .env by default.
The two validations had overlapped in the same task-only worktree. This explains
the exact observed flag; it is not a provider/bootstrap behavior regression.

After E2E teardown and verification that .env is absent, the identical failing
case plus all 90 bootstrap tests passed (91 PASS, 6.35s). A serial full sweep is
required and recorded separately; no E2E may write .env during that sweep.
Canonical CI jobs run in distinct checkouts/runners, so they do not share this file.
No safety config, test expectation, CI gate or workflow is weakened.

## Docker CLI / worktree metadata

The first E2E invocation selected Linux Docker without a Compose plugin and
failed before container creation: `unknown shorthand flag: 'p' in -p`.
The repository already supports DOCKER_BIN; the verified Docker Desktop CLI
with a new empty task-owned Docker config fixes the selection without registry
login or configuration changes. A subsequent full E2E reached MinIO/PostgreSQL
recovery and then hit the same Windows-absolute .git pointer in the DR drill.
The entire E2E was rerun with exact translated GIT_DIR/GIT_WORK_TREE and passed.
See [WSL Git RCA](WSL_GIT_RCA.md) for both original historical failures and native/
WSL 2/2 comparison. No historical validators or hash rules were altered.

That successful local E2E covers source commit a366409d27f7c98074861745e3398a9c6602ff40,
not the subsequent peer-password fallback hardening. Final candidate CI must
independently run the full E2E against the exact final PR head.

## Peer password fallback

Inspection of the installed asyncpg parser showed that password=None consults
PGPASSWORD/password-file custody even when a Unix socket is explicit. The final
bootstrap and isolated test helper pass password="" explicitly for peer auth.
The closed validation environment has no PG secret environment variables; a
metadata-only existence check confirmed the default password file is absent.
No password-file contents were read. A post-hardening actual read-only custody
check replaces the driver's password-file reader with a raising function and
still passes with zero lookups; see
[peer fallback proof](../../../../../evidence/v3-01/vf-v0s-b3-20260914-bootstrap-candidate/peer-password-fallback-proof.json).

All database writes remain isolated candidate/test metadata or fixture writes.
No provider credential, live reservation, production business write or provider call.
