"""Exact narration/model provenance with default-disabled human exceptions.

The provider's retained license labels are evidence, not a legal determination.
These decisions only admit publishing review, never a post or speech acceptance.
"""
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib,json,re,uuid
from urllib.parse import urlsplit,parse_qsl
from .backup import guard
from .contracts import WorkflowError,digest,file_sha,PROFILE_SHA
from .hardening import Artifacts
from .narration import load_reference,identity,SCHEMA
from .narration_rights_models import ReviewCreate,ReviewRecord,VERSION
from .rights_override import timestamp
from .store import now

KEY='narration_rights_exceptions'
PROVENANCE='native-narration-publication-provenance-v1'

def validate_document(document,*,project_id=None,workspace_id=None):
    rows=document.get(KEY,[])
    if not isinstance(rows,list) or len(rows)>200:raise WorkflowError('NATIVE_NARRATION_RIGHTS_HISTORY_INVALID')
    seen={}
    for value in rows:
        try:r=ReviewRecord.model_validate(value)
        except (ValueError,TypeError):raise WorkflowError('NATIVE_NARRATION_RIGHTS_HISTORY_INVALID') from None
        p=r.provenance
        if (r.sha256!=digest({k:v for k,v in value.items() if k!='sha256'}) or r.exception_id in seen
            or r.provenance_sha256!=digest(p) or r.request.expected_provenance_sha256!=r.provenance_sha256
            or p.get('schema_version')!=PROVENANCE or p.get('project_id')!=r.project_id or p.get('workspace_id')!=r.workspace_id
            or p.get('narration_job_id')!=r.narration_job_id or r.request.narration_job_id!=r.narration_job_id
            or not r.request.acknowledged or any(value.get(k) is not False for k in ('rights_independently_verified','speech_quality_accepted','publishing_authorized'))):
            raise WorkflowError('NATIVE_NARRATION_RIGHTS_HISTORY_INVALID')
        if project_id is not None and r.project_id!=project_id or workspace_id is not None and r.workspace_id!=workspace_id:raise WorkflowError('NATIVE_NARRATION_RIGHTS_SCOPE_INVALID')
        created=timestamp(r.created_at)
        if r.request.action=='grant':
            if r.request.exception_id is not None or r.request.expected_exception_sha256 is not None or r.expires_at is None or timestamp(r.expires_at)!=created+timedelta(days=r.request.valid_days):raise WorkflowError('NATIVE_NARRATION_RIGHTS_HISTORY_INVALID')
        else:
            prior=seen.get(r.request.exception_id)
            if (prior is None or prior['request']['action']!='grant' or r.expires_at is not None or r.request.allow_publishing_review
                or prior['sha256']!=r.request.expected_exception_sha256 or prior['provenance']!=p or created<timestamp(prior['created_at'])):raise WorkflowError('NATIVE_NARRATION_RIGHTS_HISTORY_INVALID')
        seen[r.exception_id]=value

