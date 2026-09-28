# VF-EXECUTOR-01 — quarantined runner and zero-call source candidate

Status: **INCOMPLETE / NOT QUALIFIED / DRAFT / NO O2 REQUEST**.
Base main: `7c023307d6a1e56a732a6ca96235a7ab3b32a253`.
Branch: `codex/vf-executor-01`. This changes executable source and scripts;
it must not merge automatically. RC-22 and its closed window are unchanged.

## Actual host inventory and provisioning

| Field | Observed or configured value |
|---|---|
| Windows host | `VANGNGUYEN` |
| WSL distro | `Ubuntu`, WSL version 2 |
| GitHub repository | `vangnguyen/npd-video-factory-v2`, public, personal account |
| Registered runner | `npd-vf-vangnguyen-ubuntu`, runner ID `21` |
| GitHub observed labels | `self-hosted`, `Linux`, `X64`, `npd-video-factory`, `provider-execution` |
| Runner version | `2.337.0`, official Linux x64 archive |
| Archive SHA-256 | `70920811a4f8ad4328818682bca5c6469c1c942fab52448868071d0063816613` |
| Linux user | `vf-executor`, system account, nologin shell, no sudo grant |
| Installation / work | `/var/lib/npd-vf-runner/runner`, work `_work` below it |
| Service | **NOT INSTALLED / NOT STARTED** |
| Runner state | **OFFLINE / QUARANTINED**, `busy=false` on GitHub readback |
| Admission allowlist | `/etc/npd-video-factory/workflow-allowlist.json`, empty |
| Admission hook | root-owned `job-started.sh` invokes isolated `/usr/bin/python3` and `job-started.py` |
| Provisioning kill switch | `/etc/npd-video-factory/kill-switch`, `ENGAGED`; not yet attested as canonical runtime switch |
| Canonical evidence root | **NOT BOUND / NOT ACCESSED** |
| Canonical PostgreSQL custody | **NOT BOUND / NOT ACCESSED** |
| Approved provider secret source | **NOT BOUND / NOT ACCESSED** |

The registration token was transferred in memory to runner configuration,
never printed or committed. Provider credential reads were zero. The phrase
"zero credential reads" must not be used to hide the short-lived GitHub
registration-token exchange. Runner authentication files remain private in
the Linux runner home; no credential file is attached to this review.

The provisioning script refuses an existing installation instead of replacing
its identity. No runtime, evidence root, canonical custody, provider secret,
budget reservation or operation was created by provisioning. In particular,
it did not migrate or change ownership of the historical RC-20 custody found
in earlier documentation.

## Restart and startup procedure

At this checkpoint, a Windows/WSL restart leaves this runner offline because
no service or startup task was installed. **Do not run `run.sh`, install/start
`svc.sh`, or enable a WSL startup task yet.**

Before startup, finish the security boundary below, bind the approved existing
custody/evidence/secret references, install the reviewed immutable runtime at
`/opt/npd-video-factory/runtime/source` and its root-owned venv/launchers, and
install `/etc/npd-video-factory/executor.json`. The dataclass `Host` defines
its non-secret keys; it contains paths and hashes, never credential values.
The host must pin the installed source commit separately from the approved
workflow commits. Empty workflow allowlists deny all work.

Only after those checks and the applicable source review may an administrator
install a service with the explicit `vf-executor` account and root-owned
admission configuration, verify it cannot bypass admission, and record its
exact unit name plus stop/start/status procedure. That procedure is deliberately
not presented as already installed. O1 is still mandatory before source merge.

## Qualification semantics

`video-factory-executor-qualification.yml` is manual, main-only, no O2 input,
no checkout or package installation, and calls an installed host launcher.
The provider workflow uses the same labels and concurrency group, with
`cancel-in-progress: false`. A queued job is blocked, not cancelled into an
overlapping dispatch. The qualification process also takes a nonblocking
Linux `flock`, without unlinking the lock inode on release.

| Gate | Implemented candidate probe | Actual-host result |
|---|---|---|
| E1 | exclusive private file, write/flush/fsync, directory fsync, isolated child read/hash; sealed manifest | NOT TESTED |
| E2 | WSL kernel/distro, Python >=3.12, runner/repo/ref, pinned clean source, Unix socket connection | NOT TESTED |
| E3 | pinned binding and socket custody, canonical `read_custody`, read-only transaction, PG identity/migration | NOT TESTED |
| E4 | canonical operation/attempt/reservation/idempotency reads plus dispatch-marker/receipt column access | NOT TESTED |
| E5 | fresh fixed-repository `git ls-remote` over HTTPS, no mutation | NOT TESTED |
| E6 | fixed `api.openai.com:443` TLS handshake; zero HTTP/model requests | NOT TESTED |
| E7 | secret reference ownership/permissions/nonempty/read-access metadata only; no plaintext open | NOT TESTED |
| E8 | read-only custody plus reservation/reconciliation table privilege checks; no reserve call | NOT TESTED |
| E9 | temporary private staged fixture, canonical loader rejects non-authority, automatic cleanup | NOT TESTED; rejection-only probe |
| E10 | root-owned engaged switch, canonical `validate_single_dispatch` on an absent fixture, evidence sealing | NOT TESTED; fail-closed entrypoint probe only |

