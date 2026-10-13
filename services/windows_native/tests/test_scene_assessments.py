"""Saved-current-text scene assessment over actual owned fixture media.

ASR text, human identities and review acknowledgements are explicit fixtures;
there is no semantic Vision inference, paid provider operation or Owner UAT.
"""
import copy
import json
import unittest
import uuid
from unittest.mock import patch

from app.auto_edit_providers import MediaSignals
from services.windows_native import auto_edit_analysis as analysis, auto_edit_timeline as timeline
from services.windows_native import scene_assessments as scenes, source_shorts, transcript_word_review
from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.store import Store
from services.windows_native.tests import test_source_preview as fixture
from services.windows_native.tests.test_transcript_word_review import request as word_request


def body(page):
    ref = page['available_sources'][0]
    return {'revision': page['revision'], 'analysis_id': ref['analysis_id'],
        'asset_sha256': ref['asset_sha256'], 'analysis_sha256': ref['analysis_sha256'],
        'expected_transcript_id': ref['transcript_id'], 'expected_transcript_version': ref['transcript_version'],
        'expected_transcript_sha256': ref['transcript_sha256'],
        'expected_timeline_version': page['timeline_version'], 'acknowledged_saved_evidence': True}


def selection(record):
    return {'assessment_id': record['assessment']['assessment_id'],
        'expected_assessment_sha256': record['sha256'], 'acknowledged': True}


