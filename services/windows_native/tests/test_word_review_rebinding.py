"""Independent copies of manual word history over real owned fixture media.

ASR and human review identities are explicit fixtures. No provider inference,
Owner acceptance, publishing or original-media mutation is claimed.
"""
import copy
import json
import unittest
import uuid
from unittest.mock import patch

from app.auto_edit_providers import MediaSignals
from services.windows_native import auto_edit_analysis as analysis
from services.windows_native import auto_edit_timeline as timeline
from services.windows_native import source_shorts, transcript_word_review
from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.tests import test_source_preview as fixture
from services.windows_native.tests.test_transcript_word_review import request


class WordReviewRebindingTests(unittest.TestCase):
    setUp = fixture.NativeSourcePreviewTests.setUp
    tearDown = fixture.NativeSourcePreviewTests.tearDown
    real_source = fixture.NativeSourcePreviewTests.real_source
    save_analysis = fixture.NativeSourcePreviewTests.save_analysis

    def reviewed(self, revisions=2):
        self.signals = MediaSignals(((1., .9), (2., .9)), (), {'fixture': True, 'provider_calls': 0})
        self.path = self.real_source()
        for index in range(revisions):
            bundle = analysis.view(self.store, self.project['id'])
            item = bundle['analyses'][0]
            current = item['analysis']['transcript']
            body = request(current, self.project['document']['canonical_timeline']['version'])
            body['segments'][0]['words'][0]['text'] = ('Vang' if index == 0 else 'Nguyễn')
            transcript_word_review.save(self.store, self.project['id'], bundle['revision'],
                item['analysis']['analysis_id'], body, actor_ref='fixture-editor',
                asset_sha256=item['asset_sha256'], analysis_sha256=item['analysis_sha256'])
            self.project = self.store.get(self.project['id'])
        return self.project

    def assert_rebound(self, parent, child):
        page = analysis.view(self.store, child['id'])
        self.assertEqual(page['pending_asset_ids'], [])
        new = page['analyses'][0]['analysis']['transcript']
        old = analysis.view(self.store, parent['id'])['analyses'][0]['analysis']['transcript']
        self.assertNotEqual(new['transcript_id'], old['transcript_id'])
        self.assertEqual(new['version'], old['version'])
        self.assertFalse(new['is_original_evidence'])
        self.assertFalse(new['provenance']['timing_independently_measured'])
        self.assertFalse(new['provenance']['identity_rebinding']['fresh_provider_measurement'])
        self.assertEqual(new['provenance']['identity_rebinding']['source_transcript_sha256'], digest(old))
        for left, right in zip(old['segments'], new['segments'], strict=True):
            self.assertNotEqual(left['segment_id'], right['segment_id'])
            for key in ('start_seconds', 'end_seconds', 'text', 'confidence'):
                self.assertEqual(left[key], right[key])
            for old_word, new_word in zip(left['words'], right['words'], strict=True):
                self.assertNotEqual(old_word['word_id'], new_word['word_id'])
                for key in ('ordinal', 'start_seconds', 'end_seconds', 'text', 'confidence'):
                    self.assertEqual(old_word[key], new_word[key])
        versions = child['document']['auto_edit_transcripts']
        old_ids = {value['transcript_id'] for value in parent['document']['auto_edit_transcripts']}
        indexed = child['document']['auto_edit_transcript_version_sha256']
        self.assertTrue(set(indexed).isdisjoint(old_ids))
        self.assertEqual(indexed, {value['transcript_id']: digest(value) for value in versions})
        available_segments = {segment['segment_id'] for value in page['analyses'][0]['transcript_history']
            for segment in value['segments']}
        for value in versions:
            self.assertTrue(set(value['provenance']['segment_id_mapping']) <= available_segments)
            self.assertTrue(set(value['provenance']['segment_id_mapping'].values()) <= available_segments)
        archived = child['document']['auto_edit_transcript_inherited_original_history'][-len(versions):]
        self.assertEqual([v['original_transcript'] for v in archived], parent['document']['auto_edit_transcripts'])
        self.assertTrue(all(v['original_transcript_sha256'] == digest(v['original_transcript'])
            and not v['authority_transferred'] and not v['fresh_provider_measurement'] for v in archived))
        self.assertEqual(child['document']['media_analysis'], parent['document']['media_analysis'])
        snapshot = child['document']['canonical_timeline']['snapshot']
        self.assertEqual(snapshot['metadata']['native_project_id'], child['id'])
        self.assertIsNone(child['approval'])
        self.assertEqual(child['jobs'], [])
        self.assertEqual(snapshot['metadata']['transcript_revision']['transcript_id'], new['transcript_id'])
        timeline.validate_document(child['document'])
        return new

    def test_duplicate_rekeys_all_hashed_versions_and_keeps_exact_original_lineage(self):
        parent = copy.deepcopy(self.reviewed())
        before_versions = self.store.versions(parent['id'])
        checksum = file_sha(self.path)
        with patch('services.windows_native.asr.analyze', side_effect=AssertionError('No ASR replay')):
            child = self.store.duplicate(parent['id'], parent['revision'])
            self.assert_rebound(parent, child)
        self.assertEqual(self.store.get(parent['id']), parent)
        self.assertEqual(self.store.versions(parent['id']), before_versions)
        self.assertEqual(file_sha(self.path), checksum)

    def test_auto_shorts_after_review_keeps_current_word_history_and_is_idempotent(self):
        parent = copy.deepcopy(self.reviewed())
        current = analysis.view(self.store, parent['id'])['analyses'][0]['analysis']
        body = {'analysis_id': current['analysis_id'], 'transcript_id': current['transcript']['transcript_id'],
            'expected_version': parent['document']['canonical_timeline']['version'], 'count': 3,
            'maximum_duration_seconds': 3., 'request_key': uuid.uuid4().hex, 'aspect_ratio': '9:16'}
        with patch('services.windows_native.asr.analyze', side_effect=AssertionError('No ASR replay')):
            result = source_shorts.create(self.store, self.config, parent['id'], parent['revision'], body)
            self.assertGreater(result['batch']['generated_count'], 0)
            for child in result['projects']:
                self.assert_rebound(parent, child)
            self.assertEqual(source_shorts.create(self.store, self.config, parent['id'], parent['revision'], body), result)
        self.assertEqual(self.store.get(parent['id']), parent)
        self.assertEqual((result['batch']['provider_calls'], result['batch']['paid_operations']), (0, 0))

    def test_corrupt_missing_or_orphaned_checksum_refuses_before_any_child_write(self):
        self.reviewed()
        document = copy.deepcopy(self.project['document'])
        checks = document['auto_edit_transcript_version_sha256']
        variants = []
        bad = copy.deepcopy(document); bad['auto_edit_transcript_version_sha256'][next(iter(checks))] = 'f' * 64
        variants.append(bad)
        bad = copy.deepcopy(document); bad['auto_edit_transcript_version_sha256'].pop(next(iter(checks)))
        variants.append(bad)
        bad = copy.deepcopy(document); bad['auto_edit_transcript_version_sha256']['trn_' + 'e' * 24] = 'e' * 64
        variants.append(bad)
        bad = copy.deepcopy(document); bad['auto_edit_transcript_version_sha256'] = []
        variants.append(bad)
        original_projects = self.store.list()
        for bad in variants:
            with self.store.transaction() as con:
                con.execute('UPDATE projects SET document=? WHERE id=?', (json.dumps(bad), self.project['id']))
            with self.assertRaisesRegex(WorkflowError, 'TRANSCRIPT_WORD_REVIEW_HISTORY_CHANGED'):
                self.store.duplicate(self.project['id'], self.project['revision'])
            self.assertEqual([p['id'] for p in self.store.list()], [p['id'] for p in original_projects])

    def test_child_word_review_and_second_copy_have_independent_version_and_custody(self):
        parent = copy.deepcopy(self.reviewed())
        child = self.store.duplicate(parent['id'], parent['revision'])
        bundle = analysis.view(self.store, child['id'])
        item = bundle['analyses'][0]
        body = request(item['analysis']['transcript'], child['document']['canonical_timeline']['version'])
        body['segments'][0]['words'][0]['text'] = 'Bản sửa riêng'
        transcript_word_review.save(self.store, child['id'], child['revision'], item['analysis']['analysis_id'],
            body, actor_ref='fixture-child-editor', asset_sha256=item['asset_sha256'],
            analysis_sha256=item['analysis_sha256'])
        child = self.store.get(child['id'])
        grandchild = self.store.duplicate(child['id'], child['revision'])
        self.assert_rebound(child, grandchild)
        self.assertEqual(self.store.get(parent['id']), parent)
        from services.windows_native.store import Store
        fresh = Store(self.root)
        self.assertEqual(analysis.view(fresh, grandchild['id']), analysis.view(self.store, grandchild['id']))
        original = parent['document']['auto_edit_transcripts']
        history = grandchild['document']['auto_edit_transcript_inherited_original_history']
        self.assertEqual([v['original_transcript'] for v in history[:len(original)]], original)

    def test_child_rehash_does_not_hide_tampered_manual_word_history(self):
        parent = self.reviewed()
        child = self.store.duplicate(parent['id'], parent['revision'])
        changed = copy.deepcopy(child['document'])
        changed['auto_edit_transcripts'][0]['segments'][0]['words'][0]['start_seconds'] += .01
        with self.store.transaction() as con:
            con.execute('UPDATE projects SET document=? WHERE id=?', (json.dumps(changed), child['id']))
        with self.assertRaisesRegex(WorkflowError, 'TRANSCRIPT_WORD_REVIEW_HISTORY_CHANGED'):
            analysis.view(self.store, child['id'])

    def test_current_scene_assessment_is_archived_verbatim_without_child_review_authority(self):
        self.reviewed()
        from services.windows_native import scene_assessments
        item = analysis.view(self.store, self.project['id'])['analyses'][0]
        current = item['analysis']['transcript']
        scene_assessments.create(self.store, self.project['id'], {
            'revision': self.project['revision'], 'analysis_id': item['analysis']['analysis_id'],
            'asset_sha256': item['asset_sha256'], 'analysis_sha256': item['analysis_sha256'],
            'expected_transcript_id': current['transcript_id'], 'expected_transcript_version': current['version'],
            'expected_transcript_sha256': digest(current),
            'expected_timeline_version': self.project['document']['canonical_timeline']['version'],
            'acknowledged_saved_evidence': True,
        }, workspace='wsp_word_scene_fixture', actor_ref='fixture-editor')
        parent = self.store.get(self.project['id'])
        original = copy.deepcopy(parent['document']['source_scene_assessments'][0])
        document = copy.deepcopy(parent['document'])
        metadata = document['canonical_timeline']['snapshot']['metadata']
        proof = scene_assessments.lineage(original)
        metadata['reviewed_local_scene_selection'] = proof
        highlighted = original['assessment']['result']['scene_ranking'][0]['highlight_id']
        metadata['reviewed_highlight_id'] = highlighted
        document['canonical_timeline']['sha256'] = digest(document['canonical_timeline']['snapshot'])
        with self.store.transaction() as con:
            con.execute('UPDATE projects SET document=? WHERE id=?', (json.dumps(document), parent['id']))
        parent = self.store.get(parent['id'])
        child = self.store.duplicate(parent['id'], parent['revision'])
        self.assert_rebound(parent, child)
        self.assertNotIn('source_scene_assessments', child['document'])
        archived = child['document']['source_scene_inherited_assessment_history'][-1]
        self.assertEqual(archived['original_record'], original)
        self.assertEqual(archived['original_record_sha256'], digest(original))
        self.assertFalse(archived['authority_transferred'])
        metadata = child['document']['canonical_timeline']['snapshot']['metadata']
        self.assertNotIn('reviewed_local_scene_selection', metadata)
        self.assertNotIn('reviewed_highlight_id', metadata)
        inherited = metadata['inherited_reviewed_local_scene_selection']
        self.assertEqual(inherited['original_selection'], proof)
        self.assertEqual(inherited['original_highlight_id'], highlighted)
        self.assertFalse(inherited['authority_transferred'])
        self.assertEqual(self.store.get(parent['id']), parent)

    def test_review_outside_retained_window_cannot_regenerate_locked_caption_identity(self):
        self.real_source(source_window=(.2, .6))
        state = self.project['document']['canonical_timeline']
        subtitles = next(t for t in state['snapshot']['tracks'] if t['kind'] == 'subtitles')
        self.assertGreater(len(subtitles['clips']), 0)
        timeline.edit(self.store, self.project['id'], self.project['revision'], {'expected_version': state['version'],
            'operations': [{'type': 'set_track_state', 'track_id': subtitles['track_id'], 'locked': True}]})
        self.project = self.store.get(self.project['id'])
        item = analysis.view(self.store, self.project['id'])['analyses'][0]
        current = item['analysis']['transcript']; outside = current['segments'][1]
        body = request(current, self.project['document']['canonical_timeline']['version'])
        body['segments'] = [{'segment_id': outside['segment_id'], 'start_seconds': outside['start_seconds'],
            'end_seconds': outside['end_seconds'], 'words': [{k: w[k] for k in
                ('word_id', 'text', 'start_seconds', 'end_seconds')} for w in outside['words']]}]
        body['segments'][0]['words'][0]['text'] = 'Ngoài cửa sổ'
        before = copy.deepcopy(self.project)
        with self.assertRaisesRegex(WorkflowError, 'LOCKED'):
            transcript_word_review.save(self.store, self.project['id'], self.project['revision'],
                item['analysis']['analysis_id'], body, actor_ref='fixture-editor',
                asset_sha256=item['asset_sha256'], analysis_sha256=item['analysis_sha256'])
        self.assertEqual(self.store.get(self.project['id']), before)

    def test_foreign_subtitle_track_does_not_receive_asr_captions_during_word_review(self):
        self.real_source()
        document = copy.deepcopy(self.project['document']); state = document['canonical_timeline']
        source = next(t for t in state['snapshot']['tracks'] if t['kind'] == 'subtitles')
        foreign = copy.deepcopy(source); foreign['track_id'] = 'trk_foreign_' + uuid.uuid4().hex[:24]
        foreign['order'] = len(state['snapshot']['tracks'])
        foreign['locked'] = True; foreign['clips'] = [copy.deepcopy(source['clips'][0])]
        foreign['clips'][0].update(clip_id='clip_' + uuid.uuid4().hex[:24], label='Phụ đề độc lập')
        foreign['clips'][0]['metadata'] = {'language': 'vi', 'subtitle_text': 'Phụ đề độc lập',
            'transcript_id': 'trn_' + 'f' * 24}
        state['snapshot']['tracks'].append(foreign); state['sha256'] = digest(state['snapshot'])
        timeline.validate_document(document)
        with self.store.transaction() as con:
            con.execute('UPDATE projects SET document=? WHERE id=?', (json.dumps(document), self.project['id']))
        self.project = self.store.get(self.project['id'])
        item = analysis.view(self.store, self.project['id'])['analyses'][0]
        body = request(item['analysis']['transcript'], state['version'])
        body['segments'][0]['words'][0]['text'] = 'Bản sửa riêng'
        transcript_word_review.save(self.store, self.project['id'], self.project['revision'],
            item['analysis']['analysis_id'], body, actor_ref='fixture-editor',
            asset_sha256=item['asset_sha256'], analysis_sha256=item['analysis_sha256'])
        after = self.store.get(self.project['id'])['document']['canonical_timeline']['snapshot']
        self.assertEqual(next(t for t in after['tracks'] if t['track_id'] == foreign['track_id']), foreign)

    def test_reviewed_segment_is_not_duplicated_into_other_derived_caption_track(self):
        self.real_source()
        document = copy.deepcopy(self.project['document']); state = document['canonical_timeline']
        track1 = next(t for t in state['snapshot']['tracks'] if t['kind'] == 'subtitles')
        item = analysis.view(self.store, self.project['id'])['analyses'][0]
        current = item['analysis']['transcript']; first_id = current['segments'][0]['segment_id']
        second_id = current['segments'][1]['segment_id']
        track2 = copy.deepcopy(track1); track2['track_id'] = 'trk_second_' + uuid.uuid4().hex[:24]
        track2['order'] = len(state['snapshot']['tracks'])
        track2['clips'] = [c for c in track2['clips'] if c['metadata']['segment_id'] == second_id]
        track1['clips'] = [c for c in track1['clips'] if c['metadata']['segment_id'] == first_id]
        self.assertEqual(len(track1['clips']), 1); self.assertEqual(len(track2['clips']), 1)
        old_second = copy.deepcopy(track2['clips'][0])
        state['snapshot']['tracks'].append(track2); state['sha256'] = digest(state['snapshot'])
        timeline.validate_document(document)
        with self.store.transaction() as con:
            con.execute('UPDATE projects SET document=? WHERE id=?', (json.dumps(document), self.project['id']))
        self.project = self.store.get(self.project['id'])
        body = request(current, state['version']); body['segments'][0]['words'][0]['text'] = 'Sửa cảnh một'
        transcript_word_review.save(self.store, self.project['id'], self.project['revision'],
            item['analysis']['analysis_id'], body, actor_ref='fixture-editor',
            asset_sha256=item['asset_sha256'], analysis_sha256=item['analysis_sha256'])
        after = self.store.get(self.project['id'])['document']['canonical_timeline']['snapshot']
        changed_track = next(t for t in after['tracks'] if t['track_id'] == track1['track_id'])
        untouched_track = next(t for t in after['tracks'] if t['track_id'] == track2['track_id'])
        self.assertEqual(len(changed_track['clips']), 1); self.assertEqual(len(untouched_track['clips']), 1)
        self.assertIn('Sửa cảnh một', changed_track['clips'][0]['metadata']['reviewed_word_text'])
        second = untouched_track['clips'][0]
        for field in ('clip_id', 'source_start', 'source_end', 'timeline_start', 'duration', 'speed', 'label'):
            self.assertEqual(second[field], old_second[field])
        self.assertNotIn('human_word_timing_review', second['metadata'])
        self.assertNotEqual(second['metadata']['segment_id'], second_id)
        self.assertNotEqual(second['metadata']['transcript_id'], current['transcript_id'])

    def test_generic_copy_before_timeline_archives_assessment_without_requiring_canonical(self):
        plain = self.store.create('Plain draft fixture', '', 'media')
        copied = self.store.duplicate(plain['id'], plain['revision'])
        self.assertNotIn('canonical_timeline', copied['document'])
        self.assertIsNone(copied['approval']); self.assertEqual(copied['jobs'], [])
        self.assertEqual(self.store.get(plain['id']), plain)
        self.path = self.real_source()
        document = copy.deepcopy(self.project['document'])
        document.pop('canonical_timeline'); document.pop('source_timeline_mutations', None)
        with self.store.transaction() as con:
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?', (json.dumps(document), self.project['id']))
            self.store.version(con, self.project['id'])
        self.project = self.store.get(self.project['id'])
        from services.windows_native import scene_assessments
        from services.windows_native.tests.test_scene_assessments import body as assessment_body
        page = scene_assessments.page(self.store, self.project['id'], 'wsp_before_timeline_fixture')
        self.assertIsNone(page['timeline_version'])
        saved = scene_assessments.create(self.store, self.project['id'], assessment_body(page),
            workspace='wsp_before_timeline_fixture', actor_ref='fixture-editor')
        parent = copy.deepcopy(self.store.get(self.project['id'])); checksum = file_sha(self.path)
        child = self.store.duplicate(parent['id'], parent['revision'])
        self.assertNotIn('canonical_timeline', child['document'])
        self.assertNotIn('source_scene_assessments', child['document'])
        inherited = child['document']['source_scene_inherited_assessment_history'][-1]
        original = {key: saved['items'][0][key] for key in ('assessment', 'sha256')}
        self.assertEqual(inherited['original_record'], original)
        self.assertEqual(inherited['original_record_sha256'], digest(original))
        self.assertFalse(inherited['authority_transferred']); self.assertTrue(inherited['new_review_required'])
        self.assertEqual(child['document']['media_analysis'], parent['document']['media_analysis'])
        self.assertIsNone(child['approval']); self.assertEqual(child['jobs'], [])
        self.assertEqual(self.store.get(parent['id']), parent)
        self.assertEqual(file_sha(self.path), checksum)


if __name__ == '__main__':
    unittest.main()
