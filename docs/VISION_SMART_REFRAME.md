# Vision AI and Smart Reframe — V2-05

V2-05 adds a provider-neutral, structured Vision contract and durable Smart Reframe decisions on
top of a succeeded V2-04 Auto Edit analysis. It produces analysis and crop-plan records only. It
does not edit source bytes, render a reframed video or publish anything.

## Evidence status

| Capability | Implementation state | Evidence state |
|---|---|---|
| Vision provider interface | implemented | contract and unit tested |
| deterministic Vision provider | implemented for local/CI | fixture/mock tested, no network call |
| live Vision provider | contract only | `not_configured`; not real-provider tested |
| OCR/object/frame/quality schema | implemented | structured fixture and persistence tested |
| subject tracking | implemented | deterministic tracking and low-confidence fallback tested |
| Smart Reframe | implemented as crop-plan keyframes | four ratios, smoothing and manual override tested |
| reframe rendering | not implemented | belongs to a later editor/render increment |
| production rollout | not implemented | owner-gated after auth, real-provider and operational acceptance |

The deterministic provider is synthetic contract evidence. It derives stable structured fixtures
from the source metadata and V2-04 scene boundaries; it does not claim that an external model
inspected the pixels. Real-provider accuracy, OCR quality and tracking quality therefore remain an
explicit acceptance gate.

## Domain flow

```text
immutable source asset
        |
        v
succeeded V2-04 analysis -----> VisionProvider
        |                             |
        |                             v
        |                       structured frames
        |                       objects + OCR
        |                       composition + quality
        v                             |
  V2-04 scenes -----------------------+
                                      v
                        scene insights + subject tracks
                                      |
                                      v
                 9:16 / 16:9 / 1:1 / 4:5 crop plans
                                      |
                                      v
                      PostgreSQL decision/evidence records
```

Canonical binaries remain in S3-compatible storage. Vision downloads one bounded scratch copy,
records evidence references such as `asset://{asset_id}#t={seconds}`, and removes the scratch file
after analysis. PostgreSQL stores configuration, provider/model provenance, normalized frames,
scene insights, subject tracks and reframe plans.

## Structured frame evidence

Each frame includes:

- timestamp and immutable evidence-frame reference;
- caption, scene description, semantic label, environment and action;
- typed object/person/face/product/building/logo/text detections with normalized boxes;
- OCR text, language, confidence and normalized box;
- primary subject, saliency, headroom, visual balance and safe-crop signals;
- black, blur, exposure, resolution, logo/watermark and frozen/duplicate quality signals;
- frame confidence, provider key and model.

The service also creates scene-level structured evidence, ranked best frames and thumbnail
candidates. Free text is supplemental; typed detections, numeric signals and evidence references
remain available for downstream decisions.

## Subject tracking and crop plans

Detections with a stable track hint are grouped into subject tracks. Each observation has a time,
normalized bounding box and confidence. A crop plan contains:

- requested aspect ratio;
- `subject_track`, `center_crop` or `manual_override` strategy;
- crop keyframes with `time`, normalized `x`, normalized `y` and `scale`;
- `bounded_ema` smoothing and the configured maximum coordinate jump;
- subtitle-safe bottom area;
- confidence, fallback and `needs_attention`;
- whether a manual override was applied.

When no subject track meets the minimum confidence, the plan fails closed to
`fallback=center_crop` and `needs_attention=true`. Manual overrides are included in the request
fingerprint, persisted as a new deterministic analysis version and never overwrite earlier
evidence.

## API

```text
POST /api/v1/projects/{project_id}/analyses/{analysis_id}/vision
GET  /api/v1/projects/{project_id}/vision-analyses
GET  /api/v1/projects/{project_id}/vision-analyses/{vision_analysis_id}
```

POST is idempotent for the same project, source checksum, V2-04 analysis fingerprint,
configuration, provider/model and algorithm version. Different manual overrides or thresholds
produce a different fingerprint and durable record.

## Safety and cost

- `source_media_mutated=false`, `publish_requested=false` and `paid_external_call=false` are
  literal response-contract fields.
- The fixture provider records one idempotent Vision provider operation at `0 VND`.
- V2-05 rejects any provider result marked as an external or paid call before creating a cost
  record. Enabling a real provider requires a separate priced, owner-approved increment.
- Downloaded scratch bytes must match the immutable asset SHA-256 before analysis begins.
- No credential value is stored in analysis, cost, provenance, logs or API responses.
- Production startup rejects the fixture. A live adapter must be separately owner-approved and
  configured before use.
- V2-05 has no autonomous editing, render, approval, publishing, Ads, CRM or messaging action.

## Intentional limits

- no real OCR/object/tracking accuracy claim;
- no B-roll/media search or generation (V2-06);
- no interactive crop/timeline editor (V2-07);
- no reframed render/audio/subtitle composition (V2-08);
- no publishing (V2-09);
- no production deployment or public API exposure.
