"""Pure sampled pixel fusion; no semantic provider/ASR results are fabricated."""
from types import SimpleNamespace
import pytest
from app.media_frame_facts import MeasuredFrame,pixel_facts
from app.scene_evidence import combine_scene_evidence


def stack():
    scene=SimpleNamespace(scene_id='scn_fixture',ordinal=0,start_seconds=0.,end_seconds=2.,
        semantic_label='unknown scene',description='',evidence={})
    analysis=SimpleNamespace(provenance={},scenes=[scene],transcript=None,source_media=SimpleNamespace(audio_codec=None))
    asset=SimpleNamespace(checksum_sha256='a'*64)
    frame=MeasuredFrame(frame_id='mfr_fixture',timestamp_seconds=1.,reference='explicit-fixture-frame.png',
        sha256='b'*64,source_sha256='a'*64,provider='local_ffmpeg_pillow_pixels',model='pixel-quality-facts-v1',
        pixel_facts=pixel_facts(bytes(255*((x+y)%2) for y in range(8) for x in range(8)),8,8))
    return analysis,asset,frame


def test_pixel_ranking_uses_actual_facts_without_promoting_them_to_semantic_vision_confidence():
    analysis,asset,frame=stack()
    assert combine_scene_evidence(analysis,asset)[0].quality_score is None
    measured=combine_scene_evidence(analysis,asset,pixel_frames=[frame])[0]
    assert measured.quality_score==frame.pixel_facts.heuristic_quality_score
    assert measured.confidence is None and measured.needs_attention and measured.subjects==[]
    assert not measured.evidence['vision_used'] and measured.evidence['pixel_quality_confidence'] is None
    assert 'uncalibrated' in measured.evidence['quality_basis']
    assert measured.evidence['frame_evidence'][0]['confidence'] is None
    assert measured.evidence['frame_evidence'][0]['sha256']=='b'*64
    assert measured.evidence['pixel_quality_facts'][0]['pixel_facts']['ocr'] is None


def test_outside_samples_do_not_supply_scene_scores_and_foreign_source_is_rejected():
    analysis,asset,frame=stack()
    outside=frame.model_copy(update={'timestamp_seconds':3.})
    assert combine_scene_evidence(analysis,asset,pixel_frames=[outside])[0].quality_score is None
    with pytest.raises(ValueError,match='checksum'):
        combine_scene_evidence(analysis,asset,pixel_frames=[frame.model_copy(update={'source_sha256':'f'*64})])
