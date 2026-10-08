"""Measured, versioned scene narration preparation over the existing TTS worker.

Preparing audio never changes edits. Applying measured scene durations is an
explicit canonical edit, clears render approval, and retains the original PCM.
"""
import copy,json,wave
from .contracts import WorkflowError,PROFILE_SHA,Proposal,digest,file_sha,write_json
from .hardening import Artifacts
from .branding import resolve,FIT_NARRATION_POLICY
from .voice_quality import resolve_policy
from .north_star_quality import resolve_policy as production_policy
from .backup import guard
SCHEMA='native-scene-narration-plan-v1'

def identity(document):
    from .shot_adapter import shots
    proposal=Proposal.model_validate(document['proposal']);values=shots(document)
    if not values:raise WorkflowError('NARRATION_CANONICAL_SHOTS_REQUIRED',400)
    return digest({'schema_version':SCHEMA,'profile_sha256':PROFILE_SHA,'voice_quality':resolve_policy(document),'production_quality':production_policy(document),
        'narration':proposal.narration,'scenes':[{'shot_id':shot['shot_id'],'scene':i+1,'narration':shot['narration'],'enabled':shot['narration_enabled']} for i,shot in enumerate(values)]})

def prepare(config,job,out,artifacts):
    from .pipeline import measured_scene_units
    from .shot_adapter import shots
    checkpoint=artifacts.load('narration')
    if checkpoint:return checkpoint['result']
    if not artifacts.load('tts'):raise WorkflowError('NARRATION_VERIFIED_TTS_REQUIRED')
    document=job['snapshot']['document'];approval=job['snapshot'].get('approval')
    if not approval or approval.get('revision')!=job['revision'] or approval.get('snapshot_sha256')!=digest(document):raise WorkflowError('HUMAN_APPROVAL_REQUIRED_BEFORE_TTS')
    meta=json.loads((out/'voice.json').read_bytes());groups=measured_scene_units(Proposal.model_validate(document['proposal']),meta)
    if meta['profile_sha256']!=PROFILE_SHA or meta['audio_sha256']!=file_sha(out/'voice.wav'):raise WorkflowError('VOICE_ARTIFACT_BINDING_MISMATCH')
    with wave.open(str(out/'voice.wav'),'rb') as audio:
        if (audio.getnchannels(),audio.getsampwidth(),audio.getframerate())!=(1,2,48000) or abs(audio.getnframes()/48000-meta['duration_seconds'])>1/48000:raise WorkflowError('NARRATION_WAVE_FORMAT_OR_DURATION_CHANGED')
    brand,template=resolve(document);values=shots(document);items=[];cursor=0.
    for i,(shot,units) in enumerate(zip(values,groups)):
        lead=brand.intro_seconds if i==0 else 0.;tail=brand.outro_seconds if i==len(values)-1 else 0.
        start=units[0]['start_seconds'] if units else 0.;end=next((group[0]['start_seconds'] for group in groups[i+1:] if group),meta['duration_seconds']) if units else 0.
        source_seconds=(round(end*48000)-round(start*48000))/48000
        duration=max(4800,round(lead*48000)+round(source_seconds*48000)+round(tail*48000))/48000 if units else max(shot['duration'],lead+tail,.1)
        items.append({'scene':i+1,'shot_id':shot['shot_id'],'narration':shot['narration'],'narration_enabled':shot['narration_enabled'],
            'source_start_seconds':start,'source_end_seconds':end,'measured_audio_seconds':source_seconds,'recommended_duration_seconds':duration,
            'start_seconds':cursor,'end_seconds':cursor+duration,'intro_seconds':lead,'outro_seconds':tail,'units':copy.deepcopy(units)})
        cursor+=duration
    if cursor>180:raise WorkflowError('NARRATION_MEASURED_DURATION_EXCEEDS_LIMIT',400)
    plan={'schema_version':SCHEMA,'version':1,'project_id':job['project_id'],'job_id':job['id'],'source_revision':job['revision'],
        'source_document_sha256':digest(document),'source_approval_sha256':digest(approval),'source_canonical_timeline':{'version':document['canonical_timeline']['version'],'sha256':document['canonical_timeline']['sha256']},
        'voice_input_sha256':identity(document),'voice_audio_sha256':meta['audio_sha256'],'voice_metadata_sha256':file_sha(out/'voice.json'),
        'tts_plan_sha256':file_sha(out/'tts-plan.json'),'profile_sha256':PROFILE_SHA,'source_duration_seconds':meta['duration_seconds'],
        'recommended_duration_seconds':cursor,'items':items,'brand_template_sha256':digest(document.get('brand_template')),
        'fit_narration_template':template is not None and template.duration_policy==FIT_NARRATION_POLICY,'timing_basis':'measured_pcm_scene_units_not_word_alignment',
        'confidence':None,'speech_quality_accepted':False,'word_alignment_claimed':False,'canonical_timeline_mutated':False,'human_final_video_accepted':False,'render_dispatched':False}
    write_json(out/'narration-plan.json',plan);result={'schema_version':SCHEMA,'status':'ready_for_timing_review','plan':plan,'plan_sha256':digest(plan),
        'voice_url':f"/api/projects/{job['project_id']}/narration/{job['id']}/audio",'automatic_timeline_apply':False,'automatic_render':False}
    artifacts.commit('narration',[out/'narration-plan.json',out/'voice.wav',out/'voice.json',out/'tts-plan.json'],result);return result

