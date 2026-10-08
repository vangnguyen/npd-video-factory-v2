# Native storyboard full media QC

New storyboard renders carrying the existing `production_quality` policy now
run the shared `FullProductionQC` inspector after native transport, render
profile, narration placement and trailing-silence checks. Source-footage QC
retains its existing consumer. Accepted artifacts, legacy reports and verified
render checkpoints are never rewritten or upgraded by assertion.

## Measured checks

The inspector measures encoded duration, dimensions, frame rate, codec, audio
format, A/V timing, black and frozen frames, silence and clipping. It fully
decodes the output and samples actual FFmpeg signalstats luminance. These CPU
samples do not establish semantic Vision, speech intelligibility or licensing.

The native consumer additionally binds the inspected bytes to the frozen
approved document, canonical timeline version/SHA, actual render manifest,
selected source hashes, voice WAV hash, contiguous rendered scene intervals and
frame counts. The manifest records the actual voice file and subtitle layout.
Explicitly planned image intervals use the same intentional-still exemption as
the shared renderer. Video intervals, including frozen or looped footage,
receive no image exemption.

## Subtitle pixels

Each ASS cue must match its saved centisecond timing and have a visible 30-fps
output frame. Local FFmpeg/libass renders the same subtitle file onto a
transparent canvas at an interior frame. Actual alpha-channel glyph and outline
bounds must lie inside the brand's saved safe rectangle. Evidence consists of
PNG masks, hashes, cue indices, timestamps and measured bounds. Vietnamese text
uses the actual ASS font/rendering path. No OCR, paid model, estimated text box,
fabricated confidence or word alignment claim is used.

Processing has bounded ASS/caption/output sizes, per-mask and aggregate
timeouts, and rechecks subtitle and output hashes. Failed checks write explicit
`failed_qc` reports and fail the job without publishing a successful render
checkpoint. The native queue now recognizes both source-footage and storyboard
QC failures as `failed_qc`.

## Artifacts and recovery

Successful render checkpoints include the original `transport-qc-report.json`,
the combined `qc-report.json`, `full-qc-report.json` and every `subtitle-qc/*.png`
alongside the existing final video, timeline, ASS, manifest and voice artifacts.
Checkpoint replay verifies all hashes, including subtitle evidence, and returns
the exact original JSON result. It does not resynthesize audio. Backup/restore
preserves these files and immutable metadata.

Legacy renders without the quality policy retain their existing checks and
make no full-QC claim. Existing cached renders without the new full report
remain legacy evidence; reading them does not certify these new checks.

## Acceptance evidence and limits

`scripts/north_star_native_storyboard_qc.py` exercises real signed-fixture human
HTTP, image/video ingestion, a technology channel, saved MediaPlan application,
canonical edits, the native queue/worker, FFmpeg render, libass masks, full QC,
job events, cost records, backup/restore and separate-process checkpoint replay.
The isolated positive render is 1080x1920, 30 fps and 3.3 seconds. The negative
case renders actual frozen MP4 footage and ends in `failed_qc`, with no success
checkpoint. Earlier failed rehearsal roots/logs are retained.

Audio is an explicitly cached 1.2-second synthetic sine-wave fixture. Runtime
verification and voice inference are isolated fixture substitutions; provider
results, final video and QC results are not manually injected. There are zero
provider or paid operations. The visual preview remains a silent proxy and is
not eligible for final audible-preview acceptance. Fixture approvals are not
Owner UAT. Genuine scene voice quality, audible preview, semantic Vision,
independent rights validation, browser usability, external provider acceptance
and production deployment remain outstanding. The full North Star program
continues; this increment does not certify Mode A, Mode B or overall completion.

See `north-star/native-storyboard-full-qc-evidence.json` and the corresponding
entry in `NORTH_STAR_WAVE_REPORTS.md` for source hashes, test results and exports.
