"""Read a measured line from the verified narration PCM. No TTS, cache writes or approval."""
import io,json,re,wave
from .contracts import WorkflowError
from .narration import load

def lines(store,project_id,job_id):
    with store.transaction() as con:
        job,out,result=load(store,con,project_id,job_id)
    meta=json.loads((out/'voice.json').read_bytes())
    if meta.get('schema_version')!='native-dialogue-audio.v1':raise WorkflowError('DRAMA_LINE_LISTENING_UNAVAILABLE',404)
    units=meta['units'];items=[]
    for u in units:
        if not re.fullmatch(r'line_[a-f0-9]{32}',u.get('line_id','')):raise WorkflowError('DRAMA_LINE_LISTENING_BINDING_CHANGED')
        items.append({'line_id':u['line_id'],'speaker_name':u['speaker_name'],'text':u['text'],'voice_id':u['voice_id'],'voice_version':u['voice_version'],
            'start_seconds':u['start_seconds'],'end_seconds':u['end_seconds'],'reused':u['reused'],
            'audio_url':f'/api/projects/{project_id}/narration/{job_id}/lines/{u["line_id"]}/audio'})
    return out,{'project_id':project_id,'job_id':job_id,'items':items,'provider_calls':0,'human_voice_uat_complete':False}

def pcm(store,project_id,job_id,line_id):
    out,page=lines(store,project_id,job_id);line=next((v for v in page['items'] if v['line_id']==line_id),None)
    if line is None:raise WorkflowError('DRAMA_LINE_NOT_FOUND',404)
    with wave.open(str(out/'voice.wav'),'rb') as source:
        rate=source.getframerate();start=round(line['start_seconds']*rate);end=round(line['end_seconds']*rate)
        if (source.getnchannels(),source.getsampwidth(),rate)!=(1,2,48000) or not 0<=start<end<=source.getnframes():raise WorkflowError('DRAMA_LINE_LISTENING_BINDING_CHANGED')
        source.setpos(start);data=source.readframes(end-start)
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as target:target.setnchannels(1);target.setsampwidth(2);target.setframerate(rate);target.writeframes(data)
    return buffer.getvalue()
