# RC-11 ASR operation evidence review

This form is a review template. Blank values are intentional and must not be inferred from an
operation status, provider response, log message or another acceptance run.

## Immutable binding

| Field | Evidence value |
|---|---|
| Operation ID | |
| Operation slot | |
| Executable RC tag | `vf-v3-01-rc11` |
| Executable RC commit | `207ff9fee5557eb0976f575c9263b61d995b20a0` |
| Governance-main commit | |
| Executable-RC CI run | |
| Governance-main CI run | |
| Provider / model / capability | `openai-transcription / whisper-1 / asr` |
| Language | `vi` |
| Bundle SHA-256 | |
| Execution-scope SHA-256 | |
| WAV path / SHA-256 | |
| Reference transcript path / SHA-256 | |
| RightsRecord path / canonical SHA-256 | |
| Critical-term set | |
| Acceptance window (UTC) | |

## Preflight

- [ ] Exact RC tag and commit verified.
- [ ] Dual-CI provenance and executable-tree equality verified.
- [ ] Bundle, scope, WAV, transcript, RightsRecord and approval hashes verified.
- [ ] Operation was unconsumed and had no prior ledger row before execution.
- [ ] The current time and UTC budget day were inside the bound window.
- [ ] Provider/controller timeouts were `90 / 120` seconds.
- [ ] Atomic reservation was at most 500 VND and the window ceiling was 1,250 VND.
- [ ] Attempts/concurrency/retry/fallback were `1 / 1 / 0 / 0`.
- [ ] Operation 2 remained locked.

## Provider execution evidence

| Field | Evidence value |
|---|---|
| Provider execution | `SUCCESS` / `FAILED` / `NOT_DISPATCHED` / `UNKNOWN_POSSIBLY_SENT` |
| Attempt count | |
| Retry / fallback count | |
| Provider request ID | |
| Client request ID | |
| Request SHA-256 | |
| Response SHA-256 | |
| Native provider duration | |
| Input/source duration | |
| Usage/duration receipt | |
| Actual cost VND | |
| Reservation before / after reconciliation | |
| Latency milliseconds | |
| Timeout class / phase | |
| Provider error type/code/message (redacted) | |

## Transcript evaluation

| Check | Result | Evidence / notes |
|---|---|---|
| ProviderTranscript mapping complete | | |
| Vietnamese language matches | | |
| WER at most 0.15 | | |
| Critical-term exact recall = 1.0 | | |
| Critical-term normalized recall = 1.0 | | |
| Word timestamps valid | | |
| Segment timestamps valid | | |
| Timestamp transcript coverage sufficient | | |
| Provider/source duration parity | | |

Attach the machine-readable output produced by
`docs/acceptance/v3-01/tools/v3_01_asr_post_run_evaluator.py`. Preserve the original provider
transcript and source receipt separately; the evaluator output does not replace either artifact.

## Durable safety and evidence integrity

| Check | Result | Evidence / notes |
|---|---|---|
| Durable operation ledger | | |
| Consumed/succeeded state | | |
| Budget-day record | | |
| Circuit state | | |
| Duplicate operation blocked | | |
| Canonical evidence serialization | | |
| Primary/fallback evidence writer | | |
| Source evidence SHA-256 | | |
| Evaluation SHA-256 | | |
| Secret scan | | |
| Gate unmounted and runner stopped | | |

## Verdict

Choose exactly one:

- `PASS`: provider execution succeeded, transcript thresholds pass and required evidence is complete.
- `REVIEW_REQUIRED`: the result cannot be safely promoted because evidence is incomplete or the
  provider result is uncertain/failed without an objective transcript failure.
- `FAIL`: a measured acceptance threshold or a mandatory safety control failed.

```text
PROVIDER EXECUTION:
ACCEPTANCE VERDICT:
MACHINE REASONS:
OPERATION CONSUMED:
OPERATION 2 STATUS: NOT APPROVED / LOCKED
ACCEPTANCE AXIS CHANGE: NONE UNTIL EVIDENCE-ONLY PR AND OWNER G-08
PRODUCTION: NO-GO
REVIEWER:
REVIEWED AT UTC:
NOTES:
```
