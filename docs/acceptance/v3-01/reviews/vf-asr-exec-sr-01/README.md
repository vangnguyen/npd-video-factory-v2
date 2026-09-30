# VF-ASR-EXEC-SR-01 — execution activation remediation

Status: source candidate and synthetic host qualification only. This document
is not O1, O2, a provider authority receipt, or an execution window.

RC-23 execution is `CANCELLED_NO_DISPATCH`. Its approvals, scope, bundle, and
Operation-1 authority remain immutable historical RC-23 evidence and are not
inputs that can be transferred to a later RC. Operation 1 remains unconsumed;
Operation 2 remains locked.

## Security architecture

- `RuntimeActivationBinding` is a strict, separately hashed host artifact. It
  binds canonical custody, the exact operation and authority, exact O2 receipt
  and window, execution-plane promotion, source and executor-tree identities,
  PostgreSQL peer mapping, and mandatory `LOGIN` → `NOLOGIN` lifecycle. It is
  neither `CustodyBinding` nor provider authority.
- `npd-vf-secret-resolver.socket` admits only the exact `vf-executor` UID/GID
  over the canonical root-controlled AF_UNIX socket. The root service obtains
  only `openai-codex-video` through `LoadCredentialEncrypted=` and accepts no
  caller-selected credential name, path, or command.
- Every resolver request binds the canonical alias, exact operation, authority
  receipt, final bundle, execution scope, execution-plane promotion, and O2
  activation receipt. A root-owned `O_EXCL` spent marker makes the handoff
  one-shot across process or service restarts.
- The execution workflow invokes a fixed root wrapper. The wrapper always
  restores the PostgreSQL role to `NOLOGIN`; a persistent systemd timer is an
  independent crash/expiry failsafe.
- PostgreSQL remains Unix-socket only. The exact peer map is
  `vf-executor` → `vf_executor_runtime`; wildcard mapping, `trust`, password
  authentication, and TCP are prohibited.
- Git trusts only `/opt/npd-video-factory/runtime/source` through a persistent
  system-level `safe.directory` entry. Runtime code no longer injects a
  per-process trust override.

## Runtime order

The source enforces host admission, source identity, qualification, bundle and
authority, O2, runtime activation, runtime peer/role security, ledger preflight,
and durable evidence before the privileged secret handoff. Reservation and the
final time check remain after that single handoff; provider transport remains
last. A `NOLOGIN` role, an overprivileged role, a missing/mismatched activation,
or resolver mismatch therefore stops before any credential read.

## Non-authority invariants

This remediation creates no RC, O2, operation authority, execution catalog
entry, reservation, provider receipt, or business write. Real provider calls,
real provider credential reads, budget reserved, operation consumption, and
actual cost must remain zero throughout source and host qualification.
