"""Issue private reference admissions from actual Native assets and current rights.

This prerequisite does not create generation jobs, attach assets, edit timelines,
verify licenses or authorize publishing. Authenticated bridge uploads use one
durable dispatch intent and exact metadata reconciliation after ambiguity.
"""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import asyncio,hashlib,io,json,re
from typing import Literal
import httpx
from pydantic import AwareDatetime,Field,StrictBool,StrictInt
from . import ingestion
from .backup import guard,io_path
from .contracts import WorkflowError,digest
from .generation_models import GenerationReference,NativeImageParameters,NativeVideoParameters
from .generation_registry import GenerationFactory
from .media import IMAGE_MAX_BYTES
from .rights import validate_document as validate_rights
from .rights_override import rights_sha,fixture
from .source_assets import canonical_assets
from app.models import StrictModel
from app.media_intelligence_models import ImageGenerationInput,VideoGenerationInput
from npd_comfyui_bridge.reference_models import ReferenceAdmission


class ReferenceSource(StrictModel):
    asset_id:str=Field(pattern=r'^[a-f0-9]{32}\.(jpg|png)$')
    asset_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    asset_record_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    rights_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    rights_receipt_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    rights_status:Literal['owned','licensed','verified','unknown']
    authorization_kind:Literal['registered_rights','explicit_owner_override']
    override_id:str|None=None
    override_sha256:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    override_expires_at:AwareDatetime|None=None
    mime_type:Literal['image/png','image/jpeg']
    size_bytes:StrictInt=Field(gt=0,le=IMAGE_MAX_BYTES)
    width:StrictInt=Field(gt=0,le=8192)
    height:StrictInt=Field(gt=0,le=8192)
    fixture:StrictBool
    full_local_decode_passed:Literal[True]=True


class ReferenceSnapshot(StrictModel):
    schema_version:Literal['native-generation-reference-snapshot-v1']='native-generation-reference-snapshot-v1'
    workspace_id:str=Field(min_length=1,max_length=100,pattern=r'^\S+$')
    project_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    revision:StrictInt=Field(ge=1)
    document_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    provider_configuration_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    provider_mode:Literal['official','fixture']
    parameters:dict
    fixture_acknowledged:StrictBool
    sources:list[ReferenceSource]=Field(max_length=11)
    created_at:AwareDatetime
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')


def parameters(value):
    try:return (NativeImageParameters if value.get('modality')=='image' else NativeVideoParameters).model_validate(value)
    except (ValueError,TypeError,AttributeError):raise WorkflowError('NATIVE_GENERATION_REFERENCE_SNAPSHOT_INVALID') from None


def selected_references(value):
    output=[];seen=set()
    for item in [*value.references,*([value.mask] if type(value) is NativeImageParameters and value.mask else [])]:
        if item.asset_id in seen:
            prior=next(ref for ref in output if ref.asset_id==item.asset_id)
            if prior!=item:raise WorkflowError('NATIVE_GENERATION_REFERENCE_SELECTION_INVALID',400)
        else:seen.add(item.asset_id);output.append(item)
    return output


def api_parameters(value,uris):
    """Only server-issued scoped URIs enter the provider-neutral request."""
    raw=value.model_dump(mode='json');raw.pop('modality');raw.pop('references');mask=raw.pop('mask',None)
    try:
        raw['reference_images']=[uris[ref.asset_id] for ref in value.references]
        if mask:raw['mask_reference']=uris[mask['asset_id']]
        return (ImageGenerationInput if type(value) is NativeImageParameters else VideoGenerationInput).model_validate(raw)
    except (ValueError,KeyError):raise WorkflowError('NATIVE_GENERATION_REFERENCE_MAPPING_INVALID') from None


