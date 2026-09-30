# VF-ASR-EXEC-FS-SR-02 — PostgreSQL expiry-failsafe remediation

Status: bounded source candidate plus synthetic host qualification. This
review is not O1, O2, provider authority, an execution catalog, or an execution
window.

The candidate starts from exact governance main
`0723211c67d08d5dc886bce74f7559b50efedc89`. RC-24 remains immutable and its
cancelled execution attempt remains `CANCELLED_NO_DISPATCH / HISTORICAL`.
Because this change modifies the executable tree, RC-24 cannot be reused for a
future provider dispatch and a fresh RC lifecycle is required after merge.

## Root cause and correction

The original persistent expiry unit ran as root and reused the normal host
activation entrypoint. That entrypoint invokes PostgreSQL commands through
`runuser -u postgres`; the qualified systemd sandbox blocks that nested UID
transition. Removing sandbox controls would weaken the execution plane.

The remediation instead separates two trust domains:

- The existing root wrapper retains governed activation and immediate cleanup.
- `runtime_role_failsafe.py` is a dedicated, PostgreSQL-user expiry backstop.
  The systemd unit runs it directly as `postgres:postgres`; it contains no
  nested `runuser`, `sudo`, or `su`, and it has no code path that grants LOGIN.

The backstop uses fixed Unix-socket coordinates, the fixed
`vf_executor_runtime` role, and four allowlisted SQL statements only: observe
role state, force NOLOGIN, terminate surviving runtime-role sessions, and
verify that no session remains. It accepts no connection or SQL input.

## Active marker custody

The root activation path writes
`/run/npd-video-factory/runtime-activation-active.json` atomically as
`root:postgres` mode `0640`. The parent remains root-owned and non-writable by
postgres. The marker contains only version, activation hash, fixed role,
`LOGIN` state, and timezone-aware expiry.

The PostgreSQL-user backstop validates the opened regular file against lstat,
rejects symlinks and substitution, requires the exact owner/group and safe
mode, forbids extra JSON fields, and validates the fixed role/state and hash.
For a LOGIN role, an expired, missing, corrupt, substituted, wrongly owned, or
writable marker always forces NOLOGIN and terminates surviving sessions. A
valid unexpired marker never extends its sealed expiry. NOLOGIN is always a
safe terminal state.

## Systemd isolation

The candidate retains `NoNewPrivileges`, `PrivateTmp`, `ProtectHome`,
`ProtectSystem=strict`, and `RestrictAddressFamilies=AF_UNIX`, and adds device,
kernel, control-group, SUID/SGID, personality, and W^X restrictions. Provider
credential stores, authority artifacts, the execution catalog, activation
authority, and resolver policy are explicitly inaccessible to the expiry
service.

## Synthetic host qualification

The exact candidate helper and unit were installed temporarily for an isolated
zero-call host test, then the pre-review live unit was restored because merge
approval has not been granted. Qualification proved:

- NOLOGIN baseline;
- valid in-window marker preserves LOGIN without extending the window;
- expired, missing, malformed, symlink, and writable markers force NOLOGIN;
- a live `vf_executor_runtime` database session is terminated;
- the persistent 15-second timer closes the role after synthetic expiry;
- final role NOLOGIN, zero runtime sessions, resolver inactive, catalog absent,
  and kill switch engaged.

The sealed host log SHA-256 is
`93a22c4017eb2ebbc6dfd64101b94c4143cbd3f5fe8f853864004f25348acc29`.
It contains no provider secret or credential-derived data.

## Zero-use boundary

Real provider calls, real provider credential reads, reservations, ledger
writes, operation consumption, and actual cost are all zero. No O2, authority,
catalog, RC tag, provider transport, or production business write is created.
