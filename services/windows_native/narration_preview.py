"""Audible storyboard preview from already approved, immutable narration.

Preview authorization grants no final-render, publishing or inference authority.
"""
import copy,json
from .backup import guard
from .contracts import WorkflowError,digest,file_sha
from .hardening import Artifacts,durable_json
from .narration import SCHEMA,identity,load_reference
PROFILE='native-narrated-storyboard-preview-v1'

def prepared(store,project,*,con=None):
    reference=project['document'].get('prepared_narration')
    if not isinstance(reference,dict) or reference.get('schema_version')!=SCHEMA or reference.get('voice_input_sha256')!=identity(project['document']):raise WorkflowError('PREPARED_NARRATION_INPUT_CHANGED_REPREPARE')
    if con is None:
        with store.transaction() as current:job,out,result=load_reference(store,current,project['id'],project['document'])
    else:job,out,result=load_reference(store,con,project['id'],project['document'])
    plan=result['plan'];approval=job['snapshot'].get('approval')
    if (reference.get('plan_sha256')!=result['plan_sha256'] or reference.get('voice_audio_sha256')!=plan['voice_audio_sha256']
        or not approval or approval.get('revision')!=job['revision'] or approval.get('snapshot_sha256')!=digest(job['snapshot']['document'])):raise WorkflowError('NARRATION_PREVIEW_SOURCE_APPROVAL_CHANGED')
    return job,out,result

def authorization(store,project,*,con=None):
    job,out,result=prepared(store,project,con=con);canonical=project['document']['canonical_timeline']
    return {'schema_version':PROFILE,'project_id':project['id'],'revision':project['revision'],'document_sha256':digest(project['document']),
        'canonical_timeline_version':canonical['version'],'canonical_timeline_sha256':canonical['sha256'],'prepared_reference_sha256':digest(project['document']['prepared_narration']),
        'voice_input_sha256':result['plan']['voice_input_sha256'],'voice_audio_sha256':result['plan']['voice_audio_sha256'],
        'source_narration_job_id':job['id'],'source_plan_sha256':result['plan_sha256'],'source_approval_sha256':digest(job['snapshot']['approval']),
        'final_render_authorized':False,'publishing_authorized':False,'new_inference_authorized':False}

def snapshot(store,project):return {'document':copy.deepcopy(project['document']),'approval':None,'preview_authorization':authorization(store,project)}

def validate_context(config,value):
    from .store import Store
    context=value.get('preview_authorization')
    if value.get('approval') is not None or not isinstance(context,dict) or context.get('schema_version')!=PROFILE:raise WorkflowError('NARRATION_PREVIEW_AUTHORIZATION_INVALID')
    store=Store(config.data_root);project=store.get(context.get('project_id'))
    if project['revision']!=context.get('revision') or digest(project['document'])!=digest(value['document']) or context!=authorization(store,project):raise WorkflowError('NARRATION_PREVIEW_INPUT_CHANGED')
    return context

def folder_for(config,project):
    state=project['document']['canonical_timeline']
    return config.data_root/'shot-previews'/digest({'project':project['id'],'timeline':state['sha256'],'revision':project['revision'],'preview_profile':PROFILE})

def render(config,store,project,folder,event):
    from .pipeline import Pipeline,render as render_storyboard
    if guard(folder,exists=True).resolve()!=folder_for(config,project).resolve():raise WorkflowError('NARRATION_PREVIEW_FOLDER_INVALID')
    if event.is_set():raise WorkflowError('PREVIEW_CANCELLED')
    value=snapshot(store,project);validate_context(config,value);_,source,_=prepared(store,project)
    job={'id':folder.name[:32],'project_id':project['id'],'revision':project['revision'],'snapshot':value}
    attempt=Pipeline.attempt(folder,'narration-preview');target=Artifacts(attempt,job)
    for name in ('voice.wav','voice.json','tts-plan.json'):target.publish(source/name,name)
    durable_json(attempt/'input.json',value)
    qc=render_storyboard(config,value,attempt,preview_only=True)
    if event.is_set():raise WorkflowError('PREVIEW_CANCELLED')
    validate_context(config,value)
    published=Artifacts(folder,job);files=[]
    published.path('subtitle-qc').mkdir(exist_ok=True)
    names=['render-manifest.json','qc-report.json','full-qc-report.json','transport-qc-report.json','subtitles.ass','timeline.json','voice.json']
    if (attempt/'render-voice.json').is_file():names.append('render-voice.json')
    names+= [path.relative_to(attempt).as_posix() for path in sorted((attempt/'subtitle-qc').glob('*.png'))]
    for name in names:files.append(published.metadata(published.publish(attempt/name,name)))
    output=published.publish(attempt/'final.mp4','preview.mp4')
    manifest={'schema_version':PROFILE,'preview_authorization':value['preview_authorization'],'project_id':project['id'],'revision':project['revision'],
        'document_sha256':digest(project['document']),'timeline_version':project['document']['canonical_timeline']['version'],'timeline_sha256':project['document']['canonical_timeline']['sha256'],
        'playable':True,'audio_mode':'measured_scene_narration_full_effects_preview','output_sha256':file_sha(output),'artifacts':files,'qc':qc,
        'voice_input_sha256':value['preview_authorization']['voice_input_sha256'],'source_voice_sha256':value['preview_authorization']['voice_audio_sha256'],
        'rendering_effects_parity':True,'final_render_parity':False,'human_final_video_accepted':False,'final_render_authorized':False,'publishing_authorized':False,
        'new_inference_calls':0,'external_provider_calls':0}
    durable_json(folder/'preview-manifest.json',manifest);return manifest

