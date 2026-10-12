"""Workspace-scoped immutable channel versions; built-ins and projects stay frozen."""
import copy,json,re
from pydantic import Field,StrictInt,model_validator
from typing import Literal
from app.models import StrictModel
from .contracts import WorkflowError,digest
from .channel_profiles import ChannelProfile,FrozenSelection,resolve_profile,catalog as builtin_catalog
from .store import now

KEY=r'^[a-z][a-z0-9-]{2,49}$'
SHA=r'^[a-f0-9]{64}$'
SQL='''
CREATE TABLE IF NOT EXISTS native_channel_profile_versions(
 workspace_id TEXT NOT NULL,profile_key TEXT NOT NULL,version INTEGER NOT NULL,
 record_json TEXT NOT NULL,record_sha256 TEXT NOT NULL,
 PRIMARY KEY(workspace_id,profile_key,version));
CREATE TABLE IF NOT EXISTS native_channel_profile_states(
 workspace_id TEXT NOT NULL,profile_key TEXT NOT NULL,revision INTEGER NOT NULL,
 version INTEGER NOT NULL,archived INTEGER NOT NULL,binding_sha256 TEXT NOT NULL,
 PRIMARY KEY(workspace_id,profile_key));
CREATE TABLE IF NOT EXISTS native_channel_profile_requests(
 workspace_id TEXT NOT NULL,profile_key TEXT NOT NULL,request_key_sha256 TEXT NOT NULL,
 fingerprint TEXT NOT NULL,result_json TEXT NOT NULL,result_sha256 TEXT NOT NULL,
 PRIMARY KEY(workspace_id,profile_key,request_key_sha256));
'''

class Mutation(StrictModel):
    profile_key:str=Field(pattern=KEY)
    action:Literal['save','archive','restore']
    expected_revision:StrictInt=Field(ge=0)
    expected_binding_sha256:str|None=Field(default=None,pattern=SHA)
    profile:ChannelProfile|None=None
    request_key:str=Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    @model_validator(mode='after')
    def bound(self):
        if (self.action=='save')!=(self.profile is not None):raise ValueError('Save requires a complete profile; lifecycle actions do not')
        if (self.expected_revision==0)!=(self.expected_binding_sha256 is None):raise ValueError('Current revision/hash binding required')
        return self

def binding(workspace,key,revision,version,archived,record_sha):
    return digest({'workspace_id':workspace,'profile_key':key,'revision':revision,'version':version,'archived':archived,'record_sha256':record_sha})

def record(row,workspace,key,con=None):
    try:
        value=json.loads(row['record_json']);profile=ChannelProfile.model_validate(value['profile'])
        if value['workspace_id']!=workspace or value['profile_key']!=key or value['version']!=row['version'] or value['sha256']!=row['record_sha256']:
            raise ValueError()
        if value['sha256']!=digest({k:v for k,v in value.items() if k!='sha256'}) or profile.profile_ref!=key+'@'+str(row['version']):raise ValueError()
        selection=value['selection'];FrozenSelection.model_validate(selection)
        if selection['profile']!=value['profile'] or selection['selection_sha256']!=digest({k:v for k,v in selection.items() if k!='selection_sha256'}):raise ValueError()
        from .channel_profiles import resolve
        resolve({'channel_profile':selection,'niche':profile.niche_profile.niche})
        if value['version']<1 or value['version']>100:raise ValueError()
        if con is not None:
            previous=con.execute('SELECT * FROM native_channel_profile_versions WHERE workspace_id=? AND profile_key=? AND version=?',(workspace,key,value['version']-1)).fetchone()
            if value['version']==1:
                if value['previous_sha256'] is not None:raise ValueError()
            elif previous is None or value['previous_sha256']!=record(previous,workspace,key,con)['sha256']:raise ValueError()
        return value
    except (ValueError,KeyError,TypeError):raise WorkflowError('CHANNEL_PROFILE_VERSION_EVIDENCE_CHANGED') from None

def state_view(con,row,workspace):
    key=row['profile_key'];version=con.execute('SELECT * FROM native_channel_profile_versions WHERE workspace_id=? AND profile_key=? AND version=?',
        (workspace,key,row['version'])).fetchone()
    if version is None:raise WorkflowError('CHANNEL_PROFILE_STATE_EVIDENCE_CHANGED')
    value=record(version,workspace,key,con)
    archived=bool(row['archived'])
    if type(row['revision']) is not int or row['revision']<row['version'] or row['archived'] not in (0,1) or row['binding_sha256']!=binding(workspace,key,row['revision'],row['version'],archived,value['sha256']):
        raise WorkflowError('CHANNEL_PROFILE_STATE_EVIDENCE_CHANGED')
    return {'profile_key':key,'revision':row['revision'],'version':row['version'],'archived':archived,'binding_sha256':row['binding_sha256'],'record':value}

