# CODEX MASTER SPEC — NPD VIDEO FACTORY V2
## Independent AI-Native Content Opportunity, Production, Publishing & Learning Platform

**Document status:** Single Source of Truth
**Replaces:** All prior Video Factory V2 implementation prompts/spec fragments
**Target repository:** `vangnguyen/npd-video-factory-v2`
**Source repository to audit:** `vangnguyen/npd-ai-video-factory`

---

# 0. EXECUTIVE DIRECTIVE

You are implementing **NPD Video Factory V2** as an independent production-grade system.

This is **not** just a video renderer, a script-to-video demo, or an Agent Hub feature.

The target is an **AI-native autonomous content opportunity and video production platform** that can:

1. discover trends and emerging opportunities;
2. generate and rank original content ideas;
3. research and create scripts/storyboards;
4. analyze uploaded media;
5. use Vision AI;
6. source licensed stock media;
7. generate AI images and AI video;
8. execute ComfyUI workflows;
9. automatically edit video;
10. expose an editable timeline in Auto Edit Studio;
11. create previews;
12. require human approval before production actions by default;
13. render production-quality final video;
14. publish through supported official platform APIs;
15. collect normalized analytics;
16. detect winning content patterns;
17. feed performance back into Trend Radar and Idea Intelligence.

The system must support two first-class operating modes.

## MODE A — Autonomous Content Factory

```text
SOCIAL / WEB SIGNALS
        ↓
    TREND RADAR
        ↓
 TREND CLUSTERING
        ↓
 OPPORTUNITY SCORING
        ↓
     IDEA ENGINE
        ↓
    IDEA RANKING
        ↓
 RESEARCH / EVIDENCE
        ↓
 SCRIPT / STORYBOARD
        ↓
   MEDIA PLANNING
        ↓
 STOCK / AI IMAGE / AI VIDEO / USER LIBRARY
        ↓
     VISION AI
        ↓
      AUTO EDIT
        ↓
       TIMELINE
        ↓
       PREVIEW
        ↓
  HUMAN APPROVAL
        ↓
       RENDER
        ↓
         QC
        ↓
      PUBLISH
        ↓
     ANALYTICS
        ↓
 WINNER DETECTION
        ↓
  LEARNING LOOP
        └────────────→ TREND / IDEA ENGINE
```

## MODE B — Auto Edit Studio

```text
UPLOAD VIDEO
      ↓
AI TRANSCRIPT
      ↓
SCENE DETECTION
      ↓
SILENCE REMOVAL
      ↓
HIGHLIGHT DETECTION
      ↓
SMART REFRAMING
      ↓
DYNAMIC SUBTITLE
      ↓
B-ROLL
      ↓
VOICE / AUDIO PROCESSING
      ↓
MUSIC DUCKING
      ↓
EDITABLE TIMELINE
      ↓
PREVIEW
      ↓
HUMAN APPROVAL
      ↓
FINAL RENDER
      ↓
PUBLISH
      ↓
ANALYTICS
```

---

# 1. IMPLEMENTATION RULES

Do not stop at architecture proposals.

**Implement working code.**

Work through small, reviewable pull requests with explicit acceptance criteria.

Do not merge to `main` without owner approval.

Do not deploy to production without a separate owner approval.

Do not disrupt the existing Agent Hub production environment during extraction.

Do not restart or mutate the current production instances of:

- Agent Hub;
- n8n;
- Caddy;
- EspoCRM;
- PostgreSQL;
- existing shared Redis;
- existing video services.

Do not rewrite source repository history.

Do not blindly merge legacy PR #6 or PR #8 into the old repository.

Audit and selectively port useful video code into V2.

If repository-creation permission is unavailable:

1. perform the extraction into an independent workspace/repository layout;
2. create valid Git commits locally;
3. document the permission blocker;
4. give the exact final command/action required to create/push the repository;
5. continue all safe implementation work.

---

# 2. SOURCE BASELINE AUDIT

Before changing architecture, inspect:

```text
current main
PR #6 — Add production pilot TTS and asset preflight
PR #8 — Complete Sprint 1 AI video vertical slice
```

Create:

`docs/MIGRATION_AUDIT.md`

Classify each existing component:

```text
KEEP
PORT
REWRITE
DEPRECATE
DROP
```

Audit at minimum:

```text
apps/api/
services/worker/
services/agent_hub/
renderer/
packages/contracts/
workflows/n8n/
examples/
storage/
docker-compose
GitHub Actions
Redis job state
video manifest
TTS providers
Remotion renderer
FFmpeg/FFprobe QC
asset resolver
subtitle timing
production pilot code
```

For every migrated component record:

- source repository;
- source commit SHA;
- source PR if applicable;
- source path;
- decision;
- reason;
- V2 destination path.

**Do not migrate `services/agent_hub` into V2.**

---

# 3. SYSTEM BOUNDARY

## Agent Hub

Agent Hub is a **control plane**.

Its concerns include:

```text
campaign orchestration
marketing operations
CRM
attribution
provider health
business analytics
approval orchestration
command center
```

## Video Factory V2

Video Factory is a **media execution and content intelligence plane**.

Its concerns include:

```text
trend intelligence
idea intelligence
research
video projects
media ingestion
transcription
vision
generation
editing
rendering
publishing
video analytics
learning
```

The systems must:

- not share databases;
- not import each other's internal Python/JS packages;
- not read/write each other's Redis namespaces;
- not depend on shared process memory.

Integration is only through:

```text
versioned REST API
signed webhook
versioned event contracts
```

Video Factory must operate normally even if Agent Hub is unavailable.

---

# 4. MULTI-NICHE CORE

Do not hardcode real-estate assumptions into core pipeline logic.

V2 must support multiple niches through configuration.

Core domain configuration includes:

```text
ChannelProfile
NicheProfile
BrandKit
ContentTemplate
VideoTemplate
PublishingProfile
AnalyticsProfile
```

