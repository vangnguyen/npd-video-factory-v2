"""CPU adapter guards and Native integration with explicit inference fixtures."""
import copy,json,math,tempfile,unittest,uuid
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
from app.local_asr_profile import profile,digest
from app.local_transcription_provider import normalize,LocalCpuTranscriptionProvider
from app.local_asr_runtime import status,plain
from app.auto_edit_providers import require_positive_duration_transcript,PositiveDurationTranscriptRequired,ProviderNotConfigured
from app.auto_edit_models import MediaMetadata
from services.windows_native.asr_request import bind,from_job
from services.windows_native import asr,local_asr,auto_edit_analysis
from services.windows_native.tests import test_asr as fixtures
from services.windows_native.tests import test_asr_language_http as http_fixture
from services.windows_native.pipeline import Pipeline
from services.windows_native.server import Runner,Handler

def result(selected,checksum,duration=1.):
    return {'version':'local-asr-result.v1','profile_sha256':digest(selected),'source_sha256':checksum,
        'language':'en' if selected['language']=='auto' else selected['language'],
        'language_confidence':.82 if selected['language']=='auto' else None,'language_probability_reported':.82,
        'duration_seconds':duration,'model_revision':selected['model_revision'],'library_version':'1.2.1',
        'device':'cpu','compute_type':'int8','external_calls':0,'paid_calls':0,'model_inferences':1,'vad_filter':False,
        'segments':[{'start_seconds':.05,'end_seconds':.65,'text':'Xin chào.','speaker':None,'confidence':None,
            'words':[{'start_seconds':.05,'end_seconds':.3,'text':'Xin','confidence':.8,'timing_semantics':'positive_interval'},
                {'start_seconds':.3,'end_seconds':.65,'text':'chào.','confidence':.3,'timing_semantics':'positive_interval'}]}]}

class LocalAsrContractTests(unittest.TestCase):
    def test_language_provider_binding_preserves_legacy_and_refuses_tamper(self):
        old=bind({'language':'en'})
        self.assertEqual(old,bind({'language':'en','provider':'assemblyai'}))
        self.assertEqual(old['request'],{'language':'en'})
        for language in ('vi','en','auto'):
            current=bind({'language':language,'provider':'local-whisper'})
            self.assertEqual(current['profile'],profile(language));self.assertNotEqual(current['profile'],old['profile'])
        with self.assertRaisesRegex(Exception,'REQUEST_INVALID'):bind({'language':'vi','provider':'unknown'})
    def test_words_are_model_estimates_with_original_intervals_and_no_invented_confidence(self):
        selected=profile('vi');raw=result(selected,'a'*64);before=copy.deepcopy(raw)
        value=normalize(raw,selected,'a'*64,1.)
        self.assertEqual(raw,before);self.assertIsNone(value.confidence);self.assertIsNone(value.actual_cost_vnd)
        self.assertIsNone(value.provenance['language_confidence']);self.assertTrue(value.provenance['recognition_review_required'])
        self.assertEqual(value.provenance['low_confidence_word_count'],1)
        self.assertEqual(value.segments[0].words[1].start_seconds,.3)
    def test_zero_duration_word_is_preserved_as_boundary_and_not_made_safe_for_edits(self):
        selected=profile('vi');raw=result(selected,'a'*64)
        raw['segments'][0]['words'][1].update(end_seconds=.3,timing_semantics='provider_boundary_point')
        value=normalize(raw,selected,'a'*64,1.)
        self.assertEqual(value.segments[0].words[1].end_seconds,.3)
        with self.assertRaises(PositiveDurationTranscriptRequired):require_positive_duration_transcript(value)
    def test_bound_input_language_duration_and_nonfinite_words_are_rejected(self):
        selected=profile('vi')
        for field,changed in [('source_sha256','b'*64),('profile_sha256','c'*64),('language','en'),
            ('duration_seconds',2.),('external_calls',1),('language_confidence',1.)]:
            raw=result(selected,'a'*64);raw[field]=changed
            with self.assertRaises(ValueError):normalize(raw,selected,'a'*64,1.)
        for field in ('start_seconds','end_seconds','confidence'):
            raw=result(selected,'a'*64);raw['segments'][0]['words'][0][field]=math.nan
            with self.assertRaises(ValueError):normalize(raw,selected,'a'*64,1.)
    def test_missing_runtime_is_disabled_without_a_remote_fallback_or_model_download(self):
        self.assertFalse(status(None)['configured']);self.assertFalse(status(Path('missing.json'))['configured'])
        with self.assertRaises(ValueError):plain('https://untrusted.invalid/model')
        import asyncio
        with self.assertRaises(ProviderNotConfigured):asyncio.run(LocalCpuTranscriptionProvider(None).transcribe(
            Path('unused.wav'),metadata=MediaMetadata(media_kind='audio',detected_content_type='audio/wav',duration_seconds=1.),checksum_sha256='a'*64))
    def test_local_failure_guidance_does_not_instruct_remote_job_observation(self):
        from services.windows_native.hardening import failure
        message=failure('LOCAL_ASR_NOT_CONFIGURED')
        self.assertEqual(message['category'],'ASR_ERROR');self.assertIn('trên máy',message['action'])
        self.assertNotIn('quan sát job',message['action'])
    def test_same_size_model_tamper_and_extra_runtime_fields_are_rejected_at_dispatch(self):
        from app.local_asr_runtime import runtime,file_sha
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);binary=root/'python.exe';binary.write_bytes(b'explicit runtime fixture')
            model=root/'model';model.mkdir();weights=model/'model.bin';weights.write_bytes(b'original')
            expected={'files':{'model.bin':{'sha256':file_sha(weights),'bytes':8}}}
            value={'version':'local-asr-runtime.v1','enabled':True,'python':str(binary),
                'python_sha256':file_sha(binary),'model_root':str(model),'model_manifest_sha256':digest(expected),
                'cpu_threads':2,'timeout_seconds':30}
            manifest=root/'runtime.json';manifest.write_text(json.dumps(value),encoding='utf-8')
            with patch('app.local_asr_runtime.model_manifest',return_value=expected):
                self.assertEqual(runtime(manifest),value)
                weights.write_bytes(b'tampered')
                with self.assertRaisesRegex(ValueError,'MODEL_CHANGED'):runtime(manifest)
                weights.write_bytes(b'original');value['client_graph']={'forbidden':True}
                manifest.write_text(json.dumps(value),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'RUNTIME_INVALID'):runtime(manifest)

