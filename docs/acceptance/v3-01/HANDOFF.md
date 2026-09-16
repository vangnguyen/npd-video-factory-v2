# Video Factory V3-01 — Canonical handoff

WORKSTREAM: Video Factory V3-01
TASK: VF-V0S-B13
VERDICT: REVIEW_REQUIRED — RC-20 materialized and RC CI passed; dual-CI governance closure pending
REPO: vangnguyen/npd-video-factory-v2

Exact governance main remains `93b5441d44347c9c40b745bdfed0969880853f68`.
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

**RC-20 dual-CI provenance is not PASS.** The canonical validator returned
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

Next safe action: Owner G-08 review of the B13 governance-only handoff Draft
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
