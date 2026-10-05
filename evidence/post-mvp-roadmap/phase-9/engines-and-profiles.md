# Phase 9C, 9D, 9E, 9H — sourced research, candidates and transparent scoring

PHASE: 9C — RESEARCH ENGINE

STATUS: PASS for implemented source-URL research; practical human usefulness acceptance pending.

HEAD SHA: Parent `2d819c9`; implementing commit accompanies this evidence in Git history.

FILES CHANGED: `research.py`, engine tests, actual-source preflight logs and case-01 evidence.

TESTS: Ten domain/engine tests PASS. Actual HTTPS retrieval from Vinhomes Market produced one retained source, three exact source-reported quotations and one unresolved finding. Actual primary-source government retrieval also succeeded with publication metadata. Initial Vingroup/Vinhomes root domains returned HTTP 403: these failures are preserved, with no invented replacement. Alternate explicitly selected Market URLs are used in configured cases. An intermediate discovery log has a console encoding error while printing Vietnamese titles; the subsequent ASCII-escaped result distinguishes successful retrieval from that output failure.

EVIDENCE: `actual-source-discovery-3.log`, `case-01.json`, original failed preflight logs, actual retained source HTML/text/receipts under `C:\NPD-Video-Factory\phase2\research-sources`.

NEW CAPABILITIES: ResearchProvider abstraction, explicit query/context, bounded public HTTPS retrieval with public-IP pinning and redirect validation, bounded gzip support, immutable source capture, quote validation and distinct SOURCE_REPORTED/INFERENCE/UNRESOLVED contracts. Source-reported is not independently verified truth. Retrieval dates do not substitute for publication dates. No source discovery/search popularity metrics are claimed.

REGRESSIONS: Native 121/121 (103 existing + 18 intelligence), Studio 31/31 (27 existing + 4 intelligence) PASS at this checkpoint. A small gzip retrieval addition is covered by actual government retrieval; repeat regression will follow final UI/guard adjustments.

BLOCKERS: Human usefulness acceptance and full end-to-end practical production remain pending.

NEXT ACTION: Finish Studio and real ten-case review.

---

PHASE: 9D — IDEA ENGINE

STATUS: PASS for candidate generation contract and one actual existing-provider case; ten-case acceptance pending.

HEAD SHA: Parent `2d819c9`; implementing commit recorded with this evidence.

FILES CHANGED: `idea_engine.py`, engine tests and `case-01.json`.

TESTS: Actual existing OpenAI `gpt-6-luna` request returned exactly five distinct structured candidates. Reference validation ties each candidate to source-backed findings and their actual source IDs. Unit paths reject unknown/unsourced references, missing candidates and duplicated titles. Test doubles are labeled test fixtures, not actual provider integration.

EVIDENCE: `practical-initial.log`, `case-01.json`; actual request/response/intent are retained outside Git under `phase2/intelligence-operations/<operation_id>`.

NEW CAPABILITIES: Research + frozen brand/channel profile → five candidates with title, hook, angle, audience, format, duration, CTA, evidence, key points and rationale. No automatic selection. Existing credential/model reused; no new provider or credential. Provider errors/unknown outcomes refuse automatic replay.

REGRESSIONS: Supported baseline tests PASS.

BLOCKERS: Human candidate selection and brief approval required for practical production.

NEXT ACTION: Display ranked candidates and editable briefs.

---

PHASE: 9E — IDEA SCORING

STATUS: PASS for HEURISTIC_SCORING; not statistically predictive.

HEAD SHA: Parent `2d819c9`; implementing commit recorded with this evidence.

FILES CHANGED: `idea_scoring.py`, scoring configuration and engine tests.

TESTS: All ten component scores, weights, total, rationale, scoring timestamp and config hash persisted for five actual candidates. Risk is inverted as a penalty; zero/invalid weights are refused. Unknown publication timestamps conservatively reduce freshness/evidence scores instead of inventing recentness.

EVIDENCE: `engine-tests.log`, `case-01.json`.

NEW CAPABILITIES: Configurable editorial ranking across ten requested dimensions, with disclosed lexical/date/length/format/CTA proxies. No learned weights, analytics or conversion forecast.

REGRESSIONS: No production pipeline replacement.

BLOCKERS: Ranking usefulness requires actual human evaluation.

NEXT ACTION: Let humans compare, select, edit, reject and regenerate.

---

PHASE: 9H — NPD INITIAL CONFIGURATION

STATUS: PASS for configuration support; practical cases are separate pending gates.

HEAD SHA: Parent `2d819c9`; implementing commit recorded with this evidence.

FILES CHANGED: `profiles/intelligence.json`, `profiles/intelligence-cases.json`.

TESTS: Config parsing/scoring tests PASS; first configured case retrieved actual source and generated five actual candidates. Four profiles and ten case inputs are configuration, with no project names encoded in core models/logic.

EVIDENCE: Config files, engine tests, actual case-01.

NEW CAPABILITIES: Green Paradise, Saigon Park, Vang Nguyễn and general Vietnam property profiles with audiences, formats, channels, CTA choices, tone, durations, keywords and references. Profile and scoring snapshots are frozen per research run.

REGRESSIONS: Existing production branding/preset catalogs are preserved.

BLOCKERS: No official brand assets supplied; profiles are internal editorial configuration, not proof of affiliation or project claims.

NEXT ACTION: Execute the configured 3/2/2/3 ten-case mix and request concrete human review.
