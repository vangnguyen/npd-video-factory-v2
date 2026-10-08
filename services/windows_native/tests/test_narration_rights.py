"""Owned PCM/provider-wire fixtures; never speech, real provider or legal clearance."""
import copy,json,tempfile,unittest,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from services.windows_native.tests import test_narration as narration_fixture
from services.windows_native.tests.test_shot_production import voice
from services.windows_native.branding import FIT_NARRATION_POLICY
from services.windows_native.contracts import WorkflowError,PROFILE_SHA,digest,file_sha,write_json
from services.windows_native.hardening import Artifacts
from services.windows_native.narration import apply,prepare
from services.windows_native.narration_rights import NativeNarrationRights,validate_document,KEY
from services.windows_native.narration_rights_models import ReviewCreate
from services.windows_native.pipeline import Pipeline
from services.windows_native.store import Store

class NarrationRightsTests(unittest.TestCase):
    setUp=narration_fixture.NarrationTests.setUp
    tearDown=narration_fixture.NarrationTests.tearDown
    audible=narration_fixture.NarrationTests.audible
    def ready(self,*,fixture=False):
        self.project=self.store.approve(self.project['id'],self.project['revision'],'EXPLICIT UNIT WIRE FIXTURE',True)
        job=self.store.enqueue(self.project['id'],self.project['revision'],'narration',uuid.uuid4().hex);job=self.store.claim()
        out=self.root/'jobs'/job['id'];out.parent.mkdir(exist_ok=True);meta,_=voice(out)
        # This simulates the already approved provider wire contract. The actual
        # unit input is a tone; no provider/model/speech acceptance is claimed.
        write_json(out/'tts-plan.json',{'profile_sha256':PROFILE_SHA,'units':meta['units'],**({'explicit_synthetic_pcm_fixture':True} if fixture else {})})
        artifacts=Artifacts(out,job);artifacts.commit('tts',[out/'voice.wav',out/'voice.json',out/'tts-plan.json'])
        result=prepare(self.config,job,out,artifacts);self.store.finish(job,result=result)
        self.project=apply(self.store,self.project['id'],job['id'],{'revision':self.project['revision'],'expected_plan_sha256':result['plan_sha256'],'acknowledged':True})
        self.clock=[datetime.now(timezone.utc)];self.service=NativeNarrationRights(self.store,enabled=True,clock=lambda:self.clock[0]);self.source=job;self.out=out
        return self.service.page(self.project['id'])
    def body(self,**changes):
        page=self.service.page(self.project['id'])
        return {'revision':page['revision'],'narration_job_id':page['provenance']['narration_job_id'],'expected_provenance_sha256':page['provenance_sha256'],
            'action':'grant','reason':'EXPLICIT UNIT RIGHTS EXCEPTION; NO LEGAL OR OWNER ACCEPTANCE','evidence_reference':'document://explicit-unit-exception',
            'valid_days':7,'allow_publishing_review':True,'acknowledged':True,'request_key':uuid.uuid4().hex,**changes}
    def grant(self,**changes):return self.service.record(self.project['id'],self.body(**changes),actor='explicit-unit-owner-fixture')
    def rendered(self):
        p=self.store.get(self.project['id']);self.audible(p);p=self.store.approve(p['id'],p['revision'],'EXPLICIT UNIT FINAL',True)
        job=self.store.enqueue(p['id'],p['revision'],'render',uuid.uuid4().hex);job=self.store.claim()
        with patch('services.windows_native.pipeline.verify_runtime'),patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('No new inference')):
            result=Pipeline(self.config).run(job,lambda _:None)
        self.store.finish(job,result=result);return self.store.get_job(job['id'])
    def test_default_disabled_read_null_no_mutation_and_browser_cannot_enable(self):
        self.ready();before=self.store.get(self.project['id']);self.service.enabled=False
        page=self.service.page(self.project['id']);self.assertFalse(page['enabled']);self.assertFalse(page['publishing_enabled']);self.assertEqual(page['history'],[])
        self.assertEqual(page['provenance']['rights_status'],'unknown');self.assertFalse(page['provenance']['speech_quality_accepted'])
        self.assertNotIn('path',json.dumps(page['provenance']['model_artifacts']));self.assertEqual(self.store.get(self.project['id']),before)
        with self.assertRaisesRegex(WorkflowError,'DISABLED'):self.grant()
        with self.assertRaisesRegex(WorkflowError,'REQUEST_INVALID'):self.grant(enabled=True)
    def test_exact_grant_clears_approval_without_changing_canonical_or_audio_and_replays_after_restart(self):
        self.ready();before=self.store.get(self.project['id']);audio=file_sha(self.out/'voice.wav');body=self.body();value=self.service.record(self.project['id'],body,actor='fixture-owner')
        after=self.store.get(self.project['id']);self.assertIsNone(after['approval']);self.assertEqual(after['revision'],before['revision']+1)
        self.assertEqual(after['document']['canonical_timeline'],before['document']['canonical_timeline']);self.assertEqual(file_sha(self.out/'voice.wav'),audio)
        self.assertEqual(len(after['jobs']),len(before['jobs']));self.assertFalse(value['record']['rights_independently_verified']);self.assertFalse(value['record']['publishing_authorized'])
        restarted=NativeNarrationRights(Store(self.root),enabled=True,clock=lambda:self.clock[0]);again=restarted.record(after['id'],body,actor='different-fixture')
        self.assertTrue(again['idempotent_replay']);self.assertEqual(again['record'],value['record']);self.assertEqual(len(restarted.page(after['id'])['history']),1)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):restarted.record(after['id'],{**body,'reason':'Different fixture decision'},actor='fixture')
    def test_no_publishing_flag_expiry_future_clock_and_disabled_config_leave_gate_closed(self):
        self.ready();value=self.grant(allow_publishing_review=False);p=self.store.get(self.project['id']);v=value['record']['provenance']
        self.assertIsNone(self.service.active(p['document'],p['id'],v,publishing=True));self.assertIsNotNone(self.service.active(p['document'],p['id'],v))
        self.clock[0]-=timedelta(days=1);self.assertIsNone(self.service.active(p['document'],p['id'],v));self.clock[0]+=timedelta(days=9)
        self.assertIsNone(self.service.active(p['document'],p['id'],v));self.service.enabled=False;self.assertIsNone(self.service.active(p['document'],p['id'],v))
    def test_strict_scope_digest_acknowledgement_secret_reference_and_fixture_reject_without_writes(self):
        self.ready();before=self.store.get(self.project['id'])
        for change in [{'expected_provenance_sha256':'0'*64},{'narration_job_id':'0'*32},{'acknowledged':1},{'valid_days':True},{'evidence_reference':'https://example.test/?api_key=private'},
            {'evidence_reference':'https://user:private@example.test/'},{'evidence_reference':'fixture://fake'},{'model_license':'client-injected'},{'revision':before['revision']-1}]:
            with self.assertRaises(WorkflowError):self.grant(**change)
            self.assertEqual(self.store.get(self.project['id']),before)
        other=self.store.create('foreign','Explicit foreign scope fixture')
        with self.assertRaisesRegex(WorkflowError,'PREPARATION_REQUIRED'):self.service.record(other['id'],{**self.body(),'revision':1},actor='fixture')
    def test_explicit_synthetic_marker_never_qualifies_as_generated_voice_rights(self):
        self.ready(fixture=True);self.assertTrue(self.service.page(self.project['id'])['provenance']['explicit_fixture'])
        with self.assertRaisesRegex(WorkflowError,'FIXTURE_INELIGIBLE'):self.grant()
    def test_changed_inputs_and_retained_history_fail_closed(self):
        self.ready();value=self.grant();p=self.store.shot_view(self.project['id']);shot=p['shot_timeline']['shots'][0]
        p=self.store.mutate_shots(p['id'],p['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'narration':'Changed spoken unit'}})
        self.assertIsNone(self.service.page(p['id'])['provenance']);self.assertEqual(self.service.page(p['id'])['attention'],'NATIVE_NARRATION_RIGHTS_INPUT_CHANGED')
        altered=copy.deepcopy(p['document']);altered[KEY][0]['provenance']['voice_audio_sha256']='0'*64
        with self.assertRaisesRegex(WorkflowError,'HISTORY_INVALID'):validate_document(altered)
    def test_changed_profile_and_original_pcm_reject_provenance_read(self):
        self.ready();body=self.body()
        with patch('services.windows_native.pipeline.profile',side_effect=WorkflowError('LOCKED_VOICE_PROFILE_CHANGED')):
            page=self.service.page(self.project['id']);self.assertIsNone(page['provenance']);self.assertEqual(page['attention'],'LOCKED_VOICE_PROFILE_CHANGED')
            with self.assertRaisesRegex(WorkflowError,'LOCKED_VOICE_PROFILE_CHANGED'):self.service.record(self.project['id'],body,actor='fixture-owner')
        self.out.joinpath('voice.wav').write_bytes(b'EXPLICIT CORRUPTION')
        page=self.service.page(self.project['id']);self.assertIsNone(page['provenance']);self.assertEqual(page['attention'],'CHECKPOINT_ARTIFACT_CHANGED')
        with self.store.transaction() as con:
            with self.assertRaisesRegex(WorkflowError,'CHECKPOINT_ARTIFACT_CHANGED'):self.service.provenance(self.project['document'],self.project['id'],con)
    def test_revoke_disabled_or_stale_preparation_still_preserves_exact_prior_and_invalidates_review(self):
        self.ready();value=self.grant();self.service.enabled=False;r=value['record'];self.out.joinpath('voice.wav').write_bytes(b'EXPLICIT CORRUPTION')
        # Revocation must remain possible even when an old source is gone/changed.
        body={'revision':value['revision'],'narration_job_id':r['narration_job_id'],'expected_provenance_sha256':r['provenance_sha256'],'action':'revoke',
            'reason':'EXPLICIT UNIT REVOKE; NO LEGAL ACCEPTANCE','evidence_reference':'document://unit-revoke','valid_days':7,'allow_publishing_review':False,
            'acknowledged':True,'exception_id':r['exception_id'],'expected_exception_sha256':r['sha256'],'request_key':uuid.uuid4().hex}
        result=self.service.record(self.project['id'],body,actor='fixture-owner');self.assertIsNone(result['record']['expires_at']);self.assertEqual(result['record']['provenance'],r['provenance'])
        p=self.store.get(self.project['id']);self.assertIsNone(self.service.active(p['document'],p['id'],r['provenance'],publishing=True))
        with self.assertRaisesRegex(WorkflowError,'REVOCATION_INVALID'):self.service.record(p['id'],{**body,'revision':p['revision'],'request_key':uuid.uuid4().hex},actor='fixture')
    def test_duplicate_drops_preparation_and_exception_authority(self):
        self.ready();self.grant();p=self.store.get(self.project['id']);copy_project=self.store.duplicate(p['id'],p['revision'])
        self.assertNotIn(KEY,copy_project['document']);self.assertNotIn('prepared_narration',copy_project['document']);self.assertTrue(copy_project['document']['narration_rights_origin']['new_review_required'])
        self.assertEqual(self.service.page(copy_project['id'])['history'],[])
    def test_actual_pcm_render_reuse_gate_requires_exact_exception_and_all_artifacts(self):
        self.ready();self.assertIsNone(self.service.active(self.project['document'],self.project['id'],self.service.page(self.project['id'])['provenance'],publishing=True))
        self.grant();job=self.rendered();result=self.service.publication(job)
        self.assertEqual(result['status'],'explicit_owner_exception');self.assertFalse(result['speech_quality_accepted']);self.assertFalse(result['publishing_authorized'])
        target=self.root/'jobs'/job['id'];target.joinpath('voice-reuse.json').write_text('{}',encoding='utf-8')
        with self.assertRaisesRegex(WorkflowError,'CHECKPOINT_ARTIFACT_CHANGED'):self.service.publication(job)
