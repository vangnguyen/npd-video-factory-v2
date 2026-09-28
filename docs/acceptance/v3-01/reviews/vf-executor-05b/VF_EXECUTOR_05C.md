# VF-EXECUTOR-05C secret binding decision evidence

Verdict: `PENDING_FINAL_EXACT_HEAD_CI`.

- Draft PR: `#93`.
- PR-opening head: `73ad828a53d5a1ddd651bb5d6e6583a4cebd3a1a`.
- PR-opening exact-head CI: `36438071556` — PASS.
- 05C executable source commit:
  `2a6ef461463d6a4a5815810774d0c64acd192f41`.
- 05C executor executable-tree SHA-256:
  `1e86f2da55d6bb7b675e0ab8699776c737ddaeb9d46c4e136f954b3485df8152`.
- Canonical binding path:
  `/etc/npd-video-factory/provider-secret-binding.json`.
- Credential alias: `secret://openai/codex-video`.
- Binding state: `UNBOUND_APPROVED_SLOT`.
- Secret source present: false.
- Expected E7: `BLOCKED_SECRET_SOURCE_NOT_INSTALLED`.
- Installed binding metadata SHA-256:
  `65bb34bced19acd9c9a97a5d9790ba384003cfc3290f66df88127a3556ab264c`.
- Installed metadata: `root:root`, mode `0644`, regular file, canonical path.
- Focused tests: `122 passed, 1 skipped`.
- Full regression: `1394 passed, 1 skipped`.
- Qualification promotion: not created.
- Runner 6: Offline/Safe; listener stopped; service not installed.
- Kill switch: engaged.

The 05C change separates binding-metadata presence from source presence and
credential reads. Qualification may parse the strict root-owned metadata and
stat a future source, but does not open that source. The production executor
does not directly read a configured file and remains blocked until an approved
privileged resolver is installed.

Zero invariants: provider calls 0, provider credential reads 0, budget reserved
0 VND, operation consumption 0, actual cost 0 VND, production business writes
0, RC-22 mutation none, O1 no, O2 no.
