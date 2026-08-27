# Quality acceptance

## Verdict

`NOT ACCEPTED FOR PRODUCTION`

The current green CI proves deterministic contracts and mechanical media properties. It does not
prove commercial quality. No designated reviewer watched a real Flow A or Flow B artifact from
start to finish, and no artifact-bound owner approval exists.

## Automated baseline

The deterministic suite checks container rendering, MP4 probing, dimensions/codecs, black/silent
failure detection, decoded audio, subtitle timing/safe zones, immutable asset hashes and API
recovery. These checks remain necessary but cannot replace human review.

## Human review rubric

Each exact final-render SHA must be reviewed on desktop and phone, with headphones and a phone
speaker. A reviewer records PASS/FAIL for:

- first-frame and first-three-second clarity;
- absence of black/frozen/corrupt frames and unintended silence;
- Vietnamese pronunciation, cadence, naturalness, clipping and intelligibility;
- subtitle spelling, diacritics, timing, line breaks, contrast and safe zones;
- framing, tracking, reframe stability, visual continuity and brand suitability;
- factual claims, offer/call-to-action accuracy and required disclaimers;
- music/SFX balance and rights;
- correct aspect ratio, duration, bitrate/codec and platform compatibility;
- no PII, secret, internal path, debug overlay or unsupported watermark;
- overall publish readiness.

## Required evidence

`QLT-001` is the automated QC bundle for the exact hash. `QLT-002` is the signed human form naming
the reviewer, device/listening setup, start/end time, artifact hash and every rubric result. Two
consecutive Flow A and Flow B outputs on one locked RC must pass. Any input, asset, edit, audio,
subtitle or render change invalidates both records.

## Historical risks retained

Earlier Video Factory work showed that metadata-only checks can miss black or silent output and
that eSpeak Vietnamese is not a production voice. V3-01 therefore keeps pixel/luminance,
decoded-audio, measured subtitle/cue and human-listening gates mandatory.

Open gaps: `V3-01-GAP-005`, `V3-01-GAP-013`, `V3-01-GAP-016`.
