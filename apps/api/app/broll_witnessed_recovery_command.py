"""Signed authorization feeds the existing locked settlement, never a new path."""
from dataclasses import dataclass, field

from sqlalchemy import select

from .broll_plan_review_api import BrollPlanPrepare
from .broll_request_recovery_command import (
    abandon_request, inspect_request, read_settlement, SETTLEMENT_NAMESPACE, _sealed_public,
)
from .broll_request_witness import WitnessEnvelope, WitnessError, WitnessKeyring, canonical, parse_unique
from .broll_request_witness_command import VerifiedWitness, verify_bound_witness, validate_claims
from .service_api_repository import ServiceOperationORM, digest

_SCOPE = object()


@dataclass(frozen=True)
class WitnessRecoveryScope:
    envelope: WitnessEnvelope
    provider: object = field(repr=False)
    authority_guard: object = field(repr=False)
    _seal: object = field(repr=False)

    async def verify(self, service, session, project, authority, intent, original):
        if self._seal is not _SCOPE:
            raise WitnessError()
        verified, current = await verify_bound_witness(service, session, project, authority,
            BrollPlanPrepare.model_validate(intent['body']), self.envelope, self.provider,
            authority_guard=self.authority_guard)
        if not isinstance(verified, VerifiedWitness):
            raise WitnessError()
        claims = verified.claims()
        if (claims['context'] != intent['context'] or claims['public_session'] != intent['principal']
                or claims['credential_sha256'] != intent['credential_sha256']
                or digest(claims['public_session']) != intent['session_sha256']
                or original is not None and original.request_sha256 != claims['prepare_request_sha256']):
            raise WitnessError('BROLL_WITNESS_INTENT_CHANGED')
        audit = {'schema_version': 'vf-broll-settlement-witness-audit.v1',
            'key_id': self.envelope.key_id, 'witness_sha256': verified.witness_sha256,
            'envelope': self.envelope.model_dump(mode='json'), 'issued_at': claims['issued_at'],
            'expires_at': claims['expires_at'], 'prepare_request_sha256': claims['prepare_request_sha256'],
            'execution_status': 'NOT_ASSERTED'}
        return {**verified.identity(), 'authorization_witness': audit}, current


def _scope(envelope, provider, authority_guard):
    proof = envelope if isinstance(envelope, WitnessEnvelope) else WitnessEnvelope.model_validate(envelope)
    return WitnessRecoveryScope(proof, provider, authority_guard, _SCOPE)


def _wrap(recovery, envelope):
    return {'schema_version': 'vf-broll-witnessed-recovery.v1', 'recovery': recovery,
        'witness_sha256': digest(envelope.model_dump(mode='json')), 'key_id': envelope.key_id,
        'execution_status': 'NOT_ASSERTED', 'provider_calls': 0,
        'source_media_mutated': False, 'publish_requested': False, 'owner_approval_inferred': False}


async def inspect_witnessed(service, project, authority, registry, payload, provider, authority_guard):
    scope = _scope(payload.witness, provider, authority_guard)
    result = await inspect_request(service, project, authority, registry, payload, witness_scope=scope)
    if result['state'] == 'settled':
        return await read_witnessed(service, project, authority, registry, result['settlement']['settlement_id'])
    return _wrap(result, scope.envelope)


async def abandon_witnessed(service, project, authority, registry, payload, provider, authority_guard):
    scope = _scope(payload.witness, provider, authority_guard)
    result = await abandon_request(service, project, authority, registry, payload, witness_scope=scope)
    # Replay B cannot relabel the already accepted envelope A. Read back its
    # immutable proof, including after the original signing key was retired.
    return await read_witnessed(service, project, authority, registry, result['settlement']['settlement_id'])


async def read_witnessed(service, project, authority, registry, identifier):
    # A committed settlement is immutable server history; reading it is not a
    # new authorization using an expired signature, and needs no signing key.
    public = await read_settlement(service, project, authority, registry, identifier)
    async with service.repository.session_factory() as session:
        row = await session.scalar(select(ServiceOperationORM).where(
            ServiceOperationORM.operation_id == identifier, ServiceOperationORM.project_id == project,
            ServiceOperationORM.actor_ref == authority['subject'], ServiceOperationORM.service_id == SETTLEMENT_NAMESPACE))
        if row is None:
            raise KeyError(identifier)
        stored = _sealed_public(row)
        omitted = {'current_authority_sha256', 'current_context_sha256'}
        if {k:v for k,v in stored.items() if k not in omitted} != {k:v for k,v in public.items() if k not in omitted}:
            raise WitnessError('BROLL_WITNESS_SETTLEMENT_CHANGED')
        audit = (row.response_json.get('_verified_identity') or {}).get('authorization_witness') if row else None
        if not isinstance(audit, dict) or audit.get('schema_version') != 'vf-broll-settlement-witness-audit.v1':
            raise KeyError(identifier)
        try:
            envelope = WitnessEnvelope.model_validate(audit['envelope'])
            if digest(envelope.model_dump(mode='json')) != audit['witness_sha256'] or envelope.key_id != audit['key_id']:
                raise WitnessError()
            claims = validate_claims(WitnessKeyring._claims(parse_unique(envelope.claims_json)))
            identity = row.response_json['_verified_identity']
            intent = row.response_json['_original_intent']
            if (canonical(claims) != envelope.claims_json or claims['original_authority'] != identity['authority']
                    or claims['public_session'] != identity['public_session'] or claims['credential_sha256'] != identity['credential_sha256']
                    or claims['context'] != intent['context'] or claims['body'] != intent['body']
                    or claims['issued_at'] != audit['issued_at'] or claims['expires_at'] != audit['expires_at']
                    or claims['prepare_request_sha256'] != audit['prepare_request_sha256']):
                raise WitnessError()
            observed = digest({'original': row.response_json['_original_snapshot'], 'settlement': None,
                'current_context_sha256': stored['current_context_sha256'],
                'authority_sha256': stored['current_authority_sha256'], 'intent_sha256': stored['intent_sha256'],
                'authorization_witness_sha256': audit['witness_sha256']})
            if observed != stored['observation_sha256'] or row.request_sha256 != digest({
                    'intent_sha256': stored['intent_sha256'], 'observation_sha256': observed}):
                raise WitnessError()
        except Exception:
            raise WitnessError('BROLL_WITNESS_STORED_AUDIT_INVALID') from None
        return _wrap(public, envelope)
