"""Local, immutable manual-posting packages. No platform/provider dispatch.

An export copies an already approved byte stream. Changing format, captions burned
into pixels, sound or rendering quality requires a new preview/render approval.
"""
import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictBool, field_validator
from app.models import StrictModel
from app.production_qc import FullProductionQC, ProductionQCError
from .backup import guard
from .contracts import WorkflowError, digest, file_sha
from .hardening import durable_json, version_components
from .north_star_quality import PROFILES, validate_render_profile
from .store import now

SCHEMA = 'native-manual-delivery.v1'
EXPORT_ID = r'nexp_[a-f0-9]{32}'
PLATFORMS = {'master', 'tiktok', 'facebook-reels', 'instagram-reels', 'youtube-shorts'}


class CopyText(StrictModel):
    title: str = Field(default='', max_length=300)
    caption: str = Field(default='', max_length=10000)
    description: str = Field(default='', max_length=10000)
    hashtags: str = Field(default='', max_length=2000)
    cta: str = Field(default='', max_length=1000)


class CaptionSave(StrictModel):
    expected_version: int = Field(strict=True, ge=0)
    request_key: str = Field(pattern=r'^[A-Za-z0-9_-]{16,120}$')
    variants: dict[str, CopyText]

    @field_validator('variants')
    @classmethod
    def platforms(cls, value):
        if not value or not set(value) <= PLATFORMS:
            raise ValueError('Unsupported copy variant')
        return value


class DeliveryCreate(StrictModel):
    revision: int = Field(strict=True, ge=1)
    render_job_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    expected_video_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    profile: Literal['vertical-short', 'landscape', 'square', 'portrait-feed'] = 'vertical-short'
    filename: str = Field(default='final-video.mp4', min_length=5, max_length=100)
    caption_version: int = Field(default=0, strict=True, ge=0)
    separate_subtitle: StrictBool = True
    cover: StrictBool = True
    cover_at_seconds: float = Field(default=0, ge=0, le=3600, allow_inf_nan=False)
    request_key: str = Field(pattern=r'^[A-Za-z0-9_-]{16,120}$')

    @field_validator('filename')
    @classmethod
    def safe_filename(cls, value):
        stem = value[:-4]
        if (not value.endswith('.mp4') or not stem or value != value.strip() or stem.endswith(('.', ' '))
            or re.search(r'[\\/:*?"<>|\x00-\x1f]', value) or value.startswith('.')
            or re.fullmatch(r'(?i:con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?', stem)):
            raise ValueError('Use one Windows-safe MP4 filename')
        return value


def srt(cues, duration):
    def clock(value):
        millis = round(value * 1000)
        return f'{millis//3600000:02}:{millis//60000%60:02}:{millis//1000%60:02},{millis%1000:03}'
    output = []
    for cue in cues:
        start = cue.get('start_seconds', cue.get('start'))
        end = cue.get('end_seconds', cue.get('end'))
        text = cue.get('text')
        if (type(start) not in (int, float) or type(end) not in (int, float)
            or not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end <= duration + .1
            or not isinstance(text, str) or not text.strip() or '\x00' in text or '-->' in text):
            raise WorkflowError('EXPORT_SUBTITLE_TIMING_INVALID', 409)
        output.append(f'{len(output)+1}\n{clock(start)} --> {clock(end)}\n{text.strip()}\n')
    return '\n'.join(output)