Example niches:

```text
real_estate
technology
AI
education
knowledge
story
comedy
entertainment
product_review
affiliate
news_explainer
custom
```

Adding a niche should primarily require new configuration/templates, not core engine changes.

---

# 5. TARGET REPOSITORY LAYOUT

Suggested structure:

```text
apps/
  api/
  studio-web/

services/
  orchestrator/
  trend-worker/
  research-worker/
  ingest-worker/
  transcription-worker/
  vision-worker/
  edit-worker/
  media-worker/
  comfyui-bridge/
  render-worker/
  publishing-worker/
  analytics-worker/

renderer/
  remotion/

packages/
  contracts/
  timeline/
  media/
  providers/
  templates/
  scoring/
  shared/

workflows/
  comfyui/
  n8n/

infra/
  docker/
  gpu/
  migrations/

storage/
  fixtures/

examples/

tests/
  contracts/
  unit/
  integration/
  e2e/
  media/
  publishing/
  analytics/

docs/
```

Do not create a single god service.

---

# 6. CORE INFRASTRUCTURE

## Metadata database

Use PostgreSQL.

## Queue / transient state

Use a Video-Factory-owned Redis instance or isolated deployment.

Do not use Agent Hub state directly.

## Media and artifact storage

Create `ObjectStorageProvider`.

Local development may use MinIO.

Production must support S3-compatible object storage.

The production architecture must not depend on a single local filesystem.

## Rendering

Use:

```text
Remotion
FFmpeg
FFprobe
```

## GPU execution

ComfyUI is a separate optional GPU execution service.

Support:

```text
local GPU
remote GPU worker
cloud GPU
```

without modifying core business logic.

If GPU generation is unavailable, the main platform must remain healthy and expose generation capability as degraded/unavailable.

---

# 7. CORE DOMAIN MODEL

At minimum implement:

```text
User
Workspace
ChannelProfile
NicheProfile
BrandKit

TrendSource
TrendSignal
TrendSnapshot
TrendCluster
TrendTopic
TrendEvidence
TrendScore

IdeaCandidate
IdeaVariant
IdeaScore
IdeaBrief
IdeaExperiment
ChannelOpportunity
ContentQueueItem

VideoProject
ProjectVersion

SourceAsset
GeneratedAsset
StockAsset

Transcript
TranscriptSegment
TranscriptWord

Scene
Shot
Highlight

MediaPlan
MediaPlanItem

Timeline
TimelineVersion
Track
Clip
Transition
Effect
Keyframe

VoiceTrack
MusicTrack
SubtitleTrack

RenderJob
RenderArtifact
QCReport

Approval
ApprovalComment

Publication
PublicationAttempt

MetricSnapshot
AnalyticsReport
WinnerAssessment

ProviderUsage
CostRecord

Job
JobEvent
WebhookDelivery
```

Important entities require:

```text
immutable ID
created_at
updated_at
version
source/provenance
workspace ownership
```

---

# 8. DURABLE JOB STATE MACHINE

Example high-level states:

```text
created
→ collecting_signals
→ opportunity_scoring
→ idea_generation
→ researching
→ planning
→ uploading
→ uploaded
→ analyzing
→ media_planning
→ generating_media
→ draft_timeline
→ preview_rendering
→ awaiting_review
→ approved
→ rendering
→ ready
→ publishing
→ published
→ analytics_active
```

Additional states:

```text
failed
failed_qc
cancelled
needs_attention
changes_requested
```

Requirements:

- progress monotonic within stage;
- resumable after worker restart;
- expensive operations idempotent;
- stable error codes;
- every transition auditable.

---

# 9. TREND RADAR — FIRST-CLASS SUBSYSTEM

Trend Radar is a core subsystem, not a UI widget.

Purpose:

> Automatically discover emerging topics, formats and social-media opportunities before content production begins.

Create provider architecture for legal/public/authorized sources.

Potential sources can include, when official or permitted access is configured:

```text
YouTube
TikTok
Instagram / Facebook
Reddit
X
Google Trends
news / RSS
search trend providers
other configured trend data providers
```

Do not use protection bypasses or unauthorized scraping.

Do not download and republish copyrighted social video as source media.

Create:

`TrendSourceProvider`

Example provider methods:

```text
collect_signals()
search_topic()
get_topic_metrics()
get_content_reference()
```

---

# 10. TREND SIGNAL NORMALIZATION

`TrendSignal` should support:

```text
source
source_reference
observed_at
country
locale
language

keyword
topic
hashtags
media_type
format
duration

views
likes
comments
shares
saves
engagement

creator_count
content_count

velocity
acceleration

raw_signal_hash
```

Not every provider exposes all metrics.

Unavailable fields must remain `null`.

Never fabricate missing metrics.

Preserve source evidence.

---

# 11. TREND CLUSTERING

One real trend may appear under multiple keywords.

Example:

```text
AI video
video AI
AI filmmaking
AI movie
#aivideo
```

Cluster signals using a configurable combination of:

```text
semantic embeddings
keyword similarity
hashtags
entity overlap
temporal correlation
cross-platform co-occurrence
```

Create a stable `TrendCluster`.

Avoid turning every individual post into an independent trend.

---

# 12. TREND LIFECYCLE

Support lifecycle states such as:

```text
discovered
rising
breakout
mainstream
saturated
declining
expired
```

The system should prioritize early indicators.

Important signals:

```text
velocity
acceleration
cross-platform propagation
novelty
competition growth
```

The primary objective is not only to report what is already viral.

It should identify **rising opportunities before peak saturation** when evidence supports that assessment.

---

# 13. TREND / OPPORTUNITY SCORING

Implement a configurable scoring framework.

Conceptual formula:

```text
TrendOpportunityScore =
    velocity
  + acceleration
  + cross_platform_spread
  + engagement_quality
  + novelty
  + channel_fit
  + format_fit
  + monetization_fit
  - saturation
  - competition
  - rights_risk
  - policy_risk
```