class SceneAssessmentTests(unittest.TestCase):
    workspace = 'wsp_scene_assessment_fixture'
    save_analysis = fixture.NativeSourcePreviewTests.save_analysis
    real_source = fixture.NativeSourcePreviewTests.real_source

    def setUp(self):
        fixture.NativeSourcePreviewTests.setUp(self)
        self.signals = MediaSignals(((1., .9), (2., .9)), (), {'fixture': True, 'provider_calls': 0})
        self.path = self.real_source()

    tearDown = fixture.NativeSourcePreviewTests.tearDown

    def page(self):
        return scenes.page(self.store, self.project['id'], self.workspace)

    def create(self, request_body=None):
        value = scenes.create(self.store, self.project['id'], request_body or body(self.page()),
            workspace=self.workspace, actor_ref='fixture-editor')
        self.project = self.store.get(self.project['id'])
        return value

    def correct(self):
        page = analysis.view(self.store, self.project['id']); item = page['analyses'][0]
        request = word_request(item['analysis']['transcript'], self.project['document']['canonical_timeline']['version'])
        request['segments'][0]['words'][0]['text'] = 'important opportunity evidence breakthrough mistake'
        transcript_word_review.save(self.store, self.project['id'], page['revision'], item['analysis']['analysis_id'],
            request, actor_ref='fixture-editor', asset_sha256=item['asset_sha256'], analysis_sha256=item['analysis_sha256'])
        self.project = self.store.get(self.project['id'])

    def test_save_is_immutable_recommendation_and_same_input_reuses_record_without_revision(self):
        before = copy.deepcopy(self.project); checksum = file_sha(self.path)
        with patch('services.windows_native.asr.analyze', side_effect=AssertionError('No ASR replay')):
            page = self.create(); saved = copy.deepcopy(self.project)
            self.assertEqual(self.create(), page)
        self.assertEqual(self.project, saved)
        for field in ('canonical_timeline', 'auto_edit_analyses', 'media_analysis'):
            self.assertEqual(saved['document'][field], before['document'][field])
        self.assertEqual(saved['jobs'], before['jobs']); self.assertIsNone(saved['approval'])
        self.assertEqual(file_sha(self.path), checksum)
        value = page['items'][0]['assessment']
        self.assertTrue(page['items'][0]['current'])
        self.assertTrue(value['recommendation_only'])
        self.assertEqual(value['semantic_vision_state'], 'NOT_CONFIGURED')
        self.assertFalse(value['result']['prediction_confidence_calibrated'])
        self.assertFalse(value['result']['owner_uat_accepted'])
        self.assertEqual(value['source_document_sha256'], digest(before['document']))
        self.assertEqual(scenes.page(Store(self.root), self.project['id'], self.workspace), page)

    def test_manual_words_refresh_keywords_ranking_and_old_selection_becomes_stale(self):
        old = self.create()['items'][0]; self.correct(); before = copy.deepcopy(self.project)
        self.assertFalse(self.page()['items'][0]['current'])
        with self.store.transaction() as con:
            with self.assertRaisesRegex(WorkflowError, 'NATIVE_SCENE_ASSESSMENT_INPUT_CHANGED'):
                scenes.selected(self.store, self.project, scenes.Selection.model_validate(selection(old)),
                    old['assessment']['input_refs']['analysis_id'], con)
        current_transcript = analysis.view(self.store, self.project['id'])['analyses'][0]['analysis']['transcript']
        with self.assertRaisesRegex(WorkflowError, 'NATIVE_SCENE_ASSESSMENT_INPUT_CHANGED'):
            timeline.create(self.store, self.project['id'], self.project['revision'], {
                'analysis_id': old['assessment']['input_refs']['analysis_id'], 'transcript_id': current_transcript['transcript_id'],
                'expected_version': self.project['document']['canonical_timeline']['version'],
                'reviewed_local_scene': selection(old),
                'reviewed_highlight_id': old['assessment']['result']['scene_ranking'][0]['highlight_id'],
            }, config=self.config)
        self.assertEqual(self.store.get(self.project['id']), before)
        page = self.create(); current = page['items'][-1]
        self.assertEqual(current['assessment']['version'], 2)
        self.assertFalse(page['items'][0]['current']); self.assertTrue(current['current'])
        result = current['assessment']['result']
        self.assertTrue(any('important' in s['evidence']['transcript_keywords'] for s in result['scenes']))
        self.assertTrue(any('breakthrough' in h['evidence']['hook_keywords'] for h in result['scene_ranking']))
        self.assertNotEqual(result['scene_ranking'], old['assessment']['result']['scene_ranking'])
        self.assertTrue(all(s['evidence']['transcript_version'] == 2 for s in result['scenes']))
        self.assertEqual(self.project['document']['auto_edit_analyses'], before['document']['auto_edit_analyses'])
        self.assertEqual(self.project['document']['canonical_timeline'], before['document']['canonical_timeline'])

    def test_rehashed_false_results_and_foreign_historical_bindings_are_rejected(self):
        self.create(); original = copy.deepcopy(self.project['document'])
        variations = (
            lambda value: value['result']['scene_ranking'][0].update(highlight_score=.999999),
            lambda value: value['input_refs'].update(transcript_id='trn_' + 'f' * 24),
            lambda value: value.update(project_id='e' * 32),
            lambda value: value.update(input_sha256='e' * 64),
            lambda value: value.update(source_document_sha256='d' * 64),
            lambda value: value['result'].update(semantic_vision_used=True),
            lambda value: value.update(recommendation_only=1),
        )
        for mutate in variations:
            document = copy.deepcopy(original); record = document['source_scene_assessments'][0]
            mutate(record['assessment']); record['sha256'] = digest(record['assessment'])
            with self.store.transaction() as con:
                con.execute('UPDATE projects SET document=? WHERE id=?', (json.dumps(document), self.project['id']))
            with self.assertRaisesRegex(WorkflowError, 'NATIVE_SCENE_ASSESSMENT_HISTORY_INVALID'):
                self.page()
        with self.store.transaction() as con:
            con.execute('UPDATE projects SET document=? WHERE id=?', (json.dumps(original), self.project['id']))
        with self.assertRaisesRegex(WorkflowError, 'NATIVE_SCENE_ASSESSMENT_WORKSPACE_CHANGED'):
            scenes.page(self.store, self.project['id'], 'wsp_foreign_fixture')

    def test_unknown_foreign_stale_and_unacknowledged_inputs_fail_without_writes(self):
        current = body(self.page()); before = copy.deepcopy(self.store.get(self.project['id']))
        for values in ({'actor_ref': 'forged-owner'}, {'expected_transcript_id': 'trn_' + 'f' * 24},
            {'expected_transcript_sha256': 'f' * 64}, {'analysis_sha256': 'e' * 64},
            {'asset_sha256': 'd' * 64}, {'expected_timeline_version': 99},
            {'acknowledged_saved_evidence': False}, {'acknowledged_saved_evidence': 1}, {'revision': 99}):
            with self.assertRaises(WorkflowError): self.create({**current, **values})
            self.assertEqual(self.store.get(self.project['id']), before)

    def test_missing_or_changed_source_retains_history_but_refuses_new_assessment(self):
        saved = self.create(); request = body(saved); before = copy.deepcopy(self.project)
        self.path.write_bytes(b'Owned corrupt fixture media')
        page = self.page()
        self.assertEqual(page['available_sources'], [])
        self.assertFalse(page['items'][0]['current'])
        self.assertEqual(page['items'][0]['assessment'], saved['items'][0]['assessment'])
        with self.assertRaises(WorkflowError): self.create(request)
        self.assertEqual(self.store.get(self.project['id']), before)

    def test_reviewed_highlight_applies_exact_lineage_and_requires_human_approval(self):
        self.correct(); record = self.create()['items'][0]; before = copy.deepcopy(self.project)
        value = record['assessment']; highlight = value['result']['scene_ranking'][0]
        request = {'analysis_id': value['input_refs']['analysis_id'], 'transcript_id': value['input_refs']['transcript_id'],
            'expected_version': self.project['document']['canonical_timeline']['version'],
            'reviewed_local_scene': selection(record), 'reviewed_highlight_id': highlight['highlight_id'], 'aspect_ratio': '4:5'}
        applied = timeline.create(self.store, self.project['id'], self.project['revision'], request, config=self.config)
        snapshot = applied['document']['canonical_timeline']['snapshot']; metadata = snapshot['metadata']
        self.assertEqual(metadata['reviewed_local_scene_selection'], scenes.lineage(record))
        self.assertEqual(metadata['reviewed_highlight_id'], highlight['highlight_id'])
        self.assertTrue(metadata['human_review_required']); self.assertIsNone(applied['approval'])
        self.assertEqual(applied['document']['auto_edit_analyses'], before['document']['auto_edit_analyses'])
        self.assertEqual(applied['document']['media_analysis'], before['document']['media_analysis'])
        timeline.validate_document(applied['document'])
        before_bad = self.store.get(self.project['id'])
        with self.assertRaises(WorkflowError):
            timeline.create(self.store, self.project['id'], applied['revision'], {
                **request, 'expected_version': applied['document']['canonical_timeline']['version'], 'source_window': [0., .5]}, config=self.config)
        self.assertEqual(self.store.get(self.project['id']), before_bad)

    def test_reviewed_auto_shorts_drafts_are_unapproved_archived_and_replay_without_new_work(self):
        self.correct(); record = self.create()['items'][0]; before = copy.deepcopy(self.project)
        value = record['assessment']; request = {
            'analysis_id': value['input_refs']['analysis_id'], 'transcript_id': value['input_refs']['transcript_id'],
            'expected_version': self.project['document']['canonical_timeline']['version'], 'count': 3,
            'maximum_duration_seconds': 3., 'request_key': uuid.uuid4().hex, 'aspect_ratio': '9:16',
            'reviewed_local_scene': selection(record)}
        with patch('services.windows_native.asr.analyze', side_effect=AssertionError('No provider replay')):
            result = source_shorts.create(self.store, self.config, self.project['id'], self.project['revision'], request)
            self.assertEqual(source_shorts.create(self.store, self.config, self.project['id'], self.project['revision'], request), result)
        self.assertGreater(result['batch']['generated_count'], 0)
        self.assertEqual((result['batch']['provider_calls'], result['batch']['paid_operations']), (0, 0))
        self.assertEqual(result['batch']['scene_evidence']['reviewed_local_scene_selection'], scenes.lineage(record))
        for child in result['projects']:
            self.assertIsNone(child['approval']); self.assertEqual(child['jobs'], [])
            metadata = child['document']['canonical_timeline']['snapshot']['metadata']
            # These are exact historical parent references, not rebound child
            # selection authority or a new assessment of the child.
            self.assertEqual(metadata['highlight_draft']['reviewed_local_scene_selection'], scenes.lineage(record))
            self.assertEqual(metadata['source_short']['evidence']['reviewed_local_scene_selection'], scenes.lineage(record))
            self.assertNotIn('reviewed_local_scene_selection', metadata)
            self.assertNotIn('source_scene_assessments', child['document'])
            original = child['document']['source_scene_inherited_assessment_history'][-1]
            self.assertEqual(original['original_record'], {k: record[k] for k in ('assessment', 'sha256')})
            self.assertFalse(original['authority_transferred'])
            self.assertEqual(scenes.page(self.store, child['id'], self.workspace)['items'], [])
            child_analysis = analysis.view(self.store, child['id'])['analyses'][0]['analysis']
            self.assertEqual(child_analysis['transcript']['version'], 2)
            self.assertNotEqual(child_analysis['analysis_id'],
                metadata['highlight_draft']['reviewed_local_scene_selection']['input_refs']['analysis_id'])
            timeline.validate_document(child['document'])
        self.assertEqual(self.store.get(self.project['id']), before)

    def test_active_job_and_archived_project_refuse_assessment_write(self):
        request = body(self.page())
        self.store.enqueue(self.project['id'], self.project['revision'], 'media_frames', uuid.uuid4().hex)
        before = self.store.get(self.project['id'])
        with self.assertRaisesRegex(WorkflowError, 'PROJECT_BUSY'): self.create(request)
        self.assertEqual(self.store.get(self.project['id']), before)
        with self.store.transaction() as con:
            con.execute("UPDATE jobs SET status='failed' WHERE project_id=? AND kind='media_frames'", (self.project['id'],))
        self.store.archive(self.project['id'], self.project['revision'], True)
        with self.assertRaisesRegex(WorkflowError, 'PROJECT_ARCHIVED'): self.create(request)

    def test_invalid_old_assessment_cannot_be_extended_after_new_transcript_input(self):
        self.create(); self.correct(); request = body(self.page())
        document = copy.deepcopy(self.project['document'])
        record = document['source_scene_assessments'][0]
        record['assessment']['result']['scene_ranking'][0]['highlight_score'] = .999999
        record['sha256'] = digest(record['assessment'])
        with self.store.transaction() as con:
            con.execute('UPDATE projects SET document=? WHERE id=?', (json.dumps(document), self.project['id']))
        before = self.store.get(self.project['id']); versions = self.store.versions(self.project['id'])
        with self.assertRaisesRegex(WorkflowError, 'NATIVE_SCENE_ASSESSMENT_HISTORY_INVALID'):
            self.create(request)
        self.assertEqual(self.store.get(self.project['id']), before)
        self.assertEqual(self.store.versions(self.project['id']), versions)

    def test_locked_tracks_allow_assessment_without_unlocking_or_changing_canonical(self):
        state = self.project['document']['canonical_timeline']
        tracks = [t for t in state['snapshot']['tracks'] if t['kind'] in ('source', 'subtitles')]
        timeline.edit(self.store, self.project['id'], self.project['revision'], {'expected_version': state['version'],
            'operations': [{'type': 'set_track_state', 'track_id': t['track_id'], 'locked': True} for t in tracks]})
        self.project = self.store.get(self.project['id']); before = copy.deepcopy(self.project['document']['canonical_timeline'])
        self.create()
        self.assertEqual(self.project['document']['canonical_timeline'], before)
        self.assertTrue(all(t['locked'] for t in before['snapshot']['tracks'] if t['kind'] in ('source', 'subtitles')))


if __name__ == '__main__':
    unittest.main()
