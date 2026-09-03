# V3-01 G-11 human quality gate

## Purpose and boundary

G-11 is the artifact-bound full-watch and full-listen decision for one complete video. Automated
QC, a successful provider call, a render exit code or an earlier review cannot substitute for it.
This checkpoint prepares the review instruments only; no video has been reviewed or accepted.

```text
G-11 STATUS: PENDING / NOT EXECUTED
DECISION: REVIEW_REQUIRED
ACCEPTED ARTIFACT: NONE
DEPLOYMENT OR PUBLISHING AUTHORITY: NONE
ACCEPTANCE AXIS PROMOTED: NO
PRODUCTION: NO-GO
```

The machine template is
[`V3-01-G11-HUMAN-QUALITY-REVIEW.template.json`](templates/V3-01-G11-HUMAN-QUALITY-REVIEW.template.json),
validated by [`human-quality-review.schema.json`](schemas/human-quality-review.schema.json). The
operator checklist is
[`V3_01_G11_HUMAN_QUALITY_CHECKLIST.md`](templates/V3_01_G11_HUMAN_QUALITY_CHECKLIST.md).

## Required artifact binding

Before review, record the exact release candidate and SHA-256 for the final video, timeline,
subtitle, voice, music, RightsRecord manifest and automated-QC receipt. Name the reviewer and
record UTC start/end times. Any later change to a bound artifact invalidates the entire G-11 review
and requires a new review ID; it is not permissible to copy the old decision.

## Required review contexts

The reviewer must:

- watch the exact complete video from first frame to last frame on a large/desktop display;
- watch the exact complete video on a mobile display;
- listen to the complete audio with headphones;
- listen to the complete audio through a phone speaker.

The machine record rejects `ACCEPT` unless all four contexts are confirmed.

## Review coverage

The 27 checks cover:

- **Visual:** corruption, black/frozen frames, face/subject crop, subject tracking, scene cuts,
  transitions, AI deformation/hallucination, text/logo/brand safe zones;
- **Subtitle:** transcript fidelity, Vietnamese spelling/diacritics, overflow, mobile safe area,
  measured median/P95 drift and readability;
- **Voice:** native Vietnamese, exact approved gender/profile, accent/cadence/stumbles, proper-name
  pronunciation and short-form rate/pause/rhythm;
- **Audio:** headphone and phone-speaker listening, voice/music balance, clipping/distortion,
  pumping/ducking/silence and agreement with loudness/peak QC;
- **Content and rights:** factual/policy/price claims, CTA/disclaimer, hallucination, complete
  RightsRecord coverage and absence of PII, credentials or internal/debug content.

Every non-pass result requires an artifact timestamp when applicable and a note. Automated metrics
remain linked evidence, not a replacement for listening or watching.

## Decision semantics

- `ACCEPT`: every check is PASS, all four review contexts are complete, all required hashes are
  present, the reviewer and UTC timestamps are recorded, and the canonical evidence SHA validates.
- `REJECT`: one or more observed defects make the artifact unsuitable under the accepted quality
  contract.
- `REVIEW_REQUIRED`: review or evidence is incomplete, ambiguous or awaiting a bounded owner
  decision.

G-11 only accepts the exact bound artifact. It does not authorize deploy, publication, public
ingress, production analytics or a broader provider capability. Those remain independent gates.

## Current readiness

The schema, JSON template and Markdown checklist are ready for a later real-media artifact. Every
template check remains `NOT_REVIEWED`, all artifact/reviewer fields remain null and the current
decision remains `REVIEW_REQUIRED`. No quality-accepted matrix row changes in this package.
