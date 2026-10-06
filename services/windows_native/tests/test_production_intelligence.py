"""Local fixtures test behavior; they are not real provider or human acceptance."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
import uuid
import http.client
import json
import threading
from unittest.mock import patch

from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.hardening import Artifacts
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.pipeline import Config
from services.windows_native.planning_store import PlanningStore
from services.windows_native.production_intelligence import ProductionIntelligence, configuration, freshness, item_id, priority
from services.windows_native.research import PublicWebResearchProvider
from services.windows_native.store import Store
from services.windows_native.server import LocalServer
from services.windows_native.tests.test_intelligence_engines import receipt
from services.windows_native.tests.test_intelligence_workflow import FixtureIdeas
from services.windows_native.tests.test_workflow import proposal


class ProductionIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = Config(data_root=self.root)
        self.production = Store(self.root)
        self.ci = IntelligenceService(self.config, self.production,
            research_provider=PublicWebResearchProvider(self.root / 'research-sources', fetch=lambda url: receipt()), idea_provider=FixtureIdeas())
        self.service = ProductionIntelligence(self.config, self.production, self.ci,
            clock=lambda: datetime(2026, 10, 6, tzinfo=timezone.utc))

    def tearDown(self):
        self.temp.cleanup()

    def approved(self):
        bundle = self.ci.create('housing research fixture', 'vietnam-property', ['https://example.com/test'])
        for action in ('research', 'ideas'):
            self.ci.enqueue(bundle['run']['id'], bundle['run']['version'], action, uuid.uuid4().hex)
            self.ci.run_one()
            bundle = self.ci.bundle(bundle['run']['id'])
        idea = bundle['ideas'][0]
        brief = self.ci.select(idea['id'], idea['version'], bundle['opportunity']['version'], 'TEST FIXTURE')
        brief = self.ci.approve_brief(brief['id'], brief['version'], 'TEST FIXTURE', True)
        return self.ci.bundle(bundle['run']['id'])

    def entry(self, row):
        return {k: row[k] for k in ('id', 'binding_sha256')} | {'planning_version': row['planning']['version']}

    def batch(self, rows, action='scripts', key=None):
        return self.service.batch({'action': action, 'items': [self.entry(r) for r in rows],
                                  'request_key': key or uuid.uuid4().hex, 'reviewer': 'TEST FIXTURE', 'acknowledged': True})

    def override(self, row):
        return self.service.save_planning(row['id'], row['planning']['version'],
            {'similarity_override': {'warning_sha256': row['similarity']['warning_sha256'], 'note': 'TEST FIXTURE deliberate comparison'}}, 'TEST FIXTURE')

    def rendered(self, accepted=False):
        project = self.production.create('Historical transport fixture', 'No provider or real render')
        project = self.production.save(project['id'], 1, proposal=proposal(), asset={'id': 'fixture.jpg', 'rights_confirmed': True, 'sha256': 'fixture'})
        project = self.production.approve(project['id'], 2, 'TEST FIXTURE not human acceptance', True)
        job = self.production.enqueue(project['id'], 2, 'render', uuid.uuid4().hex)
        out = self.root / 'jobs' / job['id']; out.mkdir(parents=True)
        path = out / 'final.mp4'; path.write_bytes(b'TRANSPORT FIXTURE NOT REAL MEDIA')
        timeline = out / 'timeline.json'; timeline.write_text('{"schema_version":"1.1","test_fixture":"transport-only; not a rendered production timeline"}', encoding='utf-8')
        result = {'qc': {'passed': True, 'final_sha256': file_sha(path), 'duration_seconds': 45}, 'test_fixture': True}
        Artifacts(out, job).commit('render', [path, timeline], result)
        self.production.claim(); self.production.finish(job, result=result)
        if accepted:
            self.production.review_render(job['id'], 2, 'TEST FIXTURE not human acceptance', True, 'approve')
        return project, self.production.get_job(job['id'])

    def test_queue_is_read_only_for_certified_records_and_statuses(self):
        b = self.approved()
        before = self.service.records()
        for _ in range(2):
            rows = self.service.queue()['items']
            self.assertEqual(rows[0]['stage'], 'BRIEF_READY')
            self.assertEqual(rows[0]['intelligence_status'], 'APPROVED')
            self.assertEqual(rows[0]['idea_id'], b['brief']['idea_id'])
        self.assertEqual(self.service.records(), before)
        with self.service.planning.transaction() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM planning').fetchone()[0], 0)

    def test_planning_identity_versions_history_restart_and_preserved_project(self):
        project = self.production.create('Preserved project', 'Original input')
        before = self.production.get(project['id'])
        row = self.service.queue()['items'][0]
        self.assertEqual(row['id'], item_id('project', project['id']))
        changed = self.service.save_planning(row['id'], 0, {'campaign': 'October', 'planned_date': '2026-10-20',
             'format': '16:9', 'duration_seconds': 60, 'assigned_to': 'Editor', 'assigned_status': 'ASSIGNED', 'project_priority': 90}, 'TEST FIXTURE')
        self.assertEqual(changed['planning']['version'], 1)
        restarted = ProductionIntelligence(self.config, Store(self.root), self.ci)
        restored = restarted.find(row['id'])
        self.assertEqual(restored['planning'], changed['planning'])
        self.assertEqual(restarted.planning.history(row['id'])[0], changed['planning'])
        self.assertEqual(self.production.get(project['id']), before)
        with self.assertRaisesRegex(WorkflowError, 'STALE'):
            self.service.save_planning(row['id'], 0, {'campaign': 'Stale'}, 'TEST FIXTURE')
        with self.assertRaisesRegex(WorkflowError, 'DATE_INVALID'):
            self.service.save_planning(row['id'], 1, {'planned_date': '2026-02-30'}, 'TEST FIXTURE')
        self.assertTrue(restarted.calendar()['planning_only'])

    def test_unknown_publication_date_never_borrows_retrieval_freshness(self):
        when = datetime(2026, 10, 6, tzinfo=timezone.utc)
        source = {'id': uuid.uuid4().hex, 'timestamp': None, 'retrieved_at': when.isoformat(), 'publication_date_known': False}
        result = freshness([source], self.service.catalog['freshness'], when)
        self.assertEqual(result['status'], 'DATE_UNKNOWN')
        self.assertEqual(result['score'], 0)
        self.assertTrue(result['needs_revalidation'])
        self.assertIsNone(result['sources'][0]['published_at'])
        self.assertEqual(result['sources'][0]['fetched_at'], when.isoformat())

    def test_future_and_stale_dates_are_explicit(self):
        when = datetime(2026, 10, 6, tzinfo=timezone.utc)
        for published, expected in [('2028-10-01T00:00:00+00:00', 'FUTURE_DATE'), ('2020-10-01T00:00:00+00:00', 'STALE')]:
            source = {'id': uuid.uuid4().hex, 'timestamp': published, 'retrieved_at': when.isoformat(), 'publication_date_known': True}
            result = freshness([source], self.service.catalog['freshness'], when)
            self.assertEqual(result['status'], expected)
            self.assertEqual(result['score'], 0)

    def test_configured_priority_is_explainable_and_not_prediction(self):
        config = deepcopy(self.service.catalog['priority'])
        config['weights'] = dict.fromkeys(config['weights'], 0); config['weights']['project_priority'] = 1
        value = priority(80, {'score': 60}, 'IDEA', {'campaign_priority': 30, 'project_priority': 90}, 0,
                         config, self.service.clock(), digest(config))
        self.assertEqual(value['score'], 90)
        self.assertEqual(value['scoring_type'], 'HEURISTIC_SCORING')
        penalty = priority(80, {'score': 60}, 'IDEA', {'campaign_priority': 30, 'project_priority': 90}, 1,
                           config, self.service.clock(), digest(config))
        self.assertEqual(penalty['score'], 70)

    def test_duplicates_require_current_reasoned_human_override_for_dispatch(self):
        first, second = self.approved(), self.approved()
        row = self.service.find(item_id('opportunity', first['opportunity']['id']))
        self.assertTrue(row['similarity']['warnings'])
        skipped = self.batch([row])
        self.assertEqual(skipped['items'][0]['code'], 'DUPLICATE_REVIEW_REQUIRED')
        row = self.override(row)
        self.assertTrue(row['similarity']['override_current'])
        accepted = self.batch([row])
        self.assertEqual(accepted['items'][0]['status'], 'QUEUED')
        changed = self.ci.store.get(second['brief']['idea_id'], 'ContentIdea')
        self.ci.edit_idea(changed['id'], changed['version'], {'hook': 'Different genuinely edited fixture hook'}, 'TEST FIXTURE')
        new_row = self.service.find(row['id'])
        self.assertFalse(new_row['similarity']['override_current'])

    def test_batch_explicit_gates_partial_results_idempotence_and_no_render(self):
        approved = self.approved()
        row = self.service.find(item_id('opportunity', approved['opportunity']['id']))
        direct = self.production.create('Unapproved direct input', 'No brief')
        direct_row = self.service.find(item_id('project', direct['id']))
        key = uuid.uuid4().hex
        result = self.batch([row, direct_row], key=key)
        self.assertEqual([r['status'] for r in result['items']], ['QUEUED', 'SKIPPED'])
        self.assertEqual(result['items'][1]['code'], 'APPROVED_BRIEF_WITHOUT_SCRIPT_REQUIRED')
        repeated = self.batch([row, direct_row], key=key)
        self.assertEqual(repeated, result)
        project = self.production.get(result['items'][0]['project_id'])
        self.assertEqual([j['kind'] for j in project['jobs']], ['content'])
        self.assertIsNone(project['approval'])
        self.assertFalse(result['automatic_approval']); self.assertFalse(result['render_dispatched'])
        with self.assertRaisesRegex(WorkflowError, 'HUMAN_BATCH'):
            self.service.batch({'action': 'render', 'items': [self.entry(row)], 'request_key': uuid.uuid4().hex, 'reviewer': 'TEST FIXTURE', 'acknowledged': True})
        with self.assertRaisesRegex(WorkflowError, 'IDEMPOTENCY_KEY'):
            self.batch([direct_row], key=key)

    def test_stale_batch_binding_is_not_dispatched(self):
        approved = self.approved()
        row = self.service.find(item_id('opportunity', approved['opportunity']['id']))
        brief = approved['brief']
        self.ci.edit_brief(brief['id'], brief['version'], {'hook': 'New fixture revision'}, 'TEST FIXTURE')
        result = self.batch([row])
        self.assertEqual(result['items'][0]['code'], 'BATCH_STALE_ITEM_RELOAD')
        self.assertEqual(self.production.list(), [])

    def test_unknown_batch_outcome_is_durable_and_never_implicitly_replayed(self):
        approved = self.approved(); row = self.service.find(item_id('opportunity', approved['opportunity']['id']))
        key = uuid.uuid4().hex
        with patch.object(self.production, 'enqueue', side_effect=RuntimeError('uncertain completion')) as enqueue:
            result = self.batch([row], key=key)
            self.assertEqual(result['items'][0]['status'], 'OUTCOME_UNKNOWN')
            restarted = ProductionIntelligence(self.config, self.production, self.ci)
            again = restarted.batch({'action': 'scripts', 'items': [self.entry(row)], 'request_key': key, 'reviewer': 'TEST FIXTURE', 'acknowledged': True})
            self.assertEqual(again, result); enqueue.assert_called_once()
        request = {'action': 'scripts', 'items': [self.entry(row)], 'reviewer': 'TEST FIXTURE', 'acknowledged': True}
        unfinished_key = uuid.uuid4().hex
        self.service.planning.begin_batch(unfinished_key, request)
        result = self.service.batch({**request, 'request_key': unfinished_key})
        self.assertEqual(result['status'], 'OUTCOME_UNKNOWN_NO_REPLAY')
        self.assertEqual(self.service.planning.batch_receipt(unfinished_key)['status'], 'OUTCOME_UNKNOWN_NO_REPLAY')
        self.assertEqual(self.service.planning.batch_receipt(key)['request'], {'action': 'scripts', 'items': [self.entry(row)], 'reviewer': 'TEST FIXTURE', 'acknowledged': True})

    def test_batch_receipt_tampering_is_refused(self):
        approved = self.approved(); row = self.service.find(item_id('opportunity', approved['opportunity']['id']))
        key = uuid.uuid4().hex; self.batch([row], key=key)
        with self.service.planning.transaction() as con:
            con.execute("UPDATE planning_batches SET document=replace(document,'QUEUED','UPDATED') WHERE request_key=?", (key,))
        with self.assertRaisesRegex(WorkflowError, 'RECEIPT_INTEGRITY'):
            self.service.planning.batch_receipt(key)

    def test_storyboard_batch_waits_for_script_review_and_preserves_approval_gate(self):
        approved = self.approved(); project = self.ci.send(approved['brief']['id'], approved['brief']['version'])
        project = self.production.save(project['id'], project['revision'], proposal=proposal(), asset={'id': 'fixture.jpg', 'sha256': 'test', 'rights_confirmed': True})
        row = self.service.find(item_id('opportunity', approved['opportunity']['id']))
        self.assertEqual(row['stage'], 'SCRIPT_REVIEW')
        result = self.batch([row], action='storyboards')
        self.assertEqual(result['items'][0]['code'], 'CURRENT_HUMAN_SCRIPT_REVIEW_REQUIRED')
        import hashlib
        self.production.review_script(project['id'], project['revision'], 'TEST FIXTURE', True, hashlib.sha256(project['document']['proposal']['narration'].encode()).hexdigest())
        row = self.service.find(row['id'])
        result = self.batch([row], action='storyboards')
        self.assertEqual(result['items'][0]['status'], 'UPDATED')
        current = self.production.get(project['id'])
        self.assertIsNotNone(current['document'].get('edit_plan')); self.assertIsNone(current['approval']); self.assertEqual(current['jobs'], [])

    def test_library_retains_approved_historical_snapshot_after_edit_and_archive(self):
        project, job = self.rendered(accepted=True)
        original = self.service.video(job['id'])
        self.production.save(project['id'], 2, proposal=proposal('Changed current narration'))
        self.production.archive(project['id'], 3, True)
        with self.assertRaisesRegex(WorkflowError, 'STALE'):
            self.production.final_video(job['id'])
        self.assertEqual(self.service.video(job['id']), original)
        item = self.service.library()['items'][0]
        self.assertTrue(item['approved']); self.assertFalse(item['is_current_project_revision']); self.assertTrue(item['archived'])
        self.assertEqual(item['snapshot_sha256'], digest(job['snapshot']))
        self.assertEqual(item['versions']['script_version'], digest(job['snapshot']['document']['proposal']))
        self.assertEqual(item['duration_seconds'], 45)

    def test_library_timeline_digest_is_actual_checkpoint_artifact_and_tamper_refused(self):
        project, job = self.rendered(accepted=True)
        timeline = self.root / 'jobs' / job['id'] / 'timeline.json'
        versions = self.service.library()['items'][0]['versions']
        self.assertEqual(versions['render_timeline_sha256'], file_sha(timeline))
        self.assertEqual(versions['timeline_schema_version'], '1.1')
        self.assertIsNone(versions['timeline_version'])
        timeline.write_text('{"schema_version":"changed fixture"}', encoding='utf-8')
        with self.assertRaisesRegex(WorkflowError, 'CHECKPOINT_ARTIFACT_CHANGED'):
            self.service.video(job['id'])
        row = self.service.library()['items'][0]
        self.assertEqual(row['integrity'], 'FAILED')
        self.assertFalse(row['approved']); self.assertIsNone(row['video_url'])

    def test_library_canvas_is_only_saved_verified_probe_and_campaign_is_current_planning(self):
        project, job = self.rendered(accepted=True)
        unknown = self.service.library()['items'][0]
        self.assertIsNone(unknown['width']); self.assertIsNone(unknown['height'])
        out = self.root / 'jobs' / job['id']; probe = out / 'ffprobe.json'
        probe.write_text(json.dumps({'streams': [{'codec_type': 'video', 'width': 1920, 'height': 1080}],
            'test_fixture': 'metadata transport only, not an actual FFmpeg result'}), encoding='utf-8')
        Artifacts(out, job).commit('render', [out / 'final.mp4', out / 'timeline.json', probe], job['result'])
        row = self.service.find(item_id('project', project['id']))
        self.service.save_planning(row['id'], 0, {'campaign': 'Current fixture campaign'}, 'TEST FIXTURE')
        item = self.service.library()['items'][0]
        self.assertEqual((item['width'], item['height'], item['aspect_ratio']), (1920, 1080, '16:9'))
        self.assertEqual(item['media_metadata_source'], 'verified_render_checkpoint_ffprobe')
        self.assertEqual(item['campaign'], 'Current fixture campaign'); self.assertEqual(item['campaign_source'], 'current_planning')
        self.assertTrue(item['approved']); self.assertEqual(item['sha256'], job['result']['qc']['final_sha256'])
        probe.write_text('{}', encoding='utf-8')
        item = self.service.library()['items'][0]
        self.assertEqual(item['integrity'], 'FAILED'); self.assertFalse(item['approved']); self.assertIsNone(item['width'])

    def test_unapproved_reviewed_and_tampered_video_states(self):
        project, job = self.rendered()
        self.assertEqual(self.service.find(item_id('project', project['id']))['stage'], 'VIDEO_REVIEW')
        self.assertFalse(self.service.library()['items'][0]['approved'])
        with self.assertRaisesRegex(WorkflowError, 'HUMAN_FINAL'):
            self.service.video(job['id'])
        self.production.review_render(job['id'], 2, 'TEST FIXTURE', True, 'approve')
        self.assertEqual(self.service.find(item_id('project', project['id']))['stage'], 'PRODUCED')
        (self.root / 'jobs' / job['id'] / 'final.mp4').write_bytes(b'changed bytes')
        self.assertEqual(self.service.find(item_id('project', project['id']))['stage'], 'FAILED')
        self.assertEqual(self.service.library()['items'][0]['integrity'], 'FAILED')
        with self.assertRaisesRegex(WorkflowError, 'CHANGED'):
            self.service.video(job['id'])

    def test_library_rejection_never_reuses_old_human_approval(self):
        project, job = self.rendered(accepted=True)
        self.production.review_render(job['id'], 2, 'TEST FIXTURE', False, 'reject', 'Fixture reconsideration')
        item = self.service.library()['items'][0]
        self.assertFalse(item['approved']); self.assertEqual(item['approval']['decision'], 'reject')
        with self.assertRaisesRegex(WorkflowError, 'HUMAN_FINAL'):
            self.service.video(job['id'])

    def test_profile_catalog_contains_five_configs_and_existing_voice(self):
        result = self.service.profiles()
        self.assertEqual({p['id'] for p in result['profiles']}, {'green-paradise', 'saigon-park', 'vang-nguyen', 'vietnam-property', 'infrastructure-news'})
        self.assertTrue(all(not p['voice']['new_credentials_required'] for p in result['profiles']))
        self.assertTrue(all(p['source_policy']['unknown_publication_date'] == 'NEEDS_REVALIDATION' for p in result['profiles']))
        self.assertTrue(all(set(p['supported_aspect_ratios']) == {'9:16', '16:9'} for p in result['profiles']))

    def test_optional_phase10_approval_requires_current_preflight_and_override(self):
        approved = self.approved()
        brief = self.ci.edit_brief(approved['brief']['id'], approved['brief']['version'], {'hook': 'A human edited fixture hook'}, 'TEST FIXTURE')
        self.approved()
        check = self.service.brief_preflight(brief['id'])
        self.assertTrue(check['human_override_required'])
        body = {'version': brief['version'], 'binding_sha256': check['binding_sha256'], 'reviewer': 'TEST FIXTURE', 'acknowledged': True}
        with self.assertRaisesRegex(WorkflowError, 'DUPLICATE_REVIEW_REQUIRED'):
            self.service.approve_brief(brief['id'], body)
        self.assertEqual(self.ci.store.get(brief['id'])['status'], 'DRAFT')
        self.override(self.service.find(check['item_id']))
        with self.assertRaisesRegex(WorkflowError, 'PREFLIGHT_CHANGED'):
            self.service.approve_brief(brief['id'], {**body, 'binding_sha256': '0' * 64})
        result = self.service.approve_brief(brief['id'], body)
        self.assertEqual(result['brief']['status'], 'APPROVED')
        self.assertEqual(self.production.list(), [])

    def test_ten_queue_cases_prioritize_and_explicitly_dispatch_five(self):
        cases = [self.approved() for _ in range(10)]
        rows = self.service.queue()['items']
        self.assertEqual(len(rows), 10)
        selected = []
        for index, row in enumerate(rows[:5]):
            row = self.service.save_planning(row['id'], row['planning']['version'],
                {'project_priority': 95 - index, 'campaign': 'TEST FIXTURE campaign', 'planned_date': '2026-10-20'}, 'TEST FIXTURE')
            selected.append(self.override(row))
        before = self.service.records()
        result = self.batch(selected)
        self.assertEqual([r['status'] for r in result['items']], ['QUEUED'] * 5)
        self.assertEqual(len(self.production.list()), 5)
        self.assertTrue(all(self.production.get(p['id'])['approval'] is None for p in self.production.list()))
        self.assertTrue(all([j['kind'] for j in self.production.get(p['id'])['jobs']] == ['content'] for p in self.production.list()))
        for case in cases:
            self.assertEqual(self.ci.store.get(case['brief']['id'])['approval'], before['ContentBrief'][case['brief']['id']]['approval'])

    def test_ci_render_library_lineage_remains_snapshot_bound(self):
        approved = self.approved(); project = self.ci.send(approved['brief']['id'], approved['brief']['version'])
        project = self.production.save(project['id'], 1, proposal=proposal(), asset={'id': 'fixture.jpg', 'rights_confirmed': True, 'sha256': 'fixture'})
        project = self.production.approve(project['id'], 2, 'TEST FIXTURE not human acceptance', True)
        job = self.production.enqueue(project['id'], 2, 'render', uuid.uuid4().hex)
        out = self.root / 'jobs' / job['id']; out.mkdir(parents=True); path = out / 'final.mp4'; path.write_bytes(b'CI TRANSPORT FIXTURE')
        result = {'qc': {'passed': True, 'final_sha256': file_sha(path)}, 'test_fixture': True}
        Artifacts(out, job).commit('render', [path], result)
        self.production.claim(); self.production.finish(job, result=result)
        self.production.review_render(job['id'], 2, 'TEST FIXTURE', True, 'approve')
        self.production.save(project['id'], 2, proposal=proposal('Current edited words'))
        row = self.service.library()['items'][0]
        self.assertEqual(row['lineage']['content_idea_id'], approved['brief']['idea_id'])
        self.assertEqual(row['lineage']['content_brief_id'], approved['brief']['id'])
        self.assertEqual(row['lineage']['content_brief_version'], approved['brief']['version'])
        self.assertEqual(row['versions']['script_version'], digest(job['snapshot']['document']['proposal']))

    def test_planning_tamper_is_detected_after_restart(self):
        project = self.production.create('Integrity fixture', 'Original')
        row = self.service.find(item_id('project', project['id']))
        self.service.save_planning(row['id'], 0, {'campaign': 'Original'}, 'TEST FIXTURE')
        with self.service.planning.transaction() as con:
            con.execute("UPDATE planning SET document=replace(document, 'Original', 'Changed')")
        with self.assertRaisesRegex(WorkflowError, 'INTEGRITY'):
            ProductionIntelligence(self.config, self.production, self.ci).queue()


class ProductionRoutesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = LocalServer(0, Config(data_root=Path(self.temp.name)), start_worker=False)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.project = self.server.store.create('HTTP transport fixture', 'No provider calls')

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=30)
        con.request(method, path, body=json.dumps(body) if body is not None else None,
            headers={'Content-Type': 'application/json', 'Cookie': 'vf_native_session=' + self.server.session,
                     'X-VF-CSRF': self.server.csrf, **(headers or {})})
        response = con.getresponse(); raw = response.read(); con.close()
        return response.status, json.loads(raw) if path.startswith('/api/') else raw

    def test_new_routes_preserve_session_csrf_and_origin_guards(self):
        path = '/api/production/queue'
        self.assertEqual(self.request('GET', path, headers={'Cookie': ''})[0], 401)
        status, queue = self.request('GET', path)
        self.assertEqual(status, 200)
        row = queue['items'][0]; planning = '/api/production/planning/' + row['id']
        body = {'version': 0, 'reviewer': 'HTTP TEST FIXTURE', 'changes': {'campaign': 'HTTP fixture'}}
        self.assertEqual(self.request('POST', planning, body, {'X-VF-CSRF': 'wrong'})[0], 403)
        self.assertEqual(self.request('POST', planning, body, {'Origin': 'https://untrusted.invalid'})[0], 403)
        self.assertEqual(self.request('POST', planning, body)[0], 200)
        self.assertEqual(self.request('GET', planning + '/history')[1][0]['version'], 1)
        self.assertEqual(self.request('GET', '/api/production/profiles')[0], 200)
        self.assertEqual(self.request('GET', '/api/production/calendar')[1]['publish_enabled'], False)
        self.assertEqual(self.request('GET', '/api/production/library')[1]['items'], [])
        self.assertEqual(self.request('GET', '/api/production/videos/' + '0' * 32, headers={'Cookie': ''})[0], 401)
        self.assertEqual(self.request('POST', '/api/production/batch', {'action': 'render', 'reviewer': 'HTTP TEST FIXTURE'})[0], 400)
        self.assertEqual(self.request('GET', '/api/production/batches/' + '0' * 32)[0], 404)
        self.assertEqual(self.server.store.get(self.project['id'])['revision'], 1)

    def test_staff_pages_and_assets_are_served(self):
        for path in ('/production?view=queue', '/production?view=calendar', '/production?view=library', '/production?view=profiles', '/production.mjs', '/production.css'):
            status, body = self.request('GET', path)
            self.assertEqual(status, 200, path)
            self.assertTrue(body)


if __name__ == '__main__':
    unittest.main()
