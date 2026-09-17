# Video Factory V3-01 — Canonical handoff

WORKSTREAM: Video Factory V3-01
TASK: VF-V0S-B14G
VERDICT: PASS — PR #77 governance closure and RC-20/main dual-CI provenance
REPO: vangnguyen/npd-video-factory-v2

Owner-approved PR #77 merged exact reviewed head
`cdf61d6c145f9b869d9f9df2f9a262bde0b3edeb` as
`4ac4880d5627c2800eb918d24c59da5f8e047091`. Its nine changed files
were handoff/governance/custody evidence only; G-08 and PR CI `35129776607`
passed (5/5). Fresh exact-main CI `35172654970` passed 5/5. Canonical
main/RC-20 dual-CI provenance is `PASS`, SHA-256
`5caca534d1cfa6a4e3d9b4f9f9b6b1c33b024ec65afdfc36cf875c673bc1eb86`.
Main and immutable RC-20 share executable-tree SHA-256
`611450db8b70b67c39090dc245a86465cc9a5bdb542f732b9bde0c7e289e1630`.

The read-only post-merge custody audit confirmed the RC-20 database
`vf_vf_v3_01_rc20_5ff19bf478b41d3580e486bb6e37279d` remains
`VIRGIN_READY_FOR_OPERATION_REBIND`, with migration head
`0015_v3_01_dispatch`, no operation record, provider receipt or reservation,
and RC-19 isolation intact. Operation-bound bootstrap is intentionally
deferred until a legitimate operation package and authority exist:
`OPERATION_BOUND_BOOTSTRAP_DEFERRED_UNTIL_OPERATION_PACKAGE_AND_AUTHORITY_EXIST`.
No bootstrap schema or runtime source was changed. PR #76 remains an open,
unmerged `SUPERSEDED_HISTORICAL_DRAFT`; its evidence is preserved. See the
[B14G closure evidence](reviews/vf-v0s-b14g/README.md).

Operation 1 rebind is ready for a separate task, not performed here. Authority
is `NOT_CREATED`; a fresh execution window is required; Operation 2 is locked;
the checked-in kill-switch default is engaged; no bundle is mounted. ASR is
`0/2 PASS`, Vision `2/2 PASS`, Production `NO-GO`. Credential reads, budget
reservations, provider calls, production business writes and actual cost
remain zero. Next safe action: Owner review and assign VF-V0S-B15 — RC-20 ASR
W1 Operation 1 `PREPARED_NOT_AUTHORIZED` rebind. Stop before B15.

## Previous B14 snapshot (historical at its task boundary)

TASK: VF-V0S-B14
VERDICT: REVIEW_REQUIRED — RC-20 custody verified; operation-bound bootstrap cannot run before rebind/authority

Exact governance main is `551379a916b9b574288fda754c0732009d23d288`
after Owner-approved PR #75 head
`c9d2c0ba13e34b060a0bc971a26bb9f5a68b78c8` merged. Fresh exact-main
CI `35126544056` and RC-20 CI `35124578033` both passed 5/5. Canonical
main/RC dual-CI provenance is `PASS`, SHA-256
`330006ae336f12a809a5d7611d250d5e096f8b44c74ab8a02187771cf238d21f`.
RC-20 remains `vf-v3-01-rc20` at
`93b5441d44347c9c40b745bdfed0969880853f68`; RC and main share canonical
executable-tree SHA-256
`611450db8b70b67c39090dc245a86465cc9a5bdb542f732b9bde0c7e289e1630`.
RC-19 remains immutable and historical.

B14 re-derived fresh ledger database
`vf_vf_v3_01_rc20_5ff19bf478b41d3580e486bb6e37279d` exactly and created
a separate private PostgreSQL 16.15 custody cluster (system identifier
`7686186223531422166`, Unix socket/peer auth only). Canonical migrations
`0001`–`0015` reached `0015_v3_01_dispatch`; migration `0011` seeded
`global/revision 0`. The ledger is `VIRGIN_READY_FOR_OPERATION_REBIND`: no
operation, attempt, provider receipt, active reservation, duplicate key or
provider usage. RC-19/RC-20 isolation passed. The exact RC-20 source and
socket guards passed, and the canonical single-dispatch runner is present.
Focused RC-source tests passed 131/131. See the
[B14 custody evidence](reviews/vf-v0s-b14/README.md).

**Full RC-20 operation-bound bootstrap is not VERIFIED.** The existing
`python -m app.provider_runtime_bootstrap` CLI requires a binding containing
`operation_key`, authority receipt, bundle, execution-scope and scope hashes.
B14 forbids creating Operation 1 or those materials. No placeholder, RC-19
identity or fabricated authority was used. This prevents a B14 PASS;
source-level guards and durable custody are verified. A later task must
rebind Operation 1 and qualify the actual operation-bound CLI with legitimate
bindings. Operation 1 authority is `NOT_CREATED`, fresh window is required,
Operation 2 remains locked. The checked-in kill-switch default is engaged;
no runtime transition occurred. ASR remains `0/2 PASS`, Vision `2/2 PASS`,
Production `NO-GO`. Credential reads, budget reservations, provider calls,
production business writes and actual spend were all zero.

