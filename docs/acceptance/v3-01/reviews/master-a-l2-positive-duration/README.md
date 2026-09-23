# Master Lane A-L2 positive-duration timing recovery

Status: **SOURCE CANDIDATE / OWNER G-08 REQUIRED / ZERO CALL**.

## Evidence boundary

The historical RC-21 Operation 1 remains `CONSUMED / PROVIDER_SUCCESS /
QUALITY_FAIL`. Its terminal file has SHA-256
`4fd23531dee1bdcc7920d7f090059f72dcac3961eb4aff762d46de8d822852c9`.
The audit reads that file twice and proves the hash is identical before and after
derivation. It does not rewrite the raw provider response, transcript, timing,
quality result, ledger, authority, reference transcript, or evidence manifest.

The exact raw transcript has 412 words and 27 provider-native boundary points
in 25 runs. Its canonical transcript SHA-256 remains
`698b802c1f0e165a788b2033f59715b9a9ec8a294f4dd08ed8ac82e24818cc0c`.

## Selected contract

`adjacent_successor_partition_v1` creates a separate derived view for strict
interval-only consumers. For each run of zero-duration boundary points it:

1. requires the immediate successor to be a positive provider interval that
   starts at the same provider anchor;
2. partitions only that already-positive successor interval into integer
   microsecond slices;
3. assigns the run to the first slices and the successor to the final slice;
4. fails closed when the successor is absent, unanchored, overlapping, outside
   the segment, or too short at microsecond resolution.

It never fills a provider-native gap, crosses a segment boundary, changes text,
or claims acoustic/provider alignment. Raw provider evidence remains version 1
and `is_original_evidence=true`; the derived view is version 2 and
`is_original_evidence=false` with explicit algorithm and source hashes.

On the exact RC-21 evidence, 27 boundary points and 25 successors are changed;
360 unrelated positive provider intervals are unchanged. Every derived word is
positive, monotonic, non-overlapping, and within its original segment. The
derived transcript SHA-256 is
`17b2b98864096e14c9436058c2bab404e52dccf6893915ad075c43ea8d7c9db2`
and its word-mapping manifest SHA-256 is
`539781ddedaced50298747bb7f50b7ee36b0ab50c9222e172dbadb2762b4a298`.

## Algorithm review

| Candidate | Result | Safety finding |
| --- | --- | --- |
| Midpoint redistribution | Rejected | recomputes unrelated positive provider intervals |
| Neighbor-bound interpolation | Rejected | 11/25 runs would enter provider gaps totalling 6.079997 seconds |
| Segment-proportional allocation | Rejected | lexical-length weighting is not acoustic evidence |
| Constrained minimum-duration expansion | Rejected | arbitrary epsilon can cross existing interval bounds |
| Adjacent successor partition | Selected | changes only the existing positive successor envelope; fails closed otherwise |

The committed [audit](actual-operation-audit.json) is reproducible with
[`audit_actual_operation.py`](audit_actual_operation.py) and the unchanged local
A6 terminal artifact.

## Runtime boundary

The request field `word_timing_policy` defaults to
`strict_provider_intervals`. The derived policy is additionally guarded by
`AUTO_EDIT_DERIVED_TIMING_ENABLED=false` in local, CI, and production defaults.
An explicit request while disabled fails before asset/provider work. A future
merge therefore does not silently enable derived timings.

When explicitly enabled after a future reviewed lineage, the analysis service
derives the separate view after provider evidence creation and before
scene/silence/highlight/persistence consumers. The repository persists both
versions and uses the latest derived version for interval-only downstream
readiness.

## Downstream regression result

The actual 27-case fixture validates:

- scene construction and highlight selection;
- speech-overlap-safe silence decisions;
- raw and derived transcript persistence/readback;
- subtitle word/cue model validation;
- reframe-keyframe monotonicity;
- timeline/render contract construction.

The full Python/API/worker/bridge suite, renderer, Studio, migration replay,
acceptance validation, safety/compose, and Docker E2E remain mandatory on the
exact PR head. Historical lexical quality failure and Operation 2 remain
unchanged/locked.

## Owner boundary

This executable change requires a new RC, fresh ledger/operation/bundle/
authority/window, and any later provider decision after an approved G-08 merge
and exact-main verification. This draft grants none of them.

```text
provider calls: 0
credential reads: 0
budget reserved: 0 VND
additional cost: 0 VND
Operation 2: LOCKED
Production: NO-GO
```