class FakeLocalProvider:
    calls=0
    def __init__(self,manifest,language):self.profile=profile(language);self.raw_result=None
    async def transcribe(self,path,*,metadata,checksum_sha256):
        type(self).calls+=1
        self.raw_result=result(self.profile,checksum_sha256,metadata.duration_seconds)
        return normalize(self.raw_result,self.profile,checksum_sha256,metadata.duration_seconds)

class NativeLocalAsrTests(unittest.TestCase):
    def setUp(self):
        fixtures.AsrTests.setUp(self);FakeLocalProvider.calls=0
        original=local_asr.analyze_local
        self.local_patch=patch.object(local_asr,'analyze_local',side_effect=lambda c,j,o,s,p:original(c,j,o,s,p,provider_factory=FakeLocalProvider))
        self.local_patch.start()
    def tearDown(self):self.local_patch.stop();fixtures.AsrTests.tearDown(self)
    def test_cpu_worker_uses_canonical_source_analysis_cost_and_offline_checkpoint_replay(self):
        job=self.store.enqueue(self.project['id'],self.project['revision'],'asr',uuid.uuid4().hex,
            asr_request={'language':'vi','provider':'local-whisper'})
        with (patch.object(asr.connection,'status',side_effect=AssertionError('REMOTE STATUS FORBIDDEN')),
             patch.object(asr.connection,'load_credential',side_effect=AssertionError('CREDENTIAL FORBIDDEN'))):
            Runner(self.store,Pipeline(self.config)).run_one()
            saved=self.store.get_job(job['id']);self.assertEqual(saved['status'],'succeeded',saved.get('error'))
            transcript=self.store.get(self.project['id'])['document']['media_analysis'][0]['transcript']
            self.assertEqual(transcript['provenance']['provider'],'faster-whisper')
            self.assertFalse(transcript['provenance']['external_call']);self.assertEqual(fixtures.FixtureTransport.calls,[])
            out=self.root/'jobs'/job['id']
            replay=asr.analyze(self.config,job,out,lambda _:None)
            self.assertEqual(replay['provider_calls'],0);self.assertEqual(FakeLocalProvider.calls,1)
        from services.windows_native.costs import CostLedger
        records=CostLedger(self.store).summary(self.project['id'])['records']
        self.assertEqual(len(records),1);self.assertFalse(records[0]['external_call']);self.assertFalse(records[0]['paid'])
        self.assertIsNone(records[0]['actual_cost'])
        from services.windows_native.media import media_path
        self.assertEqual(fixtures.file_sha(media_path(self.config,self.asset['id'])),self.asset['sha256'])
        self.assertIsNone(self.store.get(self.project['id'])['approval'])
    def test_local_job_profile_tamper_cannot_be_rebound_to_another_language(self):
        job=self.store.enqueue(self.project['id'],self.project['revision'],'asr',uuid.uuid4().hex,
            asr_request={'language':'vi','provider':'local-whisper'})
        altered=copy.deepcopy(job);altered['snapshot']['asr_request']['profile']['language']='en'
        with self.assertRaisesRegex(Exception,'BINDING_CHANGED'):from_job(altered)

class NativeLocalAsrHTTPTests(unittest.TestCase):
    def setUp(self):http_fixture.NativeAsrLanguageHTTPTests.setUp(self)
    def tearDown(self):http_fixture.NativeAsrLanguageHTTPTests.tearDown(self)
    request=http_fixture.NativeAsrLanguageHTTPTests.request
    body=http_fixture.NativeAsrLanguageHTTPTests.body
    def test_not_configured_local_asr_is_rejected_before_enqueuing_without_remote_use(self):
        body=self.body();body['asr_request']['provider']='local-whisper'
        before=self.store.get(self.project['id'])
        with (patch('services.windows_native.server.local_asr_status',return_value={'configured':False}),
             patch.object(asr.connection,'status',side_effect=AssertionError('NO REMOTE FALLBACK'))):
            self.assertEqual(self.request(body)[0],503)
        self.assertEqual(self.store.get(self.project['id']),before)
    def test_signed_editor_cpu_selection_is_frozen_and_replayable_with_auth_before_body(self):
        body=self.body();body['asr_request']['provider']='local-whisper'
        with (patch('services.windows_native.server.local_asr_status',return_value={'configured':True}),
             patch.object(asr.connection,'status',side_effect=AssertionError('NO REMOTE FALLBACK'))):
            with patch.object(Handler,'read_body',side_effect=AssertionError('AUTH BEFORE BODY')):
                self.assertEqual(self.request(body,Cookie='')[0],401)
            self.assertEqual(self.request(body,**{'X-VF-CSRF':'wrong'})[0],403)
            code,job=self.request(body);self.assertEqual(code,200,job)
            self.assertEqual(job['snapshot']['asr_request']['profile'],profile('en'))
            self.assertEqual(self.request(body)[1]['id'],job['id'])
