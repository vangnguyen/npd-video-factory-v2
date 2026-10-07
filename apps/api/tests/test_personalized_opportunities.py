"""Mock planning estimates only; no causal or real-provider performance claims."""
import math
from types import SimpleNamespace
import httpx
import pytest
from pydantic import ValidationError
from app.personalized_opportunities import ChannelRankingPolicy, rank_estimate, request_payload
from app.trend_models import TrendClusterRefreshRequest, TrendCollectionRequest, IdeaGenerateRequest, ContentQueueRefreshRequest
from app.trend_repository import TrendRepository
from app.trend_providers import create_trend_provider_registry
from app.trend_service import TrendIntelligenceService
from app.learning_models import LearningCreate
from app.learning_service import ChannelLearningService
from app.learning_templates import style_signature, subtitle_suggestions
from app.subtitle_templates import template_catalog
from app.production_models import SubtitleStyle
from auth_test_support import TEST_HUMAN_HEADERS
from test_analytics_runtime import runtime_stack
from test_channel_learning import seed_learning_history, learning_app
from test_trend_intelligence import FIXTURE_PATH, FIXTURE_AS_OF


def feedback(difference=60, state='recommendation_candidate'):
    return {'learning_snapshot_id': 'lsn_explicit_fixture', 'content_sha256': 'a' * 64, 'scope': {'mock': True},
        'recommendations': [{'dimension': 'trend_family', 'groups': [{'value': 'tcl_fixture', 'state': state,
            'score_difference': difference, 'snapshot_ids': ['ams_fixture_1', 'ams_fixture_2', 'ams_fixture_3'],
            'control_snapshot_ids': ['ams_fixture_4', 'ams_fixture_5', 'ams_fixture_6']}]}]}


@pytest.mark.parametrize('policy', [dict(history_weight=True), dict(history_weight=.6), dict(history_weight=float('nan')),
    dict(maximum_adjustment_points=26), dict(maximum_adjustment_points=False)])
def test_strict_bounded_history_controls(policy):
    with pytest.raises(ValidationError): ChannelRankingPolicy.model_validate(policy)


@pytest.mark.parametrize('base', [True, float('nan'), float('inf'), -1, 101])
def test_invalid_planning_estimates_do_not_become_rankable(base):
    with pytest.raises(ValueError, match='BASE_SCORE_INVALID'): rank_estimate(base, 'tcl_fixture', feedback())


def test_adjustment_is_bounded_recommendation_only_and_missing_history_stays_null():
    positive = rank_estimate(80, 'tcl_fixture', feedback(100))
    assert positive['personalized_planning_score'] == 95 and positive['history_adjustment_points'] == 15
    assert positive['estimated'] and positive['recommendation_only'] and not positive['autonomous_execution']
    assert positive['history_mock'] and positive['sample_snapshot_ids'] and 'predicted' in positive['limitation']
    negative = rank_estimate(5, 'tcl_fixture', feedback(-100, 'no_positive_association'))
    assert negative['personalized_planning_score'] == 0 and negative['history_adjustment_points'] == -15
    for missing in [None, feedback(None, 'insufficient_data')]:
        result = rank_estimate(80, 'tcl_fixture', missing)
        assert result['personalized_planning_score'] == 80 and result['channel_score_difference'] is result['history_adjustment_points'] is None
        assert result['history_state'] == 'insufficient_data' and result['sample_snapshot_ids'] == []
    assert rank_estimate(80, 'tcl_unknown', feedback())['history_adjustment_points'] is None
    assert rank_estimate(80, 'tcl_fixture', feedback(), ChannelRankingPolicy(history_weight=0.0))['personalized_planning_score'] == 80


def test_unrequested_controls_preserve_legacy_serialized_fingerprints_and_policy_requires_snapshot():
    request = IdeaGenerateRequest()
    legacy = request.model_dump(mode='json', exclude={'learning_snapshot_id', 'learning_policy'})
    assert request_payload(request) == legacy
    with pytest.raises(ValidationError, match='REQUIRES_SNAPSHOT'): IdeaGenerateRequest(learning_policy=ChannelRankingPolicy())
    request = IdeaGenerateRequest(learning_snapshot_id='lsn_explicit_fixture', learning_policy=ChannelRankingPolicy(history_weight=.1))
    assert request_payload(request)['learning_policy']['history_weight'] == .1


