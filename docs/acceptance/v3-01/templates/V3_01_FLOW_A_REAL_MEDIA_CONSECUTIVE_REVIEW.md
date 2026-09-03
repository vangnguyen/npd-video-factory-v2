# Flow A real-media 2/2 consecutive review

This aggregate may be completed only after two distinct input runs have independent PASS evidence.
It references each run without rewriting or deduplicating source/provider evidence.

## Immutable aggregate binding

| Field | Run 1 | Run 2 |
|---|---|---|
| Run ID | | |
| Input media SHA-256 | | |
| Executable RC tag / commit | | |
| Run-manifest SHA-256 | | |
| Final video SHA-256 | | |
| ASR evaluation SHA-256 | | |
| Automated QC SHA-256 | | |
| G-11 review SHA-256 | | |
| Run evidence SHA-256 | | |
| Run verdict | | |
| Completed at UTC | | |

## Consecutive rules

- [ ] Both run verdicts are `PASS`.
- [ ] Input media SHA-256 values are distinct.
- [ ] Both runs use the same locked executable RC.
- [ ] Run 1 completed before Run 2 began.
- [ ] Both manifests and all referenced hashes validate independently.
- [ ] Both exact G-11 reviews are `ACCEPT` and still valid for their final video hashes.
- [ ] Neither run contains an unauthorized retry, fallback, deploy, publish or public ingress.
- [ ] No later artifact change invalidates either run.

## Aggregate decision

```text
FLOW A REAL-MEDIA CONSECUTIVE STATUS: 0/2 / 1/2 / 2/2
AGGREGATE VERDICT: PASS / REVIEW_REQUIRED / FAIL
MACHINE REASONS:
AGGREGATE EVIDENCE SHA-256:
REVIEWER:
REVIEWED AT UTC:
ACCEPTANCE AXIS CHANGE: NONE UNTIL OWNER-APPROVED EVIDENCE MERGE
PRODUCTION: NO-GO
```

An aggregate PASS closes only the exact acceptance axes justified by the two bound runs. It does
not authorize deployment, publication, public ingress, analytics writes or a third provider run.
