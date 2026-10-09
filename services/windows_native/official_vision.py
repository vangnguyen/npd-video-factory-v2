"""Separate one-use official Vision journal; fixture/Session contracts stay intact."""
import asyncio, base64, hashlib, json, re, uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from app.human_identity import HumanPrincipal, HumanAuthVerifier
from app.auto_edit_models import SceneRead, MediaMetadata
from app.openai_vision_provider import VisionResponseObservation
from app.vision_logic import normalize_frames, build_vision_scenes, build_reframe_plans, rank_best_frames
from app.vision_models import VisionFrameRead, VisionSceneRead, ReframePlanRead
from .contracts import WorkflowError, digest
from .backup import guard
from .costs import CostLedger, amount, wire
from .vision import NativeVision
from .vision_models import NativeVisionRequest
from .vision_frame_bridge import NativeEvidenceFrameExtractor
from .vision_registry import NativeVisionFactory, VisionProfile
from .official_vision_models import Analyze, Action
from .official_publications import utc
from .media_frame_analysis import checked_path, validate
from .rights import validate_document as validate_rights
from .rights_override import NativeRightsOverrides, rights_sha, fixture
from .store import now

TABLES = ('native_official_vision_intents', 'native_official_vision_responses', 'native_official_vision_events')
STATUSES = {'not_configured', 'needs_approval', 'approved', 'claimed', 'succeeded', 'failed', 'review_required', 'outcome_unknown', 'cancelled'}


def typed(value, cls):
    try:
        if type(value) is not cls or set(value.__dict__) - set(cls.model_fields): raise ValueError()
        return cls.model_validate(value.model_dump(mode='python', warnings=False))
    except Exception: raise WorkflowError('NATIVE_OFFICIAL_VISION_FIELDS_INVALID', 400) from None


