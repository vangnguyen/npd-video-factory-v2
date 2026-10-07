"""Prove the existing human identity moved unchanged and runs without API services."""
import argparse
import ast
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from services.windows_native import ingestion
from services.windows_native.contracts import file_sha
from services.windows_native.tests.test_human_identity import fixture
from app.human_identity import HumanAuthRegistry, HumanAuthVerifier

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '17c5b0cbb3568250e14bd2b7a5134ca57404943d'


def symbols(source):
    result = {}
    for node in ast.parse(source).body:
        names = [node.name] if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else []
        if isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        for name in names:
            result[name] = hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
    return result


def write(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2); handle.write('\n')


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    old = subprocess.check_output(['git', 'show', BASELINE + ':apps/api/app/human_auth.py'], cwd=ROOT, text=True)
    pure = (ROOT / 'apps/api/app/human_identity.py').read_text(encoding='utf-8')
    adapter = (ROOT / 'apps/api/app/human_auth.py').read_text(encoding='utf-8')
    before, after, current = symbols(old), symbols(pure), symbols(adapter)
    moved = ['HumanRole', 'ROLE_RANK', '_TOKEN_ID', '_WORKSPACE_REF', '_TOKEN_PREFIX',
        'HumanTokenRecord', 'HumanAuthRegistry', 'HumanPrincipal', 'HumanAuthVerifier', 'InvalidHumanCredential', '_as_utc']
    retained = ['RateLimitStore', 'HumanRateLimiter', '_error', 'principal_from', 'authenticate_human_request',
        'required_role_for', 'authorize_human_request', 'authorize_workspace', 'authorize_project']
    assert all(before[name] == after[name] for name in moved)
    assert all(before[name] == current[name] for name in retained)
    assert not any(name.startswith(('fastapi', 'sqlalchemy', 'torch', 'vieneu')) for name in sys.modules)
    raw, data = fixture('editor')
    principal = HumanAuthVerifier(HumanAuthRegistry.model_validate(data), max_token_ttl_seconds=86400).verify('Bearer ' + raw)
    assert principal.role_for('wsp_native_fixture') == 'editor' and principal.role_for('wsp_other_fixture') is None
    value = asdict(principal); value['expires_at'] = principal.expires_at.isoformat()
    assert raw not in json.dumps(value)
    write(output / 'source-preservation.json', {'baseline_head': BASELINE,
        'moved_symbols_ast_sha256': {name: after[name] for name in moved},
        'unchanged_api_symbols_ast_sha256': {name: current[name] for name in retained},
        'all_moved_behavior_exact': True, 'all_api_authorization_behavior_exact': True,
        'schema_file_sha256': file_sha(ROOT / 'packages/contracts/human-auth-registry.schema.json')})
    write(output / 'native-identity.json', {'explicit_fixture': True, 'principal': value,
        'framework_database_gpu_imported': False, 'cross_workspace_role': None,
        'native_http_role_enforcement_completed': False, 'raw_token_not_serialized': True})
    write(output / 'receipt.json', {'schema': 'north-star-human-identity-contract-v1', 'status': 'PASS',
        'local_real_native_runtime': True, 'existing_protocol_behavior_preserved': True,
        'fixture_credentials_only': True, 'external_calls': 0, 'owner_uat_accepted': False,
        'production_deployed': False, 'native_rbac_ready': False,
        'exports_sha256': {path.name: file_sha(path) for path in output.glob('*.json')}})
    print(json.dumps({'status': 'PASS', 'moved_symbols': len(moved), 'api_symbols': len(retained), 'exports': 3}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-root', type=Path, required=True)
    run(parser.parse_args().output_root.resolve())
