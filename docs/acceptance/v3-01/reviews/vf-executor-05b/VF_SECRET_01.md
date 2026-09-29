# VF-SECRET-01 systemd encrypted credential evidence

Current source-side verdict: `PENDING_EXACT_HEAD_CI_AND_LIVE_QUALIFICATION`.

- Source PR: `#93`; not merged; no O1 or O2.
- systemd: `255 (255.4-1ubuntu8.17)` on Ubuntu 24.04 WSL2.
- Host key: present at `/var/lib/systemd/credential.secret`, `root:root`, mode
  `0400`; bytes were never printed, copied, hashed into evidence, or read by
  Video Factory.
- Encrypted source: present at
  `/etc/credstore.encrypted/openai-codex-video`, `root:root`, mode `0400`.
- Credential store directory: `root:root`, mode `0700`; the runner cannot list
  or traverse it and cannot read or modify the encrypted source.
- Binding: `/etc/npd-video-factory/provider-secret-binding.json`, state
  `BOUND_ENCRYPTED_SOURCE_PRESENT`.
- Binding SHA-256:
  `2167490e4dad139894985a62a453dab67e61732a6c4d45749685deace040257c`.
- Root-sealed backend receipt SHA-256:
  `4ecb5aff72799f1cea9254e1e6156eb5bebb756db4174a3b6a7aeb643a0622ec`.
- Synthetic test: encrypt PASS; exact name binding PASS; controlled systemd
  service delivery PASS; access isolation PASS; cleanup PASS.
- Actual provider credential decrypted/read by Video Factory: 0.
- Provider calls: 0; budget reserved: 0 VND; operation consumption: 0;
  actual cost: 0 VND; production writes: 0; RC-22 mutation: none.

Root validates the host-key and encrypted-source metadata, runner denial, and
synthetic mechanism test, then seals the strict receipt pinned by the binding.
The runner validates only that non-secret, root-owned receipt because it cannot
traverse the systemd credential store. Qualification never executes `systemd-creds
decrypt`, opens the encrypted provider source, starts a provider resolver, or
invokes a provider SDK. Promotion independently binds the exact secret-binding
SHA from E7 alongside runner identity, executable tree, custody binding,
hostile-job security evidence, kill switch, and zero invariants.