class NativeOfficialVision:
    def __init__(self, vision, *, factories=None, enabled=False, identity_provider=None, clock=lambda: datetime.now(timezone.utc)):
        if type(vision) is not NativeVision or type(enabled) is not bool or identity_provider is not None and not callable(identity_provider):
            raise WorkflowError('NATIVE_OFFICIAL_VISION_CONFIGURATION_INVALID', 400)
        self.vision, self.store, self.config, self.workspace = vision, vision.store, vision.config, vision.workspace
        self.enabled, self.identity_provider, self.clock = enabled, identity_provider, clock
        self.factories = dict(factories or {})
        if (not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', self.workspace) or self.config.data_root.absolute() != self.store.root.absolute()
            or any(type(f) is not NativeVisionFactory or key != f.profile.profile_id or f.workspace != self.workspace or f.root != self.store.root.absolute() for key, f in self.factories.items())):
            raise WorkflowError('NATIVE_OFFICIAL_VISION_CONFIGURATION_INVALID', 400)
        self.costs = CostLedger(self.store)
        self._frozen = (vision, self.store, self.config, self.workspace, self.store.root.absolute(), self.config.data_root.absolute(), enabled, identity_provider, clock, self.costs, tuple(sorted(self.factories.items())))
        self.check()
        with self.store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_official_vision_intents (
                vision_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,
                request_sha256 TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,status TEXT NOT NULL,
                claim_id TEXT,cost_operation_id TEXT,response_id TEXT,result_sha256 TEXT,result_json TEXT,failure_code TEXT,
                actor_ref TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(workspace_id,project_id,key_sha256));
                CREATE TABLE IF NOT EXISTS native_official_vision_responses (
                response_id TEXT PRIMARY KEY,vision_id TEXT NOT NULL,claim_id TEXT NOT NULL,workspace_id TEXT NOT NULL,
                project_id TEXT NOT NULL,cost_operation_id TEXT NOT NULL,observation_json TEXT NOT NULL,observation_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL,UNIQUE(vision_id,claim_id));
                CREATE TABLE IF NOT EXISTS native_official_vision_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,vision_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                action TEXT NOT NULL,actor_ref TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at TEXT NOT NULL);''')
            if con.execute('SELECT 1 FROM native_official_vision_intents WHERE workspace_id!=? LIMIT 1', (self.workspace,)).fetchone():
                raise WorkflowError('NATIVE_OFFICIAL_VISION_WORKSPACE_CHANGED')

    def check(self):
        if (type(self.enabled) is not bool or self.costs.store is not self.store
            or self.vision.store is not self.store or self.vision.config is not self.config or self.vision.workspace != self.workspace
            or (self.vision, self.store, self.config, self.workspace, self.store.root.absolute(), self.config.data_root.absolute(), self.enabled, self.identity_provider, self.clock, self.costs, tuple(sorted(self.factories.items()))) != self._frozen):
            raise WorkflowError('NATIVE_OFFICIAL_VISION_CONFIGURATION_CHANGED')
        path = guard(self.store.root / '.vf-auth-workspace.json')
        try:
            if not path.exists():
                if self.workspace != 'wsp_native_local': raise ValueError()
            elif path.stat().st_size > 512 or json.loads(path.read_bytes()) != {'schema': 'vf-native-workspace-binding-v1', 'workspace_id': self.workspace}: raise ValueError()
        except Exception: raise WorkflowError('NATIVE_OFFICIAL_VISION_WORKSPACE_CHANGED') from None

    def states(self):
        self.check()
        return {'schema_version': 'native-official-vision-runtime-v1', 'workspace_id': self.workspace,
            'enabled': self.enabled, 'profiles': [f.public() for _, f in sorted(self.factories.items())],
            'current_owner_required': True, 'finite_consent_required': True, 'rights_required': True,
            'automatic_dispatch': False, 'automatic_retry': False, 'publishing_enabled': False,
            'real_provider_tested': False, 'owner_uat_accepted': False}

    def identity(self, principal=None, authority=None):
        try:
            verifier = self.identity_provider() if self.identity_provider else None
            if type(verifier) is not HumanAuthVerifier: raise ValueError()
            if principal is not None and (type(principal) is not HumanPrincipal or principal.role_for(self.workspace) != 'owner'): raise ValueError()
            token = principal.token_id if principal is not None else authority['token_id']
            subject = principal.subject if principal is not None else authority['subject']
            record = verifier.registry.tokens.get(token); instant = utc(self.clock())
            if (record is None or not record.enabled or record.subject != subject or utc(record.issued_at) > instant
                or instant >= utc(record.expires_at) or record.not_before is not None and utc(record.not_before) > instant): raise ValueError()
            current = HumanPrincipal(token_id=record.token_id, subject=record.subject, display_name=record.display_name,
                platform_role=record.platform_role, workspace_roles=record.workspace_roles, expires_at=record.expires_at)
            if current.role_for(self.workspace) != 'owner' or principal is not None and current != principal: raise ValueError()
            proof = {'token_id': token, 'subject': subject, 'identity_revision_sha256': digest(record.model_dump(mode='json')),
                'expires_at': utc(record.expires_at).isoformat()}
            if authority is not None and proof != authority: raise ValueError()
            return proof
        except Exception: raise WorkflowError('NATIVE_OFFICIAL_VISION_CURRENT_OWNER_REQUIRED', 403) from None

    def source(self, project, payload, mock):
        validate_rights(project['document'], project_id=project['id'], workspace_id=self.workspace)
        request = NativeVisionRequest(revision=payload.revision, observation_ids=[payload.observation_id], request_key='internal-official-vision-source')
        source = self.vision.sources(project, request)[0]; asset = source['asset']; override = None
        if asset.get('rights_status') == 'restricted' or not mock and fixture(asset): raise WorkflowError('NATIVE_OFFICIAL_VISION_RIGHTS_BLOCKED')
        rights = asset.get('rights_status', 'unknown')
        if mock: kind = 'protocol_mock_only_unverified_rights'
        elif rights in {'owned', 'licensed', 'verified'} and asset.get('rights_review_required') is not True: kind = 'registered_rights'
        else:
            service = getattr(self.store, 'rights_overrides', None)
            if type(service) is not NativeRightsOverrides or service.workspace != self.workspace or service.store is not self.store:
                raise WorkflowError('NATIVE_OFFICIAL_VISION_RIGHTS_REVIEW_REQUIRED')
            override = service.active(project['document'], project['id'], asset)
            if override is None: raise WorkflowError('NATIVE_OFFICIAL_VISION_RIGHTS_REVIEW_REQUIRED')
            kind = 'explicit_owner_override'
        evidence = {'schema_version': 'native-official-vision-rights-v1', 'asset_id': asset['id'], 'asset_sha256': asset['sha256'],
            'rights_sha256': rights_sha(asset), 'rights_status': rights, 'authorization_kind': kind, 'override': override,
            'rights_independently_verified': False, 'publishing_authorized': False}
        bridge = NativeEvidenceFrameExtractor(self.store.root, self.config, project['id'], source)
        return source, evidence, bridge.binding()

    def factory(self, payload):
        self.check(); f = self.factories.get(payload.profile_id)
        if (type(f) is not NativeVisionFactory or f.sha256 != payload.expected_configuration_sha256 or f.mock is not payload.acknowledged_protocol_mock):
            raise WorkflowError('NATIVE_OFFICIAL_VISION_PROFILE_BINDING_CHANGED')
        f.check()
        p = f.profile
        worst = ((Decimal(16384) * max(p.input_vnd_per_million_tokens, p.cached_input_vnd_per_million_tokens)
            + Decimal(8000) * p.output_vnd_per_million_tokens) / Decimal(1000000)).quantize(Decimal('.000001'), rounding=ROUND_CEILING)
        if payload.max_operation_cost_vnd < max(worst, p.estimated_cost_vnd): raise WorkflowError('NATIVE_OFFICIAL_VISION_COST_CEILING_REQUIRED', 400)
        return f

    def event(self, con, row, action, actor, **evidence):
        con.execute('INSERT INTO native_official_vision_events(vision_id,workspace_id,project_id,action,actor_ref,evidence_json,created_at) VALUES(?,?,?,?,?,?,?)',
            (row['vision_id'], self.workspace, row['project_id'], action, actor, json.dumps(evidence), now()))

    def row(self, con, project, identity):
        if con.execute('SELECT 1 FROM projects WHERE id=?', (project,)).fetchone() is None: raise WorkflowError('PROJECT_NOT_FOUND', 404)
        row = con.execute('SELECT * FROM native_official_vision_intents WHERE vision_id=? AND workspace_id=? AND project_id=?', (identity, self.workspace, project)).fetchone()
        if row is None: raise WorkflowError('NATIVE_OFFICIAL_VISION_NOT_FOUND', 404)
        return row

    def read(self, con, row):
        try:
            value = dict(row); snapshot = json.loads(value.pop('snapshot_json')); value.pop('key_sha256')
            payload = Analyze.model_validate({**snapshot['request'], 'request_key': 'internal-official-vision-history'})
            configured_profile = VisionProfile.model_validate(snapshot['configuration']['profile'])
            rights = snapshot['rights']; asset = snapshot['source']['asset']
            if (set(snapshot) != {'schema_version','workspace_id','project_id','request','authority','document_sha256','source','rights','input_binding','configuration','approved_at','deadline','publishing_enabled','automatic_dispatch','owner_uat_accepted'}
                or snapshot['schema_version'] != 'native-official-vision-snapshot-v1' or snapshot['workspace_id'] != self.workspace
                or snapshot['project_id'] != value['project_id'] or digest(snapshot) != value['snapshot_sha256']
                or digest(snapshot['request']) != value['request_sha256'] or value['status'] not in STATUSES
                or any(snapshot[k] is not False for k in ('publishing_enabled','automatic_dispatch','owner_uat_accepted'))
                or snapshot['configuration']['configuration_sha256'] != payload.expected_configuration_sha256
                or snapshot['configuration']['mock'] is not payload.acknowledged_protocol_mock
                or snapshot['configuration']['profile']['profile_id'] != payload.profile_id
                or configured_profile.key_receipt.workspace_id != self.workspace
                or rights['schema_version'] != 'native-official-vision-rights-v1' or rights['asset_id'] != asset['id']
                or rights['asset_sha256'] != asset['sha256'] or rights['rights_sha256'] != rights_sha(asset)
                or rights['rights_status'] != asset.get('rights_status','unknown')
                or rights['rights_independently_verified'] is not False or rights['publishing_authorized'] is not False
                or (rights['authorization_kind'] == 'protocol_mock_only_unverified_rights') is not payload.acknowledged_protocol_mock
                or rights['authorization_kind'] not in {'protocol_mock_only_unverified_rights','registered_rights','explicit_owner_override'}
                or set(snapshot['authority']) != {'token_id','subject','identity_revision_sha256','expires_at'}
                or not re.fullmatch(r'[a-f0-9]{64}',snapshot['authority']['identity_revision_sha256'])
                or (utc(datetime.fromisoformat(snapshot['deadline']))-utc(datetime.fromisoformat(snapshot['approved_at']))).total_seconds() != payload.valid_for_seconds
                or utc(datetime.fromisoformat(snapshot['deadline'])) > utc(datetime.fromisoformat(snapshot['authority']['expires_at']))): raise ValueError()
            observation = validate(snapshot['source']['source_observation'], value['project_id'], snapshot['source']['asset'])
            if observation['observation_id'] != payload.observation_id or snapshot['input_binding']['source_frame_evidence'] != observation['frames']: raise ValueError()
            response = None
            if value['response_id'] is not None:
                raw = con.execute('SELECT * FROM native_official_vision_responses WHERE response_id=?', (value['response_id'],)).fetchone()
                if raw is None or any(raw[k] != value[k] for k in ('vision_id','workspace_id','project_id','claim_id','cost_operation_id')): raise ValueError()
                response = VisionResponseObservation.model_validate(json.loads(raw['observation_json']))
                if digest(response.model_dump(mode='json')) != raw['observation_sha256'] or response.mock_transport is not payload.acknowledged_protocol_mock: raise ValueError()
                cost = con.execute('SELECT * FROM native_cost_operations WHERE id=?',(value['cost_operation_id'],)).fetchone()
                if (cost is None or cost['project_id'] != value['project_id'] or cost['job_id'] is not None
                    or cost['provider'] != 'openai-vision' or cost['model'] != 'gpt-5-mini'
                    or cost['operation'] != 'vision.'+value['claim_id'] or cost['request_sha256'] != value['request_sha256']
                    or amount(cost['estimated_cost']) != payload.max_operation_cost_vnd or cost['actual_cost'] is not None
                    or cost['paid'] != int(not payload.acknowledged_protocol_mock) or cost['external_call'] != int(not payload.acknowledged_protocol_mock)
                    or cost['status'] not in {'dispatch_intent','response_received','outcome_unknown'}): raise ValueError()
                if cost['status'] == 'response_received':
                    receipt = json.loads(cost['receipt'])
                    usage = None if response.input_tokens is None else {'input_tokens':response.input_tokens,'output_tokens':response.output_tokens,'total_tokens':response.input_tokens+response.output_tokens}
                    if receipt['provider_response_sha256'] != response.response_sha256 or receipt['usage'] != usage or receipt['actual_cost_known'] is not False: raise ValueError()
                response = response.model_dump(mode='json')
            result = json.loads(value.pop('result_json')) if value['result_json'] is not None else None
            if (value['status'] == 'succeeded') != (result is not None) or (result is not None) != (value['result_sha256'] is not None): raise ValueError()
            if result is not None:
                frames = [VisionFrameRead.model_validate(v) for v in result['frames']]; scenes = [VisionSceneRead.model_validate(v) for v in result['scenes']]
                provenance = result['adapter_provenance']
                artifacts = [{'frame_index':i,'timestamp_seconds':v['timestamp_seconds'],'evidence_frame_reference':v['reference'],
                    'sha256':v['sha256'],'content_type':'image/png'} for i,v in enumerate(snapshot['input_binding']['source_frame_evidence'])]
                if (digest(result) != value['result_sha256'] or result['schema_version'] != 'native-official-vision-result-v1'
                    or any(result[k] != value[k] for k in ('vision_id','workspace_id','project_id','snapshot_sha256','response_id','cost_operation_id'))
                    or response is None or result['response_sha256'] != response['response_sha256'] or result['mock'] is not payload.acknowledged_protocol_mock
                    or result['semantic_inference_performed'] is not (not payload.acknowledged_protocol_mock)
                    or result['external_provider_calls'] != (0 if payload.acknowledged_protocol_mock else 1)
                    or result['paid_operation_attempted'] is not (not payload.acknowledged_protocol_mock)
                    or provenance['mock_tested'] is not payload.acknowledged_protocol_mock or provenance['external_call'] is not True or provenance['paid'] is not True
                    or provenance['real_provider_tested'] is not False or provenance['secret_recorded'] is not False
                    or provenance['source_checksum'] != asset['sha256'] or provenance['response_sha256'] != response['response_sha256']
                    or provenance['request_sha256'] != response['request_sha256'] or provenance['artifact_evidence'] != artifacts
                    or provenance['cost_receipt']['actual_cost_vnd'] != response['calculated_usage_cost_vnd']
                    or result['source_sha256'] != snapshot['source']['asset']['sha256'] or result['input_binding'] != snapshot['input_binding']
                    or any(result[k] is not False for k in ('automatic_planning_eligible','canonical_timeline_mutated','continuous_tracking_performed','decoded_pts_verified','confidence_calibrated','billing_invoice_verified','publishing_authorized','owner_uat_accepted','real_provider_tested'))
                    or result['subject_tracks'] != [] or result['observed_actual_billed_cost_vnd'] is not None
                    or result['calculated_usage_cost_vnd'] != response['calculated_usage_cost_vnd'] or cost['status'] != 'response_received'
                    or [(v.timestamp_seconds, v.evidence_frame_reference) for v in frames] != [(v['timestamp_seconds'], v['reference']) for v in observation['frames']]
                    or any(v.provider_key != 'openai-vision' or v.model != 'gpt-5-mini' for v in frames)
                    or not set(result['best_frame_ids'] + result['thumbnail_candidate_ids']) <= {v.frame_id for v in frames}
                    or any(not set(v.evidence_frame_ids) <= {f.frame_id for f in frames} for v in scenes)): raise ValueError()
                if len(result['reframe_plans']) != 4 or {p['aspect_ratio'] for p in result['reframe_plans']} != {'9:16','16:9','1:1','4:5'}: raise ValueError()
                expected_plans = build_reframe_plans(frames=frames,tracks=[],metadata=MediaMetadata.model_validate(snapshot['source']['source_media']),
                    aspect_ratios=['9:16','16:9','1:1','4:5'],manual_overrides=[],minimum_tracking_confidence=.7,
                    subtitle_safe_area_bottom=.2,maximum_jump=.15,fingerprint=value['snapshot_sha256'])
                if result['reframe_plans'] != [p.model_dump(mode='json') for p in expected_plans]: raise ValueError()
                for plan in result['reframe_plans']:
                    p = ReframePlanRead.model_validate(plan)
                    if p.fallback != 'center_crop' or not p.needs_attention or p.confidence != 0: raise ValueError()
            return {**value, 'schema_version': 'native-official-vision-intent-v1', 'snapshot': snapshot, 'response': response,
                'result': result, 'needs_approval': value['status'] == 'needs_approval', 'publishing_enabled': False, 'automatic_retry': False, 'owner_uat_accepted': False}
        except Exception: raise WorkflowError('NATIVE_OFFICIAL_VISION_EVIDENCE_INVALID') from None

    def budget_blocked(self, con, project, ceiling, exclude=None):
        limit = amount((project['document'].get('cost_policy') or {}).get('max_ai_cost_vnd'))
        if limit is None: return False
        exposure = Decimal(0)
        for row in con.execute("SELECT * FROM native_cost_operations WHERE project_id=? AND paid=1 AND status!='needs_approval'",(project['id'],)):
            if row['id'] == exclude: continue
            reserved = amount(row['actual_cost'] if row['actual_cost'] is not None else row['estimated_cost'])
            if reserved is None: return True
            exposure += reserved
        return exposure + ceiling > limit

    def create(self, project, payload, *, principal):
        payload = typed(payload, Analyze); request = payload.model_dump(mode='json', exclude={'request_key'})
        key = hashlib.sha256(payload.request_key.encode()).hexdigest(); fingerprint = digest(request)
        with self.store.transaction() as con:
            prior = con.execute('SELECT * FROM native_official_vision_intents WHERE workspace_id=? AND project_id=? AND key_sha256=?', (self.workspace, project, key)).fetchone()
            if prior:
                if prior['request_sha256'] != fingerprint: raise WorkflowError('NATIVE_OFFICIAL_VISION_IDEMPOTENCY_CONFLICT')
                return self.read(con, prior), True
            authority = self.identity(principal); f = self.factory(payload); current = self.store.editable(con, project, payload.revision)
            source, rights, binding = self.source(current, payload, f.mock); stamp = utc(self.clock()); deadline = stamp + timedelta(seconds=payload.valid_for_seconds)
            if deadline > utc(datetime.fromisoformat(authority['expires_at'])): raise WorkflowError('NATIVE_OFFICIAL_VISION_CONSENT_EXCEEDS_IDENTITY', 400)
            status = 'approved' if self.enabled and f.public()['status'] == 'CONFIGURED' else 'not_configured'
            if status == 'approved' and self.budget_blocked(con,current,payload.max_operation_cost_vnd): status = 'needs_approval'
            snapshot = {'schema_version': 'native-official-vision-snapshot-v1', 'workspace_id': self.workspace, 'project_id': project,
                'request': request, 'authority': authority, 'document_sha256': digest(current['document']), 'source': source, 'rights': rights,
                'input_binding': binding, 'configuration': f.public(), 'approved_at': stamp.isoformat(), 'deadline': deadline.isoformat(),
                'publishing_enabled': False, 'automatic_dispatch': False, 'owner_uat_accepted': False}
            identity = 'nvoi_' + uuid.uuid4().hex
            con.execute('INSERT INTO native_official_vision_intents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,self.workspace,project,key,fingerprint,digest(snapshot),json.dumps(snapshot,ensure_ascii=False),status,None,None,None,None,None,None,principal.subject,stamp.isoformat(),stamp.isoformat()))
            row = self.row(con, project, identity); self.event(con,row,'vision.official.consent.recorded',principal.subject,status=status,mock=f.mock,automatic_dispatch=False)
            return self.read(con,row), False

    def fence(self, con, value, claim):
        self.check(); row = self.row(con,value['project_id'],value['vision_id']); snapshot = value['snapshot']
        if row['status'] != 'claimed' or row['claim_id'] != claim or row['snapshot_sha256'] != value['snapshot_sha256']: raise WorkflowError('NATIVE_OFFICIAL_VISION_CLAIM_STOPPED')
        self.identity(authority=snapshot['authority'])
        if not self.enabled or not utc(datetime.fromisoformat(snapshot['approved_at'])) <= utc(self.clock()) < utc(datetime.fromisoformat(snapshot['deadline'])):
            raise WorkflowError('NATIVE_OFFICIAL_VISION_CONSENT_EXPIRED')
        payload = Analyze.model_validate({**snapshot['request'],'request_key':'internal-vision-current-fence'}); f = self.factory(payload)
        if f.public() != snapshot['configuration'] or f.public()['status'] != 'CONFIGURED': raise WorkflowError('NATIVE_OFFICIAL_VISION_PROFILE_CHANGED')
        project = self.store.editable(con,value['project_id'],payload.revision)
        if self.budget_blocked(con,project,payload.max_operation_cost_vnd,row['cost_operation_id']):
            raise WorkflowError('AI_COST_APPROVAL_REQUIRED_BEFORE_DISPATCH')
        source, rights, binding = self.source(project,payload,f.mock)
        if (digest(project['document']) != snapshot['document_sha256'] or source != snapshot['source'] or rights != snapshot['rights'] or binding != snapshot['input_binding']):
            raise WorkflowError('NATIVE_OFFICIAL_VISION_SOURCE_CHANGED')
        return row, f

    def retain(self, value, claim, observation):
        parsed = typed(observation, VisionResponseObservation); raw = parsed.model_dump(mode='json')
        with self.store.transaction() as con:
            row = self.row(con,value['project_id'],value['vision_id'])
            if row['claim_id'] != claim or row['snapshot_sha256'] != value['snapshot_sha256'] or parsed.mock_transport is not value['snapshot']['configuration']['mock']:
                raise WorkflowError('NATIVE_OFFICIAL_VISION_RESPONSE_BINDING_CHANGED')
            prior = con.execute('SELECT * FROM native_official_vision_responses WHERE vision_id=? AND claim_id=?',(value['vision_id'],claim)).fetchone()
            if prior:
                if prior['observation_sha256'] != digest(raw): raise WorkflowError('NATIVE_OFFICIAL_VISION_RESPONSE_CONFLICT')
                identity = prior['response_id']
            else:
                identity = 'nvor_' + uuid.uuid4().hex
                con.execute('INSERT INTO native_official_vision_responses VALUES(?,?,?,?,?,?,?,?,?)',
                    (identity,value['vision_id'],claim,self.workspace,value['project_id'],row['cost_operation_id'],json.dumps(raw),digest(raw),now()))
                con.execute('UPDATE native_official_vision_intents SET response_id=?,updated_at=? WHERE vision_id=?',(identity,now(),value['vision_id']))
                self.event(con,row,'vision.official.complete_response.observed','worker',response_id=identity,mock=parsed.mock_transport)
        if self.costs.pending(row['cost_operation_id']):
            usage = None if parsed.input_tokens is None else {'input_tokens':parsed.input_tokens,'output_tokens':parsed.output_tokens,'total_tokens':parsed.input_tokens+parsed.output_tokens}
            self.costs.settle(row['cost_operation_id'],status='response_received',usage=usage,response_sha256=parsed.response_sha256)

    def process(self, project, identity, payload):
        payload = typed(payload,Action)
        with self.store.transaction() as con:
            row = self.row(con,project,identity); value = self.read(con,row)
            if row['snapshot_sha256'] != payload.expected_snapshot_sha256: raise WorkflowError('NATIVE_OFFICIAL_VISION_SNAPSHOT_CHANGED')
            if row['status'] != 'approved': return value
            claim = 'nvoc_' + uuid.uuid4().hex; operation = 'vision.'+claim
            cost = digest({'project':project,'job':None,'provider':'openai-vision','operation':operation})
            con.execute("UPDATE native_official_vision_intents SET status='claimed',claim_id=?,cost_operation_id=?,updated_at=? WHERE vision_id=?",(claim,cost,now(),identity))
            self.event(con,row,'vision.official.one_use_claim','worker',claim_id=claim)
            value = self.read(con,self.row(con,project,identity))
        started = False
        try:
            with self.store.transaction() as con: _, f = self.fence(con,value,claim)
            request = Analyze.model_validate({**value['snapshot']['request'],'request_key':'internal-vision-dispatch'})
            self.costs.begin(project_id=project,provider='openai-vision',model='gpt-5-mini',operation=operation,
                request_sha256=value['request_sha256'],estimated_cost=wire(request.max_operation_cost_vnd),external_call=not f.mock,paid=not f.mock)
            with self.store.transaction() as con: _, f = self.fence(con,value,claim)
            source = value['snapshot']['source']; bridge = NativeEvidenceFrameExtractor(self.store.root,self.config,project,source)
            def admission():
                with self.store.transaction() as con: self.fence(con,value,claim)
            provider = f.provider(bridge,response_observer=lambda observed:self.retain(value,claim,observed),admission_guard=admission)
            started = True
            async def dispatch():
                return await asyncio.wait_for(provider.analyze(checked_path(self.config,source['asset']),metadata=bridge.input_metadata(),
                    scenes=[SceneRead.model_validate(v) for v in source['scenes']],asset_id=source['asset']['id'],
                    checksum_sha256=source['asset']['sha256'],sample_interval_seconds=1),timeout=120)
            prediction = asyncio.run(dispatch())
            with self.store.transaction() as con:
                row, f = self.fence(con,value,claim); current = self.read(con,row); observation = current['response']
                if (observation is None or prediction.provenance['response_sha256'] != observation['response_sha256']
                    or prediction.provenance['mock_tested'] is not f.mock or prediction.provenance['source_checksum'] != source['asset']['sha256']
                    or prediction.provenance['artifact_evidence'] != [{'frame_index':i,'timestamp_seconds':v['timestamp_seconds'],
                        'evidence_frame_reference':v['reference'],'sha256':v['sha256'],'content_type':'image/png'} for i,v in enumerate(value['snapshot']['input_binding']['source_frame_evidence'])]):
                    raise WorkflowError('NATIVE_OFFICIAL_VISION_RESULT_BINDING_CHANGED')
                frames = normalize_frames(prediction.frames,provider_key='openai-vision',model='gpt-5-mini',fingerprint=value['snapshot_sha256'])
                scenes = build_vision_scenes(scenes=[SceneRead.model_validate(v) for v in source['scenes']],frames=frames,fingerprint=value['snapshot_sha256'])
                plans = build_reframe_plans(frames=frames,tracks=[],metadata=MediaMetadata.model_validate(source['source_media']),aspect_ratios=['9:16','16:9','1:1','4:5'],
                    manual_overrides=[],minimum_tracking_confidence=.7,subtitle_safe_area_bottom=.2,maximum_jump=.15,fingerprint=value['snapshot_sha256'])
                best, thumbs = rank_best_frames(frames)
                result = {'schema_version':'native-official-vision-result-v1','vision_id':identity,'workspace_id':self.workspace,'project_id':project,
                    'snapshot_sha256':value['snapshot_sha256'],'response_id':row['response_id'],'cost_operation_id':cost,'response_sha256':observation['response_sha256'],
                    'source_sha256':source['asset']['sha256'],'input_binding':value['snapshot']['input_binding'],'mock':f.mock,'semantic_inference_performed':not f.mock,
                    'adapter_provenance':prediction.provenance,'external_provider_calls':0 if f.mock else 1,'paid_operation_attempted':not f.mock,
                    'frames':[v.model_dump(mode='json') for v in frames],'scenes':[v.model_dump(mode='json') for v in scenes],
                    'reframe_plans':[v.model_dump(mode='json') for v in plans],'best_frame_ids':best,'thumbnail_candidate_ids':thumbs,'subject_tracks':[],
                    'calculated_usage_cost_vnd':observation['calculated_usage_cost_vnd'],'observed_actual_billed_cost_vnd':None,
                    'automatic_planning_eligible':False,'canonical_timeline_mutated':False,'continuous_tracking_performed':False,'decoded_pts_verified':False,
                    'confidence_calibrated':False,'billing_invoice_verified':False,'publishing_authorized':False,'owner_uat_accepted':False,'real_provider_tested':False}
                con.execute("UPDATE native_official_vision_intents SET status='succeeded',result_json=?,result_sha256=?,updated_at=? WHERE vision_id=?",(json.dumps(result,ensure_ascii=False),digest(result),now(),identity))
                self.event(con,row,'vision.official.result.saved','worker',mock=f.mock,planning_authorized=False)
        except Exception as error:
            code = getattr(error,'code',None)
            if not isinstance(code,str) or not re.fullmatch(r'[A-Z0-9_]{3,120}',code): code = 'NATIVE_OFFICIAL_VISION_OPERATION_STOPPED'
            with self.store.transaction() as con:
                row = self.row(con,project,identity)
                if row['status'] == 'claimed' and row['claim_id'] == claim:
                    uncertain = started and code != 'OPENAI_VISION_DISPATCH_ADMISSION_FAILED'
                    status = 'review_required' if row['response_id'] is not None else 'outcome_unknown' if uncertain else 'needs_approval' if code == 'AI_COST_APPROVAL_REQUIRED_BEFORE_DISPATCH' else 'failed'
                    con.execute('UPDATE native_official_vision_intents SET status=?,failure_code=?,updated_at=? WHERE vision_id=?',(status,code,now(),identity))
                    self.event(con,row,'vision.official.operation.stopped','worker',status=status,failure_code=code,automatic_retry=False)
            if self.costs.pending(cost): self.costs.settle(cost,status='outcome_unknown' if started and code != 'OPENAI_VISION_DISPATCH_ADMISSION_FAILED' else 'rejected',error_code=code)
        return self.get(project,identity)

    def get(self, project, identity):
        with self.store.transaction() as con: return self.read(con,self.row(con,project,identity))

    def cancel(self, project, identity, payload, *, principal):
        payload = typed(payload,Action); self.identity(principal)
        with self.store.transaction() as con:
            row = self.row(con,project,identity)
            if row['snapshot_sha256'] != payload.expected_snapshot_sha256: raise WorkflowError('NATIVE_OFFICIAL_VISION_SNAPSHOT_CHANGED')
            if row['status'] == 'succeeded': raise WorkflowError('NATIVE_OFFICIAL_VISION_ALREADY_COMPLETE')
            if row['status'] != 'cancelled':
                con.execute("UPDATE native_official_vision_intents SET status='cancelled',updated_at=? WHERE vision_id=?",(now(),identity))
                self.event(con,row,'vision.official.cancelled',principal.subject,cancel_is_remote_rollback=False)
            return self.read(con,self.row(con,project,identity))

    def recover(self):
        self.check()
        with self.store.transaction() as con:
            rows = con.execute("SELECT * FROM native_official_vision_intents WHERE workspace_id=? AND status='claimed'",(self.workspace,)).fetchall()
            for row in rows:
                con.execute("UPDATE native_official_vision_intents SET status='outcome_unknown',failure_code='NATIVE_OFFICIAL_VISION_INTERRUPTED_NO_REPLAY',updated_at=? WHERE vision_id=?",(now(),row['vision_id']))
                self.event(con,row,'vision.official.interrupted','recovery',automatic_retry=False)
        for row in rows:
            if self.costs.pending(row['cost_operation_id']): self.costs.settle(row['cost_operation_id'],status='outcome_unknown',error_code='NATIVE_OFFICIAL_VISION_INTERRUPTED_NO_REPLAY')
        return len(rows)
