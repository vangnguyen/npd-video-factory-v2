# Flow C — Trend to publish to analytics

## Current result

`CONTRACT/MOCK PASS; OVERALL BLOCKED / NO LIVE PUBLISH ATTEMPT`

V3-01-06 adds a strict five-axis acceptance contract and deterministic evaluator for the complete
Trend-to-learning lineage. Two locked-commit fixture runs pass the contract/mock axis, but publishing
remains dry-run only and official platform adapters are not production-accepted. All live and
external gates remain false. The audit created no remote post, external analytics read, customer
contact or provider cost.

## Required production acceptance sequence

1. ingest only owner-approved trend sources and preserve source provenance;
2. create a source-grounded idea/script and complete Flow B quality and rights checks;
3. prepare one immutable publication package for one explicitly approved target;
4. obtain G-05 approval for the exact final video/caption/thumbnail hashes;
5. obtain platform-specific G-06 approval bound to those hashes and the target account;
6. perform exactly one official API publish with an idempotency key;
7. read the remote object back and compare text/media/order/visibility;
8. replay the same request and prove no duplicate remote object;
9. collect analytics at T+15 minutes and T+24 hours through a read-only official adapter;
10. store evidence, cost and correlation IDs without tokens or audience PII.

## Current stage evidence

| Stage | Current state | V3-01 decision |
|---|---|---|
| Trend ingestion/clustering | deterministic fixtures plus source/provenance/cluster-hash contract | contract/mock PASS only |
| Window/ranking/learning | reproducible scoring and recommendation-only lineage | contract/mock PASS only |
| Publication package | exact video/approval/request hash binding | contract/mock PASS |
| Publish preview/dry-run | rights/platform/idempotency/duplicate/receipt checks | contract/mock PASS |
| Official publishing adapter | absent/unaccepted | BLOCKED |
| Remote read-after-write | not run | NOT_TESTED |
| Idempotent remote replay | not run | NOT_TESTED |
| Analytics normalization | complete metric catalog and explicit null semantics | contract/mock PASS |
| Official analytics adapter | absent/unaccepted | BLOCKED |
| T+15/T+24 collection | not run | NOT_TESTED |

The checked-in evidence is `EV-V3-FLOW-C-CONTRACT-001` on locked code commit
`c1f50c4941929120b815fda33acd75acd07f454a`. Fixture evidence cannot be promoted to
real-provider, production-path or quality evidence.

## Mandatory owner boundary

G-06 is per platform, target, artifact set and time window. Approval for a draft, credential setup or
another platform does not authorize a write. The global publishing kill switch and
`PUBLISH_EXTERNAL_EXECUTION_ENABLED=false` remain the controlling state until that gate is recorded.

## Failure and rollback semantics

The system must stop on ambiguous timeout, permission mismatch, content-policy failure, duplicate
risk or remote-content mismatch. It must reconcile by official read before any retry. Takedown or
remote edit is another owner-gated external write; no automatic rollback is permitted.

Open gaps: `V3-01-GAP-002`, `V3-01-GAP-006`, `V3-01-GAP-007`, `V3-01-GAP-010`,
`V3-01-GAP-013`, `V3-01-GAP-016`.
