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

For a future `BOUND_SOURCE_INSTALLED` artifact, qualification permits only
`ROOT_FILE` or `SYSTEMD_CREDENTIAL_ENCRYPTED`. It verifies the source by path,
regular-file type, symlink rejection, root ownership, exact `0400` mode, and
non-zero size. It does not open or read source bytes. The executor also no
longer reads a path directly: provider execution remains blocked until a
separately approved privileged resolver is installed.

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

Recommendation: use `systemd` `LoadCredentialEncrypted=` backed by the systemd
host key, with a root-owned one-shot/daemon resolver, because systemd is already
the active init on this WSL host and can scope decrypted plaintext to the
resolver service. Do not create the host key, encrypted credential, resolver,
or provider credential during VF-EXECUTOR-05C.

Current invariants remain provider calls 0, credential reads 0, budget reserved
0 VND, operation consumption 0, actual cost 0 VND, RC-22 mutation none, O1 no,
O2 no, runner Offline/Safe, and kill switch engaged.
