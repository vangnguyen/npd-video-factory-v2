"""Read-only, source-bound issuance and verification of authorization witnesses."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime

from .broll_plan_review_api import BrollPlanPrepare
from .broll_plan_review_command import BrollPlanConflict, _begin, _context
from .broll_request_witness import (
    CLAIMS_VERSION, PURPOSE, WitnessEnvelope, WitnessError, canonical, parse_unique,
)
from .service_api_repository import digest
from .broll_request_witness_secrets import load_witness_keyring

PUBLIC = {'subject', 'display_name', 'platform_role', 'workspace_roles', 'expires_at', 'human_write_enabled'}
AUTHORITY = PUBLIC - {'human_write_enabled'} | {'token_id', 'credential_sha256'}
CLAIMS = {'schema_version', 'purpose', 'issued_at', 'expires_at', 'workspace_id', 'project_id',
    'request_key', 'body', 'body_sha256', 'prepare_request_sha256', 'original_authority',
    'original_authority_sha256', 'credential_sha256', 'public_session', 'context', 'source',
    'timeline_id', 'timeline_version', 'timeline_version_id'}
_VERIFIED = object()


@dataclass(frozen=True)
class VerifiedWitness:
    """Internal typed proof. Routes accept envelopes, never this capability."""
    envelope: WitnessEnvelope
    witness_sha256: str
    _claims_json: str = field(repr=False)
    _seal: object = field(repr=False)

    def claims(self):
        if self._seal is not _VERIFIED:
            raise WitnessError()
        return parse_unique(self._claims_json)

    def identity(self):
        value = self.claims()
        return {'schema_version': 'broll-recovery-identity.v1', 'authority': value['original_authority'],
            'credential_sha256': value['credential_sha256'], 'public_session': value['public_session']}


def _hash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _context_fields(value):
    return {k: v for k, v in value.items() if k not in {'context_json', 'context_sha256', 'authority_sha256', 'can_prepare'}}


def _fresh_authority(authority, instant):
    try:
        expiry = datetime.fromisoformat(authority['expires_at'])
        if expiry.tzinfo is None or instant >= expiry.timestamp():
            raise ValueError()
    except Exception:
        raise WitnessError('BROLL_WITNESS_AUTHORITY_CHANGED', 403) from None


def validate_claims(value):
    try:
        if type(value) is not dict or set(value) != CLAIMS:
            raise ValueError()
        authority, public, context = value['original_authority'], value['public_session'], value['context']
        request = BrollPlanPrepare.model_validate(value['body']).model_dump(mode='json')
        if (request != value['body'] or set(authority) != AUTHORITY or set(public) != PUBLIC
                or public['human_write_enabled'] is not True or not isinstance(authority['token_id'], str)
                or not authority['token_id'] or not _hash(authority['credential_sha256'])
                or not _hash(value['credential_sha256']) or digest(authority) != value['original_authority_sha256']
                or any(authority[k] != public[k] for k in PUBLIC - {'human_write_enabled'})
                or digest(request) != value['body_sha256'] or request['request_key'] != value['request_key']
                or digest({'project_id': value['project_id'], 'authority': authority, 'request': request}) != value['prepare_request_sha256']
                or context['schema_version'] != 'broll-plan-review-context.v1'
                or context['authority_sha256'] != value['original_authority_sha256']
                or context['actor_ref'] != public['subject'] or context['can_prepare'] is not True
                or context['context_sha256'] != request['context_sha256']
                or context['workspace_id'] != value['workspace_id'] or context['project_id'] != value['project_id']
                or context['source'] != value['source']
                or any(context[k] != value[k] for k in ('timeline_id', 'timeline_version', 'timeline_version_id'))):
            raise ValueError()
        literal = context['context_json']
        fields = {k: v for k, v in context.items() if k not in {'context_json', 'context_sha256'}}
        if (not isinstance(literal, str) or len(literal.encode()) > 65536 or parse_unique(literal) != fields
                or hashlib.sha256(literal.encode()).hexdigest() != context['context_sha256']):
            raise ValueError()
        return value
    except Exception:
        raise WitnessError() from None


def _guard_authority(guard, authority):
    if not callable(guard) or guard() != authority:
        raise WitnessError('BROLL_WITNESS_AUTHORITY_CHANGED', 403)


async def issue_witness(service, project, authority, authorization, payload, provider, *, ttl_seconds, authority_guard, now=None):
    if type(ttl_seconds) is not int or not 300 <= ttl_seconds <= 30 * 86400:
        raise WitnessError('BROLL_WITNESS_POLICY_INVALID', 503)
    request = payload.model_dump(mode='json')
    async with service.repository.session_factory() as session:
        async with session.begin():
            await _begin(session)
            context = await _context(service, session, project, authority, lock=True)
            if context['context_sha256'] != payload.context_sha256 or not context['can_prepare']:
                raise BrollPlanConflict('BROLL_REVIEW_CONTEXT_CHANGED')
            if payload.settings.allow_stock and not context['licensed_stock_enabled']:
                raise BrollPlanConflict('BROLL_STOCK_NOT_AVAILABLE')
            instant = time.time() if now is None else now
            stamp = int(instant)
            _fresh_authority(authority, instant)
            _guard_authority(authority_guard, authority)
            claims = {'schema_version': CLAIMS_VERSION, 'purpose': PURPOSE, 'issued_at': stamp,
                'expires_at': stamp + ttl_seconds, 'workspace_id': context['workspace_id'], 'project_id': project,
                'request_key': payload.request_key, 'body': request, 'body_sha256': digest(request),
                'prepare_request_sha256': digest({'project_id': project, 'authority': authority, 'request': request}),
                'original_authority': authority, 'original_authority_sha256': digest(authority),
                'credential_sha256': hashlib.sha256(authorization.removeprefix('Bearer ').strip().encode()).hexdigest(),
                'public_session': {**{k: authority[k] for k in PUBLIC - {'human_write_enabled'}}, 'human_write_enabled': True},
                'context': context, 'source': context['source'],
                **{k: context[k] for k in ('timeline_id', 'timeline_version', 'timeline_version_id')}}
            validate_claims(claims)
            ring = load_witness_keyring(provider)
            envelope = ring.sign(claims, now=stamp).model_dump(mode='json')
            return {'schema_version': 'vf-broll-request-witness-issued.v1', 'witness': envelope,
                'witness_sha256': digest(envelope), 'execution_status': 'NOT_ASSERTED', 'provider_calls': 0,
                'source_media_mutated': False, 'publish_requested': False, 'owner_approval_inferred': False}


async def verify_bound_witness(service, session, project, authority, request, envelope, provider, *, authority_guard, now=None):
    # Caller supplies the current SQL transaction. Settlement calls this only
    # after acquiring its existing project lock; key/time/source are fresh here.
    _guard_authority(authority_guard, authority)
    ring = load_witness_keyring(provider)
    stamp = int(time.time()) if now is None else now
    proof = envelope if isinstance(envelope, WitnessEnvelope) else WitnessEnvelope.model_validate(envelope)
    claims = validate_claims(ring.verify(proof, now=stamp))
    original = claims['public_session']
    if (claims['project_id'] != project or request.model_dump(mode='json') != claims['body']
            or any(authority[k] != original[k] for k in ('subject', 'display_name', 'platform_role', 'workspace_roles'))):
        raise WitnessError('BROLL_WITNESS_AUTHORITY_CHANGED', 403)
    current = await _context(service, session, project, authority, lock=True)
    if not current['can_prepare'] or _context_fields(current) != _context_fields(claims['context']):
        raise WitnessError('BROLL_WITNESS_SOURCE_CHANGED')
    instant = time.time() if now is None else now
    _fresh_authority(authority, instant)
    _guard_authority(authority_guard, authority)
    # SQL awaits cannot carry an expired/revoked key or credential into a
    # settlement. The final check has no await before the typed proof is made.
    if load_witness_keyring(provider).verify(proof, now=int(instant)) != claims:
        raise WitnessError()
    return VerifiedWitness(proof, digest(proof.model_dump(mode='json')), canonical(claims), _VERIFIED), current


async def verify_witness(service, project, authority, request, envelope, provider, *, authority_guard, now=None):
    async with service.repository.session_factory() as session:
        async with session.begin():
            await _begin(session)
            verified, current = await verify_bound_witness(service, session, project, authority, request,
                envelope, provider, authority_guard=authority_guard, now=now)
            value = verified.claims()
            return {'schema_version': 'vf-broll-request-witness-verified.v1', 'authorization_witness_valid': True,
                'witness_sha256': verified.witness_sha256, 'workspace_id': value['workspace_id'], 'project_id': project,
                'request_key': value['request_key'], 'original_authority_sha256': value['original_authority_sha256'],
                'current_authority_sha256': current['authority_sha256'], 'current_context_sha256': current['context_sha256'],
                'source': current['source'], 'execution_status': 'NOT_ASSERTED', 'provider_calls': 0,
                'source_media_mutated': False, 'publish_requested': False, 'owner_approval_inferred': False}
