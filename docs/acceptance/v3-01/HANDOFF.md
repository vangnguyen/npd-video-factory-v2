# Video Factory V3-01 — Canonical handoff

WORKSTREAM: Video Factory V3-01
TASK: VF-V0S-B16R-G1
VERDICT: GOVERNANCE_CLOSURE_CANDIDATE — exact-head G-08, PR CI, merge and exact-main closure required
REPO: vangnguyen/npd-video-factory-v2

## B16R-G1 governance closure — final authority not created

PR #81 is based directly on pre-merge governance main
`4ac4880d5627c2800eb918d24c59da5f8e047091`. Its only role is to
canonicalize B15/B16/B16R handoff and historical evidence under G-08. The
post-merge main SHA and exact-main CI run ID do not exist until the controlled
merge and CI complete. Therefore **FINAL_EXECUTION_AUTHORITY = NOT_CREATED**
for the new governance main; Operation 1 is prepared and unconsumed, not
authorized for dispatch. A separate VF-V0S-B16R-G2 must regenerate and review
the final authority/bundle/window binding against that exact new main and CI.
Do not run B17, mount the bundle, reserve budget or call the provider in G1.

Both the B16 historical receipt
`694693ca50001c93d5264418661bc8a25179a3791d6437e077f67653c2a3140c`
and the B16R corrected pre-merge receipt
`074c91cf7efff23bd7763bb698905dfe8de9e0d50ed72dea358354a4930e8dce`
are `HISTORICAL_PRE_MERGE_BINDING / INVALID_AFTER_GOVERNANCE_MERGE`.
Their recorded `GRANTED_NOT_CONSUMED` status describes only the old-main
binding; neither is live execution authority for the new main. Historical
approval, bundle, scope and receipt bytes are preserved as evidence.

The single-dispatch runner requires `executable_rc_ci_run_id` and
`governance_main_ci_run_id` in the authority receipt. RC-20's run
`35124578033` remains stable while its tag is unchanged; the required new
governance-main run ID is unknowable until after G1 merges and exact-main CI
passes. G2, not G1, must bind the new main SHA, run ID and provenance.
The proposed 21/09→22/09 window is not carried forward as active authority:
`WINDOW_REAUTH_REQUIRED = YES`, even if Owner later selects the same dates.
The RC-20 ledger remains read-only in G1; Operation 2 stays locked, kill
switch engaged, bundle unmounted, and Production `NO-GO`. See the
[G1 closure review](reviews/vf-v0s-b16r-g1/README.md).

## Historical B16R clean candidate — no execution

The B16R branch starts directly from canonical main
`4ac4880d5627c2800eb918d24c59da5f8e047091` and ports unchanged B15
preparation plus corrected B16 authority evidence. It is not stacked on PR
#79/#80; prior PRs #78/#79/#80 remain historical and unmerged. Canonical RC CI
`35124578033` and exact-main CI `35172654970` both passed 5/5, and their
dual-CI provenance SHA is
`5caca534d1cfa6a4e3d9b4f9f9b6b1c33b024ec65afdfc36cf875c673bc1eb86`.
The runner reads `executable_rc_ci_run_id` and `governance_main_ci_run_id`
from the authority receipt; B16 omitted them. The corrected receipt binds
these exact runs, with new SHA-256
`074c91cf7efff23bd7763bb698905dfe8de9e0d50ed72dea358354a4930e8dce`.
G-01/G-02/G-03 records `V3-01-APP-078/079/080` remain byte-identical:
their exact provenance SHA already binds the two runs. The strict bundle and
loaded scope schemas have no CI-run fields, so their hashes remain
`a98a78884d020138c858b608b5462df5a762ebcac9024ce0ff6257e1bdd10019`
and `2e049bfe8b2dede3ca8cb3ffdb27fd95bc96dd1d72c8e18cb4dca1788282b5de`.
The old B16 receipt `694693ca50001c93d5264418661bc8a25179a3791d6437e077f67653c2a3140c`
remains historical in Draft PR #80.

The corrected authority binds the **pre-merge** main. The runner requires
remote main to equal that exact SHA; merging any governance PR advances main
and creates a fresh exact-main CI/provenance identity. Therefore this
candidate is not post-merge B17 readiness or dispatch authority. The runner
has no side-effect-free top-level check-only mode; B16R validates its
authority loader, verifier and dual-CI validator offline. The bundle remains
unmounted, kill switch engaged, and a fresh read-only RC-20 ledger query found
zero rows in all eight execution tables and zero reserved VND. No credential read,
reservation, provider call or
production business write occurred in B16R. Owner review of a post-merge
authority-binding procedure and renewed window approval are required before B17
after main changes. G1 does not create this authority.

