# VF-SECRET-01 systemd encrypted credential evidence

Current source-side verdict: `PENDING_EXACT_HEAD_CI_AND_LIVE_QUALIFICATION`.

- Source PR: `#93`; not merged; no O1 or O2.
- systemd: `255 (255.4-1ubuntu8.17)` on Ubuntu 24.04 WSL2.
- Host key: present at `/var/lib/systemd/credential.secret`, `root:root`, mode
  `0400`; bytes were never printed, copied, hashed into evidence, or read by
  Video Factory.
- Encrypted source: present at
  `/etc/credstore.encrypted/openai-codex-video`, `root:root`, mode `0400`.
- Credential store directory: `root:root`, mode `0711`; the runner may stat the
  canonical known path but cannot list the directory or read/write the source.
- Binding: `/etc/npd-video-factory/provider-secret-binding.json`, state
  `BOUND_ENCRYPTED_SOURCE_PRESENT`.
- Binding SHA-256:
  `2e4f44e01b98b37ad81501000bbc5606a9efc70cf5ac0200e9fc9365f9647175`.
- Synthetic backend receipt SHA-256:
  `cef23840aee9a680730d4479f065166facdfd7fea7b3762149a44e2e4bbed73b`.
- Synthetic test: encrypt PASS; exact name binding PASS; controlled systemd
  service delivery PASS; access isolation PASS; cleanup PASS.
- Actual provider credential decrypted/read by Video Factory: 0.
- Provider calls: 0; budget reserved: 0 VND; operation consumption: 0;
  actual cost: 0 VND; production writes: 0; RC-22 mutation: none.

The source contract validates the host-key and encrypted-source metadata plus
the sealed synthetic receipt. Qualification never executes `systemd-creds
decrypt`, opens the encrypted provider source, starts a provider resolver, or
invokes a provider SDK. Promotion independently binds the exact secret-binding
SHA from E7 alongside runner identity, executable tree, custody binding,
hostile-job security evidence, kill switch, and zero invariants.
