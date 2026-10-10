"""Facebook-Login identity protocol fixtures; no real account or provider."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from urllib.parse import parse_qs, urlsplit
import pytest
from app.meta_publishing_credentials import (MetaOAuthCredential, REQUIRED, resolve_meta_credential,
    page_identity_request, instagram_identity_request, confirm_page_identity, confirm_instagram_identity)
from app.meta_publishing_protocol import GraphTarget
from app.publishing_models import PublishingTargetBinding
from app.publishing_wire import OfficialResponse, PublishingWireError

TOKEN = 'META-EXPLICIT-PROTOCOL-MOCK-ONLY-1234567890'
NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)


def credential(platform='instagram_reels'):
    target = PublishingTargetBinding(workspace_id='wsp_fixture', profile_id='ppf_meta_fixture', profile_version=1,
        platform=platform, provider_key={'facebook':'facebook-graph-api-publishing', 'instagram_reels':'instagram-graph-api-publishing'}[platform],
        target_account_id='12345' if platform=='facebook' else '23456', credential_binding_sha256='a'*64)
    return MetaOAuthCredential(target, GraphTarget(platform, target.target_account_id, 'v24.0', 'facebook_login'),
        '12345', NOW+timedelta(hours=1), REQUIRED[platform], TOKEN)


def response(value, status=200, headers=None):
    return OfficialResponse(status, headers or {}, json.dumps(value).encode())


@pytest.mark.parametrize('platform', ['facebook', 'instagram_reels'])
def test_explicit_page_identity_uses_fixed_readonly_origin_fields_and_no_query_secret(platform):
    c=credential(platform);r=page_identity_request(c);parsed=urlsplit(r.url)
    assert r.method=='GET' and r.body==b'' and parsed.hostname=='graph.facebook.com' and parsed.path=='/v24.0/me'
    assert parse_qs(parsed.query)=={'fields':['id' if platform=='facebook' else 'id,instagram_business_account']}
    assert dict(r.headers)=={'Authorization':'Bearer '+TOKEN} and TOKEN not in repr(r) and TOKEN not in repr(c)
    assert confirm_page_identity(response({'id':'12345', 'instagram_business_account':{'id':'23456'}}),c)


def test_instagram_read_follows_exact_page_link_and_does_not_create_container_or_claim_permissions():
    c=credential();r=instagram_identity_request(c);assert r.method=='GET' and urlsplit(r.url).path=='/v24.0/23456'
    assert parse_qs(urlsplit(r.url).query)=={'fields':['id']}
    assert confirm_instagram_identity(response({'id':'23456'}),c)
    with pytest.raises(PublishingWireError):instagram_identity_request(credential('facebook'))


@pytest.mark.parametrize('change', [dict(page_id='99999'),dict(scopes=frozenset({'instagram_basic'})),
    dict(scopes=frozenset({'instagram_basic','instagram_content_publish','pages_read_engagement','unknown'})),
    dict(expires_at=NOW.replace(tzinfo=None)),dict(token='bad\r\ntoken'),dict(page_id=12345)])
def test_dedicated_credential_rejects_foreign_page_incomplete_permissions_or_untyped_values(change):
    c=credential('facebook') if change.get('page_id')=='99999' else credential()
    with pytest.raises(PublishingWireError):replace(c,**change)


def test_resolution_binds_target_graph_page_expiry_and_reconstructs_mutated_target():
    c=credential();assert resolve_meta_credential(lambda _:c,c.target,c.graph,c.page_id,now=NOW)==c
    for value in [replace(c,expires_at=NOW+timedelta(seconds=90)),replace(c,expires_at=NOW),None]:
        with pytest.raises(PublishingWireError):resolve_meta_credential(lambda _:value,c.target,c.graph,c.page_id,now=NOW)
    with pytest.raises(PublishingWireError):resolve_meta_credential(lambda _:c,c.target,c.graph,'99999',now=NOW)
    with pytest.raises(ValueError): c.target.provider_key='youtube-data-api-publishing'
    object.__setattr__(c.target,'provider_key','youtube-data-api-publishing')  # Explicit unchecked integration tamper fixture.
    with pytest.raises(PublishingWireError):resolve_meta_credential(lambda _:c,c.target,c.graph,c.page_id,now=NOW)


@pytest.mark.parametrize('value', [{'id':'99999'}, {'id':12345}, {'id':'12345'},
    {'id':'12345','instagram_business_account':{'id':'99999'}}, {'id':'12345','instagram_business_account':{'id':23456}}])
def test_wrong_page_or_missing_foreign_instagram_link_never_confirms(value):
    with pytest.raises(PublishingWireError):confirm_page_identity(response(value),credential())


def test_duplicate_json_and_provider_errors_are_not_account_proofs():
    with pytest.raises(PublishingWireError):confirm_page_identity(OfficialResponse(200,{},b'{"id":"99999","id":"12345"}'),credential('facebook'))
    for status in (401,403,429,500):
        with pytest.raises(PublishingWireError) as error:confirm_page_identity(response({'id':'12345'},status,{'retry-after':'25'}),credential('facebook'))
        if status==429:assert error.value.code=='META_ACCOUNT_RATE_LIMIT' and error.value.retry_after==25
    with pytest.raises(PublishingWireError):confirm_instagram_identity(response({'id':'99999'}),credential())
