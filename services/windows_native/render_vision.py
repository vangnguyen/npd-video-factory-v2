"""One-use, finite Owner authority and original journal for rendered-frame QC.

Provider predictions remain advisory. They neither replace hard media QC nor
approve the final video, timeline, publication or production deployment.
"""
import asyncio,base64,hashlib,json,re,uuid
from datetime import datetime,timedelta,timezone
from decimal import Decimal,ROUND_CEILING
from app.human_identity import HumanPrincipal,HumanAuthVerifier
from app.openai_vision_provider import VisionResponseObservation
from app.auto_edit_models import MediaMetadata
from app.vision_logic import normalize_frames,rank_best_frames
from app.vision_models import VisionFrameRead
from .backup import guard
from .contracts import WorkflowError,digest,file_sha
from .costs import CostLedger,amount,wire
from .official_publications import utc
from .render_frame_qc import validate as validate_frames
from .render_vision_frame_bridge import NativeRenderEvidenceFrameExtractor
from .render_vision_registry import NativeRenderVisionFactory,RenderVisionProfile
from .render_vision_models import RenderAnalyze,RenderAction
from .rights import validate_document as validate_rights
from .rights_override import NativeRightsOverrides,rights_sha,fixture
from .source_assets import canonical_assets
from .source_approval import validate_render_approval
from .store import Store,now

TABLES=('native_render_vision_intents','native_render_vision_responses','native_render_vision_events')
STATUSES={'not_configured','needs_approval','approved','claimed','succeeded','failed','review_required','outcome_unknown','cancelled'}
FALSE_FLAGS=('canonical_timeline_mutated','hard_qc_replaced','final_video_approved','confidence_calibrated',
    'continuous_tracking_performed','billing_invoice_verified','publishing_authorized','owner_uat_accepted','real_provider_tested')


def typed(value,cls):
    try:
        if type(value) is not cls or set(value.__dict__)-set(cls.model_fields):raise ValueError()
        parsed=cls.model_validate(value.model_dump(mode='python',warnings=False))
        if digest(parsed.model_dump(mode='json'))!=digest(value.model_dump(mode='json',warnings=False)):raise ValueError()
        return parsed
    except Exception:raise WorkflowError('NATIVE_RENDER_VISION_FIELDS_INVALID',400) from None


