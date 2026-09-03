# Flow A real-media run review

Use one copy for each run. Do not infer a PASS from a provider response, successful render or an
aggregate result. Every evidence path and SHA-256 must resolve to the exact run directory.

## Binding

| Field | Value |
|---|---|
| Run / slot | |
| Executable RC tag / commit | |
| Governance-main commit | |
| Source video SHA-256 / RightsRecord | |
| Source audio SHA-256 / RightsRecord | |
| Reference transcript SHA-256 | |
| Scene annotation SHA-256 | |
| Subject/reframe annotation SHA-256 | |
| Subtitle reference SHA-256 | |
| Expected-duration record SHA-256 | |
| Run-manifest SHA-256 | |

## Pipeline and thresholds

| Stage | Required result | Actual / evidence | Result |
|---|---|---|---|
| Upload | exact input hashes and rights PASS | | |
| ASR | WER <= 0.15; critical-term recall = 1.0 | | |
| Transcript | Vietnamese, native word/segment timestamps, complete mapping | | |
| Scene detection | boundary F1 >= 0.80 at 0.50 s tolerance | | |
| Silence decisions | every cut/keep decision traceable; no abnormal output silence | | |
| Highlights | selected intervals trace to transcript/scene evidence | | |
| Vision | subject/safe-crop evidence bound to exact frames | | |
| Smart reframe | safe subject coverage >= 0.95 | | |
| Subtitle | median drift <= 0.20 s; P95 <= 0.50 s; safe area PASS | | |
| Render | >=1080x1920; H.264/AAC 48 kHz; full decode; expected delta <=0.50 s | | |
| A/V parity | delta <=0.25 s | | |
| Visual QC | black <=0.10; freeze <=0.15; dark <=0.10; broken frames = 0 | | |
| Audio QC | silence <=0.80; peak from -35.0 to -0.05 dB | | |
| G-11 | exact final artifact `ACCEPT` | | |

## Integrity and safety

- [ ] All evidence paths are covered by the run checksum manifest.
- [ ] Provider calls, attempts, costs and receipts match the durable ledger.
- [ ] Duplicate external action protection passed.
- [ ] Secret/PII scan passed.
- [ ] No unapproved provider, retry, fallback, deploy, publish or public ingress occurred.
- [ ] Missing values remain missing; no evidence was reconstructed.

## Decision

```text
RUN VERDICT: PASS / REVIEW_REQUIRED / FAIL
MACHINE REASONS:
HUMAN NOTES:
REVIEWER:
REVIEWED AT UTC:
EVIDENCE SHA-256:
ACCEPTANCE AXIS CHANGE: NONE UNTIL OWNER-APPROVED EVIDENCE MERGE
PRODUCTION: NO-GO
```
