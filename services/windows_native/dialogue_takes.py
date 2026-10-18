"""Explicit per-line new takes. A retry receipt never dispatches or repeats TTS."""
import copy,json,uuid
from pydantic import Field,StrictInt,StrictStr,ValidationError,model_validator
from app.models import StrictModel
from .contracts import WorkflowError,digest
from .drama_casting import saved
from .voice_library import KEY
from .store import now

class NewTakes(StrictModel):
    revision:StrictInt=Field(ge=1)
    expected_casting_sha256:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
    request_key:StrictStr=Field(pattern=KEY)
    line_ids:list[StrictStr]=Field(min_length=1,max_length=500)
    @model_validator(mode='after')
    def distinct(self):
        import re
        if len(set(self.line_ids))!=len(self.line_ids) or any(not re.fullmatch(r'line_[a-f0-9]{32}',v) for v in self.line_ids):raise ValueError('unique dialogue lines required')
        return self

class NativeDialogueTakes:
    def __init__(self,store,library):
        if store.root.absolute()!=library.store.root.absolute():raise WorkflowError('DRAMA_WORKSPACE_INVALID')
        self.store,self.library=store,library
        with store.transaction() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS native_dialogue_takes (
                workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,request_key TEXT NOT NULL,request_sha256 TEXT NOT NULL,
                takes_json TEXT NOT NULL,project_revision INTEGER NOT NULL,actor_ref TEXT NOT NULL,created_at TEXT NOT NULL,
                PRIMARY KEY(workspace_id,project_id,request_key))''')

    def create(self,project_id,payload,*,actor_ref,authorization_check=lambda:None):
        authorization_check();self.library.scope()
        if not isinstance(actor_ref,str) or not 1<=len(actor_ref.strip())<=100:raise WorkflowError('DRAMA_ACTOR_REQUIRED',400)
        try:body=NewTakes.model_validate(payload).model_dump(mode='json')
        except (TypeError,ValidationError):raise WorkflowError('DRAMA_REQUEST_INVALID',400) from None
        fingerprint=digest(body);workspace=self.library.workspace
        with self.store.transaction() as con:
            old=con.execute('SELECT * FROM native_dialogue_takes WHERE workspace_id=? AND project_id=? AND request_key=?',(workspace,project_id,body['request_key'])).fetchone()
            if old:
                if old['request_sha256']!=fingerprint:raise WorkflowError('DRAMA_REQUEST_KEY_CONFLICT')
                current=self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone())
                return {'project_id':project_id,'project_revision_at_write':old['project_revision'],'takes':json.loads(old['takes_json']),
                    'idempotent_replay':True,'current_for_project':current['revision']==old['project_revision'],'provider_calls':0,'new_approval_required':True}
            project=self.store.editable(con,project_id,body['revision']);document=copy.deepcopy(project['document']);casting=saved(document)
            if casting is None or casting['sha256']!=body['expected_casting_sha256']:raise WorkflowError('DRAMA_CASTING_VERSION_CHANGED')
            config=casting['configuration'];characters={v['character_id']:v for v in config['characters']}
            active={v['line_id'] for v in config['lines'] if v['enabled'] and (characters[v['character_id']]['role']!='narrator' or config['narrator_enabled'])}
            if set(body['line_ids'])-active:raise WorkflowError('DRAMA_ACTIVE_DIALOGUE_LINE_REQUIRED',400)
            takes={k:v for k,v in document.get('dialogue_delivery_takes',{}).items() if k in active}
            for line_id in body['line_ids']:takes[line_id]='take_'+uuid.uuid4().hex
            document['dialogue_delivery_takes']=takes;revision=project['revision']+1;stamp=now();authorization_check()
            con.execute('UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?',(revision,json.dumps(document,ensure_ascii=False),stamp,project_id));self.store.version(con,project_id)
            con.execute('INSERT INTO native_dialogue_takes VALUES(?,?,?,?,?,?,?,?)',(workspace,project_id,body['request_key'],fingerprint,json.dumps(takes),revision,actor_ref.strip(),stamp))
            self.store.event(con,project_id,'dialogue_new_takes_requested',{'revision':revision,'line_ids':body['line_ids'],'approval_invalidated':True,'provider_calls':0,'visual_regeneration_ids':[]})
        return {'project_id':project_id,'project_revision_at_write':revision,'takes':takes,'idempotent_replay':False,'current_for_project':True,'provider_calls':0,'new_approval_required':True}
