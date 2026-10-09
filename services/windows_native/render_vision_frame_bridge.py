"""Provider-neutral PNG input bound to one original verified render checkpoint.

This reader makes no external call, resolves no credential, and grants no
provider consent. The original asset-analysis factory cannot accept it.
"""
import copy
import hashlib
import math
from pathlib import Path
import re
import sqlite3
from contextlib import nullcontext

from app.auto_edit_models import MediaMetadata
from app.openai_vision_provider import ExtractedVisionFrame
from .backup import guard
from .contracts import WorkflowError,digest,file_sha
from .hardening import Artifacts
from .render_frame_qc import validate,checked,REPORT,MAX_PNG_BYTES
from .store import Store


class NativeRenderEvidenceFrameExtractor:
    def __init__(self,store,config,project_id,job_id,*,workspace_id='wsp_native_local',con=None):
        self.store,self.config=store,config
        self.root=store.root.absolute();self.project_id=project_id;self.job_id=job_id;self.workspace=workspace_id
        self.max_image_bytes=MAX_PNG_BYTES;self.max_dimension_pixels=960
        self._identity=(store,config,self.root,config.data_root.absolute(),project_id,job_id,workspace_id)
        original=self._load(con=con)
        self.max_frames=len(original['record']['observation']['frames'])
        self._max_frames=self.max_frames
        self._fingerprint=digest(original)
        self._check(con=con)

    def _load(self,*,con=None):
        try:
            if (type(self.store) is not Store or self.root!=self.config.data_root.absolute() or self.root!=self.store.root.absolute()
                or (self.store,self.config,self.root,self.config.data_root.absolute(),self.project_id,self.job_id,self.workspace)!=self._identity
                or not re.fullmatch(r'[a-f0-9]{32}',self.project_id) or not re.fullmatch(r'[a-f0-9]{32}',self.job_id)
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',self.workspace)
                or self.max_image_bytes!=MAX_PNG_BYTES or self.max_dimension_pixels!=960):raise ValueError()
            # Scope is the original local workspace; an asset-analysis approval
            # or a caller-supplied workspace label cannot remount this artifact.
            scope=guard(self.root/'.vf-auth-workspace.json')
            if scope.exists():
                import json
                if scope.stat().st_size>512 or scope.stat().st_nlink!=1 or json.loads(scope.read_bytes())!={'schema':'vf-native-workspace-binding-v1','workspace_id':self.workspace}:raise ValueError()
            elif self.workspace!='wsp_native_local':raise ValueError()
            # Admission already holds BEGIN IMMEDIATE. Reuse that exact owned
            # connection instead of opening a second writer and deadlocking.
            if con is not None and (type(con) is not sqlite3.Connection or not con.in_transaction
                or Path(con.execute('PRAGMA database_list').fetchone()[2]).absolute()!=self.store.db.absolute()):raise ValueError()
            with nullcontext(con) if con is not None else self.store.transaction() as owned:
                project=self.store.project(owned.execute('SELECT * FROM projects WHERE id=?',(self.project_id,)).fetchone())
                job=self.store.job(owned.execute('SELECT * FROM jobs WHERE id=?',(self.job_id,)).fetchone(),owned)
            if job['project_id']!=self.project_id or job['kind']!='render' or job['status']!='succeeded' or not job['result']:raise ValueError()
            directory=self.root/'jobs'/self.job_id;artifact=Artifacts(directory,job);checkpoint=artifact.load('render')
            if checkpoint is None or digest(checkpoint['result'])!=digest(job['result']):raise ValueError()
            qc=job['result']['qc']
            if qc.get('passed') is not True:raise ValueError()
            full=qc.get('full_quality')
            if full is not None:
                if full.get('status')!='passed':raise ValueError()
                measured=full['full_production_qc']
            else:measured=qc
            record=measured.get('rendered_frame_evidence')
            import json
            saved=json.loads(checked(directory,REPORT).read_bytes())
            if record is None or digest(saved)!=digest(record):raise ValueError()
            document_sha=digest(job['snapshot']['document'])
            observation=validate(directory,record,document_sha256=document_sha)
            if observation['rendered_video_sha256']!=qc['final_sha256'] or observation['rendered_video_sha256']!=measured['checksum_sha256']:raise ValueError()
            required={REPORT,'render-frame-qc.log',*(frame['evidence_frame_reference'] for frame in observation['frames'])}
            if not required.issubset({item['path'] for item in checkpoint['artifacts']}):raise ValueError()
            if len({(frame['width'],frame['height']) for frame in observation['frames']})!=1:raise ValueError()
            metadata=MediaMetadata(media_kind='video',detected_content_type='video/mp4',width=measured['width'],height=measured['height'],
                duration_seconds=measured['duration_seconds'],fps=measured['fps'],video_codec=measured['video_codec'],audio_codec=measured['audio_codec'])
            return {'workspace_id':self.workspace,'project_id':self.project_id,'job_id':self.job_id,'revision':job['revision'],
                'original_snapshot_sha256':digest(job['snapshot']),'original_document_sha256':document_sha,
                'original_approval_sha256':digest(job['snapshot'].get('approval')),'original_result_sha256':digest(job['result']),
                'original_render_checkpoint_sha256':file_sha(checked(directory,'checkpoint-render.json')),
                'record':copy.deepcopy(record),'render_metadata':metadata.model_dump(mode='json'),
                'current_project_revision':project['revision'],'current_project_document_sha256':digest(project['document']),
                'matches_current_project_document':document_sha==digest(project['document'])}
        except Exception:raise WorkflowError('NATIVE_RENDER_VISION_INPUT_BINDING_INVALID') from None

    def _check(self,*,con=None):
        value=self._load(con=con)
        if (digest(value)!=self._fingerprint or type(self.max_frames) is not int or self.max_frames!=self._max_frames
            or self.max_frames!=len(value['record']['observation']['frames'])):
            raise WorkflowError('NATIVE_RENDER_VISION_INPUT_CHANGED')
        return value

    def input_metadata(self,*,con=None):
        value=self._check(con=con);frame=value['record']['observation']['frames'][0]
        return MediaMetadata(media_kind='image',detected_content_type='image/png',format_name='png',width=frame['width'],height=frame['height'])

    def binding(self,*,con=None):
        value=self._check(con=con)
        return {'schema_version':'native-render-vision-frame-input-v1',**copy.deepcopy(value),
            'render_artifact_id':'render:'+self.job_id,'input_metadata':self.input_metadata(con=con).model_dump(mode='json'),
            'source_asset_analysis_consent_reused':False,'separate_owner_provider_consent_required':True,
            'purpose':'rendered_video_quality_review','semantic_inference_performed':False,'prediction_confidence_calibrated':False,
            'continuous_tracking_performed':False,'external_provider_calls':0,'paid_operations':0,'publishing_authorized':False,
            'owner_uat_accepted':False,'real_provider_tested':False}

    async def extract(self,path,*,metadata,scenes,asset_id,sample_interval_seconds):
        value=self._check();directory=self.root/'jobs'/self.job_id;observation=value['record']['observation']
        try:
            if (Path(path).absolute()!=checked(directory,'final.mp4').absolute() or asset_id!='render:'+self.job_id
                or type(asset_id) is not str or type(metadata) is not MediaMetadata
                or set(metadata.__dict__)-set(MediaMetadata.model_fields)
                or digest(metadata.model_dump(mode='json'))!=digest(self.input_metadata().model_dump(mode='json'))
                or type(scenes) is not list or scenes!=[] or type(sample_interval_seconds) not in (int,float) or not math.isfinite(sample_interval_seconds)
                or abs(sample_interval_seconds-observation['sampling_interval_seconds'])>.000001):raise ValueError()
            frames=[]
            for frame in observation['frames']:
                payload=checked(directory,frame['evidence_frame_reference']).read_bytes()
                if len(payload)>self.max_image_bytes or hashlib.sha256(payload).hexdigest()!=frame['sha256']:raise ValueError()
                frames.append(ExtractedVisionFrame(timestamp_seconds=frame['timestamp_seconds'],
                    evidence_frame_reference=f"render-frame://{self.project_id}/{self.job_id}/{Path(frame['evidence_frame_reference']).name}",
                    content_type='image/png',payload=payload,sha256=frame['sha256']))
            self._check()
            return tuple(frames)
        except WorkflowError:raise
        except Exception:raise WorkflowError('NATIVE_RENDER_VISION_INPUT_REQUEST_INVALID') from None
