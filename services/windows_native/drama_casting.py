"""Project characters/casts/dialogue drafts; no implicit single-voice fallback."""
import copy,json,math
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,StrictStr,ValidationError,model_validator
from app.models import StrictModel
from .contracts import WorkflowError,digest
from .store import now
from .voice_library import VOICE_ID,KEY

SCHEMA='native-drama-casting.v1'

class Character(StrictModel):
    character_id:StrictStr=Field(pattern=r'^chr_[a-f0-9]{32}$')
    name:StrictStr=Field(min_length=1,max_length=100)
    role:Literal['character','narrator']='character'

class Cast(StrictModel):
    character_id:StrictStr=Field(pattern=r'^chr_[a-f0-9]{32}$')
    voice_id:StrictStr=Field(pattern='^'+VOICE_ID+'$')
    voice_version:StrictInt=Field(ge=1)
    voice_sha256:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')

class DialogueLine(StrictModel):
    line_id:StrictStr=Field(pattern=r'^line_[a-f0-9]{32}$')
    character_id:StrictStr=Field(pattern=r'^chr_[a-f0-9]{32}$')
    shot_id:StrictStr|None=Field(default=None,pattern=r'^shot_[a-f0-9]{32}$')
    text:StrictStr=Field(min_length=1,max_length=4000)
    enabled:StrictBool=True
    speed:float=Field(default=1.0,ge=.5,le=2,strict=True)
    style:Literal['neutral','warm','serious','energetic','soft']='neutral'
    pause_after_seconds:float=Field(default=.15,ge=0,le=3,strict=True)
    @model_validator(mode='after')
    def finite(self):
        if not self.text.strip() or not math.isfinite(self.speed) or not math.isfinite(self.pause_after_seconds):raise ValueError('finite nonblank dialogue required')
        return self

class DramaConfiguration(StrictModel):
    narrator_enabled:StrictBool=False
    characters:list[Character]=Field(min_length=1,max_length=50)
    casting:list[Cast]=Field(default_factory=list,max_length=50)
    lines:list[DialogueLine]=Field(default_factory=list,max_length=500)
    @model_validator(mode='after')
    def references(self):
        ids={c.character_id for c in self.characters};narrators=[c for c in self.characters if c.role=='narrator']
        if len(ids)!=len(self.characters) or any(not c.name.strip() for c in self.characters):raise ValueError('unique named characters required')
        if len(narrators)>1 or self.narrator_enabled and not narrators:raise ValueError('one narrator required when enabled')
        if len({c.character_id for c in self.casting})!=len(self.casting) or any(c.character_id not in ids for c in self.casting):raise ValueError('unique known casting required')
        if len({line.line_id for line in self.lines})!=len(self.lines) or any(line.character_id not in ids for line in self.lines):raise ValueError('unique known speaker lines required')
        return self

class CastingSave(StrictModel):
    revision:StrictInt=Field(ge=1)
    expected_version:StrictInt=Field(ge=0)
    request_key:StrictStr=Field(pattern=KEY)
    configuration:DramaConfiguration
    sync_canonical_script:StrictBool=False
    clear_legacy_voice_policy:StrictBool=False

def saved(document):
    record=document.get('drama_casting')
    if record is None:return None
    try:
        if set(record)!={'schema_version','version','configuration','sha256'} or record['schema_version']!=SCHEMA or type(record['version']) is not int or record['version']<1:raise ValueError()
        config=DramaConfiguration.model_validate(record['configuration']).model_dump(mode='json')
        if digest(config)!=record['sha256']:raise ValueError()
    except (TypeError,ValueError,ValidationError):raise WorkflowError('DRAMA_CASTING_CHANGED') from None
    return copy.deepcopy(record)

def require_execution_ready(document,**context):
    if saved(document) is not None:
        from .dialogue_runtime import require_ready
        return require_ready(document,**context)