class NativeNarrationRights:
    def __init__(self,store,*,workspace_id='wsp_native_local',enabled=False,clock=lambda:datetime.now(timezone.utc)):
        if type(enabled) is not bool:raise WorkflowError('NATIVE_NARRATION_RIGHTS_CONFIGURATION_INVALID',400)
        self.store,self.workspace,self.enabled,self.clock=store,workspace_id,enabled,clock
        store.narration_rights=self
        with store.transaction() as con:
            con.execute('CREATE TABLE IF NOT EXISTS native_narration_rights_requests (workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,request_sha256 TEXT NOT NULL,result_json TEXT NOT NULL,result_sha256 TEXT NOT NULL,PRIMARY KEY(workspace_id,project_id,key_sha256))')

    def provenance(self,document,project_id,con):
        from .pipeline import profile,LOCKS
        ref=document.get('prepared_narration')
        if not isinstance(ref,dict) or ref.get('schema_version')!=SCHEMA:raise WorkflowError('NATIVE_NARRATION_RIGHTS_PREPARATION_REQUIRED',409)
        job,out,result=load_reference(self.store,con,project_id,document);plan=result['plan']
        if (ref.get('plan_sha256')!=result['plan_sha256'] or ref.get('voice_input_sha256')!=identity(document)
            or ref['voice_input_sha256']!=plan['voice_input_sha256'] or ref.get('voice_audio_sha256')!=plan['voice_audio_sha256']):raise WorkflowError('NATIVE_NARRATION_RIGHTS_INPUT_CHANGED',409)
        meta=json.loads((out/'voice.json').read_bytes());tts=json.loads((out/'tts-plan.json').read_bytes());locked=profile()
        manifest=json.loads((LOCKS/'tts-artifacts.json').read_bytes())
        if (meta.get('profile_sha256')!=PROFILE_SHA or meta.get('audio_sha256')!=plan['voice_audio_sha256']
            or file_sha(out/'voice.json')!=plan['voice_metadata_sha256'] or file_sha(out/'tts-plan.json')!=plan['tts_plan_sha256']
            or manifest.get('profile_sha256')!=PROFILE_SHA):raise WorkflowError('NATIVE_NARRATION_RIGHTS_PROVENANCE_CHANGED')
        # No private local artifact paths or narration text are exposed in this projection.
        value={'schema_version':PROVENANCE,'workspace_id':self.workspace,'project_id':project_id,'narration_job_id':job['id'],
            'source_revision':job['revision'],'source_snapshot_sha256':digest(job['snapshot']),'plan_sha256':result['plan_sha256'],
            'voice_input_sha256':plan['voice_input_sha256'],'voice_audio_sha256':plan['voice_audio_sha256'],
            'voice_metadata_sha256':plan['voice_metadata_sha256'],'tts_plan_sha256':plan['tts_plan_sha256'],'profile_sha256':PROFILE_SHA,
            'model_manifest_sha256':file_sha(LOCKS/'tts-artifacts.json'),
            'profile':{k:deepcopy(locked[k]) for k in ('provider_key','model','model_revision','voice_id','locale','sdk_commit','sdk_version','rights')},
            'model_artifacts':[{k:a[k] for k in ('repository','revision','file','sha256','bytes')} for a in manifest['files']],
            'voice_duration_seconds':plan['source_duration_seconds'],
            'explicit_fixture':tts.get('explicit_synthetic_pcm_fixture') is True or meta.get('explicit_synthetic_pcm_fixture') is True,
            'rights_status':'unknown','rights_independently_verified':False,'speech_quality_accepted':False,'publishing_authorized':False}
        if 'derivation' in ref:value.update({'source_project_id':job['project_id'],'derivation_sha256':digest(ref['derivation']),
            'approval_inherited':False,'rights_authority_inherited':False})
        return value

    def active(self,document,project_id,provenance,*,publishing=False):
        validate_document(document,project_id=project_id,workspace_id=self.workspace)
        if not self.enabled or provenance['explicit_fixture']:return None
        rows=document.get(KEY,[]);revoked={r['request']['exception_id'] for r in rows if r['request']['action']=='revoke'}
        for r in reversed(rows):
            if (r['request']['action']=='grant' and r['exception_id'] not in revoked and r['provenance']==provenance
                and timestamp(r['created_at'])<=self.clock()<timestamp(r['expires_at'])
                and (not publishing or r['request']['allow_publishing_review'])):return deepcopy(r)
        return None

    def page(self,project_id):
        with self.store.transaction() as con:
            p=self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone());doc=p['document']
            validate_document(doc,project_id=project_id,workspace_id=self.workspace)
            provenance=None;failure=None
            if doc.get('prepared_narration') is not None:
                try:provenance=self.provenance(doc,project_id,con)
                except WorkflowError as e:failure=e.code
            return {'schema_version':'native-narration-rights-review-v1','workspace_id':self.workspace,'project_id':project_id,'revision':p['revision'],
                'enabled':self.enabled,'provenance':provenance,'provenance_sha256':digest(provenance) if provenance else None,'attention':failure,
                'active_exception':self.active(doc,project_id,provenance) if provenance else None,'history':deepcopy(doc.get(KEY,[])),
                'publishing_enabled':False,'rights_independently_verified':False,'speech_quality_accepted':False,'external_calls':0}

    def record(self,project_id,body,*,actor):
        try:payload=ReviewCreate.model_validate(body)
        except ValueError:raise WorkflowError('NATIVE_NARRATION_RIGHTS_REQUEST_INVALID',400) from None
        if not payload.acknowledged or not isinstance(actor,str) or not 1<=len(actor)<=100:raise WorkflowError('NATIVE_NARRATION_RIGHTS_ACK_REQUIRED',400)
        try:ref=urlsplit(payload.evidence_reference)
        except ValueError:raise WorkflowError('NATIVE_NARRATION_RIGHTS_REFERENCE_INVALID',400) from None
        if (ref.scheme not in ('http','https','document','library','upload') or ref.username or ref.password
            or any(re.search(r'(token|password|secret|api.?key|signature|credential)',k,re.I) for k,_ in parse_qsl(ref.query))):raise WorkflowError('NATIVE_NARRATION_RIGHTS_REFERENCE_INVALID',400)
        request=payload.model_dump(mode='json');key=hashlib.sha256(request.pop('request_key').encode()).hexdigest();fp=digest(request)
        with self.store.transaction() as con:
            old=con.execute('SELECT * FROM native_narration_rights_requests WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project_id,key)).fetchone()
            if old:
                if old['request_sha256']!=fp:raise WorkflowError('NATIVE_NARRATION_RIGHTS_IDEMPOTENCY_CONFLICT',409)
                try:result=json.loads(old['result_json'])
                except (ValueError,TypeError):raise WorkflowError('NATIVE_NARRATION_RIGHTS_RECEIPT_INVALID') from None
                if not isinstance(result,dict):raise WorkflowError('NATIVE_NARRATION_RIGHTS_RECEIPT_INVALID')
                saved=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',(project_id,result.get('revision'))).fetchone()
                if (digest(result)!=old['result_sha256'] or result.get('schema_version')!=VERSION or result.get('workspace_id')!=self.workspace
                    or result.get('project_id')!=project_id or result.get('revision')!=payload.revision+1 or result.get('record',{}).get('request')!=request
                    or saved is None):raise WorkflowError('NATIVE_NARRATION_RIGHTS_RECEIPT_INVALID')
                doc=json.loads(saved[0]);validate_document(doc,project_id=project_id,workspace_id=self.workspace)
                if result['record'] not in doc.get(KEY,[]):raise WorkflowError('NATIVE_NARRATION_RIGHTS_RECEIPT_INVALID')
                return {**result,'idempotent_replay':True}
            p=self.store.editable(con,project_id,payload.revision);doc=deepcopy(p['document']);validate_document(doc,project_id=project_id,workspace_id=self.workspace)
            rows=doc.setdefault(KEY,[])
            if len(rows)>=200:raise WorkflowError('NATIVE_NARRATION_RIGHTS_HISTORY_LIMIT',409)
            created=self.clock().astimezone(timezone.utc)
            if payload.action=='grant':
                if not self.enabled:raise WorkflowError('NATIVE_NARRATION_RIGHTS_DISABLED',403)
                provenance=self.provenance(doc,project_id,con)
                if provenance['explicit_fixture']:raise WorkflowError('NATIVE_NARRATION_RIGHTS_FIXTURE_INELIGIBLE',400)
                if payload.exception_id is not None or payload.expected_exception_sha256 is not None:raise WorkflowError('NATIVE_NARRATION_RIGHTS_REQUEST_INVALID',400)
                expires=(created+timedelta(days=payload.valid_days)).isoformat()
            else:
                prior=next((r for r in rows if r['exception_id']==payload.exception_id),None)
                if (prior is None or prior['request']['action']!='grant' or prior['sha256']!=payload.expected_exception_sha256 or payload.allow_publishing_review
                    or any(r['request']['action']=='revoke' and r['request']['exception_id']==payload.exception_id for r in rows)):raise WorkflowError('NATIVE_NARRATION_RIGHTS_REVOCATION_INVALID',400)
                provenance=deepcopy(prior['provenance']);expires=None
            if provenance['narration_job_id']!=payload.narration_job_id or digest(provenance)!=payload.expected_provenance_sha256:raise WorkflowError('NATIVE_NARRATION_RIGHTS_PROVENANCE_CHANGED',409)
            record={'schema_version':VERSION,'exception_id':'nvr_'+uuid.uuid4().hex,'workspace_id':self.workspace,'project_id':project_id,
                'narration_job_id':payload.narration_job_id,'provenance':provenance,'provenance_sha256':digest(provenance),'request':request,
                'actor_ref':actor,'created_at':created.isoformat(),'expires_at':expires,'rights_independently_verified':False,'speech_quality_accepted':False,'publishing_authorized':False}
            record['sha256']=digest(record);rows.append(record);validate_document(doc)
            con.execute('UPDATE projects SET revision=revision+1,document=?,approval=NULL,updated_at=? WHERE id=?',(json.dumps(doc,ensure_ascii=False),now(),project_id));self.store.version(con,project_id)
            self.store.event(con,project_id,'narration_rights_exception_review_required',{'exception_id':record['exception_id'],'action':payload.action,
                'record_sha256':record['sha256'],'provenance_sha256':record['provenance_sha256'],'revision':payload.revision+1,'publishing_authorized':False})
            result={'schema_version':VERSION,'workspace_id':self.workspace,'project_id':project_id,'revision':payload.revision+1,'record':record,
                'approval_invalidated':True,'media_bytes_changed':False,'external_calls':0,'idempotent_replay':False}
            con.execute('INSERT INTO native_narration_rights_requests VALUES(?,?,?,?,?,?)',(self.workspace,project_id,key,fp,json.dumps(result,ensure_ascii=False),digest(result)))
            return result

    def publication(self,job,con=None):
        if job['snapshot']['document'].get('prepared_narration') is None:return None
        with self.store.transaction() if con is None else nullcontext(con) as connection:
            doc=job['snapshot']['document'];pid=job['project_id'];provenance=self.provenance(doc,pid,connection)
            current=self.store.project(connection.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone())
            record=self.active(doc,pid,provenance,publishing=True);live=self.active(current['document'],pid,provenance,publishing=True)
            if not record or not live or live['sha256']!=record['sha256']:return None
            out=guard(self.store.root/'jobs'/job['id'],exists=True);artifacts=Artifacts(out,job)
            if not artifacts.load('tts') or not artifacts.load('render'):raise WorkflowError('NATIVE_NARRATION_RIGHTS_RENDER_CHECKPOINT_REQUIRED')
            reuse=json.loads((out/'voice-reuse.json').read_bytes());render=json.loads((out/'render-voice.json').read_bytes())
            if (file_sha(out/'voice.wav')!=provenance['voice_audio_sha256'] or file_sha(out/'voice.json')!=provenance['voice_metadata_sha256']
                or file_sha(out/'tts-plan.json')!=provenance['tts_plan_sha256'] or reuse.get('schema_version')!='native-prepared-narration-reuse-v1'
                or reuse.get('source_job_id')!=provenance['narration_job_id'] or reuse.get('source_snapshot_sha256')!=provenance['source_snapshot_sha256']
                or reuse.get('source_plan_sha256')!=provenance['plan_sha256'] or reuse.get('source_voice_sha256')!=provenance['voice_audio_sha256']
                or reuse.get('voice_input_sha256')!=provenance['voice_input_sha256'] or reuse.get('new_inference_calls')!=0 or reuse.get('sample_preserving') is not True
                or render.get('source_voice_sha256')!=provenance['voice_audio_sha256'] or render.get('profile_sha256')!=PROFILE_SHA
                or render.get('audio_sha256')!=file_sha(out/'render-voice.wav')):raise WorkflowError('NATIVE_NARRATION_RIGHTS_RENDER_BINDING_CHANGED')
            return {'status':'explicit_owner_exception','policy_version':VERSION,'exception_id':record['exception_id'],'exception_sha256':record['sha256'],
                'provenance_sha256':record['provenance_sha256'],'expires_at':record['expires_at'],'narration_job_id':provenance['narration_job_id'],
                'voice_audio_sha256':provenance['voice_audio_sha256'],'render_voice_sha256':render['audio_sha256'],
                'rights_independently_verified':False,'speech_quality_accepted':False,'publishing_authorized':False}
