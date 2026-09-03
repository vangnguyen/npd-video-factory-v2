# V3-01-19 Vietnamese TTS production gate design

## Decision boundary

```text
STATUS: DESIGN ONLY / ZERO CALL
PROVIDER OR VOICE SELECTED: NO
RUNTIME WIRED: NO
PROVIDER CALLS / CREDENTIAL READS / RESERVATION / SPEND: 0 / 0 / 0 VND / 0 VND
TTS REAL-PROVIDER / PRODUCTION-PATH / HUMAN-QUALITY: NOT_TESTED
DEPLOY / PUBLISH / PUBLIC INGRESS: NO / NO / NO
PRODUCTION: NO-GO
```

The target is a native Vietnamese female voice that is young, warm, soft and natural, with no
foreign accent or robotic cadence. It must pronounce Vietnamese and project names exactly, provide
controllable speaking rate, pauses and sentence rhythm, and remain suitable for short-form social
video. No candidate is approved by this design.

The canonical machine contract is
[`V3-01-19-VIETNAMESE-TTS-PRODUCTION-GATE.v1.json`](contracts/V3-01-19-VIETNAMESE-TTS-PRODUCTION-GATE.v1.json),
validated by [`tts-production-gate.schema.json`](schemas/tts-production-gate.schema.json).

## Candidate compatibility matrix

| Candidate | Vietnamese / female evidence | Deployment | Commercial-rights state | Control | Current result |
|---|---|---|---|---|---|
| Piper `vi_VN` voices | Vietnamese models listed; gender and human quality unverified | local/offline; GPU optional for inference | exact model card/license required | custom phoneme/lexicon pipeline | research only |
| Azure `vi-VN-HoaiMyNeural` | Vietnamese female voice officially listed; quality untested | cloud API/SDK | terms, region and data handling review required | SSML/phoneme/lexicon capabilities require exact vi-VN test | research only |
| Google Cloud vi-VN female voices | Vietnamese female voices officially listed; quality untested | cloud API | terms, project and data handling review required | SSML; exact dictionary/timing evidence unresolved | research only |
| OpenAI current speech model | Vietnamese native/female quality and phoneme controls unproven | paid API | terms and gate-specific lifecycle/price refresh required | instruction-based; native dictionary/alignment unproven | research only |
| Coqui XTTS-v2 | Vietnamese absent from inspected supported-language list | local/offline | current model terms do not establish commercial production use | cloning/custom pipeline | incompatible on current evidence |
| Owner-trained Vietnamese path | no model, corpus or voice yet bound | self-hosted | corpus/model licenses plus explicit biometric voice consent required | potentially highest control | research only |

The matrix separates API availability from production suitability. A free allowance is not a zero
cost authority. A local model is not automatically commercially licensed. A listed Vietnamese
voice is not human-quality acceptance. Any cloud or self-hosted candidate needs its own exact
provider/model/voice, credential or model artifact, rights, cost, privacy and operational gate.

Official evidence inspected for this design:

- [OpenAI GPT-4o mini TTS model](https://developers.openai.com/api/docs/models/gpt-4o-mini-tts)
  and [OpenAI model catalog](https://developers.openai.com/api/docs/models/all);
- [Azure Speech language and voice support](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support),
  [text-to-speech overview](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/text-to-speech),
  [pronunciation controls](https://learn.microsoft.com/en-ca/azure/ai-services/speech-service/speech-synthesis-markup-pronunciation)
  and [pricing](https://azure.microsoft.com/en-us/pricing/details/speech/);
- [Google Cloud voice list](https://docs.cloud.google.com/text-to-speech/docs/list-voices-and-types),
  [Text-to-Speech](https://cloud.google.com/text-to-speech) and
  [pricing](https://cloud.google.com/text-to-speech/pricing/);
- [Piper voices](https://github.com/rhasspy/piper/blob/master/VOICES.md),
  [Piper repository](https://github.com/rhasspy/piper) and
  [Piper training path](https://github.com/rhasspy/piper/blob/master/TRAINING.md);
- [Coqui XTTS-v2 model card](https://huggingface.co/coqui/XTTS-v2) and
  [XTTS documentation](https://github.com/coqui-ai/TTS/blob/dev/docs/source/models/xtts.md).

Catalog, licensing and price facts are time-sensitive and must be refreshed at the later owner
gate. This document records evidence for candidate screening, not a provider recommendation.

## Acceptance inputs

Two distinct Vietnamese scripts are prepared:

- [`V3-01-TTS-REFERENCE-SCRIPT-01.txt`](templates/V3-01-TTS-REFERENCE-SCRIPT-01.txt);
- [`V3-01-TTS-REFERENCE-SCRIPT-02.txt`](templates/V3-01-TTS-REFERENCE-SCRIPT-02.txt).

The exact proper-name and phrase list is
[`V3-01-TTS-PRONUNCIATION-SET.json`](templates/V3-01-TTS-PRONUNCIATION-SET.json). A later gate must
hash the scripts, pronunciation set, selected voice/configuration, output audio, cost/latency
receipt, RightsRecord and human review. It must not silently rewrite a script to hide a
pronunciation defect.

## Acceptance contract

Two distinct script outputs from the same pinned provider/model/voice/configuration are required.
Each output must meet all of these conditions:

- naturalness at least 4/5;
- pronunciation 5/5 and critical-term accuracy exactly 100%;
- prosody and artifact-freedom at least 4/5;
- no foreign accent, robotic cadence, stumble or swallowed syllable;
- duration deviation no more than 5% from the bound target;
- integrated loudness from -18 to -12 LUFS, true peak at most -1 dBFS and zero clipped samples;
- complete listening on headphones and a phone speaker;
- complete latency, actual-cost, provider/model/voice, output-hash, rights/consent and secret-scan
  evidence.

The later run must fail closed on any provider/model/voice mismatch, missing commercial license or
voice consent, price/FX/budget drift, input/pronunciation hash mismatch, receipt gap, quality
threshold failure, output-hash mismatch, secret finding, unauthorized retry or fallback.

## Owner gates before execution

The minimum sequence is `G-01-TTS -> G-02-TTS -> G-03-TTS -> governance G-08 -> exact-RC and CI
verification -> bounded operation authority -> G-11`. G-04 remains required before any claim of a
production-like path. Provider selection, live generation, deployment and publication are outside
this package.
