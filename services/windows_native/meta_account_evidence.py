"""Meta readonly proofs inside the existing Native account journal/cost ledger."""
import asyncio
from datetime import datetime, timedelta
from typing import Literal
from pydantic import Field, field_validator, model_validator
from app.models import StrictModel
from app.analytics_official import response_digest
from app.meta_publishing_credentials import (REQUIRED, ALLOWED, page_identity_request,
    instagram_identity_request, confirm_page_identity, confirm_instagram_identity)
from .contracts import WorkflowError, digest
from .meta_connection import NativeMetaAccountFactory, Profile


class Metadata(StrictModel):
    schema_version: Literal['native-meta-account-source-v1']
    profile: Profile
    cipher_sha256: str | None = Field(pattern=r'^[a-f0-9]{64}$')
    consented_at: datetime
    deadline: datetime

    @model_validator(mode='after')
    def interval(self):
        if self.consented_at.tzinfo is None or self.deadline.tzinfo is None or self.deadline - self.consented_at != timedelta(seconds=900):
            raise ValueError('Exact finite readonly window required')
        return self


class Observation(StrictModel):
    operation: Literal['page_identity', 'instagram_identity']
    request_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    response_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    response_status: Literal[200]
    cost_operation_id: str = Field(pattern=r'^[a-f0-9]{64}$')


class Proof(StrictModel):
    schema_version: Literal['native-meta-account-proof-v1']
    page_id: str
    instagram_account_id: str | None
    token_page_match: Literal[True]
    linked_instagram_match: Literal[True] | None
    declared_permissions: list[str] = Field(min_length=2, max_length=7)
    provider_permissions_verified: Literal[False]
    app_eligibility_verified: Literal[False]
    publishing_enabled: Literal[False]
    read_only: Literal[True]
    observations: list[Observation] = Field(min_length=1, max_length=2)

    @field_validator('token_page_match', 'provider_permissions_verified', 'app_eligibility_verified', 'publishing_enabled', 'read_only', 'linked_instagram_match', mode='before')
    @classmethod
    def raw_flags(cls, value):
        if value is not None and type(value) is not bool: raise ValueError('Raw boolean required')
        return value


def source(factory, clock):
    instant = clock()
    return Metadata(schema_version='native-meta-account-source-v1', profile=factory.profile,
        cipher_sha256=factory.cipher_sha256, consented_at=instant, deadline=instant + timedelta(seconds=900)).model_dump(mode='json')


def validate(snapshot, result=None):
    try:
        metadata = Metadata.model_validate(snapshot['meta'])
        target = metadata.profile.target
        if target.model_dump(mode='json') != snapshot['target']: raise ValueError()
        if result is not None:
            proof = Proof.model_validate(result['meta'])
            if metadata.cipher_sha256 is None: raise ValueError()
            ig = target.platform == 'instagram_reels'
            if (proof.page_id != metadata.profile.page_id or proof.instagram_account_id != (target.target_account_id if ig else None)
                or proof.linked_instagram_match is not (True if ig else None)
                or proof.declared_permissions != sorted(set(proof.declared_permissions))
                or not REQUIRED[target.platform] <= set(proof.declared_permissions) <= ALLOWED
                or [r.operation for r in proof.observations] != (['page_identity', 'instagram_identity'] if ig else ['page_identity'])
                or len({r.cost_operation_id for r in proof.observations}) != len(proof.observations)
                or result['cost_operation_id'] != proof.observations[-1].cost_operation_id
                or result['response_sha256'] != proof.observations[-1].response_sha256): raise ValueError()
        return metadata
    except Exception: raise WorkflowError('NATIVE_META_ACCOUNT_EVIDENCE_CHANGED') from None