Weights must be configurable by:

```text
channel
niche
platform
business objective
```

Examples:

Entertainment may emphasize:

```text
virality
velocity
shareability
```

Affiliate channels may emphasize:

```text
buyer intent
product fit
conversion potential
```

Scores are model/system estimates and must be labeled as such.

---

# 14. IDEA ENGINE

A trend is not an idea.

Create `IdeaEngine`.

Input:

```text
TrendCluster
ChannelProfile
NicheProfile
audience context
historical analytics
production capability
budget
```

Output:

```text
IdeaCandidate[]
```

Each candidate should contain:

```text
title
angle
hook concept
format
recommended duration
visual concept
audience
CTA concept
trend references
originality notes
```

The engine must produce genuinely different angles, not superficial paraphrases.

---

# 15. IDEA SCORING

Conceptual scoring:

```text
IdeaScore =
    hook_strength
  + trend_relevance
  + originality
  + audience_fit
  + visual_potential
  + production_feasibility
  + expected_retention
  + shareability
  + monetization_potential
  - production_cost
  - saturation
  - policy_risk
```

Persist explainable component scores.

Example output:

```json
{
  "idea_score": 91,
  "trend_score": 88,
  "channel_fit": 94,
  "visual_potential": 96,
  "monetization_fit": 72,
  "saturation": 31,
  "recommended_format": "vertical_short",
  "recommended_duration_seconds": 38
}
```

Scores are estimates, not observed real-world performance.

---

# 16. ORIGINALITY / REUSE SAFETY

Trend references may be used for:

```text
topic understanding
format analysis
hook pattern analysis
audience reaction
competitive research
```

Do not:

```text
copy scripts
download/re-upload creator videos
closely reproduce copyrighted creative treatment
```

Idea output should generate:

```text
new angle
new script
new structure
new narration
new visual treatment
```

Preserve references for research/provenance only.

---

# 17. TREND RADAR UI

Auto Edit Studio must include a top-level `Trend Radar` section.

Views:

```text
Trending Now
Rising Fast
Breakout
Early Signals
Cross-platform
Low Competition
High Monetization Potential
Near Saturation
```

Filters:

```text
platform
country
language
niche
channel
time range
format
business objective
```

Trend detail page should show:

```text
trend summary
growth/time evidence
platform distribution
keywords / hashtags
trend lifecycle
competition
opportunity score
source references
suggested ideas
```

User flow:

```text
Trend
→ Generate Ideas
→ Select Idea
→ Create Video Project
```

---

# 18. CONTENT OPPORTUNITY QUEUE

Create a daily/periodic ranked content opportunity queue.

Conceptually:

```text
100 trend clusters
      ↓
20 channel opportunities
      ↓
50 generated ideas
      ↓
idea scoring
      ↓
Top N production candidates
      ↓
Content Queue
```

The purpose is to answer:

> What are the best videos to produce now for this specific channel?

---

# 19. RESEARCH / EVIDENCE LAYER

Before script generation, support structured research.

Create provenance-bound `ResearchEvidence`.

Research outputs should include:

```text
claim
summary
source reference
retrieved_at
confidence
freshness
```

Do not invent facts to fill gaps.

Script generation should distinguish:

```text
verified facts
creative framing
uncertain claims
```

---

# 20. AUTO EDIT STUDIO

Build:

`apps/studio-web`

Desktop-first, responsive.

This is a lightweight AI-assisted NLE, not only a job form.

Primary workspace:

```text
Project Dashboard
Trend Radar
Content Queue
Media Browser
Transcript Panel
Scene Panel
Preview Player
Timeline
Inspector
AI Actions
Subtitle Editor
Audio Mixer
B-roll Browser
Publish Panel
Analytics Panel
```

---

# 21. UPLOAD

Support:

```text
video
audio
image
logo
music
subtitle
```

Requirements:

- resumable upload;
- multipart/chunk upload;
- SHA-256 hashing;
- duplicate detection;
- safe file naming;
- MIME and magic-byte validation;
- FFprobe metadata;
- duration;
- dimensions;
- FPS;
- audio stream metadata;
- object storage.

Do not trust client file extensions.

---

# 22. AI TRANSCRIPT

Create `TranscriptionProvider`.

Core pipeline must be vendor-independent.

Normalized output:

```json
{
  "language": "vi",
  "segments": [],
  "words": [],
  "confidence": 0.0
}
```

Support where provider capability allows:

```text
Vietnamese
English
language detection
punctuation
word-level timestamps
optional diarization
```

Transcript edits must be versioned.

Never overwrite the original transcript evidence.

---

# 23. SCENE DETECTION

Do not rely only on an LLM.

Use a combined pipeline:

```text
shot boundary detection
+
motion analysis
+
audio boundary analysis
+
transcript semantics
+
Vision AI semantic analysis
```

Output:

```text
scene_id
start
end
semantic_label
description
subjects
quality_score
motion_score
speech_score
confidence
```

---

# 24. SILENCE REMOVAL

Implement non-destructive silence detection.

Use combinations of:

```text
audio energy
FFmpeg silence detection
transcript gaps
```

Configuration:

```text
silence_threshold_db
minimum_silence_duration
padding_before
padding_after
```

Do not cut through spoken words.

Auto Edit creates edit decisions, not destructive changes to source media.

Users can enable/disable each cut.

---

# 25. HIGHLIGHT DETECTION

Highlight detection must be multimodal.

Possible inputs:

```text
speech semantics
keywords
emotion
audio energy
motion
faces
objects
scene novelty
visual quality
hook potential
information density
```

Output:

```text
highlight_score
reason
recommended_start
recommended_end
recommended_platform
```

Support:

```text
Top 3
Top 5
Auto Shorts
```

---

# 26. VISION AI — REQUIRED

Create `VisionProvider`.

Core capabilities:

## Frame understanding

