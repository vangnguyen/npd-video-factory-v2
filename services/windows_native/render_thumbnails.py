"""Human-selected original rendered PNGs, separate from edit and publish authority.

References reuse the original checkpoint PNG: no copied video/image, new render,
provider request, project revision or final-video approval is created here.
"""
import base64,copy,hashlib,json,re,sqlite3,uuid
from datetime import datetime
from pathlib import Path
from typing import Literal
from pydantic import Field,StrictBool,field_validator
from app.models import StrictModel
from .contracts import WorkflowError,digest
from .render_frame_qc import validate as validate_frames,checked
from .render_vision import NativeRenderVision
from .render_vision_frame_bridge import NativeRenderEvidenceFrameExtractor
from .store import Store,now

SCHEMA='native-render-thumbnail-selection-v1'
PATTERN=r'ast_rthumb_[a-f0-9]{32}'
FALSE_FLAGS=('canonical_timeline_mutated','project_revision_changed','final_video_approved','provider_authorized',
    'source_asset_consent_reused','publishing_authorized','rights_independently_verified','owner_uat_accepted','real_provider_tested')

class VisionReview(StrictModel):
    vision_id:str=Field(pattern=r'^nrvi_[a-f0-9]{32}$')
    expected_snapshot_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    expected_result_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    acknowledged_protocol_mock:StrictBool=False

class Create(StrictModel):
    revision:int=Field(strict=True,ge=1)
    render_job_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    expected_render_input_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    frame_id:str=Field(pattern=r'^rqf_[a-f0-9]{24}$')
    expected_frame_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    acknowledged_thumbnail:Literal[True]
    reviewed_vision:VisionReview|None=None
    request_key:str=Field(min_length=16,max_length=200,pattern=r'^[A-Za-z0-9_-]+$')

    @field_validator('acknowledged_thumbnail',mode='before')
    @classmethod
    def raw_ack(cls,value):
        if value is not True:raise ValueError('Explicit rendered thumbnail review required')
        return value

