# VF-V0S-B16R — historical pre-merge RC-20 authority binding, no execution

The explicit Owner VF-V0S-B16 decision approved G-01/G-02/G-03 for **only**
the RC-20 ASR W1 Operation 1 identified by the B15 preparation package. This
directory preserves pre-merge approval and bundle evidence; it is not a
post-merge execution mount or live authority. The clean branch
starts directly from governance main `4ac4880d5627c2800eb918d24c59da5f8e047091`
and ports B15 preparation and B16 evidence without changing executable source.
Draft PRs #78, #79 and #80 remain historical and unmerged.

## Binding and hashes

- Governance main: `4ac4880d5627c2800eb918d24c59da5f8e047091`, exact-main CI `35172654970` PASS 5/5.
- RC: `vf-v3-01-rc20` → `93b5441d44347c9c40b745bdfed0969880853f68`, RC CI `35124578033` PASS 5/5.
- Executable tree: `611450db8b70b67c39090dc245a86465cc9a5bdb542f732b9bde0c7e289e1630` on both main and RC.
- Dual-CI provenance: `PASS`, SHA-256 `5caca534d1cfa6a4e3d9b4f9f9b6b1c33b024ec65afdfc36cf875c673bc1eb86`.
- Canonical ledger: `vf_vf_v3_01_rc20_5ff19bf478b41d3580e486bb6e37279d`, PostgreSQL 16.15, system ID `7686186223531422166`, migration `0015_v3_01_dispatch`.
- Operation 1/key: `v3-01-rc20-openai-transcription-asr-al-0001-9722891b4ae68168375adea9fc53cc6ad89c20fa8f3c5d8535f056173f428624-call-01`.
- Execution scope: `cc68432affb13d290860cb7ca71feb3efb46f0e82541c6d0d2a54fff60d00093`.
- B15 prepared scope: `667c88a949feec343e6b37934ba4705edbb0c616ba92217124227045ad5a4be4`.
- B15 operation manifest: `a16fb870af5572e57081a3de7f8d90c789393445efa5dcaa5186bc562b13d4d2`.
- B15 preparation template raw hash: `6c3efc700df2c3c2163c0ff9f7ea8f71af728e5f1eec5b1c55c1ef92301057c0`.

The three fresh records are [G-01](../../approvals/V3-01-APP-078.json)
`600d8f11333a012fe2b301c3ed4ba9e9359655c35de73c7711a6acb83da7f2bd`,
[G-02](../../approvals/V3-01-APP-079.json)
`5dce4a03aee485212a2b30558d4704d497d16aa48eff2e762bfe0ba18bfa58a0`,
and [G-03](../../approvals/V3-01-APP-080.json)
`063fcb3c1af4e0801c7cd055765fea38549163e95fd3848897b5e4e3ecb768e4`.
G-03 binds both RightsRecords because the established loader requires two
slots, but only slot 1 has authority; slot 2 remains locked.

The [final bundle](final-runtime-bundle.json) raw SHA-256 remains
`a98a78884d020138c858b608b5462df5a762ebcac9024ce0ff6257e1bdd10019`.
Its [loaded scope](final-loaded-scope.json) likewise remains at canonical SHA-256
`2e049bfe8b2dede3ca8cb3ffdb27fd95bc96dd1d72c8e18cb4dca1788282b5de`.
The [corrected Op1-only authority](operation-1-authority.json) raw receipt SHA-256 is
`074c91cf7efff23bd7763bb698905dfe8de9e0d50ed72dea358354a4930e8dce`,
recorded status `GRANTED_NOT_CONSUMED` only for pre-merge main `4ac4880d...`.
After PR #81 governance merge this receipt is
`HISTORICAL_PRE_MERGE_BINDING / INVALID_AFTER_GOVERNANCE_MERGE`, not executable
authority for the new main. The B16 historical receipt has the same
post-merge classification. Final execution authority for the new main is
`NOT_CREATED` until a separate G2 review/materialization.
The historical B16 receipt `694693ca50001c93d5264418661bc8a25179a3791d6437e077f67653c2a3140c`
is preserved by Draft PR #80, not silently represented as this candidate's receipt.
A [B17 binding candidate](bootstrap-binding-for-b17.json)
is schema-valid under Linux but has **not** been used to run bootstrap. The
[hash manifest](final-material-hashes.json) binds all key identities. Raw
file hashes are in [SHA256SUMS.txt](SHA256SUMS.txt).

