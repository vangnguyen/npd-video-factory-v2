"""Current saved transcript/pixel/audio evidence; no inference or provider call."""
from types import SimpleNamespace
from .scene_evidence import combine_scene_evidence
from .auto_edit_logic import build_highlights

ALGORITHM='current-scene-assessment-v1'

def assess(analysis,asset_sha256,*,pixel_frames=()):
    current=analysis.model_copy(deep=True)
    current.provenance={**current.provenance,'semantic_analysis_refresh_required':False}
    scenes=[v.model_dump(mode='json') for v in combine_scene_evidence(
        current,SimpleNamespace(checksum_sha256=asset_sha256),pixel_frames=pixel_frames)]
    for scene in scenes:
        evidence=scene['evidence']
        evidence.update(transcript_segment_count=len(evidence['transcript_segment_ids']),
            transcript_revision_id=current.transcript.transcript_id if current.transcript else None,
            transcript_version=current.transcript.version if current.transcript else None,
            text_semantics_basis='saved text keyword/information-density heuristics; no semantic model',
            semantic_vision_state='NOT_CONFIGURED',prediction_confidence_calibrated=False,
            source_frame_time_basis='sampled requested timestamp; decoded source PTS not certified')
    ranking=build_highlights(scenes=scenes,top_k=len(scenes))
    by_ordinal={scene['ordinal']:scene for scene in scenes}
    for item in ranking:
        scene=by_ordinal[item['scene_ordinal']]
        item['scene_id']=scene['scene_id']
        if scene['confidence'] is None:item['evidence']['confidence']=None
        item['evidence'].update(prediction_confidence_calibrated=False,recommendation_only=True,
            automatic_application=False,semantic_vision_state='NOT_CONFIGURED')
    return {'scenes':scenes,'scene_ranking':ranking,'highlights':ranking[:5],
        'semantic_vision_used':False,'semantic_vision_state':'NOT_CONFIGURED',
        'prediction_confidence_calibrated':False,'continuous_tracking_performed':False,
        'decoded_source_pts_verified':False,'recommendation_only':True,
        'canonical_timeline_mutated':False,'silence_decisions_mutated':False,
        'publishing_authorized':False,'owner_uat_accepted':False,'provider_dispatches':0}
