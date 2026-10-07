"""Native asset rights declarations with immutable history and no legal override."""
from copy import deepcopy
import hashlib
import json
import re
import uuid
from urllib.parse import parse_qsl,urlsplit
from .contracts import WorkflowError,digest,file_sha
from .backup import guard
from .source_assets import canonical_assets
from .store import now
from .rights_models import RightsDeclaration,RightsRecord

VERSION='native-rights-declaration-v1'


def validate_document(document,*,project_id=None,workspace_id=None):
    values=document.get('media_rights_declarations',[])
    if not isinstance(values,list) or len(values)>200:raise WorkflowError('NATIVE_RIGHTS_HISTORY_INVALID')
    seen=set()
    for value in values:
        try:record=RightsRecord.model_validate(value)
        except (ValueError,TypeError):raise WorkflowError('NATIVE_RIGHTS_HISTORY_INVALID') from None
        body={key:item for key,item in value.items() if key!='sha256'}
        if (value.get('schema_version')!=VERSION or value.get('sha256')!=digest(body)
            or not isinstance(value.get('declaration_id'),str) or not re.fullmatch(r'nrd_[a-f0-9]{32}',value['declaration_id'])
            or value.get('verified') is not False or value.get('owner_override_recorded') is not False
            or value.get('effective_rights_status') not in ('unknown','restricted')):
            raise WorkflowError('NATIVE_RIGHTS_HISTORY_INVALID')
        if (not record.request.acknowledged or record.declaration_id in seen
            or value['request'].get('asset_sha256')!=value.get('asset_sha256')
            or value['effective_rights_status']!=('restricted' if value['request']['claimed_rights']=='restricted' else 'unknown')):
            raise WorkflowError('NATIVE_RIGHTS_HISTORY_INVALID')
        if ((project_id is not None and record.project_id!=project_id)
            or (workspace_id is not None and record.workspace_id!=workspace_id)):
            raise WorkflowError('NATIVE_RIGHTS_SCOPE_INVALID')
        seen.add(record.declaration_id)
    assets=[*document.get('assets',[]),*document.get('source_music_assets',[]),document.get('asset'),document.get('music')]
    for asset in assets:
        if not isinstance(asset,dict):continue
        record=next((row for row in reversed(values) if row['asset_id']==asset.get('id')),None)
        reference=asset.get('rights_declaration_ref')
        if reference is None:
            if record is not None or asset.get('rights_declaration_sha256') is not None:raise WorkflowError('NATIVE_RIGHTS_ASSET_BINDING_INVALID')
            continue
        if (record is None or reference!=record['declaration_id'] or asset.get('rights_declaration_sha256')!=record['sha256']
            or asset.get('sha256')!=record['asset_sha256'] or asset.get('rights_status')!=record['effective_rights_status']):
            raise WorkflowError('NATIVE_RIGHTS_ASSET_BINDING_INVALID')


def clear_project_claims(document):
    """A derived project preserves physical restrictions, never another project's receipt."""
    reviewed={row['asset_id'] for key in ('media_rights_declarations','media_rights_overrides') for row in document.get(key,[])}
    document.pop('media_rights_declarations',None)
    document.pop('media_rights_overrides',None)
    values=[*document.get('assets',[]),*document.get('source_music_assets',[]),document.get('asset'),document.get('music')]
    for asset in values:
        if isinstance(asset,dict):
            if asset.get('id') in reviewed:asset['rights_review_required']=True
            asset.pop('rights_declaration_ref',None);asset.pop('rights_declaration_sha256',None)
    return document


