"""Meta official wire/normalization contracts, explicit protocol fixtures only."""
from dataclasses import replace
from datetime import timedelta
import json

import httpx
import pytest

from app import analytics_meta as meta
from app.analytics_official import AnalyticsOfficialError
from app.analytics_providers import AnalyticsRateLimited
from app.db import utc_now
from app.publishing_models import PublishingTargetBinding
from app.publishing_profiles import PROVIDER_KEYS
from app.publishing_wire import OfficialRequest, OfficialResponse, PublishingWireError


def target(platform='instagram_reels'):
    return PublishingTargetBinding(workspace_id='wsp_meta_analytics_fixture', profile_id='ppf_meta_read_fixture',
        profile_version=1, platform=platform, provider_key=PROVIDER_KEYS[platform],
        target_account_id='17890000000000001' if platform == 'instagram_reels' else '100000000000001',
        credential_binding_sha256='a'*64)


def credential(platform='instagram_reels', **changes):
    return meta.MetaAnalyticsCredential(**{'target': target(platform), 'api_version': 'v26.0',
        'page_id': '100000000000001', 'expires_at': utc_now()+timedelta(hours=1),
        'scopes': meta.SCOPES[platform], 'token': 'EXPLICIT-META-READ-FIXTURE-NOT-A-SECRET', **changes})


def response(value, status=200, headers=None):
    return OfficialResponse(status, headers or {}, json.dumps(value).encode())


REMOTE = '18000000000000001'


def ig_table(values=None):
    values = {'views': 123, 'reach': 100, 'likes': 4, 'comments': 0, 'shares': 2, 'saved': 3} if values is None else values
    return {'data': [{'id': f'{REMOTE}/insights/{name}/lifetime', 'name': name, 'period': 'lifetime',
        'values': [{'value': value}]} for name, value in values.items()]}


def fb_table(**changes):
    return {'id': REMOTE, 'from': {'id': target('facebook').target_account_id}, 'views': 55,
        'likes': {'data': [], 'summary': {'total_count': 3}},
        'comments': {'data': [], 'summary': {'total_count': 0}}, **changes}


def test_meta_authentication_uses_page_token_me_and_its_linked_instagram_account():
    current = credential();request = meta.account_request(current)
    assert httpx.URL(request.url).path == '/v26.0/me'
    assert dict(httpx.URL(request.url).params) == {'fields': 'id,instagram_business_account'}
    assert request.headers['Authorization'].endswith(current.token)
    assert current.token not in request.url+repr(current)+repr(request)
    good = {'id': current.page_id, 'instagram_business_account': {'id': current.target.target_account_id}}
    assert meta.confirm_account(response(good), current.target, page_id=current.page_id)['authenticated_page_match']
    for changed in ({**good, 'id': '222'}, {**good, 'instagram_business_account': {'id': '333'}}):
        with pytest.raises(AnalyticsOfficialError, match='ACCOUNT_NOT_CONFIRMED'):
            meta.confirm_account(response(changed), current.target, page_id=current.page_id)


@pytest.mark.parametrize('platform', ['instagram_reels', 'facebook'])
def test_credentials_require_exact_target_expiry_read_scopes_and_explicit_version(platform):
    current = credential(platform)
    assert meta.resolve_credential(lambda _: current, current.target) == current
    for changes in ({'api_version': ''}, {'page_id': 'not-numeric'}, {'scopes': frozenset({'pages_manage_posts'})},
                    {'expires_at': utc_now().replace(tzinfo=None)}):
        with pytest.raises(AnalyticsOfficialError, match='OAUTH_INVALID'): replace(current, **changes)
    with pytest.raises(AnalyticsOfficialError, match='REFRESH_REQUIRED'):
        meta.resolve_credential(lambda _: replace(current, expires_at=utc_now()), current.target)
    with pytest.raises(AnalyticsOfficialError, match='SCOPES_REQUIRED'):
        meta.resolve_credential(lambda _: replace(current, scopes=frozenset({'pages_show_list'})), current.target)
    with pytest.raises(AnalyticsOfficialError, match='TARGET_MISMATCH'):
        meta.resolve_credential(lambda _: current, current.target.model_copy(update={'profile_version': 2}))


@pytest.mark.asyncio
@pytest.mark.parametrize('platform', ['instagram_reels', 'facebook'])
async def test_only_the_closed_get_shapes_can_reach_the_mock_transport(platform):
    calls=[];current=credential(platform)
    client=meta.MetaAnalyticsHTTPClient(platform,api_version='v26.0',transport=httpx.MockTransport(
        lambda request:(calls.append(str(request.url)) or httpx.Response(200,json={'fixture':True}))))
    for request in (meta.account_request(current),meta.ownership_request(current,REMOTE),meta.metrics_request(current,REMOTE)):
        await client.request(request)
    assert len(calls)==3
    valid=meta.metrics_request(current,REMOTE)
    headers=dict(valid.headers)
    invalid=[OfficialRequest('POST',valid.url,headers,b'{}'),
        OfficialRequest('GET',valid.url+'&since=2026-10-01',headers),
        OfficialRequest('GET',valid.url+'&fields=id',headers),
        OfficialRequest('GET',valid.url.replace('/v26.0/','/v27.0/'),headers),
        OfficialRequest('GET',valid.url.replace('graph.facebook.com','rupload.facebook.com'),headers),
        OfficialRequest('GET','https://graph.facebook.com/v26.0/'+REMOTE+'/comments?fields=message',headers)]
    for request in invalid:
        with pytest.raises(AnalyticsOfficialError,match='READ_ONLY_ENDPOINT_REQUIRED'):await client.request(request)
    assert len(calls)==3
    disabled=meta.MetaAnalyticsHTTPClient(platform,api_version='v26.0')
    with pytest.raises(PublishingWireError,match='NOT_ACTIVATED'):await disabled.request(meta.account_request(current))