class NativeRenderThumbnails:
    def __init__(self,store,config,*,workspace_id='wsp_native_local',render_vision=None):
        if type(store) is not Store or config.data_root.absolute()!=store.root.absolute() or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',workspace_id):
            raise WorkflowError('NATIVE_RENDER_THUMBNAIL_SCOPE_INVALID',400)
        if render_vision is not None and (type(render_vision) is not NativeRenderVision or render_vision.store is not store
            or render_vision.config is not config or render_vision.workspace!=workspace_id):raise WorkflowError('NATIVE_RENDER_THUMBNAIL_SCOPE_INVALID',400)
        self.store,self.config,self.workspace,self.vision=store,config,workspace_id,render_vision
        self._binding=(store,config,store.root.absolute(),workspace_id,render_vision)
        with store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_render_thumbnails (
                thumbnail_asset_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                key_sha256 TEXT NOT NULL,request_sha256 TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,
                created_at TEXT NOT NULL,UNIQUE(workspace_id,project_id,key_sha256));
                CREATE INDEX IF NOT EXISTS native_render_thumbnail_history ON native_render_thumbnails(workspace_id,project_id,created_at,thumbnail_asset_id);''')
            if con.execute('SELECT 1 FROM native_render_thumbnails WHERE workspace_id!=? LIMIT 1',(workspace_id,)).fetchone():
                raise WorkflowError('NATIVE_RENDER_THUMBNAIL_SCOPE_INVALID')

    def check(self):
        if self._binding!=(self.store,self.config,self.store.root.absolute(),self.workspace,self.vision) or self.config.data_root.absolute()!=self.store.root.absolute():
            raise WorkflowError('NATIVE_RENDER_THUMBNAIL_SCOPE_INVALID')
        from .backup import guard
        try:
            marker=guard(self.store.root/'.vf-auth-workspace.json')
            if marker.exists():
                if marker.stat().st_size>512 or json.loads(marker.read_bytes())!={'schema':'vf-native-workspace-binding-v1','workspace_id':self.workspace}:raise ValueError()
            elif self.workspace!='wsp_native_local':raise ValueError()
        except Exception:raise WorkflowError('NATIVE_RENDER_THUMBNAIL_SCOPE_INVALID') from None

    def bridge(self,project,job,con):
        return NativeRenderEvidenceFrameExtractor(self.store,self.config,project,job,workspace_id=self.workspace,con=con)

    def connection(self,con):
        self.check()
        if type(con) is not sqlite3.Connection or not con.in_transaction or Path(con.execute('PRAGMA database_list').fetchone()[2]).absolute()!=self.store.db.absolute():
            raise WorkflowError('NATIVE_RENDER_THUMBNAIL_SCOPE_INVALID')

    def reviewed(self,con,project,request,binding):
        if request is None:return None
        if self.vision is None:raise WorkflowError('NATIVE_RENDER_THUMBNAIL_ORIGINAL_VISION_REQUIRED')
        self.vision.check();row=self.vision.read(con,self.vision.row(con,project,request.vision_id));result=row['result']
        if (row['status']!='succeeded' or result is None or row['snapshot_sha256']!=request.expected_snapshot_sha256
            or row['result_sha256']!=request.expected_result_sha256 or result['render_job_id']!=binding['job_id']
            or result['mock'] is not request.acknowledged_protocol_mock
            or row['snapshot']['input_binding']!=binding):raise WorkflowError('NATIVE_RENDER_THUMBNAIL_ORIGINAL_VISION_REQUIRED')
        return {'vision_id':row['vision_id'],'snapshot_sha256':row['snapshot_sha256'],'result_sha256':row['result_sha256'],
            'response_id':row['response_id'],'response_sha256':row['response']['response_sha256'],'cost_operation_id':row['cost_operation_id'],
            'mock':result['mock'],'semantic_inference_performed':result['semantic_inference_performed'],'confidence_calibrated':False,
            'publishing_authorized':False,'source_asset_consent_reused':False}

    def read(self,con,row):
        self.connection(con)
        try:
            if row is None:raise WorkflowError('NATIVE_RENDER_THUMBNAIL_NOT_FOUND',404)
            v=dict(row);snapshot=json.loads(v.pop('snapshot_json'));request=Create.model_validate({**snapshot['request'],'request_key':'internal-render-thumbnail-read'})
            if set(snapshot)!={'schema_version','thumbnail_asset_id','workspace_id','project_id','request','input_binding','frame','reviewed_vision','actor_ref','created_at','image','external_provider_calls','paid_operations',*FALSE_FLAGS}:raise ValueError()
            binding=snapshot['input_binding'];frame=snapshot['frame'];job=self.store.job(con.execute('SELECT * FROM jobs WHERE id=?',(request.render_job_id,)).fetchone(),con)
            project=self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(v['project_id'],)).fetchone())
            if (v['workspace_id']!=self.workspace or snapshot['workspace_id']!=self.workspace or snapshot['project_id']!=project['id']
                or snapshot['schema_version']!=SCHEMA or snapshot['thumbnail_asset_id']!=v['thumbnail_asset_id'] or not re.fullmatch(PATTERN,v['thumbnail_asset_id'])
                or digest(snapshot)!=v['snapshot_sha256'] or digest(snapshot['request'])!=v['request_sha256']
                or any(snapshot[k] is not False for k in FALSE_FLAGS) or snapshot['external_provider_calls']!=0 or type(snapshot['external_provider_calls']) is not int
                or snapshot['paid_operations']!=0 or type(snapshot['paid_operations']) is not int or snapshot['created_at']!=v['created_at']
                or not isinstance(snapshot['actor_ref'],str) or not 1<=len(snapshot['actor_ref'])<=100 or datetime.fromisoformat(v['created_at']).utcoffset() is None
                or job['project_id']!=project['id'] or job['kind']!='render' or job['status']!='succeeded'
                or binding['workspace_id']!=self.workspace or binding['project_id']!=project['id'] or binding['job_id']!=job['id']
                or digest(binding)!=request.expected_render_input_sha256 or binding['current_project_revision']!=request.revision
                or binding['matches_current_project_document'] is not True or binding['original_document_sha256']!=digest(job['snapshot']['document'])
                or binding['original_snapshot_sha256']!=digest(job['snapshot']) or binding['original_result_sha256']!=digest(job['result'])
                or binding['original_approval_sha256']!=digest(job['snapshot'].get('approval'))):raise ValueError()
            if (binding['schema_version']!='native-render-vision-frame-input-v1' or binding['purpose']!='rendered_video_quality_review'
                or binding['render_artifact_id']!='render:'+job['id'] or type(binding['current_project_revision']) is not int
                or type(binding['revision']) is not int or binding['revision']!=job['revision']
                or binding['separate_owner_provider_consent_required'] is not True
                or any(binding[k] is not False for k in ('source_asset_analysis_consent_reused','semantic_inference_performed',
                    'prediction_confidence_calibrated','continuous_tracking_performed','publishing_authorized','owner_uat_accepted','real_provider_tested'))
                or any(type(binding[k]) is not int or binding[k]!=0 for k in ('external_provider_calls','paid_operations'))):raise ValueError()
            original=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',(project['id'],request.revision)).fetchone()
            if original is None or digest(json.loads(original[0]))!=binding['current_project_document_sha256']:raise ValueError()
            qc=job['result']['qc'];measured=qc['full_quality']['full_production_qc'] if qc.get('full_quality') is not None else qc
            if (qc['passed'] is not True or qc.get('full_quality') is not None and qc['full_quality']['status']!='passed'
                or binding['record']!=measured['rendered_frame_evidence'] or binding['record']['observation']['rendered_video_sha256']!=qc['final_sha256']):raise ValueError()
            validate_frames(self.store.root/'jobs'/job['id'],binding['record'],document_sha256=binding['original_document_sha256'],physical=False)
            expected=next(f for f in binding['record']['observation']['frames'] if f['frame_id']==request.frame_id)
            if expected!=frame or frame['sha256']!=request.expected_frame_sha256 or frame['pixel_facts']['black_sample']:raise ValueError()
            if self.reviewed(con,project['id'],request.reviewed_vision,binding)!=snapshot['reviewed_vision']:raise ValueError()
            if snapshot['image']!={'content_type':'image/png','sha256':frame['sha256'],'bytes':frame['size_bytes'],'width':frame['width'],'height':frame['height'],
                'evidence_frame_reference':frame['evidence_frame_reference'],'copied_asset_created':False,'rights_status':'unknown',
                'source_type':'rendered_frame','license':None,'publishing_rights_review_required':True}:raise ValueError()
            v.pop('key_sha256');return {**v,'schema_version':SCHEMA,'snapshot':snapshot,'publishing_authorized':False,'owner_uat_accepted':False}
        except WorkflowError:raise
        except Exception:raise WorkflowError('NATIVE_RENDER_THUMBNAIL_EVIDENCE_INVALID') from None

    def create(self,project,payload,*,actor):
        self.check()
        try:
            if type(payload) is not Create:raise ValueError()
            payload=Create.model_validate(payload.model_dump(mode='python'))
            if not isinstance(actor,str) or not 1<=len(actor)<=100:raise ValueError()
        except ValueError:raise WorkflowError('NATIVE_RENDER_THUMBNAIL_FIELDS_INVALID',400) from None
        request=payload.model_dump(mode='json',exclude={'request_key'});fp=digest(request);key=digest(payload.request_key)
        with self.store.transaction() as con:
            old=con.execute('SELECT * FROM native_render_thumbnails WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
            if old:
                if old['request_sha256']!=fp:raise WorkflowError('NATIVE_RENDER_THUMBNAIL_IDEMPOTENCY_CONFLICT')
                return self.read(con,old),True
            self.store.editable(con,project,payload.revision);bridge=self.bridge(project,payload.render_job_id,con);binding=bridge.binding(con=con)
            if digest(binding)!=payload.expected_render_input_sha256 or binding['current_project_revision']!=payload.revision or binding['matches_current_project_document'] is not True:
                raise WorkflowError('NATIVE_RENDER_THUMBNAIL_INPUT_CHANGED')
            frame=next((f for f in binding['record']['observation']['frames'] if f['frame_id']==payload.frame_id),None)
            if frame is None or frame['sha256']!=payload.expected_frame_sha256 or frame['pixel_facts']['black_sample']:
                raise WorkflowError('NATIVE_RENDER_THUMBNAIL_FRAME_REQUIRED')
            reviewed=self.reviewed(con,project,payload.reviewed_vision,binding);stamp=now();identity='ast_rthumb_'+uuid.uuid4().hex
            snapshot={'schema_version':SCHEMA,'thumbnail_asset_id':identity,'workspace_id':self.workspace,'project_id':project,'request':request,
                'input_binding':binding,'frame':copy.deepcopy(frame),'reviewed_vision':reviewed,'actor_ref':actor,'created_at':stamp,
                'image':{'content_type':'image/png','sha256':frame['sha256'],'bytes':frame['size_bytes'],'width':frame['width'],'height':frame['height'],
                    'evidence_frame_reference':frame['evidence_frame_reference'],'copied_asset_created':False,'rights_status':'unknown','source_type':'rendered_frame',
                    'license':None,'publishing_rights_review_required':True},'external_provider_calls':0,'paid_operations':0,**{k:False for k in FALSE_FLAGS}}
            if bridge.binding(con=con)!=binding:raise WorkflowError('NATIVE_RENDER_THUMBNAIL_INPUT_CHANGED')
            con.execute('INSERT INTO native_render_thumbnails VALUES(?,?,?,?,?,?,?,?)',(identity,self.workspace,project,key,fp,digest(snapshot),json.dumps(snapshot,ensure_ascii=False),stamp))
            return self.read(con,con.execute('SELECT * FROM native_render_thumbnails WHERE thumbnail_asset_id=?',(identity,)).fetchone()),False

    def get(self,project,identity,*,con=None):
        from contextlib import nullcontext
        self.check()
        if not isinstance(identity,str) or not re.fullmatch(PATTERN,identity):raise WorkflowError('NATIVE_RENDER_THUMBNAIL_NOT_FOUND',404)
        with self.store.transaction() if con is None else nullcontext(con) as owned:
            self.connection(owned)
            return self.read(owned,owned.execute('SELECT * FROM native_render_thumbnails WHERE workspace_id=? AND project_id=? AND thumbnail_asset_id=?',(self.workspace,project,identity)).fetchone())

    def image(self,project,identity,*,con=None):
        from contextlib import nullcontext
        self.check()
        with self.store.transaction() if con is None else nullcontext(con) as owned:
            selected=self.get(project,identity,con=owned)['snapshot'];job=selected['request']['render_job_id'];bridge=self.bridge(project,job,owned);actual=bridge.binding(con=owned)
            if any(actual[k]!=selected['input_binding'][k] for k in ('original_snapshot_sha256','original_document_sha256','original_approval_sha256',
                'original_result_sha256','original_render_checkpoint_sha256','record','render_metadata','input_metadata')):raise WorkflowError('NATIVE_RENDER_THUMBNAIL_INPUT_CHANGED')
            frame=selected['frame'];path=checked(self.store.root/'jobs'/job,frame['evidence_frame_reference']);payload=path.read_bytes()
            if digest(bridge.binding(con=owned))!=digest(actual) or hashlib.sha256(payload).hexdigest()!=frame['sha256']:
                raise WorkflowError('NATIVE_RENDER_THUMBNAIL_INPUT_CHANGED')
            return payload,selected

    def page(self,project,*,limit=25,cursor=None):
        self.check();after=None
        if type(limit) is not int or not 1<=limit<=100:raise WorkflowError('NATIVE_RENDER_THUMBNAIL_PAGE_INVALID',400)
        if cursor is not None:
            try:
                if not isinstance(cursor,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,1000}',cursor):raise ValueError()
                after=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if (type(after) is not list or len(after)!=4 or after[:2]!=[self.workspace,project] or not isinstance(after[2],str)
                    or datetime.fromisoformat(after[2]).utcoffset() is None or not re.fullmatch(PATTERN,after[3])):raise ValueError()
            except Exception:raise WorkflowError('NATIVE_RENDER_THUMBNAIL_CURSOR_INVALID',400) from None
        with self.store.transaction() as con:
            self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone());where='workspace_id=? AND project_id=?';params=[self.workspace,project]
            if after:where+=' AND (created_at<? OR (created_at=? AND thumbnail_asset_id<?))';params.extend([after[2],after[2],after[3]])
            rows=con.execute('SELECT * FROM native_render_thumbnails WHERE '+where+' ORDER BY created_at DESC,thumbnail_asset_id DESC LIMIT ?',(*params,limit+1)).fetchall()
            next_cursor=base64.urlsafe_b64encode(json.dumps([self.workspace,project,rows[limit-1]['created_at'],rows[limit-1]['thumbnail_asset_id']]).encode()).decode().rstrip('=') if len(rows)>limit else None
            return {'schema_version':'native-render-thumbnail-page-v1','workspace_id':self.workspace,'project_id':project,'items':[self.read(con,r) for r in rows[:limit]],
                'next_cursor':next_cursor,'limit':limit,'publishing_authorized':False,'owner_uat_accepted':False}