E8 is access verification, not a successful live reservation/reconciliation.
E9 proves file staging and cleanup, **not a privileged OS bind mount or a
successful valid-bundle load**. E10 proves the canonical negative check-only
entrypoint; it does not attest a particular operation's readiness. These
limitations must not be presented as full dispatch qualification.

Even if every probe passes later, this candidate emits
`CAPABILITY_PROBES_PASS`, not `SELF_HOSTED_EXECUTION_PLANE = QUALIFIED`:
security review and full dispatch integration remain independent requirements.
No qualification workflow has run on runner 21. Source/mock test results are
not a substitute. Canonical durable qualification evidence does not exist.

## Execution contract and remaining implementation

The structured request allowlist contains exactly operation ID, bundle ID,
bundle SHA, loaded-scope SHA, authority SHA, RC tag/commit, governance-main SHA
and ASR capability. Bundle IDs cannot be paths. Invalid fields, RC-22, and even
otherwise well-shaped requests always produce `BLOCKED_PRE_CALL` under an
unconditional source latch. No variable, user input or stored authority receipt
can enable dispatch in this candidate. Inputs are never echoed.

This is **not yet the requested full execution workflow**. The candidate does
not call `run_single_dispatch`, does not mount an active bundle, reserve budget,
consume an operation or infer authority from CI/main/tag. It uses the existing
`validate_single_dispatch` for the negative qualification probe. No competing
transport/dispatch engine has been added.

Before the full execution contract can pass, implement and review the host
allowlisted package binding, fresh provenance/O2 checks and these transitions
through the canonical `run_single_dispatch` contract:

`INIT -> ENVIRONMENT_PREFLIGHT -> BINDING_PREFLIGHT -> LEDGER_PREFLIGHT ->
BUNDLE_VALIDATED -> EVIDENCE_ARMED -> SECRET_AVAILABLE -> BUDGET_RESERVED ->
FINAL_TIME_CHECK -> READY_TO_DISPATCH -> SINGLE_DISPATCH -> TERMINAL_EVIDENCE`.

The current canonical implementation resolves credentials before reservation
and arms evidence after reservation; failures before its internal protocol do
not all seal a terminal receipt. Those differences need explicit remediation,
including cancellation/crash cleanup, reservation release when appropriate,
kill-switch engagement, bundle cleanup, sealing and ambiguous-ledger handling.
Never blindly release a reservation whose provider transport state is unknown.
The wrapper must not add retries around the canonical single-dispatch call.

Attempts=1, concurrency=1, retry=0 and fallback=0 remain required. Existing
canonical tests cover authority/scope, stale/consumed operations, receipt and
reservation collisions. They are retained, not replaced with a second engine.

The old GitHub-hosted paid smoke workflow is disabled **in this candidate**.
Main and historical refs remain unchanged until the required governed merge;
do not claim that every remote legacy route has already been removed.

## Threat model and security review

An attacker may submit PRs, alter workflow files/inputs, request runner labels,
or attempt to reuse an old authority. Labels are routing, not authorization.
The public personal repository currently allows all Actions. A repository-scoped
runner prevents other repositories from scheduling it, but does not by itself
prevent untrusted PR jobs within this repository.

Main-only manual workflow checks, immutable host code, no checkout, strict
input parsing and root-owned admission hooks are defense in depth. The runner
home is runner-owned; a root-owned `.env` file alone is not a tamper-proof
boundary because its parent directory is writable. Job-hook context and
container/service setup ordering have not been penetration-tested on this host.
**Runner security PASS is therefore withheld, and the service stays offline.**

A deployable boundary needs independently enforced workflow restrictions
(for example an eligible organization runner group restricted to the exact
approved workflow/ref), or a reviewed broker/service sandbox that prevents
arbitrary runner jobs from accessing custody, secrets, evidence and outbound
provider transport. Moving repository ownership/visibility is not performed
implicitly. Repository/environment secret inventory and provider egress policy
also need verification without exposing values. No provider secret is installed
in this runner while these requirements remain open.

References: [GitHub runner access groups](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/manage-access)
and [GitHub job hooks](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/run-scripts).

## Next safe action

Review the Draft PR as an incomplete, zero-call foundation. Resolve the runner
security boundary and approved host references; complete dispatch integration
and technical G-08 before claiming candidate readiness. Stop at Mandatory Owner
Gate O1 before any executable merge. No new O2 window, no RC-22 mutation and
no Operation 1 test dispatch. Other lanes may continue offline source work;
no other executable-changing lane is merged by this task.
