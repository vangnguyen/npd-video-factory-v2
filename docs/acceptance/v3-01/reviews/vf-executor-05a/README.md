# VF-EXECUTOR-05A — runner identity source remediation

Status: **SOURCE_READY_FOR_LIVE_QUALIFICATION; live qualification not run; no
merge, O1 or O2 authorized**. Draft PR #91 is the candidate. Its pre-remediation
head is `e607463060c062b512bf43ac2b32ea3443b18045`. The final candidate head,
executor executable-tree SHA-256 and exact-head CI receipt are intentionally
recorded in the external final handoff after those values exist.

## Scope and trust root

This remediation removes hard-coded runner ID 21 from the executor
qualification/runtime trust contract. It does not replace that value with
hard-coded runner ID 6. Runtime identity is rooted in the immutable,
root-owned host configuration at `/etc/npd-video-factory/executor.json`; the
execution catalog refers to a separately hash-pinned, root-owned qualification
promotion. Root-ownership and non-writability checks remain mandatory for the
configuration, catalog, promotion and their ancestors.

The canonical runner identity has exactly these fields:

- `runner_id`
- `runner_name`
- `execution_organization`
- `runner_group`
- `execution_repository`
- `source_commit`
- `executor_executable_tree_sha256`

Missing, extra, wrong-typed or unequal fields fail closed. The deployment
binding expected for the later live qualification is runner ID 6,
`npd-vf-executor-ubuntu-02`, organization `npd-ai`, group
`vf-provider-execution`, and repository
`npd-ai/npd-video-factory-executor`. ID 6 appears here as a deployment
expectation and in test fixtures; it is not a production runtime constant.

At runtime, the trusted host binding remains authoritative. System runner name
and GitHub organization/repository context must match it. A workflow request
cannot select a runner: any caller-supplied canonical identity field or
`runner_identity` object is rejected before exact approved-request binding.

## Promotion convergence

The qualification promotion, raw `probe_receipt` and independent
`security_review` must each carry the same exact canonical `runner_identity`
object as the root-owned host binding. The promotion continues to require all
E1–E10 gates PASS, zero invariants, engaged kill switch, and hash-pinned probe,
manifest and security artifacts. The raw probe remains
`CAPABILITY_PROBES_PASS` with `execution_plane_qualified=false`; it cannot
promote itself. The security review still requires validated quarantine
clearance and every hostile-job result PASS.

This identity convergence prevents a valid receipt for one runner, source or
executable tree from authorizing another runner. It does not weaken the existing
catalog, request, authority, ledger, locking, credential, reservation,
single-dispatch or cleanup gates.

## Required negative source evidence

The source test matrix proves fail-closed rejection of:

- legacy runner ID 21 when the trusted binding expects another runner;
- a wrong runner name;
- missing or partial runner identity;
- caller-supplied runner identity input;
- a qualification promotion for a different runner;
- a probe receipt for a different runner;
- a security review for a different runner;
- an executor executable-tree mismatch.

Existing hostile request, receipt hash, gate, zero-invariant, kill-switch,
manifest, quarantine and hostile-job tests remain in force. Final executor test,
full-regression, secret-scan, diff-check and true exact-head CI results are
reported in the external final handoff so they bind the actual final PR head.

## Source provenance boundary

The source-side G-08 result is documented in
[G08_SOURCE_REVIEW.md](G08_SOURCE_REVIEW.md). It reviews the bounded identity
contract only. The final handoff must establish
`EXPECTED_HEAD_SHA == CHECKED_OUT_SHA` for the true PR head; the normal PR
merge-ref run is not exact-head evidence. The final new head, executable-tree
SHA-256 and CI run ID are pending until the candidate is committed and the
workflow completes, and are therefore not guessed in this source document.

## Preserved live boundary

Runner `npd-vf-executor-ubuntu-02` (ID 6) remains OFFLINE, its listener STOPPED,
service NOT_INSTALLED, kill switch ENGAGED and live allowlist EMPTY. This task
does not install an executor runtime into `/opt`, write live host configuration
or promotion evidence, start a runner, dispatch a self-hosted workflow, bind or
read a provider credential, reserve budget, consume an operation, call a
provider, mutate RC-22, request O1/O2 or merge PR #91.

Provider calls, credential reads, budget reserved, operation consumption and
actual cost remain zero. The next safe action is separately authorized live
qualification of the already-bound runner after Owner review; source readiness
is not live runner readiness.
