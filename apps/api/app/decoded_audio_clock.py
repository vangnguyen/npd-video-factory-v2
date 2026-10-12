"""Clocked mono PCM after an explicit asettb=1/sample_rate filter."""
import math,re
from decimal import Decimal


def parse_audio_clock(text:str,*,sample_rate:int,maximum_frames:int=100000):
    if sample_rate not in (8000,16000) or type(sample_rate) is not int or len(text)>16*1024*1024:
        raise ValueError('DECODED_AUDIO_CLOCK_BOUND_INVALID')
    frames=[];total=0;previous_end=None
    for line in text.splitlines():
        if not re.search(r'\[Parsed_ashowinfo_[^\]]+\].*\bn:\s*',line):continue
        m=re.search(r'\bn:(\d+)\s+pts:(-?\d+)\s+pts_time:([\deE.+-]+).*?\bchannels:(\d+).*?\brate:(\d+)\s+nb_samples:(\d+)',line)
        if not m:raise ValueError('DECODED_AUDIO_STAMP_INVALID')
        ordinal,pts,printed,channels,rate,count=m.groups();ordinal,pts,channels,rate,count=map(int,(ordinal,pts,channels,rate,count))
        if ordinal!=len(frames) or channels!=1 or rate!=sample_rate or pts<0 or not 0<count<=192000:
            raise ValueError('DECODED_AUDIO_STAMP_INVALID')
        value=Decimal(printed)
        if not value.is_finite() or not -15<=value.as_tuple().exponent<=9:raise ValueError('DECODED_AUDIO_STAMP_INVALID')
        seconds=pts/sample_rate;tolerance=float(Decimal('0.500001')*(Decimal(10)**value.as_tuple().exponent))
        if seconds>3600 or abs(float(value)-seconds)>tolerance+1e-12:raise ValueError('DECODED_AUDIO_STAMP_INVALID')
        # No implicit gap filling or packet overlap removal. A single affine
        # ASR mapping is valid only for continuous decoded sample coordinates.
        if previous_end is not None and (abs(pts-previous_end)>1 or abs(pts-(frames[0]['pts']+total))>1):raise ValueError('DECODED_AUDIO_NONCONTIGUOUS_REVIEW_REQUIRED')
        frames.append({'ordinal':ordinal,'pts':pts,'sample_rate':sample_rate,'nb_samples':count,
            'pcm_start_sample':total,'pcm_end_sample':total+count,'source_start_seconds':seconds,'source_end_seconds':(pts+count)/sample_rate})
        total+=count;previous_end=pts+count
        if len(frames)>maximum_frames or total>sample_rate*3600:raise ValueError('DECODED_AUDIO_CLOCK_BOUND_INVALID')
    if not frames:raise ValueError('DECODED_AUDIO_STAMPS_EMPTY')
    return {'schema_version':'decoded-mono-audio-clock-v1','sample_rate':sample_rate,'time_base_numerator':1,
        'time_base_denominator':sample_rate,'normalization':'copyts_start_at_zero; asettb_1_over_sample_rate',
        'contiguous':True,'source_start_seconds':frames[0]['source_start_seconds'],
        'source_end_seconds':frames[-1]['source_end_seconds'],'pcm_samples':total,'frames':frames,
        'implicit_gap_fill_performed':False,'implicit_overlap_removal_performed':False}


def audio_clock_lines(text):
    return '\n'.join(line for line in text.splitlines() if re.search(r'\[Parsed_ashowinfo_[^\]]+\].*\bn:\d+\s+pts:',line))+'\n'
