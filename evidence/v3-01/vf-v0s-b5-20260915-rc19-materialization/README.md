# VF-V0S-B5 — RC-19 materialization

Task verdict: REVIEW_REQUIRED. Fresh RC materialization and independent RC CI passed; actual dual-CI
governance closure is blocked by the existing distinct-main/nonempty-diff contract.

Exact main/new RC commit: `dc8ff55322267dfe54674fa6c4003a899bf235ab`.
Canonical executable tree: `432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502`.
Annotated `vf-v3-01-rc19` tag object: `09a9a51628ab2e33d4ee85a1620f7afca692d18e`.
[RC CI 34875483864](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34875483864): 5/5 PASS.
[Main CI 34869652973](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34869652973): 5/5 PASS.

## Evidence

- [Pre-tag metadata](pre-tag-live-metadata.json), [preflight](pre-tag-preflight.json)
- [Post-tag metadata](post-tag-live-metadata.json), [source/hash qualification](post-tag-source-verification.json)
- [Tag annotation](tag-annotation.json), [tag origin](tag-origin.json)
- [Independent RC CI/jobs/artifacts](rc-ci.json), [safe CI excerpts](ci-log-excerpts.log), [Renderer excerpts](renderer-log-excerpts.log)
- [Real dual-CI rejection](dual-ci-blocked.json), [focused validation](focused-validation.json)
- [Verbatim B4 main provenance](b4-main-provenance-source.json):
  original SHA `f08e979daba7d4049d5840a71c2aa99d7f3c9f165dc3b60df9e83ee61ddc6246`,
  from PR #66 exact head `71609bdb691ceabb9cc1b4ee3175260a28132395`; not substituted RC CI.
- [SHA-256 manifest](SHA256SUMS.txt)
- [Canonical handoff](../../../docs/acceptance/v3-01/HANDOFF.md)

## Reproduction and gate boundary

Canonical algorithm: SHA-256 of sorted compact UTF-8 JSON mapping the exact 12 executable paths to Git object IDs,
using unchanged `app.provider_ci_provenance.executable_tree_sha256`. Exact inputs, component blob hashes,
independent clean-worktree recomputations and GitHub equality are retained.

```text
PYTHONPATH=<clean-RC19-source>/apps/api python -B <governance-worktree>/docs/acceptance/v3-01/reviews/vf-v0s-b5/verify_rc19.py \
  --repo <clean-RC19-source> --second-clean-repo <clean-dc8ff553-source> \
  --metadata <pack>/post-tag-live-metadata.json --b4proof <pack>/b4-main-provenance-source.json --after-tag
PYTHONPATH=<governance-worktree>/apps/api python -B <governance-worktree>/docs/acceptance/v3-01/reviews/vf-v0s-b5/audit_evidence.py \
  --repo <governance-worktree> --verify-manifest
python -B <clean-RC19-source>/scripts/v3_01_ci_provenance.py --repo <clean-RC19-source> \
  --executable-rc-commit dc8ff55322267dfe54674fa6c4003a899bf235ab \
  --governance-main-commit dc8ff55322267dfe54674fa6c4003a899bf235ab \
  --executable-rc-ci-run-id 34875483864 --governance-main-ci-run-id 34869652973
```

Actual canonical collector: exit 2, BLOCKED_0_CALL / CI_PROVENANCE_INVALID. Actual governance paths: empty.
No trusted provenance SHA is claimed for the invalid contract. The task does not change the schema,
invent paths, substitute PR CI, or automatically merge the separate governance draft.

Required next gate: Owner G-08 controlled governance-only merge, successful fresh merged-main CI and
canonical RC19/main dual-CI closure. A docs-only merge does not require another RC if executable tree stays identical.
Stop before ledger creation, Operation 1 rebind or authority.

Naming metadata is only a sequence-1 preview. No actual instance/namespace, operation ID, scope, bundle,
approval, authority or window was created. RC-18/RC-17 remain immutable. Historical receipts remain unchanged.
PR #66 remains an unmerged historical draft. B3 prior handoff hashes resolve to their original main Git blobs.

Provider credential reads, real provider calls, runtime ledger writes, live reservation and production business
writes: 0. Actual cost: 0 VND. Isolated existing tests/CI use disposable fixtures only.
Kill switch: ENGAGED. Bundle: UNMOUNTED. Operation 2: LOCKED.
ASR: 0/2 PASS. Vision: 2/2 PASS. Production: NO-GO.
