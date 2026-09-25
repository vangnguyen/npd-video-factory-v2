# VF-EXECUTOR-02 — remediation checkpoint

Status: **BLOCKED; NOT QUALIFIED; no O1 or O2 requested**. PR #90 remains
Draft. This review supersedes the VF-EXECUTOR-01 current checkpoint, preserving
its history. Source/test evidence is not actual execution-host qualification.

## E0: actual host RCA

Runner 21, `npd-vf-vangnguyen-ubuntu`, is scoped to
`vangnguyen/npd-video-factory-v2`, pool Default. GitHub reports offline/not busy.
Labels: self-hosted, Linux, X64, npd-video-factory, provider-execution.
Host VANGNGUYEN runs Ubuntu WSL2, kernel 6.6.87.2-microsoft-standard-WSL2,
PID 1 systemd. Installation `/var/lib/npd-vf-runner/runner`, work directory
`_work`, user `vf-executor` (uid 997), runner version 2.337.0.

There is no `.service` binding, runner systemd unit, listener, worker or Worker
diagnostic log. Consequently no runner service journal exists. Safe Runner log
metadata and installation inventory are in
`evidence/v3-01/vf-executor-02-host-rca/`. Offline cause: A (listener absent)
and G (deliberate local quarantine), not demonstrated registration/network failure.

Quarantine is project policy: provisioning deliberately omitted service startup,
the root-owned workflow allowlist is empty, and runtime/config/catalog/custody
grants are absent. It is not a GitHub-native status. The supported runner
`config.sh --check --url` diagnostic passed Internet, Actions, Git TLS/proxy and
Node TLS/proxy checks. A GitHub administrative token was handled only in memory;
raw diagnostics remain private. No TLS bypass was enabled.

Clear only after independently enforced job admission passes hostile workflow,
PR, `always()` and admission-launch-failure tests, policy is pinned to the exact
qualified tree, and resource grants are reviewed. Labels and pre-job hooks do
not satisfy this condition. See [security analysis](SECURITY_DESIGN.md).
Supported organization workflow restrictions require an Owner topology/scope
decision; no repository transfer or organization permission expansion occurred.
A custom maintained runner admission implementation remains a separate possible
engineering route, not an implemented or qualified control.

## E1: MinIO RCA

The accepted image is unchanged:
`quay.io/minio/minio@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`
(RELEASE.2025-09-07T16-13-09Z). The original failing CI run 36155628327,
job 108139352406, returned unauthorized pulling this image before startup.
Fresh anonymous and bearer requests to Quay return 401; Docker Hub same-digest
access also returns 401 and the release tag returns 404. Historical accepted
Quay verification is preserved; no floating Docker Hub rollback/version upgrade
was made. See `evidence/v3-01/vf-executor-02-minio-rca/rca.json` for inventory,
history and exact results. Image-contract tests pass, but cannot prove a pull.

Local Docker Desktop also cannot start because its `sailor-ingest.sock` reparse
point cannot be renamed (Windows error 1920). Supported bounded restart failed;
no volume deletion/factory reset was attempted. Pull/start/health/CRUD/persistence
and Docker E2E remain blocked. Restored registry access or an approved immutable
same-release mirror is required; no usable registry credential source was found.

## E2–E4: source remediation and remaining prerequisites

The host adapter now invokes existing `validate_single_dispatch` and
`run_single_dispatch`; it contains no competing provider transport. It uses a
fixed root-owned catalog, exact structured request binding, immutable source,
nonblocking host lock through cleanup, independent qualification promotion,
ordered canonical transitions, one credential resolution, and terminal evidence.
The canonical runner arms evidence before credentials/reservation, checks final
authority/time, and retains uncertain outcomes for review. Reservation-acknowledgment
failure gets one custody read and release only when safe, never a reserve retry.
Post-dispatch cleanup failures preserve actual outcome rather than reporting zero.

Qualification now loads a valid, expired, explicitly synthetic RC999999 fixture
and checks cleanup, re-reads custody to prove no observed ledger change, and binds
a versioned executor tree including **all** workflow files. Historical RC hashing
is unchanged. The negative check-only probe proves fail-closed behavior, not
readiness of a real operation. Real PG custody is never replaced with fixture PG.

No host runtime/catalog was deployed or enabled. Canonical PG/socket/database/
namespace, durable evidence root and approved secret reference remain unbound.
No production credential plaintext was read. Provisioning kill switch is ENGAGED;
this is not E10 proof for a bound live runtime. E1–E10 are NOT RUN because E0/E2
prerequisites are not met. No qualification workflow was dispatched.

## Promotion contract

`execution-catalog.json` is fixed at `/etc/npd-video-factory/` and disabled unless
`version=1` and `dispatch_enabled=true`. A future approved catalog must contain
`qualification_receipt`, its SHA-256, and exact allowlisted operation entries
(`request`, canonical `paths`, `runtime_policy`, `runtime_policy_sha256`). It is
deployment policy, never Owner authority. RC22 remains explicitly rejected.

The separate root-owned promotion receipt must bind source commit, runner ID/name,
executor tree, all gates and zero invariants; raw `probe_receipt`/SHA,
`probe_manifest`/SHA and `security_review`/SHA are independently verified. The
raw report stays `CAPABILITY_PROBES_PASS` with `execution_plane_qualified=false`.
Security review must bind the same tree and contain all hostile-job PASS results
and `CLEARED_BY_VALIDATED_POLICY`. Root ownership includes nonwritable ancestors.
No such promotion receipt or security PASS artifact was fabricated here.

## Lifecycle after validated admission only

Current safe state is stopped/uninstalled service. Once admission is validated,
install using the distribution's supported `sudo ./svc.sh install vf-executor`
from the runner install directory; record the generated `.service` unit. Use
`sudo ./svc.sh start`, `status`, `stop` and stop/start for recovery. Inspect that
exact unit with systemctl/journalctl, listener status, and GitHub idle/not-busy
status. These service commands were **not executed** during this checkpoint.

After Windows reboot, WSL must be launched before a Linux service can run. Any
Windows scheduled startup under the distro owner must launch the named Ubuntu
distro, retain the admission guard, and verify idle status; it is not configured
while quarantined. After WSL restart, verify systemd, service binding, pinned
policy and no active dispatch before recovery. Never kill an in-flight dispatch
as a health-check action. Evidence root is pending binding, not a guessed path.

## Acceptance boundary

Full source regression and exact candidate CI are recorded in the handoff. Live
security and MinIO/CI failures block G-08 and O1 even if offline tests pass.
No executable-changing merge is authorized. No O2 window is requested.
Provider calls, reservations, consumption, business writes and provider cost
remain zero. Existing RC22 tag/window/Operation 1 are untouched.