The strict loader schema has no arbitrary main/provenance/ledger/operation
fields at the bundle top level. Those additional exact bindings live in the
approval records and authority receipt; no new runtime schema was invented.
The runner specifically reads `executable_rc_ci_run_id = 35124578033` and
`governance_main_ci_run_id = 35172654970` from the authority receipt. Both
canonical runs are 5/5 PASS and the exact [baseline provenance snapshot](../../reviews/vf-v0s-b16r/baseline-dual-ci-provenance.json)
hashes to `5caca534d1cfa6a4e3d9b4f9f9b6b1c33b024ec65afdfc36cf875c673bc1eb86`.
The three Owner records already bind this provenance SHA and exact main/RC;
their signed content does not change. The bundle/scope schema has no CI-run
fields, so adding the IDs there would be an unverified schema change.
No null approval slot or unbound extra field remains in the final bundle.

## Governance merge and new-authority boundary

The exact-current-main runner checks remote `main` against the binding before
custody access. A governance merge of this branch will necessarily advance
`main` away from `4ac4880d...`, and the exact-main CI/provenance run ID will
also change. Thus this corrected authority is only historical pre-merge
evidence after PR #81 merges; it **cannot be carried forward as execution
authority**. PR #81 is governance/handoff/evidence closure only, not
post-merge B17 readiness or dispatch authority. The runner requires both
`executable_rc_ci_run_id` and `governance_main_ci_run_id`; RC CI `35124578033`
remains stable, while the new governance-main CI run ID can only be known
after merge and exact-main CI. G2 must bind the new main, run and provenance
and obtain a fresh window authorization.
The existing runner exposes no side-effect-free top-level dispatch mode;
offline validation exercises the same authority loader, authority verifier
and provenance validator, not the dispatch function. A separately reviewed
post-merge authority-binding procedure is required before B17.

## Window, budget and safety

The approved exclusive window is `2026-09-21 21:00` → `2026-09-22 01:00`
ICT (`2026-09-21 14:00` → `18:00` UTC). One attempt and one concurrent call
are permitted in a later separately assigned execution task. Retry and
fallback are zero. Modeled cost is `326.3004 VND`; maximum reservation is
`500 VND` for this operation and total window exposure must stay at or below
`1,250 VND`. Timeouts are 90 seconds provider / 120 seconds controller.
This task made **no** reservation or provider call.

The private ledger was read back after materialization using the established
read-only RC-20 custody audit: all eight execution tables remain empty,
reserved VND is zero, no operation record, provider request receipt or
idempotency collision exists. RC-19 and RC-20 custody remain isolated. Kill
switch is engaged, bundle unmounted, Operation 1 unconsumed, Operation 2
locked. Credential reads, real provider calls, production business writes and
actual cost are all zero. Production remains `NO-GO`.

## Reproduction and validation

`materialize.py --check` independently rebuilds identical bytes twice,
checks the checked-in outputs, invokes the real gate loader, validates the
final loaded scope and uses the current single-dispatch authority loader,
verifier and dual-CI validator without entering dispatch. The historical B16
Linux evidence checked the Unix-socket binding schema; B16R's read-only
ledger query independently checked the exact custody identity. Negative
controls reject a changed G-02 ceiling,
consumed authority, Operation 2 authorization and a shifted window. The
focused gate/single-dispatch/W1/safety suite passed `141/141`; Linux bootstrap
tests passed `90/90`. The canonical RC-20 custody audit passed after artifact
creation. No bundle was mounted.

B15's own `prepare_materials.py --check` assumes `HEAD ==` the historical
governance main, so it does not run unmodified on this clean candidate branch.
This is a checker working-tree guard, not a hash mismatch: B16R
independently checked the exact B15 raw files, canonical scope/manifest
hashes, immutable inputs, remote main, RC tag, tree and provenance. B15
history was not changed.

Next safe action after G1 closure is a separate G2 final authority and window
rebinding decision. Do not infer permission to run B17, mount, inspect
credentials, reserve funds or call the provider from this package.
