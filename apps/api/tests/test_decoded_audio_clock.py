import pytest
from app.decoded_audio_clock import parse_audio_clock,audio_clock_lines

LOG='''private input path must not escape
[Parsed_ashowinfo_2 @ local] n:0 pts:4000 pts_time:0.5 fmt:flt channels:1 chlayout:mono rate:8000 nb_samples:800 checksum:00
[Parsed_ashowinfo_2 @ local] n:1 pts:4800 pts_time:0.6 fmt:flt channels:1 chlayout:mono rate:8000 nb_samples:800 checksum:01
'''

def test_observed_pcm_origin_and_source_clock_are_distinct_from_wav_zero():
    filtered=audio_clock_lines(LOG);assert 'private input' not in filtered
    clock=parse_audio_clock(filtered,sample_rate=8000)
    assert clock['source_start_seconds']==.5 and clock['source_end_seconds']==.7
    assert clock['pcm_samples']==1600 and clock['frames'][1]['pcm_start_sample']==800
    assert not clock['implicit_gap_fill_performed'] and not clock['implicit_overlap_removal_performed']

@pytest.mark.parametrize('log',[LOG.replace('pts:4800','pts:5000'),LOG.replace('pts:4800','pts:4500'),
    LOG.replace('pts_time:0.6','pts_time:0.9'),LOG.replace('channels:1','channels:2'),LOG.replace('rate:8000','rate:16000'),LOG.replace('n:1','n:5')])
def test_discontinuity_overlap_geometry_or_clock_inconsistency_is_not_guessed(log):
    with pytest.raises(ValueError):parse_audio_clock(audio_clock_lines(log),sample_rate=8000)
