"""Offline cooldown custody and active wire lease backup guards; HTTP fixtures."""
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from services.windows_native.backup import create_backup, database_status, read_database, restore_backup
from services.windows_native.contracts import digest, WorkflowError
from services.windows_native.pipeline import Config
from services.windows_native.stock import NativeStock
from services.windows_native.stock_models import StockSearch
from services.windows_native.stock_registry import StockCredential, StockFactory
from services.windows_native.store import Store


class StockCooldownBackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='vf-stock-backup-')
        self.folder = Path(self.temporary.name)
        self.store = Store(self.folder/'state')
        self.config = Config(data_root=self.store.root)
        self.project = self.store.create('Explicit cooldown backup fixture', 'No external provider')
        self.wire_calls = []
        def fixture(request):
            self.wire_calls.append(str(request.url))
            return httpx.Response(429, headers={'Retry-After':'600'})
        factory = StockFactory('pexels', StockCredential(api_key='explicit-test-key', enabled=True),
            owner_enabled=True, transport=httpx.MockTransport(fixture))
        self.service = NativeStock(self.store, self.config, workspace_id='wsp_stock_backup_fixture',
            factories={'pexels':factory})
        payload = StockSearch(revision=self.project['revision'], provider='pexels', query='explicit test',
            media_type='image', orientation='landscape', limit=1, fixture_acknowledged=True,
            request_key='explicit-cooldown-backup-fixture')
        admitted, _ = self.service.create(self.project['id'], payload, actor='fixture-editor')
        self.service.process()
        self.job = self.service.get(self.project['id'], admitted['stock_id'])
        self.assertEqual(self.job['status'], 'retry_scheduled')
        self.assertEqual(len(self.wire_calls), 1)
        self.service.cancel(self.project['id'], admitted['stock_id'],
            fingerprint=admitted['request_fingerprint'], actor='fixture-editor')

    def tearDown(self):
        self.service.close()
        self.temporary.cleanup()

    def rows(self, root):
        con = read_database(root/'workflow.sqlite3')
        try:
            columns = [r[1] for r in con.execute('PRAGMA table_info(native_stock_provider_cooldowns)')]
            return [dict(zip(columns,row)) for row in con.execute(
                'SELECT * FROM native_stock_provider_cooldowns ORDER BY scope_sha256')]
        finally:
            con.close()

    def test_idle_cooldown_does_not_block_backup_and_restores_exact_observation(self):
        original = self.rows(self.store.root)
        self.assertEqual(len(original), 1)
        observed = json.loads(original[0]['evidence_json'])
        self.assertEqual(digest(observed), original[0]['evidence_sha256'])
        self.assertEqual(observed['status_code'], 429)
        self.assertEqual(original[0]['request_class'], 'api')
        self.assertIsNone(original[0]['lease_id'])
        status = database_status(self.store.root/'workflow.sqlite3')
        self.assertEqual(status['active_operations'], 0)
        self.assertEqual(status['counts']['native_stock_provider_cooldowns'], 1)
        archive = self.folder/'backup.zip'
        receipt = create_backup(self.config, archive)
        destination = self.folder/'restored'
        restore_backup(archive, destination, expected_sha256=receipt['sha256'])
        self.assertEqual(self.rows(destination), original)
        self.assertEqual(self.store.get(self.project['id']), self.project)
        self.assertEqual(len(self.wire_calls), 1)

    def test_live_wire_lease_blocks_snapshot_after_terminal_job_then_release_allows_backup(self):
        # Simulate only the wire admission boundary, without contacting the CDN.
        counter = {'wire_attempts':0, 'wire_leases':{}}
        lease = self.service.wire_admit(self.job['snapshot'], 'cdn:images.pexels.com', self.job['stock_id'], counter)
        scope, stock_id = counter['wire_leases'][lease]
        try:
            status = database_status(self.store.root/'workflow.sqlite3')
            self.assertEqual(status['counts']['native_stock_provider_cooldowns'], 2)
            self.assertEqual(status['active_operations'], 1)
            with self.assertRaisesRegex(WorkflowError, 'BACKUP_SOURCE_HAS_ACTIVE_OPERATIONS'):
                create_backup(self.config, self.folder/'blocked.zip')
            self.assertFalse((self.folder/'blocked.zip').exists())
            self.assertEqual(self.store.get(self.project['id']), self.project)
        finally:
            self.service.wire_release(scope, lease, stock_id=stock_id)
        self.assertEqual(database_status(self.store.root/'workflow.sqlite3')['active_operations'], 0)
        receipt = create_backup(self.config, self.folder/'released.zip')
        self.assertEqual(receipt['database_status']['workflow.sqlite3']['counts']['native_stock_provider_cooldowns'], 2)
        self.assertEqual(len(self.wire_calls), 1)


if __name__ == '__main__':
    unittest.main()
