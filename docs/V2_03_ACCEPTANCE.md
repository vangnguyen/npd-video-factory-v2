# V2-03 Trend Radar & Idea Intelligence acceptance

Date: 2026-08-26. Branch: `feat/v2-03-trend-idea-intelligence`, based on approved `main` after
PR #2 (`ec377b66cbe60fdb73eb28abad7e67c1d097391e`). This increment is review-only until owner
approval. It does not merge, tag or deploy production as part of implementation.

## Acceptance contract

- [x] provider-agnostic `TrendSourceProvider` interface;
- [x] one legal, synthetic, deterministic fixture provider for local/CI;
- [x] live-provider contracts visibly `not_configured`;
- [x] normalized signals preserve unavailable metrics as `null`;
- [x] source snapshots, evidence, clusters, scores, ideas and queue persist in PostgreSQL;
- [x] deterministic clustering, seven-state lifecycle and stable IDs;
- [x] configurable, explainable estimated opportunity score;
- [x] six genuinely distinct idea strategies and explainable IdeaScore;
- [x] ranked, idempotent Content Opportunity Queue and restart recovery;
- [x] responsive Trend Radar Studio with eight views and draft-project selection;
- [x] no creator-media download, scraping bypass, paid call, publish or autonomous execution;
- [x] API package, worker and renderer version aligned to `0.4.0`;
- [ ] GitHub CI evidence attached to the draft PR after push.

## Deterministic scenario

The fixture contains eight signals over four topics and six source types. With
`as_of=2026-08-26T08:00:00Z`, the three-source “AI video cho bất động sản” topic is classified
`breakout`. The acceptance flow collects eight signals, creates four clusters, generates six
distinct draft ideas, ranks six proposed queue entries and creates one draft project. Missing
Google Trends/RSS engagement metrics remain `null`.

## Test matrix

| Layer | Evidence |
|---|---|
| Python | repository/service/API tests for collection replay, null metrics, clustering, lifecycle, scoring, idea diversity, queue recovery, draft project and fail-closed providers |
| Migration | Alembic `upgrade head -> downgrade base -> upgrade head` |
| Studio | Node tests for eight views, filtering, ranking and VND/lifecycle formatting; JavaScript syntax check |
| Renderer/worker | all existing V2-01/V2-02 regression tests |
| Compose E2E | video render/QC plus Trend -> Ideas -> Queue -> Draft Project, Studio/CSP and API restart recovery |
| Safety | secret scan, independent runtime, localhost bindings, research-only provenance and `git diff --check` |

## Owner gates and intentional limits

Green CI is not merge authorization. This remains a draft PR until explicit owner approval. No
production deployment is requested. Live trend credentials, API authentication/RBAC, paid calls,
publishing, learned ranking, performance feedback and human Vietnamese voice acceptance remain
separate future gates.
