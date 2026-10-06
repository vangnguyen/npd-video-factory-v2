"""Versioned gates for new projects; never rewrite approved or historical media."""
from __future__ import annotations
import copy
import math
import re
import unicodedata
from .contracts import WorkflowError, digest

POLICY = {
    'id': 'north-star-production-quality-v1', 'version': 1,
    'max_narration_tail_seconds': 2., 'max_between_unit_gap_seconds': 2.,
    'max_final_audio_tail_seconds': 2., 'silence_threshold_db': -45.,
    'activity_window_seconds': .02,
    'proper_names': ['Vinhomes Green Paradise Cần Giờ', 'Vinhomes Saigon Park', 'Vang Nguyễn'],
    'human_listening_required': True,
}
PROFILES = {'vertical-short': (1080,1920,'9:16'), 'landscape': (1920,1080,'16:9'),
            'square': (1080,1080,'1:1'), 'portrait-feed': (1080,1350,'4:5')}
_NAMES = (
    (r'(?:Vinhomes\s+)?Green\s+Paradise(?:\s+Cần\s+Giờ)?', POLICY['proper_names'][0]),
    (r'(?:Vinhomes\s+)?(?:Saigon|Sài\s+Gòn)\s+Park', POLICY['proper_names'][1]),
    (r'Vang\s+(?:Nguyễn|Nguyen)', POLICY['proper_names'][2]),
)


def policy_reference():
    return {'id':POLICY['id'], 'version':POLICY['version'], 'sha256':digest(POLICY)}


def resolve_policy(document):
    if 'production_quality' not in document:
        return None
    if document['production_quality'] != policy_reference():
        raise WorkflowError('PRODUCTION_QUALITY_POLICY_CHANGED_REVIEW_REQUIRED')
    return copy.deepcopy(POLICY)


def canonical_names(text):
    """Normalize a draft for visible review, without guessing phonetic spellings."""
    value=unicodedata.normalize('NFC',text)
    for pattern,replacement in _NAMES:
        value=re.sub(r'(?<!\w)'+pattern+r'(?!\w)',replacement,value,flags=re.I)
    return value


def canonicalize_draft(proposal):
    result=copy.deepcopy(proposal)
    result['narration']=canonical_names(result['narration'])
    for scene in result['visual_brief']:
        scene['narration_excerpt']=canonical_names(scene['narration_excerpt'])
    return result


def validate_tts_names(document,proposal):
    if resolve_policy(document) is None:
        return
    if canonical_names(proposal.narration)!=proposal.narration or any(
        canonical_names(s.narration_excerpt)!=s.narration_excerpt for s in proposal.visual_brief
    ):
        raise WorkflowError('TTS_PROPER_NAME_REVIEW_REQUIRED')


def validate_render_profile(profile,width,height,aspect_ratio=None):
    if not isinstance(profile,str) or profile not in PROFILES:
        raise WorkflowError('RENDER_PROFILE_UNKNOWN',400)
    w,h,ratio=PROFILES[profile]
    if type(width) is not int or type(height) is not int or (width,height)!=(w,h) or (aspect_ratio is not None and aspect_ratio!=ratio):
        raise WorkflowError('RENDER_PROFILE_CANVAS_MISMATCH',400)
    return {'id':profile,'width':width,'height':height,'aspect_ratio':ratio}


def evaluate_speech_placement(placement,duration,policy):
    end=placement.get('last_narration_activity_end_seconds')
    gaps=placement.get('between_unit_activity_gaps_seconds',[])
    if (isinstance(duration,bool) or not isinstance(duration,(int,float)) or not math.isfinite(duration)
        or isinstance(end,bool) or not isinstance(end,(int,float)) or not math.isfinite(end)
        or not 0<end<=duration or not isinstance(gaps,list)
        or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<0 for x in gaps)):
        raise WorkflowError('NARRATION_ACTIVITY_BINDING_INVALID')
    tail=duration-end
    return {'narration_tail_seconds':round(tail,6),
            'maximum_between_unit_gap_seconds':round(max(gaps,default=0),6),
            'no_narration_dead_air':tail<=policy['max_narration_tail_seconds']+.02,
            'no_excessive_speech_gaps':max(gaps,default=0)<=policy['max_between_unit_gap_seconds']+.02,
            'timing_source':placement.get('timing_source'),'word_alignment_claimed':False}


def audio_activity(samples,sample_rate,*,threshold_db=-45.,window_seconds=.02):
    """Measure PCM RMS activity; music activity is not labeled as speech."""
    import numpy as np
    values=np.asarray(samples,dtype=np.float64)
    if (values.ndim!=1 or not len(values) or not np.isfinite(values).all()
        or type(sample_rate) is not int or sample_rate<=0
        or isinstance(window_seconds,bool) or not isinstance(window_seconds,(int,float)) or not math.isfinite(window_seconds) or not 0<window_seconds<=1
        or isinstance(threshold_db,bool) or not isinstance(threshold_db,(int,float)) or not math.isfinite(threshold_db) or not -100<=threshold_db<=0):
        raise WorkflowError('AUDIO_ACTIVITY_INPUT_INVALID')
    width=max(1,round(sample_rate*window_seconds))
    starts=np.arange(0,len(values),width)
    lengths=np.minimum(width,len(values)-starts)
    rms=np.sqrt(np.add.reduceat(values*values,starts)/lengths)
    active=np.flatnonzero(rms>10**(threshold_db/20))
    duration=len(values)/sample_rate
    first=float(starts[active[0]]/sample_rate) if len(active) else None
    last=float(min(len(values),starts[active[-1]]+width)/sample_rate) if len(active) else None
    return {'duration_seconds':duration,'activity_start_seconds':first,'activity_end_seconds':last,
            'leading_silence_seconds':first if first is not None else duration,
            'trailing_silence_seconds':duration-last if last is not None else duration,
            'speech_detected':False,'audio_activity_detected':bool(len(active)),
            'threshold_db':threshold_db,'window_seconds':window_seconds,'source':'decoded_pcm_rms'}
