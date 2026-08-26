# Idea Intelligence — V2-03

Idea Intelligence converts one scored TrendCluster into multiple original content directions and
ranks them for planning. It is deterministic in V2-03, persists every draft and its evidence, and
never performs production execution.

## Input and output

Input includes the trend cluster, source evidence, channel, niche, business objective, audience,
CTA, optional VND budget and requested idea count. Each `IdeaCandidate` returns:

- title, distinct angle and hook concept;
- format and recommended duration;
- visual concept, audience and CTA concept;
- source references as metadata only;
- originality notes and a structured brief;
- estimated `IdeaScore`, component values and rationale;
- durable draft/selected state and provenance.

The six deterministic strategies cover myth reframing, data explanation, action checklist,
before/after comparison, a clearly labeled hypothetical case and expert questions. Their angle,
hook and visual treatment are intentionally different. References guide research; the new script,
structure, narration and visuals must be independently created.

## Evidence classes

- `verified_fact`: a provider-supplied claim with source, retrieval time, confidence and freshness.
- `creative_framing`: the proposed storytelling angle, never represented as a verified fact.
- `uncertain_claim`: explicitly listed for later verification; the fixture path currently emits
  none rather than inventing claims.

## Estimated idea score

The 0–100 estimate includes hook strength, trend relevance, originality, audience fit, visual
potential, feasibility, expected retention, shareability and monetization potential, with cost,
saturation and policy-risk penalties. The API always returns `estimated=true` and a rationale
stating that no observed performance is claimed.

## Content Opportunity Queue

Queue refresh scores ideas for one channel/context, blends 72% IdeaScore and 28% TrendScore,
persists a stable ranked run and returns only `proposed` items. Replaying an identical state returns
the same queue item IDs. PostgreSQL recovery tests prove the latest queue survives API/repository
restart.

## Create Project boundary

Selecting an idea creates or reuses one project and its initial immutable version. The snapshot
contains the source idea, evidence references and this approval contract:

```json
{
  "human_required": true,
  "approved": false,
  "publish_enabled": false
}
```

The project remains `draft`; there is no implicit video job, paid call, media download or publish.
Repeated selection is idempotent.