def reviewed(store,config,project,*,con=None):
    from .media import verify_selected_files
    expected=authorization(store,project,con=con);folder=folder_for(config,project)
    if not folder.exists():raise WorkflowError('NARRATION_CURRENT_AUDIBLE_PREVIEW_REVIEW_REQUIRED',400)
    folder=guard(folder,exists=True)
    try:
        record=json.loads((folder/'preview.json').read_bytes());manifest=json.loads((folder/'preview-manifest.json').read_bytes())
        if (record.get('status')!='READY' or record.get('project_id')!=project['id'] or record.get('revision')!=project['revision'] or record.get('preview_profile')!=PROFILE
            or record.get('manifest')!=manifest or record.get('manifest_sha256')!=file_sha(folder/'preview-manifest.json') or manifest.get('preview_authorization')!=expected
            or manifest.get('playable') is not True or manifest.get('audio_mode')!='measured_scene_narration_full_effects_preview' or not manifest.get('qc',{}).get('passed')
            or manifest.get('final_render_authorized') is not False or manifest.get('publishing_authorized') is not False or manifest.get('new_inference_calls')!=0
            or file_sha(folder/'preview.mp4')!=manifest.get('output_sha256') or record.get('sha256')!=manifest.get('output_sha256')):raise ValueError()
        artifacts=manifest.get('artifacts')
        required={'render-manifest.json','qc-report.json','full-qc-report.json','transport-qc-report.json','subtitles.ass','timeline.json','voice.json'}
        if not isinstance(artifacts,list) or not 7<=len(artifacts)<=256 or len({item['path'] for item in artifacts})!=len(artifacts) or not required.issubset({item['path'] for item in artifacts}):raise ValueError()
        bound=Artifacts(folder,{'snapshot':{'document':project['document'],'approval':None}})
        for item in artifacts:
            path=guard(bound.path(item['path']),exists=True)
            if path.stat().st_size!=item['bytes'] or file_sha(path)!=item['sha256']:raise ValueError()
        full=json.loads((folder/'full-qc-report.json').read_bytes())
        if full!=manifest['qc']['full_quality'] or full.get('status')!='passed' or full.get('render_purpose')!='narration_preview' or full.get('final_sha256')!=manifest['output_sha256'] or full.get('document_sha256')!=expected['document_sha256']:raise ValueError()
        verify_selected_files(config,project['document'])
    except (OSError,ValueError,KeyError,TypeError):raise WorkflowError('NARRATION_CURRENT_AUDIBLE_PREVIEW_REVIEW_REQUIRED',400) from None
    return {'id':folder.name,'sha256':manifest['output_sha256'],'manifest_sha256':file_sha(folder/'preview-manifest.json'),'profile':PROFILE,
        'timeline_version':manifest['timeline_version'],'timeline_sha256':manifest['timeline_sha256'],'document_sha256':manifest['document_sha256'],
        'source_narration_job_id':expected['source_narration_job_id'],'source_plan_sha256':expected['source_plan_sha256'],'voice_audio_sha256':expected['voice_audio_sha256'],
        'final_render_parity':False,'final_video_review_required':True,'rendering_effects_parity':True,'new_inference_calls':0}

def validate_render_approval(config,job):
    from .store import Store
    approval=job['snapshot'].get('approval');document=job['snapshot']['document']
    if not approval or approval.get('approval_scope')=='narration_only' or approval.get('render_mode')!='prepared_narration' or approval.get('revision')!=job['revision'] or approval.get('snapshot_sha256')!=digest(document):raise WorkflowError('NARRATION_AUDIBLE_PREVIEW_APPROVAL_REQUIRED',400)
    store=Store(config.data_root);project=store.get(job['project_id'])
    if project['revision']!=job['revision'] or digest(project['document'])!=digest(document) or project['approval']!=approval or approval.get('reviewed_preview')!=reviewed(store,config,project):raise WorkflowError('NARRATION_AUDIBLE_PREVIEW_APPROVAL_CHANGED',400)
    return approval
