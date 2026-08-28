# V3-01-04 — Flow A closure checkpoint

## Decision

V3-01-04 implements the fail-closed Flow A acceptance plane and passes local contract/mock tests.
It does **not** close production acceptance. Repository verdict remains `NO-GO` because no real ASR,
Vision or production Vietnamese voice provider was called, no production-like path ran and no owner
accepted an exact final video after full watch.

The checkpoint is based on exact merged `main`
`4779ddcb1af5cc0138922ea144ddf4496fc313f1`. The locked code-only remediation commit used by the
redacted evidence is `88e6bcce22bf31bb3f23547c1d4d4a445abc0407`.

## Implemented

### Provider preflight before ASR and Vision

- ASR and Vision provider contracts now declare execution class, paid status, credential alias and
  estimated VND cost.
- `AutoEditAnalysisService` and `VisionAnalysisService` call the central provider safety controller
  before invoking an adapter.
- A future external adapter is stopped by the global kill switch or missing owner gates before its
  method can make a network call.
- Local fixtures still run with a zero-VND receipt. Contract-only adapters still return
  `PROVIDER_NOT_CONFIGURED`.
- The persisted provider provenance includes a secret-free safety receipt.
- Basic upload labels such as `owned` are not silently promoted into a complete G-03 rights
  approval record.

### Flow A acceptance contract

The strict runtime model and policy contract require exactly two chronological, distinct-input runs
on the same locked code commit. The evaluator computes rather than trusts these thresholds:

| Metric | Required value |
|---|---:|
| Source duration | at least 90 seconds |
| Source frame | at least 1080 x 1080, real audio, Vietnamese speech |
| ASR word error rate | at most 15% |
| Names, numbers and CTA | 100% present |
| Scene-boundary F1 | at least 0.80 within 0.5 seconds |
| Reframe safe coverage | at least 95% |
| Subtitle median drift | at most 0.20 seconds |
| Subtitle P95 drift | at most 0.50 seconds |
| Cost currency | VND only |

It also checks input and media rights IDs, provider request/artifact hashes, provider receipts,
timeline-to-approval hash binding, full decode, black/silent/frozen-frame checks, A/V sync, restart
recovery, production-path status and final-video-to-human-review hash binding.

Fixture evidence cannot be reclassified as real-provider evidence. Changing the locked code commit,
input identity, approval timeline or final video invalidates the corresponding acceptance claim.

## Evidence and axis result

Evidence run: `vf-v3-01-20260828T010641Z-88e6bcc`.

| Axis | Result | Meaning |
|---|---|---|
| Implemented | PASS | strict contract, evaluator and runtime preflight exist |
| Mock-tested | PASS | two redacted deterministic contract runs meet measured thresholds |
| Real-provider-tested | BLOCKED | G-01/G-02/G-03 pending; zero real calls |
| Production-path-tested | BLOCKED | G-04 pending; zero deploy/public-ingress change |
| Quality-accepted | BLOCKED | G-11 pending; no human full-watch approval |
| Overall V3-01-04 | BLOCKED | not a production closure or release candidate |

The fixture runs are intentionally synthetic and contain no customer PII. Their placeholder hashes
and rights IDs are contract-test inputs, not claims that the corresponding real assets exist. The
recorded cost is 0 VND, external actions are zero and publishing is false.

Reproduce the evaluator result:

```powershell
python scripts/v3_01_flow_a_acceptance.py `
  evidence/v3-01/vf-v3-01-20260828T010641Z-88e6bcc/flows/flow-a-upload-auto-edit/two-run-contract.json `
  --expect-verdict BLOCKED
```

## Test coverage

- external ASR is blocked before adapter invocation and before cost recording;
- external/paid Vision is blocked before adapter invocation and before cost recording;
- local ASR/Vision receipts are persisted as zero-VND and non-external;
- fixture-to-real evidence promotion is rejected;
- locked-commit and distinct-input rules;
- ASR WER and critical Vietnamese term measurement;
- scene F1, reframe and subtitle drift thresholds;
- timeline approval hash, technical QC and restart recovery;
- separate real-provider, production-path and human-quality axes;
- VND-only cost contract;
- API-only regression: 133 tests passed on the code-only commit.
- Final local regression: 177 Python API/worker/ComfyUI tests, 14 Studio tests and 14 Renderer
  tests passed; Renderer typecheck/bundle, migration upgrade/downgrade/replay and deterministic
  Docker E2E also passed.

GitHub CI and Docker E2E must pass again on the final draft PR head. Local PASS is not merge or
runtime authorization.

## Open gaps

- `V3-01-GAP-003` stays `OPEN`: no owner-approved production ASR/Vision adapter or real-media
  evidence.
- `V3-01-GAP-005` stays `OPEN`: no accepted production Vietnamese voice and licensed music mix.
- `V3-01-GAP-016` stays `OPEN`: no designated reviewer completed artifact-bound full-watch
  acceptance.
- `V3-01-GAP-010` and `V3-01-GAP-011` stay `IN_PROGRESS`: durable provider safety and quarantine
  are not production-like accepted.

## Gates and exact continuation

This branch may be pushed and opened as a draft PR under G-00. A new explicit G-08 is required to
merge it. G-08 would authorize only a repository merge unless the owner separately grants more.

To resume real Flow A acceptance later:

1. choose the exact ASR, Vision and production TTS adapters without storing credentials in Git;
2. record G-01 least-privilege credential aliases, G-02 VND limits and G-03 owned/licensed input,
   B-roll and music RightsRecords;
3. lock the release candidate, isolated production-like topology, backup and rollback under G-04;
4. run two distinct owned inputs consecutively without code changes and retain provider/job/hash,
   cost, timing, retry and failure-path evidence;
5. render and technically QC both exact outputs;
6. obtain G-11 only after desktop/mobile and headphone/phone-speaker full-watch review binds each
   final SHA-256;
7. update the matrix and gaps without inferring one acceptance axis from another.

No credential activation, external/paid provider call, deployment, public ingress, publish or
production analytics action is authorized by this checkpoint.