```text
frame captioning
scene description
object detection
person/face detection
product detection
environment/location classification
action understanding
```

## OCR

Detect text in image/video frames.

## Composition intelligence

```text
subject position
safe crop
headroom
visual balance
saliency
frame quality
```

## Quality detection

```text
black frames
blur
overexposure
underexposure
low resolution
watermark/logo evidence
duplicate/frozen frames
```

## Editing intelligence

Vision output must support:

```text
best frame selection
B-roll relevance
smart crop
scene ranking
asset reranking
thumbnail candidates
```

Use structured JSON.

Include:

```text
confidence
provider
model
timestamp
evidence frame reference
```

Free-text model output alone must not become the only source of truth.

---

# 27. SMART REFRAMING

Support exports:

```text
9:16
16:9
1:1
4:5
```

Smart reframe requirements:

```text
detect subject
track face/person/object
generate crop path
smooth motion
avoid crop jumping
respect subtitle safe area
allow manual override
```

Store crop animation as timeline keyframes:

```text
time
x
y
scale
```

Low-confidence fallback:

```text
fallback=center_crop
needs_attention=true
```

---

# 28. DYNAMIC SUBTITLES

Do not limit subtitles to simple burned SRT.

Support:

```text
sentence captions
word-by-word
karaoke
keyword highlights
animated captions
speaker styles
```

Configurable template fields:

```text
font
size
weight
stroke
shadow
background
position
max_lines
highlight_style
animation
safe_area
```

Word timing should use transcript timestamps.

Create Vietnamese typography regression tests.

---

# 29. B-ROLL ENGINE

Create `BrollPlanner`.

Input:

```text
script
transcript
scene
niche
visual context
existing assets
```

Output:

```text
broll_intent
search_query
duration
preferred_media_type
generation_prompt
placement
confidence
```

Configurable resolver priority:

```text
user assets
licensed stock
internal media library
AI generated image
AI generated video
```

Do not download social-platform videos for unauthorized republishing.

---

# 30. STOCK MEDIA PROVIDERS

Create `StockMediaProvider`.

Methods:

```text
search_images()
search_videos()
get_asset()
download_asset()
```

Metadata must retain:

```text
provider
provider_asset_id
creator
source
license
license_url
attribution_requirement
width
height
duration
orientation
downloaded_at
```

Adapters may include legal stock APIs such as Pexels/Pixabay when credentials are configured.

Pipeline must not hardcode one provider.

Semantic ranking should rank relevance.

Vision AI may rerank top candidates.

---

# 31. MEDIA RIGHTS & PROVENANCE

Every media asset must include:

```text
source_type =
  user_upload
  stock
  ai_generated
  internal_library
```

Store:

```text
rights_status
license
provider
source reference
generation provenance
```

Default publishing rule:

```text
rights_status=unknown
→ publishing blocked
```

unless explicit owner override is recorded.

---

# 32. COMFYUI — REQUIRED

Create:

`services/comfyui-bridge`

Frontend must not talk directly to ComfyUI.

Bridge responsibilities:

```text
submit
queue
status
progress
result
cancel
timeout
retry
artifact registration
```

Version-control approved workflows under:

`workflows/comfyui/`

Provide architecture for:

```text
text-to-image
image-to-image
inpainting
outpainting
upscale
background replacement
image-to-video
video generation
```

depending on installed models/nodes.

Do not commit model weights.

Create:

```text
docs/COMFYUI_SETUP.md
workflows/comfyui/manifest.json
```

Workflow manifest includes:

```text
workflow version
required custom nodes
required model identifiers
VRAM expectation
input schema
output schema
```

Only approved/whitelisted workflows may execute.

Do not allow arbitrary client-submitted graphs by default.

---

# 33. AI IMAGE GENERATION

Create `ImageGenerationProvider`.

Adapters:

```text
ComfyUI
remote API providers
```

Normalized input:

```text
prompt
negative_prompt
aspect_ratio
reference_images
style
seed
quality
```

Output provenance:

```text
provider
model
workflow
seed
prompt
cost
generation_time
asset reference
```

Support:

```text
regenerate
variation
upscale
inpaint
```

---

# 34. AI VIDEO GENERATION

Create `VideoGenerationProvider`.

Support provider architecture for:

```text
text-to-video
image-to-video
reference-assisted video generation
```

Potential backends:

```text
ComfyUI
remote commercial provider
```

Generation must be asynchronous.

Persist:

```text
provider_job_id
progress
cost estimate
actual cost if available
result
failure reason
```

Do not hold HTTP requests open for long generation jobs.

---

# 35. MEDIA PLANNER

Create `MediaPlanner`.

Input:

```text
script
storyboard
scene
niche
brand
platform
available assets
budget
provider availability
```

Decision examples:

```text
uploaded footage
stock video
stock image
AI image
AI video
motion graphic
```

Create versioned `MediaPlan`.

Example:

```json
{
  "scene_id": "scene_03",
  "strategy": "stock_video",
  "query": "modern AI data center cinematic",
  "fallback": ["ai_image", "motion_graphic"],
  "max_cost": 0.1
}
```

Media planning must be cost-aware.

---

# 36. VOICE ENGINE

Audit and port useful production TTS behavior from legacy pilot code.

Create `TTSProvider`.

Support:

```text
provider adapters
voice
language
speed
style/instructions
scene-based TTS
```

Voice generation must be scene/semantic-chunk aligned.

Do not default to one giant narration file that is forcibly squeezed into the timeline.

Support:

```text
normalization
pause control
duration measurement
bounded timing adjustment
```

Voice cloning is outside default scope.

Any future voice-cloning feature requires explicit consent architecture.

---

# 37. MUSIC ENGINE

Support music assets with:

```text
source
license
BPM
duration
mood
energy
```

Music recommendation can use:

```text
niche
scene emotion
video pace
platform
```

Do not auto-publish media with unclear music rights.

---

