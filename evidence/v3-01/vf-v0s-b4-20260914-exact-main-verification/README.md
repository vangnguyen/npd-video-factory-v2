# VF-V0S-B4 — exact-main verification

VERDICT: PASS. Controlled [PR #65](https://github.com/vangnguyen/npd-video-factory-v2/pull/65) merge of
exact approved head 40d8de37e8fb4294a478422ed4f5f546e815ef55.
Merge/main: dc8ff55322267dfe54674fa6c4003a899bf235ab.
[Exact-main CI 34869652973](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34869652973):
completed/success, 5/5 canonical jobs. No PR CI substitute.

New executable tree: 432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502.
The current main is not historical RC18. RC17/18 tags and old receipts stay immutable.
NEW_RC_REQUIRED = YES; FRESH_LEDGER_BINDING_REQUIRED = YES; FRESH_EXECUTION_WINDOW_REQUIRED = YES.
No new RC, execution ledger namespace, operation rebind, bundle, window or authority created.

## Evidence

- [Pre-merge exact-head G-08](premerge-g08.json): 20 reviewed files/blob identities and candidate CI.
- [Post-merge provenance](postmerge-provenance.json): exact source objects, real main CI/jobs, immutable tags.
- [Regression](regression.json): local/CI Python 1048, Studio 14, Renderer 14, migration/Flow/safety/Docker.
- [Read-only PostgreSQL regression](postgres-readonly-result.json): reuse 2 pre-existing B3 synthetic DBs, 9 negative cases, no writes.
- [Canonical CI excerpts](ci-log-excerpts.log): real main counts and disposable E2E recovery.
- [Preserved B3 optional download timeout](b3-optional-artifact-timeout.json): exact remote artifact digest, no CI cancellation or bypass.
- [SHA-256 manifest](SHA256SUMS.txt): exact current B4 evidence/tooling/canonical handoff bytes.
- [Canonical handoff](../../../docs/acceptance/v3-01/HANDOFF.md).
- [Offline source verifier](../../../docs/acceptance/v3-01/reviews/vf-v0s-b4/verify_postmerge.py).
- [SELECT-only PostgreSQL check](../../../docs/acceptance/v3-01/reviews/vf-v0s-b4/postgres_readonly_check.py).

## Historical checksum context

B3 original manifest remains unchanged. Its prior handoff hashes resolve at
dc8ff55322267dfe54674fa6c4003a899bf235ab; the B4 verifier reads those original Git blobs.
Do not rewrite B3 hashes to match the newer handoff. This pack has a separate manifest.
Old B3 source/candidate artifacts do not substitute for new exact-main CI.
The optional B3 local archive-copy timeout is preserved; all canonical jobs and
required uploads actually succeeded. No full local archive copy is required by
the current five-job CI/provenance contract.

## Reproduction and stop

Run the existing canonical algorithm through the offline verifier, with a configured
non-secret Python environment and repository source on PYTHONPATH:

```text
python -B docs/acceptance/v3-01/reviews/vf-v0s-b4/verify_postmerge.py --repo <repository> --verify-manifest
```

This verifier does not access credentials, ledgers, budget, provider, deployment or authority.
The separate PostgreSQL check is SELECT-only on the documented existing synthetic
B3 test databases, not final custody for any future RC.

RC18 execution material: HISTORICAL_REFERENCE_ONLY / INVALID_FOR_CURRENT_MAIN.
Operation 1 authority: NOT_CREATED_FOR_CURRENT_MAIN. Operation 2: NOT_APPROVED / LOCKED / NOT_TRANSFERRED.
Kill switch ENGAGED, bundle UNMOUNTED, external/paid execution FALSE.
Credential reads / live reservation / provider calls / production business writes: 0.
Actual cost: 0 VND. ASR 0/2 PASS; Vision 2/2 PASS; Production NO-GO.

This governance-only handoff update requires its own Owner review before merge.
NEXT_SAFE_ACTION: Owner assign VF-V0S-B5 — fresh RC materialization from the verified main.
STOP before RC creation/rebind/future ledger/window/authority/credential/reservation/provider.
