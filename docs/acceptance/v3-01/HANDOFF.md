# Video Factory V3-01 — Canonical handoff

WORKSTREAM: Video Factory V3-01
TASK: VF-V0S-B12H
VERDICT: PASS — governance handoff merge and exact-main closure
REPO: vangnguyen/npd-video-factory-v2

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

The next safe action is Owner assignment of VF-V0S-B13 to materialize a fresh
RC from exact verified governance main. This B12H handoff/evidence update is
governance-only and must receive separate review before any later merge. Do
not perform B13, ledger creation, operation rebind or authority work under
B12H.
