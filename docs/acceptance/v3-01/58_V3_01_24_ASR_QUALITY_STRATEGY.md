# V3-01-24 — ASR Quality Strategy & Candidate Architecture Review

Status: PROPOSED / OWNER G-08 PENDING. Research only, not model selection or execution authority.
Reference date: 2026-09-08. Production: NO-GO.

## Decision in one paragraph

Recommend **W1: the same bounded vocabulary prompt on whisper-1 for both approved inputs**
as the next *source-remediation proposal*, with W2 short domain context as a separately
reviewed alternative, never an automatic fallback. This is the lowest incremental-complexity
way to test terminology improvement while preserving the documented native-timing interface.
Its probability of achieving 8/8 is **UNKNOWN**, not measured or guaranteed.
Do not run either candidate now: the current adapter has no prompt contract, RC-15 authority
is retired, and positive-duration Flow A compatibility is still a separate blocker.
GPT transcription plus reviewed local alignment is deferred, not rejected.

Read the [model matrix](59_V3_01_24_ASR_COMPATIBILITY_MATRIX.md),
[alignment alternatives](60_V3_01_24_ALIGNMENT_ARCHITECTURE_OPTIONS.md) and
[machine-readable strategy](contracts/V3-01-24-ASR-QUALITY-STRATEGY.v1.json).
None is a gate bundle or an approval record.

## Exact post-PR #52 baseline

Owner G-08 authorized only head `c092827223406f0489ad1e57a414e073f371c3df`.
PR #52 merged into `5a8c96da6816ad6f424eaaa3952947738d4c49d5`.
[Exact-main CI 34241909331](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34241909331)
completed successfully, 5/5 jobs including deterministic Docker E2E. Local exact-main
Python/API/worker/bridge regression: 642 passed. Acceptance validation: 60 matrix rows,
16 gaps, 35 evidence runs. The strategy branch starts at that exact post-merge main.

[Read-only dual-CI collector output](evidence/v3-01-24-quality-strategy/post-pr52-ci-provenance.json)
binds RC-15 CI `34142662132` and post-merge CI `34241909331` to their distinct exact commits.
Its canonical provenance SHA is
`30405c8c46c1af687a97e626409c51d98bf79d6d7df717fa16e0592e04cf44e2`.

| Surface | RC-15 versus post-PR #52 main | Consequence |
| --- | --- | --- |
| Canonical runtime/executable projection | Both SHA-256 `9fab766b285eb2db580032b914eb2ccdf474d18b3958fd218a73a22fb75701e8` | No runtime/config drift |
| Offline evaluator source and evaluation schema under docs | Changed in #52 | Do not claim every executable source byte is unchanged |
| Strategy work package | Docs and offline guard tests only | No runtime wiring, new RC or authority |

The canonical projection is defined by
[provider_ci_provenance.py](../../../apps/api/app/provider_ci_provenance.py):
environment example, CI workflow, API app/pyproject, Studio, deploy/Compose, packages,
renderer, scripts, services and workflows; API tests and acceptance docs/evidence are
outside it. Its equality is not proof that offline evaluator code under docs is unchanged.
The post-#52 evaluator raw SHA is
`82c3871a6650cc2c473b614c275f91c27a8eff148141e97f757dff82e907cbdc`.
Future evidence must bind that evaluator identity separately from the provider runtime.

**RC creation requirement: PENDING_STRATEGY_DECISION.**
This review does not require or create a new RC. If W1/W2 request-profile support or any
alignment/runtime path is implemented, a separately reviewed executable change and new
locked RC are required before live acceptance. Even choosing unchanged W0 would not revive
retired RC-15 authority; evaluator/bootstrap identity and a fresh reviewed scope would still
need an explicit decision. No RC-16 tag is created here.

## Historical evidence remains authoritative

