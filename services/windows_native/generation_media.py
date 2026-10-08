"""Trusted worker intake of job-bound registered bytes into owned Native media.

No provider is called, no job is self-accepted, and no project/timeline is edited.
Original and normalized assets are bound in an immutable durable stage receipt.
"""
import hashlib,json,math,re,uuid
from copy import deepcopy
from .backup import guard,io_path
from .contracts import WorkflowError,digest,file_sha
from .media import ingest_media,discard_media,IMAGE_MAX_BYTES,VIDEO_MAX_BYTES
from .store import now
from app.media_intelligence_models import ImageGenerationInput,VideoGenerationInput
from app.media_generation_routes import generation_envelope,workflow_routes
from app.media_intelligence_providers import ProviderMaterializedMedia
from npd_comfyui_bridge.binary_artifacts import ArtifactProvenance


class NativeGenerationMedia:
    def __init__(self,queue,config):
        if guard(config.data_root)!=guard(queue.store.root):raise WorkflowError('NATIVE_GENERATION_MEDIA_ROOT_MISMATCH',400)
        self.queue,self.store,self.config=queue,queue.store,config
        with self.store.transaction() as con:
            con.execute('CREATE TABLE IF NOT EXISTS native_generation_media (generation_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,request_fingerprint TEXT NOT NULL,receipt_json TEXT NOT NULL,receipt_sha256 TEXT NOT NULL,created_at TEXT NOT NULL)')

    def workflow_evidence(self,value):
        selected=value['snapshot']['selection'];factory=self.queue.factory
        if factory is None:raise WorkflowError('NATIVE_GENERATION_MEDIA_WORKFLOW_INVALID')
        definition=factory.catalog['definitions'][selected['workflow_id']]
        graph_sha=file_sha(guard(factory.manifest_path.parent/definition.graph_file,exists=True))
        evidence={'definition':definition.model_dump(mode='json',exclude_none=True),'graph_sha256':graph_sha}
        if digest(evidence)!=selected['workflow_sha256']:raise WorkflowError('NATIVE_GENERATION_MEDIA_WORKFLOW_INVALID')
        return evidence

    def proof(self,value,provenance,proof,workflow_evidence,*,sha,size,mime,width,height,duration):
        selected=value['snapshot']['selection'];modality=value['snapshot']['request']['parameters']['modality']
        payload=(ImageGenerationInput if modality=='image' else VideoGenerationInput).model_validate(value['provider_input'])
        workflow,operation,inputs=generation_envelope(modality,payload,workflow_routes(modality,'npd-text-to-image-v1' if modality=='image' else 'npd-video-generation-v1'))
        try:
            registered=ArtifactProvenance.model_validate(proof['provenance']);definition=workflow_evidence['definition'];media=proof['media']
            refs=value['snapshot']['references']['sources'];by_id={r['asset_id']:r['asset_sha256'] for r in refs}
            parameters=value['snapshot']['request']['parameters'];ids=[r['asset_id'] for r in parameters['references']]
            if parameters.get('mask'):ids.append(parameters['mask']['asset_id'])
            if (not re.fullmatch(r'[a-f0-9]{64}',sha) or type(size) is not int or not 1<=size<=(IMAGE_MAX_BYTES if modality=='image' else VIDEO_MAX_BYTES)
                or mime not in ({'image/png','image/jpeg'} if modality=='image' else {'video/mp4'})
                or type(width) is not int or type(height) is not int or not 1<=width<=8192 or not 1<=height<=8192 or width*height>16*1024*1024
                or digest(workflow_evidence)!=selected['workflow_sha256'] or definition['workflow_id']!=workflow or definition['version']!=selected['workflow_version']
                or registered.graph_sha256!=workflow_evidence['graph_sha256'] or registered.model!=(', '.join(definition.get('required_model_identifiers',[]))[:200] or 'unspecified-reviewed-model')
                or registered.source_reference_sha256!=[by_id[i] for i in ids]
                or registered.workflow_id!=workflow or registered.workflow_version!=selected['workflow_version'] or registered.inputs_sha256!=digest(inputs)
                or registered.prompt_sha256!=hashlib.sha256(payload.prompt.encode()).hexdigest() or registered.seed!=payload.seed
                or proof.get('artifact_id')!=digest([self.queue.workspace,value['provider_job_id'],sha]) or proof.get('checksum_sha256')!=sha
                or proof.get('workspace_id')!=self.queue.workspace or proof.get('job_id')!=value['provider_job_id'] or proof.get('size_bytes')!=size or proof.get('mime_type')!=mime
                or proof.get('rights_status')!='unknown' or proof.get('production_eligible') is not False or type(proof.get('fixture')) is not bool
                or proof['fixture']!=(selected['mode']=='fixture') or provenance.get('fixture') is not proof['fixture'] or provenance.get('binary_artifact_registered') is not True
                or provenance.get('registered_artifact')!=proof or provenance.get('provider')!=selected['provider'] or provenance.get('model')!='workflow:'+workflow
                or provenance.get('workflow')!=workflow or provenance.get('workflow_version')!=selected['workflow_version'] or provenance.get('bridge_job_id')!=value['provider_job_id']
                or provenance.get('operation')!=operation or type(provenance.get('seed')) is not int or provenance['seed']!=payload.seed
                or media.get('full_decode_passed') is not True or media.get('qc_passed') is not False or type(media.get('width')) is not int or type(media.get('height')) is not int
                or media['width']!=width or media['height']!=height or media.get('duration_seconds')!=duration):raise ValueError()
            if modality=='image':
                if duration is not None or media.get('fps') is not None or media.get('decoded_video_frames')!=1 or media.get('audio_streams')!=0 or media.get('video_codec')!=('png' if mime=='image/png' else 'mjpeg'):raise ValueError()
            elif (type(duration) not in (int,float) or not math.isfinite(duration) or not 0<duration<=600
                or type(media.get('fps')) not in (int,float) or not math.isfinite(media['fps']) or not 1<=media['fps']<=120
                or type(media.get('decoded_video_frames')) is not int or not 1<=media['decoded_video_frames']<=72000
                or type(media.get('audio_streams')) is not int or not 0<=media['audio_streams']<=3):raise ValueError()
        except (ValueError,TypeError,KeyError,AttributeError):raise WorkflowError('NATIVE_GENERATION_MEDIA_BINDING_INVALID') from None

    def binding(self,value,output):
        if type(output) is not ProviderMaterializedMedia:raise WorkflowError('NATIVE_GENERATION_MEDIA_RESULT_INVALID')
        selected=value['snapshot']['selection'];mode=selected['mode'];modality=value['snapshot']['request']['parameters']['modality']
        proof=output.generation_provenance.get('registered_artifact') if isinstance(output.generation_provenance,dict) else None
        raw=value['provider_input'];payload=(ImageGenerationInput if modality=='image' else VideoGenerationInput).model_validate(raw)
        workflow,operation,inputs=generation_envelope(modality,payload,workflow_routes(modality,'npd-text-to-image-v1' if modality=='image' else 'npd-video-generation-v1'))
        if (not value['dispatch_started'] or value['provider_job_id']!=output.provider_job_id or value['observation'] is None or value['observation']['status']!='succeeded'
            or output.source_type!='ai_generated' or output.rights_status!='unknown' or output.production_eligible is not False or output.real_provider_tested is not False
            or output.actual_cost_vnd is not None or output.estimated_cost_vnd is not None or output.paid is not False or output.external_call is not True
            or output.license!='provider-terms-review-required' or type(output.width) is not int or type(output.height) is not int or not isinstance(output.payload,bytes)
            or not 1<=len(output.payload)<=(IMAGE_MAX_BYTES if modality=='image' else VIDEO_MAX_BYTES)
            or output.content_type not in ({'image/png','image/jpeg'} if modality=='image' else {'video/mp4'})
            or not isinstance(proof,dict) or not isinstance(proof.get('provenance'),dict) or not isinstance(proof.get('media'),dict)):
            raise WorkflowError('NATIVE_GENERATION_MEDIA_RESULT_INVALID')
        binary_sha=hashlib.sha256(output.payload).hexdigest();provenance=output.generation_provenance
        artifact_id=digest([self.queue.workspace,output.provider_job_id,binary_sha])
        if (output.source_reference!='vf-artifact://'+artifact_id or proof.get('artifact_id')!=artifact_id or proof.get('checksum_sha256')!=binary_sha
            or proof.get('workspace_id')!=self.queue.workspace or proof.get('job_id')!=output.provider_job_id or proof.get('size_bytes')!=len(output.payload)
            or proof.get('mime_type')!=output.content_type or proof.get('rights_status')!='unknown' or proof.get('production_eligible') is not False
            or type(proof.get('fixture')) is not bool or proof['fixture']!=(mode=='fixture')
            or provenance.get('fixture')!=proof['fixture'] or provenance.get('binary_artifact_registered') is not True
            or provenance.get('provider')!=selected['provider'] or provenance.get('workflow')!=workflow or provenance.get('workflow_version')!=selected['workflow_version']
            or provenance.get('bridge_job_id')!=output.provider_job_id or provenance.get('operation')!=operation or provenance.get('seed')!=payload.seed
            or proof['provenance'].get('workflow_id')!=workflow or proof['provenance'].get('workflow_version')!=selected['workflow_version']
            or proof['provenance'].get('inputs_sha256')!=digest(inputs) or proof['provenance'].get('prompt_sha256')!=hashlib.sha256(payload.prompt.encode()).hexdigest()
            or proof['provenance'].get('seed')!=payload.seed or proof['provenance'].get('estimated_cost_vnd') is not None or proof['provenance'].get('actual_cost_vnd') is not None
            or proof['media'].get('full_decode_passed') is not True or proof['media'].get('qc_passed') is not False
            or proof['media'].get('width')!=output.width or proof['media'].get('height')!=output.height):raise WorkflowError('NATIVE_GENERATION_MEDIA_BINDING_INVALID')
        workflow_evidence=self.workflow_evidence(value)
        self.proof(value,provenance,proof,workflow_evidence,sha=binary_sha,size=len(output.payload),mime=output.content_type,width=output.width,height=output.height,duration=output.duration_seconds)
        return binary_sha,deepcopy(proof),workflow_evidence

    def read(self,con,project,identity,*,physical=True):
        parent=self.queue.read(self.queue.row(con,project,identity))
        row=con.execute('SELECT * FROM native_generation_media WHERE generation_id=? AND workspace_id=? AND project_id=?',(identity,self.queue.workspace,project)).fetchone()
        if row is None:raise WorkflowError('NATIVE_GENERATION_MEDIA_NOT_READY',404)
        try:
            receipt=json.loads(row['receipt_json']);asset=receipt['asset'];proof=receipt['registered_bridge_artifact'];selected=parent['snapshot']['selection'];sha=receipt['provider_payload_sha256']
            if (digest(receipt)!=row['receipt_sha256'] or row['request_fingerprint']!=parent['request_fingerprint']
                or receipt.get('schema_version')!='native-generation-media-v1' or receipt.get('workspace_id')!=self.queue.workspace or receipt.get('project_id')!=project
                or receipt.get('generation_id')!=identity or receipt.get('request_fingerprint')!=parent['request_fingerprint']
                or receipt.get('provider_job_id')!=parent['provider_job_id'] or receipt.get('provider_input_sha256')!=digest(parent['provider_input'])
                or receipt.get('actual_cost_vnd') is not None or receipt.get('rights_independently_verified') is not False
                or receipt.get('canonical_timeline_mutated') is not False or receipt.get('automatic_attachment') is not False
                or receipt.get('full_native_media_validation_passed') is not True or receipt.get('real_provider_tested') is not False
                or receipt.get('asset_record_sha256')!=digest(asset)
                or not re.fullmatch(r'[a-f0-9]{32}\.(jpg|mp4)',asset['id']) or not re.fullmatch(r'[a-f0-9]{32}\.(png|jpg|mp4)',asset['original_id'])
                or asset['id'].split('.')[0]!=asset['original_id'].split('.')[0] or asset.get('source_type')!='ai_generated' or asset.get('rights_status')!='unknown'
                or asset.get('thumbnail_id')!=asset['id'].split('.')[0]+'.thumb.jpg'
                or asset.get('license')!='provider-terms-review-required' or asset.get('provider')!=selected['provider'] or asset.get('production_eligible') is not False
                or asset.get('needs_attention') is not True or asset.get('explicit_fixture')!=(selected['mode']=='fixture')
                or asset.get('independent_rights_verification') is not False or asset.get('kind')!=parent['snapshot']['request']['parameters']['modality']
                or asset.get('source')!=('explicit-generation-fixture' if selected['mode']=='fixture' else 'comfyui-registered-generation')
                or asset.get('provider_asset_id')!=parent['provider_job_id']
                or asset.get('source_sha256')!=sha or proof.get('checksum_sha256')!=sha or proof.get('job_id')!=parent['provider_job_id']
                or proof.get('workspace_id')!=self.queue.workspace or proof.get('artifact_id')!=digest([self.queue.workspace,parent['provider_job_id'],sha])
                or asset.get('source_reference')!='vf-artifact://'+proof['artifact_id'] or proof.get('fixture')!=(selected['mode']=='fixture')
                or proof.get('rights_status')!='unknown' or proof.get('production_eligible') is not False or proof['media'].get('full_decode_passed') is not True
                or asset.get('generation_provenance',{}).get('native_generation_id')!=identity or asset['generation_provenance'].get('fixture')!=(selected['mode']=='fixture')):
                raise ValueError()
            provenance=asset['generation_provenance']
            if (provenance.get('native_workspace_id')!=self.queue.workspace or provenance.get('native_project_id')!=project
                or provenance.get('native_request_fingerprint')!=parent['request_fingerprint'] or provenance.get('native_provider_input_sha256')!=digest(parent['provider_input'])):raise ValueError()
            self.proof(parent,provenance,proof,receipt['workflow_evidence'],sha=sha,size=asset['source_bytes'],mime=asset['source_mime'],
                width=asset['width'],height=asset['height'],duration=asset.get('duration_seconds'))
            expected_original={ 'image/png':'.png','image/jpeg':'.jpg','video/mp4':'.mp4'}[asset['source_mime']]
            if not asset['original_id'].endswith(expected_original) or not asset['id'].endswith('.jpg' if asset['kind']=='image' else '.mp4'):raise ValueError()
            if physical:
                for directory,key,checksum,size in [('assets','id','sha256','bytes'),('originals','original_id','source_sha256','source_bytes')]:
                    path=guard(self.store.root/directory/asset[key],exists=True)
                    if not io_path(path).is_file() or file_sha(io_path(path))!=asset[checksum] or io_path(path).stat().st_size!=asset[size]:raise ValueError()
                thumbnail=guard(self.store.root/'assets'/asset['thumbnail_id'],exists=True)
                if file_sha(io_path(thumbnail))!=receipt['thumbnail_sha256']:raise ValueError()
        except (ValueError,TypeError,KeyError):raise WorkflowError('NATIVE_GENERATION_MEDIA_RECEIPT_INVALID') from None
        return receipt

    def get(self,project,identity):
        with self.store.transaction() as con:return self.read(con,project,identity)

    def register(self,claim,output):
        with self.store.transaction() as con:
            row=self.queue.fenced(con,claim);value=self.queue.read(row);binary_sha,proof,workflow_evidence=self.binding(value,output)
            existing=con.execute('SELECT 1 FROM native_generation_media WHERE generation_id=?',(row['generation_id'],)).fetchone()
            if existing:
                receipt=self.read(con,row['project_id'],row['generation_id'])
                if receipt['provider_payload_sha256']!=binary_sha or receipt['registered_bridge_artifact']!=proof:raise WorkflowError('NATIVE_GENERATION_MEDIA_REPLAY_CONFLICT')
                return receipt
        folder=guard(self.store.root/'generation-work'/claim['generation_id']);folder.mkdir(parents=True,exist_ok=True)
        path=guard(folder/(claim['claim_id']+'-'+uuid.uuid4().hex+'.media'));asset=None;committed=False
        try:
            with io_path(path).open('xb') as handle:handle.write(output.payload)
            for directory in ['assets','originals']:guard(self.store.root/directory)
            asset=ingest_media(self.config,io_path(path),output.content_type,output.filename,rights_confirmed=True,illustration=True)
            if (asset['source_sha256']!=binary_sha or asset['source_bytes']!=len(output.payload) or asset['width']!=output.width or asset['height']!=output.height):
                raise WorkflowError('NATIVE_GENERATION_MEDIA_LOCAL_METADATA_CHANGED')
            if asset['kind']=='video' and (abs(asset['duration_seconds']-output.duration_seconds)>.05
                or asset.get('fps') is None or abs(asset['fps']-proof['media']['fps'])>.01
                or asset['has_audio']!=(proof['media']['audio_streams']>0)):
                raise WorkflowError('NATIVE_GENERATION_MEDIA_LOCAL_METADATA_CHANGED')
            asset.update(source_type='ai_generated',rights_status='unknown',license='provider-terms-review-required',provider=value['snapshot']['selection']['provider'],
                source='explicit-generation-fixture' if value['snapshot']['selection']['mode']=='fixture' else 'comfyui-registered-generation',
                source_reference=output.source_reference,provider_asset_id=output.provider_job_id,production_eligible=False,needs_attention=True,independent_rights_verification=False,
                explicit_fixture=value['snapshot']['selection']['mode']=='fixture',generation_provenance={**deepcopy(output.generation_provenance),
                    'native_generation_id':claim['generation_id'],'native_workspace_id':self.queue.workspace,'native_project_id':claim['project_id'],
                    'native_request_fingerprint':value['request_fingerprint'],'native_provider_input_sha256':digest(value['provider_input'])})
            receipt={'schema_version':'native-generation-media-v1','generation_id':claim['generation_id'],'workspace_id':self.queue.workspace,'project_id':claim['project_id'],
                'request_fingerprint':value['request_fingerprint'],'provider_job_id':output.provider_job_id,'provider_input_sha256':digest(value['provider_input']),
                'provider_payload_sha256':binary_sha,'registered_bridge_artifact':proof,'asset':asset,
                'workflow_evidence':workflow_evidence,'asset_record_sha256':digest(asset),
                'thumbnail_sha256':file_sha(io_path(guard(self.store.root/'assets'/asset['thumbnail_id'],exists=True))),
                'actual_cost_vnd':None,'rights_independently_verified':False,
                'canonical_timeline_mutated':False,'automatic_attachment':False,'full_native_media_validation_passed':True,'real_provider_tested':False,'created_at':now()}
            with self.store.transaction() as con:
                current=self.queue.fenced(con,claim);self.binding(self.queue.read(current),output)
                existing=con.execute('SELECT 1 FROM native_generation_media WHERE generation_id=?',(claim['generation_id'],)).fetchone()
                if existing:
                    saved=self.read(con,claim['project_id'],claim['generation_id'])
                    if saved['provider_payload_sha256']!=binary_sha or saved['registered_bridge_artifact']!=proof:raise WorkflowError('NATIVE_GENERATION_MEDIA_REPLAY_CONFLICT')
                    return saved
                con.execute('INSERT INTO native_generation_media VALUES(?,?,?,?,?,?,?)',(claim['generation_id'],self.queue.workspace,claim['project_id'],value['request_fingerprint'],json.dumps(receipt),digest(receipt),now()))
                self.read(con,claim['project_id'],claim['generation_id']);self.queue.event(con,current,'generation.media.staged','native-generation-worker',
                    asset_id=asset['id'],asset_sha256=asset['sha256'],provider_payload_sha256=binary_sha,rights_status='unknown',production_eligible=False)
                committed=True;return receipt
        finally:
            io_path(path).unlink(missing_ok=True)
            if asset is not None and not committed:
                for directory,key in [('assets','id'),('assets','thumbnail_id'),('originals','original_id')]:guard(self.store.root/directory/asset[key])
                discard_media(self.config,asset)
