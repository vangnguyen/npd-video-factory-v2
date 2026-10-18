"""Server-compiled dialogue inputs. Compilation grants neither inference nor render approval."""
import copy,json,re,sqlite3
from pydantic import Field,StrictInt,StrictStr,ValidationError
from app.models import StrictModel
from .contracts import WorkflowError,digest,normalize
from .drama_casting import saved
from .dialogue_plan import build
from .dialogue_audio import profile_signature
from .voice_library import KEY
from .store import now

SCHEMA='native-compiled-dialogue.v1'

class CompileRequest(StrictModel):
    revision:StrictInt=Field(ge=1)
    expected_version:StrictInt=Field(ge=0)
    request_key:StrictStr=Field(pattern=KEY)

def inputs(document):
    from .production_workflows import is_drama
    if is_drama(document) and document.get('drama_script',{}).get('characters_confirmed') is not True:
        raise WorkflowError('DRAMA_CHARACTER_CONFIRMATION_REQUIRED',400)
    from .shot_adapter import shots
    from .voice_quality import resolve_policy
    from .north_star_quality import resolve_policy as quality
    casting=saved(document)
    if casting is None:raise WorkflowError('DRAMA_CASTING_REQUIRED',400)
    values=shots(document);config=casting['configuration'];characters={c['character_id']:c for c in config['characters']}
    active=[v for v in config['lines'] if v['enabled'] and (characters[v['character_id']]['role']!='narrator' or config['narrator_enabled'])]
    takes=document.get('dialogue_delivery_takes',{})
    if (not isinstance(takes,dict) or set(takes)-{v['line_id'] for v in active}
        or any(not isinstance(v,str) or not re.fullmatch(r'take_[a-f0-9]{32}',v) for v in takes.values())):raise WorkflowError('DRAMA_DELIVERY_TAKES_INVALID')
    scene_ids={v['shot_id']:i for i,v in enumerate(values)}
    if not active or any(v['shot_id'] not in scene_ids for v in active):raise WorkflowError('DRAMA_SHOT_BINDING_CHANGED')
    sequence=[scene_ids[v['shot_id']] for v in active]
    if sequence!=sorted(sequence):raise WorkflowError('DRAMA_DIALOGUE_SHOT_ORDER_INVALID')
    for shot in values:
        lines=[v for v in active if v['shot_id']==shot['shot_id']]
        expected=normalize(shot['narration']) if shot['narration_enabled'] else ''
        if normalize(' '.join(v['text'] for v in lines))!=expected or bool(lines)!=bool(expected):
            raise WorkflowError('DRAMA_CANONICAL_SCRIPT_BINDING_CHANGED')
    if normalize(' '.join(v['text'] for v in active))!=normalize(document['proposal']['narration']):raise WorkflowError('DRAMA_CANONICAL_SCRIPT_BINDING_CHANGED')
    return {'configuration':config,'delivery_takes':copy.deepcopy(takes),'narration':document['proposal']['narration'],
        'scenes':[{'shot_id':s['shot_id'],'narration':s['narration'],'enabled':s['narration_enabled']} for s in values],
        'voice_quality':resolve_policy(document),'production_quality':quality(document)}

