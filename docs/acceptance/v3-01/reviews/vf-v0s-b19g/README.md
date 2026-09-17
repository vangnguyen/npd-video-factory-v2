# VF-V0S-B19G — RC-21 governance-only closure candidate

This review preserves the already-materialized RC-21 and creates only a
handoff/evidence delta from exact source main
`6dcf144a4e3830e27fd617e52bc8eeab0952126e`. It neither changes the
12-path executable tree nor creates a ledger, operation, bundle, approval,
authority or execution window. The final PR head and CI must be rechecked
under G-08 immediately before merge.

## B19 lineage evidence

- Remote RC sequence was contiguous through RC-20; RC-21 was absent before
  materialization. Annotated `vf-v3-01-rc21` object
  `9a270642024cc6e0dff7881c2c4befb62e7efb59` peels to
  `6dcf144a4e3830e27fd617e52bc8eeab0952126e`.
- Canonical executable-tree SHA-256 from the twelve Git object IDs is
  `e75e284a8cebb9864ed441c93cafea17717f247729fe0f3635e1a4f106795bd0`
  on both tag and source main. Full Git tree object is
  `8872f730a53de98a065e1b61fd338c87578ccc8a`.
- Exact-main CI [35193731609](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/35193731609)
  and RC-bound CI [35194969154](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/35194969154)
  each passed all five canonical jobs. All RC job head SHAs match the peeled
  commit. RC provenance is `PASS_RC_ONLY`.
- The unmodified canonical dual-CI validator returned
  `CI_PROVENANCE_INVALID` at B19 because RC and then-current main were the
  same commit and `governance_changed_paths=[]`. A distinct governance-only
  main plus fresh exact-main CI is mandatory; no validator relaxation is
  permitted.
- The separately preserved B19 external-local handoff has SHA-256
  `b64e9a9e5c6f376f2d9eb91ccc08aace26a89828215d21b79eee585f5a6c1895`;
  its structured lineage evidence has SHA-256
  `ea218c76765965bead7323ea52925bc06ba5f76d4d1124be956efa141457d860`.
- The tagged runner blob `3f7c2fa4269c333d11ff24b6f9eb5869cbbf4811`
  contains `run_single_dispatch` and `validate_single_dispatch`.
  Check-only source/mock tests establish no credential resolver, budget
  reservation, provider adapter, dispatch marker, operation consumption or
  bundle mount. No check-only call against a real ledger occurred in B19.
- Expected RC-21 ledger
  `vf_vf_v3_01_rc21_5dc91b550ffa095ca105e68b6a495a33` is a
  deterministic `PLAN_ONLY` identity, not a created database or custody
  attestation. RC-20 remains immutable/historical and no execution material
  was reused.

The [machine-readable B19 evidence](rc21-lineage.json) is a copy of the
bounded lineage facts, not a post-merge provenance claim. B19G must review
the exact final PR head/diff, require PR CI PASS, merge only this governance
delta, then require fresh exact-main CI and the real dual-CI validator PASS.
The pre-merge candidate must never be treated as provider or Operation 1
authority. Kill switch stays engaged, Operation 2 locked, Production NO-GO,
credential reads 0, reservation 0 VND, provider calls 0 and cost 0 VND.
