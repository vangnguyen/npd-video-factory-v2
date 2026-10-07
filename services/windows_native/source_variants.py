"""Atomic source variant families; reused evidence is derived, never a fresh inference."""
import base64,json,re,uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from pydantic import Field,StrictInt,model_validator
from .contracts import WorkflowError,digest
from .auto_edit_analysis import asset_reference
from .auto_edit_timeline import _cas,is_auto_edit,validate_document
from .media import project_assets
from .source_assets import canonical_assets
from .source_duplicate import rebind
from .source_preview import resolve_assets
from .store import now
from app.models import StrictModel
from app.auto_edit_models import MediaMetadata
from app.timeline_models import TimelineSnapshot
from app.timeline_reframe import ASPECT_DIMENSIONS,bind_reframe
from app.timeline_logic import TimelineEditError
from app.vision_logic import build_reframe_plans
from app.production_logic import derive_subtitle_cues,validate_subtitles,ProductionContractError
from app.production_models import SubtitleStyle

CATALOG=Path(__file__).resolve().parents[2]/'packages/contracts/native-source-variants.json'
ALGORITHM='native-source-variants-v1'

class Profile(StrictModel):
    profile_ref:str=Field(pattern=r'^[a-z][a-z0-9-]{2,60}@[1-9][0-9]*$')
    label:str=Field(min_length=1,max_length=100)
    platform:Literal['youtube','tiktok','instagram','facebook']|None
    aspect_ratio:Literal['9:16','16:9','1:1','4:5']
    width:StrictInt
    height:StrictInt
    @model_validator(mode='after')
    def geometry(self):
        if (self.width,self.height)!=ASPECT_DIMENSIONS[self.aspect_ratio]:raise ValueError('Profile geometry mismatch')
        return self

class Catalog(StrictModel):
    schema_version:Literal['native-source-variant-catalog-v1']
    catalog_ref:str=Field(pattern=r'^[a-z][a-z0-9-]{2,60}@[1-9][0-9]*$')
    profiles:list[Profile]=Field(min_length=1,max_length=32)
    @model_validator(mode='after')
    def unique(self):
        if len({p.profile_ref for p in self.profiles})!=len(self.profiles):raise ValueError('Duplicate profile')
        return self

class Create(StrictModel):
    revision:StrictInt=Field(ge=1)
    expected_version:StrictInt=Field(ge=1)
    profile_refs:list[str]=Field(min_length=1,max_length=6)
    crop_policy:Literal['center_attention']='center_attention'
    request_key:str=Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{15,99}$')
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.profile_refs))!=len(self.profile_refs):raise ValueError('Duplicate profiles')
        return self

def catalog():
    try:value=Catalog.model_validate_json(CATALOG.read_bytes()).model_dump(mode='json')
    except (ValueError,OSError):raise WorkflowError('SOURCE_VARIANT_CATALOG_INVALID',503) from None
    return {**value,'sha256':digest(value),'render_or_publish_dispatched':False}

