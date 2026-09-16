# VF-V0S-B12G — PR #72 exact-main verification

This is governance evidence only; it grants no execution authority. PR #72 was
merged at its Owner-approved exact head
`412c377123dc92b55eec3bf6b559da05e7388bbb` into main as merge commit
`3bb0bdc0bb55bd0f5d24b12d92c092376989c2c7`. The merge parents are
`7ad25cb039c712d450486778d2981d9ef8175385` and the approved head.

## Pre-merge G-08

- PR was OPEN, DRAFT and MERGEABLE; it was marked ready only after checks.
- Head and base matched exact Owner bindings. The 11 changed paths matched the
  prior B12R review: four runtime/provider-safety files, migration `0015`,
  three tests, handoff MD/JSON and B12R review. No additional diff appeared.
- No provider/model change, quality-gate relaxation, retry or fallback was
  present. The new runner is opt-in and fail-closed for a future fresh RC.
- Candidate CI `35117631890`: PASS 5/5, exact PR head. Canonical candidate
  executable-tree SHA-256: `611450db8b70b67c39090dc245a86465cc9a5bdb542f732b9bde0c7e289e1630`.
- `git diff --check`: PASS. Historical RC-19 tag and main baseline were exact.

## Exact-main evidence

- Main push CI [35119072381](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/35119072381):
  completed/success for exact merge commit; 5/5 jobs PASS: Python unit and
  contract tests, Studio tests, Renderer tests and bundle, Safety and compose
  contract, Docker deterministic E2E.
- Local exact-main regression: Python/API/worker/bridge 1068 PASS with one
  explicit Windows POSIX-socket skip; Studio 14 PASS; Renderer 14 PASS;
  acceptance/evidence repository validation PASS; secret scan and diff check
  PASS. Linux CI executes the POSIX-specific contract test and migration replay.
- Main-only provenance PASS: remote `main`, clean local HEAD, CI head SHA,
  merge commit and canonical Git-object executable-tree map all bind to
  `3bb0bdc0bb55bd0f5d24b12d92c092376989c2c7`. The canonical hash on
  merged main is `611450db8b70b67c39090dc245a86465cc9a5bdb542f732b9bde0c7e289e1630`,
  equal to the approved candidate. This is not RC-19/main dual-CI provenance:
  those trees intentionally differ and no RC-19 execution claim is made.

## Lineage and safety

`vf-v3-01-rc19` still resolves to
`dc8ff55322267dfe54674fa6c4003a899bf235ab` (annotated tag object
`09a9a51628ab2e33d4ee85a1620f7afca692d18e`), whose canonical tree is
`432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502`.
Its operation ID, custody ledger, scope/bundle, G-01/G-02/G-03, authority and
16–17 September window are historical only and invalid for current main.
The RC-19 ledger and evidence were not mutated or removed. A fresh RC,
lineage-specific ledger, operation rebind, authority and window are required
in separately assigned tasks. No new RC or execution artifact was created.

Operation 2 remains locked; checked-in kill switch remains engaged; no bundle
was mounted. B12G had zero provider credential reads, live reservations, real
provider calls, production business writes and actual provider cost. ASR
remains `0/2 PASS`, Vision `2/2 PASS`, Production `NO-GO`. Stop before B13.
