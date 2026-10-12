from fractions import Fraction
import pytest
from app.decoded_frame_clock import DecodedFrameStamp,parse_showinfo,select_filter,targets


LOG='''[Parsed_showinfo_3 @ local] config in time_base: 1/15360, frame_rate: 30/1
[Parsed_showinfo_3 @ local] n: 0 pts: 0 pts_time:0 duration: 512 fmt:rgb24 s:480x360 i:P
[Parsed_showinfo_3 @ local] n: 1 pts: 6656 pts_time:0.433333 duration: 512 fmt:rgb24 s:480x360 i:P
'''


def test_raw_rational_clock_does_not_use_requested_time_or_rounded_log_time():
    samples=parse_showinfo(LOG,maximum_frames=8)
    assert samples[1].timestamp_seconds==float(Fraction(6656,15360))
    assert samples[1].timestamp_seconds!=.433333
    assert samples[1].selected_ordinal==1 and samples[1].width==480
    assert targets(2.,8)==[0.,.25,.5,.75,1.,1.25,1.5,1.75]
    expression=select_filter(targets(2.,8));assert 'prev_t' in expression and 'eq(n,0)' in expression


@pytest.mark.parametrize('value',[
    LOG.replace('1/15360','0/15360'),LOG.replace('pts: 6656','pts: 0'),
    LOG.replace('n: 1','n: 7'),LOG.replace('pts_time:0.433333','pts_time:0.9'),
    LOG.replace('pts: 6656','pts: N/A'),LOG+LOG,
])
def test_missing_inconsistent_or_reordered_decoder_clock_never_becomes_verified(value):
    with pytest.raises(ValueError):parse_showinfo(value,maximum_frames=8)


def test_unbounded_frames_and_client_clock_are_refused():
    with pytest.raises(ValueError):parse_showinfo(LOG,maximum_frames=1)
    with pytest.raises(ValueError):targets(float('inf'),8)
    with pytest.raises(ValueError):select_filter([0.,.25,.25])
    with pytest.raises(ValueError):DecodedFrameStamp(selected_ordinal=0,pts=1,time_base_numerator=1,
        time_base_denominator=3,timestamp_seconds=.5,width=320,height=240)
