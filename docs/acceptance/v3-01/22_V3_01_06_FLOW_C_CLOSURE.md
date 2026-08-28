# V3-01-06 — Flow C acceptance plane

## Decision and scope

V3-01-06 implements the offline acceptance plane for:

`Trend signal -> normalize -> cluster -> opportunity score -> Idea -> VideoProject ->`
`publish validation -> approval binding -> publication receipt -> analytics snapshot ->`
`winner assessment -> recommendation-only learning feedback`.

It deliberately does not add or enable an official trend, publishing or analytics adapter. The
checkpoint is limited to strict contracts, deterministic evaluation, negative tests, redacted
fixture evidence and governance updates. No credential, paid call, deployment, public ingress,
remote publication, remote read, production analytics or autonomous learning action is part of
this change.

## Deliverables

- `apps/api/app/flow_c_acceptance.py`: strict evidence models and five-axis evaluator;
- `apps/api/tests/test_flow_c_acceptance.py`: lineage, tamper and owner-gate tests;
- `packages/contracts/flow-c-acceptance.v1.json`: checked-in quantitative policy;
- `scripts/v3_01_flow_c_acceptance.py`: offline evidence validator;
- `evidence/v3-01/vf-v3-01-20260828T043714Z-c1f50c4`: redacted two-run fixture bundle.

## What the evaluator proves

For each locked-commit run it independently calculates or validates:

- trend-source count and provenance completeness;
- normalized signal/source references and deterministic cluster hashes;
- reproducible opportunity scoring;
- idea-to-trend and VideoProject-to-idea bindings;
- final-video, exact approval and publication-request hash binding;
- rights and per-platform validation gates;
- publication idempotency and duplicate-post prevention;
- publication receipt payload integrity;
- analytics normalization across the complete metric catalog;
- unsupported or missing metric values represented as `null`, never fabricated as zero;
- chronological analytics snapshots;
- reproducible and explainable winner assessment;
- recommendation-only learning lineage back to snapshot, assessment, idea and trend cluster;
- restart recovery and VND-only provider/cost accounting.

It requires two chronological runs on one locked code commit. Contract/mock evidence may pass while
real-provider, production-path and human-quality axes remain independently `BLOCKED`.

## Fail-closed behavior

- fixture providers, trend sources, analytics snapshots and publications cannot claim real status;
- unknown source, signal, cluster, opportunity, provider, project or publication references fail;
- missing rights, platform validation, idempotency, duplicate protection or receipt integrity fail;
- unsupported analytics metrics with non-null values fail schema validation;
- non-VND currency fails schema validation;
- local/CI evidence fails if any external execution, production write or publication is claimed;
- winner and learning outputs remain recommendation-only and cannot mutate paid media;
- G-01/G-02/G-03, G-04/G-05/G-06 and G-11 are evaluated separately and cannot be inferred from CI.

## Current evidence result

Two synthetic runs pass every contract/mock threshold with `0 VND` cost, no credential, no external
call and no remote post. The result is still `BLOCKED` because:

- G-01 credential/provider scope is pending;
- G-02 VND budget is pending;
- G-03 rights inputs are pending;
- G-04 production-like staging is pending;
- G-05 exact final artifact approval is pending;
- G-06 one bounded official publication is pending;
- G-11 human full-watch quality acceptance is pending.

Fixture publication receipts and fixture analytics snapshots are not remote evidence. Therefore
`V3-01-GAP-006` moves only from `OPEN` to `IN_PROGRESS`; it is not remediated or closed. The
repository-wide verdict remains `NO-GO`.

## Exact next gate

After CI passes on the final V3-01-06 PR head, a new bounded G-08 is required to merge this
acceptance plane. That decision must not grant G-01 through G-07, deployment, public ingress or
publication. V3-01-07 DR/observability may begin only after that repository decision and remains a
separate scope.
