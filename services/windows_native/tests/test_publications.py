"""Owned nonplayable render/rights/QC fixtures; no real publication or Owner acceptance."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
import uuid

from pydantic import ValidationError
from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.hardening import Artifacts
from services.windows_native.publication_models import NativePublicationCreate, NativePublishApproval, NativePublicationAction
from services.windows_native.publications import NativePublications
from services.windows_native.store import Store, now

ROOT = Path(__file__).resolve().parents[3]
CAPABILITIES = ROOT / 'packages/contracts/publishing-capabilities.json'


def render_fixture(store, *, rights='owned', source_mode=True,asset=None,project=None):
    project = project or store.create('EXPLICIT SYNTHETIC PUBLICATION FIXTURE', '', 'media'); identifier = uuid.uuid4().hex
    asset = asset or {'id': 'explicit_fixture.mp4', 'kind': 'video', 'filename': 'EXPLICIT OWNED RIGHTS FIXTURE',
        'rights_confirmed': True, 'rights_status': rights, 'license': 'explicit-owned-fixture-license'}
    document = {**project['document'], 'assets': [asset], 'canonical_timeline': {'snapshot': {
        'metadata': {'native_auto_edit_schema': 'native-auto-edit-timeline-v1' if source_mode else 'explicit-shot-fixture'},
        'tracks': [{'disabled': False, 'clips': [{'disabled': False, 'asset_id': 'ast_explicit_fixture', 'metadata': {'native_asset_id': asset['id']}}]}]}}}
    revision = project['revision'] + 1
    approval = {'revision': revision, 'reviewer': 'EXPLICIT SYNTHETIC REVIEW — NOT OWNER UAT', 'acknowledged': True}
    snapshot = {'document': document, 'approval': approval}; stamp = now()
    with store.transaction() as con:
        # Explicit fixture seeding, never a product approval shortcut.
        con.execute('UPDATE projects SET revision=?,document=?,approval=? WHERE id=?', (revision, json.dumps(document), json.dumps(approval), project['id']))
        store.version(con, project['id'])
        con.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (identifier, project['id'], revision, 'render', 'running',
            'explicit_fixture', uuid.uuid4().hex, digest(snapshot), json.dumps(snapshot), None, None, stamp, stamp))
    job = store.get_job(identifier); directory = store.root / 'jobs' / identifier; directory.mkdir(parents=True)
    final = directory / 'final.mp4'; final.write_bytes(b'EXPLICIT NONPLAYABLE NATIVE PUBLICATION FIXTURE; NO FULL QC')
    result = {'qc': {'passed': True, 'width': 1080, 'height': 1920, 'duration_seconds': 3, 'video_codec': 'h264',
        'audio_codec': 'aac', 'final_sha256': file_sha(final), 'fixture': True, 'full_media_qc': False},
        'review_required': True, 'output_directory': str(directory), 'provider_calls': 0}
    Artifacts(directory, job).commit('render', [final], result)
    store.finish(job, result=result)
    store.review_render(identifier, revision, 'EXPLICIT SYNTHETIC FINAL REVIEW — NOT OWNER UAT', True, 'approve')
    return store.get(project['id']), store.get_job(identifier)


class NativePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name); self.store = Store(self.root)
        self.project, self.job = render_fixture(self.store); self.clock = [datetime.now(timezone.utc)]
        self.service = NativePublications(self.store, CAPABILITIES, clock=lambda: self.clock[0])

    def tearDown(self): self.temp.cleanup()

    def payload(self, **changes):
        return NativePublicationCreate.model_validate({'revision': self.project['revision'], 'final_job_id': self.job['id'],
            'platform': 'youtube', 'metadata': {'title': 'Explicit mock distribution fixture', 'privacy': 'private'},
            'request_key': 'native-publication-owned-fixture-key', **changes})

    def create(self, **changes): return self.service.create(self.project['id'], self.payload(**changes), actor='fixture-editor')[0]

    def approve(self, value):
        return self.service.approve(self.project['id'], value['publication_id'], NativePublishApproval(
            expected_fingerprint=value['request_fingerprint'], expected_artifact_sha256=value['snapshot']['final_sha256'], acknowledged=True), actor='fixture-owner')

    def test_four_platforms_share_validator_approval_and_mock_provider_without_post_ids(self):
        original = self.store.get(self.project['id'])
        for platform in ['youtube', 'tiktok', 'instagram_reels', 'facebook']:
            value = self.create(platform=platform, request_key='native-four-platform-fixture-' + platform)
            self.assertEqual(value['status'], 'awaiting_publish_approval'); self.assertFalse(value['external_action'])
            self.assertIsNone(self.service.process()); self.approve(value)
            done = self.service.process(); self.assertEqual(done['status'], 'dry_run_succeeded')
            self.assertTrue(done['receipt']['mock']); self.assertIsNone(done['receipt']['remote_post_id'])
            self.assertFalse(done['receipt']['external_action']); self.assertFalse(done['publish_enabled'])
        self.assertEqual(self.store.get(self.project['id']), original)

    def test_restart_idempotency_and_repeated_dispatch_preserve_one_receipt(self):
        value = self.create(); self.approve(value); done = self.service.process()
        restarted = NativePublications(Store(self.root), CAPABILITIES)
        again, replay = restarted.create(self.project['id'], self.payload(), actor='fixture-another-editor')
        self.assertTrue(replay); self.assertEqual(again, done)
        repeat = restarted.process(project=self.project['id'], identity=value['publication_id'], fingerprint=value['request_fingerprint'])
        self.assertEqual(repeat, done); self.assertIsNone(restarted.process())
        self.assertEqual(len(restarted.get(self.project['id'], value['publication_id'])['events']), 3)
        with self.assertRaisesRegex(WorkflowError, 'IDEMPOTENCY_CONFLICT'):
            restarted.create(self.project['id'], self.payload(platform='tiktok'), actor='fixture')

    def test_due_clock_and_cancellation_never_dispatch_early_or_revive(self):
        scheduled = self.clock[0] + timedelta(hours=1)
        value = self.create(metadata={'title': 'Scheduled mock', 'scheduled_at': scheduled.astimezone(timezone(timedelta(hours=7))).isoformat()})
        self.assertEqual(self.approve(value)['status'], 'scheduled'); self.assertIsNone(self.service.process())
        self.clock[0] += timedelta(hours=1); self.assertEqual(self.service.process()['status'], 'dry_run_succeeded')
        other = self.create(request_key='native-cancelled-fixture-key'); self.approve(other)
        payload = NativePublicationAction(expected_fingerprint=other['request_fingerprint'])
        cancel = self.service.cancel(self.project['id'], other['publication_id'], payload, actor='fixture-owner')
        self.assertEqual(cancel['status'], 'cancelled'); self.assertIsNone(cancel['approval']); self.assertIsNone(self.service.process())

    def test_unknown_rights_voice_provenance_and_platform_failures_are_persisted_blockers(self):
        for rights, source in [('unknown', True), ('licensed', False), ('owner_attested', True)]:
            project, job = render_fixture(self.store, rights=rights, source_mode=source)
            value, _ = self.service.create(project['id'], self.payload(revision=project['revision'], final_job_id=job['id'], request_key='blocked-fixture-' + uuid.uuid4().hex), actor='fixture')
            self.assertEqual(value['status'], 'blocked'); self.assertIsNone(value['receipt'])
        value = self.create(metadata={'title': 'x' * 101}); self.assertEqual(value['status'], 'blocked')
        self.assertEqual(value['snapshot']['validation']['platform']['status'], 'failed')

    def test_edit_review_or_artifact_change_invalidates_pending_publish_approval(self):
        for mutation in ['edit', 'review', 'artifact']:
            project, job = render_fixture(self.store)
            value, _ = self.service.create(project['id'], self.payload(final_job_id=job['id'], request_key='mutation-fixture-' + mutation), actor='fixture')
            approved = self.service.approve(project['id'], value['publication_id'], NativePublishApproval(
                expected_fingerprint=value['request_fingerprint'], expected_artifact_sha256=value['snapshot']['final_sha256'], acknowledged=True), actor='fixture-owner')
            if mutation == 'edit':
                # This fixture has a minimal/non-renderable timeline; simulate version drift in owned state.
                with self.store.transaction() as con:
                    con.execute('UPDATE projects SET revision=revision+1,approval=NULL WHERE id=?', (project['id'],))
                    self.store.version(con, project['id'])
            if mutation == 'review': self.store.review_render(job['id'], job['revision'], 'fixture-rejection', False, 'reject', 'Explicit fixture rejection')
            if mutation == 'artifact': (self.root / 'jobs' / job['id'] / 'final.mp4').write_bytes(b'explicit corruption')
            result = self.service.process(); self.assertEqual(result['status'], 'blocked'); self.assertIsNone(result['receipt'])

    def test_final_review_required_and_strict_inputs_cannot_enable_live(self):
        with self.store.transaction() as con: con.execute('DELETE FROM render_reviews WHERE job_id=?', (self.job['id'],))
        with self.assertRaisesRegex(WorkflowError, 'HUMAN_FINAL_VIDEO_APPROVAL'): self.create()
        for invalid in [{'mode':'live'}, {'revision': True}, {'publish_enabled':True}]:
            with self.assertRaises(ValidationError): self.payload(**invalid)
        for invalid in [1, 'true', False]:
            with self.assertRaises(ValidationError): NativePublishApproval(expected_fingerprint='a'*64,expected_artifact_sha256='b'*64,acknowledged=invalid)
        for invalid in [True, 1800000000, 1800000000.5, '2026-10-07', '2026-10-07T12:00:00']:
            with self.assertRaises(ValidationError): self.payload(metadata={'title':'Explicit invalid schedule', 'scheduled_at': invalid})

    def test_capability_change_requires_restart_and_invalidates_old_approval(self):
        manifest = self.root / 'capability-fixture.json'; manifest.write_bytes(CAPABILITIES.read_bytes())
        self.service = NativePublications(self.store, manifest, clock=lambda: self.clock[0])
        value = self.create(); self.approve(value)
        manifest.write_bytes(manifest.read_bytes() + b'\n')
        with self.assertRaisesRegex(WorkflowError, 'CAPABILITIES_CHANGED_RESTART_REQUIRED'):
            self.create(request_key='new-capability-fixture-key')
        self.service = NativePublications(Store(self.root), manifest, clock=lambda: self.clock[0])
        blocked = self.service.process()
        self.assertEqual(blocked['status'], 'blocked'); self.assertIsNone(blocked['receipt'])
        self.assertEqual(blocked['failure_code'], 'NATIVE_PUBLICATION_REVIEW_BINDING_CHANGED')

    def test_changed_approval_blocks_dispatch_and_remote_receipt_corruption_blocks_read(self):
        value = self.create(); approved = self.approve(value)
        approval = {**approved['approval'], 'live_publication_authorized': True}
        with self.store.transaction() as con:
            con.execute('UPDATE native_publications SET approval_json=? WHERE publication_id=?', (json.dumps(approval), value['publication_id']))
        blocked = self.service.process(); self.assertEqual(blocked['failure_code'], 'NATIVE_PUBLISH_REVIEW_REQUIRED')
        self.assertIsNone(blocked['receipt'])
        other = self.create(request_key='native-receipt-corruption-fixture-key'); self.approve(other); done = self.service.process()
        receipt = {**done['receipt'], 'remote_post_id':'explicit-corrupt-remote-id'}
        with self.store.transaction() as con:
            con.execute('UPDATE native_publications SET receipt_json=? WHERE publication_id=?', (json.dumps(receipt), other['publication_id']))
        with self.assertRaisesRegex(WorkflowError, 'RECEIPT_INVALID'):
            self.service.get(self.project['id'], other['publication_id'])

    def test_concurrent_create_and_workers_do_not_duplicate(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.service.create(self.project['id'], self.payload(), actor='fixture'), range(2)))
        self.assertEqual(sum(not replay for _, replay in results), 1); self.approve(results[0][0])
        with ThreadPoolExecutor(max_workers=2) as pool: completed = list(pool.map(lambda _: self.service.process(), range(2)))
        self.assertEqual(sum(item is not None for item in completed), 1)

    def test_scoped_keyset_pages_and_snapshot_tamper_fail_closed(self):
        values = [self.create(request_key='native-page-fixture-' + str(index)) for index in range(4)]
        first = self.service.page(self.project['id'], limit=2); second = self.service.page(self.project['id'], limit=2, cursor=first['next_cursor'])
        self.assertEqual(len({item['publication_id'] for item in [*first['items'], *second['items']]}), 4)
        self.assertIsNone(second['next_cursor'])
        other = self.store.create('Foreign fixture', 'No publication')
        with self.assertRaisesRegex(WorkflowError, 'CURSOR_INVALID'): self.service.page(other['id'], cursor=first['next_cursor'])
        with self.assertRaisesRegex(WorkflowError, 'NOT_FOUND'): self.service.get(other['id'], values[0]['publication_id'])
        value = values[0]
        with self.store.transaction() as con:
            snapshot = copy.deepcopy(value['snapshot']); snapshot['final_sha256'] = 'f' * 64
            con.execute('UPDATE native_publications SET snapshot_json=? WHERE publication_id=?', (json.dumps(snapshot), value['publication_id']))
        with self.assertRaisesRegex(WorkflowError, 'IMMUTABLE_EVIDENCE'): self.service.get(self.project['id'], value['publication_id'])

    def test_additive_schema_and_new_workspace_do_not_leak_or_change_old_rows(self):
        value = self.create()
        with self.store.transaction() as con:
            before = list(con.execute('SELECT * FROM projects')); columns = list(con.execute('PRAGMA table_info(projects)'))
        other = NativePublications(Store(self.root), CAPABILITIES, workspace_id='wsp_other_fixture')
        self.assertEqual(other.page(self.project['id'])['items'], [])
        with self.assertRaisesRegex(WorkflowError, 'NOT_FOUND'): other.get(self.project['id'], value['publication_id'])
        with self.store.transaction() as con:
            self.assertEqual([tuple(row) for row in before], [tuple(row) for row in con.execute('SELECT * FROM projects')])
            self.assertEqual([tuple(row) for row in columns], [tuple(row) for row in con.execute('PRAGMA table_info(projects)')])


if __name__ == '__main__': unittest.main()
