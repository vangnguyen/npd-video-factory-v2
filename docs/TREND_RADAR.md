# Trend Radar — V2-03

Trend Radar is a research and prioritization layer for NPD Video Factory V2. It accepts only
public, licensed or explicitly authorized metadata providers, normalizes their signals, groups
related topics and produces explainable opportunity estimates. It does not scrape around access
controls, download creator media, publish content or call a paid provider in normal development
and CI.

## Data flow

```text
TrendSourceProvider
  -> immutable collection snapshot
  -> normalized trend signals + research evidence
  -> deterministic topic clusters
  -> lifecycle + context-specific opportunity score
  -> Trend Radar Studio
  -> Idea Engine -> ranked Content Opportunity Queue
```

PostgreSQL owns all snapshots, signals, evidence, clusters, scores and queue state. Redis remains
the transient video-job queue only; Trend Radar does not put canonical research data in Redis.

## Provider contract

Every adapter implements `collect_signals`, `search_topic`, `get_topic_metrics` and
`get_content_reference`. Provider SDKs and credentials stay inside adapters. Core clustering and
scoring code depends only on normalized contracts.

| Provider key | V2-03 state | Intended access |
|---|---|---|
| `fixture-trends` | `healthy` in dev/CI | bundled synthetic metadata only |
| `youtube-data-api` | `not_configured` | authorized YouTube Data API |
| `tiktok-authorized-api` | `not_configured` | approved TikTok research/API access |
| `google-trends-authorized` | `not_configured` | authorized trends data provider |
| `meta-content-library` | `not_configured` | Meta-approved research API |
| `public-rss` | `not_configured` | explicit public-feed allowlist |

`not_configured` is a real fail-closed state. The API never substitutes fixture data for a live
provider and never fabricates missing provider metrics. Set `TREND_FIXTURE_ENABLED=false` for any
production environment; startup rejects an enabled fixture in `APP_ENV=production`.

## Normalized signal and evidence

A signal records source/reference, observation time, country/locale/language, topic/keyword,
hashtags, media/format and nullable metrics such as views, engagement, velocity and acceleration.
An unavailable metric remains `null`. The source reference is research metadata; the fixture and
repository provenance explicitly record `creator_media_downloaded=false`.

Each signal has evidence with claim, summary, source reference, retrieval time, confidence and
freshness. The idea layer stores verified evidence separately from creative framing and uncertain
claims.

## Clustering and lifecycle

Normalization uses Unicode-aware tokens, exact normalized topic matching and a configurable
Jaccard fallback. A stable workspace/canonical-topic hash gives a repeatable cluster ID.

Lifecycle values are `discovered`, `rising`, `breakout`, `mainstream`, `saturated`, `declining`
and `expired`. Rules use only available observed time, velocity, acceleration, platform spread and
saturation inputs. They are deterministic and covered by fixed-time fixtures.

## Explainable opportunity score

The estimated 0–100 score combines velocity, acceleration, cross-platform spread, engagement
quality, novelty, channel/format fit and monetization fit, then applies saturation, competition,
rights and policy penalties. Every component and weight is returned by the API. Weights are part
of the score profile hash, so different channel/niche/objective contexts remain distinguishable.
The score is a planning estimate, not observed performance or a promise of reach or revenue.

## Studio views and filters

The local Studio at `http://localhost:3000` provides eight views: Trending now, Rising fast,
Breakout, Early signals, Cross-platform, Low competition, High monetization and Near saturation.
It also exposes platform, market, language, niche, channel, objective and search controls; trend
detail with score components and source links; idea generation; a ranked queue; and draft-project
creation. The responsive UI is served by its own local-only Nginx container and proxies only
`/api/` to the V2 API.

## Intentional limits

- No general web crawler, protection bypass, transcript copier or media downloader.
- No live provider is claimed configured in V2-03.
- No recommendation automatically becomes a script, render, publish or ad action.
- No authentication/RBAC yet; the Studio and API remain localhost-only and non-production.
- No learned ranking or performance feedback loop; scores are deterministic estimates.
