# Video Factory V3-01 — Canonical handoff

WORKSTREAM: Video Factory V3-01
TASK: VF-V0S-B5G
VERDICT: PASS
REPO: vangnguyen/npd-video-factory-v2

## RC-19 governance closure

- G-08 reviewed PR #67 at exact head `cd866a03445eff1df0f489b2b6050f22939a363f`: PASS.
- The 18 changed files were limited to `docs/acceptance/v3-01/` and `evidence/v3-01/`.
- PR #67 merged as `d13c57bf480ed3b6b8b56f46370fef58b291810b`; its parents are the exact source baseline
  `dc8ff55322267dfe54674fa6c4003a899bf235ab` and the exact reviewed head. The merge tree equals the reviewed PR tree.
- Exact governance-main CI `34916352282`: completed/success, attempt 1, 5/5 canonical jobs PASS.
- Main provenance: PASS. Canonical RC-19/main dual-CI provenance: PASS,
  SHA-256 `12128084c7fff1397b2476e5360b45e13232eef0bbf161f962c3c6de38d43228`.
- Canonical executable-tree SHA on RC-19 and governance main:
  `432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502`; equality PASS.
- `vf-v3-01-rc19` remains the same annotated tag at
  `dc8ff55322267dfe54674fa6c4003a899bf235ab`; RC CI `34875483864` remains PASS 5/5.
- RC19_GOVERNANCE_LINEAGE: CLOSED / PASS. The previous `CI_PROVENANCE_INVALID` blocker is resolved by the
  distinct allowlisted governance merge and its fresh exact-main CI; no validator or executable source was changed.

The merge was observed after an exact-head pre-merge guard saw the PR state transition to `MERGED`; the local guarded
merge command did not run. GitHub records `vangnguyen` as merge actor, a valid GitHub signature, and the exact authorized
base/head parents. This race is retained explicitly in the evidence rather than rewritten as a local merge action.

## Execution boundary

Future ledger identity remains plan-only:
`vf_vf_v3_01_rc19_5a72b3be5266c9801013f579e75662ed`.
No database, namespace, operation identity, bundle, approval, authority, window or reservation was created.

- Fresh ledger binding: REQUIRED.
- Operation 1 rebind: REQUIRED; no Operation 1 ID exists for RC-19.
- Fresh authority: REQUIRED.
- Fresh execution window: REQUIRED.
- Operation 2: NOT_APPROVED / LOCKED / NOT_TRANSFERRED.
- Kill switch: ENGAGED. Bundle: UNMOUNTED. External/paid execution: false.
- Credential reads: 0. Budget reserved: 0 VND. Real provider calls: 0.
- Production business writes: 0. Actual cost: 0 VND. Production: NO-GO.

RC-18 and RC-17 remain immutable historical lineages. Their operation IDs, scopes, bundles, approvals, receipts,
windows, ledger namespaces and reservation state were not transferred or reused.

## Validation and acceptance

- PR #67 candidate CI `34877142919`: 5/5 PASS.
- Exact-main CI `34916352282`: Python/API/worker/bridge, Studio, Renderer, Safety/Compose and Docker E2E all PASS.
- G-08 audit, JSON, Markdown links, checksums, secret scan and `git diff --check`: PASS.
- Main/RC executable-tree equality and canonical dual-CI collector: PASS.
- ASR: 0/2 PASS. Vision: 2/2 PASS. Production: NO-GO.

## Evidence and historical drafts

- [B5G closure evidence](../../../evidence/v3-01/vf-v0s-b5g-20260915-rc19-provenance-closure/README.md)
- [Machine-readable handoff](handoff.json)
- [PR #67](https://github.com/vangnguyen/npd-video-factory-v2/pull/67): MERGED exact reviewed head.
- [Exact-main CI](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34916352282): PASS 5/5.
- PR #66 remains OPEN/DRAFT and is classified `SUPERSEDED_HISTORICAL_DRAFT`; it was not merged, closed or deleted.
- B5 and older evidence remain in Git history without silent rewrite.

## Next safe action — recommendation only

Owner may assign `VF-V0S-B6 — RC-19 fresh durable ledger custody/bootstrap qualification` against the exact closed
governance baseline. Stop before ledger creation until that separate task is issued, and continue to stop before
Operation 1 rebind, authority/window, credential access, reservation or provider dispatch.
