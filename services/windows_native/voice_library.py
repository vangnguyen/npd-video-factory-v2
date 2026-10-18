"""Workspace voice definitions and immutable versions. No inference or cloning here."""
import json,re,uuid
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,StrictStr,ValidationError,model_validator
from app.models import StrictModel
from .backup import guard
from .contracts import WorkflowError,digest
from .store import now

VOICE_ID=r'nvoice_[a-f0-9]{32}'
KEY=r'^[A-Za-z0-9_.:-]{12,128}$'


class VoiceDefinition(StrictModel):
    display_name:StrictStr=Field(min_length=1,max_length=100)
    provider:StrictStr=Field(pattern=r'^[a-z][a-z0-9-]{0,63}$')
    model:StrictStr=Field(min_length=1,max_length=150)
    provider_voice_id:StrictStr=Field(min_length=1,max_length=150)
    locale:StrictStr=Field(pattern=r'^[a-z]{2}(?:-[A-Z]{2})?$')
    source_type:Literal['provider_preset','licensed_reference']='provider_preset'
    rights_status:Literal['unknown','owner_declared','source_licensed','blocked']='unknown'
    license:StrictStr|None=Field(default=None,min_length=1,max_length=1000)
    source_reference:StrictStr|None=Field(default=None,min_length=1,max_length=2000)
    permission_reference:StrictStr|None=Field(default=None,min_length=1,max_length=2000)
    reference_asset_id:StrictStr|None=Field(default=None,pattern=r'^[A-Za-z0-9_-]{1,100}$')
    reference_sha256:StrictStr|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    cloning_consent:StrictBool=False
    @model_validator(mode='after')
    def complete(self):
        for name in ('display_name','model','provider_voice_id','license','source_reference','permission_reference'):
            value=getattr(self,name)
            if value is not None and not value.strip():raise ValueError('nonblank voice metadata required')
        if self.source_type=='provider_preset' and (self.reference_asset_id is not None or self.reference_sha256 is not None or self.cloning_consent):raise ValueError('preset cannot contain cloning material')
        if self.source_type=='licensed_reference' and (not self.reference_asset_id or not self.reference_sha256):raise ValueError('registered reference and hash required')
        if self.rights_status in ('owner_declared','source_licensed') and (not self.license or not self.source_reference or not self.permission_reference):raise ValueError('rights declaration evidence required')
        return self


class VoiceCreate(StrictModel):
    request_key:StrictStr=Field(pattern=KEY)
    definition:VoiceDefinition


class VoiceUpdate(VoiceCreate):
    expected_version:StrictInt=Field(ge=1)