# 38. MUSIC DUCKING / AUDIO MIX

Audio engine should support:

```text
voice normalization
music normalization
sidechain ducking
fade in
fade out
crossfade
limiter
```

Speech sections:

```text
music level decreases
```

Non-speech sections:

```text
music level can recover
```

Automated QC:

```text
voice audible
music not overpowering voice
no clipping
no silent final output
```

---

# 39. TIMELINE ENGINE

Timeline is the edit source of truth.

Do not render directly from storyboard.

Create:

`packages/contracts/timeline.schema.json`

Conceptual structure:

```text
Timeline
 ├ video tracks
 │   ├ source clips
 │   ├ B-roll
 │   ├ overlays
 │   └ generated media
 │
 ├ text tracks
 │   └ subtitles
 │
 ├ audio tracks
 │   ├ original audio
 │   ├ voice
 │   ├ music
 │   └ SFX
 │
 └ metadata
```

Clip fields should support:

```text
source_start
source_end
timeline_start
duration
speed
crop
transform
opacity
volume
transition
effects
```

Timeline mutations require versioning and optimistic concurrency.

---

# 40. TIMELINE UI

Users must be able to:

```text
drag
drop
trim
split
move
delete
reorder
disable
duplicate
```

Provide:

```text
timeline zoom
waveform
playhead
snapping
undo/redo
track lock
track mute
```

The MVP need not match full professional NLE feature depth, but it must be genuinely editable.

---

# 41. PREVIEW

Create a fast proxy preview path.

Example:

```text
540p
lower bitrate
proxy assets
cached media
```

Preview must:

```text
bind to timeline version
invalidate when timeline changes
report progress
support cancel
```

---

# 42. HUMAN APPROVAL

Default:

```text
HUMAN_APPROVAL_REQUIRED=true
```

States:

```text
draft
awaiting_review
changes_requested
approved
```

Reviewers can:

```text
comment
approve
reject
request changes
```

Approval must reference:

```text
timeline_version
preview_version
```

Any subsequent timeline change invalidates the approval.

---

# 43. FINAL RENDER

Use:

```text
Remotion
+
FFmpeg
```

Must support requested outputs such as:

```text
1080x1920
1920x1080
1080x1080
```

Configurable:

```text
fps
codec
CRF
bitrate
audio codec
sample rate
```

Default production delivery:

```text
H.264
AAC
```

Verify final media using FFprobe.

---

# 44. VIDEO QC

Render success is not equivalent to FFmpeg exit code zero.

QC must inspect:

```text
duration
resolution
fps
codec
audio stream
black-frame ratio
freeze-frame ratio
audio silence
audio clipping
subtitle bounds
timeline duration
missing assets
broken frames
A/V sync
```

Include sampled Vision QC.

Hard failures set:

```text
render status = failed_qc
```

and block publishing.

Regression tests must cover previously encountered issues:

```text
black output
silent output
subtitle drift
scene gaps
incorrect duration
Vietnamese font breakage
audio/video desync
```

---

# 45. PUBLISHING — REQUIRED

Create `PublishingProvider`.

Architecture targets:

```text
YouTube
TikTok
Instagram Reels
Facebook
```

Use official/authorized APIs.

Do not use browser automation to bypass platform limitations.

Provider methods when supported:

```text
validate()
publish()
get_status()
delete_or_cancel_if_supported()
```

Publication metadata:

```text
title
description
caption
hashtags
thumbnail
privacy
scheduled_at
```

---

# 46. PUBLISH SAFETY

Default:

```text
PUBLISH_ENABLED=false
```

CI:

```text
real external publishing prohibited
```

Staging:

```text
dry-run by default
```

Real publishing requires all:

```text
credentials configured
project approved
rights validation passed
platform validation passed
owner enabled publishing
```

Use idempotency keys.

Retries must not create duplicate posts.

---

# 47. PLATFORM CAPABILITY VALIDATION

Before publishing validate, based on adapter capability:

```text
duration
resolution
aspect ratio
file size
codec
caption limits
thumbnail requirements
```

Platform capabilities must be versionable/configurable.

Do not assume platform limits remain static forever.

---

# 48. ANALYTICS — REQUIRED

Create `AnalyticsProvider`.

Normalized metrics may include:

```text
views
impressions
reach
watch_time
average_view_duration
completion_rate
likes
comments
shares
saves
followers/subscribers gained
clicks
CTR
revenue
RPM
```

Unsupported/unavailable metrics remain:

```text
null
```

Never fabricate data.

Persist:

```text
provider
metric
value
collected_at
source
```

---

# 49. ANALYTICS SYNC

Analytics worker should support:

```text
initial sync
scheduled refresh
backoff
rate-limit handling
historical snapshots
```

Keep time-series snapshots.

Do not only overwrite current values.

---

# 50. WINNER DETECTION

Performance intelligence should consider more than views.

Possible factors:

```text
view velocity
retention
completion
engagement
shares
saves
CTR
subscriber/follower conversion
revenue
production cost
```

Output states:

```text
winner_candidate
normal
underperforming
insufficient_data
```

Do not automatically delete underperforming video.

Do not automatically change paid media budget.

Recommendation first.

---

# 51. LEARNING LOOP

Persist video features:

```text
trend cluster
idea
hook type
duration
scene count
subtitle template
voice
music
visual strategy
niche
topic
CTA
publishing time
```

Connect analytics back to:

```text
Trend Radar
Idea Engine
Media Planner
Template recommendations
```

Generate insights such as:

```text
winning trend families
winning hooks
winning duration
winning visual strategy
winning subtitle style
winning voice profile
winning publishing windows
```

The important model is:

```text
GLOBAL TREND
     +
CHANNEL HISTORY
     +
AUDIENCE RESPONSE
     ↓
PERSONALIZED OPPORTUNITY ENGINE
```

V2 should generate recommendations first.

Autonomous decision execution can be a later gated phase.

---

# 52. COST ENGINE

