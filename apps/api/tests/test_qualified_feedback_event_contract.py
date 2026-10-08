"""Wire-schema fixtures only; no provider, Native runtime or audience acceptance."""
import copy,json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator,FormatChecker,ValidationError

ROOT=Path(__file__).resolve().parents[3]
schema=json.loads((ROOT/'packages/contracts/agent-hub-qualified-feedback.v1.schema.json').read_bytes())
validator=Draft202012Validator(schema,format_checker=FormatChecker())
def event():
    project='a'*32;ref='nowa_'+'b'*32;sha='c'*64
    return {'contract_version':'agent-hub-qualified-feedback.v1','event_id':'bevt_'+'d'*48,'event_type':'video.winner.assessed','occurred_at':'2026-10-08T00:00:00+00:00',
      'payload':{'workspace_id':'wsp_explicit_schema_fixture','backend':'windows_native','origin_ref':'qualified-v1:winner:'+project+':'+ref,'execution_controlled_by_video_factory':True,'automatic_action':False,
        'payload_schema_version':'native-qualified-source-event-v1','source_type':'winner','source_kind':'qualified_official_winner','source_ref':ref,'source_sha256':sha,'original_snapshot_sha256':sha,'result_sha256':sha,
        'project_id':project,'publication_id':'nopu_'+'e'*32,'scope_sha256':sha,'source_binding_sha256':sha,'state':'insufficient_data','assessment_score':None,'peer_count':0,'observation_count':1,
        'winner_policy_sha256':sha,'winner_factor_basis_sha256':sha,'channel_baseline_verified':False,'mock':True,'real_audience_observation':False,'source_external_call':False,
        'recommendation_only':True,'automatic_application':False,'publishing_enabled':False,'provider_calls':0,'real_provider_acceptance':False}}
def test_valid_sparse_contract_preserves_nulls_and_legacy_contract_stays_separate():
    Draft202012Validator.check_schema(schema);validator.validate(event())
    legacy=json.loads((ROOT/'packages/contracts/agent-hub-bridge.v1.schema.json').read_bytes())
    assert len(legacy['properties']['event_type']['enum'])==13
    assert 'video.winner.assessed' not in legacy['properties']['event_type']['enum'] and 'video.learning.updated' not in legacy['properties']['event_type']['enum']
    with pytest.raises(ValidationError):Draft202012Validator(legacy).validate(event())
@pytest.mark.parametrize('change',[
    lambda v:v.update(contract_version='agent-hub-bridge.v1'),lambda v:v['payload'].update(mock=1),lambda v:v['payload'].update(automatic_application=0),
    lambda v:v['payload'].update(provider_calls=False),lambda v:v['payload'].update(real_audience_observation=True),lambda v:v['payload'].update(peer_count='0'),
    lambda v:v['payload'].update(assessment_score='72'),lambda v:v['payload'].update(token='NEVER'),lambda v:v.update(event_type='video.winner.detected'),
    lambda v:v['payload'].update(source_type='analytics'),lambda v:v['payload'].update(source_sha256='bad')])
def test_relabel_raw_flags_private_data_counts_and_source_mismatch_refused(change):
    value=event();change(value)
    with pytest.raises(ValidationError):validator.validate(value)
def test_qualified_positive_mock_winner_remains_mock_and_does_not_assert_provider_acceptance():
    value=event();value['event_type']='video.winner.detected';value['payload'].update(state='winner_candidate',assessment_score=82.5,peer_count=5)
    validator.validate(value);assert not value['payload']['real_audience_observation'] and not value['payload']['channel_baseline_verified'] and not value['payload']['real_provider_acceptance']
