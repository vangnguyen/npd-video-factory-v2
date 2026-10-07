"""Actual Native SQLite/CAS/budget evidence; monetary inputs are explicit fixtures."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from services.windows_native.contracts import WorkflowError, digest
from services.windows_native.costs import CostLedger
from services.windows_native.store import Store


def write(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def run(data_root, output_root):
    data_root.mkdir(parents=True, exist_ok=False)
    output_root.mkdir(parents=True, exist_ok=False)
    store = Store(data_root)
    project = store.create('Explicit Native cost fixture', 'No real provider or billing')
    unrelated = store.create('Preservation fixture', 'This project remains unchanged')
    ledger = CostLedger(store)
    project = ledger.set_budget(project['id'], project['revision'], '300')
    first = ledger.begin(project_id=project['id'], provider='explicit-cost-fixture', model='no-provider',
        operation='billed-fixture', request_sha256='a' * 64, estimated_cost='100', external_call=False)
    ledger.settle(first, status='response_received', actual_cost='70', billing_receipt_sha256='b' * 64,
        response_sha256='c' * 64, usage={'input_tokens': 2, 'output_tokens': 3, 'total_tokens': 5})
    second = ledger.begin(project_id=project['id'], provider='explicit-cost-fixture', model='no-provider',
        operation='unbilled-fixture', request_sha256='d' * 64, estimated_cost='100', external_call=False)
    ledger.settle(second, status='outcome_unknown', error_code='ExplicitFixtureTimeout')
    try:
        ledger.begin(project_id=project['id'], provider='explicit-cost-fixture', model='no-provider',
            operation='blocked-fixture', request_sha256='e' * 64, estimated_cost=None, external_call=False)
        raise AssertionError('An unknown estimate under an explicit limit must block.')
    except WorkflowError as error:
        assert error.code == 'AI_COST_APPROVAL_REQUIRED_BEFORE_DISPATCH'
    summary = ledger.summary(project['id'])
    assert summary['known_actual_cost_subtotal'] == '70'
    assert summary['estimated_cost_total'] == '200' and summary['actual_cost_total'] is None
    assert summary['known_budget_exposure_vnd'] == '170'
    assert summary['attempted_operations'] == 2 and len(summary['records']) == 3
    assert summary['needs_attention'] and summary['needs_approval']
    assert store.get(unrelated['id']) == unrelated
    restarted = CostLedger(Store(data_root))
    assert restarted.summary(project['id']) == summary
    try:
        restarted.begin(project_id=project['id'], provider='explicit-cost-fixture', model='no-provider',
            operation='unbilled-fixture', request_sha256='d' * 64, estimated_cost='100', external_call=False)
        raise AssertionError('An uncertain operation must never dispatch again.')
    except WorkflowError as error:
        assert error.code == 'COST_OPERATION_ALREADY_DISPATCHED_NO_REPLAY'
    assert restarted.summary(project['id']) == summary
    with store.transaction() as con:
        events = [{**dict(row), 'payload': json.loads(row['payload'])} for row in con.execute(
            'SELECT * FROM events WHERE project_id=? ORDER BY id', (project['id'],))]
    write(output_root / 'cost.json', summary)
    write(output_root / 'project.json', store.get(project['id']))
    write(output_root / 'versions.json', store.versions(project['id']))
    write(output_root / 'job-events.json', events)
    write(output_root / 'preservation.json', {'unrelated_project_exact': True, 'unrelated_project_sha256': digest(unrelated),
        'database_sha256_after_close': hashlib.sha256(store.db.read_bytes()).hexdigest(), 'data_root': str(data_root)})
    receipt = {'schema': 'north-star-native-cost-contract-v1', 'status': 'PASS',
        'input_prices_and_receipts': 'explicit synthetic fixtures; no actual billing',
        'local_real_sqlite': True, 'budget_refused_before_dispatch': True, 'restart_exact': True,
        'uncertain_operation_never_replayed': True, 'unrelated_project_exact': True,
        'external_provider_calls': 0, 'paid_operations': 0, 'owner_uat_accepted': False,
        'full_project_cost_capture_verified': False, 'production_deployed': False,
        'exports_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in output_root.glob('*.json')}}
    write(output_root / 'receipt.json', receipt)
    print(json.dumps({'status': 'PASS', 'exports': 6, 'output_root': str(output_root)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    run(args.data_root.resolve(), args.output_root.resolve())