def links(journal, con, value):
    if value['result'] is None: return
    validate(value['snapshot'], value['result'])
    try:
        for observation in value['result']['meta']['observations']:
            provider = 'official-' + value['snapshot']['target']['platform']
            operation = 'account_lookup.' + value['check_id'] + '.' + observation['operation']
            expected = digest({'check_id': value['check_id'], 'snapshot_sha256': value['snapshot_sha256'], 'operation': observation['operation']})
            identity = digest({'project': value['project_id'], 'job': None, 'provider': provider, 'operation': operation})
            row = con.execute('SELECT * FROM native_cost_operations WHERE id=? AND project_id=?', (identity, value['project_id'])).fetchone()
            if (observation['cost_operation_id'] != identity or observation['request_sha256'] != expected or row is None
                or row['provider'] != provider or row['operation'] != operation or row['job_id'] is not None
                or row['request_sha256'] != expected or row['status'] != 'response_received' or row['paid'] != 0
                or row['external_call'] != int(not value['snapshot']['mock'])): raise ValueError()
            import json
            receipt = json.loads(row['receipt'])
            if receipt['provider_response_sha256'] != observation['response_sha256']: raise ValueError()
    except Exception: raise WorkflowError('NATIVE_META_ACCOUNT_COST_EVIDENCE_CHANGED') from None


def admission(factory, snapshot, instant):
    metadata = validate(snapshot)
    if (type(factory) is not NativeMetaAccountFactory or metadata.profile != factory.profile
        or metadata.cipher_sha256 != factory.cipher_sha256 or not metadata.consented_at <= instant < metadata.deadline):
        raise WorkflowError('NATIVE_META_ACCOUNT_READ_WINDOW_OR_BINDING_CHANGED')


def lookup(journal, factory, value, project, identity, claim):
    credential = factory.credential(now=journal.clock())
    reads = [(page_identity_request(credential), confirm_page_identity, 'page_identity')]
    if factory.profile.target.platform == 'instagram_reels':
        reads.append((instagram_identity_request(credential), confirm_instagram_identity, 'instagram_identity'))
    observations = []
    for request, confirm, name in reads:
        operation = None; sent = False
        try:
            journal.admission(project, identity, claim)
            factory.credential(now=journal.clock())  # Expiry and custody stay current for every request.
            fingerprint = digest({'check_id': identity, 'snapshot_sha256': value['snapshot_sha256'], 'operation': name})
            operation = journal.costs.begin(project_id=project, provider='official-' + credential.target.platform,
                model=None, operation='account_lookup.' + identity + '.' + name, request_sha256=fingerprint,
                estimated_cost=None, external_call=not factory.client.mock, paid=False)
            journal.admission(project, identity, claim); sent = True
            response = asyncio.run(factory.client.request(request))
            sha = response_digest(response)
            journal.costs.settle(operation, status='response_received', response_sha256=sha)
            confirm(response, credential); journal.admission(project, identity, claim)
            observations.append(Observation(operation=name, request_sha256=fingerprint,
                response_sha256=sha, response_status=response.status, cost_operation_id=operation))
        except Exception as error:
            if operation is not None:
                with journal.store.transaction() as con:
                    cost = con.execute('SELECT status FROM native_cost_operations WHERE id=?', (operation,)).fetchone()
                if cost and cost['status'] == 'dispatch_intent':
                    journal.costs.settle(operation, status='outcome_unknown' if sent else 'rejected',
                        error_code=getattr(error, 'code', 'NATIVE_META_ACCOUNT_CHECK_FAILED'))
            raise
    ig = credential.target.platform == 'instagram_reels'
    proof = Proof(schema_version='native-meta-account-proof-v1', page_id=credential.page_id,
        instagram_account_id=credential.target.target_account_id if ig else None, token_page_match=True,
        linked_instagram_match=True if ig else None, declared_permissions=sorted(credential.scopes),
        provider_permissions_verified=False, app_eligibility_verified=False, publishing_enabled=False,
        read_only=True, observations=observations).model_dump(mode='json')
    return {'schema_version': 'native-official-account-check-result-v1', 'check_id': identity,
        'workspace_id': journal.workspace, 'project_id': project, 'account_ref': value['account_ref'],
        'snapshot_sha256': value['snapshot_sha256'], 'target_binding_sha256': value['snapshot']['target_binding_sha256'],
        'account_match': True, 'operation': 'account_lookup', 'response_sha256': observations[-1].response_sha256,
        'response_status': 200, 'cost_operation_id': observations[-1].cost_operation_id, 'mock': factory.client.mock,
        'external_call': not factory.client.mock, 'read_only': True, 'verified_at': journal.clock().isoformat(),
        'publishing_enabled': False, 'token_returned': False, 'real_provider_tested': False, 'meta': proof}
