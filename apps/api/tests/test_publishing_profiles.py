"""Public configuration only. No actual account, key, OAuth or paid operation."""
from decimal import Decimal
import json

import pytest
from pydantic import ValidationError

from app.publishing_models import PublishingTargetBinding
from app.publishing_profiles import PublishingProfile, PublishingProfileCatalog, PublishingProfileError, PublishingProfileRegistry, PROVIDER_KEYS


def profile(workspace='explicit-workspace', identifier='ppf_explicit_profile', version=1, platform='youtube', **kwargs):
    target = PublishingTargetBinding(workspace_id=workspace, profile_id=identifier, profile_version=version,
        platform=platform, provider_key=PROVIDER_KEYS[platform], target_account_id='EXPLICIT-ACCOUNT-FIXTURE',
        credential_binding_sha256='a' * 64)
    return PublishingProfile(target=target, category_id='27', made_for_kids=False, contains_synthetic_media=True, **kwargs)


def catalog(*profiles): return PublishingProfileCatalog(profiles=list(profiles))


def test_catalog_roundtrip_retains_vietnamese_free_configuration_and_exact_decimal_without_secrets():
    value = profile(max_ai_cost=Decimal('100.0001'), estimated_costs={'chunk': Decimal('0.0123')})
    registry = PublishingProfileRegistry.from_json(catalog(value).model_dump_json())
    selected = registry.select(value.target.workspace_id, 'youtube')
    assert selected == value and selected.youtube_ready() and len(selected.fingerprint()) == 64
    assert registry.target(value.target.workspace_id, value.target.profile_id) == value.target
    assert 'credential_ref' not in catalog(value).model_dump_json() and 'token' not in catalog(value).model_dump_json()


def test_multiple_workspaces_and_channels_need_exact_selection_without_cross_scope_fallback():
    first = profile(); second = profile(identifier='ppf_another_channel'); foreign = profile(workspace='foreign')
    registry = PublishingProfileRegistry(catalog(first, second, foreign))
    assert registry.select('foreign', 'youtube') == foreign
    assert registry.select(first.target.workspace_id, 'youtube', first.target.profile_id) == first
    for args in ((first.target.workspace_id, 'youtube'), ('unknown', 'youtube'), (first.target.workspace_id, 'tiktok')):
        with pytest.raises(PublishingProfileError, match='SELECTION_REQUIRED'): registry.select(*args)
    with pytest.raises(PublishingProfileError, match='SCOPE_NOT_FOUND'): registry.resolve('foreign', second.target.profile_id)


def test_history_is_additive_latest_version_selected_and_mutable_results_cannot_change_registry():
    first = profile(); second = profile(version=2, max_ai_cost=Decimal('20'))
    registry = PublishingProfileRegistry(catalog(first))
    registry.replace_catalog(catalog(first, second))
    assert registry.resolve(first.target.workspace_id, first.target.profile_id) == second
    mutable = registry.resolve(first.target.workspace_id, first.target.profile_id)
    mutable.estimated_costs['chunk'] = Decimal('999')
    assert registry.resolve(first.target.workspace_id, first.target.profile_id).estimated_costs == {}
    for value in (catalog(second), catalog(first.model_copy(update={'category_id': '28'}), second)):
        with pytest.raises(PublishingProfileError, match='HISTORY_IMMUTABLE'): registry.replace_catalog(value)
    with pytest.raises(ValidationError, match='duplicate profile version'): catalog(first, first)


@pytest.mark.parametrize('updates', [
    {'made_for_kids': 1}, {'contains_synthetic_media': 'true'}, {'category_id': '../bad'},
    {'max_ai_cost': True}, {'max_ai_cost': Decimal('NaN')}, {'max_ai_cost': Decimal('-1')},
    {'max_ai_cost': Decimal('0.00001')}, {'estimated_costs': {'fake': Decimal('1')}},
    {'estimated_costs': {'chunk': Decimal('Infinity')}}, {'credential_ref': 'secret://private'},
    {'token': 'EXPLICIT-NOT-A-TOKEN'}])
def test_invalid_disclosures_costs_and_secret_fields_refuse(updates):
    base = profile().model_dump(); base.update(updates)
    with pytest.raises(ValidationError): PublishingProfile.model_validate(base)


@pytest.mark.parametrize('data', ['bad json', '[]', '{}', 'x' * 262145, b'\xff'],
    ids=['malformed-json', 'wrong-root', 'missing-schema', 'oversized', 'invalid-utf8'])
def test_invalid_catalog_has_fixed_public_error(data):
    with pytest.raises(PublishingProfileError, match='CATALOG_INVALID'): PublishingProfileRegistry.from_json(data)


def test_unchecked_model_and_wrong_platform_provider_cannot_enter_catalog():
    valid = profile()
    invalid = valid.model_copy(update={'made_for_kids': 1})
    with pytest.raises(PublishingProfileError): PublishingProfileRegistry(catalog(invalid))
    wrong = valid.target.model_copy(update={'provider_key': PROVIDER_KEYS['facebook']})
    with pytest.raises(ValidationError): PublishingProfile(target=wrong)
    raw = json.loads(catalog(valid).model_dump_json()); raw['profiles'][0]['target']['profile_version'] = True
    with pytest.raises(PublishingProfileError): PublishingProfileRegistry.from_json(json.dumps(raw))