async def personalized_history(stack, target, *, subtitle_styles=None):
    learning = ChannelLearningService(stack.repository.session_factory)
    providers = create_trend_provider_registry(FIXTURE_PATH); repository = TrendRepository(stack.repository.session_factory)
    await repository.seed_sources(providers.definitions())
    trend = TrendIntelligenceService(repository, providers, stack.production.platform, learning=learning)
    await trend.collect(stack.publication.workspace_id, TrendCollectionRequest())
    clusters = await trend.refresh_clusters(stack.publication.workspace_id, TrendClusterRefreshRequest(niche=stack.production.project.niche, as_of=FIXTURE_AS_OF))
    assert len(clusters) >= 2
    await seed_learning_history(stack, target, family_ids=[clusters[0].cluster_id, clusters[1].cluster_id], subtitle_styles=subtitle_styles)
    saved, _ = await learning.create(stack.publication.project_id, LearningCreate(publication_id=stack.publication.publication_id), actor='fixture', key='personalized-learning-history-fixture')
    return learning, trend, saved, clusters


@pytest.mark.asyncio
async def test_history_changes_proposal_ranking_with_exact_persisted_evidence_and_no_execution(runtime_stack):
    stack, _, current, calls, _, _ = runtime_stack
    learning, trend, saved, before = await personalized_history(stack, current[0])
    policy = ChannelRankingPolicy(history_weight=.5, maximum_adjustment_points=25.0)
    after = await trend.list_clusters(saved.workspace_id, learning_snapshot_id=saved.learning_snapshot_id, niche=saved.scope['niche'], learning_policy=policy)
    by_id = {item.cluster_id: item for item in after}
    first = by_id[before[0].cluster_id]; second = by_id[before[1].cluster_id]
    a = first.learning_feedback['personalized_opportunity']; b = second.learning_feedback['personalized_opportunity']
    assert a['history_adjustment_points'] > 0 and b['history_adjustment_points'] < 0
    assert first.score.total_score == before[0].score.total_score and a['learning_content_sha256'] == saved.content_sha256
    assert a['sample_snapshot_ids'] and a['control_snapshot_ids']
    request = ContentQueueRefreshRequest(niche=saved.scope['niche'], learning_snapshot_id=saved.learning_snapshot_id, learning_policy=policy)
    queue = await trend.refresh_queue(saved.workspace_id, request)
    assert queue and [item.score for item in queue] == sorted((item.score for item in queue), reverse=True)
    for item in queue:
        evidence = item.provenance['personalized_estimate']
        assert evidence['personalized_planning_score'] == item.score and evidence['learning_snapshot_id'] == saved.learning_snapshot_id
        assert item.idea.brief['personalized_estimate']['ranking_policy'] == policy.model_dump(mode='json')
        assert item.state == 'proposed' and not item.provenance['execution']
    replay = await trend.refresh_queue(saved.workspace_id, request)
    assert [item.queue_item_id for item in replay] == [item.queue_item_id for item in queue]
    alternative = await trend.refresh_queue(saved.workspace_id, request.model_copy(update={'learning_policy': ChannelRankingPolicy(history_weight=0.0)}))
    assert alternative[0].queue_run_id != queue[0].queue_run_id
    assert all(item.provenance['personalized_estimate']['history_adjustment_points'] in (None, 0) for item in alternative)
    assert (await learning.get(saved.workspace_id, saved.learning_snapshot_id)) == saved and len(calls) == 3