def load(store,con,project_id,job_id):
    row=con.execute('SELECT * FROM jobs WHERE id=? AND project_id=?',(job_id,project_id)).fetchone()
    if row is None:raise WorkflowError('NARRATION_JOB_NOT_FOUND',404)
    job=store.job(row,con)
    if job['kind']!='narration' or job['status']!='succeeded':raise WorkflowError('NARRATION_JOB_NOT_READY',409)
    out=guard(store.root/'jobs'/job_id,exists=True);artifacts=Artifacts(out,job);tts=artifacts.load('tts');record=artifacts.load('narration')
    if not tts or not record or record['result']!=job['result']:raise WorkflowError('NARRATION_CHECKPOINT_CHANGED')
    result=record['result'];plan=json.loads((out/'narration-plan.json').read_bytes())
    if result['plan']!=plan or result['plan_sha256']!=digest(plan) or plan['schema_version']!=SCHEMA or plan['project_id']!=project_id or plan['job_id']!=job_id or plan['source_document_sha256']!=digest(job['snapshot']['document']) or plan['source_approval_sha256']!=digest(job['snapshot']['approval']):raise WorkflowError('NARRATION_PLAN_BINDING_CHANGED')
    return job,out,result

def page(store,project_id):
    with store.transaction() as con:
        project=store.project(con.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone());items=[]
        for row in con.execute("SELECT * FROM jobs WHERE project_id=? AND kind='narration' ORDER BY created_at DESC LIMIT 50",(project_id,)):
            job=store.job(row,con);result=None
            if job['status']=='succeeded':_,_,result=load(store,con,project_id,job['id'])
            try:current=result is not None and result['plan']['voice_input_sha256']==identity(project['document'])
            except (WorkflowError,ValueError,KeyError,TypeError):current=False
            items.append({'job_id':job['id'],'revision':job['revision'],'status':job['status'],'error':job['error'],'result':result,'voice_input_current':current,
                'timing_apply_current':current and result['plan']['source_document_sha256']==digest(project['document'])})
    return {'schema_version':SCHEMA,'project_id':project_id,'revision':project['revision'],'items':items,'prepared_narration':project['document'].get('prepared_narration')}

