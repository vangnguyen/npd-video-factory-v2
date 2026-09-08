# V3-01-23 — ASR Critical-Term Accuracy & Evaluator Reconciliation Remediation

**DRAFT / OWNER G-08 PENDING / ZERO-CALL. Production: NO-GO.**

Base: `07e276f2ec69b2e0247899077537374f3d94f4b4` (PR #51 governance main).
Historical executable: `vf-v3-01-rc15` at `7d1290aacac61df98a51544731243e5e322a8644`.
This PR changes the offline evaluator, not provider/runtime/config, transcript models,
timestamp semantics, ledger or subtitle/reframe/scene pipeline. The evaluator is executable
source despite its `docs/` location; this is not a governance-only RC rebind.
No merge, RC-16, new operation, authority or window is created here.

## Outcome

The critical-term matcher is correct. Three phrases differ from the exact owner-confirmed
reference in six occurrences. No matching change is justified; 8/8 remains mandatory and
the retained transcript stays 5/8 FAIL. The independent reconciliation bug is fixed:
`Decimal("0.0000") == Decimal("0")`. Removing that false warning does not change overall FAIL.

## Source and reference audit

Three original receipts were imported byte-for-byte. The [manifest](evidence/rc15-asr-operation-1/manifest.json)
binds their raw hashes; replay verifies them before computing derived diagnostics. No original
receipt, reference, WAV, RightsRecord, bundle or scope is rewritten.

The [reference transcript](transcripts/g03-asr-vi-owned-01.txt) remains SHA-256
`585b460291f11f1eb54c2b9a728bca26953ccce98719859e16ab15c7af9ff36e`.
The [owner manifest](assets/V3-01-RC11-ASR-ASSET-MANIFEST.json) records prior confirmation
of speech/reference and consent for limited ASR acceptance. WAV SHA-256 remains
`fce31015644960a5f69640d7f5b90a7da078887b15c9d17dc227530d26b875ef`.
The forensic helper verifies those hashes and the reference file's terminal LF omitted
from the retained input string; every other character must match.

**No new acoustic listening/retranscription is claimed.** Classification is relative to
the owner-confirmed reference, not independent proof of pronunciation. A later contradictory
audio audit requires REVIEW_REQUIRED, not a reference edit to make historical output PASS.

## Critical-term forensic results

Word indexes are zero-based/inclusive across provider word objects; seconds are retained
values, not newly aligned timestamps.

| Expected | Provider phrase | Word indexes | Start–end seconds | Classification |
| --- | --- | --- | --- | --- |
| Vinhomes Green Paradise | Vinhome Bring Paradise | 76–78 | 18.700001–20.32 | PROVIDER_MISRECOGNITION |
| Vinhomes Green Paradise | ping home ring paradise | 280–283 | 79.040001–80.480003 | PROVIDER_MISRECOGNITION |
| tham quan sa bàn | thăm quan xa bàn | 159–162 | 45.139999–46.02 | PROVIDER_MISRECOGNITION |
| tham quan sa bàn | thăm quan xa bàn | 290–293 | 83.519997–84.279999 | PROVIDER_MISRECOGNITION |
| chính sách bán hàng | chính xác bán hàng | 185–188 | 53.18–53.84 | PROVIDER_MISRECOGNITION |
| chính sách bán hàng | chính xác bán hàng | 299–302 | 86.080002–86.879997 | PROVIDER_MISRECOGNITION |

[Forensic JSON](evidence/rc15-asr-operation-1/critical-term-forensic.json) includes exact/normalized
tokens, Unicode/case/diacritics/punctuation/whitespace, segment/local/global indexes, timing,
neighbors and nullable confidence. All reference occurrences are accounted for. No word
confidence was supplied: null remains null. Edit distance is diagnostic only.

These are content differences, not canonical equivalents: `tham/thăm`, `sa/xa`, `sách/xác`
and altered project names. `ping home ring paradise` is the provider's four-token output,
not an evaluator split bug. No evidence supports a reference/normalization/tokenization/
evaluator defect for these three terms; missing/unverified observations remain UNKNOWN.

## Matching contract — unchanged

Full contiguous normalized-token matching remains required. Existing normalization is
NFKC, casefold, punctuation/symbol boundaries to spaces and whitespace tokenization;
Vietnamese diacritics are preserved. Tests cover exact phrases and equivalent Unicode/case/
punctuation/space forms. Missing/reordered/inserted/duplicated/split/joined words, partial
phrases, wrong diacritics/project names and 7/8 or 5/8 fail; only 8/8 passes.
No fuzzy/synonym/embedding match, accent stripping, correction, provider prompt or model change.

## Numeric reconciliation — fixed

Old evaluator: outstanding reservation text had to equal `"0"`; `"0.0000"` falsely failed.
New evaluator: a canonical finite nonnegative Decimal parser handles reservation before,
outstanding reservation after and actual cost using numeric semantics, not raw strings.
Invalid text, booleans/floats, exponents, nonfinite/negative amounts and unsupported precision
fail closed. Missing cost/usage receipts never become zero/PASS. Actual above reservation,
reservation above 500 VND and window above 1,250 VND fail closed.

Normal evaluator inputs contain only ledger counts; aggregate amounts are explicitly
NOT_PROVIDED, never invented. A separate pure `reconcile_single_operation_ledger(input, ledger)`
checks the complete retained single-operation evidence: identities/day/currency/status,
one attempt, absent Op2, reservation/charge/budget equality and ceilings. Missing/multi-operation
records cannot produce aggregate PASS. It never opens PostgreSQL.

Provider actual cost stays **326.294996 VND**. Durable PostgreSQL `NUMERIC(20,4)` stores
**326.2950 VND**; the helper uses an explicit nonnegative half-up storage projection and exact
equality, not tolerance. Provider cost itself is not rounded/replaced. Operation-row
`reserved_vnd=500.0000` records historical reservation; budget-row `reserved_vnd=0.0000`
is outstanding reservation. Those fields are not interchangeable.

## Immutable history versus diagnostic recomputation

| Axis | Original RC-15 | New diagnostic only |
| --- | --- | --- |
| Provider / transcript / timestamps | SUCCESS / PASS / PASS | unchanged |
| WER | 40/414 = 9.6618%, PASS below 15% | unchanged |
| Critical terms | normalized 5/8 FAIL; exact 4/8 | unchanged |
| Outstanding reservation | false string-format warning | numeric zero PASS |
| Evidence completeness | false due to reconciliation | PASS |
| Retained full ledger | runner numeric reconciliation passed | explicit offline ledger check PASS |
| Overall acceptance | **FAIL** | **FAIL** |
| Consumed / actual cost | YES, succeeded / 326.294996 VND | unchanged |

[Comparison JSON](evidence/rc15-asr-operation-1/diagnostic-evaluator-comparison.json) retains old
reasons/hash and a separate new evaluation. No original is overwritten; no missing usage,
cost, confidence or transcript is reconstructed. No retrospective acceptance promotion.

Of 412 words, 27 remain adjacent-anchored boundary points. Timestamp evidence is PASS but
`downstream_positive_duration_ready=false`. `PositiveDurationTranscript` still blocks interval
consumers. No epsilon/duration invention/drop/swap/downstream projection is introduced.

## Validation and reproducibility

Focused tests cover matcher, money, original hashes, all six occurrence locations, immutable
inputs, deterministic replay and positive-duration boundaries. Full Python/API/worker/bridge,
Studio, Renderer, migrations, acceptance/Flow A, JSON/schema/checksum/link, secret/diff checks
and deterministic Docker E2E results are recorded with exact-head CI in the draft PR.

```bash
python docs/acceptance/v3-01/tools/v3_01_23_evidence_review.py
python -m pytest apps/api/tests/test_v3_01_23_critical_term_matching.py apps/api/tests/test_v3_01_23_critical_term_forensic.py apps/api/tests/test_v3_01_23_numeric_reconciliation.py apps/api/tests/test_v3_01_23_evidence_review.py -q
python scripts/v3_01_acceptance.py validate-repo
```

The review helper defaults to read-only verification. `--write` regenerates only three derived
artifacts after original-hash verification. The rolling offline-preparation manifest refreshes
current source/schema/document hashes; historical operation/gate evidence is not rewritten.

## Owner boundary

This work: **0 provider calls / 0 credential reads / 0 live reservations / 0 VND**.
Historical Op1 is consumed/succeeded, acceptance FAIL. Op2 stays NOT_APPROVED/LOCKED.
Vision 2/2 PASS; ASR 0/2; production NO-GO. No gap or production/human-quality axis is closed.

STOP at separate owner G-08 for this draft. Any later merge/exact-main/new-RC/gates/call follow
their own approval sequence. Critical-term accuracy remains unresolved; this fix does not
predict a new live PASS or authorize model/provider/prompt changes or another live attempt.
