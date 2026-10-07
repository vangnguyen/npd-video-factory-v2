"""Pure complete-speech limits; synthetic domain fixtures, no provider dispatch."""
from app.highlight_draft_logic import HighlightDraftRequest,build_drafts
from test_auto_edit_studio import analysis_fixture
from test_silence_word_safety import asset


def test_over_limit_whole_segment_is_skipped_without_shrinking_speech_or_mutating_evidence():
    source=asset();analysis=analysis_fixture(source.project_id,source.asset_id)
    duration=float(analysis.source_media.duration_seconds)
    analysis.scenes=[analysis.scenes[0].model_copy(update={'start_seconds':0,'end_seconds':duration})]
    segment=analysis.transcript.segments[0]
    segment.start_seconds=0;segment.end_seconds=duration;segment.words=[]
    analysis.transcript.segments=[segment]
    before=analysis.model_dump(mode='json')
    payload=HighlightDraftRequest(analysis_id=analysis.analysis_id,mode='auto_shorts',maximum_duration_seconds=3)
    assert duration>3
    assert build_drafts(analysis,source,payload)==[]
    assert analysis.model_dump(mode='json')==before
