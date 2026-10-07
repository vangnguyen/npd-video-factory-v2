"""Offline recovery contracts; all projects, provider and monetary inputs are fixtures."""
from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3
from unittest.mock import patch
import subprocess
import tempfile
import unittest
import uuid
import zipfile

from services.windows_native.backup import create_backup, restore_backup, relative_name, offline_lease
from services.windows_native.contracts import WorkflowError, file_sha
from services.windows_native.costs import CostLedger
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.pipeline import Config
from services.windows_native.store import Store
from services.windows_native.tests.test_multi_niche import build_tech_project, ExplicitAIIdeasFixture


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / 'source'
        self.store = Store(self.root)
        self.config = Config(data_root=self.root, runtime_root=self.base / 'runtime',
            secret_file=self.base / 'private' / 'openai.env',
            assemblyai_secret_file=self.base / 'private' / 'assemblyai.dpapi')
        self.project = self.store.create('Recovery fixture', 'No external provider')
        self.archive = self.base / 'backup.zip'
        self.destination = self.base / 'restored'

    def tearDown(self):
        self.assertEqual(self.base, Path(self.temp.name).resolve())
        self.temp.cleanup()

    def backup(self):
        return create_backup(self.config, self.archive)

    def restore(self, receipt, destination=None):
        return restore_backup(self.archive, destination or self.destination, expected_sha256=receipt['sha256'])

    def test_actual_snapshot_preserves_projects_history_costs_assets_and_config(self):
        (self.config.secret_file.parent).mkdir()
        self.config.secret_file.write_text('SECRET_VALUE_NOT_INCLUDED_IN_PACKAGE', encoding='utf-8')
        blob = self.root / 'assets' / 'owned-fixture.bin'; blob.parent.mkdir()
        blob.write_bytes(b'owned asset fixture; not a playable video')
        ledger = CostLedger(self.store)
        identifier = ledger.begin(project_id=self.project['id'], provider='explicit-fixture', model=None,
            operation='unknown-fixture', request_sha256='a' * 64, estimated_cost=None, external_call=False)
        ledger.settle(identifier, status='outcome_unknown', error_code='ExplicitFixtureTimeout')
        before = self.store.get(self.project['id'])
        versions = self.store.versions(self.project['id'])
        costs = ledger.summary(self.project['id'])
        original_hash = file_sha(blob)
        receipt = self.backup()
        with zipfile.ZipFile(self.archive) as archive:
            self.assertNotIn('SECRET_VALUE_NOT_INCLUDED_IN_PACKAGE', json.dumps(json.loads(archive.read('manifest.json'))))
            self.assertTrue(any(name.startswith('configuration/source-config/profiles/') for name in archive.namelist()))
        restored = self.restore(receipt)
        self.assertFalse(restored['services_started'])
        self.assertEqual(restored['provider_calls'], 0)
        recovered = Store(self.destination)
        self.assertEqual(before, recovered.get(self.project['id']))
        self.assertEqual(versions, recovered.versions(self.project['id']))
        self.assertEqual(costs, CostLedger(recovered).summary(self.project['id']))
        self.assertEqual(file_sha(self.destination / 'assets' / blob.name), original_hash)
        self.assertEqual(file_sha(blob), original_hash)
        runtime = Config.load(restored['runtime_config_path'])
        self.assertEqual(runtime.data_root, self.destination)
        self.assertEqual(runtime.secret_file, self.config.secret_file)
        self.assertFalse(any(path.suffix == '.env' for path in self.destination.rglob('*')))

    def test_restored_fixture_flows_work_without_original_root(self):
        config, original_store, service, project, original_bundle, original = build_tech_project(self.root / 'technology')
        # Nested factory databases require their own bounded factory snapshot.
        package = create_backup(config, self.archive)
        receipt = self.restore(package)
        source = config.data_root.resolve()
        target = self.base / 'retained-original'
        self.assertIn(self.base, source.parents)
        self.assertIn(self.base, target.parents)
        source.rename(target)
        self.assertFalse(source.exists())
        recovered_config = Config.load(receipt['runtime_config_path'])
        recovered_store = Store(self.destination)
        recovered_service = IntelligenceService(recovered_config, recovered_store,
            idea_provider=ExplicitAIIdeasFixture())
        self.assertEqual(recovered_store.get(project['id']), project)
        self.assertEqual(recovered_service.bundle(original_bundle['run']['id']), original_bundle)
        recovered_service.verify_sources(original_bundle['sources'], original_bundle['findings'])
        self.assertTrue((self.destination / 'assets').is_dir())
        before = recovered_store.shot_view(project['id'])
        # A real existing editor operation persists in the recovered database.
        updated = recovered_store.mutate_shots(project['id'], project['revision'],
            {'type': 'reorder', 'shot_ids': [shot['shot_id'] for shot in before['shot_timeline']['shots']]})
        self.assertTrue(updated['document']['canonical_timeline'])
        self.assertIsNone(updated['approval'])

    def test_backup_from_restored_root_can_be_restored_again_without_overwrite(self):
        receipt = self.backup()
        first = self.restore(receipt)
        second_package = self.base / 'second.zip'
        second_receipt = create_backup(Config.load(first['runtime_config_path']), second_package)
        second_root = self.base / 'second-restored'
        result = restore_backup(second_package, second_root, expected_sha256=second_receipt['sha256'])
        self.assertEqual(Store(second_root).get(self.project['id']), self.store.get(self.project['id']))
        self.assertTrue(Path(result['runtime_config_path']).is_file())
        self.assertTrue((second_root / Path(first['runtime_config_path']).name).is_file())

    def test_wrong_trusted_hash_and_existing_destination_do_not_write(self):
        receipt = self.backup()
        with self.assertRaisesRegex(WorkflowError, 'TRUSTED_CHECKSUM_MISMATCH'):
            restore_backup(self.archive, self.destination, expected_sha256='0' * 64)
        self.assertFalse(self.destination.exists())
        self.destination.mkdir(); marker = self.destination / 'keep.txt'; marker.write_text('unchanged')
        with self.assertRaisesRegex(WorkflowError, 'NEW_DESTINATION'):
            self.restore(receipt)
        self.assertEqual(marker.read_text(), 'unchanged')

    def test_changed_payload_with_new_package_checksum_still_rejects_entry(self):
        receipt = self.backup()
        changed = self.base / 'changed.zip'
        with zipfile.ZipFile(self.archive) as source, zipfile.ZipFile(changed, 'x', compression=zipfile.ZIP_STORED) as target:
            for info in source.infolist():
                raw = source.read(info.filename)
                if info.filename == 'state/workflow.sqlite3':
                    raw = b'X' + raw[1:]
                target.writestr(info.filename, raw)
        with self.assertRaisesRegex(WorkflowError, 'ENTRY_HASH_MISMATCH'):
            restore_backup(changed, self.destination, expected_sha256=file_sha(changed))
        self.assertFalse(self.destination.exists())
        self.assertTrue(any(self.base.glob('.restored.restore-*')), 'Owned failed staging is retained for inspection')

    def test_archive_path_special_mode_duplicate_and_compression_reject_before_staging(self):
        good = self.backup()
        for variant in ('traversal', 'duplicate', 'symlink', 'compressed', 'foreign'):
            with self.subTest(variant=variant):
                package = self.base / (variant + '.zip')
                with zipfile.ZipFile(self.archive) as source, zipfile.ZipFile(package, 'x', compression=zipfile.ZIP_STORED) as target:
                    for info in source.infolist():
                        target.writestr(info.filename, source.read(info.filename))
                    if variant == 'traversal':
                        target.writestr('../escape.txt', b'forbidden')
                    elif variant == 'duplicate':
                        target.writestr('STATE/workflow.sqlite3', b'forbidden case collision')
                    elif variant == 'symlink':
                        info = zipfile.ZipInfo('state/link'); info.external_attr = 0o120777 << 16
                        target.writestr(info, b'../outside')
                    elif variant == 'compressed':
                        target.writestr('state/compressed', b'x' * 100, compress_type=zipfile.ZIP_DEFLATED)
                    else:
                        target.writestr('foreign.txt', b'not in manifest')
                with self.assertRaises(WorkflowError):
                    restore_backup(package, self.destination, expected_sha256=file_sha(package))
                self.assertFalse(self.destination.exists())
        self.assertFalse((self.base / 'escape.txt').exists())

    def test_active_jobs_and_operations_refuse_backup(self):
        self.store.enqueue(self.project['id'], self.project['revision'], 'content', uuid.uuid4().hex)
        with self.assertRaisesRegex(WorkflowError, 'ACTIVE_OPERATIONS'):
            self.backup()
        self.assertFalse(self.archive.exists())

    def test_committed_wal_pages_survive_without_copying_journal_files(self):
        connection = sqlite3.connect(self.store.db)
        try:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA wal_autocheckpoint=0')
            connection.execute("INSERT INTO events(project_id,action,payload,created_at) VALUES(?,?,?,?)",
                (self.project['id'], 'wal_fixture', json.dumps({'fixture': True, 'committed': True}), '2000-01-01T00:00:00+00:00'))
            connection.commit()
            self.assertTrue((self.root / 'workflow.sqlite3-wal').is_file())
            receipt = self.backup()
            with zipfile.ZipFile(self.archive) as archive:
                self.assertFalse(any(name.endswith(('-wal', '-shm')) for name in archive.namelist()))
            self.restore(receipt)
            with Store(self.destination).transaction() as recovered:
                value = recovered.execute("SELECT payload FROM events WHERE action='wal_fixture'").fetchone()
                self.assertEqual(json.loads(value[0]), {'fixture': True, 'committed': True})
        finally:
            connection.close()

    def test_same_count_source_mutation_refuses_to_commit_snapshot(self):
        from services.windows_native import backup as module
        original = module.add_file
        changed = False
        def mutate(archive, name, path):
            nonlocal changed
            result = original(archive, name, path)
            if not changed:
                changed = True
                with self.store.transaction() as connection:
                    connection.execute('UPDATE projects SET updated_at=? WHERE id=?', ('2000-01-01T00:00:00+00:00', self.project['id']))
            return result
        with patch.object(module, 'add_file', side_effect=mutate):
            with self.assertRaisesRegex(WorkflowError, 'SOURCE_CHANGED_DURING_COPY'):
                self.backup()
        self.assertFalse(self.archive.exists())

    def test_semantically_corrupt_project_history_refuses_snapshot(self):
        with self.store.transaction() as con:
            con.execute("UPDATE projects SET document=json_set(document,'$.name','Corrupt fixture document') WHERE id=?", (self.project['id'],))
        with self.assertRaisesRegex(WorkflowError, 'PROJECT_HISTORY_INTEGRITY'):
            self.backup()
        self.assertFalse(self.archive.exists())

    def test_existing_package_and_inside_source_output_refuse(self):
        self.archive.write_bytes(b'unchanged')
        with self.assertRaisesRegex(WorkflowError, 'NEW_AND_OUTSIDE_SOURCE'):
            self.backup()
        self.assertEqual(self.archive.read_bytes(), b'unchanged')
        with self.assertRaisesRegex(WorkflowError, 'NEW_AND_OUTSIDE_SOURCE'):
            create_backup(self.config, self.root / 'unsafe.zip')

    def test_data_root_secret_unknown_database_hardlink_and_junction_reject(self):
        sensitive = self.root / 'unexpected.env'
        sensitive.write_text('private fixture')
        # .env is an exact conventional name; configured .env values stay outside root.
        sensitive.rename(self.root / '.env')
        with self.assertRaisesRegex(WorkflowError, 'SECRET_FILE'):
            self.backup()
        (self.root / '.env').unlink()
        other = self.root / 'unknown.sqlite3'; other.write_bytes(b'unknown database')
        with self.assertRaisesRegex(WorkflowError, 'UNKNOWN_DATABASE'):
            self.backup()
        other.unlink()
        target = self.base / 'outside.txt'; target.write_text('untouched')
        linked = self.root / 'hardlink.txt'; os.link(target, linked)
        with self.assertRaisesRegex(WorkflowError, 'LINKED_PATH'):
            self.backup()
        linked.unlink()
        target_dir = self.base / 'outside'; target_dir.mkdir()
        link = self.root / 'linked-folder'
        if os.name == 'nt':
            command = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target_dir)],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(command.returncode, 0)
        else:
            link.symlink_to(target_dir, target_is_directory=True)
        try:
            with self.assertRaisesRegex(WorkflowError, 'LINKED_PATH'):
                self.backup()
            self.assertEqual(target.read_text(), 'untouched')
        finally:
            link.rmdir() if os.name == 'nt' else link.unlink()

    def test_server_lease_refuses_backup_and_lock_path_escape(self):
        with offline_lease(self.root):
            with self.assertRaisesRegex(WorkflowError, 'ALREADY_IN_USE'):
                self.backup()
        (self.root / '.server.lock').unlink()
        external = self.base / 'lock-target'; external.write_bytes(b'unchanged')
        os.link(external, self.root / '.server.lock')
        with self.assertRaisesRegex(WorkflowError, 'LINKED_PATH'):
            self.backup()
        self.assertEqual(external.read_bytes(), b'unchanged')

    def test_windows_portable_entry_names(self):
        for name in ('../x', '/x', 'x//y', 'C:/x', 'x\\y', 'x/./y', 'NUL', 'x/CON.txt', 'trailing.', 'space '):
            with self.subTest(name=name), self.assertRaisesRegex(WorkflowError, 'ENTRY_PATH_INVALID'):
                relative_name(name)
        self.assertEqual(relative_name('assets/nguồn-hợp-lệ.jpg'), 'assets/nguồn-hợp-lệ.jpg')
