# G-11 human quality checklist

## Binding before review

- [ ] Record the exact release-candidate commit and final video SHA-256.
- [ ] Bind timeline, subtitle, voice, music, RightsRecord manifest and automated-QC SHA-256 values.
- [ ] Confirm the reviewer and record UTC start/end timestamps.
- [ ] Confirm that any later change to a bound artifact invalidates this review.

## Visual — full watch on desktop and mobile

- [ ] Watch from first frame to last frame without skipping.
- [ ] No corrupted, black, frozen or undecodable frame.
- [ ] No face or material subject is cropped incorrectly.
- [ ] Reframe follows the subject without jitter or unsafe crop.
- [ ] Scene cuts and transitions are intentional and defect-free.
- [ ] AI media has no obvious deformation, hallucination or continuity defect.
- [ ] Text, logo, colors and safe zones match the approved brand artifact.

## Subtitle

- [ ] Content matches the approved spoken transcript.
- [ ] Vietnamese spelling and diacritics are correct.
- [ ] No overflow, clipping or mobile safe-area violation.
- [ ] Measured median drift is at most 0.20 s and P95 drift is at most 0.50 s.
- [ ] Size, contrast, line breaks and dwell time are readable on a phone.

## Voice

- [ ] Vietnamese sounds native and natural.
- [ ] Gender and voice profile match the exact approved voice.
- [ ] No foreign accent, robotic cadence, stumble or swallowed syllable.
- [ ] Every bound proper name and project name is pronounced correctly.
- [ ] Rate, pause, emphasis and sentence rhythm suit short-form video.

## Audio — complete listen twice

- [ ] Complete listen with headphones.
- [ ] Complete listen through a phone speaker.
- [ ] Voice remains intelligible above music and effects.
- [ ] No clipping, distortion, pumping, ducking defect or abnormal silence.
- [ ] Loudness and true peak match the exact automated-QC receipt.

## Content and rights

- [ ] All factual, price, policy and project claims match approved evidence.
- [ ] CTA and required disclaimer are exact.
- [ ] No unsupported or hallucinated statement, visual or audio claim.
- [ ] All sources, media, music, voice, logos and transformations have bound RightsRecords.
- [ ] No PII, credential, internal path, debug overlay or unsupported watermark.

## Decision

Choose exactly one: `ACCEPT`, `REJECT`, or `REVIEW_REQUIRED`. Record every failure with an artifact
timestamp and note. `ACCEPT` is invalid without all bound hashes, completed device/listening passes,
all checks `PASS`, a named reviewer, UTC timestamps and a deterministic evidence SHA-256. G-11 does
not itself authorize deployment or publishing.
