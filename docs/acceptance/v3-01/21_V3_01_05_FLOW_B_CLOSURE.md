# V3-01-05 — Flow B acceptance plane

## Decision and scope

V3-01-05 implements the acceptance plane for:

`Idea -> Research -> Script -> Storyboard -> Media Plan -> Stock / AI Image / AI Video ->`
`Vision QC -> TTS -> Subtitle -> Music / Ducking -> Timeline -> Preview -> Approval ->`
`Final Render -> QC`.

It deliberately does not add or enable real providers. The checkpoint is limited to strict
contracts, deterministic evaluation, negative tests, redacted fixture evidence and governance
updates. No runtime API route, credential, paid call, deployment, public ingress, publication or
production analytics is part of this change.

## Deliverables

- `apps/api/app/flow_b_acceptance.py`: strict evidence models and five-axis evaluator;
- `apps/api/tests/test_flow_b_acceptance.py`: threshold, tamper and owner-gate tests;
- `packages/contracts/flow-b-acceptance.v1.json`: checked-in quantitative policy;
- `scripts/v3_01_flow_b_acceptance.py`: offline evidence validator;
- `evidence/v3-01/vf-v3-01-20260828T033515Z-2563dfd`: redacted two-run fixture bundle.

## What the evaluator proves

For each run it independently calculates or validates:

- research source count, claim-source coverage and verified-claim coverage;
- maximum similarity against the originality comparison set;
- storyboard/media-plan and visual-asset shot coverage;
- per-asset rights record, provider receipt, lineage, provider reference and decode state;
- minimum visual relevance;
- narration-duration deviation and subtitle median/P95 drift;
- integrated loudness, true peak, clipping, speech/music ratio and ducking;
- exact timeline and render-input approval bindings;
- final render resolution, full decode, black/freeze/silence/A-V sync QC;
- restart recovery and VND-only provider/cost ledger.

It also requires two chronological runs on one locked code commit. Contract/mock evidence may pass
while real-provider, production-path and human-quality axes remain independently `BLOCKED`.

## Fail-closed behavior

- a fixture provider cannot set `real_provider_tested=true`;
- a fixture source cannot set `real_source_tested=true`;
- unknown claim/source/provider/shot references fail evaluation;
- missing rights, receipts or lineage fail evaluation;
- USD or any non-VND currency fails schema validation;
- external actions and publication are constant `false` in the run contract;
- G-01/G-02/G-03, G-04 and G-11 are evaluated separately and cannot be inferred from CI.

## Current evidence result

Two synthetic runs pass every contract/mock threshold with `0 VND` cost. The result is still
`BLOCKED` because:

- G-01 credential/provider scope is pending;
- G-02 VND budget is pending;
- G-03 owned inputs/rights policy is pending;
- G-04 production-like staging is pending;
- G-11 human full-watch quality acceptance is pending.

Therefore the repository-wide verdict remains `NO-GO`.

## Exact next gate

After CI passes on the final V3-01-05 PR head, a new bounded G-08 is required to merge this
acceptance plane. That decision must not grant G-01/G-02/G-03/G-04/G-11, deployment, public ingress
or publication. Real-provider runs remain a separate later owner decision.
