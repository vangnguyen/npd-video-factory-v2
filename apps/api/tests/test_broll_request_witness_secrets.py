"""Ephemeral owned key fixture across real subprocesses; no production secrets."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.broll_request_witness import WitnessError, WitnessKey, WitnessKeyring
from app.broll_request_witness_secrets import SettingsWitnessSecretProvider
from app.config import Settings
from test_broll_request_witness_crypto import claims, document


def test_disabled_and_unconfigured_do_not_read_key_material_and_settings_never_dump_it():
    class ForbiddenRead:
        def get_secret_value(self):raise AssertionError('disabled cannot read key')
    provider=SettingsWitnessSecretProvider(SimpleNamespace(broll_request_witness_enabled=False,
        broll_request_witness_keyring_json=ForbiddenRead()))
    with pytest.raises(WitnessError,match='BROLL_WITNESS_NOT_CONFIGURED'):provider.load()
    raw=document([WitnessKey('fixture-secret-key',secrets.token_bytes(32),100,10000,100000,'active')],active='fixture-secret-key')
    settings=Settings(_env_file=None,broll_request_witness_enabled=True,broll_request_witness_keyring_json=SecretStr(raw))
    provider=SettingsWitnessSecretProvider(settings)
    assert isinstance(provider.load(),WitnessKeyring)
    for public in [repr(settings),json.dumps(settings.model_dump(mode='json')),repr(provider)]:
        assert raw not in public and 'secret_b64' not in public


def test_invalid_secret_raises_fixed_safe_code_without_embedding_private_input():
    secret='EPHEMERAL-INVALID-SECRET-NOT-FOR-OUTPUT'
    provider=SettingsWitnessSecretProvider(SimpleNamespace(broll_request_witness_enabled=True,
        broll_request_witness_keyring_json=SecretStr(secret)))
    with pytest.raises(WitnessError) as e:provider.load()
    assert str(e.value)=='BROLL_WITNESS_KEYRING_INVALID' and secret not in repr(e.value)


def test_environment_key_is_stable_across_distinct_processes_with_owned_private_fixture(tmp_path):
    # Only this synthetic key is written. The API never provisions/generates a
    # key or discovers this file; its adapter receives explicit environment data.
    k=WitnessKey('fixture-restart-key',secrets.token_bytes(32),100,10000,100000,'active')
    raw=document([k],active=k.key_id);private=tmp_path/'owned-ephemeral-private-keyring.json'
    with private.open('x',encoding='utf8') as out:out.write(raw)
    api=Path(__file__).resolve().parents[1]
    env={**os.environ,'PYTHONPATH':str(api),'BROLL_REQUEST_WITNESS_ENABLED':'true',
        'BROLL_REQUEST_WITNESS_KEYRING_JSON':private.read_text(encoding='utf8')}
    program="""import json,os,sys
from app.config import Settings
from app.broll_request_witness_secrets import SettingsWitnessSecretProvider
value=json.load(sys.stdin);ring=SettingsWitnessSecretProvider(Settings(_env_file=None)).load()
result=ring.sign(value['claims'],now=1000).model_dump(mode='json') if value['mode']=='sign' else ring.verify(value['proof'],now=1500)
print(json.dumps({'pid':os.getpid(),'result':result},sort_keys=True))
"""
    first=subprocess.run([sys.executable,'-X','utf8','-c',program],input=json.dumps({'mode':'sign','claims':claims()}),
        env=env,text=True,encoding='utf8',capture_output=True,check=True)
    proof=json.loads(first.stdout)
    second=subprocess.run([sys.executable,'-X','utf8','-c',program],input=json.dumps({'mode':'verify','proof':proof['result']}),
        env=env,text=True,encoding='utf8',capture_output=True,check=True)
    verified=json.loads(second.stdout)
    assert proof['pid']!=verified['pid'] and verified['result']==claims()
    assert raw not in first.stdout+first.stderr+second.stdout+second.stderr