@pytest.mark.asyncio
async def test_readonly_api_provides_ranked_snapshot_scope_and_rejects_wrong_niche(runtime_stack):
    from fastapi import Depends
    from app.human_auth import authorize_human_request
    from app.trend_routes import router
    stack, _, current, _, _, _ = runtime_stack
    _, trend, saved, _ = await personalized_history(stack, current[0])
    app = learning_app(stack); app.state.trend_intelligence_service = trend; app.include_router(router, dependencies=[Depends(authorize_human_request)])
    endpoint = f'/api/v1/workspaces/{saved.workspace_id}/trend-clusters'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://fixture', headers=TEST_HUMAN_HEADERS) as client:
        reply = await client.get(endpoint, params={'learning_snapshot_id': saved.learning_snapshot_id, 'history_weight': .5, 'niche': saved.scope['niche']})
        assert reply.status_code == 200 and reply.headers['Cache-Control'] == 'no-store'
        assert all(item['learning_feedback']['personalized_opportunity']['estimated'] for item in reply.json())
        assert (await client.get(endpoint, params={'history_weight': .5})).status_code == 422
        assert (await client.get(endpoint, params={'learning_snapshot_id': saved.learning_snapshot_id, 'niche': 'technology'})).status_code == 409
        assert (await client.get(endpoint, params={'learning_snapshot_id': saved.learning_snapshot_id, 'history_weight': .9})).status_code == 422


@pytest.mark.asyncio
async def test_supported_style_association_maps_to_available_template_and_requires_explicit_save(runtime_stack):
    stack, _, current, calls, _, _ = runtime_stack
    catalog = template_catalog(); sentence = next(item for item in catalog['templates'] if item['template_ref'] == 'sentence-clean@v1')
    fade = next(item for item in catalog['templates'] if item['template_ref'] == 'animated-fade@v1')
    _, _, saved, _ = await personalized_history(stack, current[0], subtitle_styles=[sentence['style'], fade['style']])
    package_before = await stack.production.service.get(stack.publication.project_id)
    result = subtitle_suggestions(saved, package_before)
    assert result['suggestions'] and result['suggestions'][0]['template_ref'] == 'sentence-clean@v1'
    suggestion = result['suggestions'][0]
    assert suggestion['source_style_signature'] == style_signature(sentence['style']) and suggestion['selectable']
    assert not suggestion['historical_template_identity_verified'] and not result['automatic_application']
    assert not subtitle_suggestions(saved, None)['suggestions'][0]['selectable']
    app = learning_app(stack); app.state.production_package_service = stack.production.service
    endpoint = f'/api/v1/projects/{stack.publication.project_id}/analytics/learning-snapshots/{saved.learning_snapshot_id}/subtitle-suggestions'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://fixture', headers=TEST_HUMAN_HEADERS) as client:
        response = await client.get(endpoint)
        assert response.status_code == 200 and response.headers['Cache-Control'] == 'no-store'
        assert response.json()['project_id'] == stack.publication.project_id
    assert await stack.production.service.get(stack.publication.project_id) == package_before and len(calls) == 3


@pytest.mark.asyncio
async def test_word_timed_suggestion_is_disabled_without_alignment_and_unknown_style_is_not_invented(runtime_stack):
    stack, _, current, _, _, _ = runtime_stack
    catalog = template_catalog(); word = next(item for item in catalog['templates'] if item['template_ref'] == 'word-focus@v1')
    sentence = next(item for item in catalog['templates'] if item['template_ref'] == 'sentence-clean@v1')
    _, _, saved, _ = await personalized_history(stack, current[0], subtitle_styles=[word['style'], sentence['style']])
    package = await stack.production.service.get(stack.publication.project_id)
    package = package.model_copy(deep=True)
    for cue in package.subtitle.cues: cue.words = []
    result = subtitle_suggestions(saved, package)
    word_result = next(item for item in result['suggestions'] if item['template_ref'] == 'word-focus@v1')
    assert not word_result['selectable'] and word_result['attention'] == 'WORD_TIMESTAMPS_REQUIRED'
    changed = saved.model_copy(deep=True)
    next(item for item in changed.dimensions if item.dimension == 'subtitle_style').groups[0].value = 'unknown:fixture:style:signature'
    assert subtitle_suggestions(changed, package)['unmatched_historical_styles'] == ['unknown:fixture:style:signature']