Draft PR #76 remains `OPEN / DRAFT` as historical B13G handoff; it was not
merged or deleted in B14. The B14 handoff/evidence update is separate and
newer, and requires its own G-08 before any merge. Next safe action is Owner
review of the bootstrap ordering and a separately assigned RC-20 Operation 1
`PREPARED_NOT_AUTHORIZED` rebind. Do not execute B15 automatically.

## Previous B13 snapshot (historical at its task boundary)

Exact governance main at B13 remained `93b5441d44347c9c40b745bdfed0969880853f68`.
Exact-main CI `35123204511` passed all five canonical jobs and main-only
provenance passed. The canonical executable tree recomputed twice to
`611450db8b70b67c39090dc245a86465cc9a5bdb542f732b9bde0c7e289e1630`.
The canonical single-dispatch callable
`app.provider_single_dispatch.run_single_dispatch` and bootstrap
`python -m app.provider_runtime_bootstrap` are in this exact source tree.

Sequential annotated tag `vf-v3-01-rc20` (tag object
`9fe8d77a6c58a31beccf38bc2cc72b71a8dac240`) was created on that exact
commit. Its executable tree is unchanged. Independent RC-bound CI
[35124578033](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/35124578033)
passed 5/5, including Docker deterministic E2E. RC-only provenance is PASS:
remote tag, peeled commit, Git tree, canonical executable-tree hash and all
five job head SHAs agree. No source commit was created while tagging.

**At the B13 task boundary, RC-20 dual-CI provenance was not PASS.** The canonical validator returned
`CI_PROVENANCE_INVALID` because RC-20 and current main are the *same commit*
and the governance diff is empty. Its contract requires a distinct,
governance-only main commit and a separate successful exact-main CI. No
validator rule was relaxed and no governance merge was performed in B13.
See the [B13 lineage evidence](reviews/vf-v0s-b13/README.md).

Fresh RC-20 ledger identity is a `PLAN_ONLY / NOT_CREATED` preview:
`vf_vf_v3_01_rc20_5ff19bf478b41d3580e486bb6e37279d`. It must be
re-derived and qualified after dual-CI closure. There is no fresh Operation 1
ID, ledger, bundle, approval, authority or execution window. RC-19 remains
immutable and historical; none of its execution material transfers to RC-20.
The checked-in kill-switch default remains engaged, Operation 2 remains
locked, and production remains `NO-GO` (ASR `0/2 PASS`, Vision `2/2 PASS`).
This task made zero credential reads, budget reservations, provider calls,
production business writes and actual spend.

Historical next safe action: Owner G-08 review of the B13 governance-only handoff Draft
PR, then separately authorized controlled merge, fresh exact-main CI and
RC-20/main dual-CI provenance closure. Stop before ledger custody/B14,
Operation 1 rebind or authority.

## Previous B12H snapshot

PR #73 contained only B12G handoff/evidence. G-08 reviewed exact head
`b9e7db84925eecd1155c7ecdba0c75517703cdec`; it merged as governance
main `694f8ac8e98dbb2b47406f1c1fbb2511808a8970`. Exact-main push CI
`35121062274` passed all 5 canonical jobs, including Docker E2E. Remote
main, CI head, clean checkout and canonical Git-object tree match. Main-only
provenance is PASS; this does not claim dual-CI equivalence to RC-19. See the
[B12H governance closure](reviews/vf-v0s-b12h/README.md).

Owner-approved PR #72 head
`412c377123dc92b55eec3bf6b559da05e7388bbb` was merged as
`3bb0bdc0bb55bd0f5d24b12d92c092376989c2c7`. G-08 revalidated the
exact head and 11-file diff against the prior candidate review. The merge
parents are exact baseline main `7ad25cb039c712d450486778d2981d9ef8175385`
and approved PR head. Candidate CI `35117631890` passed 5/5; exact-main
push CI `35119072381` passed 5/5 on the merge commit, including Docker E2E.
Main-only provenance is PASS for that exact commit, run and canonical job set.
See the [B12G exact-main review](reviews/vf-v0s-b12g/README.md).

The canonical executable-tree SHA-256 on governance main is
`611450db8b70b67c39090dc245a86465cc9a5bdb542f732b9bde0c7e289e1630`,
matching the approved candidate. Historical `vf-v3-01-rc19` remains immutable
at `dc8ff55322267dfe54674fa6c4003a899bf235ab`, with executable-tree SHA
`432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502`.
RC-19 is not the current executable main; its Operation 1 ID, ledger binding,
bundle, G-01/G-02/G-03 records, authority receipt and 16–17 September window
are **historical reference only and invalid for current main**. Do not delete
or mutate that evidence or ledger.

Next lineage requires a fresh RC, fresh deterministic ledger custody, fresh
Operation 1 rebind, fresh authority and fresh execution window. None was
created in B12G or B12H. Operation 2 remains locked. Bundle unmounted; checked-in kill
switch engaged. This task performed zero provider credential reads, live budget
reservations, real provider calls, production business writes and actual spend.
ASR remains `0/2 PASS`; Vision `2/2 PASS`; Production `NO-GO`.

At the end of B12H the next safe action was Owner assignment of B13. That
historical gate has now been exercised only to create and qualify RC-20; its
new dual-CI governance closure remains open as stated above.
