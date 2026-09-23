# Master Lane B — Vietnamese TTS readiness (B1–B7)

This offline source candidate was reconciled on 2026-09-23 onto exact
post-PR #87 governance main
`56fc2c4ddcc0b220510051a5148d9ba913965357`. The RC-21 tag remains immutable
at `vf-v3-01-rc21` (`6dcf144a4e3830e27fd617e52bc8eeab0952126e`).
It is **not** RC-21 executable authority. Any executable-tree-changing merge
requires Owner Gate O1 and fresh lineage. The mock artifacts are non-speech
tones; they cannot satisfy a real voice or G-11 human acceptance decision.

## B1 — bounded candidate shortlist

No provider, model, or voice is selected or approved. This is a research
shortlist from official catalogs and already-supported repository paths as of
2026-09-17, not a license, deployment, or paid-call decision.

| Candidate | Verified catalog/repo fact | Readiness limitation |
| --- | --- | --- |
| Azure Speech `vi-VN-HoaiMyNeural` | [Microsoft lists Vietnamese and Female](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts). | No repository adapter; region, price, account terms, pronunciation, perceived age/timbre and latency untested. |
| Google Cloud `vi-VN-Neural2-A` | [Google lists Vietnamese and FEMALE](https://cloud.google.com/text-to-speech/docs/voices). | No repository adapter; human quality, project-name pronunciation, region and commercial/account terms untested. |
| OpenAI `gpt-4o-mini-tts` with existing `marin` configuration | [Current model page](https://developers.openai.com/api/docs/models/gpt-4o-mini-tts) lists speech generation; `apps/api/app/providers.py` already contains a gated `OpenAIVietnameseTTSProvider`. | Vietnamese-native and female-perceived 25–30 profile are unproven; output-token consumption and VND ceiling cannot be bound from script length alone. No credential inspection or API work in this lane. |

The repository's eSpeak path remains CI/dev only, not a production-quality
candidate. Piper, custom voice, and cloning are not in this bounded first
evaluation because exact model license, voice gender, corpus/consent and/or
human quality are unresolved. The prior V3-01-19 gate remains design-only.

## B2 — rights, privacy and commercial checks

- The two exact scripts and pronunciation list are bound by SHA-256 below. An
  Owner-reviewed RightsRecord is still needed for script/project-name claims,
  brand names, any music and final output; this package cannot confer rights.
- Prebuilt catalog voices are the only shortlist. No person's voice is cloned
  or trained. If a custom/personal voice is proposed later, obtain separate
  voice-talent consent and data-rights review. [Microsoft's TTS privacy
  guidance](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/speech-service/text-to-speech/data-privacy-security?view=foundry-classic)
  discusses voice-talent permission and biometric obligations.
- Cloud use means scripts leave the local environment. A future selection must
  bind account/project, processing region, retention/logging settings, DPA,
  permitted commercial use, disclosure and deletion policy. Microsoft states
  customer data is not used to improve Speech models and describes logging
  controls; [see its encryption/storage documentation](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-encryption-of-data-at-rest).
  [OpenAI's business-data statement](https://openai.com/business-data/) says
  API inputs/outputs are not used for training by default, while the exact
  account's retention controls remain to be verified. Google terms and actual
  TTS project data configuration need separate Owner/legal review.
- A synthetic-voice disclosure decision is required before public use;
  [Microsoft's transparency note](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/speech-service/text-to-speech/transparency-note)
  calls for disclosure. This is a risk checklist, not legal clearance.

## B3 — VND cost envelope, not reservation

For a reproducible *planning example only*, Google lists Neural2 at
[USD 16 per 1M billable characters](https://cloud.google.com/text-to-speech/pricing/).
The two unchanged NFC scripts each contain 245 Unicode characters including
their trailing newline. With a deliberately explicit, **non-live planning FX**
of 27,000 VND/USD and no free-tier deduction, `ceil(245 × 16 × 27000 / 1M)`
is **106 VND per output**, **212 VND for two**. This is not an exchange-rate
claim or a provider quote. SSML or rewritten inputs change billable length.

The *proposed, not authorized* limits are 500 VND/output and 1,250 VND for
the two-output window, one call per script, concurrency 1, retry 0, fallback
0. Before a real call, G-02 must bind the exact account/SKU, price timestamp,
live FX, submitted payload length, taxes/fees and budget ledger. Azure's
[public pricing page](https://azure.microsoft.com/en-us/pricing/details/speech/)
does not expose a stable account/region-specific amount in the inspected view;
OpenAI audio output tokens are unknown pre-generation. Neither candidate has
an executable VND estimate or spend authority here.

## B4/B6 — mock adapter and two-output harness

`app.tts_readiness.MockToneTTSAdapter` implements the existing `TTSProvider`
protocol and intentionally emits non-speech deterministic WAVs. Run
`python scripts/v3_01_tts_readiness.py --output-dir <outside-repo-path>` to
produce two exact mock outputs and a manifest. The harness checks distinct
scripts and outputs, SHA-256 input/output bindings, all critical terms across
the pair, WAV format, reproducibility, and no credential/network/provider
path. It neither changes `production_audio.py` nor selects a live provider.

| Input | SHA-256 | Characters | Mock output SHA-256 |
| --- | --- | ---: | --- |
| `V3-01-TTS-REFERENCE-SCRIPT-01.txt` | `57049c34389e2b6f582df2735baf2479edd20cd0e6ed270429d64404a1b91be5` | 245 | `b41431a28d99beac8543849c881489302636743bcf46dc26fea24c55b5583fd4` |
| `V3-01-TTS-REFERENCE-SCRIPT-02.txt` | `71d4a882588918c18efb72b612b3b2c181fb8c63257aec9dd97cdba56ad4a530` | 245 | `f5cd117b845bd44bcd7a47e3e45ac4814030481988d02bc04c1c55ad597b33dd` |

Pronunciation set SHA-256: `8b4d892ddf70050706727612ecfc55aaf63af2c5b028f5f2249640863a42f36d`.
Canonical mock manifest SHA-256: `26597cbef615fbae530f6f03ff243a14a0b62d9e56abaf59f03f0650f0548208`.

## B5/B7 — Vietnamese QA and G-11 listening package

The real-provider gate must use the **same pinned provider/model/voice/config**
for two different scripts and separately bind both audio hashes. The Owner
target is a female voice *perceived* as 25–30, soft, warm and professional;
catalog gender is not evidence of perceived age, accent or naturalness.

For each output, a named Vietnamese reviewer must complete full listening
through headphones and a phone speaker. Score naturalness ≥4/5,
pronunciation 5/5, prosody ≥4/5 and artifact-freedom ≥4/5. All eight critical
terms need exact human acceptance. Explicitly reject a foreign accent,
robotic cadence, swallowed syllables or incorrect project names. The existing
V3-01-19 gate also requires ≤5% duration deviation, -18 to -12 LUFS,
true peak ≤-1 dBFS, zero clipping, latency/cost receipts, RightsRecord,
secret scan and no unauthorized retry/fallback. Do **not** infer any of these
from the mock tone outputs.

The [`G-11 TTS listening template`](g11-tts-listening.template.json) binds
both future real audio hashes and reviewer/device checks but deliberately
leaves them null/NOT_REVIEWED. Final full-video G-11 remains the separate
27-check [`V3-01-G11` template](../../templates/V3-01-G11-HUMAN-QUALITY-REVIEW.template.json),
not replaced by this TTS subreview. Owner Gate O5 is mandatory for final
voice acceptance. O2 is mandatory before paid/provider/credential activity.

## Disposition

The offline preparation target is `READY_FOR_REAL_PROVIDER_EVALUATION`,
conditional on candidate CI/provenance and G-08 review of the exact PR head.
It is **not** `READY_FOR_PROVIDER_DISPATCH`, not a production voice, and not
an O2/O5 approval. All provider calls, credential reads, reservations,
production writes and actual cost remain zero.