class NativeManualDelivery:
    def __init__(self, store, config, *, workspace_id='wsp_native_local'):
        if config.data_root.absolute() != store.root.absolute():
            raise WorkflowError('EXPORT_WORKSPACE_INVALID')
        self.store, self.config, self.workspace = store, config, workspace_id
        self._scope = (store.root.absolute(), config.data_root.absolute(), workspace_id)
        with store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_manual_exports (
                export_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, project_id TEXT NOT NULL,
                request_key TEXT NOT NULL, request_sha256 TEXT NOT NULL, request_json TEXT NOT NULL,
                binding_json TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL,
                manifest_sha256 TEXT, package_sha256 TEXT, error_code TEXT,
                UNIQUE(workspace_id, project_id, request_key));
                CREATE TABLE IF NOT EXISTS native_delivery_copy (
                workspace_id TEXT NOT NULL, project_id TEXT NOT NULL, version INTEGER NOT NULL,
                request_key TEXT NOT NULL, request_sha256 TEXT NOT NULL, variants_json TEXT NOT NULL,
                created_at TEXT NOT NULL, PRIMARY KEY(workspace_id,project_id,version),
                UNIQUE(workspace_id,project_id,request_key));''')

    def scope(self):
        if self._scope != (self.store.root.absolute(), self.config.data_root.absolute(), self.workspace):
            raise WorkflowError('EXPORT_WORKSPACE_INVALID')
        guard(self.store.root, exists=True)
        marker = guard(self.store.root/'.vf-auth-workspace.json')
        if marker.exists() and json.loads(marker.read_bytes()) != {'schema':'vf-native-workspace-binding-v1','workspace_id':self.workspace}:
            raise WorkflowError('EXPORT_WORKSPACE_INVALID')
        if not marker.exists() and self.workspace!='wsp_native_local':raise WorkflowError('EXPORT_WORKSPACE_INVALID')

    def copies(self, project_id):
        self.scope(); self.store.get(project_id)
        with self.store.transaction() as con:
            rows = con.execute('SELECT version,variants_json,created_at FROM native_delivery_copy WHERE workspace_id=? AND project_id=? ORDER BY version DESC LIMIT 100', (self.workspace,project_id)).fetchall()
        return {'items':[{'version':r['version'],'variants':json.loads(r['variants_json']),'created_at':r['created_at']} for r in rows],
                'externally_posted':False}

    def save_copy(self, project_id, payload):
        self.scope(); self.store.get(project_id)
        request = payload.model_dump(mode='json'); fingerprint = digest(request)
        with self.store.transaction() as con:
            old = con.execute('SELECT * FROM native_delivery_copy WHERE workspace_id=? AND project_id=? AND request_key=?', (self.workspace,project_id,payload.request_key)).fetchone()
            if old:
                if old['request_sha256'] != fingerprint: raise WorkflowError('EXPORT_REQUEST_KEY_CONFLICT')
                return {'version':old['version'],'variants':json.loads(old['variants_json']),'idempotent_replay':True}
            version = con.execute('SELECT COALESCE(MAX(version),0) FROM native_delivery_copy WHERE workspace_id=? AND project_id=?',(self.workspace,project_id)).fetchone()[0]
            if version != payload.expected_version: raise WorkflowError('EXPORT_CAPTION_VERSION_CHANGED')
            variants = request['variants']
            con.execute('INSERT INTO native_delivery_copy VALUES(?,?,?,?,?,?,?)', (self.workspace,project_id,version+1,payload.request_key,fingerprint,json.dumps(variants,ensure_ascii=False),now()))
            return {'version':version+1,'variants':variants,'idempotent_replay':False}

    def binding(self, project_id, payload, con):
        job, checksum = self.store.verified_render(payload.render_job_id, con)
        if job['project_id'] != project_id or job['revision'] != payload.revision or checksum != payload.expected_video_sha256:
            raise WorkflowError('EXPORT_APPROVED_VERSION_CHANGED')
        review = job['final_review']
        if not review or review['decision'] != 'approve' or review['artifact_sha256'] != checksum or review['snapshot_sha256'] != digest(job['snapshot']):
            raise WorkflowError('HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED')
        qc = job['result']['qc']; full = (qc.get('full_quality') or {}).get('full_production_qc') or qc
        if full.get('status') != 'passed' or full.get('checksum_sha256') != checksum:
            raise WorkflowError('EXPORT_MEASURED_QC_REQUIRED')
        validate_render_profile(payload.profile, full.get('width'), full.get('height'))
        doc = job['snapshot']['document']; timeline = doc.get('canonical_timeline') or {}
        return {'project_id':project_id,'project_revision':job['revision'],'project_title':doc['name'],
            'render_job_id':job['id'],'snapshot_sha256':digest(job['snapshot']),'document_sha256':digest(doc),
            'timeline_version':timeline.get('version'),'timeline_sha256':timeline.get('sha256'),
            **version_components(doc),'audio_version':digest({'voice':doc.get('prepared_narration'),'music':doc.get('music'),'timeline':timeline.get('sha256')}),
            'subtitle_version':digest({'timeline':timeline.get('sha256'),'captions':doc.get('proposal')}),
            'render_profile':payload.profile,'final_preview_sha256':checksum,'video_sha256':checksum,
            'duration_seconds':full['duration_seconds'],'width':full['width'],'height':full['height'],'fps':full['fps'],
            'final_review_sha256':digest(review),'production_approval_sha256':digest(job['snapshot']['approval'])}, job, full

    def row(self, con, project_id, export_id):
        self.scope()
        value = con.execute('SELECT * FROM native_manual_exports WHERE workspace_id=? AND project_id=? AND export_id=?', (self.workspace,project_id,export_id)).fetchone()
        if value is None: raise WorkflowError('EXPORT_NOT_FOUND',404)
        return dict(value)

    def directory(self, row):
        return guard(self.store.root/'deliveries'/row['project_id']/row['export_id'])

    def verify(self, row):
        directory = self.directory(row); path = guard(directory/'delivery-manifest.json', exists=True)
        if path.stat().st_size > 256*1024: raise WorkflowError('EXPORT_MANIFEST_CHANGED')
        manifest = json.loads(path.read_bytes())
        if (manifest.get('schema_version') != SCHEMA or manifest.get('export_id') != row['export_id']
            or manifest.get('binding') != json.loads(row['binding_json']) or manifest.get('request_sha256') != row['request_sha256']
            or manifest.get('created_at') != row['created_at'] or not isinstance(manifest.get('files'),dict)
            or not row['manifest_sha256'] or file_sha(path) != row['manifest_sha256']):
            raise WorkflowError('EXPORT_MANIFEST_CHANGED')
        for name, expected in manifest['files'].items():
            if not isinstance(name,str) or Path(name).name != name or name in ('.','..') or '/' in name or '\\' in name:
                raise WorkflowError('EXPORT_MANIFEST_CHANGED')
            source = guard(directory/name, exists=True)
            if source.stat().st_size != expected['bytes'] or file_sha(source) != expected['sha256']:
                raise WorkflowError('EXPORT_FILE_CHANGED')
        package = guard(directory/'delivery-package.zip', exists=True)
        if not row['package_sha256'] or file_sha(package) != row['package_sha256']: raise WorkflowError('EXPORT_PACKAGE_CHANGED')
        with zipfile.ZipFile(package) as archive:
            if set(archive.namelist()) != set(manifest['files']) | {'delivery-manifest.json'} or archive.testzip() is not None:
                raise WorkflowError('EXPORT_PACKAGE_CHANGED')
            for name, expected in manifest['files'].items():
                import hashlib
                h=hashlib.sha256()
                with archive.open(name) as stream:
                    for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
                if h.hexdigest()!=expected['sha256']:raise WorkflowError('EXPORT_PACKAGE_CHANGED')
            if archive.read('delivery-manifest.json') != path.read_bytes():raise WorkflowError('EXPORT_PACKAGE_CHANGED')
        return manifest

    def get(self, project_id, export_id, *, verify=True):
        with self.store.transaction() as con:
            row = self.row(con,project_id,export_id)
            project = self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone())
        manifest = self.verify(row) if row['status']=='ready' and verify else None
        binding=json.loads(row['binding_json'])
        return {'export_id':export_id,'project_id':project_id,'created_at':row['created_at'],'status':row['status'],
            'binding':binding,'profile':binding['render_profile'],'manifest':manifest,'error_code':row['error_code'],
            'approval_state':'approved_at_export' if row['status']=='ready' else 'pending_delivery',
            'current_for_project':project['revision']==binding['project_revision'] and digest(project['document'])==binding['document_sha256'],
            'integrity_checked':manifest is not None,'output_location':str(self.directory(row)),'externally_posted':False,
            'filename':json.loads(row['request_json'])['filename'],
            'files':list(manifest['files']) if manifest else [],'package_ready':row['status']=='ready'}

    def page(self, project_id):
        self.scope(); self.store.get(project_id)
        with self.store.transaction() as con:
            ids=[r[0] for r in con.execute('SELECT export_id FROM native_manual_exports WHERE workspace_id=? AND project_id=? ORDER BY created_at DESC,export_id DESC LIMIT 100',(self.workspace,project_id))]
        return {'items':[self.get(project_id,identifier,verify=False) for identifier in ids],'externally_posted':False}

    def create(self, project_id, payload, *, authorization_check=lambda:None):
        self.scope();authorization_check()
        # Shared OS/thread lease releases on process termination. Exact-key retries
        # serialize before custody hashes can be recorded or the directory handed off.
        from .source_audio_cache import lease
        lockdir=guard(self.store.root/'.export-locks');lockdir.mkdir(exist_ok=True)
        with lease(lockdir/(digest([self.workspace,project_id,payload.request_key])+'.lock'),timeout=15):
            authorization_check()
            return self._create(project_id,payload,authorization_check=authorization_check)

    def _create(self, project_id, payload, *, authorization_check):
        self.scope(); request=payload.model_dump(mode='json'); fingerprint=digest(request)
        with self.store.transaction() as con:
            binding, job, measured=self.binding(project_id,payload,con)
            old=con.execute('SELECT * FROM native_manual_exports WHERE workspace_id=? AND project_id=? AND request_key=?',(self.workspace,project_id,payload.request_key)).fetchone()
            if old:
                if old['request_sha256']!=fingerprint or json.loads(old['binding_json'])!=binding:raise WorkflowError('EXPORT_REQUEST_KEY_CONFLICT')
                row=dict(old)
            else:
                row={'export_id':'nexp_'+uuid.uuid4().hex,'workspace_id':self.workspace,'project_id':project_id,
                    'request_key':payload.request_key,'request_sha256':fingerprint,'request_json':json.dumps(request),
                    'binding_json':json.dumps(binding,ensure_ascii=False),'created_at':now(),'status':'preparing',
                    'manifest_sha256':None,'package_sha256':None,'error_code':None}
                con.execute('INSERT INTO native_manual_exports VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
        try:
            if row['status']=='ready':return {**self.get(project_id,row['export_id']),'idempotent_replay':True}
            target=self.directory(row)
            if target.exists():
                self.verify(row)
            else:
                self.build(row,payload,job,measured)
            with self.store.transaction() as con:
                fresh,_,_=self.binding(project_id,payload,con)
                if fresh!=binding:raise WorkflowError('EXPORT_APPROVED_VERSION_CHANGED')
                self.verify(row)
                authorization_check()
                con.execute("UPDATE native_manual_exports SET status='ready',manifest_sha256=?,package_sha256=?,error_code=NULL WHERE export_id=?",(file_sha(target/'delivery-manifest.json'),file_sha(target/'delivery-package.zip'),row['export_id']))
            return {**self.get(project_id,row['export_id']),'idempotent_replay':old is not None}
        except (OSError,ValueError,KeyError,zipfile.BadZipFile,WorkflowError,ProductionQCError,subprocess.SubprocessError) as error:
            code=error.code if isinstance(error,WorkflowError) else 'EXPORT_QC_FAILED' if isinstance(error,ProductionQCError) else 'EXPORT_WRITE_FAILED'
            with self.store.transaction() as con:
                con.execute("UPDATE native_manual_exports SET status='failed',error_code=? WHERE export_id=? AND status!='ready'",(code,row['export_id']))
            raise WorkflowError(code,409 if code!='EXPORT_WRITE_FAILED' else 503) from None

    def build(self, row, payload, job, measured):
        source=guard(self.store.root/'jobs'/job['id'],exists=True)
        target=self.directory(row);parent=guard(target.parent);parent.mkdir(parents=True,exist_ok=True)
        stage=guard(parent/('.partial-'+row['export_id']+'-'+uuid.uuid4().hex));stage.mkdir()
        if shutil.disk_usage(parent).free < (source/'final.mp4').stat().st_size*2+16*1024*1024:
            raise WorkflowError('EXPORT_DISK_SPACE_REQUIRED',503)
        # Copy bytes before measuring so the actual delivered file receives full QC.
        shutil.copyfile(guard(source/'final.mp4',exists=True),stage/payload.filename)
        if file_sha(stage/payload.filename)!=payload.expected_video_sha256:raise WorkflowError('EXPORT_FILE_CHANGED')
        qc=job['result']['qc']; full=(qc.get('full_quality') or {})
        subtitle=full.get('subtitle_bounds') or qc.get('subtitle_bounds')
        timeline=full.get('timeline') or qc.get('timeline')
        if not subtitle or not timeline:raise WorkflowError('EXPORT_MEASURED_QC_REQUIRED')
        report=asyncio.run(FullProductionQC(ffmpeg_path=str(self.config.ffmpeg_bin/'ffmpeg.exe'),ffprobe_path=str(self.config.ffmpeg_bin/'ffprobe.exe')).inspect(
            stage/payload.filename,expected_duration=measured['duration_seconds'],expected_width=measured['width'],expected_height=measured['height'],
            expected_fps=measured['fps'],subtitle_qc=subtitle,timeline_qc=timeline))
        durable_json(stage/'qc-report.json',report)
        doc=job['snapshot']['document']
        from .source_assets import canonical_assets
        rights=[]
        for asset in canonical_assets(doc):
            rights.append({key:asset.get(key) for key in ('id','sha256','kind','source_type','rights_status','license','provider')})
        durable_json(stage/'rights-summary.json',{'items':rights,'independently_verified':False,'manual_posting_review_required':True,
            'unknown_rights_count':sum(a.get('rights_status') not in ('owned','licensed') for a in rights),'external_publishing_authorized':False})
        with self.store.transaction() as con:
            copyrow=con.execute('SELECT * FROM native_delivery_copy WHERE workspace_id=? AND project_id=? AND version=?',(self.workspace,row['project_id'],payload.caption_version)).fetchone()
        if payload.caption_version and not copyrow:raise WorkflowError('EXPORT_CAPTION_VERSION_CHANGED')
        variants=json.loads(copyrow['variants_json']) if copyrow else {}
        if variants:
            durable_json(stage/'caption-variants.json',{'version':payload.caption_version,'variants':variants})
            for platform,text in variants.items():
                for key,value in text.items():
                    if value:(stage/f'{platform}-{key}.txt').write_text(value+'\n',encoding='utf-8')
            for key,value in variants.get('master',{}).items():
                if value:(stage/f'{key}.txt').write_text(value+'\n',encoding='utf-8')
        if payload.separate_subtitle:
            raw=None
            if (source/'subtitles.json').is_file():raw=json.loads((source/'subtitles.json').read_bytes()).get('cues')
            if raw is None and (source/'render-manifest.json').is_file():raw=json.loads((source/'render-manifest.json').read_bytes()).get('captions')
            if raw:
                (stage/'subtitle.srt').write_text(srt(raw,report['duration_seconds']),encoding='utf-8')
        if payload.cover:
            if payload.cover_at_seconds>=report['duration_seconds']:raise WorkflowError('EXPORT_COVER_TIME_INVALID',400)
            subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-ss',str(payload.cover_at_seconds),'-i',str(stage/payload.filename),
                '-frames:v','1','-q:v','2',str(stage/'cover.jpg')],check=True,timeout=60,capture_output=True)
            durable_json(stage/'cover-provenance.json',{'source_type':'approved_render_frame','video_sha256':payload.expected_video_sha256,
                'timestamp_seconds':payload.cover_at_seconds,'crop':'original_render_geometry','generated_by_ai':False})
        durable_json(stage/'metadata.json',{'project_title':doc['name'],'export_id':row['export_id'],'profile':payload.profile,
            'caption_version':payload.caption_version,'externally_posted':False})
        files={p.name:{'bytes':p.stat().st_size,'sha256':file_sha(p)} for p in stage.iterdir() if p.is_file()}
        manifest={'schema_version':SCHEMA,'export_id':row['export_id'],'created_at':row['created_at'],'request_sha256':row['request_sha256'],
            'binding':json.loads(row['binding_json']),'video_filename':payload.filename,'video_sha256':payload.expected_video_sha256,
            'duration_seconds':report['duration_seconds'],'width':report['width'],'height':report['height'],
            'aspect_ratio':PROFILES[payload.profile][2],'video_codec':report['video_codec'],'audio_codec':report['audio_codec'],
            'fps':report['fps'],'qc_result':report['status'],'caption_version':payload.caption_version,
            'rights_summary_reference':'rights-summary.json','files':files,'externally_posted':False}
        durable_json(stage/'delivery-manifest.json',manifest)
        with zipfile.ZipFile(stage/'delivery-package.zip','x',compression=zipfile.ZIP_STORED) as archive:
            for name in [*files,'delivery-manifest.json']:archive.write(stage/name,name)
        # Persist exact output custody before the directory handoff. A restart may
        # reconcile these exact bytes; it cannot bless a substituted manifest.
        row.update(manifest_sha256=file_sha(stage/'delivery-manifest.json'),package_sha256=file_sha(stage/'delivery-package.zip'))
        with self.store.transaction() as con:
            con.execute('UPDATE native_manual_exports SET manifest_sha256=?,package_sha256=? WHERE export_id=? AND status!=?',
                (row['manifest_sha256'],row['package_sha256'],row['export_id'],'ready'))
        # No replace: a collision is preserved and reconciled, never overwritten.
        stage.rename(target)

    def file(self, project_id, export_id, filename):
        with self.store.transaction() as con:row=self.row(con,project_id,export_id)
        if row['status']!='ready':raise WorkflowError('EXPORT_NOT_READY')
        manifest=self.verify(row)
        if filename not in {*manifest['files'],'delivery-manifest.json','delivery-package.zip'}:raise WorkflowError('EXPORT_FILE_NOT_FOUND',404)
        return guard(self.directory(row)/filename,exists=True)
