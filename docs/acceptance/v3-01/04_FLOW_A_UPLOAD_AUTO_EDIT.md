# Flow A — Upload to Auto Edit

## Current result

`BLOCKED / CONTRACT-MOCK PASS / NOT RUN ON REAL MEDIA`

The repository has a deterministic upload, media-inspection, analysis, timeline, preview, subtitle,
audio, render and QC path. Main CI proves that path only with generated fixtures. V3-01 has not
received owner-approved source media, provider credentials, a production-like environment or a
designated human reviewer. No external provider was called in this audit.

V3-01-04 adds a fail-closed pre-call ASR/Vision safety boundary and a measured two-run evaluator.
The redacted evidence run `vf-v3-01-20260828T010641Z-88e6bcc` passes the implemented and mock-tested
axes on locked code-only commit `88e6bcce22bf31bb3f23547c1d4d4a445abc0407`. It intentionally
returns `BLOCKED` overall because G-01/G-02/G-03/G-04/G-11 and all corresponding real evidence are
absent.

## Acceptance contract

The controlled Flow A input is one owner-controlled vertical source video of about 90 seconds. A
valid acceptance run must preserve the source object and hash, produce an immutable artifact chain,
and prove:

1. upload validation, MIME/probe checks and malware/quarantine policy;
2. real ASR with word/segment timing and measured accuracy;
3. scene/silence/caption/safe-zone analysis;
4. an editable timeline and non-final proxy preview;
5. approved Vietnamese narration, subtitle readability and licensed audio;
6. a final 1080x1920 MP4 with pixel/luminance and decoded-audio QC;
7. no publish request and no source mutation.

## Current stage evidence

| Stage | Implementation | Current evidence | V3-01 decision |
|---|---|---|---|
| Intake/upload | Present with quarantine-before-decoder and clean-verdict promotion | deterministic API/E2E plus EICAR/archive/error tests | mock PASS; internal scanner/production NOT_TESTED |
| Source preservation | Present | object hash and immutable asset tests | mock PASS |
| ASR | fixture/contract plus fail-closed OpenAI adapter | measured deterministic fixtures, WER/critical-term checks, RC-12 response reach and V3-01-21 diagnostics | mock PASS; RC-12 validation failed; real-provider acceptance NOT_TESTED |
| Auto Edit analysis | Present | synthetic video tests | mock PASS |
| Vision/reframe | fixture/contract plus pre-call safety | measured scene F1/reframe coverage and zero-call receipt | mock PASS; real provider BLOCKED |
| Timeline/preview | Present | FFmpeg container E2E | mock PASS; human quality NOT_TESTED |
| Audio/subtitle/render | Present | measured subtitle drift, eSpeak and generated media | mock PASS; production voice NOT_ACCEPTED |
| Automated QC | Present | probe, black/silent/subtitle checks | mock PASS |
| Human full-watch | Not executed | none | BLOCKED |

## Planned bounded runs

- `FLW-A-01`: first owner-gated real-media run; evidence collection and defect discovery only.
- `FLW-A-02`: consecutive repeat on the same locked RC after all Flow A defects are remediated.

Both runs must use the same release candidate and a RightsRecord. Required pre-run gates are G-00,
G-01, G-02, G-03 and G-04 as applicable. The designated reviewer then supplies the artifact-bound
full-watch record for G-11. Any asset or timeline mutation invalidates the earlier preview, render
and quality approval.

## Stop conditions

Stop without retrying when a provider scope, budget, rights record, source ownership, credential
alias, human reviewer or production-like target is missing. A black, silent, corrupt, clipped,
mis-timed or unreadable result is `FAIL`, never a partial pass.

Open gaps: `V3-01-GAP-003`, `V3-01-GAP-005`, `V3-01-GAP-007`,
`V3-01-GAP-011`, `V3-01-GAP-013`, `V3-01-GAP-016`.