## Historical B16 authority state — no execution

The explicit Owner decision in VF-V0S-B16 materialized fresh G-01/G-02/G-03
records `V3-01-APP-078/079/080` for the exact RC-20 Operation 1 below. The
existing strict gate loader validates the completed bundle. Its raw SHA-256 is
`a98a78884d020138c858b608b5462df5a762ebcac9024ce0ff6257e1bdd10019`;
the final loaded scope's canonical SHA-256 is
`2e049bfe8b2dede3ca8cb3ffdb27fd95bc96dd1d72c8e18cb4dca1788282b5de`.
These are distinct from B15's prepared scope and preparation template. The
Historical Operation-1-only authority receipt SHA-256 was
`694693ca50001c93d5264418661bc8a25179a3791d6437e077f67653c2a3140c`
and recorded status was `GRANTED_NOT_CONSUMED`. Corrected candidate approval
records, bundle, scope, authority and reproducibility checks are in the
[B16 final package](prepared/vf-v0s-b16-rc20-final-authority/README.md).

The historical B16 authorized window was **2026-09-21 21:00 → 2026-09-22 01:00 ICT**
(2026-09-21 14:00 → 18:00 UTC), limited to one call, one concurrent operation,
500 VND per operation and 1,250 VND total window exposure. Modeled cost is
326.3004 VND; retry and fallback are zero; provider/controller timeouts are
90/120 seconds. That historical authority does not dispatch or bypass future
fresh preflight. The final bundle is unmounted, kill switch engaged, and the
private RC-20 ledger was read back virgin: no operation record, provider
receipt, reservation or duplicate. Credential reads, real provider calls,
production business writes and actual spend remain zero. Operation 2 stays
`NOT_APPROVED / LOCKED / NOT_TRANSFERRED`; Production is `NO-GO`.

Draft PRs #78/#79/#80 remain open and unmerged as historical evidence. B16R
does not treat them as executable lineage. B17 has not run; stop before B17.

## Historical B15 preparation snapshot

Exact governance main is `4ac4880d5627c2800eb918d24c59da5f8e047091`
after PR #77; exact-main CI `35172654970` and RC-20 CI `35124578033`
passed 5/5. Fresh dual-CI provenance is `PASS`, SHA-256
`5caca534d1cfa6a4e3d9b4f9f9b6b1c33b024ec65afdfc36cf875c673bc1eb86`.
RC-20 remains `vf-v3-01-rc20` at
`93b5441d44347c9c40b745bdfed0969880853f68`; main and RC share
executable-tree SHA-256
`611450db8b70b67c39090dc245a86465cc9a5bdb542f732b9bde0c7e289e1630`.

B15 read-only revalidated the private RC-20 PostgreSQL 16.15 custody
(`vf_vf_v3_01_rc20_5ff19bf478b41d3580e486bb6e37279d`, system ID
`7686186223531422166`, migration `0015_v3_01_dispatch`). All execution
state tables remain empty; no operation, receipt, reservation or duplicate
exists. The fresh derived Operation 1 ID/ledger key is
`v3-01-rc20-openai-transcription-asr-al-0001-9722891b4ae68168375adea9fc53cc6ad89c20fa8f3c5d8535f056173f428624-call-01`.
All W1, prompt, asset, reference transcript and RightsRecord hashes match.
The [B15 preparation package](prepared/vf-v0s-b15-rc20-asr-w1/README.md)
is `PREPARED_NOT_AUTHORIZED`; its template is intentionally not loader-valid.
Its execution-scope, prepared-scope, manifest and template hashes are recorded
in `prepared-material-hashes.json` and reproduce exactly. The proposed
21/09 21:00 → 22/09 01:00 ICT window and 500/1,250 VND ceilings grant no
execution permission. Operation-bound bootstrap is `DEFERRED_BY_CONTRACT`
until B16 produces legitimate approvals, final bundle and authority; B17 is
the later zero-call qualification. No metadata registration or other ledger
write occurred. Kill switch remains engaged; Operation 2 stays locked;
credential reads, budget reservation, provider calls, production business
writes and actual cost are zero. Production is `NO-GO`.

Draft PR #78 remains open and unchanged as B14G historical handoff/evidence.
At the B15 boundary, the next action was separately assigned B16 final
G-01/G-02/G-03, runtime bundle and authority materialization.

## Historical B14 snapshot (superseded as current task state)

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
