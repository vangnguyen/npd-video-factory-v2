"""Opt-in bridge to the existing human-approved measured narration workflow."""
import json
from .backup import guard
from .contracts import WorkflowError,digest,file_sha,write_json
from .dialogue_binding import specification,validate
from .voice_library import NativeVoiceLibrary

def library_for(store):
    """Attach for reads without creating a second write transaction inside Store.approve."""
    marker=guard(store.root/'.vf-auth-workspace.json');workspace='wsp_native_local'
    if marker.exists():
        try:
            if marker.stat().st_size>4096:raise ValueError()
            value=json.loads(marker.read_bytes())
            if not isinstance(value,dict) or set(value)!={'schema','workspace_id'} or value['schema']!='vf-native-workspace-binding-v1' or not isinstance(value['workspace_id'],str):raise ValueError()
            workspace=value['workspace_id']
        except (OSError,ValueError,TypeError):raise WorkflowError('VOICE_WORKSPACE_INVALID') from None
    library=NativeVoiceLibrary.__new__(NativeVoiceLibrary)
    library.store,library.workspace,library._scope=store,workspace,(store.root.absolute(),workspace)
    library.scope();return library

def providers_for(config):
    from .dialogue_vieneu import PROVIDER,VieNeuDialoguePresetAdapter
    try:return {PROVIDER:VieNeuDialoguePresetAdapter(config)}
    except (WorkflowError,OSError,ValueError):return {}

def require_ready(document,*,store=None,con=None,project_id=None,purpose='production',providers=None):
    if document.get('drama_casting') is None:return None
    if document.get('compiled_dialogue') is None:raise WorkflowError('DRAMA_DIALOGUE_AUDIO_REQUIRED',400)
    if store is None:raise WorkflowError('DRAMA_DIALOGUE_AUTHORITY_REQUIRED')
    from .branding import resolve,FIT_NARRATION_POLICY
    _,template=resolve(document)
    if template is None or template.duration_policy!=FIT_NARRATION_POLICY:raise WorkflowError('DRAMA_FIT_NARRATION_TEMPLATE_REQUIRED',400)
    record=validate(document,library_for(store),con=con,providers=providers,project_id=project_id)
    if purpose!='narration' and not document.get('prepared_narration'):raise WorkflowError('DRAMA_DIALOGUE_AUDIO_REQUIRED',400)
    return record

def expected_profile(document):
    if document.get('drama_casting') is not None:return specification(document)['profile_sha256']
    from .contracts import PROFILE_SHA
    return PROFILE_SHA

def voice_metadata(config,document,directory,meta,*,store=None,con=None):
    """Validate the separate dialogue binding; never relabel it as the old narrator profile."""
    if document.get('drama_casting') is None:return
    from .store import Store
    from .dialogue_audio import measure,SCHEMA
    store=store or Store(config.data_root);record=validate(document,library_for(store),con=con,providers=providers_for(config))
    try:
        plan=json.loads(guard(directory/'tts-plan.json',exists=True).read_bytes())
        bundle=json.loads(guard(directory/'dialogue-audio.json',exists=True).read_bytes())
        if (meta.get('schema_version')!=SCHEMA or meta.get('profile_sha256')!=record['profile_sha256']
            or meta.get('compiled_specification_sha256')!=record['sha256'] or meta.get('evidence_modes')!=sorted(set(record['provider_evidence_modes'].values()))
            or plan.get('schema_version')!=SCHEMA or plan.get('profile_sha256')!=record['profile_sha256']
            or plan.get('delivery_plan',{}).get('sha256')!=record['delivery_plan_sha256']
            or plan['delivery_plan']['sha256']!=digest({k:v for k,v in plan['delivery_plan'].items() if k!='sha256'})
            or plan.get('delivery_takes')!=document.get('dialogue_delivery_takes',{})
            or bundle.get('metadata')!=meta or bundle.get('pcm')!=measure(directory/'voice.wav')):raise ValueError()
        lines=plan['delivery_plan']['lines'];units=meta['units']
        if len(units)!=len(lines):raise ValueError()
        for unit,line in zip(units,lines):
            if any(unit.get(a)!=line[b] for a,b in (('line_id','line_id'),('character_id','character_id'),('speaker_name','character_name'),
                ('voice_id','voice_id'),('voice_version','voice_version'),('text','tts_text'))):raise ValueError()
    except (OSError,KeyError,TypeError,ValueError):raise WorkflowError('DRAMA_MEASURED_AUDIO_BINDING_CHANGED') from None

def authorize_job(config,job,providers):
    from .store import Store
    store=Store(config.data_root);project=store.get(job['project_id']);snapshot=job['snapshot'];approval=snapshot.get('approval')
    if (not approval or approval.get('source')!='local_ui_human_review' or approval.get('snapshot_sha256')!=digest(snapshot['document'])
        or approval.get('revision')!=job['revision'] or project['revision']!=job['revision'] or project['approval']!=approval
        or digest(project['document'])!=digest(snapshot['document'])):raise WorkflowError('DRAMA_CURRENT_HUMAN_APPROVAL_REQUIRED')
    require_ready(snapshot['document'],store=store,project_id=job['project_id'],purpose=job['kind'],providers=providers)
    if job['kind']=='narration' and approval.get('approval_scope')!='narration_only':raise WorkflowError('DRAMA_NARRATION_APPROVAL_REQUIRED')
    return store

def prepare_job(config,job,artifacts,stage):
    from .pipeline import Pipeline
    from .dialogue_audio import prepare,recover_interrupted
    providers=providers_for(config);store=authorize_job(config,job,providers);library=library_for(store)
    recover_interrupted(library)
    completed=[p for p in sorted((artifacts.out/'attempts').glob('dialogue-*'),reverse=True) if all((p/n).is_file() for n in ('voice.wav','voice.json','tts-plan.json','dialogue-audio.json','input.json'))]
    if completed:
        Pipeline.publish_voice(artifacts,completed[0],job,stage,extra_names=('dialogue-audio.json',),dialogue_config=config);return
    attempt=Pipeline.attempt(artifacts.out,'dialogue');stage('project_character_dialogue_tts')
    meta=prepare(config,library,job['snapshot'],providers,attempt,authorization_check=lambda:authorize_job(config,job,providers),on_progress=lambda index,total:stage(f'dialogue_line_{index}_of_{total}'))
    meta['compiled_specification_sha256']=specification(job['snapshot']['document'])['sha256']
    write_json(attempt/'voice.json',meta);bundle=json.loads((attempt/'dialogue-audio.json').read_bytes());bundle['metadata']=meta
    write_json(attempt/'dialogue-audio.json',bundle);write_json(attempt/'input.json',job['snapshot'])
    authorize_job(config,job,providers)
    Pipeline.publish_voice(artifacts,attempt,job,stage,extra_names=('dialogue-audio.json',),dialogue_config=config)
