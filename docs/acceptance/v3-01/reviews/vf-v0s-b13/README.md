# VF-V0S-B13 — RC-20 materialization and dual-CI boundary

Verdict: **REVIEW_REQUIRED**. RC-20 was materialized and independently
qualified, but the current governance main cannot close canonical dual-CI
provenance because it is the same commit as the RC. This review/evidence update
is governance-only; it grants no operation, ledger, bundle or provider authority.

## Exact baseline and sequencing

- Remote `main` before and after tagging:
  `93b5441d44347c9c40b745bdfed0969880853f68`.
- Exact-main push CI
  [35123204511](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/35123204511):
  5/5 PASS, including Docker deterministic E2E; main-only provenance PASS.
- Canonical `app.provider_ci_provenance.executable_tree_sha256` over the 12
  required Git object IDs recomputed twice as
  `611450db8b70b67c39090dc245a86465cc9a5bdb542f732b9bde0c7e289e1630`.
  Git's full tree object is `e01d009650ae4e9b249d75d4d416053cdfacdfc4`.
- Remote V3-01 RC tags formed the uninterrupted sequence RC-1 through RC-19;
  no RC-20 tag existed before this task. Historical RC-19 annotated tag object
  `09a9a51628ab2e33d4ee85a1620f7afca692d18e` still resolves to
  `dc8ff55322267dfe54674fa6c4003a899bf235ab`.
- The exact main includes `app.provider_single_dispatch.run_single_dispatch`
  from `apps/api/app/provider_single_dispatch.py` (Git object
  `a61a035d7b8e60be61581ce5d9d59028e2715688`, dispatch marker protocol
  version 1) and bootstrap `python -m app.provider_runtime_bootstrap`.
  Checked-in provider defaults remain fail-closed.

## RC-20 result

Annotated `vf-v3-01-rc20` tag object
`9fe8d77a6c58a31beccf38bc2cc72b71a8dac240` was pushed without a source
commit. It peels to exact main `93b5441d44347c9c40b745bdfed0969880853f68`.
The tag message binds the executable tree, runner/bootstrap/provider-safety
Git objects, acceptance/provenance versions, W1 profile/prompt hashes and
same-release immutable MinIO digest. The tag and main have the same full Git
tree and the same canonical executable-tree hash; the worktree stayed clean.

Independent RC-bound workflow-dispatch CI
[35124578033](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/35124578033)
ran on ref `vf-v3-01-rc20`. Its head SHA and all five job head SHAs equal the
peeled RC commit. Python/API/worker/bridge, Studio, Renderer, Safety/Compose
and Docker deterministic E2E all completed successfully. RC-only provenance
is PASS; it does not grant live acceptance authority.

## Dual-CI remains open

The unmodified canonical `scripts/v3_01_ci_provenance.py` was run using RC CI
`35124578033` and exact-main CI `35123204511`. It returned
`CI_PROVENANCE_INVALID` / `BLOCKED_0_CALL`. RC-20 commit and current main are
identical, so `git diff RC..main` has zero changed paths. The current
`ProviderAcceptanceCiProvenance` schema requires both a distinct governance
main commit and at least one allowlisted governance path. No relaxation or
alternate proof was used. Thus `MAIN/RC DUAL-CI PROVENANCE = BLOCKED`, and
B13 cannot be marked PASS despite the successful tag and RC CI.

The deterministic first-lineage ledger preview (provider
`openai-transcription`, model `whisper-1`, capability `asr`, sequence 1) is
`al-0001-9722891b4ae68168375adea9fc53cc6ad89c20fa8f3c5d8535f056173f428624`;
its derived database name is
`vf_vf_v3_01_rc20_5ff19bf478b41d3580e486bb6e37279d`. This is **PLAN_ONLY**,
not a custody binding; it must be re-derived after governance closure. No
database, migration, operation ID, bundle, G-01/G-02/G-03 approval, authority,
window or reservation was created. RC-19 execution material remains historical
and invalid for RC-20. Operation 2 is locked; kill-switch default is engaged;
ASR remains 0/2 PASS, Vision 2/2 PASS, Production NO-GO.

See [structured RC evidence](rc20-lineage.json). Next action requires a new
Owner G-08 exact-head review and controlled governance-only merge, fresh
exact-main CI, then RC-20/main dual-CI provenance. Do not start B14 or any
provider preflight under this task. Credential reads, provider calls, budget
reservation, production business writes and actual cost were all zero.
