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

def test_explicit_forward_gap_keeps_both_pcm_and_source_coordinates():
    gap=LOG.replace('pts:4800 pts_time:0.6','pts:8000 pts_time:1.0')
    value=parse_audio_clock(audio_clock_lines(gap),sample_rate=8000,allow_gaps=True)
    assert value['schema_version']=='decoded-mono-audio-clock-v2' and not value['contiguous']
    assert value['pcm_samples']==1600 and value['source_end_seconds']==1.1
    assert value['segments'][1]=={'pcm_start_sample':800,'pcm_end_sample':1600,'source_start_sample':8000}
    assert value['gaps']==[{'source_start_sample':4800,'source_end_sample':8000,'decoded_pcm_boundary_sample':800}]
    assert not value['implicit_gap_fill_performed']

def test_backward_overlap_is_still_refused_with_forward_gap_support():
    with pytest.raises(ValueError,match='NONCONTIGUOUS'):
        parse_audio_clock(audio_clock_lines(LOG.replace('pts:4800 pts_time:0.6','pts:4400 pts_time:0.55')),sample_rate=8000,allow_gaps=True)

def test_continuous_clock_evidence_does_not_change_when_gaps_are_supported():
    assert parse_audio_clock(audio_clock_lines(LOG),sample_rate=8000)==parse_audio_clock(audio_clock_lines(LOG),sample_rate=8000,allow_gaps=True)