def specification(document):
    record=document.get('compiled_dialogue')
    if not isinstance(record,dict):raise WorkflowError('DRAMA_DIALOGUE_SPECIFICATION_REQUIRED',400)
    try:
        required={'schema_version','version','project_id','workspace_id','input_sha256','provider_signatures','provider_evidence_modes',
            'voice_bindings','profile_sha256','delivery_plan_sha256','sha256'}
        if (set(record)!=required or record['schema_version']!=SCHEMA or type(record['version']) is not int or record['version']<1
            or not re.fullmatch(r'[a-f0-9]{32}',record['project_id']) or not re.fullmatch(r'wsp_[A-Za-z0-9_-]{1,100}',record['workspace_id'])
            or record['sha256']!=digest({k:v for k,v in record.items() if k!='sha256'})):raise ValueError()
        for field in ('input_sha256','profile_sha256','delivery_plan_sha256'):
            if not re.fullmatch(r'[a-f0-9]{64}',record[field]):raise ValueError()
        signatures=record['provider_signatures'];modes=record['provider_evidence_modes'];voices=record['voice_bindings']
        if (not isinstance(signatures,dict) or not signatures or not isinstance(modes,dict) or set(signatures)!=set(modes)
            or any(not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',k) or not re.fullmatch(r'[a-f0-9]{64}',v) for k,v in signatures.items())
            or any(v not in {'explicit-mock','local-real','real-provider'} for v in modes.values()) or not isinstance(voices,list) or not voices):raise ValueError()
        for voice in voices:
            if (set(voice)!={'voice_id','voice_version','voice_sha256','provider','provider_configuration_sha256'}
                or not re.fullmatch(r'nvoice_[a-f0-9]{32}',voice['voice_id']) or type(voice['voice_version']) is not int or voice['voice_version']<1
                or not re.fullmatch(r'[a-f0-9]{64}',voice['voice_sha256'])
                or voice['provider_configuration_sha256']!=signatures[voice['provider']]):raise ValueError()
        if len({v['voice_id'] for v in voices})!=len(voices):raise ValueError()
        expected=digest({'schema_version':'native-dialogue-audio.v1','workspace_id':record['workspace_id'],
            'voice_bindings':sorted((v['voice_id'],v['voice_version'],v['voice_sha256'],v['provider_configuration_sha256']) for v in voices)})
        if expected!=record['profile_sha256']:raise ValueError()
    except (KeyError,TypeError,ValueError):raise WorkflowError('DRAMA_DIALOGUE_SPECIFICATION_CHANGED') from None
    if digest(inputs(document))!=record['input_sha256']:raise WorkflowError('DRAMA_DIALOGUE_SPECIFICATION_STALE')
    return copy.deepcopy(record)

def validate(document,library,*,con=None,providers=None,project_id=None,require_receipt=True):
    library.scope();record=specification(document)
    if record['workspace_id']!=library.workspace or project_id is not None and record['project_id']!=project_id:raise WorkflowError('DRAMA_DIALOGUE_SCOPE_CHANGED')
    if con is None:
        with library.store.transaction() as current:return validate(document,library,con=current,providers=providers,project_id=project_id,require_receipt=require_receipt)
    if require_receipt:
        try:rows=con.execute("SELECT specification_json FROM native_dialogue_compiles WHERE workspace_id=? AND project_id=? AND json_extract(specification_json,'$.sha256')=?",
            (library.workspace,record['project_id'],record['sha256'])).fetchall()
        except sqlite3.DatabaseError:raise WorkflowError('DRAMA_DIALOGUE_COMPILATION_RECEIPT_CHANGED') from None
        if len(rows)!=1 or json.loads(rows[0][0])!=record:raise WorkflowError('DRAMA_DIALOGUE_COMPILATION_RECEIPT_CHANGED')
    for ref in record['voice_bindings']:
        voice=library._record(con,ref['voice_id'],ref['voice_version']);definition=voice['definition']
        if not voice['current'] or voice['definition_sha256']!=ref['voice_sha256'] or definition['provider']!=ref['provider']:raise WorkflowError('DRAMA_VOICE_BINDING_CHANGED')
        if definition['rights_status'] not in ('owner_declared','source_licensed'):raise WorkflowError('VOICE_RIGHTS_CONFIRMATION_REQUIRED')
        if definition['source_type']=='licensed_reference' and not definition['cloning_consent']:raise WorkflowError('VOICE_REFERENCE_CONSENT_REQUIRED')
    if providers is not None:
        for key,signature in record['provider_signatures'].items():
            adapter=providers.get(key)
            if (adapter is None or adapter.configuration_sha256!=signature or adapter.evidence_mode!=record['provider_evidence_modes'][key]):raise WorkflowError('DRAMA_PROVIDER_CONFIGURATION_CHANGED')
            if type(adapter.paid) is not bool or adapter.paid:raise WorkflowError('DRAMA_PAID_PROVIDER_NOT_ENABLED')
    return record

class NativeDialogueCompiler:
    def __init__(self,store,library,providers):
        if store.root.absolute()!=library.store.root.absolute():raise WorkflowError('DRAMA_WORKSPACE_INVALID')
        self.store,self.library,self.providers=store,library,providers
        with store.transaction() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS native_dialogue_compiles (
                workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,request_key TEXT NOT NULL,request_sha256 TEXT NOT NULL,
                specification_json TEXT NOT NULL,project_revision INTEGER NOT NULL,actor_ref TEXT NOT NULL,created_at TEXT NOT NULL,
                PRIMARY KEY(workspace_id,project_id,request_key))''')

    def compile(self,project_id,payload,*,actor_ref,authorization_check=lambda:None):
        authorization_check();self.library.scope()
        if not isinstance(actor_ref,str) or not 1<=len(actor_ref.strip())<=100:raise WorkflowError('DRAMA_ACTOR_REQUIRED',400)
        try:body=CompileRequest.model_validate(payload).model_dump(mode='json')
        except (TypeError,ValidationError):raise WorkflowError('DRAMA_REQUEST_INVALID',400) from None
        fingerprint=digest(body);workspace=self.library.workspace
        with self.store.transaction() as con:
            old=con.execute('SELECT * FROM native_dialogue_compiles WHERE workspace_id=? AND project_id=? AND request_key=?',(workspace,project_id,body['request_key'])).fetchone()
            if old:
                if old['request_sha256']!=fingerprint:raise WorkflowError('DRAMA_REQUEST_KEY_CONFLICT')
                current=self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone());frozen=json.loads(old['specification_json'])
                return {'project_id':project_id,'project_revision_at_write':old['project_revision'],'specification':frozen,'idempotent_replay':True,
                    'current_for_project':current['revision']==old['project_revision'] and current['document'].get('compiled_dialogue')==frozen,'provider_calls':0,'human_approval_granted':False}
        project=self.store.get(project_id);document=project['document'];stable=inputs(document)
        from .branding import resolve,FIT_NARRATION_POLICY
        _,template=resolve(document)
        if template is None or template.duration_policy!=FIT_NARRATION_POLICY:raise WorkflowError('DRAMA_FIT_NARRATION_TEMPLATE_REQUIRED',400)
        if stable['voice_quality'] is not None:raise WorkflowError('DRAMA_LEGACY_NARRATOR_POLICY_CONFLICT',400)
        signatures={k:v.configuration_sha256 for k,v in self.providers.items()}
        plan=build(stable['configuration'],self.library,provider_signatures=signatures)
        if plan['needs_attention']:raise WorkflowError('DRAMA_DELIVERY_PLAN_NOT_READY',400)
        bindings={};used={}
        for line in plan['lines']:
            voice=self.library.get(line['voice_id'],version=line['voice_version'],for_generation=True);key=voice['definition']['provider'];adapter=self.providers[key]
            if type(adapter.paid) is not bool or adapter.paid:raise WorkflowError('DRAMA_PAID_PROVIDER_NOT_ENABLED')
            if adapter.evidence_mode not in {'explicit-mock','local-real','real-provider'}:raise WorkflowError('DRAMA_PROVIDER_EVIDENCE_MODE_INVALID')
            adapter.validate(voice['definition'],line);used[key]=adapter
            bindings[line['voice_id']]={k:line[k] for k in ('voice_id','voice_version','voice_sha256','provider_configuration_sha256')}
            bindings[line['voice_id']]['provider']=key
        record={'schema_version':SCHEMA,'version':body['expected_version']+1,'project_id':project_id,'workspace_id':workspace,
            'input_sha256':digest(stable),'provider_signatures':{k:signatures[k] for k in sorted(used)},
            'provider_evidence_modes':{k:used[k].evidence_mode for k in sorted(used)},'voice_bindings':[bindings[k] for k in sorted(bindings)],
            'profile_sha256':profile_signature(plan),'delivery_plan_sha256':plan['sha256']}
        record['sha256']=digest(record);authorization_check()
        with self.store.transaction() as con:
            project=self.store.editable(con,project_id,body['revision']);document=copy.deepcopy(project['document']);previous=document.get('compiled_dialogue')
            if (previous['version'] if previous else 0)!=body['expected_version']:raise WorkflowError('DRAMA_DIALOGUE_SPECIFICATION_VERSION_CHANGED')
            document['compiled_dialogue']=record;validate(document,self.library,con=con,providers=self.providers,project_id=project_id,require_receipt=False);authorization_check()
            revision=project['revision']+1;stamp=now()
            con.execute('UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?',(revision,json.dumps(document,ensure_ascii=False),stamp,project_id));self.store.version(con,project_id)
            con.execute('INSERT INTO native_dialogue_compiles VALUES(?,?,?,?,?,?,?,?)',(workspace,project_id,body['request_key'],fingerprint,json.dumps(record,ensure_ascii=False),revision,actor_ref.strip(),stamp))
            self.store.event(con,project_id,'dialogue_specification_compiled',{'revision':revision,'specification_sha256':record['sha256'],'approval_invalidated':True,'provider_calls':0})
        return {'project_id':project_id,'project_revision_at_write':revision,'specification':record,'idempotent_replay':False,'current_for_project':True,'provider_calls':0,'human_approval_granted':False}