Every external AI/media provider operation should record:

```text
provider
model
operation
estimated_cost
actual_cost
project_id
job_id
```

Each project must expose a cost summary.

Media planning must accept:

```text
max_ai_cost
```

When projected cost exceeds budget:

```text
needs_approval=true
```

Normal CI must not generate paid API charges.

Real provider tests require:

```text
manual workflow_dispatch
explicit enable flag
secret configuration
```

---

# 53. AGENT HUB ↔ V2 API

V2 is independent but exposes a service API.

Version:

```text
/v1/
```

Example endpoints:

```text
POST /v1/trends/refresh
GET  /v1/trends
GET  /v1/opportunities
POST /v1/ideas/generate

POST /v1/projects
POST /v1/projects/{id}/generate
GET  /v1/projects/{id}

POST /v1/uploads/init
POST /v1/uploads/complete

POST /v1/projects/{id}/analyze

GET  /v1/projects/{id}/timeline
PUT  /v1/projects/{id}/timeline

POST /v1/projects/{id}/preview
POST /v1/projects/{id}/approve

POST /v1/projects/{id}/render
POST /v1/projects/{id}/publish

GET /v1/projects/{id}/publications
GET /v1/projects/{id}/analytics
```

Agent Hub service authentication must use a dedicated service identity/token.

---

# 54. WEBHOOKS

Outbound events may include:

```text
trend.opportunity.detected
idea.shortlist.ready

video.project.created
video.analysis.completed
video.preview.ready
video.approval.required
video.approved
video.render.completed
video.render.failed
video.publish.completed
video.publish.failed
video.analytics.updated
video.winner.detected
```

Webhook delivery requirements:

```text
HMAC signed
timestamped
idempotent
retryable
delivery state persisted
```

Never expose secrets in payloads.

---

# 55. AUTH / RBAC

Minimum roles:

```text
owner
editor
reviewer
viewer
service
```

Examples:

`editor`:
- edit project/timeline.

`reviewer`:
- approve/request changes.

`owner`:
- manage publishing providers and high-risk production configuration.

`service`:
- Agent Hub or system-to-system integration.

---

# 56. SECRETS

Never commit:

```text
API keys
OAuth tokens
refresh tokens
cookies
storage secrets
ComfyUI credentials
provider credentials
```

`.env.example` contains placeholders only.

Do not log secrets.

Publishing credentials must use encrypted-at-rest storage or an appropriate external secret store.

---

# 57. OBSERVABILITY

Each service provides:

```text
/healthz
/readyz
```

Use structured logging.

Useful context:

```text
request_id
job_id
project_id
stage
provider
duration
```

Do not log secrets.

Avoid logging private uploaded content unnecessarily.

---

# 58. PROVIDER ARCHITECTURE

Capabilities that must be provider-based:

```text
TrendSourceProvider
ResearchProvider
LLMProvider
TranscriptionProvider
VisionProvider
TTSProvider
ImageGenerationProvider
VideoGenerationProvider
StockMediaProvider
PublishingProvider
AnalyticsProvider
ObjectStorageProvider
```

Core business logic must not directly use vendor SDKs.

Vendor SDKs live in adapters.

---

# 59. PROVIDER FALLBACK

Allow:

```text
primary
fallback
disabled
```

Provider failure must not corrupt project state.

Capability status should clearly report:

```text
healthy
degraded
unavailable
not_configured
```

---

# 60. TEMPLATE SYSTEM

Create versioned:

```text
ContentTemplate
VideoTemplate
SubtitleTemplate
BrandTemplate
PublishingTemplate
ScoringProfile
```

Do not deeply embed templates into renderer code.

---

# 61. CHANNEL PROFILE

A channel can define:

```text
name
platform
niche
language
audience
default_duration
aspect_ratio
brand_kit
subtitle_template
voice_profile
CTA style
publishing profile
trend scoring profile
monetization goal
```

One project may export multiple channel variants.

---

# 62. MULTI-PLATFORM VARIANTS

One master project can produce:

```text
16:9 YouTube
9:16 Shorts
9:16 TikTok
9:16 Reels
1:1 social
4:5 feed
```

Reuse expensive generated artifacts when possible.

Deduplicate/cache by deterministic content fingerprint.

---

# 63. CACHE

Cache appropriate artifacts:

```text
trend provider responses
research
transcript
vision result
stock search
generated media
proxy
render intermediates
```

Use deterministic keys.

Never leak cache across workspaces/users/projects.

---

# 64. E2E FLOW A — AUTO EDIT

CI deterministic fixture:

```text
upload video fixture
→ transcript fixture/provider
→ scene detection
→ silence edit decisions
→ highlight selection
→ smart reframing
→ dynamic subtitle
→ B-roll insertion
→ voice/music mix
→ editable timeline
→ proxy preview
→ simulated approval
→ render
→ QC
→ final MP4
```

No paid external AI call.

---

# 65. E2E FLOW B — IDEA TO VIDEO

CI:

```text
topic
→ script
→ storyboard
→ media plan
→ mock stock / mock AI media
→ voice
→ subtitle
→ timeline
→ render
→ QC
→ final video
```

---

# 66. E2E FLOW C — PUBLISHING

CI:

```text
final video
→ rights validation
→ platform validation
→ mock PublishingProvider
→ publication receipt
```

Never real-publish from CI.

---

# 67. E2E FLOW D — ANALYTICS

CI:

```text
published fixture
→ mock AnalyticsProvider
→ metric snapshots
→ normalized analytics
→ winner score
```

---

# 68. E2E FLOW E — TREND TO LEARNING LOOP

This flow is mandatory.

```text
social/web trend fixture signals
→ normalize
→ cluster
→ trend lifecycle
→ opportunity score
→ generate original ideas
→ rank ideas
→ select top idea
→ create VideoProject
→ research
→ script
→ storyboard
→ media plan
→ timeline
→ render
→ publish mock
→ analytics mock
→ performance assessment
→ feed performance into Trend/Idea learning data
```