class NativeVoiceLibrary:
    """A voice belongs to the library, never permanently to a character."""
    def __init__(self,store,*,workspace_id='wsp_native_local'):
        self.store,self.workspace=store,workspace_id;self._scope=(store.root.absolute(),workspace_id)
        self.scope()
        with store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_voice_versions (
                workspace_id TEXT NOT NULL,voice_id TEXT NOT NULL,version INTEGER NOT NULL,
                definition_json TEXT NOT NULL,definition_sha256 TEXT NOT NULL,created_at TEXT NOT NULL,
                PRIMARY KEY(workspace_id,voice_id,version));
                CREATE TABLE IF NOT EXISTS native_voice_writes (
                workspace_id TEXT NOT NULL,request_key TEXT NOT NULL,request_sha256 TEXT NOT NULL,
                voice_id TEXT NOT NULL,version INTEGER NOT NULL,actor_ref TEXT NOT NULL,created_at TEXT NOT NULL,
                PRIMARY KEY(workspace_id,request_key));''')

    def scope(self):
        if self._scope!=(self.store.root.absolute(),self.workspace) or not re.fullmatch(r'wsp_[A-Za-z0-9_-]{1,100}',self.workspace):raise WorkflowError('VOICE_WORKSPACE_INVALID')
        guard(self.store.root,exists=True);marker=guard(self.store.root/'.vf-auth-workspace.json')
        try:
            if marker.exists():
                if marker.stat().st_size>4096 or json.loads(marker.read_bytes())!={'schema':'vf-native-workspace-binding-v1','workspace_id':self.workspace}:raise ValueError()
            elif self.workspace!='wsp_native_local':raise ValueError()
        except (OSError,ValueError):raise WorkflowError('VOICE_WORKSPACE_INVALID') from None

    def _id(self,identifier):
        if not isinstance(identifier,str) or not re.fullmatch(VOICE_ID,identifier):raise WorkflowError('VOICE_NOT_FOUND',404)

    def _record(self,con,identifier,version=None):
        self._id(identifier)
        latest=con.execute('SELECT MAX(version) FROM native_voice_versions WHERE workspace_id=? AND voice_id=?',(self.workspace,identifier)).fetchone()[0]
        if latest is None:raise WorkflowError('VOICE_NOT_FOUND',404)
        target=latest if version is None else version
        if type(target) is not int or target<1:raise WorkflowError('VOICE_VERSION_INVALID',400)
        row=con.execute('SELECT * FROM native_voice_versions WHERE workspace_id=? AND voice_id=? AND version=?',(self.workspace,identifier,target)).fetchone()
        if row is None:raise WorkflowError('VOICE_VERSION_NOT_FOUND',404)
        try:
            definition=VoiceDefinition.model_validate_json(row['definition_json']).model_dump(mode='json')
            if digest(definition)!=row['definition_sha256']:raise ValueError()
        except (ValueError,ValidationError):raise WorkflowError('VOICE_LIBRARY_CHANGED') from None
        return {'voice_id':identifier,'version':target,'current_version':latest,'definition':definition,'definition_sha256':row['definition_sha256'],
            'created_at':row['created_at'],'current':target==latest,'rights_independently_verified':False,
            'provider_execution':'NOT_CONFIGURED_BY_LIBRARY','human_voice_uat_complete':False}

    def get(self,identifier,*,version=None,for_generation=False):
        self.scope()
        with self.store.transaction() as con:
            record=self._record(con,identifier,version)
        if for_generation:
            definition=record['definition']
            if not record['current']:raise WorkflowError('VOICE_VERSION_CHANGED')
            if definition['rights_status'] not in ('owner_declared','source_licensed'):raise WorkflowError('VOICE_RIGHTS_CONFIRMATION_REQUIRED')
            if definition['source_type']=='licensed_reference' and not definition['cloning_consent']:raise WorkflowError('VOICE_REFERENCE_CONSENT_REQUIRED')
        return record

    def page(self):
        self.scope()
        with self.store.transaction() as con:
            ids=[r[0] for r in con.execute('SELECT DISTINCT voice_id FROM native_voice_versions WHERE workspace_id=? ORDER BY voice_id',(self.workspace,))]
            records=[self._record(con,identifier) for identifier in ids]
        return {'items':records,'external_provider_calls':0,'inference_dispatched':False}

    def create(self,payload,*,actor_ref,authorization_check=lambda:None):return self._write(None,payload,actor_ref,authorization_check)
    def update(self,identifier,payload,*,actor_ref,authorization_check=lambda:None):
        self._id(identifier);return self._write(identifier,payload,actor_ref,authorization_check)

    def _write(self,identifier,payload,actor_ref,authorized,*,_source_evidence=None):
        self.scope();authorized();self.scope()
        if not isinstance(actor_ref,str) or not 1<=len(actor_ref.strip())<=100:raise WorkflowError('VOICE_ACTOR_REQUIRED',400)
        model=VoiceUpdate if identifier is not None else VoiceCreate
        try:body=model.model_validate(payload).model_dump(mode='json')
        except (ValidationError,TypeError):raise WorkflowError('VOICE_REQUEST_INVALID',400) from None
        fingerprint=digest({'voice_id':identifier,'body':body});definition=body['definition']
        if definition['rights_status']=='source_licensed' and (_source_evidence is None or identifier is not None):raise WorkflowError('VOICE_PRESET_INTERNAL_IMPORT_REQUIRED',403)
        with self.store.transaction() as con:
            old=con.execute('SELECT * FROM native_voice_writes WHERE workspace_id=? AND request_key=?',(self.workspace,body['request_key'])).fetchone()
            if old:
                if old['request_sha256']!=fingerprint:raise WorkflowError('VOICE_REQUEST_KEY_CONFLICT')
                return {**self._record(con,old['voice_id'],old['version']),'idempotent_replay':True}
            if identifier is None:identifier='nvoice_'+uuid.uuid4().hex;version=1
            else:
                current=self._record(con,identifier)
                if current['version']!=body['expected_version']:raise WorkflowError('VOICE_VERSION_CHANGED')
                version=current['version']+1
            stamp=now();authorized()
            con.execute('INSERT INTO native_voice_versions VALUES(?,?,?,?,?,?)',(self.workspace,identifier,version,json.dumps(definition,ensure_ascii=False),digest(definition),stamp))
            con.execute('INSERT INTO native_voice_writes VALUES(?,?,?,?,?,?,?)',(self.workspace,body['request_key'],fingerprint,identifier,version,actor_ref.strip(),stamp))
            return {**self._record(con,identifier,version),'idempotent_replay':False}