The [PR #52 forensic review](57_V3_01_23_ASR_CRITICAL_TERM_EVALUATOR.md) and
[immutable receipt manifest](evidence/rc15-asr-operation-1/manifest.json) remain unchanged:

- RC-15 Op1 provider/structured transcript/timestamp validation succeeded; 412 words,
  including 27 preserved provider boundary points.
- WER 9.6618% passes the 15% threshold; normalized critical-term recall is 5/8, therefore
  official acceptance remains FAIL, consumed, with actual cost 326.294996 VND.
- Three failures are provider misrecognition relative to the owner-confirmed reference:
  project-name substitutions, `thăm quan xa bàn`, and `chính xác bán hàng`.
- Decimal reconciliation removed a false formatting warning, not a language-quality failure.
  No historical receipt or reference is rewritten and no retrospective PASS is issued.
- RC-15 Op2 remains NOT APPROVED / LOCKED; ASR 0/2, Vision 2/2; Production NO-GO.

No independent acoustic listening or new provider result is claimed by this review.

## Candidate requests — design, not executable configuration

The inspected [adapter](../../../apps/api/app/auto_edit_providers.py) currently sends
model, language=vi, verbose_json, segment+word timestamp granularities and the file.
It sends **neither prompt nor temperature**. Its manifest/hash and Settings/gate/context
contracts accordingly have no prompt profile. An environment variable or bootstrap patch
cannot safely add a prompt behind that verified scope.

| Candidate | Exact proposed prompt | Controls held constant |
| --- | --- | --- |
| W0 | Absent; retained baseline only, no replay | whisper-1, vi, verbose_json, segment+word, temperature omitted |
| W1 | Ngọc Phương Đông, Vinhomes Green Paradise, Cần Giờ, tham quan sa bàn, chính sách bán hàng. | Same profile for both WAVs; no expected-answer transcript |
| W2 | Tư vấn bất động sản của Ngọc Phương Đông: Vinhomes Green Paradise tại Cần Giờ, tham quan sa bàn và chính sách bán hàng. | Same profile for both WAVs; alternative, not chained pass |

Whisper context can guide spelling/vocabulary; the guide describes a 224-token limit and
does not promise general instruction following. The candidate strings are proposed input
context, not commands to force output. Current documentation supports the timing use case;
it does not establish these prompts' quality on NPD audio.
[OpenAI file-transcription guide](https://developers.openai.com/api/docs/guides/speech-to-text).

Offline tests bound each draft prompt to 224 UTF-8 bytes and verify no customer data or
reference transcript is embedded. This byte check is **not an exact Whisper token count**.
Before a future gate, pin the multilingual Whisper tokenizer identity, verify actual token
length against the documented limit, reject excess rather than truncate, and bind exact
UTF-8 prompt hash/length plus tokenization evidence. No tokenizer/model weights are
downloaded or inference run here.

Keep temperature omitted for a clean W0/W1 comparison. If later proposed explicitly, it
requires its own bound request policy: temperature zero is not a determinism guarantee,
because the API describes provider-internal temperature adjustment. That is distinct from
the forbidden second client attempt or model fallback.
[Create transcription reference](https://developers.openai.com/api/reference/python/resources/audio/subresources/transcriptions/methods/create).

### Required future source contract

Use one canonical **ASR request profile** through Settings → verified gate/scope → call context
→ adapter request manifest/body → evidence. Bind profile ID, exact prompt bytes/hash, tokenizer
identity/count, language, format, granularities and explicit temperature omission/value.
Keep request-profile fields separate from money/timeout authority limits; operation authority
binds the resulting execution-scope and bundle hashes. Missing/tampered/overlong/unapproved
profiles fail before credential or budget boundaries. No code implementing this is in V3-01-24.

W1 can plausibly help the three spelling/recognition failures without changing requested
native timestamp fields, but this is a testable hypothesis. The output words/timestamps
may still change or contain boundary points; no timestamp stability or 8/8 guarantee follows.

## Quality experiment and bias controls

No candidate is executed. After source review, fresh RC/gates and explicit operation authority:

1. Freeze one profile before seeing new responses; use the same two exact WAVs and their
   own owner-confirmed references/8-term lists. Do not tune between consecutive runs.
2. Score the complete retained transcript using the unchanged read-only normalization:
   NFKC, casefold, punctuation/symbol boundaries and whitespace, retaining Vietnamese accents.
   Require contiguous full phrases: **8/8 for each asset**, WER ≤15%, completeness and valid timing.
3. Retain raw response hash, request/profile hash, nullable confidence, usage and separate
   media/billed duration, Decimal cost/ledger reconciliation and exact evaluator hash.
   Missing evidence is not zero or PASS.
4. Check *all occurrences*, not just phrase presence: compare insertion counts and mismatched
   audio spans against the reference, then require a human listen for suspect/new vocabulary.
   A hallucinated insertion fails even if it happens to produce 8/8.
5. Asset 02's retained reference contains none of the five W1 vocabulary terms. Using the
   same profile makes it an available **planned negative-insertion control** without inventing
   another asset. This is reference inspection, not a completed acoustic/provider test.
6. Two bounded assets do not establish production-general accuracy or calibrated insertion
   risk. A broader holdout set would require separate rights/consent and operation/budget gates.
7. Stop after each authorized attempt; Op2 is a separate owner decision. No automatic candidate
   sweep, retry, fallback or third operation. Offline design of W0/W1/W2 is not three API calls.

Never use fuzzy rescue, synonyms, embeddings, accent stripping, partial phrases, dictionary
rewrite, hidden substitutions or reference-as-answer prompting. Do not fix provider words
or timings after the call.

| Risk | Detection / stop condition |
| --- | --- |
| Prompt bias / unspoken names inserted | Asset-02 negative terms, occurrence-level audit and human audio comparison |
| WER worsens while terms improve | Full transcript WER/completeness gate unchanged |
| Partial phrase masks content error | Exact normalized contiguous token contract, still 8/8 |
| Native timing output changes | Full segment/word/source bounds and anchored-point validation, raw evidence retained |
| Provider evidence passes but edit pipeline cannot consume points | PositiveDurationTranscript blocks; separate downstream decision, no epsilon |
| Missing billing/usage or new request fields | Fail closed; no inferred zero cost or unchanged old scope |
| Generalization overstated | New quality and latency probabilities remain UNKNOWN |

## Cost and timing envelope — no new approval

The [current pricing table](https://developers.openai.com/api/docs/pricing) lists GPT-Transcribe
at 0.0045 USD/minute and GPT-4o-Transcribe at an estimated 0.006 USD/minute with token billing;
[Whisper's model page](https://developers.openai.com/api/docs/models/whisper-1) lists
0.006 USD/minute. Using the **previous accounting assumption**, not a newly approved FX rate,
27,000 VND/USD gives 162 VND/minute for Whisper and 121.5 for GPT-Transcribe.

At 180 seconds, modeled Whisper cost is 486 VND; GPT-Transcribe is 364.5 VND before any local
alignment resources. GPT-4o's estimated per-minute price is not a hard token-based bound.
A dual paid GPT-Transcribe + Whisper pass models 850.5 VND for 180 seconds, exceeding the old
500 VND/operation ceiling. Do not divide it into disguised sub-operations to bypass that gate.

W1 does not justify increasing the prior 500/1,250 VND or 90/120-second design automatically.
Revalidate price/FX and any billing-rounding policy for a future envelope. Media duration,
provider usage duration and ledger-rounded cost are distinct evidence fields. Prompt impact
on latency and quality is unmeasured; the old 12.17-second observation is not a future SLA.
No budget, deadline or authority is activated by these calculations.

## Ranked recommendation and owner decisions

| Rank | Candidate | Expected benefit (hypothesis) | Debt / required decision |
| --- | --- | --- | --- |
| 1 — recommended | W1, Whisper + bounded vocabulary | Target spelling errors with least architecture change; native timing interface retained | Canonical prompt-profile remediation, bias tests, new RC/gates; downstream point blocker remains |
| 2 — fallback proposal | W2, Whisper + short domain context | Test domain disambiguation if W1 is insufficient | More bias surface; separate owner-selected experiment, not automatic fallback |
| 3 — deferred | GPT-Transcribe + independently reviewed local alignment | Potential transcript quality improvement plus explicit derived timing | New adapter/receipts/alignment/rights/license/OOV/quality/cost/deadline evidence |
| Deferred further | GPT-4o or dual-pass architecture | Alternative quality or timing source | No NPD superiority proof; native timing incompatibility or cross-consistency/cost complexity |

This ranking is engineering judgment, **not a measured probability that W1 is the most accurate**.
There is no evidence to assign any candidate a numeric 8/8 success probability.

- **G-01:** future W1 keeps provider/model but rebinds exact new RC and request profile. GPT models
  or alignment capability require explicit new selection, never fallback.
- **G-02:** rebind prompt-aware scope, price/FX/cost receipt and 90/120 envelope; any dual-pass
  accounting or local-alignment envelope needs a separate decision. No budget carry-over.
- **G-03:** same WAV/reference hashes may be reused after rights/expiry/context-scope revalidation;
  no replacement media is inherently necessary. Alignment processor/derived artifact use needs
  an explicit rights review; new assets require their own record/consent. Publishing/training/resale
  remain forbidden. No new RightsRecord or approval is fabricated in this PR.
- **Next exact step:** Owner G-08 for this strategy package **and explicit candidate decision**;
  then a narrow zero-call prompt-profile remediation if W1 is chosen, separate G-08, exact-main,
  new RC, fresh operation IDs/window/scope/bundle and G-01/G-02/G-03, then separate Op1 authority.
  Strategy merge alone is not approval for that implementation or call.

## Delivery boundary

New artifacts are docs and offline tests; the existing evaluator, provider/runtime/config,
ledger, timestamp domain models and historical receipts are untouched by this package.
Provider calls=0; credential reads=0; live reservations=0; spend=0 VND.
No bundle mount, automation, new authority, RC tag, deploy, publish or public ingress.
Validation results are recorded in the Draft PR on its exact head. **STOP AT OWNER G-08.**