This proves V2 is more than a video generator.

---

# 69. REAL PROVIDER ACCEPTANCE

Real integration testing for:

```text
trend sources
research
TTS
Vision
stock
ComfyUI GPU
AI image
AI video
publishing
analytics
```

must run only through explicit manual workflows with configured credentials.

Differentiate:

```text
implemented
mock-tested
locally tested
real-provider tested
production deployed
```

Never conflate these states.

---

# 70. COMFYUI CI

Standard CI does not require a GPU.

Test:

```text
workflow schema validation
bridge unit tests
mock ComfyUI server
queue behavior
timeout
cancel
failure
result parsing
```

GPU acceptance is a separate manual gate.

---

# 71. QUALITY BAR

A video cannot become `ready` if:

```text
QC failed
missing media
rights invalid
audio missing
timeline invalid
hard subtitle overflow
broken artifacts
```

Publishing cannot proceed without readiness and approval.

---

# 72. DOCUMENTATION

Required documents:

```text
README.md
docs/ARCHITECTURE.md
docs/MIGRATION_AUDIT.md
docs/TREND_RADAR.md
docs/IDEA_INTELLIGENCE.md
docs/AUTO_EDIT_STUDIO.md
docs/VISION_AI.md
docs/COMFYUI_SETUP.md
docs/MEDIA_PROVIDERS.md
docs/PUBLISHING.md
docs/ANALYTICS.md
docs/LEARNING_LOOP.md
docs/API.md
docs/SECURITY.md
docs/DEPLOYMENT.md
docs/OPERATIONS.md
docs/TESTING.md
docs/COST_CONTROL.md
```

---

# 73. DEPLOYMENT PROFILES

At minimum:

```text
dev
ci
production-cpu
production-gpu
```

CPU services must start without GPU services.

ComfyUI outage should not make the whole platform unhealthy.

---

# 74. DOCKER

Local core should boot through Docker Compose with services such as:

```text
postgres
redis
minio
api
orchestrator
workers
renderer
studio-web
```

ComfyUI can be an optional profile.

---

# 75. PRODUCTION ISOLATION

If V2 later shares a VPS with other NPD systems:

```text
separate container names
separate networks
separate ports
separate PostgreSQL database
separate Redis
separate storage paths
separate env
separate backups
```

Do not modify production Caddy routing during extraction PRs.

Caddy integration is a separate owner-gated deployment task.

---

# 76. MIGRATION STRATEGY

## Step 1

Document/tag the source baseline.

## Step 2

Create/extract V2 repository.

## Step 3

Port video-only components:

```text
apps/api video functionality
services/worker
renderer
video contracts
video examples
video tests
video workflows
```

## Step 4

Exclude:

```text
services/agent_hub
marketing OS
attribution
CRM business logic
campaign OS
provider-health logic
Agent Hub Command Center
```

## Step 5 — Port relevant PR #8 work

Especially:

```text
subtitle synchronization
visible E2E fixtures
black-frame QC
resumability
stable error codes
renderer tests
Docker E2E
```

## Step 6 — Port relevant PR #6 work

Especially:

```text
production TTS provider
asset preflight
Vietnamese text rendering
scene-aligned narration
production media handling
motion/pacing improvements
```

## Step 7

Do not merge old PRs solely as an extraction shortcut.

---

# 77. DO NOT DELETE LEGACY VIDEO CODE YET

During initial extraction:

**Do not immediately delete video code from the old repository.**

First demonstrate parity in V2.

After V2 acceptance, create a separate old-repo PR to:

```text
mark legacy video modules deprecated
update documentation
replace integrations with V2 API
```

Deleting old code is a separate decision and owner gate.

---

# 78. PR SEQUENCE

Do not create one giant all-system PR.

## PR V2-01 — Extraction & Parity

Deliver:

```text
independent repository/workspace
video core extraction
no Agent Hub runtime dependency
Docker boot
CI
corrected Sprint 1 parity
selected PR #6/#8 port
deterministic E2E
```

Acceptance:

```text
V2 boots independently.
Existing deterministic video flow passes.
Agent Hub production remains unchanged.
```

## PR V2-02 — Durable Project Platform

Deliver:

```text
PostgreSQL
object storage
workspace/project model
asset persistence
versioning
durable jobs
provider registry
cost records
```

## PR V2-03 — Trend Radar & Idea Intelligence

Deliver:

```text
TrendSourceProvider
normalized trend signals
TrendCluster
lifecycle
opportunity scoring
Trend Radar UI
Idea Engine
IdeaScore
Content Opportunity Queue
E2E trend fixtures
```

## PR V2-04 — Auto Edit Analysis

Deliver:

```text
upload
transcription
scene detection
silence decisions
highlight detection
```

## PR V2-05 — Vision AI + Smart Reframe

Deliver:

```text
VisionProvider
OCR
scene/frame analysis
quality signals
subject tracking
smart crop/reframe
```

## PR V2-06 — Media Intelligence

Deliver:

```text
StockMediaProvider
MediaPlanner
BrollPlanner
ImageGenerationProvider
VideoGenerationProvider
ComfyUI bridge
rights/provenance
```

## PR V2-07 — Auto Edit Studio

Deliver:

```text
studio UI
media browser
transcript
scene panel
timeline UI
editor interactions
preview
```

## PR V2-08 — Audio / Subtitle / Render / QC

Deliver:

```text
TTS
dynamic subtitles
music
music ducking
audio mix
final renderer
full QC
```

## PR V2-09 — Publishing

Deliver:

```text
PublishingProvider
official platform adapter architecture
OAuth/token architecture
dry-run
rights gate
platform gate
idempotent publication
```

## PR V2-10 — Analytics + Winner Detection + Learning Loop

Deliver:

```text
AnalyticsProvider
metric snapshots
normalized metrics
winner detection
video feature metadata
trend/idea performance feedback
personalized recommendations
```