def apply(store,project_id,job_id,payload):
    from .shot_adapter import _state,shots_from_snapshot,_check_shot,_assets,project_projection,snapshot_from_shots,validate_document
    from .store import now
    if not isinstance(payload,dict) or set(payload)!={'revision','expected_plan_sha256','acknowledged'} or type(payload['revision']) is not int or payload['acknowledged'] is not True:raise WorkflowError('NARRATION_TIMING_REVIEW_REQUIRED',400)
    with store.transaction() as con:
        project=store.editable(con,project_id,payload['revision']);job,out,result=load(store,con,project_id,job_id);plan=result['plan'];doc=project['document']
        if payload['expected_plan_sha256']!=result['plan_sha256'] or plan['source_document_sha256']!=digest(doc) or plan['voice_input_sha256']!=identity(doc) or plan['brand_template_sha256']!=digest(doc.get('brand_template')):raise WorkflowError('NARRATION_TIMING_PLAN_STALE')
        if not plan['fit_narration_template']:raise WorkflowError('NARRATION_FIT_TEMPLATE_REQUIRED',400)
        state,_=_state(project);values=shots_from_snapshot(state['snapshot'])
        if [v['shot_id'] for v in values]!=[i['shot_id'] for i in plan['items']]:raise WorkflowError('NARRATION_CANONICAL_SHOTS_CHANGED')
        for shot,item in zip(values,plan['items']):
            shot['duration']=item['recommended_duration_seconds'];shot['requested_duration']=item['recommended_duration_seconds'];_check_shot(shot,_assets(doc))
        updated=project_projection(doc,values);timeline=snapshot_from_shots(values,updated,canvas=state['snapshot'])
        updated['canonical_timeline']={'version':state['version']+1,'snapshot':timeline,'sha256':digest(timeline)}
        updated['prepared_narration']={'schema_version':SCHEMA,'job_id':job_id,'plan_sha256':result['plan_sha256'],'voice_input_sha256':plan['voice_input_sha256'],
            'voice_audio_sha256':plan['voice_audio_sha256'],'applied_from_revision':project['revision'],'review_required':True,'automatic_render':False}
        validate_document(updated)
        con.execute('UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?',(project['revision']+1,json.dumps(updated,ensure_ascii=False),now(),project_id));store.version(con,project_id)
        store.event(con,project_id,'narration_measured_timing_applied_approval_invalidated',{'job_id':job_id,'plan_sha256':result['plan_sha256'],'revision':project['revision']+1,
            'timeline_version':state['version']+1,'timeline_sha256':digest(timeline),'provider_calls':0,'automatic_render':False,'human_review_required':True})
    return store.shot_view(project_id)

def reuse(config,job,artifacts,stage):
    """Reuse only verified, approved source PCM with the same current voice inputs."""
    from .store import Store
    from .pipeline import Pipeline
    reference=job['snapshot']['document'].get('prepared_narration')
    if reference is None:return False
    if not isinstance(reference,dict) or reference.get('schema_version')!=SCHEMA or reference.get('voice_input_sha256')!=identity(job['snapshot']['document']):raise WorkflowError('PREPARED_NARRATION_INPUT_CHANGED_REPREPARE')
    store=Store(config.data_root)
    with store.transaction() as con:source,source_out,result=load(store,con,job['project_id'],reference['job_id'])
    plan=result['plan']
    if result['plan_sha256']!=reference.get('plan_sha256') or plan['voice_audio_sha256']!=reference.get('voice_audio_sha256') or plan['voice_input_sha256']!=identity(job['snapshot']['document']):raise WorkflowError('PREPARED_NARRATION_BINDING_CHANGED')
    attempt=Pipeline.attempt(artifacts.out,'voice-reuse');copy_artifacts=Artifacts(attempt,job)
    for name in ('voice.wav','voice.json','tts-plan.json'):copy_artifacts.publish(source_out/name,name)
    write_json(attempt/'input.json',job['snapshot']);write_json(attempt/'voice-reuse.json',{'schema_version':'native-prepared-narration-reuse-v1',
        'source_job_id':source['id'],'source_revision':source['revision'],'source_snapshot_sha256':digest(source['snapshot']),'source_plan_sha256':result['plan_sha256'],
        'voice_input_sha256':plan['voice_input_sha256'],'source_voice_sha256':plan['voice_audio_sha256'],'new_inference_calls':0,'sample_preserving':True})
    Pipeline.publish_voice(artifacts,attempt,job,stage,extra_names=('voice-reuse.json',));return True
