# VF-EXECUTOR-05C non-plaintext provider-secret binding

Canonical host path:
`/etc/npd-video-factory/provider-secret-binding.json`.

The artifact is metadata, not a secret store. It binds the canonical logical
alias `secret://openai/codex-video` to a future root-controlled source while
keeping `authority_granted` false. Its strict schema rejects extra fields. It
must never contain an API key, token, derivative hash or fragment of secret
plaintext, environment value, encrypted credential bytes, O2, an operation ID,
an execution window, or provider-call authority.

The initial artifact is `UNBOUND_APPROVED_SLOT`, with `source_type` `UNBOUND`,
null `source_locator`, and `secret_source_present` false. Consequently E7 must
report `BLOCKED_SECRET_SOURCE_NOT_INSTALLED`; metadata presence alone is not
secret-source presence and cannot produce qualification promotion.

VF-SECRET-01 approves exactly one installed backend:
`SYSTEMD_ENCRYPTED_CREDENTIAL`, credential ID `openai-codex-video`, encrypted
source `/etc/credstore.encrypted/openai-codex-video`, and host-key encryption.
The bound state is `BOUND_ENCRYPTED_SOURCE_PRESENT`. Root verifies the source
by canonical path, regular-file type, symlink rejection, root ownership, exact
`0400` mode, and non-zero size. It verifies the host key by presence,
regular-file type, symlink rejection, root ownership, and exact `0400` mode.
It also proves the runner cannot read or modify either artifact and cannot
list or traverse the `root:root` mode `0700` credential store. No check opens
the encrypted provider source or host-key bytes.

E7 additionally requires a sealed, strict-schema synthetic backend receipt at
`/etc/npd-video-factory/systemd-credential-backend-qualification.json`. The
receipt proves the root-only source/key metadata checks, runner denials,
host-key encryption, exact name binding, delivery through
`LoadCredentialEncrypted=`, controlled-service receipt, access isolation, and
cleanup using non-provider synthetic content. The binding pins the receipt
SHA-256. The runner reads only this non-secret root-owned receipt. E7 reports
`PASS_SECRET_SOURCE_PRESENT_NOT_RESOLVED` only when the binding, source
metadata, host-key custody, runner isolation, and synthetic receipt all pass.

## Backend decision proposal

1. A root-owned local file plus a dedicated privileged resolver is simple and
   auditable. The resolver can keep the file `root:root` mode `0400` and return
   a credential only at the final provider boundary after all authority gates.
   Its main cost is implementing and securing the narrow resolver IPC.
2. `systemd` encrypted credentials are supported by the qualified WSL host
   (`systemd 255`, system manager running, `systemd-creds` available). They
   offer encrypted-at-rest storage and service-lifetime plaintext material.
   This host does not yet have `/var/lib/systemd/credential.secret`, and its
   TPM2 report is only partial, so enrollment and recovery behavior require a
   separate Owner-approved installation and restore exercise.

Approved implementation: `systemd` `LoadCredentialEncrypted=` backed by the
systemd host key. VF-SECRET-01 installs only the encrypted source; it does not
install or start a provider resolver. Recovery is host-loss rotation: revoke
or rotate the provider API key, create a new host key, then install a newly
encrypted credential. The host key is not copied off-host.

Current invariants remain provider calls 0, runtime credential reads 0, budget reserved
0 VND, operation consumption 0, actual cost 0 VND, RC-22 mutation none, O1 no,
O2 no, runner Offline/Safe, and kill switch engaged.