class NativeDramaCasting:
    def __init__(self,store,library):
        if store.root.absolute()!=library.store.root.absolute():raise WorkflowError('DRAMA_WORKSPACE_INVALID')
        self.store,self.library=store,library;library.scope()
        with store.transaction() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS native_drama_writes (
                workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,request_key TEXT NOT NULL,request_sha256 TEXT NOT NULL,
                casting_json TEXT NOT NULL,project_revision INTEGER NOT NULL,actor_ref TEXT NOT NULL,created_at TEXT NOT NULL,
                PRIMARY KEY(workspace_id,project_id,request_key))''')

    def view(self,project_id):
        self.library.scope();project=self.store.get(project_id);record=saved(project['document'])
        return {'project_id':project_id,'project_revision':project['revision'],'casting':record,'narrator_enabled':record['configuration']['narrator_enabled'] if record else False,
            'per_line_tts_ready':False,'provider_calls':0,'human_voice_uat_complete':False}

    def save(self,project_id,payload,*,actor_ref,authorization_check=lambda:None):
        self.library.scope();authorization_check();self.library.scope()
        if not isinstance(actor_ref,str) or not 1<=len(actor_ref.strip())<=100:raise WorkflowError('DRAMA_ACTOR_REQUIRED',400)
        try:body=CastingSave.model_validate(payload).model_dump(mode='json')
        except (TypeError,ValidationError):raise WorkflowError('DRAMA_REQUEST_INVALID',400) from None
        fingerprint=digest(body);workspace=self.library.workspace
        with self.store.transaction() as con:
            old=con.execute('SELECT * FROM native_drama_writes WHERE workspace_id=? AND project_id=? AND request_key=?',(workspace,project_id,body['request_key'])).fetchone()
            if old:
                if old['request_sha256']!=fingerprint:raise WorkflowError('DRAMA_REQUEST_KEY_CONFLICT')
                current=self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone())
                frozen=json.loads(old['casting_json']);saved({'drama_casting':frozen})
                return {'project_id':project_id,'project_revision_at_write':old['project_revision'],'casting':frozen,'idempotent_replay':True,
                    'current_for_project':current['revision']==old['project_revision'] and saved(current['document'])==frozen,'per_line_tts_ready':False,'provider_calls':0}
            project=self.store.editable(con,project_id,body['revision']);document=copy.deepcopy(project['document'])
            from .auto_edit_timeline import is_auto_edit
            if is_auto_edit(document):raise WorkflowError('DRAMA_NARRATED_PROJECT_REQUIRED',400)
            previous=saved(document)
            if (previous['version'] if previous else 0)!=body['expected_version']:raise WorkflowError('DRAMA_CASTING_VERSION_CHANGED')
            config=body['configuration']
            if body['clear_legacy_voice_policy'] and 'voice_quality' in document:
                before_policy=copy.deepcopy(document);document.pop('voice_quality')
                if not body['sync_canonical_script']:document=self.store.sync_shot_document(document,before_policy,project_id)
            for cast in config['casting']:
                voice=self.library._record(con,cast['voice_id'],cast['voice_version'])
                if not voice['current'] or voice['definition_sha256']!=cast['voice_sha256']:raise WorkflowError('DRAMA_VOICE_BINDING_CHANGED')
            if any(line['shot_id'] is not None for line in config['lines']):
                from .shot_adapter import shots
                known={s['shot_id'] for s in shots(document)}
                if any(line['shot_id'] is not None and line['shot_id'] not in known for line in config['lines']):raise WorkflowError('DRAMA_SHOT_BINDING_CHANGED')
            if body['sync_canonical_script']:
                from .shot_adapter import _state,shots_from_snapshot,project_projection,snapshot_from_shots,validate_document
                from .contracts import normalize
                state,_=_state(project);values=shots_from_snapshot(state['snapshot']);characters={v['character_id']:v for v in config['characters']}
                active=[v for v in config['lines'] if v['enabled'] and (characters[v['character_id']]['role']!='narrator' or config['narrator_enabled'])]
                if not active or any(v['shot_id'] is None for v in active):raise WorkflowError('DRAMA_ACTIVE_DIALOGUE_SHOTS_REQUIRED',400)
                for shot in values:
                    text=normalize(' '.join(v['text'] for v in active if v['shot_id']==shot['shot_id']))
                    if text:shot['narration']=text
                    shot['narration_enabled']=bool(text);shot['subtitle']=text
                document=project_projection(document,values)
                timeline=snapshot_from_shots(values,document,canvas=state['snapshot'])
                document['canonical_timeline']={'version':state['version']+1,'snapshot':timeline,'sha256':digest(timeline)}
                validate_document(document)
            record={'schema_version':SCHEMA,'version':body['expected_version']+1,'configuration':config,'sha256':digest(config)}
            if 'dialogue_delivery_takes' in document:
                characters={v['character_id']:v for v in config['characters']}
                active={v['line_id'] for v in config['lines'] if v['enabled'] and (characters[v['character_id']]['role']!='narrator' or config['narrator_enabled'])}
                document['dialogue_delivery_takes']={k:v for k,v in document['dialogue_delivery_takes'].items() if k in active}
            document['drama_casting']=record
            if document.get('canonical_timeline'):
                from .shot_adapter import validate_document
                validate_document(document)
            revision=project['revision']+1;stamp=now();authorization_check()
            con.execute('UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?',(revision,json.dumps(document,ensure_ascii=False),stamp,project_id))
            self.store.version(con,project_id)
            con.execute('INSERT INTO native_drama_writes VALUES(?,?,?,?,?,?,?,?)',(workspace,project_id,body['request_key'],fingerprint,json.dumps(record,ensure_ascii=False),revision,actor_ref.strip(),stamp))
            self.store.event(con,project_id,'drama_casting_saved',{'revision':revision,'casting_version':record['version'],'approval_invalidated':True,'preview_invalidated':True,'final_export_invalidated':True,'provider_calls':0})
        return {'project_id':project_id,'project_revision_at_write':revision,'casting':record,'idempotent_replay':False,'current_for_project':True,'per_line_tts_ready':False,'provider_calls':0}
