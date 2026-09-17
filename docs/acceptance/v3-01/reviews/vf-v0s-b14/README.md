# VF-V0S-B14 — RC-20 durable ledger custody and bootstrap boundary

Verdict: **REVIEW_REQUIRED**. The fresh, lineage-specific RC-20 PostgreSQL
custody is verified and virgin. The real `python -m app.provider_runtime_bootstrap`
CLI cannot be invoked as an operation-bound bootstrap in this task: its existing
schema requires an operation key, authority receipt, bundle, execution-scope
and scope hashes, while B14 explicitly forbids creating Operation 1 and its
authority/bundle. No placeholder or RC-19 material was used to force PASS.

## Pre-write binding

- Governance main `551379a916b9b574288fda754c0732009d23d288` stayed exact.
- Annotated `vf-v3-01-rc20` tag object
  `9fe8d77a6c58a31beccf38bc2cc72b71a8dac240` peels to
  `93b5441d44347c9c40b745bdfed0969880853f68`.
- RC CI [35124578033](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/35124578033)
  and exact-main CI [35126544056](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/35126544056)
  each passed 5/5. The canonical dual-CI validator returned PASS, SHA-256
  `330006ae336f12a809a5d7611d250d5e096f8b44c74ab8a02187771cf238d21f`.
- RC/main executable-tree SHA-256:
  `611450db8b70b67c39090dc245a86465cc9a5bdb542f732b9bde0c7e289e1630`.
- The RC-20 source blobs of `provider_runtime_bootstrap.py` and
  `provider_single_dispatch.py` are respectively
  `ebcc65d1f23491a42d3894547a8fb1f16e6608d6` and
  `a61a035d7b8e60be61581ce5d9d59028e2715688`.
- The canonical first acceptance-lineage ID and database name re-derived
  exactly; see [baseline.json](baseline.json).

## Durable custody

The new PostgreSQL 16.15 cluster lives under
`/home/vang_nguyen/.local/share/npd-vf-rc20-ledger-9722891b4ae6` with
owner-only `0700` cluster/socket directories. It uses local Unix socket
`55440`, peer authentication, rejects host authentication, and has no TCP
listener. System identifier `7686186223531422166` differs from RC-19's
`7685665008963764889`. Its sole V3-01 RC database is
`vf_vf_v3_01_rc20_5ff19bf478b41d3580e486bb6e37279d`, schema `public`,
role `vang_nguyen`. RC-19 has a separate cluster, socket, system identifier
and database; no RC-19 database exists in the RC-20 cluster.

Canonical migrations `0001`–`0015` reached `0015_v3_01_dispatch`.
Migration `0011` created the `global` control seed at revision 0; no separate
seed call was made. Normalized schema-only SHA-256 recomputed twice as
`ae4b86420608b7078850c86f1872dc5667d963316b21bc92db20be57153955da`.
All eight inspected operation/attempt/budget/circuit/usage/idempotency/cost
tables have zero rows and reserved VND is 0. Classification:
`VIRGIN_READY_FOR_OPERATION_REBIND`. See [custody-audit.json](custody-audit.json).

Allowed durable writes were limited to this new private cluster/database and
canonical migrations/control seed. A disposable database
`vf_v0s_b14_replay_5ff19bf4` was created solely for migration replay
`head → base → head`, then removed after the test. It contained no user or
provider data and is not recoverable; the RC-20 custody database was retained.

## Qualification and stop boundary

The exact RC source guard and socket guard passed. The canonical single-dispatch
callable is present in the RC-20 source blob; 131 focused RC-source tests passed
for bootstrap, provider safety and single-dispatch semantics. The CLI help
confirms a required binding file/hash with no lineage-only switch. Its binding
schema has five required operation/authority fields listed above. Therefore
`RC20_EXECUTION_BOOTSTRAP = PARTIAL / NOT_VERIFIED_OPERATION_BOUND`; it would
be incorrect to mark B14 PASS. No Operation 1 key, operation record, authority,
window, bundle, reservation or provider receipt was created. No credential was
read, provider called, kill switch transitioned or production business write
made. The checked-in kill-switch default remains engaged; live execution state
was not enabled.

The [audit helper](audit_custody.py) is read-only. Canonical migration `0011`
already seeded control, so no separate seed path was needed. The evidence files
and checksums are listed in
`SHA256SUMS.txt`.

Draft PR #76 remains open and unmerged as the historical B13G handoff. This
B14 handoff/evidence candidate is newer, separate and must receive its own G-08
review before any merge. Do not silently delete or rewrite #76.

Next safe action requires Owner review of ordering: prepare a fresh RC-20
Operation 1 package in a separately scoped `PREPARED_NOT_AUTHORIZED` task,
then qualify the operation-bound bootstrap when its required authority/bundle
bindings legitimately exist. No B15 action was performed here.
