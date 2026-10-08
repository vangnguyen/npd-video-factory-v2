"""Guided creation/authority guards over actual storage and canonical media."""
import copy,json,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from services.windows_native.tests import test_shot_production as media
from services.windows_native.tests import test_intelligence_workflow as intelligence
from services.windows_native.tests import test_access_http as http
from services.windows_native.tests import test_narration as narration_fixture
from services.windows_native.narrated_workflow import reference,required
from services.windows_native.narration import apply
from services.windows_native.pipeline import Pipeline
from services.windows_native.branding import FIT_NARRATION_POLICY
from services.windows_native.contracts import WorkflowError,digest,write_json
from services.windows_native.hardening import Artifacts

class GuidedNarrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.config,self.store,self.legacy=media.prepared(self.root)
        self.unchanged=copy.deepcopy(self.store.get(self.legacy['id']))
        p=self.store.create('Guided isolated fixture','No provider',production_quality=True,narrated_workflow=True)
        for asset in self.legacy['document']['assets']:p=self.store.append_media(p['id'],p['revision'],asset)
        p=self.store.save(p['id'],p['revision'],proposal=self.legacy['document']['proposal'],scene_media=self.legacy['document']['scene_media'],music_enabled=False)
        p=self.store.auto_plan(p['id'],p['revision'])
        self.project=self.store.set_brand(p['id'],p['revision'],'vang-nguyen','personal-30',duration_mode=FIT_NARRATION_POLICY)
    def tearDown(self):self.temp.cleanup()
    def test_creation_is_strict_and_versioned_without_mutating_legacy_or_dispatching(self):
        self.assertEqual(self.project['document']['narrated_workflow'],reference());self.assertTrue(required(self.project['document']))
        self.assertTrue(self.store.shot_view(self.project['id'])['shot_timeline']['persisted'])
        self.assertEqual(self.store.get(self.legacy['id']),self.unchanged);self.assertEqual(self.project['jobs'],[]);self.assertIsNone(self.project['approval'])
        for options in [{'narrated_workflow':'true','production_quality':True},{'narrated_workflow':True},{'production_quality':1}]:
            before=len(self.store.list())
            with self.assertRaises(WorkflowError):self.store.create('Invalid fixture','No provider',**options)
            self.assertEqual(len(self.store.list()),before)
        bad=copy.deepcopy(self.project['document']);bad['narrated_workflow']['sha256']='0'*64
        with self.assertRaisesRegex(WorkflowError,'POLICY_CHANGED'):required(bad)
    def test_first_content_result_saves_one_canonical_snapshot_without_an_arbitrary_edit_or_read_mutation(self):
        p=self.store.create('Guided authored result fixture','No provider',production_quality=True,narrated_workflow=True)
        self.store.enqueue(p['id'],p['revision'],'content',uuid.uuid4().hex);job=self.store.claim()
        self.store.finish(job,result={'proposal':self.legacy['document']['proposal']});current=self.store.get(p['id'])
        self.assertEqual(current['document']['canonical_timeline']['version'],1);self.assertIsNone(current['approval'])
        before=copy.deepcopy(current);view=self.store.shot_view(p['id']);self.assertTrue(view['shot_timeline']['persisted']);self.assertEqual(self.store.get(p['id']),before)
    def test_production_approval_and_frozen_worker_guard_require_measured_narration(self):
        p=self.project
        with self.assertRaisesRegex(WorkflowError,'MEASURED_TIMING'):self.store.approve(p['id'],p['revision'],'EXPLICIT HUMAN FIXTURE',True)
        approved=self.store.approve(p['id'],p['revision'],'EXPLICIT NARRATION ONLY FIXTURE',True,purpose='narration')
        with self.assertRaisesRegex(WorkflowError,'AUDIBLE_PREVIEW_APPROVAL'):self.store.enqueue(p['id'],p['revision'],'render',uuid.uuid4().hex)
        fabricated=copy.deepcopy(approved['approval']);fabricated.pop('approval_scope')
        job={'id':uuid.uuid4().hex,'project_id':p['id'],'revision':p['revision'],'kind':'render','snapshot':{'document':p['document'],'approval':fabricated}}
        with patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('Must reject before inference')):
            with self.assertRaisesRegex(WorkflowError,'MEASURED_TIMING'):Pipeline(self.config).run(job,lambda _:None)
        self.assertEqual(self.store.get(p['id'])['jobs'],[])
    def test_actual_preparation_apply_preview_approval_sequence_uses_same_canonical_timeline(self):
        p=self.store.approve(self.project['id'],self.project['revision'],'EXPLICIT PREPARATION FIXTURE',True,purpose='narration')
        self.store.enqueue(p['id'],p['revision'],'narration',uuid.uuid4().hex);job=self.store.claim();out=self.root/'jobs'/job['id'];out.parent.mkdir(exist_ok=True)
        media.voice(out);write_json(out/'tts-plan.json',{'explicit_synthetic_pcm_fixture':True});Artifacts(out,job).commit('tts',[out/'voice.wav',out/'voice.json',out/'tts-plan.json'])
        with patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('No inference')):result=Pipeline(self.config).run(job,lambda _:None)
        self.store.finish(job,result=result);updated=apply(self.store,p['id'],job['id'],{'revision':p['revision'],'expected_plan_sha256':result['plan_sha256'],'acknowledged':True})
        self.assertIsNone(updated['approval']);self.assertEqual(updated['document']['canonical_timeline']['version'],p['document']['canonical_timeline']['version']+1)
        with self.assertRaisesRegex(WorkflowError,'CURRENT_AUDIBLE_PREVIEW'):self.store.approve(p['id'],updated['revision'],'EXPLICIT TOO EARLY FIXTURE',True)
        narration_fixture.NarrationTests.audible(self,updated)
        approved=self.store.approve(p['id'],updated['revision'],'EXPLICIT AFTER-PREVIEW FIXTURE',True);queued=self.store.enqueue(p['id'],updated['revision'],'render',uuid.uuid4().hex)
        self.assertEqual(queued['snapshot']['approval']['render_mode'],'prepared_narration');self.assertEqual(approved['document']['canonical_timeline'],updated['document']['canonical_timeline'])
        self.assertEqual(self.store.get(self.legacy['id']),self.unchanged)
    def test_duplicate_retains_guided_policy_but_has_no_narration_or_production_authority(self):
        p=self.store.duplicate(self.project['id'],self.project['revision']);self.assertTrue(required(p['document']));self.assertIsNone(p['approval']);self.assertEqual(p['jobs'],[])
        with self.assertRaisesRegex(WorkflowError,'MEASURED_TIMING'):self.store.approve(p['id'],p['revision'],'EXPLICIT DUPLICATE FIXTURE',True)