def draft_document(parent,identifier,profile,request_sha,stamp,media):
    document=rebind(parent['document'],parent['id'],identifier,parent['revision'],stamp)
    snapshot=TimelineSnapshot.model_validate(document['canonical_timeline']['snapshot'])
    assets={asset_reference(asset):asset for asset in canonical_assets(document)}
    needed={clip.asset_id for track in snapshot.tracks if track.type=='video' and not track.disabled for clip in track.clips if clip.asset_id and not clip.disabled}
    root=next(record for record in document['auto_edit_analyses'] if record['analysis']['analysis_id']==snapshot.metadata['source_analysis_id'])
    plans=[]
    for asset_id in sorted(needed):
        asset=assets[asset_id];measured=root['analysis']['source_media'] if asset['id']==root['native_asset_id'] else asset
        if not measured.get('width') or not measured.get('height'):raise WorkflowError('SOURCE_VARIANT_MEASURED_GEOMETRY_REQUIRED',400)
        with media[asset_id][1].open('rb') as file:header=file.read(16)
        mime='image/jpeg' if header.startswith(b'\xff\xd8\xff') else 'image/png' if header.startswith(b'\x89PNG\r\n\x1a\n') else (
            'video/quicktime' if header[8:12]==b'qt  ' else 'video/mp4') if header[4:8]==b'ftyp' else None
        if mime is None or mime.split('/')[0]!=asset['kind']:raise WorkflowError('SOURCE_VARIANT_MEDIA_MAGIC_INVALID',400)
        metadata=MediaMetadata(media_kind=asset['kind'],detected_content_type=mime,
            width=measured['width'],height=measured['height'],duration_seconds=asset.get('duration_seconds'))
        plan=build_reframe_plans(frames=[],tracks=[],metadata=metadata,aspect_ratios=[profile['aspect_ratio']],manual_overrides=[],
            minimum_tracking_confidence=.6,subtitle_safe_area_bottom=.18,maximum_jump=.12,fingerprint=digest([ALGORITHM,request_sha,identifier,asset_id]))[0]
        try:snapshot=bind_reframe(snapshot,asset_id=asset_id,metadata=metadata,plan=plan,vision_analysis_id=None)
        except TimelineEditError:raise WorkflowError('SOURCE_VARIANT_UNLOCK_VISUAL_TRACK_BEFORE_DERIVATION',400) from None
        plans.append({'asset_id':asset_id,'plan':plan.model_dump(mode='json'),'source_sha256':asset['sha256']})
    if not needed:raise WorkflowError('SOURCE_VARIANT_ACTIVE_VISUAL_REQUIRED',400)
    snapshot.width,snapshot.height=profile['width'],profile['height'];snapshot.aspect_ratio=profile['aspect_ratio']
    snapshot.metadata.pop('source_reframe_plan',None)
    snapshot.metadata['reframe_review']={'needs_attention':True,'fallback':'center_crop','tracking_confidence':None,'human_review_required':True,'confidence_basis':'unmeasured_subject_center_fallback'}
    snapshot.metadata['source_variant']={'schema_version':ALGORITHM,'master_project_id':parent['id'],'master_revision':parent['revision'],
        'master_document_sha256':digest(parent['document']),'master_timeline_sha256':parent['document']['canonical_timeline']['sha256'],
        'profile':profile,'request_fingerprint':request_sha,'crop_policy':'center_attention','plans':plans,
        'provider_dispatches':0,'fresh_provider_measurement':False,'approval_inherited':False,'human_review_required':True}
    try:validate_subtitles(derive_subtitle_cues(snapshot),SubtitleStyle.model_validate(snapshot.metadata.get('subtitle_style') or {'animation':'none'}),snapshot.duration_seconds)
    except ProductionContractError:raise WorkflowError('SOURCE_VARIANT_SUBTITLE_REVIEW_REQUIRED',400) from None
    document['canonical_timeline']={'version':1,'snapshot':snapshot.model_dump(mode='json'),'sha256':digest(snapshot.model_dump(mode='json'))}
    document['name']=parent['document']['name'][:100]+' · '+profile['label'][:45]
    validate_document(document);return document

