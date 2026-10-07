"""Default-disabled, scoped and expiring human exceptions; never license verification."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib,json,re,uuid
from urllib.parse import urlsplit,parse_qsl
from .backup import guard
from .contracts import WorkflowError,digest,file_sha
from .source_assets import canonical_assets
from .rights_override_models import OverrideCreate,OverrideRecord
from .store import now

VERSION='native-owner-rights-override-v1'


def timestamp(value):
    try:
        result=datetime.fromisoformat(value)
        if result.tzinfo is None or result.utcoffset()!=timedelta(0):raise ValueError()
        return result.astimezone(timezone.utc)
    except (TypeError,ValueError):raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_HISTORY_INVALID') from None


def rights_sha(asset):
    return digest({key:asset.get(key) for key in ('id','sha256','source_type','rights_status','license','provider','source_reference',
        'production_eligible','explicit_fixture','generation_provenance','rights_declaration_ref','rights_declaration_sha256')})


def fixture(asset):
    value=asset.get('generation_provenance')
    return asset.get('explicit_fixture') is True or isinstance(value,dict) and value.get('fixture') is True


def validate_document(document,*,project_id=None,workspace_id=None):
    values=document.get('media_rights_overrides',[])
    if not isinstance(values,list) or len(values)>200:raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_HISTORY_INVALID')
    seen={}
    for value in values:
        try:record=OverrideRecord.model_validate(value)
        except (ValueError,TypeError):raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_HISTORY_INVALID') from None
        if (record.sha256!=digest({k:v for k,v in value.items() if k!='sha256'}) or record.override_id in seen
            or not record.request.acknowledged or record.request.asset_sha256!=record.asset_sha256
            or value.get('rights_independently_verified') is not False or value.get('publishing_authorized') is not False):
            raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_HISTORY_INVALID')
        if (project_id is not None and record.project_id!=project_id or workspace_id is not None and record.workspace_id!=workspace_id):
            raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_SCOPE_INVALID')
        created=timestamp(record.created_at)
        if record.request.action=='grant':
            if (record.request.override_id is not None or record.request.expected_override_sha256 is not None
                or record.expires_at is None or timestamp(record.expires_at)!=created+timedelta(days=record.request.valid_days)):
                raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_HISTORY_INVALID')
        else:
            prior=seen.get(record.request.override_id)
            if (prior is None or prior['request']['action']!='grant' or record.expires_at is not None
                or record.request.expected_override_sha256!=prior['sha256'] or record.asset_id!=prior['asset_id']
                or record.asset_sha256!=prior['asset_sha256'] or record.request.allow_publishing_review or created<timestamp(prior['created_at'])):
                raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_HISTORY_INVALID')
        seen[record.override_id]=value


class NativeRightsOverrides:
    def __init__(self,store,*,workspace_id='wsp_native_local',enabled=False,clock=lambda:datetime.now(timezone.utc)):
        if type(enabled) is not bool:raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_CONFIGURATION_INVALID',400)
        self.store,self.workspace,self.enabled,self.clock=store,workspace_id,enabled,clock
        store.rights_overrides=self
        with store.transaction() as con:
            con.execute('CREATE TABLE IF NOT EXISTS native_rights_override_requests (workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,request_sha256 TEXT NOT NULL,result_json TEXT NOT NULL,result_sha256 TEXT NOT NULL,PRIMARY KEY(workspace_id,project_id,key_sha256))')

    def active(self,document,project_id,asset,*,publishing=False):
        validate_document(document,project_id=project_id,workspace_id=self.workspace)
        if not self.enabled or fixture(asset) or asset.get('rights_status')=='restricted':return None
        records=document.get('media_rights_overrides',[]);revoked={r['request']['override_id'] for r in records if r['request']['action']=='revoke'}
        for row in reversed(records):
            if (row['request']['action']=='grant' and row['asset_id']==asset['id'] and row['asset_sha256']==asset.get('sha256')
                and row['override_id'] not in revoked and row['request']['expected_rights_sha256']==rights_sha(asset)
                and timestamp(row['created_at'])<=self.clock()<timestamp(row['expires_at'])
                and (not publishing or row['request']['allow_publishing_review'])):return deepcopy(row)
        return None

    def page(self,project_id):
        project=self.store.get(project_id);doc=project['document'];validate_document(doc,project_id=project_id,workspace_id=self.workspace)
        return {'schema_version':'native-owner-rights-review-v1','workspace_id':self.workspace,'project_id':project_id,'revision':project['revision'],
            'enabled':self.enabled,'publishing_enabled':False,'rights_independently_verified':False,'external_calls':0,
            'items':[{'asset_id':a['id'],'asset_sha256':a.get('sha256'),'filename':a.get('filename'),'rights_status':a.get('rights_status','unknown'),
                'rights_sha256':rights_sha(a),'fixture':fixture(a),'active_override':self.active(doc,project_id,a),
                'override_count':sum(r['asset_id']==a['id'] for r in doc.get('media_rights_overrides',[]))} for a in canonical_assets(doc)],
            'history':deepcopy(doc.get('media_rights_overrides',[]))}

    def record(self,project_id,asset_id,body,*,actor):
        try:payload=OverrideCreate.model_validate(body)
        except ValueError:raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_REQUEST_INVALID',400) from None
        if not payload.acknowledged or not isinstance(actor,str) or not 1<=len(actor)<=100:raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_ACK_REQUIRED',400)
        # References are retained as human evidence, never fetched or treated as provider output.
        try:reference=urlsplit(payload.evidence_reference)
        except ValueError:raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_REFERENCE_INVALID',400) from None
        if (reference.scheme not in ('http','https','document','library','upload') or reference.username or reference.password
            or any(re.search(r'(token|password|secret|api.?key|signature|credential)',key,re.I) for key,_ in parse_qsl(reference.query))):
            raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_REFERENCE_INVALID',400)
        request=payload.model_dump(mode='json');key=hashlib.sha256(request.pop('request_key').encode()).hexdigest();fp=digest({'asset_id':asset_id,**request})
        with self.store.transaction() as con:
            old=con.execute('SELECT * FROM native_rights_override_requests WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project_id,key)).fetchone()
            if old:
                if old['request_sha256']!=fp:raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_IDEMPOTENCY_CONFLICT',409)
                try:result=json.loads(old['result_json'])
                except (ValueError,TypeError):raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_RECEIPT_INVALID') from None
                try:OverrideRecord.model_validate(result.get('record') if isinstance(result,dict) else None)
                except (ValueError,TypeError):raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_RECEIPT_INVALID') from None
                if (not isinstance(result,dict) or digest(result)!=old['result_sha256'] or result.get('schema_version')!=VERSION
                    or result.get('workspace_id')!=self.workspace or result.get('project_id')!=project_id or result.get('revision')!=payload.revision+1
                    or result.get('record',{}).get('request')!=request or result.get('record',{}).get('asset_id')!=asset_id):
                    raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_RECEIPT_INVALID')
                row=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',(project_id,result['revision'])).fetchone()
                if row is None:raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_RECEIPT_INVALID')
                saved=json.loads(row[0]);validate_document(saved,project_id=project_id,workspace_id=self.workspace)
                if result['record'] not in saved.get('media_rights_overrides',[]):raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_RECEIPT_INVALID')
                return {**result,'idempotent_replay':True}
            project=self.store.editable(con,project_id,payload.revision);doc=deepcopy(project['document']);validate_document(doc,project_id=project_id,workspace_id=self.workspace)
            asset=next((a for a in canonical_assets(doc) if a['id']==asset_id),None)
            if asset is None:raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_ASSET_NOT_FOUND',404)
            if (asset.get('sha256')!=payload.asset_sha256 or rights_sha(asset)!=payload.expected_rights_sha256
                or not re.fullmatch(r'[a-f0-9]{32}\.(jpg|png|mp4|wav)',asset_id)
                or file_sha(guard(self.store.root/'assets'/asset_id,exists=True))!=payload.asset_sha256):
                raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_ASSET_CHANGED',409)
            history=doc.setdefault('media_rights_overrides',[])
            if len(history)>=200:raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_HISTORY_LIMIT',409)
            if payload.action=='grant':
                if not self.enabled:raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_DISABLED',403)
                if fixture(asset) or asset.get('rights_status')=='restricted':raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_INELIGIBLE',400)
                if payload.override_id is not None or payload.expected_override_sha256 is not None:raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_REQUEST_INVALID',400)
                created=self.clock().astimezone(timezone.utc);expires=(created+timedelta(days=payload.valid_days)).isoformat()
            else:
                previous=next((r for r in history if r['override_id']==payload.override_id),None)
                if (previous is None or previous['request']['action']!='grant' or previous['asset_id']!=asset_id
                    or previous['sha256']!=payload.expected_override_sha256 or payload.allow_publishing_review
                    or any(r['request']['action']=='revoke' and r['request']['override_id']==payload.override_id for r in history)):
                    raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_REVOCATION_INVALID',400)
                created=self.clock().astimezone(timezone.utc);expires=None
            record={'schema_version':VERSION,'override_id':'nro_'+uuid.uuid4().hex,'workspace_id':self.workspace,'project_id':project_id,
                'asset_id':asset_id,'asset_sha256':payload.asset_sha256,'request':request,'actor_ref':actor,'created_at':created.isoformat(),
                'expires_at':expires,'rights_independently_verified':False,'publishing_authorized':False}
            record['sha256']=digest(record);history.append(record);validate_document(doc)
            con.execute('UPDATE projects SET revision=revision+1,document=?,approval=NULL,updated_at=? WHERE id=?',(json.dumps(doc,ensure_ascii=False),now(),project_id))
            self.store.version(con,project_id)
            self.store.event(con,project_id,'media_rights_override_review_required',{'revision':payload.revision+1,'asset_id':asset_id,
                'override_id':record['override_id'],'action':payload.action,'record_sha256':record['sha256'],'publishing_authorized':False})
            result={'schema_version':VERSION,'workspace_id':self.workspace,'project_id':project_id,'revision':payload.revision+1,
                'record':record,'approval_invalidated':True,'media_bytes_changed':False,'external_calls':0,'idempotent_replay':False}
            con.execute('INSERT INTO native_rights_override_requests VALUES(?,?,?,?,?,?)',(self.workspace,project_id,key,fp,json.dumps(result,ensure_ascii=False),digest(result)))
            return result


def validate_publication_rights(store,document,project_id,assets,used,base):
    """Apply only verified local exception records to the rights gate; other gates stay independent."""
    service=getattr(store,'rights_overrides',None)
    if service is None:return base
    available={a['id']:a for a in assets}
    changed=False
    for check in base.checks:
        asset=available.get(check.evidence.get('asset_id'))
        if check.passed or asset is None or asset['id'] not in used:continue
        record=service.active(document,project_id,asset,publishing=True)
        if record:
            changed=True
            check.passed=True;check.code='RIGHTS_EXPLICIT_OWNER_EXCEPTION'
            check.message='Scoped Owner exception recorded; rights are not independently verified and publishing still requires approval.'
            check.evidence.update(owner_override_id=record['override_id'],owner_override_sha256=record['sha256'],expires_at=record['expires_at'],rights_independently_verified=False)
    if changed:
        base.status='passed' if base.checks and all(c.passed for c in base.checks) else 'failed'
        base.policy_version='native-owner-rights-exception-v1'
    return base
