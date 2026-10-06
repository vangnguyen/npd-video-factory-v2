"""Consume canonical requested shot times with sample-preserving voice placement."""
import copy
import math
import wave
from .contracts import WorkflowError, file_sha, write_json


def retime_voice(doc, meta, out, brand, template):
    from .shot_adapter import shots
    import numpy as np
    if not doc.get('canonical_timeline'): return None
    canonical=shots(doc)
    with wave.open(str(out/'voice.wav'),'rb') as wav:
        if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate())!=(1,2,48000):
            raise WorkflowError('SHOT_VOICE_FORMAT_INVALID')
        original=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').copy()
    if file_sha(out/'voice.wav')!=meta['audio_sha256']:
        raise WorkflowError('VOICE_ARTIFACT_BINDING_MISMATCH')
    groups=[[u for u in meta['units'] if u['scene']==i+1] for i in range(len(canonical))]
    layout=[]; placements=[]; updated=[]; cursor=0.
    for i,(shot,units) in enumerate(zip(canonical,groups)):
        lead=brand.intro_seconds if i==0 else 0.
        tail=brand.outro_seconds if i==len(canonical)-1 else 0.
        source_start=units[0]['start_seconds'] if units else 0.
        following=next((g[0]['start_seconds'] for g in groups[i+1:] if g),meta['duration_seconds'])
        source_end=following if units else 0.
        samples=original[round(source_start*48000):round(source_end*48000)] if units else np.zeros(0,dtype='<i2')
        required=lead+len(samples)/48000+tail
        requested=shot['requested_duration']
        duration=float(requested) if requested is not None else (required if units else max(shot['duration'],required))
        if duration+1/48000<required:
            raise WorkflowError('SHOT_DURATION_NARRATION_OVERFLOW_SHORTEN_OR_EXTEND')
        duration=max(.1,duration)
        target_start=cursor+lead
        placements.append((round(target_start*48000),samples))
        for u in units:
            mapped=copy.deepcopy(u)
            for key in ('start_seconds','end_seconds','activity_start_seconds','activity_end_seconds'):
                mapped[key]=target_start+u[key]-source_start
            mapped['source_start_seconds']=u['start_seconds']; mapped['source_end_seconds']=u['end_seconds']
            mapped['shot_id']=shot['shot_id']; updated.append(mapped)
        layout.append({'scene':i+1,'shot_id':shot['shot_id'],'start':cursor,'end':cursor+duration,'requested_duration':requested,
                       'measured_voice_seconds':len(samples)/48000,'narration_enabled':shot['narration_enabled']})
        cursor+=duration
    target=float(template.duration_seconds) if template else max(25.,cursor)
    if cursor>target+.001 or target>180: raise WorkflowError('TEMPLATE_NARRATION_TOO_LONG_CHOOSE_LONGER_OR_EDIT')
    # A template may hold the final shot; it must never make a requested last shot longer.
    if target>cursor+1/48000:
        if canonical[-1]['requested_duration'] is not None:
            if template: raise WorkflowError('SHOT_EXPLICIT_DURATIONS_DO_NOT_FILL_TEMPLATE')
            target=cursor  # Explicit canonical timings may be shorter than the legacy minimum.
        else: layout[-1]['end']=target
    audio=np.zeros(round(target*48000),dtype='<i2')
    for start,samples in placements:
        if start+len(samples)>len(audio): raise WorkflowError('SHOT_VOICE_PLACEMENT_OVERFLOW')
        audio[start:start+len(samples)]=samples
    path=out/'render-voice.wav'
    with wave.open(str(path),'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(48000); wav.writeframes(audio.tobytes())
    value={**meta,'audio_sha256':file_sha(path),'duration_seconds':target,'units':updated,
           'source_voice_sha256':meta['audio_sha256'],'canonical_timeline_sha256':doc['canonical_timeline']['sha256'],
           'canonical_timeline_version':doc['canonical_timeline']['version'],'sample_preserving_placement':True,
           'speed':1,'pitch_changed':False,'scene_layout':layout,'audio_file':'render-voice.wav'}
    write_json(out/'render-voice.json',value)
    return value