class SourceVariants:
    def __init__(self,store,*,workspace_id='wsp_native_local'):
        self.store,self.workspace=store,workspace_id
        with store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_source_variant_batches (
                batch_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,master_project_id TEXT NOT NULL,
                request_key_sha256 TEXT NOT NULL,request_fingerprint TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,result_sha256 TEXT NOT NULL,result_json TEXT NOT NULL,actor_ref TEXT NOT NULL,created_at TEXT NOT NULL,
                UNIQUE(workspace_id,master_project_id,request_key_sha256));
                CREATE INDEX IF NOT EXISTS native_source_variant_history ON native_source_variant_batches(workspace_id,master_project_id,created_at,batch_id);''')

    def read(self,row,con):
        value=dict(row);snapshot=json.loads(value.pop('snapshot_json'));result=json.loads(value.pop('result_json'))
        if digest(snapshot)!=value['snapshot_sha256'] or digest(result)!=value['result_sha256'] or snapshot['workspace_id']!=self.workspace or snapshot['master_project_id']!=value['master_project_id']:
            raise WorkflowError('SOURCE_VARIANT_EVIDENCE_CHANGED')
        if digest(snapshot['request'])!=value['request_fingerprint'] or [item['profile']['profile_ref'] for item in result['variants']]!=snapshot['request']['profile_refs']:
            raise WorkflowError('SOURCE_VARIANT_EVIDENCE_CHANGED')
        frozen=snapshot['catalog'];parsed=Catalog.model_validate({key:frozen[key] for key in ['schema_version','catalog_ref','profiles']}).model_dump(mode='json')
        if digest(parsed)!=frozen['sha256'] or result.get('master_project_mutated') is not False or result.get('external_provider_calls')!=0 or result.get('paid_operations')!=0 or result.get('publishing_enabled') is not False:
            raise WorkflowError('SOURCE_VARIANT_EVIDENCE_CHANGED')
        profiles={item['profile_ref']:item for item in parsed['profiles']}
        parent=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',(value['master_project_id'],snapshot['master_revision'])).fetchone()
        if parent is None or digest(json.loads(parent['document']))!=snapshot['master_document_sha256'] or snapshot['master_revision']!=snapshot['request']['revision']:
            raise WorkflowError('SOURCE_VARIANT_MASTER_HISTORY_CHANGED')
        for item in result['variants']:
            Profile.model_validate(item['profile'])
            if item['profile']!=profiles.get(item['profile']['profile_ref']) or not re.fullmatch(r'[a-f0-9]{32}',item['project_id']) or item['approval_inherited'] is not False or item['render_dispatched'] is not False or item['crop_needs_attention'] is not True:
                raise WorkflowError('SOURCE_VARIANT_EVIDENCE_CHANGED')
            child=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=1',(item['project_id'],)).fetchone()
            document=json.loads(child['document']) if child else None
            if document is None or digest(document)!=item['initial_document_sha256'] or document['canonical_timeline']['sha256']!=item['initial_timeline_sha256']:
                raise WorkflowError('SOURCE_VARIANT_CHILD_HISTORY_CHANGED')
            lineage=document['canonical_timeline']['snapshot']['metadata'].get('source_variant',{})
            if lineage.get('master_project_id')!=value['master_project_id'] or lineage.get('master_document_sha256')!=snapshot['master_document_sha256'] or lineage.get('request_fingerprint')!=value['request_fingerprint'] or lineage.get('profile')!=item['profile']:
                raise WorkflowError('SOURCE_VARIANT_CHILD_HISTORY_CHANGED')
        value.pop('request_key_sha256');return {**value,'schema_version':'native-source-variant-batch-v1','snapshot':snapshot,'result':result,'external_provider_calls':0}

    def create(self,project_id,payload,*,actor):
        request=payload.model_dump(mode='json',exclude={'request_key'});fingerprint=digest(request);key=digest(payload.request_key)
        with self.store.transaction() as con:
            prior=con.execute('SELECT * FROM native_source_variant_batches WHERE workspace_id=? AND master_project_id=? AND request_key_sha256=?',(self.workspace,project_id,key)).fetchone()
            if prior:
                if prior['request_fingerprint']!=fingerprint:raise WorkflowError('SOURCE_VARIANT_IDEMPOTENCY_CONFLICT')
                return self.read(prior,con),True
            parent=self.store.editable(con,project_id,payload.revision)
            if not is_auto_edit(parent['document']):raise WorkflowError('SOURCE_VARIANT_CANONICAL_SOURCE_TIMELINE_REQUIRED',400)
            _cas(parent,payload.expected_version);_,media=resolve_assets(SimpleNamespace(data_root=self.store.root),parent)
            available=catalog();profiles={item['profile_ref']:item for item in available['profiles']}
            if any(ref not in profiles for ref in payload.profile_refs):raise WorkflowError('SOURCE_VARIANT_PROFILE_UNKNOWN',400)
            if con.execute('SELECT COUNT(*) FROM native_source_variant_batches WHERE workspace_id=? AND master_project_id=?',(self.workspace,project_id)).fetchone()[0]>=50:
                raise WorkflowError('SOURCE_VARIANT_BATCH_LIMIT',400)
            stamp=now();children=[]
            for ref in payload.profile_refs:
                identifier=uuid.uuid5(uuid.NAMESPACE_URL,ALGORITHM+'/'+self.workspace+'/'+project_id+'/'+fingerprint+'/'+key+'/'+ref).hex
                document=draft_document(parent,identifier,profiles[ref],fingerprint,stamp,media)
                con.execute('INSERT INTO projects VALUES(?,?,?,?,?,?)',(identifier,1,json.dumps(document,ensure_ascii=False),None,stamp,stamp));self.store.version(con,identifier)
                self.store.event(con,identifier,'source_variant_created_unapproved',{'master_project_id':project_id,'master_revision':parent['revision'],'profile_ref':ref,'request_fingerprint':fingerprint,'provider_calls':0})
                children.append({'project_id':identifier,'name':document['name'],'profile':profiles[ref],'initial_document_sha256':digest(document),
                    'initial_timeline_sha256':document['canonical_timeline']['sha256'],'approval_inherited':False,'render_dispatched':False,'crop_needs_attention':True,
                    'asset_reuse':[{'asset_id':asset['id'],'sha256':asset['sha256']} for asset in project_assets(document)],
                    'analysis_reuse_count':len(document.get('auto_edit_analyses',[])),'frame_observation_reuse_count':len(document.get('media_frame_analyses',[])),
                    'fresh_provider_measurement':False})
            snapshot={'schema_version':'native-source-variant-snapshot-v1','workspace_id':self.workspace,'master_project_id':project_id,
                'master_revision':parent['revision'],'master_document_sha256':digest(parent['document']),'master_timeline_sha256':parent['document']['canonical_timeline']['sha256'],
                'request':request,'catalog':available,'provider_calls':0}
            result={'schema_version':ALGORITHM,'variants':children,'master_project_mutated':False,'external_provider_calls':0,'paid_operations':0,
                'render_intermediates_reused':False,'human_approval_required_per_variant':True,'publishing_enabled':False}
            identity='nsvb_'+uuid.uuid4().hex
            con.execute('INSERT INTO native_source_variant_batches VALUES(?,?,?,?,?,?,?,?,?,?,?)',(identity,self.workspace,project_id,key,fingerprint,digest(snapshot),json.dumps(snapshot,ensure_ascii=False),
                digest(result),json.dumps(result,ensure_ascii=False),actor,stamp))
            self.store.event(con,project_id,'source_variant_batch_created_unapproved',{'batch_id':identity,'request_fingerprint':fingerprint,'variants':len(children),'master_document_mutated':False})
            return self.read(con.execute('SELECT * FROM native_source_variant_batches WHERE batch_id=?',(identity,)).fetchone(),con),False

    def page(self,project_id,*,limit=25,cursor=None):
        if type(limit)is not int or not 1<=limit<=100:raise WorkflowError('SOURCE_VARIANT_PAGE_INVALID',400)
        after=None
        if cursor:
            try:
                if not isinstance(cursor,str) or len(cursor)>1000:raise ValueError()
                after=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if not isinstance(after,list) or len(after)!=4 or after[:2]!=[self.workspace,project_id] or datetime.fromisoformat(after[2]).tzinfo is None or not isinstance(after[3],str):raise ValueError()
            except (ValueError,TypeError):raise WorkflowError('SOURCE_VARIANT_CURSOR_INVALID',400) from None
        with self.store.transaction() as con:
            self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone());where='workspace_id=? AND master_project_id=?';params=[self.workspace,project_id]
            if after:where+=' AND (created_at<? OR (created_at=? AND batch_id<?))';params.extend([after[2],after[2],after[3]])
            rows=con.execute('SELECT * FROM native_source_variant_batches WHERE '+where+' ORDER BY created_at DESC,batch_id DESC LIMIT ?',(*params,limit+1)).fetchall()
            next_cursor=base64.urlsafe_b64encode(json.dumps([self.workspace,project_id,rows[limit-1]['created_at'],rows[limit-1]['batch_id']]).encode()).decode().rstrip('=') if len(rows)>limit else None
            return {'schema_version':'native-source-variant-page-v1','workspace_id':self.workspace,'master_project_id':project_id,'items':[self.read(row,con) for row in rows[:limit]],
                'next_cursor':next_cursor,'external_provider_calls':0}