class NativeRights:
    def __init__(self,store,*,workspace_id='wsp_native_local'):
        self.store,self.workspace=store,workspace_id
        with store.transaction() as con:
            con.execute('CREATE TABLE IF NOT EXISTS native_rights_requests (workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,request_sha256 TEXT NOT NULL,result_json TEXT NOT NULL,result_sha256 TEXT NOT NULL,PRIMARY KEY(workspace_id,project_id,key_sha256))')

    def page(self,project_id):
        project=self.store.get(project_id);document=project['document'];validate_document(document,project_id=project_id,workspace_id=self.workspace)
        declarations=document.get('media_rights_declarations',[])
        rows=[]
        for asset in canonical_assets(document):
            selected=next((row for row in reversed(declarations) if row['asset_id']==asset['id']),None)
            rows.append({'asset_id':asset['id'],'asset_sha256':asset.get('sha256'),'filename':asset.get('filename'),
                'kind':asset.get('kind'),'source_type':asset.get('source_type'),
                'rights_status':asset.get('rights_status','unknown'),'license':asset.get('license'),
                'provider':asset.get('provider'),'source_reference':asset.get('source_reference'),
                'generation_provenance':deepcopy(asset.get('generation_provenance',{})),
                'declaration':deepcopy(selected),'human_assertion_is_provider_verification':False})
        return {'schema_version':'native-rights-review-v1','workspace_id':self.workspace,'project_id':project_id,'revision':project['revision'],
            'items':rows,'declaration_count':len(declarations),'unknown_rights_block_publishing':True,'owner_override_enabled':False,'external_calls':0}

    def declare(self,project_id,asset_id,body,*,actor):
        try:payload=RightsDeclaration.model_validate(body)
        except ValueError:raise WorkflowError('NATIVE_RIGHTS_DECLARATION_INVALID',400) from None
        if not payload.acknowledged or not isinstance(actor,str) or not 1<=len(actor)<=100:raise WorkflowError('NATIVE_RIGHTS_DECLARATION_ACK_REQUIRED',400)
        if payload.claimed_rights=='licensed' and not (payload.license and payload.provider and payload.source_reference):
            raise WorkflowError('NATIVE_RIGHTS_LICENSE_REFERENCE_REQUIRED',400)
        reference=payload.source_reference
        if reference:
            try:parsed=urlsplit(reference)
            except ValueError:raise WorkflowError('NATIVE_RIGHTS_PUBLIC_REFERENCE_REQUIRED',400) from None
            if (parsed.scheme and parsed.scheme not in ('http','https','upload','library','provider','document') or parsed.username or parsed.password
                or any(re.search(r'(token|password|secret|api.?key|signature|credential)',key,re.I) for key,_ in parse_qsl(parsed.query))):
                raise WorkflowError('NATIVE_RIGHTS_PUBLIC_REFERENCE_REQUIRED',400)
        value=payload.model_dump(mode='json');key=hashlib.sha256(value.pop('request_key').encode()).hexdigest();fingerprint=digest({'asset_id':asset_id,**value})
        with self.store.transaction() as con:
            old=con.execute('SELECT * FROM native_rights_requests WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project_id,key)).fetchone()
            if old:
                if old['request_sha256']!=fingerprint:raise WorkflowError('NATIVE_RIGHTS_IDEMPOTENCY_CONFLICT',409)
                result=json.loads(old['result_json'])
                if (digest(result)!=old['result_sha256'] or result.get('workspace_id')!=self.workspace or result.get('project_id')!=project_id
                    or result.get('revision')!=payload.revision+1 or result.get('schema_version')!=VERSION
                    or result.get('declaration',{}).get('request')!=value or result.get('declaration',{}).get('asset_id')!=asset_id):
                    raise WorkflowError('NATIVE_RIGHTS_RECEIPT_INVALID')
                frozen=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',(project_id,result['revision'])).fetchone()
                if frozen is None:raise WorkflowError('NATIVE_RIGHTS_RECEIPT_INVALID')
                saved=json.loads(frozen[0]);validate_document(saved,project_id=project_id,workspace_id=self.workspace)
                if result['declaration'] not in saved.get('media_rights_declarations',[]):raise WorkflowError('NATIVE_RIGHTS_RECEIPT_INVALID')
                return {**result,'idempotent_replay':True}
            project=self.store.editable(con,project_id,payload.revision);document=deepcopy(project['document']);validate_document(document,project_id=project_id,workspace_id=self.workspace)
            asset=next((item for item in canonical_assets(document) if item['id']==asset_id),None)
            if asset is None:raise WorkflowError('NATIVE_RIGHTS_ASSET_NOT_FOUND',404)
            if asset.get('sha256')!=payload.asset_sha256 or not re.fullmatch(r'[a-f0-9]{32}\.(jpg|png|mp4|wav)',asset_id):
                raise WorkflowError('NATIVE_RIGHTS_ASSET_CHANGED',409)
            path=guard(self.store.root/'assets'/asset_id,exists=True)
            if file_sha(path)!=payload.asset_sha256:raise WorkflowError('NATIVE_RIGHTS_ASSET_CHANGED',409)
            history=document.setdefault('media_rights_declarations',[])
            if len(history)>=200:raise WorkflowError('NATIVE_RIGHTS_HISTORY_LIMIT',409)
            status='restricted' if payload.claimed_rights=='restricted' else 'unknown'
            record={'schema_version':VERSION,'declaration_id':'nrd_'+uuid.uuid4().hex,'workspace_id':self.workspace,
                'project_id':project_id,'asset_id':asset_id,'asset_sha256':payload.asset_sha256,'request':value,
                'actor_ref':actor,'created_at':now(),'verified':False,'owner_override_recorded':False,'effective_rights_status':status}
            record['sha256']=digest(record);history.append(record)
            # Keep actual provider/source/generation metadata separate from a
            # human claim. Manual declarations never become provider results.
            def update(item):
                if isinstance(item,dict) and item.get('id')==asset_id:
                    if item.get('sha256')!=payload.asset_sha256:raise WorkflowError('NATIVE_RIGHTS_ASSET_CHANGED',409)
                    item.update(rights_status=status,rights_declaration_ref=record['declaration_id'],rights_declaration_sha256=record['sha256'])
            for item in document.get('assets',[]):update(item)
            for item in document.get('source_music_assets',[]):update(item)
            update(document.get('asset'));update(document.get('music'))
            validate_document(document)
            con.execute('UPDATE projects SET revision=revision+1,document=?,approval=NULL,updated_at=? WHERE id=?',(json.dumps(document,ensure_ascii=False),now(),project_id))
            self.store.version(con,project_id)
            self.store.event(con,project_id,'media_rights_declared_review_required',{'revision':payload.revision+1,'asset_id':asset_id,
                'declaration_id':record['declaration_id'],'declaration_sha256':record['sha256'],'verified':False,'owner_override_recorded':False})
            result={'schema_version':VERSION,'workspace_id':self.workspace,'project_id':project_id,'revision':payload.revision+1,
                'declaration':record,'approval_invalidated':True,'media_bytes_changed':False,'external_calls':0,'idempotent_replay':False}
            con.execute('INSERT INTO native_rights_requests VALUES(?,?,?,?,?,?)',(self.workspace,project_id,key,fingerprint,json.dumps(result,ensure_ascii=False),digest(result)))
            return result
