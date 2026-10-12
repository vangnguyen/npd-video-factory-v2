"""Strict FFmpeg showinfo clock parsing; no seek/FPS grid is called decoded PTS."""
import math
import re
from decimal import Decimal
from fractions import Fraction

from pydantic import Field, StrictInt, model_validator
from .models import StrictModel

ALGORITHM='single-decode-threshold-sampling-v1'
BASIS='decoded_source_pts; copyts_start_at_zero'


class DecodedFrameStamp(StrictModel):
    selected_ordinal:StrictInt=Field(ge=0)
    pts:StrictInt=Field(ge=0,le=2**63-1)
    time_base_numerator:StrictInt=Field(ge=1,le=2**31-1)
    time_base_denominator:StrictInt=Field(ge=1,le=2**31-1)
    timestamp_seconds:float=Field(ge=0,le=3600,allow_inf_nan=False)
    width:StrictInt=Field(ge=1,le=7680)
    height:StrictInt=Field(ge=1,le=7680)

    @model_validator(mode='after')
    def exact_clock(self):
        expected=float(Fraction(self.pts*self.time_base_numerator,self.time_base_denominator))
        if abs(expected-self.timestamp_seconds)>1e-10:
            raise ValueError('DECODED_FRAME_CLOCK_INCONSISTENT')
        return self


def targets(duration:float,count:int)->list[float]:
    if type(duration) not in (int,float) or not math.isfinite(duration) or not 0<duration<=3600:
        raise ValueError('DECODED_FRAME_DURATION_INVALID')
    if type(count) is not int or not 1<=count<=1000:
        raise ValueError('DECODED_FRAME_BOUND_INVALID')
    return [round(duration*index/count,9) for index in range(count)]


def select_filter(requested:list[float])->str:
    if (type(requested) is not list or not requested or len(requested)>1000 or requested[0]!=0
        or any(type(t) not in (int,float) or not math.isfinite(t) or t<0 for t in requested)
        or any(b<=a for a,b in zip(requested,requested[1:]))):
        raise ValueError('DECODED_FRAME_TARGETS_INVALID')
    # Crossing multiple targets selects one decoded frame, never duplicate PNGs.
    terms=['eq(n,0)']+[f'gte(t,{t:.9f})*lt(prev_t,{t:.9f})' for t in requested[1:]]
    return "select='"+'+'.join(terms)+"'"


def parse_showinfo(text:str,*,maximum_frames:int)->list[DecodedFrameStamp]:
    if type(text) is not str or len(text)>1024*1024:raise ValueError('DECODED_FRAME_LOG_BOUND_INVALID')
    if type(maximum_frames) is not int or not 1<=maximum_frames<=1000:
        raise ValueError('DECODED_FRAME_BOUND_INVALID')
    ratios=re.findall(r'\[Parsed_showinfo_[^\]]+\].*config in time_base:\s*(\d+)/(\d+)',text)
    if len(ratios)!=1 or any(int(n)<=0 or int(d)<=0 for n,d in ratios):
        raise ValueError('DECODED_FRAME_TIME_BASE_UNAVAILABLE')
    numerator,denominator=map(int,ratios[0]);output=[]
    for line in text.splitlines():
        if not re.search(r'\[Parsed_showinfo_[^\]]+\].*\bn:\s*',line):continue
        m=re.search(r'\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:([\deE.+-]+).*?\bs:(\d+)x(\d+)',line)
        if not m:raise ValueError('DECODED_FRAME_STAMP_UNAVAILABLE')
        ordinal,pts,display,width,height=m.groups();timestamp=float(Fraction(int(pts)*numerator,denominator))
        printed=Decimal(display)
        if not printed.is_finite() or not -15<=printed.as_tuple().exponent<=9:raise ValueError('DECODED_FRAME_PRINTED_CLOCK_MISMATCH')
        tolerance=float(Decimal('0.500001')*(Decimal(10)**printed.as_tuple().exponent))
        if abs(float(printed)-timestamp)>tolerance+1e-12:
            raise ValueError('DECODED_FRAME_PRINTED_CLOCK_MISMATCH')
        stamp=DecodedFrameStamp(selected_ordinal=int(ordinal),pts=int(pts),time_base_numerator=numerator,
            time_base_denominator=denominator,timestamp_seconds=timestamp,width=int(width),height=int(height))
        if (stamp.selected_ordinal!=len(output) or output and timestamp<=output[-1].timestamp_seconds):
            raise ValueError('DECODED_FRAME_CLOCK_NON_MONOTONIC')
        output.append(stamp)
        if len(output)>maximum_frames:raise ValueError('DECODED_FRAME_BOUND_EXCEEDED')
    if not output:raise ValueError('DECODED_FRAME_STAMPS_EMPTY')
    return output
