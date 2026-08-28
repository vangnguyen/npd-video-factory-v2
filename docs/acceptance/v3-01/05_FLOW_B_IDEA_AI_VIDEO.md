# Flow B — Idea to AI-assisted video

## Current result

`CONTRACT / MOCK PASS; OVERALL BLOCKED`

V3-01-05 adds a strict acceptance contract and deterministic evaluator for the complete Flow B
chain. Two secret-free fixture runs on code commit
`2563dfd4735fd24497fd285d40e2173093c0a351` pass the contract/mock axis. This is not
real-source, real-provider, production-path or human-quality evidence.

The overall V3 verdict remains `NO-GO`. G-01, G-02, G-03, G-04 and G-11 remain pending. External
and paid execution are disabled, budget is `0 VND`, the global provider kill switch is engaged,
credentials are unused, and no deployment, public ingress or publication occurred.

## Acceptance contract

One owner-approved business brief must produce a traceable chain:

`brief -> sources -> claim map -> script version -> storyboard -> media plan ->`
`licensed/generated assets -> Vision QC -> TTS -> subtitles -> music/ducking ->`
`timeline -> preview -> hash-bound approval -> final render -> technical QC`.

The checked-in policy is
[`flow-b-acceptance.v1.json`](../../../packages/contracts/flow-b-acceptance.v1.json). The evaluator
is `apps/api/app/flow_b_acceptance.py`; the offline validator is
`scripts/v3_01_flow_b_acceptance.py`.

## Quantitative mock checks

| Check | Contract threshold | Fixture result |
|---|---:|---:|
| Research sources | at least 3 per run | 3 / 3 |
| Script claim-to-source coverage | 100% | 100% / 100% |
| Verified script-claim coverage | 100% | 100% / 100% |
| Maximum originality similarity | at most 0.30 | 0.24 / 0.22 |
| Storyboard-to-media-plan coverage | 100% | 100% / 100% |
| Visual-asset shot coverage | 100% | 100% / 100% |
| Rights and receipt completeness | 100% | 100% / 100% |
| Minimum visual relevance | at least 0.80 | 0.88 / 0.89 |
| TTS duration deviation | at most 5% | 3% / 2% |
| Subtitle median / P95 drift | at most 0.20s / 0.50s | 0.18s / 0.36s; 0.17s / 0.34s |
| Integrated loudness | -18 to -12 LUFS | -15.0 / -15.2 LUFS |
| True peak / clipping | at most -1 dBFS / zero samples | -2.0 / -2.1 dBFS; zero |
| Speech-to-music ratio / ducking | at least 6 dB / required | 8.0 / 8.2 dB; applied |
| Minimum final render | 1080 x 1920 | 1080 x 1920 both |
| Timeline and render-input approval | exact SHA-256 binding | PASS / PASS |
| Restart recovery and technical decode/QC | required | PASS / PASS |
| Cost | VND-only ledger | 0 VND |

These values belong to synthetic contract fixtures. They establish evaluator behavior, not video
quality or provider capability.

## Acceptance axes

| Axis | State | Reason |
|---|---|---|
| Implemented | PASS | strict model, policy, evaluator, CLI and negative tests are present |
| Mock-tested | PASS | two consecutive locked-commit fixture bundles meet all quantitative thresholds |
| Real-provider-tested | BLOCKED | G-01/G-02/G-03 are pending; all sources and providers are fixtures |
| Production-path-tested | BLOCKED | G-04 is pending; no production-like staging run |
| Quality-accepted | BLOCKED | G-11 is pending; no designated human full-watch on exact final hashes |

## Evidence and reproduction

Evidence bundle:
[`vf-v3-01-20260828T033515Z-2563dfd`](../../../evidence/v3-01/vf-v3-01-20260828T033515Z-2563dfd).

```powershell
python scripts/v3_01_flow_b_acceptance.py `
  evidence/v3-01/vf-v3-01-20260828T033515Z-2563dfd/flows/flow-b-idea-ai-video/two-run-contract.json `
  --expect-verdict BLOCKED
```

## Stop conditions

Unsupported claims, excessive similarity, incomplete storyboard/media coverage, unknown rights,
missing provider or asset receipts, provider/model drift, low visual relevance, TTS/subtitle/audio
threshold failure, unbound approvals, restart failure, render-QC failure or non-VND cost data stops
the run. Fixture output can never be promoted to real-provider or real-source evidence.

Open/in-progress gaps remain `V3-01-GAP-002`, `V3-01-GAP-004`, `V3-01-GAP-005`,
`V3-01-GAP-013` and `V3-01-GAP-016`. This checkpoint does not close any of them.
