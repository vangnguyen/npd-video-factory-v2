"""Actual FFmpeg/SQLite paths; speech-provider payloads are explicit fixtures."""
import copy,json,uuid,unittest
from unittest.mock import patch
from services.windows_native import asr
from services.windows_native.asr_request import bind,from_job,from_snapshot
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.pipeline import Pipeline
from services.windows_native.server import Runner
from services.windows_native.store import Store
from services.windows_native.tests import test_asr as fixture
from services.windows_native import auto_edit_analysis


class LanguageTransport(fixture.FixtureTransport):
    requests=[]
    wrong_language=False
    async def request(self,method,path,credential,timeout,**kwargs):
        if path=='/v2/transcript':self.requests.append(copy.deepcopy(kwargs['json']))
        result=await super().request(method,path,credential,timeout,**kwargs)
        if method=='GET':
            language='en' if self.profile.language=='auto' else self.profile.language
            result['language_code']='fr' if self.wrong_language else language
            if language=='en':
                result['text']='Hello world.';result['words'][0]['text']='Hello';result['words'][1]['text']='world.'
            result['language_confidence']=None
        return result


class NativeAsrLanguageTests(unittest.TestCase):
    tearDown=fixture.AsrTests.tearDown
    def setUp(self):
        fixture.AsrTests.setUp(self);original=self.analyze_original
        self.analyze_original=lambda c,j,o,s,**kw:original(c,j,o,s,transport_factory=LanguageTransport)
        LanguageTransport.requests=[];LanguageTransport.wrong_language=False
    def enqueue(self,language,key=None):
        return self.store.enqueue(self.project['id'],self.project['revision'],'asr',key or uuid.uuid4().hex,asr_request={'language':language})
    def test_vi_en_auto_worker_normalization_source_and_restart_with_no_reference_prompt(self):
        for language in ('vi','en','auto'):
            if language!='vi':
                self.project=self.store.create('Language fixture '+language,'','media')
                self.project=self.store.append_media(self.project['id'],1,self.asset)
            job=self.enqueue(language);Runner(self.store,Pipeline(self.config)).run_one();saved=self.store.get_job(job['id'])
            self.assertEqual(saved['status'],'succeeded',saved.get('error'));project=Store(self.root).get(self.project['id'])
            transcript=project['document']['media_analysis'][0]['transcript'];expected='en' if language=='auto' else language
            self.assertEqual(transcript['language'],expected);self.assertEqual(transcript['provenance']['requested_language'],language)
            self.assertEqual(transcript['provenance']['language_detection_requested'],language=='auto')
            self.assertIsNone(transcript['provenance']['language_detection_performed'])
            self.assertIsNone(transcript['provenance']['language_confidence']);self.assertIsNone(transcript['provenance']['estimated_cost_vnd'])
            normalized=auto_edit_analysis.normalize_transcript(transcript,analysis_id='ana_'+'1'*24,
                asset_id='ast_'+'2'*32,duration=1.,created_at='2026-10-12T00:00:00+00:00')
            self.assertEqual(normalized.language,expected);self.assertEqual(normalized.segments[0].words[1].start_seconds,.21)
            self.assertIsNone(project['approval']);self.assertEqual(file_sha(self.source),self.original_sha)
            request=LanguageTransport.requests[-1];self.assertNotIn('prompt',request);self.assertNotIn('keyterms_prompt',request)
            self.assertNotIn(fixture.KEY,json.dumps(saved))
            if language=='en':
                raw=copy.deepcopy(project['document']['media_analysis'])
                self.store.enqueue(project['id'],project['revision'],'auto_edit_analysis',uuid.uuid4().hex)
                Runner(self.store,Pipeline(self.config)).run_one();bundle=auto_edit_analysis.view(self.store,project['id'])
                current=bundle['analyses'][0]['analysis']['transcript'];self.assertEqual(current['language'],'en')
                changed=auto_edit_analysis.edit_transcript(self.store,project['id'],bundle['revision'],current['analysis_id'],
                    {'expected_version':current['version'],'segments':[{'segment_id':current['segments'][0]['segment_id'],'text':'Hello updated.'}]})
                edited=changed['analyses'][0]['analysis']['transcript'];self.assertEqual(edited['version'],2)
                self.assertEqual(edited['language'],'en');self.assertEqual(edited['segments'][0]['words'],[])
                self.assertIsNone(edited['segments'][0]['confidence']);self.assertEqual(self.store.get(project['id'])['document']['media_analysis'],raw)
    def test_idempotency_language_binding_and_invalid_requests_are_atomic(self):
        before=copy.deepcopy(self.project);key=uuid.uuid4().hex;job=self.enqueue('en',key)
        self.assertEqual(self.enqueue('en',key),job)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_KEY_CONFLICT'):self.enqueue('vi',key)
        with self.assertRaisesRegex(WorkflowError,'REQUEST_INVALID'):self.enqueue('fr')
        with self.assertRaisesRegex(WorkflowError,'KIND_INVALID'):self.store.enqueue(self.project['id'],self.project['revision'],'content',uuid.uuid4().hex,asr_request={'language':'en'})
        snapshot=copy.deepcopy(job['snapshot']);snapshot['asr_request']['profile']['language']='vi'
        with self.assertRaisesRegex(WorkflowError,'BINDING_CHANGED'):from_snapshot(snapshot)
        altered=copy.deepcopy(job);altered['snapshot']['asr_request']=bind({'language':'vi'})
        with self.assertRaisesRegex(WorkflowError,'JOB_BINDING_CHANGED'):from_job(altered)
        self.assertEqual(self.store.get(self.project['id'])['document'],before['document'])
    def test_known_english_job_resume_does_not_repeat_upload_or_paid_creation(self):
        fixture.FixtureTransport.fail_observe_once=True;job=self.enqueue('en');Runner(self.store,Pipeline(self.config)).run_one()
        self.assertEqual(self.store.get_job(job['id'])['status'],'failed')
        self.store.resume(job['id']);Runner(self.store,Pipeline(self.config)).run_one()
        self.assertEqual(self.store.get_job(job['id'])['status'],'succeeded')
        self.assertEqual(fixture.FixtureTransport.calls.count(('POST','/v2/upload')),1)
        self.assertEqual(fixture.FixtureTransport.calls.count(('POST','/v2/transcript')),1)
        self.assertEqual(self.store.get(self.project['id'])['document']['media_analysis'][0]['transcript']['language'],'en')
    def test_unexpected_detected_language_saves_no_transcript_and_refuses_new_paid_job(self):
        LanguageTransport.wrong_language=True;job=self.enqueue('auto');Runner(self.store,Pipeline(self.config)).run_one()
        self.assertEqual(self.store.get_job(job['id'])['status'],'failed')
        self.assertNotIn('media_analysis',self.store.get(self.project['id'])['document'])
        with self.assertRaisesRegex(WorkflowError,'EXISTING_JOB_RESUME_REQUIRED'):self.enqueue('en')