class NativeGenerationReferences:
    def __init__(self,store,*,workspace_id='wsp_native_local',clock=lambda:datetime.now(timezone.utc)):
        if not isinstance(workspace_id,str) or not re.fullmatch(r'\S{1,100}',workspace_id):raise WorkflowError('NATIVE_GENERATION_REFERENCE_SCOPE_INVALID',400)
        self.store,self.workspace,self.clock=store,workspace_id,clock
        with store.transaction() as con:
            con.execute('CREATE TABLE IF NOT EXISTS native_generation_reference_admissions (workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,generation_id TEXT NOT NULL,asset_id TEXT NOT NULL,snapshot_json TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,admission_json TEXT NOT NULL,reference_id TEXT NOT NULL,state TEXT NOT NULL,metadata_json TEXT,metadata_sha256 TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(workspace_id,project_id,generation_id,asset_id))')

    def image(self,reference,asset):
        if asset.get('kind')!='image' or asset.get('id')!=reference.asset_id or asset.get('sha256')!=reference.asset_sha256:
            raise WorkflowError('NATIVE_GENERATION_REFERENCE_SOURCE_CHANGED')
        directory=guard(self.store.root/'assets',exists=True);path=guard(directory/reference.asset_id,exists=True)
        if path.parent!=directory:raise WorkflowError('NATIVE_GENERATION_REFERENCE_SOURCE_CHANGED')
        physical=io_path(path)
        if not physical.is_file() or not 1<=physical.stat().st_size<=IMAGE_MAX_BYTES:raise WorkflowError('NATIVE_GENERATION_REFERENCE_SOURCE_INVALID')
        with physical.open('rb') as handle:content=handle.read(IMAGE_MAX_BYTES+1)
        if not 1<=len(content)<=IMAGE_MAX_BYTES or hashlib.sha256(content).hexdigest()!=reference.asset_sha256:
            raise WorkflowError('NATIVE_GENERATION_REFERENCE_SOURCE_CHANGED')
        mime='image/png' if reference.asset_id.endswith('.png') else 'image/jpeg'
        if not (content.startswith(b'\x89PNG\r\n\x1a\n') if mime=='image/png' else content.startswith(b'\xff\xd8\xff')):
            raise WorkflowError('NATIVE_GENERATION_REFERENCE_MAGIC_INVALID')
        try:
            from PIL import Image
            with Image.open(io.BytesIO(content)) as image:
                if (image.format!=('PNG' if mime=='image/png' else 'JPEG') or not 1<=image.width<=8192 or not 1<=image.height<=8192
                    or image.width*image.height>16*1024*1024 or getattr(image,'n_frames',1)!=1):raise ValueError()
                image.load();width,height=image.size
        except Exception:raise WorkflowError('NATIVE_GENERATION_REFERENCE_DECODE_INVALID') from None
        if (asset.get('bytes')!=len(content) or asset.get('width')!=width or asset.get('height')!=height):
            raise WorkflowError('NATIVE_GENERATION_REFERENCE_METADATA_CHANGED')
        return content,mime,width,height

    def source(self,project,reference,mode):
        validate_rights(project['document'],project_id=project['id'],workspace_id=self.workspace)
        matches=[asset for asset in canonical_assets(project['document']) if asset.get('id')==reference.asset_id]
        if len(matches)!=1:raise WorkflowError('NATIVE_GENERATION_REFERENCE_NOT_IN_PROJECT')
        asset=matches[0];content,mime,width,height=self.image(reference,asset)
        raw_rights=asset.get('rights_status','unknown');is_fixture=bool(fixture(asset))
        if raw_rights not in {'owned','licensed','verified','unknown'}:raise WorkflowError('NATIVE_GENERATION_REFERENCE_RIGHTS_BLOCKED')
        if is_fixture and mode!='fixture':raise WorkflowError('NATIVE_GENERATION_REFERENCE_FIXTURE_BLOCKED')
        authority=getattr(self.store,'rights_overrides',None);override=None
        if authority is not None:
            if authority.workspace!=self.workspace:raise WorkflowError('NATIVE_GENERATION_REFERENCE_RIGHTS_SCOPE_INVALID')
            override=authority.active(project['document'],project['id'],asset)
        if raw_rights=='unknown' or asset.get('rights_review_required') is True:
            if override is None:raise WorkflowError('NATIVE_GENERATION_REFERENCE_RIGHTS_REVIEW_REQUIRED')
            authorization='explicit_owner_override'
        else:authorization='registered_rights';override=None
        evidence={'schema_version':'native-generation-reference-rights-v1','workspace_id':self.workspace,'project_id':project['id'],
            'asset_id':reference.asset_id,'asset_sha256':reference.asset_sha256,'asset_record_sha256':digest(asset),
            'rights_sha256':rights_sha(asset),'authorization_kind':authorization,'override':override,
            'rights_independently_verified':False,'publishing_authorized':False}
        value=ReferenceSource(asset_id=reference.asset_id,asset_sha256=reference.asset_sha256,asset_record_sha256=digest(asset),
            rights_sha256=rights_sha(asset),rights_receipt_sha256=digest(evidence),rights_status=raw_rights,authorization_kind=authorization,
            override_id=override['override_id'] if override else None,override_sha256=override['sha256'] if override else None,
            override_expires_at=override['expires_at'] if override else None,mime_type=mime,size_bytes=len(content),width=width,height=height,fixture=is_fixture)
        return value,content

    def freeze(self,project_id,revision,value,factory,*,fixture_acknowledged=False):
        if type(value) not in (NativeImageParameters,NativeVideoParameters) or type(factory) is not GenerationFactory:
            raise WorkflowError('NATIVE_GENERATION_REFERENCE_REQUEST_INVALID',400)
        if type(fixture_acknowledged) is not bool or factory.mode=='fixture' and not fixture_acknowledged:
            raise WorkflowError('NATIVE_GENERATION_REFERENCE_FIXTURE_ACK_REQUIRED',400)
        chosen=selected_references(value)
        # The placeholder URIs are used only for static workflow selection; no
        # provider is constructed or called until immutable admissions exist.
        provider_input=api_parameters(value,{ref.asset_id:'native-owned-selection://'+ref.asset_id for ref in chosen})
        selection=factory.selection(value.modality,provider_input)
        if selection['status']!='CONFIGURED':raise WorkflowError('NATIVE_GENERATION_NOT_CONFIGURED',503)
        with self.store.transaction() as con:
            project=self.store.editable(con,project_id,revision)
            sources=[self.source(project,ref,factory.mode)[0].model_dump(mode='json') for ref in chosen]
            raw={'schema_version':'native-generation-reference-snapshot-v1','workspace_id':self.workspace,'project_id':project_id,
                'revision':revision,'document_sha256':digest(project['document']),'provider_configuration_sha256':factory.sha256,
                'provider_mode':factory.mode,'parameters':value.model_dump(mode='json'),'fixture_acknowledged':fixture_acknowledged,
                'sources':sources,'created_at':self.clock().isoformat()}
            normalized=ReferenceSnapshot.model_validate({**raw,'sha256':'0'*64}).model_dump(mode='json')
            normalized['sha256']=digest({k:v for k,v in normalized.items() if k!='sha256'})
            return normalized

    def check(self,snapshot,factory,con):
        try:typed=ReferenceSnapshot.model_validate(snapshot);value=parameters(typed.parameters)
        except (ValueError,TypeError):raise WorkflowError('NATIVE_GENERATION_REFERENCE_SNAPSHOT_INVALID') from None
        if (typed.sha256!=digest({k:v for k,v in snapshot.items() if k!='sha256'}) or typed.workspace_id!=self.workspace
            or type(factory) is not GenerationFactory or typed.provider_configuration_sha256!=factory.sha256 or typed.provider_mode!=factory.mode
            or factory.mode=='fixture' and not typed.fixture_acknowledged):raise WorkflowError('NATIVE_GENERATION_REFERENCE_SNAPSHOT_CHANGED')
        project=self.store.editable(con,typed.project_id,typed.revision)
        if digest(project['document'])!=typed.document_sha256:raise WorkflowError('NATIVE_GENERATION_REFERENCE_PROJECT_CHANGED')
        refs=selected_references(value);sources=[];contents={}
        for ref in refs:
            source,content=self.source(project,ref,factory.mode);sources.append(source);contents[ref.asset_id]=content
        if sources!=typed.sources:raise WorkflowError('NATIVE_GENERATION_REFERENCE_RIGHTS_CHANGED')
        candidate=api_parameters(value,{ref.asset_id:'native-owned-selection://'+ref.asset_id for ref in refs})
        if factory.selection(value.modality,candidate)['status']!='CONFIGURED':raise WorkflowError('NATIVE_GENERATION_NOT_CONFIGURED',503)
        return typed,value,contents

    def issue(self,generation_id,snapshot,factory):
        if not isinstance(generation_id,str) or not re.fullmatch(r'[a-f0-9]{32}',generation_id):raise WorkflowError('NATIVE_GENERATION_REFERENCE_JOB_INVALID',400)
        with self.store.transaction() as con:
            typed,_,_=self.check(snapshot,factory,con);current=self.clock()
            existing=con.execute('SELECT * FROM native_generation_reference_admissions WHERE workspace_id=? AND project_id=? AND generation_id=? ORDER BY asset_id',
                (self.workspace,typed.project_id,generation_id)).fetchall()
            if existing:
                if len(existing)!=len(typed.sources) or {r['asset_id'] for r in existing}!={r.asset_id for r in typed.sources}:raise WorkflowError('NATIVE_GENERATION_REFERENCE_JOURNAL_INVALID')
                return [self.read(row,snapshot)['admission'] for row in existing]
            if con.execute('SELECT COUNT(*) FROM native_generation_reference_admissions').fetchone()[0]+len(typed.sources)>5000:
                raise WorkflowError('NATIVE_GENERATION_REFERENCE_JOURNAL_LIMIT')
            admissions=[]
            for source in typed.sources:
                expires=min(current+timedelta(minutes=30),source.override_expires_at) if source.override_expires_at else current+timedelta(minutes=30)
                if expires<=current:raise WorkflowError('NATIVE_GENERATION_REFERENCE_ADMISSION_EXPIRED')
                admission=ReferenceAdmission(workspace_id=self.workspace,project_id=typed.project_id,asset_id=source.asset_id,
                    content_sha256=source.asset_sha256,mime_type=source.mime_type,rights_status=source.rights_status,
                    authorization_kind=source.authorization_kind,rights_receipt_sha256=source.rights_receipt_sha256,
                    issued_at=current,expires_at=expires,fixture=source.fixture).model_dump(mode='json')
                con.execute('INSERT INTO native_generation_reference_admissions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (self.workspace,typed.project_id,generation_id,source.asset_id,json.dumps(snapshot),typed.sha256,json.dumps(admission),digest(admission),
                        'reserved',None,None,current.isoformat(),current.isoformat()))
                admissions.append(admission)
            return admissions

    def read(self,row,snapshot):
        try:
            saved=json.loads(row['snapshot_json']);typed=ReferenceSnapshot.model_validate(saved);admission=ReferenceAdmission.model_validate_json(row['admission_json'])
            source=next(s for s in typed.sources if s.asset_id==row['asset_id'])
            if (saved!=snapshot or row['snapshot_sha256']!=typed.sha256 or typed.sha256!=digest({k:v for k,v in saved.items() if k!='sha256'})
                or row['workspace_id']!=self.workspace or typed.workspace_id!=self.workspace or admission.workspace_id!=self.workspace
                or row['project_id']!=typed.project_id or admission.project_id!=typed.project_id or admission.asset_id!=source.asset_id
                or admission.content_sha256!=source.asset_sha256 or admission.mime_type!=source.mime_type or admission.rights_status!=source.rights_status
                or admission.authorization_kind!=source.authorization_kind or admission.rights_receipt_sha256!=source.rights_receipt_sha256
                or admission.fixture!=source.fixture or source.override_expires_at is not None and admission.expires_at>source.override_expires_at
                or digest(admission.model_dump(mode='json'))!=row['reference_id'] or row['state'] not in {'reserved','dispatching','confirmed'}):raise ValueError()
            if admission.issued_at>self.clock()+timedelta(seconds=30) or admission.expires_at<=self.clock():raise WorkflowError('NATIVE_GENERATION_REFERENCE_ADMISSION_EXPIRED')
            metadata=json.loads(row['metadata_json']) if row['metadata_json'] else None
            if row['state']=='confirmed':
                self.metadata(metadata,admission.model_dump(mode='json'),row['reference_id'],source)
                if digest(metadata)!=row['metadata_sha256']:raise ValueError()
            elif metadata is not None or row['metadata_sha256'] is not None:raise ValueError()
            return {'admission':admission.model_dump(mode='json'),'reference_id':row['reference_id'],'source':source,'metadata':metadata}
        except WorkflowError:raise
        except (ValueError,TypeError,KeyError,StopIteration):raise WorkflowError('NATIVE_GENERATION_REFERENCE_JOURNAL_INVALID') from None

    def metadata(self,value,admission,identity,source):
        if (not isinstance(value,dict) or set(value)!={'reference_id','source_reference','filename','size_bytes','admission','media','rights_independently_verified','publishing_authorized','created_at'}
            or value.get('reference_id')!=identity or value.get('source_reference')!='vf-reference://'+identity or value.get('admission')!=admission
            or value.get('filename')!=('reference.png' if source.mime_type=='image/png' else 'reference.jpg')
            or type(value.get('size_bytes')) is not int or value['size_bytes']!=source.size_bytes
            or value.get('rights_independently_verified') is not False or value.get('publishing_authorized') is not False
            or not isinstance(value.get('media'),dict) or value['media'].get('full_decode_passed') is not True
            or value['media'].get('width')!=source.width or value['media'].get('height')!=source.height or value['media'].get('qc_passed') is not False):
            raise WorkflowError('NATIVE_GENERATION_REFERENCE_BRIDGE_BINDING_INVALID')
        return value

    async def request(self,client,method,path,**options):
        try:
            async with asyncio.timeout(35),client.stream(method,path,**options) as response:
                if method=='GET' and response.status_code==404:return None
                if response.status_code not in (200,201):raise WorkflowError('NATIVE_GENERATION_REFERENCE_BRIDGE_REJECTED')
                content=bytearray()
                async for chunk in response.aiter_bytes():
                    if len(chunk)>65536-len(content):raise WorkflowError('NATIVE_GENERATION_REFERENCE_BRIDGE_RESULT_INVALID')
                    content.extend(chunk)
                def pairs(items):
                    result={}
                    for key,value in items:
                        if key in result:raise ValueError()
                        result[key]=value
                    return result
                return json.loads(bytes(content),object_pairs_hook=pairs)
        except WorkflowError:raise
        except (ValueError,TypeError):raise WorkflowError('NATIVE_GENERATION_REFERENCE_BRIDGE_RESULT_INVALID') from None
        except Exception:raise WorkflowError('NATIVE_GENERATION_REFERENCE_BRIDGE_OUTCOME_UNKNOWN') from None

    async def stage(self,generation_id,snapshot,factory):
        self.issue(generation_id,snapshot,factory);output={}
        with self.store.transaction() as con:
            typed,_,_=self.check(snapshot,factory,con)
            rows=con.execute('SELECT * FROM native_generation_reference_admissions WHERE workspace_id=? AND project_id=? AND generation_id=? ORDER BY asset_id',
                (self.workspace,typed.project_id,generation_id)).fetchall()
            for row in rows:self.read(row,snapshot)
        headers={'Authorization':'Bearer '+factory.credential.service_token,'X-VF-Workspace-Id':self.workspace,'X-VF-Project-Id':typed.project_id}
        async with httpx.AsyncClient(base_url=factory.credential.bridge_url,headers=headers,transport=factory.transport,timeout=30,follow_redirects=False,trust_env=False) as client:
            for row in rows:
                binding=self.read(row,snapshot);identity=binding['reference_id'];admission=binding['admission'];source=binding['source']
                if source.fixture and factory.mode!='fixture':raise WorkflowError('NATIVE_GENERATION_REFERENCE_FIXTURE_BLOCKED')
                result=await self.request(client,'GET','/v1/references/'+identity)
                if result is None:
                    with self.store.transaction() as con:
                        _,_,contents=self.check(snapshot,factory,con)
                        current=con.execute('SELECT * FROM native_generation_reference_admissions WHERE workspace_id=? AND project_id=? AND generation_id=? AND asset_id=?',
                            (self.workspace,typed.project_id,generation_id,source.asset_id)).fetchone();self.read(current,snapshot)
                        if current['state']!='reserved':raise WorkflowError('NATIVE_GENERATION_REFERENCE_RECOVERY_REQUIRED')
                        con.execute("UPDATE native_generation_reference_admissions SET state='dispatching',updated_at=? WHERE workspace_id=? AND project_id=? AND generation_id=? AND asset_id=? AND state='reserved'",
                            (self.clock().isoformat(),self.workspace,typed.project_id,generation_id,source.asset_id))
                    try:
                        result=await self.request(client,'POST','/v1/references',content=contents[source.asset_id],
                            headers={'Content-Type':source.mime_type,'X-VF-Reference-Admission':json.dumps(admission,separators=(',',':'))})
                    except WorkflowError:
                        result=await self.request(client,'GET','/v1/references/'+identity)
                        if result is None:raise WorkflowError('NATIVE_GENERATION_REFERENCE_RECOVERY_REQUIRED') from None
                self.metadata(result,admission,identity,source)
                with self.store.transaction() as con:
                    self.check(snapshot,factory,con)
                    current=con.execute('SELECT * FROM native_generation_reference_admissions WHERE workspace_id=? AND project_id=? AND generation_id=? AND asset_id=?',
                        (self.workspace,typed.project_id,generation_id,source.asset_id)).fetchone();prior=self.read(current,snapshot)
                    if prior['metadata'] is not None and prior['metadata']!=result:raise WorkflowError('NATIVE_GENERATION_REFERENCE_BRIDGE_BINDING_INVALID')
                    con.execute("UPDATE native_generation_reference_admissions SET state='confirmed',metadata_json=?,metadata_sha256=?,updated_at=? WHERE workspace_id=? AND project_id=? AND generation_id=? AND asset_id=?",
                        (json.dumps(result),digest(result),self.clock().isoformat(),self.workspace,typed.project_id,generation_id,source.asset_id))
                output[source.asset_id]='vf-reference://'+identity
        return api_parameters(parameters(snapshot['parameters']),output)
