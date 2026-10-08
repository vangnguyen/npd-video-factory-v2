"""Explicit immutable projection of qualified channel learning into local planning."""
import copy, sqlite3
from contextlib import nullcontext
from typing import Literal
from pydantic import Field, StrictBool, ValidationError, field_validator
from app.models import StrictModel
from app.learning_templates import style_signature
from app.subtitle_templates import CATALOG, template_catalog
from .contracts import WorkflowError, digest, file_sha,canonical
from .channel_profiles import select, resolve
from .official_learning import NativeOfficialLearning
from .trend_radar import NativeTrendRadar

SCHEMA = 'native-qualified-learning-feedback-v1'
CONTEXT = 'native-qualified-learning-context-v1'
CONSUMERS = {'trend_radar': ('trend_family',), 'idea_engine': ('hook', 'duration'),
             'media_planner': ('visual_strategy', 'voice_profile', 'duration'),
             'template_recommendations': ('subtitle_style',)}
LIMITATIONS = [
    'Descriptive channel associations support reviewed experiments, without causal or future performance claims.',
    'Every consumer retains the qualified original learning, assessment, response-cost and frozen render-feature lineage.',
    'An explicit selected account/report/policy scope is not exhaustive channel history or account totals.',
    'Protocol mocks cannot rank real trend signals or become real audience feedback.',
    'Unknown publishing windows, costs and features remain unavailable; no media or budget is changed.',
    'Template suggestions match only the recorded reference or style fields; full historical style equivalence is unverified.']

class Create(StrictModel):
    schema_version: Literal['native-qualified-learning-feedback-request-v1'] = 'native-qualified-learning-feedback-request-v1'
    project_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    learning_id: str = Field(pattern=r'^nols_[a-f0-9]{32}$')
    expected_learning_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    channel_profile_ref: str = Field(pattern=r'^[a-z][a-z0-9-]{2,60}@[1-9][0-9]*$')
    platform: Literal['youtube', 'tiktok', 'instagram_reels', 'facebook'] = 'youtube'
    acknowledged_recommendation_only: Literal[True]
    acknowledged_protocol_mock: StrictBool = False
    request_key: str = Field(pattern=r'^[A-Za-z0-9_-]{16,100}$')

    @field_validator('acknowledged_recommendation_only', mode='before')
    @classmethod
    def raw_ack(cls, value):
        if value is not True: raise ValueError('Explicit recommendation acknowledgement required')
        return value

def source_binding(value):
    s = value['snapshot']
    return {'project_id': value['project_id'], 'learning_id': value['learning_id'],
            'learning_sha256': value['snapshot_sha256'], 'publication_id': value['publication_id'],
            'anchor_assessment_id': value['anchor_assessment_id'],
            'anchor_assessment_sha256': s['request']['expected_assessment_sha256'],
            'anchor_candidate_sha256': s['anchor_candidate_sha256'],
            'anchor_result_snapshot_id': value['anchor_result_snapshot_id'],
            'winner_policy_sha256': s['winner_policy_sha256'],
            'winner_factor_basis_sha256': s['winner_factor_basis_sha256']}

def content(request, source, selection, authority):
    scope = source['snapshot']['scope']
    if (source['snapshot_sha256'] != request.expected_learning_sha256
        or source['project_id'] != request.project_id or source['learning_id'] != request.learning_id):
        raise WorkflowError('NATIVE_QUALIFIED_LEARNING_SOURCE_CHANGED', 409)
    if request.acknowledged_protocol_mock is not source['mock']:
        raise WorkflowError('NATIVE_QUALIFIED_LEARNING_MOCK_ACK_REQUIRED', 409)
    resolve({'channel_profile': selection, 'niche': scope['niche']})
    if (scope['workspace_id'] != source['workspace_id'] or scope['channel_profile_ref'] != request.channel_profile_ref
        or scope['channel_profile_ref'] != selection['profile']['profile_ref']
        or scope['channel_profile_sha256'] != selection['profile_sha256']
        or scope['platform'] != request.platform or scope['niche'] != selection['profile']['niche_profile']['niche']):
        raise WorkflowError('NATIVE_QUALIFIED_LEARNING_SCOPE_MISMATCH', 409)
    return {'schema_version': SCHEMA, 'request': request.model_dump(mode='json', exclude={'request_key'}),
            'request_sha256': digest(request.model_dump(mode='json', exclude={'request_key'})),
            'source_binding': source_binding(source), 'scope': copy.deepcopy(scope),
            'channel_selection': copy.deepcopy(selection), 'authority': copy.deepcopy(authority),
            'actor_ref': authority['token_id'], 'status': source['status'],
            'observation_count': source['observation_count'], 'recommendations': copy.deepcopy(source['dimensions']),
            'consumers': {name: [copy.deepcopy(d) for d in source['dimensions'] if d['dimension'] in dimensions]
                          for name, dimensions in CONSUMERS.items()},
            'candidate_rows_truncated': source['snapshot']['candidate_rows_truncated'],
            'selected_posts_truncated': source['snapshot']['selected_posts_truncated'],
            'excluded_rows': copy.deepcopy(source['snapshot']['excluded_rows']),
            'mock': source['mock'], 'real_audience_observation': source['real_audience_observation'],
            'recommendation_only': True, 'automatic_production': False, 'autonomous_execution': False,
            'automatic_application': False, 'publishing_enabled': False, 'provider_calls': 0,
            'external_call': False, 'token_returned': False, 'real_provider_tested': False,
            'limitations': LIMITATIONS}

