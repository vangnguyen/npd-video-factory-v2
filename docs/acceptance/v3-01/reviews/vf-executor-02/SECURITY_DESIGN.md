# VF-EXECUTOR-02 runner admission security review

Date: 2026-09-25. Read-only architecture review; no host change, provider call,
secret read, or runner startup performed by this review.

Decision: `RUNNER_SECURITY = BLOCKED`. Keep the listener stopped until an actual
admission boundary has been implemented and tested. An empty workflow allowlist
and a failed job-started hook are not sufficient authorization boundaries.

## Verified current topology

GitHub REST repository metadata returns `visibility=public`, `owner.type=User`,
`full_name=vangnguyen/npd-video-factory-v2`. This is a personal repository, not an
organization repository. Provisioning source registers a repository runner named
`npd-vf-vangnguyen-ubuntu`, user `vf-executor`, under
`/var/lib/npd-vf-runner/runner`, with runner version 2.337.0. The provisioning
script deliberately does not install/start a service. Its quarantine is a local
policy choice plus empty `/etc/npd-video-factory/workflow-allowlist.json`; it is
not a GitHub-native runner state. Live host status is recorded by track E0.

## Hook limitations

The upstream v2.337.0 [JobExtension source](https://github.com/actions/runner/blob/v2.337.0/src/Runner.Worker/JobExtension.cs#L270-L300)
prepares/downloads actions before adding the job-started hook as a pre-job step.
The hook precedes ordinary container startup, but this ordering does not make it
an admission controller. Do not claim it runs before all job preparation.

The upstream [StepsRunner source](https://github.com/actions/runner/blob/v2.337.0/src/Runner.Worker/StepsRunner.cs#L182-L255)
evaluates each remaining step condition even after a failed step updates job
status. A hostile workflow can use `if: always()` or `if: failure()` rather than
the default success condition. A hook returning 1 therefore cannot establish
that no subsequent untrusted job code runs. This is a source-derived finding,
not a malicious job tested against runner 21.

The [JobHookProvider](https://github.com/actions/runner/blob/v2.337.0/src/Runner.Worker/JobHookProvider.cs#L49-L78)
uses the worker's script handler. This is part of job execution, not a distinct
privileged admission service. Root-owned hook files help prevent modification;
they do not change the worker's scheduling semantics.

## Supported GitHub boundary

[Runner-group workflow restrictions](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/manage-access)
can restrict eligible repositories and selected workflows, including a ref.
These groups belong to organizations/enterprises; the current personal
repository runner does not supply that control. Labels select runners and are
not workflow authorization. A workflow's own `if` or manual-only trigger cannot
prevent another workflow from naming the same runner labels.

A supported group solution needs an explicitly selected organization topology
and permissions/plan that support the required workflow restriction. Transfer
of this repository or creating a separate execution repository changes ownership
or scope; this review does not authorize or perform either. Merely making the
repository private does not supply exact-workflow admission.

## Host-enforced alternative without repository transfer

A custom admission implementation is technically possible, but is NOT currently
implemented or qualified. It must reject a job before the worker performs job
initialization, action preparation, shell launch, or container setup. One design
is a maintained runner worker change around the authenticated job message,
before [JobRunner initializes the job extension](https://github.com/actions/runner/blob/v2.337.0/src/Runner.Worker/JobRunner.cs#L165-L188).
It must compare trusted server job identity plus independently resolved workflow
bytes against a root-owned exact-commit/plan allowlist, never caller-supplied
environment claims. Reject unknown fields/features, dynamic steps, unexpected
actions, containers/services, environment injection, stale commits, and any
non-manual event. On denial complete the job without executing any job steps,
including post/always steps. Failures/timeouts deny admission.

This approach introduces a maintained runner fork and update responsibility.
It needs reproducible builds, pinned provenance, root-owned immutable binaries,
safe update policy, complete hostile-plan tests, and an independent security
review. A wrapper that watches logs or asynchronously cancels an assigned job
is not equivalent: it races execution. A privilege-separated broker can protect
custody/secrets, but alone does not satisfy the stricter requirement that the
provider runner never execute untrusted PR code.

Replacing `Runner.Worker` with a proxy is also a custom runner integration, not
a supported stdin filter. The [Worker entry point](https://github.com/actions/runner/blob/v2.337.0/src/Runner.Worker/Worker.cs#L29-L103)
uses an internal process channel with two pipe handles and a serialized job
message. A proxy would need framing, first-message replay, cancellation,
termination, identity integrity, and secret-safe parsing. The source shown does
not independently verify a publicly signed job envelope at this boundary. Trust
would depend on the protected listener and IPC. No such proxy was implemented
or tested here, and automatic runner updates must not silently replace it.

### Bounded review of kill-on-denial hook

Synchronously killing the worker on denial can close the ordinary hook-return-1
path, but cannot handle failure to invoke the hook itself. JobHookProvider throws
on a missing hook file before executing it; interpreter/process-start errors can
also precede hook code. StepsRunner catches these as failed steps and retains
the conditional execution semantics described above. Kill logic inside the hook
therefore cannot establish fail-closed admission when the hook is unavailable.
SIGTERM is also cooperative; worker termination behavior would need validation.
Do not promote this proposal to a qualified boundary without an independent
guard for these failure paths.

The [ActionManager implementation](https://github.com/actions/runner/blob/v2.337.0/src/Runner.Worker/ActionManager.cs#L136-L169)
returns Docker build/pull work as deferred steps, which JobExtension queues after
the hook. No inline Docker build was found in preparation. Action preparation
does invoke host `tar` to extract action archives before the hook (line 1259),
and parses manifests. No direct workflow-environment injection into the hook
interpreter was confirmed in this bounded review. These distinctions avoid
incorrectly claiming that ordinary container code already executes pre-hook.

## Supported connectivity diagnostic

Version 2.337.0 [CommandSettings](https://github.com/actions/runner/blob/v2.337.0/src/Runner.Listener/CommandSettings.cs#L101-L128)
accepts `ACTIONS_RUNNER_INPUT_PAT`, masks it as a secret, and removes the input
environment variable. It can be supplied in memory to `config.sh --check --url`
without a token command-line argument. [Runner check handling](https://github.com/actions/runner/blob/v2.337.0/src/Runner.Listener/Runner.cs#L100-L136)
runs before configure/listen and reports each check separately. Its overall
return is zero even when an individual check fails: retain only safe per-check
PASS/FAIL fields, not exit status as proof. Do not publish raw diagnostic logs.

## Required threat tests and remaining boundaries

Before clearing quarantine, prove malicious PR and modified workflow denial
before any sentinel step or container executes, including `always()` and
post-action paths. Deny command/env injection, stale RC, altered authority,
unapproved executable hashes, and replay. Protect host policy and binaries from
the runner UID. Keep secrets and custody inaccessible until approved admission;
test exfiltration denial without using actual provider plaintext. Test global
nonblocking host lock contention across qualification/execution and require
`cancel-in-progress=false`. Concurrency YAML alone queues jobs and does not
prove host lock behavior. Separately validate canonical runtime O2 bindings;
admission is not provider authority.

No approved architecture decision, production secret binding, or qualification
PASS follows from this design document. A repository ownership/scope change
needs Owner direction. Continuing with a custom host admission implementation
does not intrinsically need new O2 authority, but cannot be labeled PASS merely
because a design exists. Do not request O1 while these technical blockers remain.