class GuidedIdeaTests(unittest.TestCase):
    setUp=intelligence.IntelligenceWorkflowTests.setUp;tearDown=intelligence.IntelligenceWorkflowTests.tearDown
    candidates=intelligence.IntelligenceWorkflowTests.candidates;selected=intelligence.IntelligenceWorkflowTests.selected
    def test_approved_idea_creation_preferences_are_frozen_and_retry_cannot_change_policy(self):
        b=self.selected();brief=self.service.approve_brief(b['brief']['id'],b['brief']['version'],'EXPLICIT IDEA FIXTURE',True)
        p=self.service.send(brief['id'],brief['version'],production_quality=True,narrated_workflow=True)
        self.assertTrue(required(p['document']));self.assertIsNone(p['approval']);self.assertEqual(p['jobs'],[])
        self.assertEqual(self.service.send(brief['id'],brief['version'],production_quality=True,narrated_workflow=True),p)
        with self.assertRaisesRegex(WorkflowError,'CREATION_POLICY_CONFLICT'):self.service.send(brief['id'],brief['version'])
        self.assertEqual(self.production.get(p['id']),p)
    def test_invalid_idea_creation_policy_leaves_approved_brief_and_projects_unchanged(self):
        b=self.selected();brief=self.service.approve_brief(b['brief']['id'],b['brief']['version'],'EXPLICIT IDEA FIXTURE',True)
        before=self.service.bundle(b['run']['id']);projects=self.production.list()
        with self.assertRaises(WorkflowError):self.service.send(brief['id'],brief['version'],narrated_workflow=True)
        self.assertEqual(self.service.bundle(b['run']['id']),before);self.assertEqual(self.production.list(),projects)

class GuidedCreationHTTPTests(unittest.TestCase):
    setUp=http.NativeAccessHTTPTests.setUp;tearDown=http.NativeAccessHTTPTests.tearDown
    start_server=http.NativeAccessHTTPTests.start_server;stop_server=http.NativeAccessHTTPTests.stop_server
    request=http.NativeAccessHTTPTests.request;account=http.NativeAccessHTTPTests.account
    def test_editor_creates_guided_project_without_jobs_or_approval_and_bad_preferences_create_nothing(self):
        self.account('editor');status,p,_=self.request('POST','/api/projects',{'name':'EXPLICIT GUIDED HTTP FIXTURE','prompt':'No provider','production_quality':True,'narrated_workflow':True})
        self.assertEqual(status,201,p);self.assertTrue(required(p['document']));self.assertEqual(p['jobs'],[]);self.assertIsNone(p['approval'])
        before=len(self.server.store.list());status,_,_=self.request('POST','/api/projects',{'name':'Invalid fixture','prompt':'No provider','narrated_workflow':True})
        self.assertEqual(status,400);self.assertEqual(len(self.server.store.list()),before);self.assertEqual(self.pipeline.calls,0)