## PR V2-11 — Agent Hub Bridge & Production Hardening

Deliver:

```text
service auth
versioned API
signed webhooks
Agent Hub contract
security hardening
backup/restore
production deployment runbook
soak testing
```

---

# 79. BRANCH PROTECTION

Protect `main`.

Required CI at minimum:

```text
lint
unit tests
contract tests
API tests
worker tests
frontend tests
renderer tests
Docker E2E
security checks
```

No merge on required-check failure.

---

# 80. DEFINITION OF DONE — MODE B

Auto Edit Studio is not complete until a non-developer can:

```text
create project
upload video
wait for AI analysis
review transcript
review detected scenes
review/remove silence cuts
review highlights
reframe
change subtitles
change B-roll
edit timeline
preview
approve
render
publish
view analytics
```

through UI.

---

# 81. DEFINITION OF DONE — MODE A

Autonomous Content Factory is not complete until the system can:

```text
collect trend signals
identify opportunity
generate original ideas
rank ideas
select/approve idea
research
write script
build storyboard
plan media
search licensed stock
generate missing image/video
run Vision AI
create voice/subtitles/music
build editable timeline
render preview
request human approval
render final
pass QC
publish through provider path
collect analytics
feed performance into learning data
```

---

# 82. ACCEPTANCE ARTIFACTS

Produce at least:

## Artifact A — Uploaded Footage Auto Edit

Bundle:

```text
final.mp4
preview.mp4
timeline.json
transcript.json
scene-analysis.json
highlight-analysis.json
asset-provenance.json
subtitle output
audio analysis
render manifest
qc.json
job events
cost.json
```

## Artifact B — Idea-to-Video

Bundle:

```text
trend-evidence.json
idea-shortlist.json
selected-idea.json
research-evidence.json
script.json
storyboard.json
media-plan.json
generated/stock asset provenance
timeline.json
preview.mp4
final.mp4
qc.json
cost.json
```

## Artifact C — Trend-to-Learning E2E

Bundle evidence for:

```text
trend signals
cluster
score
idea
video project
mock publication
mock analytics
winner assessment
learning feedback
```

Do not use screenshots as the sole acceptance evidence.

---

# 83. OWNER REPORTING

After each PR report:

```text
What changed
What was tested
CI status
Known limitations
Security impact
Cost impact
Production impact
Next PR
```

Clearly distinguish:

```text
implemented
mock-tested
real-provider tested
production deployed
```

Do not claim "done" when only interfaces exist.

---

# 84. HARD GUARDRAILS

Do not:

- self-merge;
- self-deploy production;
- enable production auto-publishing by default;
- incur significant paid AI cost without configured budget/approval;
- commit secrets;
- scrape/bypass protected platforms;
- reuse copyrighted social videos without rights;
- share Agent Hub database/state;
- make Agent Hub depend on V2 internal code;
- fabricate trend metrics;
- fabricate analytics;
- label mock provider results as real-provider validation.

---

# 85. TECHNICAL PRIORITY

Priority:

```text
Reliability
→ Content opportunity quality
→ Editing quality
→ Human usability
→ Media intelligence
→ Render quality
→ Publishing
→ Analytics
→ Learning
→ Scale
```

Do not spend excessive time building dashboards before end-to-end production quality works.

---

# 86. PRODUCT PRINCIPLE

NPD Video Factory V2 is not:

> a script that combines images, narration and subtitles into an MP4.

It is:

> **an AI-native content opportunity, media intelligence, editing, production, publishing and learning platform with an editable timeline and human approval gates.**

---

# 87. FIRST ACTION — BEGIN IMPLEMENTATION NOW

Begin with:

```text
1. Inspect current main.
2. Inspect PR #6.
3. Inspect PR #8.
4. Produce migration inventory.
5. Record exact source SHAs.
6. Create/extract npd-video-factory-v2.
7. Remove Agent Hub runtime dependencies.
8. Make Docker and CI boot Video Factory independently.
9. Port corrected Sprint 1 + production TTS functionality.
10. Run full deterministic E2E.
11. Open PR V2-01.
```

Do not stop at an architecture proposal.

PR V2-01 must contain working code.

After V2-01 passes required CI, proceed in the PR sequence above.

---

# 88. OWNER GATE

No PR merge or production deployment without owner approval.

If an unsafe/destructive blocker appears:

```text
stop the destructive action
document the blocker
continue all safe implementation work
```

A blocker in one area is not a reason to stop the whole project.

---

# 89. NORTH STAR ARCHITECTURE

```text
                    NPD VIDEO FACTORY V2

SOCIAL / WEB SIGNALS
          ↓
      TREND RADAR
          ↓
 OPPORTUNITY ENGINE
          ↓
       IDEA ENGINE
          ↓
        RESEARCH
          ↓
CONTENT INTELLIGENCE
          ↓
       STORYBOARD
          ↓
    MEDIA PLANNER
   ↙       ↓        ↘
STOCK   COMFYUI    AI APIs
   ↘       ↓        ↙
      MEDIA LIBRARY
          ↓
       VISION AI
          ↓
       AUTO EDIT
          ↓
       TIMELINE
          ↓
   AUTO EDIT STUDIO
          ↓
        PREVIEW
          ↓
    HUMAN APPROVAL
          ↓
        RENDER
          ↓
 QUALITY CONTROL
          ↓
┌─────────┼──────────┐
↓         ↓          ↓
YOUTUBE  TIKTOK    META
└─────────┼──────────┘
          ↓
       ANALYTICS
          ↓
 WINNER DETECTION
          ↓
    LEARNING LOOP
          ↓
TREND / IDEA / TEMPLATE
   PERSONALIZATION
```

**Video Factory V2 must remain independently operable even when Agent Hub is offline.**

Agent Hub is an optional upstream orchestrator, not the runtime owner of Video Factory V2.
