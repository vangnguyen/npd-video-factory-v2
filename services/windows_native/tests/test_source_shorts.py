"""Atomic drafts over actual synthetic bytes and explicit saved ASR/shot fixtures."""
import copy
import json
import subprocess
import sys
import unittest
import uuid
from unittest.mock import patch
from services.windows_native import source_shorts as shorts,auto_edit_analysis as analysis,auto_edit_timeline as timeline
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.tests import test_source_preview as fixture
from app.auto_edit_providers import MediaSignals


class SourceShortsTests(unittest.TestCase):
    setUp=fixture.NativeSourcePreviewTests.setUp
    tearDown=fixture.NativeSourcePreviewTests.tearDown
    save_analysis=fixture.NativeSourcePreviewTests.save_analysis
    real_source=fixture.NativeSourcePreviewTests.real_source

    def source(self):
        self.signals=MediaSignals(((1.,.9),(2.,.9)),(),{'fixture':True,'provider_calls':0})
        self.path=self.real_source()
        current=analysis.view(self.store,self.project['id'])['analyses'][0]['analysis']
        self.body={'analysis_id':current['analysis_id'],'transcript_id':current['transcript']['transcript_id'],
            'expected_version':1,'count':3,'maximum_duration_seconds':3,'request_key':uuid.uuid4().hex,'aspect_ratio':'4:5'}
        return current

    def create(self,**values):
        return shorts.create(self.store,self.config,self.project['id'],self.project['revision'],{**self.body,**values})

    def test_top3_independent_speech_safe_drafts_and_retry_preserve_parent(self):
        current=self.source();before=copy.deepcopy(self.project);versions=self.store.versions(self.project['id']);checksum=file_sha(self.path)
        result=self.create();self.assertEqual(result['batch']['generated_count'],3)
        words=[w for s in current['transcript']['segments'] for w in s['words']]
        for child,entry in zip(result['projects'],result['batch']['drafts'],strict=True):
            self.assertIsNone(child['approval']);self.assertEqual(child['jobs'],[])
            self.assertEqual(child['revision'],1);self.assertEqual(child['shot_timeline']['version'],1)
            snap=child['shot_timeline']['snapshot'];self.assertLessEqual(snap['duration_seconds'],3)
            self.assertEqual((snap['width'],snap['height']),(1080,1350))
            self.assertEqual(snap['metadata']['native_project_id'],child['id'])
            self.assertEqual(snap['metadata']['source_short']['parent_project_id'],self.project['id'])
            self.assertEqual(snap['metadata']['source_short']['parent_document_sha256'],result['batch']['source_document_sha256'])
            for boundary in entry['source_window']:
                self.assertFalse(any(w['start_seconds']<boundary<w['end_seconds'] for w in words))
            self.assertFalse(analysis.pending(child['document'],child['id']))
        self.assertEqual(self.create(),result)
        self.assertEqual(timeline.view(self.store,self.project['id']),before)
        self.assertEqual(self.store.versions(self.project['id']),versions);self.assertEqual(file_sha(self.path),checksum)
        self.assertEqual(len(shorts.view(self.store,self.project['id'])['batches']),1)

    def test_top5_reports_only_three_available_candidates_without_fabrication(self):
        self.source();result=self.create(count=5)
        self.assertEqual(result['batch']['requested_count'],5);self.assertEqual(result['batch']['generated_count'],3)
        self.assertTrue(result['batch']['fewer_candidates_than_requested'])

    def test_atomic_rollback_after_first_insert_and_bad_media_leaves_no_drafts(self):
        self.source();before=self.store.list();versions=self.store.versions(self.project['id']);original=shorts.resolve_assets;count=0
        def fail_second(*args):
            nonlocal count
            count+=1
            if count==2:raise WorkflowError('EXPLICIT_SECOND_CHILD_FAILURE_FIXTURE')
            return original(*args)
        with patch.object(shorts,'resolve_assets',side_effect=fail_second):
            with self.assertRaisesRegex(WorkflowError,'EXPLICIT_SECOND_CHILD_FAILURE_FIXTURE'):self.create()
        self.assertEqual(self.store.list(),before);self.assertEqual(self.store.versions(self.project['id']),versions)
        self.assertEqual(shorts.view(self.store,self.project['id'])['batches'],[])
        self.path.write_bytes(b'Corrupted isolated fixture')
        with self.assertRaisesRegex(WorkflowError,'SOURCE_MEDIA_CHANGED_OR_MISSING'):self.create()
        self.assertEqual(self.store.list(),before)

    def test_version_idempotency_and_client_claims_reject_without_extra_projects(self):
        self.source();result=self.create();before=self.store.list()
        for values,error in [({'count':5},'AUTO_SHORTS_IDEMPOTENCY_CONFLICT'),
                ({'request_key':uuid.uuid4().hex,'expected_version':99},'AUTO_EDIT_TIMELINE_VERSION_CHANGED'),
                ({'request_key':uuid.uuid4().hex,'transcript_id':'trn_'+'f'*24},'AUTO_EDIT_TRANSCRIPT_VERSION_CHANGED'),
                ({'actor_ref':'owner'},'AUTO_SHORTS_REQUEST_INVALID'),({'count':4},'AUTO_SHORTS_REQUEST_INVALID')]:
            with self.assertRaisesRegex(WorkflowError,error):self.create(**values)
            self.assertEqual(self.store.list(),before)
        self.assertEqual(result['batch']['provider_calls'],0);self.assertEqual(result['batch']['paid_operations'],0)

    def test_native_planning_import_has_no_api_database_or_repository_dependency(self):
        subprocess.run([sys.executable,'-c',"import sys;sys.path.insert(0,'apps/api');from services.windows_native import source_shorts;assert not any(n.startswith('sqlalchemy') or n in {'app.auto_edit_db','app.timeline_repository'} for n in sys.modules)"],check=True,capture_output=True,timeout=10)


if __name__=='__main__':unittest.main()