def context(record):
    p = record['payload']
    value = {'schema_version': CONTEXT, 'projection_id': record['id'], 'projection_sha256': digest(record),
             'workspace_id': record['workspace_id'], 'source_binding': copy.deepcopy(p['source_binding']),
             'scope': copy.deepcopy(p['scope']), 'consumers': copy.deepcopy(p['consumers']),
             'status': p['status'], 'observation_count': p['observation_count'],
             'mock': p['mock'], 'real_audience_observation': p['real_audience_observation'],
             'recommendation_only': True, 'automatic_application': False, 'provider_calls': 0,
             'publishing_enabled': False, 'limitations': LIMITATIONS}
    return {**value, 'sha256': digest(value)}

def from_run_context(value):
    return (((value or {}).get('trend_radar') or {}).get('assessment') or {}).get('payload', {}).get('learning_feedback')

def idea_recommendations(feedback):
    return {'schema_version':'native-qualified-idea-recommendations-v1',
        'projection_id':feedback['projection_id'],'projection_sha256':feedback['projection_sha256'],
        'source_binding':copy.deepcopy(feedback['source_binding']),'mock':feedback['mock'],
        'real_audience_observation':feedback['real_audience_observation'],
        'dimensions':copy.deepcopy(feedback['consumers']['idea_engine']),'recommendation_only':True,
        'automatic_selection':False,'limitation':feedback['limitations'][0]}

def validate_context(value, record=None):
    try:
        if (value['schema_version'] != CONTEXT or value['sha256'] != digest({k:v for k,v in value.items() if k!='sha256'})
            or value['recommendation_only'] is not True or value['automatic_application'] is not False
            or type(value['mock']) is not bool or value['real_audience_observation'] is not (not value['mock'])
            or value['provider_calls'] != 0 or type(value['provider_calls']) is not int or value['publishing_enabled'] is not False
            or value['scope']['workspace_id'] != value['workspace_id'] or value['scope']['mock'] is not value['mock']
            or set(value['consumers']) != set(CONSUMERS) or value['limitations'] != LIMITATIONS
            or record is not None and context(record) != value): raise ValueError()
        return value
    except (ValueError, TypeError, KeyError): raise WorkflowError('NATIVE_QUALIFIED_LEARNING_CONTEXT_CHANGED') from None

def qualified_context(service, value, *, source_con=None):
    if type(service) is not NativeQualifiedLearningFeedback:
        raise WorkflowError('NATIVE_QUALIFIED_LEARNING_NOT_CONFIGURED', 409)
    validate_context(value)
    record = service.get(value['projection_id'], source_con=source_con)
    return validate_context(value, record)