def select_saved(store,workspace,reference,*,con=None):
    match=re.fullmatch(r'([a-z][a-z0-9-]{2,49})@([1-9][0-9]*)',reference)
    if not match:raise WorkflowError('CHANNEL_PROFILE_NOT_FOUND',400)
    def read(connection):
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='native_channel_profile_states'").fetchone():raise WorkflowError('CHANNEL_PROFILE_NOT_FOUND',400)
        row=connection.execute('SELECT * FROM native_channel_profile_states WHERE workspace_id=? AND profile_key=?',(workspace,match[1])).fetchone()
        if row is None:raise WorkflowError('CHANNEL_PROFILE_NOT_FOUND',400)
        current=state_view(connection,row,workspace)
        if current['archived'] or current['version']!=int(match[2]):raise WorkflowError('CHANNEL_PROFILE_VERSION_NOT_CURRENT',409)
        return copy.deepcopy(current['record']['selection'])
    if con is not None:return read(con)
    with store.transaction() as connection:return read(connection)

class NativeChannelRegistry:
    def __init__(self,store,workspace):
        if not isinstance(workspace,str) or not re.fullmatch(r'wsp_[A-Za-z0-9_-]{1,100}',workspace):raise WorkflowError('CHANNEL_PROFILE_WORKSPACE_INVALID',400)
        self.store,self.workspace=store,workspace
        with store.transaction() as con:
            for statement in SQL.split(';'):
                if statement.strip():con.execute(statement)
    def page(self):
        with self.store.transaction() as con:
            rows=con.execute('SELECT * FROM native_channel_profile_states WHERE workspace_id=? ORDER BY profile_key',(self.workspace,)).fetchall()
            if len(rows)>48:raise WorkflowError('CHANNEL_PROFILE_STATE_LIMIT')
            items=[state_view(con,row,self.workspace) for row in rows]
        from .branding import catalog as brands
        from .idea_scoring import configuration
        from app.subtitle_templates import load_templates
        choices={'content_profiles':configuration()['profiles'],'brands':brands()['brands'],'templates':brands()['templates'],
                 'subtitle_templates':load_templates(),'narration_languages_configured':['vi']}
        return {'schema_version':'native-channel-profile-admin-v1','workspace_id':self.workspace,'items':items,'choices':choices,'publishing_enabled':False,'external_dispatches':0}
    def catalog(self):
        base=builtin_catalog();items=[v for v in self.page()['items'] if not v['archived']]
        if not items:return base
        return {**base,'profiles':base['profiles']+[v['record']['profile'] for v in items],
            'selections':base['selections']+[v['record']['selection'] for v in items],
            'sha256':digest({'builtin_sha256':base['sha256'],'workspace_id':self.workspace,'active_bindings':[v['binding_sha256'] for v in items]})}
    def history(self,key,*,before_version=None,limit=20):
        if not isinstance(key,str) or not re.fullmatch(KEY,key) or type(limit) is not int or not 1<=limit<=50 or (before_version is not None and (type(before_version) is not int or before_version<1)):
            raise WorkflowError('CHANNEL_PROFILE_HISTORY_QUERY_INVALID',400)
        with self.store.transaction() as con:
            rows=con.execute('SELECT * FROM native_channel_profile_versions WHERE workspace_id=? AND profile_key=? AND version<? ORDER BY version DESC LIMIT ?',
                (self.workspace,key,before_version or 2147483647,limit+1)).fetchall()
            items=[record(row,self.workspace,key,con) for row in rows[:limit]]
        return {'schema_version':'native-channel-profile-history-v1','workspace_id':self.workspace,'profile_key':key,'items':items,
            'next_before_version':items[-1]['version'] if len(rows)>limit else None}
    def mutate(self,payload,*,actor):
        request=payload.model_dump(mode='json',exclude={'request_key'});fingerprint=digest(request);request_sha=digest(payload.request_key);key=payload.profile_key
        if key in {p['profile_ref'].split('@')[0] for p in builtin_catalog()['profiles']}:raise WorkflowError('CHANNEL_PROFILE_BUILTIN_READ_ONLY',400)
        if not isinstance(actor,str) or not 1<=len(actor)<=200:raise WorkflowError('CHANNEL_PROFILE_ACTOR_REQUIRED',400)
        with self.store.transaction() as con:
            prior=con.execute('SELECT * FROM native_channel_profile_requests WHERE workspace_id=? AND profile_key=? AND request_key_sha256=?',(self.workspace,key,request_sha)).fetchone()
            if prior:
                if prior['fingerprint']!=fingerprint:raise WorkflowError('CHANNEL_PROFILE_IDEMPOTENCY_CONFLICT')
                try:
                    result=json.loads(prior['result_json']);item=result['item']
                    if digest(result)!=prior['result_sha256'] or result['schema_version']!='native-channel-profile-mutation-v1' or result['workspace_id']!=self.workspace or result['action']!=payload.action or result['publishing_enabled'] is not False or result['external_dispatches']!=0 or item['profile_key']!=key or item['revision']!=payload.expected_revision+1 or type(item['archived']) is not bool:raise ValueError()
                    saved=con.execute('SELECT * FROM native_channel_profile_versions WHERE workspace_id=? AND profile_key=? AND version=?',(self.workspace,key,item['version'])).fetchone()
                    if saved is None or item['record']!=record(saved,self.workspace,key,con) or item['binding_sha256']!=binding(self.workspace,key,item['revision'],item['version'],item['archived'],item['record']['sha256']):raise ValueError()
                except (ValueError,KeyError,TypeError):raise WorkflowError('CHANNEL_PROFILE_REQUEST_EVIDENCE_CHANGED') from None
                return {**result,'idempotent_replay':True}
            row=con.execute('SELECT * FROM native_channel_profile_states WHERE workspace_id=? AND profile_key=?',(self.workspace,key)).fetchone()
            current=state_view(con,row,self.workspace) if row else None
            if payload.expected_revision!=(current['revision'] if current else 0) or payload.expected_binding_sha256!=(current['binding_sha256'] if current else None):
                raise WorkflowError('CHANNEL_PROFILE_BINDING_STALE')
            if current is None and (payload.action!='save' or con.execute('SELECT count(*) FROM native_channel_profile_states WHERE workspace_id=?',(self.workspace,)).fetchone()[0]>=48):
                raise WorkflowError('CHANNEL_PROFILE_CREATE_REQUIRED_OR_LIMIT',400)
            revision=(current['revision'] if current else 0)+1;version=current['version'] if current else 0;archived=current['archived'] if current else False
            if payload.action=='save':
                if archived:raise WorkflowError('CHANNEL_PROFILE_RESTORE_REQUIRED',400)
                version+=1
                if version>100:raise WorkflowError('CHANNEL_PROFILE_VERSION_LIMIT',400)
                if payload.profile.profile_ref!=key+'@'+str(version):raise WorkflowError('CHANNEL_PROFILE_REFERENCE_VERSION_INVALID',400)
                profile=payload.profile.model_dump(mode='json')
                try:selection=resolve_profile(payload.profile,customize_content=True)
                except (ValueError,WorkflowError):raise WorkflowError('CHANNEL_PROFILE_DEFINITION_INVALID',400) from None
                selection.update(catalog_ref='workspace-channel-definitions@1',catalog_sha256=digest({'workspace_id':self.workspace,'profile':profile}))
                selection['selection_sha256']=digest(selection)
                value={'schema_version':'native-channel-profile-version-v1','workspace_id':self.workspace,'profile_key':key,'version':version,
                    'profile':profile,'selection':selection,'previous_sha256':current['record']['sha256'] if current else None,'actor_ref':actor,'created_at':now()}
                value['sha256']=digest(value)
                con.execute('INSERT INTO native_channel_profile_versions VALUES(?,?,?,?,?)',(self.workspace,key,version,json.dumps(value,ensure_ascii=False),value['sha256']))
            else:
                if archived==(payload.action=='archive'):raise WorkflowError('CHANNEL_PROFILE_LIFECYCLE_ALREADY_CURRENT',400)
                archived=payload.action=='archive';value=current['record']
            bind=binding(self.workspace,key,revision,version,archived,value['sha256'])
            con.execute('INSERT OR REPLACE INTO native_channel_profile_states VALUES(?,?,?,?,?,?)',(self.workspace,key,revision,version,int(archived),bind))
            result={'schema_version':'native-channel-profile-mutation-v1','workspace_id':self.workspace,'action':payload.action,
                'item':{'profile_key':key,'revision':revision,'version':version,'archived':archived,'binding_sha256':bind,'record':value},'publishing_enabled':False,'external_dispatches':0}
            con.execute('INSERT INTO native_channel_profile_requests VALUES(?,?,?,?,?,?)',(self.workspace,key,request_sha,fingerprint,json.dumps(result,ensure_ascii=False),digest(result)))
            return {**result,'idempotent_replay':False}
