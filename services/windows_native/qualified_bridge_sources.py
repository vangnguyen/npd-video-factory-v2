"""Provider-free original source readers for separately versioned Bridge events."""
from contextlib import nullcontext
from .contracts import WorkflowError,digest
from .official_analytics import NativeOfficialAnalytics
from .official_analytics_models import Collect
from .official_winners import NativeOfficialWinners
from .official_learning import NativeOfficialLearning
from .qualified_learning_feedback import NativeQualifiedLearningFeedback
from app.bridge_auth import canonical_json_bytes

VERSION='native-qualified-source-event-v1'
CONTRACT='agent-hub-qualified-feedback.v1'
EVENTS=('video.analytics.updated','video.winner.assessed','video.winner.detected','video.learning.updated')
TYPES={'analytics':NativeOfficialAnalytics,'winner':NativeOfficialWinners,'learning':NativeOfficialLearning,'projection':NativeQualifiedLearningFeedback}
KINDS={'analytics':'qualified_official_analytics','winner':'qualified_official_winner','learning':'qualified_official_learning','projection':'qualified_learning_projection'}
REFS={'analytics':'sync_id','winner':'assessment_id','learning':'learning_id','projection':'id'}

class QualifiedSources:
    def __init__(self,bridge):self.bridge=bridge;self.services={}
    def bind(self,**services):
        for kind,service in services.items():
            if kind not in TYPES or type(service) is not TYPES[kind]:raise WorkflowError('NATIVE_BRIDGE_QUALIFIED_SOURCE_INVALID')
            self.check(kind,service,chain=False)
        self.services.update(services)
    def check(self,kind,service,chain=True):
        if kind not in TYPES or type(service) is not TYPES[kind]:raise WorkflowError('NATIVE_BRIDGE_QUALIFIED_SOURCE_INVALID')
        bridge=self.bridge;store=service.learning.store if kind=='projection' else service.store
        if store is not bridge.store or service.workspace!=bridge.workspace or store.root.absolute()!=bridge.store.root.absolute():raise WorkflowError('NATIVE_BRIDGE_QUALIFIED_SOURCE_INVALID')
        service.check()
        if kind=='projection' and (bridge.intelligence is not service.store or service.radar.intelligence.store is not bridge.intelligence):raise WorkflowError('NATIVE_BRIDGE_QUALIFIED_SOURCE_INVALID')
        expected={'winner':('analytics',getattr(service,'analytics',None)),'learning':('winner',getattr(service,'winners',None)),'projection':('learning',getattr(service,'learning',None))}.get(kind)
        if chain and expected and self.services.get(expected[0]) is not expected[1]:raise WorkflowError('NATIVE_BRIDGE_QUALIFIED_SOURCE_CONFIGURATION_CHANGED')
    def read(self,kind,project,identity,con=None,record=None):
        service=self.services.get(kind)
        if service is None:raise WorkflowError('NATIVE_BRIDGE_QUALIFIED_SOURCE_NOT_CONFIGURED')
        self.check(kind,service)
        with (self.bridge.store.transaction() if con is None else nullcontext(con)) as source:
            if kind=='analytics':
                value=service.get(project,identity,con=source)
                if value['status']!='succeeded' or value['result'] is None:raise WorkflowError('NATIVE_BRIDGE_QUALIFIED_ANALYTICS_REQUIRED')
                request=Collect.model_validate({**value['snapshot']['request'],'request_key':'internal-qualified-bridge-source-key'})
                _,proof=service.source(project,request,value['result']['features']['captured_at'],con=source)
                if proof!=value['snapshot']['source']:raise WorkflowError('NATIVE_BRIDGE_QUALIFIED_SOURCE_CHANGED')
            elif kind=='winner':value=service.read(source,service.row(source,project,identity))
            elif kind=='learning':value=service.read(source,service.row(source,project,identity))
            else:
                value=service.read(record,source_con=source) if record is not None else service.get(identity,source_con=source)
                if value['payload']['source_binding']['project_id']!=project:raise WorkflowError('NATIVE_BRIDGE_QUALIFIED_SOURCE_CHANGED')
        return value
    def payload(self,kind,value):
        if kind=='projection':
            p=value['payload'];binding=p['source_binding'];project=binding['project_id'];publication=binding['publication_id'];scope=p['scope'];mock=p['mock'];snapshot=digest(value);result=snapshot
            state=p['status'];score=None;peers=None;count=p['observation_count'];baseline=None;binding_sha=digest(binding);basis=binding['winner_factor_basis_sha256'];policy=binding['winner_policy_sha256'];stamp=value['updated_at'];ref=value['id']
        else:
            p=value['snapshot'];project=value['project_id'];publication=value['publication_id'];mock=value['mock'];snapshot=value['snapshot_sha256'];ref=value[REFS[kind]]
            if kind=='analytics':
                r=value['result'];f=r['features']['evidence'];scope={'target_binding_sha256':p['target_binding_sha256'],'platform':r['platform'],'provider_key':r['provider_key'],'source_kind':r['source_kind'],'mock':mock,'source_external_call':r['external_call'],
                    'query':p['request']['query'],'channel_profile_ref':f.get('channel_profile_ref'),'channel_profile_sha256':f.get('channel_profile_sha256')}
                result=digest(r);state=value['status'];score=None;peers=None;count=1;baseline=None;binding_sha=digest(p['source']);basis=policy=None;stamp=r['collected_at']
            elif kind=='winner':
                scope=p['candidate']['scope'];result=digest(value['assessment']);state=value['assessment']['state'];score=value['assessment']['score'];peers=value['peer_count'];count=1;baseline=value['assessment']['channel_baseline_verified']
                binding_sha=digest(p['candidate']);basis=NativeOfficialLearning.basis(value);policy=p['policy_sha256'];stamp=value['created_at']
            else:
                scope=p['scope'];result=digest(value['dimensions']);state=value['status'];score=None;peers=None;count=value['observation_count'];baseline=None;binding_sha=digest({'anchor_assessment_id':value['anchor_assessment_id'],'anchor_assessment_sha256':p['request']['expected_assessment_sha256'],'selected_assessments':p['selected_assessments']})
                basis=p['winner_factor_basis_sha256'];policy=p['winner_policy_sha256'];stamp=value['created_at']
        if type(mock) is not bool or scope.get('mock') is not mock:raise WorkflowError('NATIVE_BRIDGE_QUALIFIED_SOURCE_CHANGED')
        return {'payload_schema_version':VERSION,'source_type':kind,'source_kind':KINDS[kind],'source_ref':ref,'source_sha256':digest(value),'original_snapshot_sha256':snapshot,'result_sha256':result,
            'project_id':project,'publication_id':publication,'scope_sha256':digest(scope),'source_binding_sha256':binding_sha,'state':state,'assessment_score':score,'peer_count':peers,'observation_count':count,
            'winner_policy_sha256':policy,'winner_factor_basis_sha256':basis,'channel_baseline_verified':baseline,'mock':mock,'real_audience_observation':not mock,'source_external_call':scope['source_external_call'],
            'recommendation_only':True,'automatic_application':False,'publishing_enabled':False,'provider_calls':0,'real_provider_acceptance':False},stamp
    @staticmethod
    def events(kind,payload):
        if kind=='analytics':return ('video.analytics.updated',)
        if kind=='winner':return ('video.winner.assessed','video.winner.detected') if payload['state']=='winner_candidate' else ('video.winner.assessed',)
        return ('video.learning.updated',)
    def envelope(self,kind,value,event_type):
        payload,stamp=self.payload(kind,value)
        if event_type not in self.events(kind,payload):raise WorkflowError('NATIVE_BRIDGE_QUALIFIED_EVENT_TYPE_INVALID')
        origin='qualified-v1:'+kind+':'+payload['project_id']+':'+payload['source_ref']
        envelope=self.bridge.envelope(event_type,origin,payload,stamp);envelope['contract_version']=CONTRACT;return envelope
    def validate(self,value,con=None):
        p=value['payload'];kind=p.get('source_type')
        if p.get('payload_schema_version')!=VERSION or kind not in TYPES:raise WorkflowError('NATIVE_BRIDGE_QUALIFIED_SOURCE_CHANGED')
        original=self.read(kind,p.get('project_id'),p.get('source_ref'),con)
        if canonical_json_bytes(value)!=canonical_json_bytes(self.envelope(kind,original,value['event_type'])):raise WorkflowError('NATIVE_BRIDGE_QUALIFIED_SOURCE_CHANGED')
