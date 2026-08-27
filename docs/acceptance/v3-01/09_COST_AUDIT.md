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

The code has VND ledger concepts and bounded behavior in selected paths, but not one global
provider circuit breaker, budget reservation system or kill switch covering every capability.
Therefore all external, paid, ComfyUI, publishing and analytics execution gates remain false.

No budget is inferred from credential availability. No automatic currency conversion may be stored
as authoritative cost without its dated source and calculated VND value.

Open gap: `V3-01-GAP-010`.
