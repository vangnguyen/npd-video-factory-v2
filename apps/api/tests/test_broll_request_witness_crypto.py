"""Ephemeral dedicated signing fixtures; no configured production key or IO."""
import base64
import copy
import hashlib
import hmac
import json
import secrets

import pytest

from app.broll_request_witness import (
    CLAIMS_VERSION, DOMAIN, KEYRING_VERSION, PURPOSE, WitnessError, WitnessKey,
    WitnessKeyring, canonical,
)


def key(identifier='test-key-a', state='active', secret=None):
    return WitnessKey(identifier, secret or secrets.token_bytes(32), 100, 10000, 100000, state)


def claims():
    return {'schema_version': CLAIMS_VERSION, 'purpose': PURPOSE, 'issued_at': 1000,
        'expires_at': 2000, 'request_key': 'fixture-request-0001', 'body_sha256': 'a'*64}


def document(keys, active='test-key-a'):
    return canonical({'schema_version': KEYRING_VERSION, 'purpose': PURPOSE, 'active_key_id': active,
        'keys': [{'key_id': k.key_id, 'secret_b64': base64.b64encode(k.secret).decode(),
            'not_before': k.not_before, 'sign_until': k.sign_until, 'verify_until': k.verify_until, 'state': k.state} for k in keys]})


def test_exact_standard_hmac_and_literal_domain_match_without_secret_in_public_output():
    k=key();ring=WitnessKeyring.from_json(document([k]));value=claims();proof=ring.sign(value,now=1000)
    expected=hmac.new(k.secret,DOMAIN+k.key_id.encode()+b'\n'+canonical(value).encode(),hashlib.sha256).hexdigest()
    assert proof.signature==expected and ring.verify(proof,now=1500)==value
    for public in [repr(k),repr(ring),proof.model_dump_json()]:
        assert base64.b64encode(k.secret).decode() not in public and k.secret.hex() not in public
    with pytest.raises(TypeError):ring.keys['new']=k


@pytest.mark.parametrize('change',[
    lambda v:v.update(signature='f'*64),lambda v:v.update(key_id='unknown'),
    lambda v:v.update(schema_version='another-purpose'),lambda v:v.update(extra=True),
    lambda v:v.update(claims_json=v['claims_json']+' '),
    lambda v:v.update(claims_json=v['claims_json'].replace('fixture-request-0001','foreign-request-0001')),
])
def test_tamper_never_verifies(change):
    k=key();ring=WitnessKeyring(k.key_id,{k.key_id:k});proof=ring.sign(claims(),now=1000).model_dump()
    change(proof)
    with pytest.raises(WitnessError,match='BROLL_WITNESS_INVALID'):ring.verify(proof,now=1500)


def test_rotation_retains_only_old_allowed_window_and_revocation_fails_closed():
    old=key();proof=WitnessKeyring(old.key_id,{old.key_id:old}).sign(claims(),now=1000)
    new=key('test-key-b');retired=key(old.key_id,'verify_only',old.secret)
    rotated=WitnessKeyring(new.key_id,{old.key_id:retired,new.key_id:new})
    assert rotated.verify(proof,now=1500)==claims()
    revoked=key(old.key_id,'revoked',old.secret)
    for ring in [WitnessKeyring(new.key_id,{new.key_id:new}),WitnessKeyring(new.key_id,{old.key_id:revoked,new.key_id:new})]:
        with pytest.raises(WitnessError):ring.verify(proof,now=1500)
    assert rotated.sign(claims(),now=1000).key_id==new.key_id


@pytest.mark.parametrize('now',[True,999,2000,100001])
def test_expiry_future_issuance_and_invalid_clock_rejected(now):
    k=key();ring=WitnessKeyring(k.key_id,{k.key_id:k});proof=ring.sign(claims(),now=1000)
    with pytest.raises(WitnessError):ring.verify(proof,now=now)


@pytest.mark.parametrize('change',[
    lambda v:v.update(purpose='agent-hub'),lambda v:v.update(schema_version='unknown'),
    lambda v:v['keys'].append(copy.deepcopy(v['keys'][0])),lambda v:v.update(active_key_id='unknown'),
    lambda v:v['keys'][0].update(secret_b64='secret fixture invalid base64'),
    lambda v:v['keys'][0].update(sign_until=True),lambda v:v['keys'][0].update(not_before=10001),
    lambda v:v['keys'][0].update(state='verify_only'),lambda v:v['keys'][0].update(extra='secret fixture'),
])
def test_invalid_secret_documents_have_only_fixed_error_code(change):
    value=json.loads(document([key()]));change(value)
    with pytest.raises(WitnessError,match='^BROLL_WITNESS_KEYRING_INVALID$') as e:
        WitnessKeyring.from_json(canonical(value))
    assert e.value.status==503 and 'secret fixture' not in str(e.value)


def test_duplicate_and_nonfinite_json_rejected_even_with_valid_hmac():
    k=key();ring=WitnessKeyring(k.key_id,{k.key_id:k})
    for literal in [canonical(claims())[:-1]+',"purpose":"'+PURPOSE+'"}',canonical(claims())[:-1]+',"bad":NaN}']:
        value={'schema_version':'vf-broll-request-witness.v1','key_id':k.key_id,'claims_json':literal,
            'signature':hmac.new(k.secret,DOMAIN+k.key_id.encode()+b'\n'+literal.encode(),hashlib.sha256).hexdigest()}
        with pytest.raises(WitnessError):ring.verify(value,now=1500)