class NativeRenderVision:
    def __init__(self,store,config,*,workspace_id='wsp_native_local',factories=None,enabled=False,identity_provider=None,clock=lambda:datetime.now(timezone.utc)):
        if (type(store) is not Store or type(enabled) is not bool or not callable(clock)
            or identity_provider is not None and not callable(identity_provider)
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',workspace_id)
            or config.data_root.absolute()!=store.root.absolute()):raise WorkflowError('NATIVE_RENDER_VISION_RUNTIME_INVALID',400)
        self.store,self.config,self.workspace=store,config,workspace_id
        self.factories=dict(factories or {});self.enabled=enabled;self.identity_provider=identity_provider;self.clock=clock
        if any(type(f) is not NativeRenderVisionFactory or k!=f.profile.profile_id or f.root!=store.root.absolute()
            or f.workspace!=workspace_id for k,f in self.factories.items()):raise WorkflowError('NATIVE_RENDER_VISION_RUNTIME_INVALID',400)
        self.costs=CostLedger(store)
        self._frozen=(store,config,workspace_id,store.root.absolute(),config.data_root.absolute(),enabled,identity_provider,clock,self.costs,tuple(sorted(self.factories.items())))
        self.check()
        with store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_render_vision_intents (
                vision_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,
                request_sha256 TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,status TEXT NOT NULL,
                claim_id TEXT,cost_operation_id TEXT,response_id TEXT,result_sha256 TEXT,result_json TEXT,failure_code TEXT,
                actor_ref TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(workspace_id,project_id,key_sha256));
                CREATE TABLE IF NOT EXISTS native_render_vision_responses (
                response_id TEXT PRIMARY KEY,vision_id TEXT NOT NULL,claim_id TEXT NOT NULL,workspace_id TEXT NOT NULL,
                project_id TEXT NOT NULL,cost_operation_id TEXT NOT NULL,observation_json TEXT NOT NULL,observation_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL,UNIQUE(vision_id,claim_id));
                CREATE TABLE IF NOT EXISTS native_render_vision_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,vision_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                action TEXT NOT NULL,actor_ref TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at TEXT NOT NULL);''')
            if con.execute('SELECT 1 FROM native_render_vision_intents WHERE workspace_id!=? LIMIT 1',(workspace_id,)).fetchone():
                raise WorkflowError('NATIVE_RENDER_VISION_WORKSPACE_CHANGED')

    def check(self):
        if (type(self.enabled) is not bool or self.costs.store is not self.store
            or (self.store,self.config,self.workspace,self.store.root.absolute(),self.config.data_root.absolute(),self.enabled,
                self.identity_provider,self.clock,self.costs,tuple(sorted(self.factories.items())))!=self._frozen):
            raise WorkflowError('NATIVE_RENDER_VISION_RUNTIME_CHANGED')
        path=guard(self.store.root/'.vf-auth-workspace.json')
        try:
            if path.exists():
                if path.stat().st_size>512 or path.stat().st_nlink!=1 or json.loads(path.read_bytes())!={'schema':'vf-native-workspace-binding-v1','workspace_id':self.workspace}:raise ValueError()
            elif self.workspace!='wsp_native_local':raise ValueError()
        except Exception:raise WorkflowError('NATIVE_RENDER_VISION_WORKSPACE_CHANGED') from None

    def states(self):
        self.check()
        return {'schema_version':'native-render-vision-runtime-v1','workspace_id':self.workspace,'enabled':self.enabled,
            'profiles':[f.public() for _,f in sorted(self.factories.items())],'purpose':'rendered_video_quality_review',
            'current_owner_required':True,'finite_consent_required':True,'original_request_response_cost_journal':True,
            'source_asset_consent_reused':False,'automatic_dispatch':False,'automatic_retry':False,'publishing_enabled':False,
            'hard_qc_replaced':False,'owner_uat_accepted':False,'real_provider_tested':False}

    def identity(self,principal=None,authority=None):
        try:
            verifier=self.identity_provider() if self.identity_provider else None
            if type(verifier) is not HumanAuthVerifier:raise ValueError()
            if principal is not None and (type(principal) is not HumanPrincipal or principal.role_for(self.workspace)!='owner'):raise ValueError()
            token=principal.token_id if principal is not None else authority['token_id'];subject=principal.subject if principal is not None else authority['subject']
            record=verifier.registry.tokens.get(token);instant=utc(self.clock())
            if (record is None or not record.enabled or record.subject!=subject or utc(record.issued_at)>instant
                or instant>=utc(record.expires_at) or record.not_before is not None and utc(record.not_before)>instant):raise ValueError()
            current=HumanPrincipal(token_id=record.token_id,subject=record.subject,display_name=record.display_name,
                platform_role=record.platform_role,workspace_roles=record.workspace_roles,expires_at=record.expires_at)
            if current.role_for(self.workspace)!='owner' or principal is not None and current!=principal:raise ValueError()
            proof={'token_id':token,'subject':subject,'identity_revision_sha256':digest(record.model_dump(mode='json')),'expires_at':utc(record.expires_at).isoformat()}
            if authority is not None and proof!=authority:raise ValueError()
            return proof
        except Exception:raise WorkflowError('NATIVE_RENDER_VISION_CURRENT_OWNER_REQUIRED',403) from None

    def factory(self,payload):
        self.check();f=self.factories.get(payload.profile_id)
        if (type(f) is not NativeRenderVisionFactory or f.sha256!=payload.expected_configuration_sha256
            or f.mock is not payload.acknowledged_protocol_mock):raise WorkflowError('NATIVE_RENDER_VISION_PROFILE_BINDING_CHANGED')
        p=f.check()
        allowance=((Decimal(16384)*max(p.input_vnd_per_million_tokens,p.cached_input_vnd_per_million_tokens)
            +Decimal(8000)*p.output_vnd_per_million_tokens)/Decimal(1000000)).quantize(Decimal('.000001'),rounding=ROUND_CEILING)
        if payload.max_operation_cost_vnd<max(allowance,p.estimated_cost_vnd):raise WorkflowError('NATIVE_RENDER_VISION_COST_CEILING_REQUIRED',400)
        return f

    def budget_blocked(self,con,project,ceiling,exclude=None):
        limit=amount((project['document'].get('cost_policy') or {}).get('max_ai_cost_vnd'))
        if limit is None:return False
        exposure=Decimal(0)
        for row in con.execute("SELECT * FROM native_cost_operations WHERE project_id=? AND paid=1 AND status!='needs_approval'",(project['id'],)):
            if row['id']==exclude:continue
            reserved=amount(row['actual_cost'] if row['actual_cost'] is not None else row['estimated_cost'])
            if reserved is None:return True
            exposure+=reserved
        return exposure+ceiling>limit

    def context(self,con,project,payload,mock):
        current=self.store.editable(con,project,payload.revision)
        bridge=NativeRenderEvidenceFrameExtractor(self.store,self.config,project,payload.render_job_id,workspace_id=self.workspace,con=con)
        binding=bridge.binding(con=con)
        if not binding['matches_current_project_document'] or digest(binding)!=payload.expected_render_input_sha256:
            raise WorkflowError('NATIVE_RENDER_VISION_CURRENT_RENDER_REQUIRED')
        job=self.store.job(con.execute('SELECT * FROM jobs WHERE id=?',(payload.render_job_id,)).fetchone(),con)
        approval=job['snapshot'].get('approval')
        try:approved_at=utc(datetime.fromisoformat(approval['approved_at']))
        except Exception:raise WorkflowError('NATIVE_RENDER_VISION_ORIGINAL_RENDER_APPROVAL_REQUIRED') from None
        if (not isinstance(approval,dict) or type(approval.get('revision')) is not int or approval['revision']!=job['revision']
            or approval.get('snapshot_sha256')!=digest(current['document']) or digest(current['approval'])!=digest(approval)
            or approval.get('approval_scope')=='narration_only' or approval.get('source') not in {'local_ui_human_review','human_user_reply_in_codex'}
            or not isinstance(approval.get('reviewer'),str) or not 1<=len(approval['reviewer'].strip())<=100
            or approved_at>utc(self.clock())):
            raise WorkflowError('NATIVE_RENDER_VISION_ORIGINAL_RENDER_APPROVAL_REQUIRED')
        if approval.get('render_mode')=='source_footage':validate_render_approval(job)
        elif approval.get('render_mode')=='prepared_narration' and not approval.get('reviewed_preview'):
            raise WorkflowError('NATIVE_RENDER_VISION_ORIGINAL_RENDER_APPROVAL_REQUIRED')
        validate_rights(current['document'],project_id=project,workspace_id=self.workspace)
        rights=[]
        # All registered visual assets are included conservatively. Only PNGs
        # from the final video are transmitted; music/audio never leaves here.
        for asset in canonical_assets(current['document']):
            if asset['kind'] not in {'image','video','logo'}:continue
            if asset.get('rights_status')=='restricted' or not mock and fixture(asset):raise WorkflowError('NATIVE_RENDER_VISION_RIGHTS_BLOCKED')
            override=None
            if mock:kind='protocol_mock_only_unverified_rights'
            elif asset.get('rights_status') in {'owned','licensed','verified'} and asset.get('rights_review_required') is not True:kind='registered_rights'
            else:
                service=getattr(self.store,'rights_overrides',None)
                if type(service) is not NativeRightsOverrides or service.store is not self.store or service.workspace!=self.workspace:
                    raise WorkflowError('NATIVE_RENDER_VISION_RIGHTS_REVIEW_REQUIRED')
                override=service.active(current['document'],project,asset)
                if override is None:raise WorkflowError('NATIVE_RENDER_VISION_RIGHTS_REVIEW_REQUIRED')
                kind='explicit_owner_override'
            path=guard(self.store.root/'assets'/asset['id'],exists=True)
            if path.stat().st_nlink!=1 or file_sha(path)!=asset['sha256']:raise WorkflowError('NATIVE_RENDER_VISION_ASSET_CHANGED')
            rights.append({'asset_id':asset['id'],'asset_sha256':asset['sha256'],'rights_sha256':rights_sha(asset),
                'rights_status':asset.get('rights_status','unknown'),'authorization_kind':kind,'override':override,
                'rights_independently_verified':False,'publishing_authorized':False})
        return current,binding,rights

    def event(self,con,row,action,actor,**evidence):
        con.execute('INSERT INTO native_render_vision_events(vision_id,workspace_id,project_id,action,actor_ref,evidence_json,created_at) VALUES(?,?,?,?,?,?,?)',
            (row['vision_id'],self.workspace,row['project_id'],action,actor,json.dumps(evidence),now()))

    def row(self,con,project,identity):
        if con.execute('SELECT 1 FROM projects WHERE id=?',(project,)).fetchone() is None:raise WorkflowError('PROJECT_NOT_FOUND',404)
        row=con.execute('SELECT * FROM native_render_vision_intents WHERE vision_id=? AND workspace_id=? AND project_id=?',(identity,self.workspace,project)).fetchone()
        if row is None:raise WorkflowError('NATIVE_RENDER_VISION_NOT_FOUND',404)
        return row

    def create(self,project,payload,*,principal):
        payload=typed(payload,RenderAnalyze);request=payload.model_dump(mode='json',exclude={'request_key'})
        key=hashlib.sha256(payload.request_key.encode()).hexdigest();fingerprint=digest(request)
        with self.store.transaction() as con:
            prior=con.execute('SELECT * FROM native_render_vision_intents WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
            if prior:
                if prior['request_sha256']!=fingerprint:raise WorkflowError('NATIVE_RENDER_VISION_IDEMPOTENCY_CONFLICT')
                return self.read(con,prior),True
            authority=self.identity(principal);f=self.factory(payload);current,binding,rights=self.context(con,project,payload,f.mock)
            stamp=utc(self.clock());deadline=stamp+timedelta(seconds=payload.valid_for_seconds)
            if deadline>utc(datetime.fromisoformat(authority['expires_at'])):raise WorkflowError('NATIVE_RENDER_VISION_CONSENT_EXCEEDS_IDENTITY',400)
            status='approved' if self.enabled and f.public()['status']=='CONFIGURED' else 'not_configured'
            if status=='approved' and self.budget_blocked(con,current,payload.max_operation_cost_vnd):status='needs_approval'
            snapshot={'schema_version':'native-render-vision-snapshot-v1','workspace_id':self.workspace,'project_id':project,'request':request,
                'authority':authority,'input_binding':binding,'rights':rights,'configuration':f.public(),'approved_at':stamp.isoformat(),'deadline':deadline.isoformat(),
                'source_asset_consent_reused':False,'automatic_dispatch':False,'publishing_enabled':False,'owner_uat_accepted':False}
            identity='nrvi_'+uuid.uuid4().hex
            con.execute('INSERT INTO native_render_vision_intents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,self.workspace,project,key,fingerprint,digest(snapshot),json.dumps(snapshot,ensure_ascii=False),status,None,None,None,None,None,None,principal.subject,stamp.isoformat(),stamp.isoformat()))
            row=self.row(con,project,identity);self.event(con,row,'vision.render.consent.recorded',principal.subject,status=status,mock=f.mock,automatic_dispatch=False)
            return self.read(con,row),False

    def fence(self,con,value,claim):
        self.check();row=self.row(con,value['project_id'],value['vision_id']);snapshot=value['snapshot']
        if row['status']!='claimed' or row['claim_id']!=claim or row['snapshot_sha256']!=value['snapshot_sha256']:raise WorkflowError('NATIVE_RENDER_VISION_CLAIM_STOPPED')
        self.read(con,row);self.identity(authority=snapshot['authority'])
        if not self.enabled or not utc(datetime.fromisoformat(snapshot['approved_at']))<=utc(self.clock())<utc(datetime.fromisoformat(snapshot['deadline'])):
            raise WorkflowError('NATIVE_RENDER_VISION_CONSENT_EXPIRED')
        payload=RenderAnalyze.model_validate({**snapshot['request'],'request_key':'internal-render-vision-fence'});f=self.factory(payload)
        if f.public()!=snapshot['configuration'] or f.public()['status']!='CONFIGURED':raise WorkflowError('NATIVE_RENDER_VISION_PROFILE_CHANGED')
        current,binding,rights=self.context(con,value['project_id'],payload,f.mock)
        if binding!=snapshot['input_binding'] or rights!=snapshot['rights']:raise WorkflowError('NATIVE_RENDER_VISION_INPUT_OR_RIGHTS_CHANGED')
        if self.budget_blocked(con,current,payload.max_operation_cost_vnd,row['cost_operation_id']):raise WorkflowError('AI_COST_APPROVAL_REQUIRED_BEFORE_DISPATCH')
        return row,f

    def retain(self,value,claim,observation):
        parsed=typed(observation,VisionResponseObservation);raw=parsed.model_dump(mode='json')
        with self.store.transaction() as con:
            row=self.row(con,value['project_id'],value['vision_id'])
            if (row['claim_id']!=claim or row['snapshot_sha256']!=value['snapshot_sha256'] or row['cost_operation_id'] is None
                or parsed.mock_transport is not value['snapshot']['configuration']['mock']):raise WorkflowError('NATIVE_RENDER_VISION_RESPONSE_BINDING_CHANGED')
            prior=con.execute('SELECT * FROM native_render_vision_responses WHERE vision_id=? AND claim_id=?',(value['vision_id'],claim)).fetchone()
            if prior:
                if prior['observation_sha256']!=digest(raw):raise WorkflowError('NATIVE_RENDER_VISION_RESPONSE_CONFLICT')
            else:
                identity='nrvr_'+uuid.uuid4().hex
                con.execute('INSERT INTO native_render_vision_responses VALUES(?,?,?,?,?,?,?,?,?)',
                    (identity,value['vision_id'],claim,self.workspace,value['project_id'],row['cost_operation_id'],json.dumps(raw),digest(raw),now()))
                con.execute('UPDATE native_render_vision_intents SET response_id=?,updated_at=? WHERE vision_id=?',(identity,now(),value['vision_id']))
                if row['status']=='outcome_unknown':
                    con.execute("UPDATE native_render_vision_intents SET status='review_required' WHERE vision_id=?",(value['vision_id'],))
                self.event(con,row,'vision.render.complete_response.observed','worker',response_id=identity,mock=parsed.mock_transport)
        if self.costs.pending(row['cost_operation_id']):
            usage=None if parsed.input_tokens is None else {'input_tokens':parsed.input_tokens,'output_tokens':parsed.output_tokens,'total_tokens':parsed.input_tokens+parsed.output_tokens}
            self.costs.settle(row['cost_operation_id'],status='response_received',usage=usage,response_sha256=parsed.response_sha256)

    def process(self,project,identity,payload):
        payload=typed(payload,RenderAction)
        with self.store.transaction() as con:
            row=self.row(con,project,identity);value=self.read(con,row)
            if row['snapshot_sha256']!=payload.expected_snapshot_sha256:raise WorkflowError('NATIVE_RENDER_VISION_SNAPSHOT_CHANGED')
            if row['status']!='approved':return value
            claim='nrvc_'+uuid.uuid4().hex;operation='render-vision.'+claim;job=value['snapshot']['request']['render_job_id']
            cost=digest({'project':project,'job':job,'provider':'openai-vision','operation':operation})
            con.execute("UPDATE native_render_vision_intents SET status='claimed',claim_id=?,cost_operation_id=?,updated_at=? WHERE vision_id=?",(claim,cost,now(),identity))
            self.event(con,row,'vision.render.one_use_claim','worker',claim_id=claim)
            value=self.read(con,self.row(con,project,identity))
        started=False
        try:
            with self.store.transaction() as con:_,f=self.fence(con,value,claim)
            request=RenderAnalyze.model_validate({**value['snapshot']['request'],'request_key':'internal-render-vision-dispatch'})
            self.costs.begin(project_id=project,job_id=job,provider='openai-vision',model='gpt-5-mini',operation=operation,
                request_sha256=value['request_sha256'],estimated_cost=wire(request.max_operation_cost_vnd),external_call=not f.mock,paid=not f.mock)
            with self.store.transaction() as con:_,f=self.fence(con,value,claim)
            bridge=NativeRenderEvidenceFrameExtractor(self.store,self.config,project,job,workspace_id=self.workspace)
            def admission():
                with self.store.transaction() as con:self.fence(con,value,claim)
            provider=f.provider(bridge,admission_guard=admission,response_observer=lambda observed:self.retain(value,claim,observed))
            binding=value['snapshot']['input_binding'];observation=binding['record']['observation'];started=True
            async def dispatch():
                return await asyncio.wait_for(provider.analyze(self.store.root/'jobs'/job/'final.mp4',metadata=bridge.input_metadata(),scenes=[],
                    asset_id=binding['render_artifact_id'],checksum_sha256=observation['rendered_video_sha256'],
                    sample_interval_seconds=observation['sampling_interval_seconds']),timeout=120)
            prediction=asyncio.run(dispatch())
            with self.store.transaction() as con:
                row,f=self.fence(con,value,claim);current=self.read(con,row);response=current['response']
                artifacts=self.artifacts(binding)
                if (response is None or prediction.provenance['response_sha256']!=response['response_sha256']
                    or prediction.provenance['request_sha256']!=response['request_sha256'] or prediction.provenance['mock_tested'] is not f.mock
                    or prediction.provenance['source_checksum']!=observation['rendered_video_sha256'] or prediction.provenance['artifact_evidence']!=artifacts):
                    raise WorkflowError('NATIVE_RENDER_VISION_RESULT_BINDING_CHANGED')
                if response['calculated_usage_cost_vnd'] is not None and amount(response['calculated_usage_cost_vnd'])>request.max_operation_cost_vnd:
                    raise WorkflowError('NATIVE_RENDER_VISION_OBSERVED_USAGE_EXCEEDS_CEILING')
                result=self.result(value,row,response,prediction)
                con.execute("UPDATE native_render_vision_intents SET status='succeeded',result_json=?,result_sha256=?,updated_at=? WHERE vision_id=?",(json.dumps(result,ensure_ascii=False),digest(result),now(),identity))
                self.event(con,row,'vision.render.advisory_result.saved','worker',mock=f.mock,hard_qc_replaced=False)
        except Exception as error:
            code=getattr(error,'code',None)
            if not isinstance(code,str) or not re.fullmatch(r'[A-Z0-9_]{3,120}',code):code='NATIVE_RENDER_VISION_OPERATION_STOPPED'
            uncertain=started and code!='OPENAI_VISION_DISPATCH_ADMISSION_FAILED'
            with self.store.transaction() as con:
                row=self.row(con,project,identity)
                if row['status']=='claimed' and row['claim_id']==claim:
                    status='review_required' if row['response_id'] is not None else 'outcome_unknown' if uncertain else 'needs_approval' if code=='AI_COST_APPROVAL_REQUIRED_BEFORE_DISPATCH' else 'failed'
                    con.execute('UPDATE native_render_vision_intents SET status=?,failure_code=?,updated_at=? WHERE vision_id=?',(status,code,now(),identity))
                    self.event(con,row,'vision.render.operation.stopped','worker',status=status,failure_code=code,automatic_retry=False)
            if self.costs.pending(cost):self.costs.settle(cost,status='outcome_unknown' if uncertain else 'rejected',error_code=code)
        return self.get(project,identity)

    @staticmethod
    def artifacts(binding):
        return [{'frame_index':i,'timestamp_seconds':v['timestamp_seconds'],
            'evidence_frame_reference':f"render-frame://{binding['project_id']}/{binding['job_id']}/{v['evidence_frame_reference'].rsplit('/',1)[-1]}",
            'sha256':v['sha256'],'content_type':'image/png'} for i,v in enumerate(binding['record']['observation']['frames'])]

    @staticmethod
    def result(value,row,response,prediction):
        frames=normalize_frames(prediction.frames,provider_key='openai-vision',model='gpt-5-mini',fingerprint=value['snapshot_sha256'])
        best,thumbs=rank_best_frames(frames);mock=value['snapshot']['configuration']['mock']
        return {'schema_version':'native-render-vision-result-v1','vision_id':row['vision_id'],'workspace_id':row['workspace_id'],
            'project_id':row['project_id'],'render_job_id':value['snapshot']['request']['render_job_id'],'snapshot_sha256':value['snapshot_sha256'],
            'response_id':row['response_id'],'cost_operation_id':row['cost_operation_id'],'response_sha256':response['response_sha256'],
            'render_input_sha256':value['snapshot']['request']['expected_render_input_sha256'],'rendered_video_sha256':value['snapshot']['input_binding']['record']['observation']['rendered_video_sha256'],
            'mock':mock,'semantic_inference_performed':not mock,'external_provider_calls':0 if mock else 1,'paid_operation_attempted':not mock,
            'adapter_provenance':prediction.provenance,'frames':[v.model_dump(mode='json') for v in frames],
            'best_frame_ids':best,'thumbnail_candidate_ids':thumbs,'subject_tracks':[],
            'calculated_usage_cost_vnd':response['calculated_usage_cost_vnd'],'observed_actual_billed_cost_vnd':None,
            'decoded_render_pts_verified':True,'advisory_only':True,'human_semantic_review_required':True,**{k:False for k in FALSE_FLAGS}}

    def read(self,con,row):
        """Original keyless history: no current provider config/rights/authority renewal."""
        try:
            value=dict(row);snapshot=json.loads(value.pop('snapshot_json'));value.pop('key_sha256')
            request=RenderAnalyze.model_validate({**snapshot['request'],'request_key':'internal-render-vision-history'})
            profile=RenderVisionProfile.model_validate(snapshot['configuration']['profile']);binding=snapshot['input_binding']
            job=self.store.job(con.execute('SELECT * FROM jobs WHERE id=?',(request.render_job_id,)).fetchone(),con)
            document=job['snapshot']['document'];qc=job['result']['qc'];full=qc.get('full_quality');measured=full['full_production_qc'] if full is not None else qc
            render_metadata=MediaMetadata(media_kind='video',detected_content_type='video/mp4',width=measured['width'],height=measured['height'],
                duration_seconds=measured['duration_seconds'],fps=measured['fps'],video_codec=measured['video_codec'],audio_codec=measured['audio_codec'])
            first=binding['record']['observation']['frames'][0]
            input_metadata=MediaMetadata(media_kind='image',detected_content_type='image/png',format_name='png',width=first['width'],height=first['height'])
            if (set(snapshot)!={'schema_version','workspace_id','project_id','request','authority','input_binding','rights','configuration','approved_at','deadline','source_asset_consent_reused','automatic_dispatch','publishing_enabled','owner_uat_accepted'}
                or snapshot['schema_version']!='native-render-vision-snapshot-v1' or snapshot['workspace_id']!=self.workspace
                or snapshot['project_id']!=value['project_id'] or value['status'] not in STATUSES
                or not re.fullmatch(r'nrvi_[a-f0-9]{32}',value['vision_id']) or digest(snapshot)!=value['snapshot_sha256']
                or digest(snapshot['request'])!=value['request_sha256'] or digest(binding)!=request.expected_render_input_sha256
                or any(snapshot[k] is not False for k in ('source_asset_consent_reused','automatic_dispatch','publishing_enabled','owner_uat_accepted'))
                or profile.profile_id!=request.profile_id or profile.key_receipt.workspace_id!=self.workspace
                or digest(profile.model_dump(mode='json'))!=digest(snapshot['configuration']['profile'])
                or snapshot['configuration']['configuration_sha256']!=request.expected_configuration_sha256
                or snapshot['configuration']['mock'] is not request.acknowledged_protocol_mock
                or any(snapshot['configuration'][k] is not False for k in ('startup_decryption','credential_verified','asset_analysis_consent_reused','provider_authorized','automatic_dispatch','publishing_enabled','real_provider_tested'))
                or set(snapshot['authority'])!={'token_id','subject','identity_revision_sha256','expires_at'}
                or snapshot['authority']['subject']!=value['actor_ref'] or not re.fullmatch(r'[a-f0-9]{64}',snapshot['authority']['identity_revision_sha256'])
                or snapshot['approved_at']!=value['created_at']
                or (utc(datetime.fromisoformat(snapshot['deadline']))-utc(datetime.fromisoformat(snapshot['approved_at']))).total_seconds()!=request.valid_for_seconds
                or utc(datetime.fromisoformat(snapshot['deadline']))>utc(datetime.fromisoformat(snapshot['authority']['expires_at']))
                or binding['schema_version']!='native-render-vision-frame-input-v1' or binding['purpose']!='rendered_video_quality_review'
                or any(binding[k] is not False for k in ('source_asset_analysis_consent_reused','semantic_inference_performed','prediction_confidence_calibrated',
                    'continuous_tracking_performed','publishing_authorized','owner_uat_accepted','real_provider_tested'))
                or binding['separate_owner_provider_consent_required'] is not True or type(binding['external_provider_calls']) is not int
                or binding['external_provider_calls']!=0 or type(binding['paid_operations']) is not int or binding['paid_operations']!=0
                or binding['render_artifact_id']!='render:'+job['id'] or binding['render_metadata']!=render_metadata.model_dump(mode='json')
                or digest(binding['input_metadata'])!=digest(input_metadata.model_dump(mode='json'))
                or binding['project_id']!=value['project_id'] or binding['workspace_id']!=self.workspace or binding['job_id']!=job['id']
                or job['project_id']!=value['project_id'] or job['status']!='succeeded' or job['kind']!='render'
                or binding['revision']!=job['revision'] or binding['current_project_revision']!=request.revision or binding['matches_current_project_document'] is not True
                or binding['original_snapshot_sha256']!=digest(job['snapshot']) or binding['original_document_sha256']!=digest(document)
                or binding['current_project_document_sha256']!=digest(document) or binding['original_approval_sha256']!=digest(job['snapshot']['approval'])
                or binding['original_result_sha256']!=digest(job['result']) or binding['record']!=measured['rendered_frame_evidence']
                or binding['record']['observation']['rendered_video_sha256']!=qc['final_sha256'] or qc['passed'] is not True
                or full is not None and full['status']!='passed'):raise ValueError()
            validate_frames(self.store.root/'jobs'/job['id'],binding['record'],document_sha256=digest(document),physical=False)
            assets={a['id']:a for a in canonical_assets(document) if a['kind'] in {'image','video','logo'}}
            if {r['asset_id'] for r in snapshot['rights']}!=set(assets) or len(snapshot['rights'])!=len(assets):raise ValueError()
            for right in snapshot['rights']:
                asset=assets[right['asset_id']]
                if (set(right)!={'asset_id','asset_sha256','rights_sha256','rights_status','authorization_kind','override','rights_independently_verified','publishing_authorized'}
                    or right['asset_sha256']!=asset['sha256'] or right['rights_sha256']!=rights_sha(asset)
                    or right['rights_status']!=asset.get('rights_status','unknown') or right['rights_independently_verified'] is not False
                    or right['publishing_authorized'] is not False or right['authorization_kind'] not in {'protocol_mock_only_unverified_rights','registered_rights','explicit_owner_override'}
                    or (right['authorization_kind']=='protocol_mock_only_unverified_rights') is not request.acknowledged_protocol_mock):raise ValueError()
                if right['authorization_kind']=='registered_rights' and (asset.get('rights_status') not in {'owned','licensed','verified'}
                    or asset.get('rights_review_required') is True or fixture(asset) or right['override'] is not None):raise ValueError()
                if right['authorization_kind']=='protocol_mock_only_unverified_rights' and right['override'] is not None:raise ValueError()
                if right['authorization_kind']=='explicit_owner_override':
                    override=right['override']
                    if (override not in document.get('media_rights_overrides',[]) or override['request']['action']!='grant'
                        or override['asset_id']!=asset['id'] or override['asset_sha256']!=asset['sha256']
                        or override['workspace_id']!=self.workspace or override['project_id']!=value['project_id']
                        or override['request']['expected_rights_sha256']!=rights_sha(asset)
                        or not utc(datetime.fromisoformat(override['created_at']))<=utc(datetime.fromisoformat(snapshot['approved_at']))<utc(datetime.fromisoformat(override['expires_at']))):raise ValueError()
            response=None;cost=None
            if value['cost_operation_id'] is not None:
                if not re.fullmatch(r'nrvc_[a-f0-9]{32}',value['claim_id']):raise ValueError()
                expected_cost=digest({'project':value['project_id'],'job':job['id'],'provider':'openai-vision','operation':'render-vision.'+value['claim_id']})
                if value['cost_operation_id']!=expected_cost:raise ValueError()
                cost=con.execute('SELECT * FROM native_cost_operations WHERE id=?',(expected_cost,)).fetchone()
                if cost is not None and (cost['project_id']!=value['project_id'] or cost['job_id']!=job['id'] or cost['provider']!='openai-vision'
                    or cost['model']!='gpt-5-mini' or cost['operation']!='render-vision.'+value['claim_id'] or cost['request_sha256']!=value['request_sha256']
                    or amount(cost['estimated_cost'])!=request.max_operation_cost_vnd or cost['actual_cost'] is not None
                    or cost['paid']!=int(not request.acknowledged_protocol_mock) or cost['external_call']!=int(not request.acknowledged_protocol_mock)):raise ValueError()
            if value['response_id'] is not None:
                raw=con.execute('SELECT * FROM native_render_vision_responses WHERE response_id=?',(value['response_id'],)).fetchone()
                if raw is None or cost is None or any(raw[k]!=value[k] for k in ('vision_id','workspace_id','project_id','claim_id','cost_operation_id')):raise ValueError()
                saved_response=json.loads(raw['observation_json']);response=VisionResponseObservation.model_validate(saved_response)
                if digest(response.model_dump(mode='json'))!=digest(saved_response) or digest(saved_response)!=raw['observation_sha256'] or response.mock_transport is not request.acknowledged_protocol_mock:raise ValueError()
                if cost['status']=='response_received':
                    receipt=json.loads(cost['receipt']);usage=None if response.input_tokens is None else {'input_tokens':response.input_tokens,'output_tokens':response.output_tokens,'total_tokens':response.input_tokens+response.output_tokens}
                    if receipt['provider_response_sha256']!=response.response_sha256 or receipt['usage']!=usage or receipt['actual_cost_known'] is not False:raise ValueError()
                elif cost['status'] not in {'dispatch_intent','outcome_unknown'}:raise ValueError()
                response=response.model_dump(mode='json')
            result=json.loads(value.pop('result_json')) if value['result_json'] is not None else None
            if (value['status']=='succeeded')!=(result is not None) or (result is not None)!=(value['result_sha256'] is not None):raise ValueError()
            if result is not None:
                frames=[VisionFrameRead.model_validate(f) for f in result['frames']];artifacts=self.artifacts(binding);provenance=result['adapter_provenance']
                if (digest(result)!=value['result_sha256'] or result['schema_version']!='native-render-vision-result-v1' or response is None or cost['status']!='response_received'
                    or any(result[k]!=value[k] for k in ('vision_id','workspace_id','project_id','snapshot_sha256','response_id','cost_operation_id'))
                    or result['render_job_id']!=job['id'] or result['render_input_sha256']!=request.expected_render_input_sha256
                    or result['rendered_video_sha256']!=qc['final_sha256'] or result['response_sha256']!=response['response_sha256']
                    or result['mock'] is not request.acknowledged_protocol_mock or result['semantic_inference_performed'] is not (not request.acknowledged_protocol_mock)
                    or type(result['external_provider_calls']) is not int or result['external_provider_calls']!=(0 if request.acknowledged_protocol_mock else 1)
                    or result['paid_operation_attempted'] is not (not request.acknowledged_protocol_mock)
                    or any(result[k] is not False for k in FALSE_FLAGS) or result['decoded_render_pts_verified'] is not True
                    or result['advisory_only'] is not True or result['human_semantic_review_required'] is not True
                    or result['subject_tracks']!=[] or result['observed_actual_billed_cost_vnd'] is not None
                    or result['calculated_usage_cost_vnd']!=response['calculated_usage_cost_vnd']
                    or provenance['mock_tested'] is not request.acknowledged_protocol_mock or provenance['external_call'] is not True or provenance['paid'] is not True
                    or provenance['real_provider_tested'] is not False or provenance['secret_recorded'] is not False
                    or provenance['request_sha256']!=response['request_sha256'] or provenance['response_sha256']!=response['response_sha256']
                    or provenance['source_checksum']!=qc['final_sha256'] or provenance['artifact_evidence']!=artifacts
                    or provenance['cost_receipt']['actual_cost_vnd']!=response['calculated_usage_cost_vnd']
                    or [(f.timestamp_seconds,f.evidence_frame_reference) for f in frames]!=[(a['timestamp_seconds'],a['evidence_frame_reference']) for a in artifacts]
                    or any(f.provider_key!='openai-vision' or f.model!='gpt-5-mini' for f in frames)
                    or not set(result['best_frame_ids']+result['thumbnail_candidate_ids'])<={f.frame_id for f in frames}):raise ValueError()
            return {**value,'schema_version':'native-render-vision-intent-v1','snapshot':snapshot,'response':response,'result':result,
                'needs_approval':value['status']=='needs_approval','automatic_retry':False,'publishing_enabled':False,'owner_uat_accepted':False}
        except Exception:raise WorkflowError('NATIVE_RENDER_VISION_EVIDENCE_INVALID') from None

    def get(self,project,identity):
        self.check()
        with self.store.transaction() as con:return self.read(con,self.row(con,project,identity))

    def page(self,project,*,limit=25,cursor=None):
        self.check()
        if type(limit) is not int or not 1<=limit<=100:raise WorkflowError('NATIVE_RENDER_VISION_PAGE_INVALID',400)
        after=None
        if cursor is not None:
            try:
                if not isinstance(cursor,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,1000}',cursor):raise ValueError()
                after=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if (not isinstance(after,list) or len(after)!=4 or after[:2]!=[self.workspace,project]
                    or not isinstance(after[2],str) or len(after[2])>40 or datetime.fromisoformat(after[2]).tzinfo is None
                    or not isinstance(after[3],str) or not re.fullmatch(r'nrvi_[a-f0-9]{32}',after[3])):raise ValueError()
            except Exception:raise WorkflowError('NATIVE_RENDER_VISION_CURSOR_INVALID',400) from None
        with self.store.transaction() as con:
            if con.execute('SELECT 1 FROM projects WHERE id=?',(project,)).fetchone() is None:raise WorkflowError('PROJECT_NOT_FOUND',404)
            where='workspace_id=? AND project_id=?';params=[self.workspace,project]
            if after:where+=' AND (created_at<? OR (created_at=? AND vision_id<?))';params.extend([after[2],after[2],after[3]])
            rows=con.execute('SELECT * FROM native_render_vision_intents WHERE '+where+' ORDER BY created_at DESC,vision_id DESC LIMIT ?',(*params,limit+1)).fetchall()
            next_cursor=base64.urlsafe_b64encode(json.dumps([self.workspace,project,rows[limit-1]['created_at'],rows[limit-1]['vision_id']]).encode()).decode().rstrip('=') if len(rows)>limit else None
            return {'schema_version':'native-render-vision-page-v1','workspace_id':self.workspace,'project_id':project,'items':[self.read(con,r) for r in rows[:limit]],
                'next_cursor':next_cursor,'limit':limit,'automatic_dispatch':False,'publishing_enabled':False,'owner_uat_accepted':False}

    def cancel(self,project,identity,payload,*,principal):
        payload=typed(payload,RenderAction);self.check();self.identity(principal)
        with self.store.transaction() as con:
            row=self.row(con,project,identity);self.read(con,row)
            if row['snapshot_sha256']!=payload.expected_snapshot_sha256:raise WorkflowError('NATIVE_RENDER_VISION_SNAPSHOT_CHANGED')
            if row['status']=='succeeded':raise WorkflowError('NATIVE_RENDER_VISION_ALREADY_COMPLETE')
            if row['status']!='cancelled':
                con.execute("UPDATE native_render_vision_intents SET status='cancelled',updated_at=? WHERE vision_id=?",(now(),identity))
                self.event(con,row,'vision.render.cancelled',principal.subject,cancel_is_remote_rollback=False)
            return self.read(con,self.row(con,project,identity))

    def recover(self):
        self.check()
        with self.store.transaction() as con:
            rows=con.execute("SELECT * FROM native_render_vision_intents WHERE workspace_id=? AND status='claimed'",(self.workspace,)).fetchall()
            for row in rows:
                self.read(con,row);status='review_required' if row['response_id'] is not None else 'outcome_unknown'
                con.execute('UPDATE native_render_vision_intents SET status=?,failure_code=?,updated_at=? WHERE vision_id=?',(status,'NATIVE_RENDER_VISION_INTERRUPTED_NO_REPLAY',now(),row['vision_id']))
                self.event(con,row,'vision.render.interrupted','recovery',automatic_retry=False)
        for row in rows:
            if self.costs.pending(row['cost_operation_id']):self.costs.settle(row['cost_operation_id'],status='outcome_unknown',error_code='NATIVE_RENDER_VISION_INTERRUPTED_NO_REPLAY')
        return len(rows)