def test_instagram_exact_owned_reel_is_required_before_insights():
    current=credential();good={'id':REMOTE,'owner':{'id':current.target.target_account_id},'media_product_type':'REELS'}
    assert meta.confirm_ownership(response(good),current.target,REMOTE)==good
    for changed in ({**good,'id':'222'},{**good,'owner':{'id':'333'}},{**good,'media_product_type':'FEED'}):
        with pytest.raises(AnalyticsOfficialError,match='OWNERSHIP_NOT_CONFIRMED'):
            meta.confirm_ownership(response(changed),current.target,REMOTE)


def test_instagram_lifetime_counts_never_infer_other_metrics_or_a_reporting_window():
    metrics,evidence=meta.metrics(response(ig_table()),target(),REMOTE,api_version='v26.0')
    assert metrics.views==123 and metrics.comments==0 and metrics.saves==3
    assert all(getattr(metrics,key) is None for key in ('impressions','watch_time','average_view_duration',
        'completion_rate','followers_gained','clicks','ctr','revenue','rpm','observation_window_hours'))
    assert evidence['query'] is None and evidence['observed_window_hours'] is None
    assert evidence['metric_scope']=='lifetime_media_insights'
    metrics,_=meta.metrics(response({'data':[]}),target(),REMOTE,api_version='v26.0')
    assert all(value is None for value in metrics.model_dump().values())
    metrics,_=meta.metrics(response(ig_table({'views':0})),target(),REMOTE,api_version='v26.0')
    assert metrics.views==0 and metrics.likes is None


@pytest.mark.parametrize('kind',['duplicate','foreign-id','unknown-name','invalid-name','day','multiple-values','pagination','malformed-paging','breakdown'])
def test_instagram_rejects_series_breakdowns_duplicates_and_foreign_evidence(kind):
    table=ig_table({'views':1});row=table['data'][0]
    if kind=='duplicate':table['data'].append(dict(row))
    if kind=='foreign-id':row['id']='222/insights/views/lifetime'
    if kind=='unknown-name':row['name']='impressions'
    if kind=='invalid-name':row['name']={'private':'PRIVATE TOKEN'}
    if kind=='day':row['period']='day'
    if kind=='multiple-values':row['values'].append({'value':2})
    if kind=='pagination':table['paging']={'next':'https://private.invalid/?token=PRIVATE'}
    if kind=='malformed-paging':table['paging']=None
    if kind=='breakdown':row['values'][0]['value']={'organic':1,'paid':2}
    with pytest.raises(AnalyticsOfficialError):meta.metrics(response(table),target(),REMOTE,api_version='v26.0')


@pytest.mark.parametrize('value',[True,-1,'4',float('nan'),float('inf'),2**53,2.5])
def test_counters_do_not_coerce_or_round_untrusted_values(value):
    with pytest.raises(AnalyticsOfficialError,match='METRIC_INVALID'):
        meta.metrics(response(ig_table({'views':value})),target(),REMOTE,api_version='v26.0')


def test_facebook_video_node_counters_require_owner_and_empty_summary_edges():
    metrics,evidence=meta.metrics(response(fb_table()),target('facebook'),REMOTE,api_version='v26.0')
    assert (metrics.views,metrics.likes,metrics.comments)==(55,3,0)
    assert metrics.reach is None and metrics.shares is None and metrics.watch_time is None
    assert evidence['metric_scope']=='cumulative_video_node_counters'
    for changes in ({'from':{'id':'333'}},{'likes':{'data':[{'id':'PRIVATE'}],'summary':{'total_count':3}}},
                    {'comments':{'data':[],'summary':{'total_count':'0'}}}):
        with pytest.raises(AnalyticsOfficialError):meta.metrics(response(fb_table(**changes)),target('facebook'),REMOTE,api_version='v26.0')
    metrics,_=meta.metrics(response({'id':REMOTE,'from':{'id':target('facebook').target_account_id}}),target('facebook'),REMOTE,api_version='v26.0')
    assert all(value is None for value in metrics.model_dump().values())
    metrics,_=meta.metrics(response(fb_table(views=None,likes=None,comments={'data':[]})),target('facebook'),REMOTE,api_version='v26.0')
    assert metrics.views is None and metrics.likes is None and metrics.comments is None


@pytest.mark.parametrize('status,code',[(429,None),(503,None),(400,4),(400,17),(400,32),(400,613)])
def test_meta_rate_limits_are_sanitized_and_preserve_bounded_backoff(status,code):
    with pytest.raises(AnalyticsRateLimited) as caught:
        meta.response_object(response({'error':{'code':code,'message':'PRIVATE TOKEN'}},status,{'retry-after':'999999999'}))
    assert 1<=caught.value.retry_after_seconds<=3600 and 'PRIVATE' not in str(caught.value)


@pytest.mark.parametrize('status,code',[(400,100),(400,190),(403,200),(200,100)])
def test_unsupported_or_denied_metrics_fail_without_fallback_or_private_text(status,code):
    with pytest.raises(AnalyticsOfficialError) as caught:
        meta.response_object(response({'error':{'code':code,'message':'PRIVATE TOKEN'}},status))
    assert 'PRIVATE' not in str(caught.value)