class NativeQualifiedLearningFeedback:
    def __init__(self, learning, radar):
        if (type(learning) is not NativeOfficialLearning or type(radar) is not NativeTrendRadar
            or learning.store is not radar.analytics.store or learning.workspace != radar.workspace):
            raise WorkflowError('NATIVE_QUALIFIED_LEARNING_CONFIGURATION_INVALID', 400)
        self.learning, self.radar = learning, radar
        self.store, self.workspace = radar.store, radar.workspace
        self.frozen = (learning, radar, self.store, self.workspace, learning.store.root.absolute(), self.store.root.absolute())
        self.check()

    def check(self):
        if ((self.learning, self.radar, self.store, self.workspace,
            self.learning.store.root.absolute(), self.store.root.absolute()) != self.frozen
            or self.radar.store is not self.store or self.radar.workspace != self.workspace
            or self.radar.analytics.store is not self.learning.store):
            raise WorkflowError('NATIVE_QUALIFIED_LEARNING_CONFIGURATION_CHANGED')
        self.learning.check()

    def read(self, record, source_con=None):
        self.check()
        try:
            if record['workspace_id'] != self.workspace or record['record_type'] != 'learning' or record['version'] != 1:
                raise ValueError()
            p = record['payload']
            request = Create.model_validate({**p['request'], 'request_key': 'internal-qualified-learning-key'})
            with (self.learning.store.transaction() if source_con is None else nullcontext(source_con)) as source:
                original = self.learning.read(source, self.learning.row(source, request.project_id, request.learning_id))
                expected = content(request, original, p['channel_selection'], p['authority'])
            if canonical(p) != canonical(expected) or p['schema_version'] != SCHEMA or record['provenance'] != {
                'origin': 'native-trend-radar-v1', 'recommendation_only': True, 'automatic_production': False}:
                raise ValueError()
            return record
        except (ValueError, TypeError, KeyError, ValidationError):
            raise WorkflowError('NATIVE_QUALIFIED_LEARNING_EVIDENCE_CHANGED') from None

    def create(self, payload, *, principal):
        self.check()
        if not isinstance(payload, Create): payload = Create.model_validate(payload)
        authority = self.learning.winners.analytics.identity(principal)
        # The consistent order is intelligence -> workflow. No workflow write is performed.
        with self.store.transaction() as con:
            identifier, request, prior = self.radar.replay(con, 'qualified-learning', payload)
            if prior:
                self.read(prior)
                self.learning.winners.analytics.identity(authority=authority)
                return prior, True
            selection = select(payload.channel_profile_ref)
            with self.learning.store.transaction() as source:
                original = self.learning.read(source, self.learning.row(source, payload.project_id, payload.learning_id))
                value = content(payload, original, selection, authority)
                self.learning.winners.analytics.identity(authority=authority)
                record = self.radar.put('learning', value, con, identifier)
                self.store.decision(con, identifier, 'human_projected_qualified_channel_learning', {
                    'actor_ref': authority['token_id'], 'source_binding': source_binding(original),
                    'mock': original['mock'], 'observation_count': original['observation_count'],
                    'recommendation_only': True, 'provider_calls': 0})
                bridge=getattr(self.store,'bridge',None)
                if bridge is not None:bridge.capture_projection(con,self,record,source)
            return record, False

    def get(self, identifier, *, source_con=None):
        self.check()
        # A WAL read snapshot never takes the intelligence writer lock. A planner
        # already holding the workflow transaction can reuse it without reversing
        # the intelligence -> workflow writer lock order or nesting BEGIN.
        con = sqlite3.connect(self.store.db.as_uri()+'?mode=ro', uri=True, timeout=15)
        con.row_factory = sqlite3.Row
        try:
            con.execute('PRAGMA query_only=ON'); con.execute('BEGIN')
            record = self.store.get(identifier, 'RadarRecord', con)
            return self.read(record, source_con=source_con)
        finally: con.close()

    def suggestions(self, identifier):
        record = self.get(identifier)
        p = record['payload']; catalog = template_catalog(); suggestions = []; unmatched = []
        for d in p['consumers']['template_recommendations']:
            for group in d['groups']:
                if group['state'] != 'recommendation_candidate': continue
                matches = [t for t in catalog['templates'] if t['template_ref'] == group['value'] or style_signature(t['style']) == group['value']]
                if not matches: unmatched.append(group['value'])
                for template in matches:
                    suggestions.append({'template_ref': template['template_ref'], 'name': template['name'],
                        'style': copy.deepcopy(template['style']), 'requires_word_timestamps': template['requires_word_timestamps'],
                        'recorded_subtitle_feature': group['value'], 'historical_full_style_verified': False,
                        'match_kind': 'recorded_template_reference' if template['template_ref'] == group['value'] else 'recorded_style_fields_only', 'sample_count': group['sample_count'],
                        'control_count': group['control_count'], 'score_difference': group['score_difference'],
                        'snapshot_ids': group['snapshot_ids'], 'control_snapshot_ids': group['control_snapshot_ids'],
                        'human_selection_required': True, 'automatic_application': False})
        suggestions.sort(key=lambda t: (-t['score_difference'], t['template_ref']))
        return {'schema_version': 'native-qualified-learning-template-suggestions-v1',
            'workspace_id': self.workspace, 'projection_id': record['id'], 'projection_sha256': digest(record),
            'source_binding': p['source_binding'], 'catalog_version': catalog['version'], 'catalog_sha256': file_sha(CATALOG),
            'suggestions': suggestions[:100], 'suggestions_truncated': len(suggestions) > 100,
            'unmatched_historical_styles': unmatched, 'mock': p['mock'], 'real_audience_observation': p['real_audience_observation'],
            'recommendation_only': True, 'automatic_application': False, 'human_selection_required': True,
            'provider_calls': 0, 'publishing_enabled': False, 'token_returned': False,
            'limitation': LIMITATIONS[-1]}
