# VF-V0S-B16R-G1 — governance closure only

PR #81 is a main-based governance/handoff/evidence candidate for RC-20. Its
pre-merge base is `4ac4880d5627c2800eb918d24c59da5f8e047091`; it is not
stacked on Draft PR #78, #79 or #80. The PR preserves B15 preparation, B16
Owner approval artifacts and B16R's missing-CI-field correction as historical
records. Files under `docs/acceptance/v3-01/prepared/` and `approvals/` are
evidence, not a runtime mount. No path selected by the canonical executable
tree manifest changes. RC-20 remains `vf-v3-01-rc20` at
`93b5441d44347c9c40b745bdfed0969880853f68`, executable tree
`611450db8b70b67c39090dc245a86465cc9a5bdb542f732b9bde0c7e289e1630`.

## Authority classification

| Record | Historical recorded state | Binding after governance merge |
| --- | --- | --- |
| B16 receipt `694693ca50001c93d5264418661bc8a25179a3791d6437e077f67653c2a3140c` | `GRANTED_NOT_CONSUMED` on the old main | `HISTORICAL_PRE_MERGE_BINDING / INVALID_AFTER_GOVERNANCE_MERGE` |
| B16R receipt `074c91cf7efff23bd7763bb698905dfe8de9e0d50ed72dea358354a4930e8dce` | `GRANTED_NOT_CONSUMED` on pre-merge main `4ac4880d...` | `HISTORICAL_PRE_MERGE_BINDING / INVALID_AFTER_GOVERNANCE_MERGE` |
| Final execution authority for new main | none | `NOT_CREATED` until separate G2 |

The old G-01/G-02/G-03 records, final bundle, loaded scope and proposed window
remain historical evidence. They do not confer dispatch authority on the new
governance main. Operation 1 is prepared but unconsumed; Operation 2 remains
locked. The old window must be reauthorized even if its dates are later
chosen again.

## Why G2 must follow G1

`app.provider_single_dispatch.run_single_dispatch` requires exact remote-main
binding and two receipt fields: `executable_rc_ci_run_id` and
`governance_main_ci_run_id`. RC-20 CI run `35124578033` is stable while the
RC stays immutable. The new main SHA and its exact-main CI run ID cannot be
known until after PR #81 merges. Only then can fresh main and dual-CI
provenance be validated and a separate Owner-reviewed G2 authority be bound.
This PR must not generate that final authority or run B17.

## G-08 and safety boundary

G-08 must inspect the final exact PR head and complete diff, confirm all
changes are handoff/governance/evidence/approval-history metadata, recompute
the unchanged executable tree, and require exact-head PR CI PASS before merge.
After controlled merge, exact-main CI and RC-20/main dual-CI provenance must
pass independently. The private RC-20 ledger may only be queried read-only:
no consumed operation, provider receipt, reservation or duplicate may appear.
Kill switch remains engaged, bundle unmounted, credentials unread, budget
unreserved, provider calls and actual cost zero, Production `NO-GO`.
