# Cost audit

## Current result

| Currency | Approved budget | Actual external cost | External calls |
|---|---:|---:|---:|
| VND | 0 | 0 | 0 |

The baseline audit used repository, GitHub CI and local static/mock evidence only. No provider call,
GPU workflow, hosted render, publish or analytics collection was performed. USD is not an accepted
operating currency for this acceptance program.

## Required provider budget contract

Before G-02, the owner must approve in VND for every real-provider test:

- provider/capability and credential alias;
- model/workflow/version and region;
- maximum calls, media seconds, pixels/tokens or GPU minutes;
- unit-price source and conversion rule if the provider bills in another currency;
- maximum retry and polling count;
- warning thresholds at 50% and 80%;
- hard stop at 100%;
- owner and expiry time.

Failed, timed-out, moderated, retried and partially completed calls count toward actual cost. A
successful response without a usage/cost record is `FAIL` for cost acceptance.

## Current gaps and containment

V3-01-02 now implements one VND-only control plane with per-operation/daily reservation, attempt
costing, exact 50/80/100 alerts, bounded retry/poll/timeout/concurrency, circuit state and a global
kill switch. Local tests prove those contracts while all configured limits stay zero and the kill
switch remains engaged.

The runtime attempt, circuit and reservation state is process-local at this checkpoint. Durable
multi-instance reconciliation, monitoring/retention and owner-gated real-provider acceptance are
still required. Therefore all external, paid, ComfyUI, publishing and analytics execution gates
remain false.

No budget is inferred from credential availability. No automatic currency conversion may be stored
as authoritative cost without its dated source and calculated VND value.

Gap `V3-01-GAP-010`: `IN_PROGRESS`, supported by `EV-V3-PROVIDER-SAFETY-001`; not remediated or
production-verified.
