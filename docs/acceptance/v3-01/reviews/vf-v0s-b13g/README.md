# VF-V0S-B13G — RC-20 governance and dual-CI closure

Verdict: **PASS** for the exact PR #75 merge and post-merge provenance.
This is governance closure, not execution authorization.

## G-08 and merge

- Approved PR #75 head: `c9d2c0ba13e34b060a0bc971a26bb9f5a68b78c8`.
- Base: `93b5441d44347c9c40b745bdfed0969880853f68`.
- Full diff and `git diff --check`: PASS. The four changed paths were only
  `HANDOFF.md`, `handoff.json`, and two B13 review/evidence artifacts under
  `docs/acceptance/v3-01/`; no executable/runtime path changed.
- Candidate CI [35125546072](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/35125546072):
  5/5 PASS on the approved PR head.
- Merge commit and resulting main:
  `551379a916b9b574288fda754c0732009d23d288`. Its parents are the
  exact base and approved head above. PR #75 is MERGED.

## Exact-main and RC provenance

- Fresh exact-main push CI
  [35126544056](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/35126544056):
  5/5 PASS; run and all job head SHAs equal the merge commit.
- Annotated `vf-v3-01-rc20` tag object
  `9fe8d77a6c58a31beccf38bc2cc72b71a8dac240` still peels to
  `93b5441d44347c9c40b745bdfed0969880853f68`.
- Independent RC CI
  [35124578033](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/35124578033):
  5/5 PASS on the RC commit.
- Canonical executable-tree SHA-256 on both RC and governance main:
  `611450db8b70b67c39090dc245a86465cc9a5bdb542f732b9bde0c7e289e1630`.
  All 12 executable input Git object IDs matched; only the four allowlisted
  governance paths differ.
- Unmodified canonical validator `scripts/v3_01_ci_provenance.py` returned
  `PASS`, provenance SHA-256
  `330006ae336f12a809a5d7611d250d5e096f8b44c74ab8a02187771cf238d21f`.
  The exact validator result is in [dual-ci-provenance.json](dual-ci-provenance.json).
  RC-20 governance lineage is now `CLOSED / PASS`.

## Deferred safety boundary

The first RC-20 lineage re-derived as
`al-0001-9722891b4ae68168375adea9fc53cc6ad89c20fa8f3c5d8535f056173f428624`.
Expected ledger identity
`vf_vf_v3_01_rc20_5ff19bf478b41d3580e486bb6e37279d` is still
`PLAN_ONLY / NOT_CREATED`. B13G did not create a ledger, Operation 1 ID,
bundle, G-01/G-02/G-03 approval, authority, window or reservation. RC-19
remains immutable and historical; its execution material is not reusable.
The checked-in kill-switch default is engaged; no runtime transition was
made. Operation 2 remains locked, ASR `0/2 PASS`, Vision `2/2 PASS`, and
Production `NO-GO`. Credential reads, budget reservations, provider calls,
production business writes and actual cost were all zero.

The B13 review artifact retains the historical `CI_PROVENANCE_INVALID`
result from the time before PR #75 merged; it is not rewritten. B14 ledger
custody/bootstrap qualification requires a separate Owner task. No B14 step
was performed here.
