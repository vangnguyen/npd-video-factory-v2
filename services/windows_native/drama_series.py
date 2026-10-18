"""Workspace series casting presets. Voices remain independent reusable library records."""
import copy,json,re,uuid
from pydantic import Field,StrictInt,StrictStr,ValidationError
from app.models import StrictModel
from .contracts import WorkflowError,digest
from .drama_casting import DramaConfiguration,saved,SCHEMA as CASTING_SCHEMA
from .voice_library import KEY
from .store import now

SCHEMA='native-drama-series-casting.v1'
SERIES=r'nseries_[a-f0-9]{32}'
class SeriesSave(StrictModel):
    revision:StrictInt=Field(ge=1)
    request_key:StrictStr=Field(pattern=KEY)
    series_id:StrictStr|None=Field(default=None,pattern='^'+SERIES+'$')
    expected_version:StrictInt=Field(ge=0)
    name:StrictStr=Field(min_length=1,max_length=100)
class SeriesApply(StrictModel):
    revision:StrictInt=Field(ge=1)
    request_key:StrictStr=Field(pattern=KEY)
    series_id:StrictStr=Field(pattern='^'+SERIES+'$')
    version:StrictInt=Field(ge=1)
    expected_sha256:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')

class NativeDramaSeries:
    def __init__(self,store,library):
        if store.root.absolute()!=library.store.root.absolute():raise WorkflowError('DRAMA_WORKSPACE_INVALID')
        self.store,self.library=store,library;library.scope()
        with store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_drama_series (
                workspace_id TEXT NOT NULL,series_id TEXT NOT NULL,version INTEGER NOT NULL,record_json TEXT NOT NULL,
                created_at TEXT NOT NULL,PRIMARY KEY(workspace_id,series_id,version));
                CREATE TABLE IF NOT EXISTS native_drama_series_writes (
                workspace_id TEXT NOT NULL,request_key TEXT NOT NULL,request_sha256 TEXT NOT NULL,result_json TEXT NOT NULL,
                actor_ref TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(workspace_id,request_key));''')
    def record(self,con,identifier,version):
        row=con.execute('SELECT record_json FROM native_drama_series WHERE workspace_id=? AND series_id=? AND version=?',(self.library.workspace,identifier,version)).fetchone()
        if row is None:raise WorkflowError('DRAMA_SERIES_NOT_FOUND',404)
        try:
            record=json.loads(row[0]);configuration=DramaConfiguration.model_validate(record['configuration']).model_dump(mode='json')
            if (set(record)!={'schema_version','series_id','version','name','configuration','source_project_id','source_revision','sha256'}
                or record['schema_version']!=SCHEMA or record['series_id']!=identifier or record['version']!=version or configuration['lines']
                or record['sha256']!=digest({k:v for k,v in record.items() if k!='sha256'})):raise ValueError()
        except (KeyError,TypeError,ValueError,ValidationError):raise WorkflowError('DRAMA_SERIES_CHANGED') from None
        return record
    def page(self):
        self.library.scope()
        with self.store.transaction() as con:
            rows=con.execute('SELECT series_id,MAX(version) AS version FROM native_drama_series WHERE workspace_id=? GROUP BY series_id ORDER BY series_id LIMIT 100',(self.library.workspace,)).fetchall()
            return {'items':[self.record(con,r['series_id'],r['version']) for r in rows],'provider_calls':0,'approval_inherited':False}
    def write(self,project_id,payload,*,apply=False,actor_ref,authorization_check=lambda:None):
        authorization_check();self.library.scope()
        if not isinstance(actor_ref,str) or not 1<=len(actor_ref.strip())<=100:raise WorkflowError('DRAMA_ACTOR_REQUIRED',400)
        try:body=(SeriesApply if apply else SeriesSave).model_validate(payload).model_dump(mode='json')
        except (TypeError,ValidationError):raise WorkflowError('DRAMA_REQUEST_INVALID',400) from None
        if not apply and (not body['name'].strip() or (body['series_id'] is None)!=(body['expected_version']==0)):raise WorkflowError('DRAMA_SERIES_REQUEST_INVALID',400)
        fingerprint=digest({'project_id':project_id,'apply':apply,'body':body});workspace=self.library.workspace
        with self.store.transaction() as con:
            old=con.execute('SELECT * FROM native_drama_series_writes WHERE workspace_id=? AND request_key=?',(workspace,body['request_key'])).fetchone()
            if old:
                if old['request_sha256']!=fingerprint:raise WorkflowError('DRAMA_REQUEST_KEY_CONFLICT')
                return {**json.loads(old['result_json']),'idempotent_replay':True}
            project=self.store.editable(con,project_id,body['revision']);document=copy.deepcopy(project['document']);previous=saved(document)
            if apply:
                series=self.record(con,body['series_id'],body['version'])
                if series['sha256']!=body['expected_sha256']:raise WorkflowError('DRAMA_SERIES_VERSION_CHANGED')
                configuration=copy.deepcopy(series['configuration']);configuration['lines']=previous['configuration']['lines'] if previous else []
                if any(line['character_id'] not in {v['character_id'] for v in configuration['characters']} for line in configuration['lines']):raise WorkflowError('DRAMA_SERIES_CHARACTER_REVIEW_REQUIRED',400)
            else:
                if previous is None:raise WorkflowError('DRAMA_CASTING_REQUIRED',400)
                configuration=copy.deepcopy(previous['configuration']);configuration['lines']=[]
            for cast in configuration['casting']:
                voice=self.library._record(con,cast['voice_id'],cast['voice_version'])
                if not voice['current'] or voice['definition_sha256']!=cast['voice_sha256']:raise WorkflowError('DRAMA_VOICE_BINDING_CHANGED')
            authorization_check();stamp=now()
            if apply:
                from .auto_edit_timeline import is_auto_edit
                if is_auto_edit(document):raise WorkflowError('DRAMA_NARRATED_PROJECT_REQUIRED',400)
                casting={'schema_version':CASTING_SCHEMA,'version':(previous['version'] if previous else 0)+1,'configuration':configuration,'sha256':digest(configuration)}
                document['drama_casting']=casting;revision=project['revision']+1
                con.execute('UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?',(revision,json.dumps(document,ensure_ascii=False),stamp,project_id));self.store.version(con,project_id)
                self.store.event(con,project_id,'series_casting_applied',{'series_id':series['series_id'],'version':series['version'],'revision':revision,'approval_invalidated':True,'provider_calls':0})
                result={'project_id':project_id,'project_revision_at_write':revision,'casting':casting,'series':series,'approval_inherited':False,'provider_calls':0}
            else:
                identifier=body['series_id'] or 'nseries_'+uuid.uuid4().hex
                latest=con.execute('SELECT MAX(version) FROM native_drama_series WHERE workspace_id=? AND series_id=?',(workspace,identifier)).fetchone()[0] or 0
                if latest!=body['expected_version']:raise WorkflowError('DRAMA_SERIES_VERSION_CHANGED')
                series={'schema_version':SCHEMA,'series_id':identifier,'version':latest+1,'name':body['name'].strip(),'configuration':configuration,'source_project_id':project_id,'source_revision':project['revision']}
                series['sha256']=digest(series);con.execute('INSERT INTO native_drama_series VALUES(?,?,?,?,?)',(workspace,identifier,latest+1,json.dumps(series,ensure_ascii=False),stamp))
                result={'project_id':project_id,'series':series,'approval_inherited':False,'provider_calls':0}
            con.execute('INSERT INTO native_drama_series_writes VALUES(?,?,?,?,?,?)',(workspace,body['request_key'],fingerprint,json.dumps(result,ensure_ascii=False),actor_ref.strip(),stamp))
        return {**result,'idempotent_replay':False}
