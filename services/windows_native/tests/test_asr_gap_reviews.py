"""Human timestamp review over real gapped media and explicit mock speech."""
import copy,unittest,uuid
from unittest.mock import patch
from services.windows_native.tests import test_asr as fixture
from services.windows_native.tests import test_source_audio_gaps as gap_fixture
from services.windows_native.tests.test_source_audio_gaps import GapTransport
from services.windows_native import asr,asr_gap_reviews as reviews,auto_edit_analysis
from services.windows_native.pipeline import Pipeline
from services.windows_native.server import Runner
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.media import media_path


class AsrGapReviewTests(unittest.TestCase):
    gapped=gap_fixture.SourceAudioGapTests.gapped
    run_asr=gap_fixture.SourceAudioGapTests.run_asr
    tearDown=fixture.AsrTests.tearDown
    def setUp(self):
        fixture.AsrTests.setUp(self);self.gapped();self.job=self.run_asr(cross_gap=True)
        self.assertEqual(self.job['error']['code'],'ASR_WORD_OVER_SOURCE_AUDIO_GAP_REVIEW_REQUIRED')
        self.workspace='wsp_gap_review_fixture';self.item=reviews.view(self.store,self.config,self.project['id'],self.workspace)['items'][0]
    def body(self):
        words=copy.deepcopy(self.item['current_words']);words[1]['start_seconds']=1.3
        return {'revision':self.project['revision'],'candidate_sha256':self.item['candidate_sha256'],'expected_version':0,'request_key':uuid.uuid4().hex,
                'acknowledged':True,'words':words,'note':'Explicit fixture human timestamp check'}
    def save(self,body):return reviews.save(self.store,self.config,self.project['id'],self.job['id'],self.asset['id'],body,actor_ref='fixture-editor')
    def test_read_and_save_preserve_original_source_project_job_and_versioned_idempotency(self):
        before=self.store.get(self.project['id']);source=media_path(self.config,self.asset['id']);sha=file_sha(source);body=self.body()
        self.assertEqual(self.item['original_words'][1]['start_seconds'],.6);self.assertTrue(self.item['original_words'][1]['crosses_missing_audio'])
        self.assertTrue(self.save(body));self.assertFalse(self.save(body));self.assertEqual(self.store.get(self.project['id']),before)
        current=reviews.view(self.store,self.config,self.project['id'],self.workspace)['items'][0]
        self.assertEqual(current['version'],1);self.assertEqual(current['current_words'][1]['start_seconds'],1.3)
        self.assertEqual(current['original_words'],self.item['original_words']);self.assertTrue(current['can_resume']);self.assertEqual(file_sha(source),sha)
        changed=copy.deepcopy(body);changed['words'][1]['text']='Khác'
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.save(changed)
        changed['request_key']=uuid.uuid4().hex
        with self.assertRaisesRegex(WorkflowError,'VERSION_CHANGED'):self.save(changed)
        self.assertEqual(len(GapTransport.calls),3)
    def test_keyless_same_job_resume_applies_human_times_without_provider_creation_and_auto_edit_uses_them(self):
        self.save(self.body());calls=copy.deepcopy(GapTransport.calls);self.store.resume(self.job['id'])
        with (patch.object(asr.connection,'status',side_effect=AssertionError('No credential status needed')),
              patch.object(asr.connection,'load_credential',side_effect=AssertionError('No credential read needed'))):
            Runner(self.store,Pipeline(self.config)).run_one()
        job=self.store.get_job(self.job['id']);self.assertEqual(job['status'],'succeeded',job.get('error'))
        project=self.store.get(self.project['id']);record=project['document']['media_analysis'][0]
        self.assertEqual(record['provider_pcm_transcript']['segments'][0]['words'][1]['start_seconds'],.6)
        self.assertEqual(record['transcript']['segments'][0]['words'][1]['start_seconds'],1.3)
        self.assertIsNone(record['transcript']['segments'][0]['words'][1]['confidence']);self.assertFalse(record['transcript']['provenance']['original_evidence'])
        self.assertEqual(record['transcript']['provenance']['source_clock_mapping']['input_transcript_kind'],'human_reviewed_pcm')
        self.assertEqual(asr.analysis_for_asset(project['document'],self.asset),record);self.assertEqual(GapTransport.calls,calls);self.assertIsNone(project['approval'])
        self.store.enqueue(project['id'],project['revision'],'auto_edit_analysis',uuid.uuid4().hex);Runner(self.store,Pipeline(self.config)).run_one()
        transcript=auto_edit_analysis.view(self.store,project['id'])['analyses'][0]['analysis']['transcript']
        self.assertFalse(transcript['is_original_evidence']);self.assertEqual(transcript['segments'][0]['words'][1]['start_seconds'],1.3)
    def test_invalid_intervals_empty_edits_and_acknowledgement_do_not_change_evidence(self):
        before=self.store.get(self.project['id']);bad=[]
        b=self.body();b['words'][1]['start_seconds']=.6;bad.append(b)
        b=self.body();b['words'][1]['start_seconds']=.15;bad.append(b)
        b=self.body();b['words'][0]['removed']=b['words'][1]['removed']=True;bad.append(b)
        b=self.body();b['words'].pop();bad.append(b)
        b=self.body();b['acknowledged']=False;bad.append(b)
        b=self.body();b['words'][0]['start_seconds']='0.1';bad.append(b)
        b=self.body();b['candidate_sha256']='f'*64;bad.append(b)
        for body in bad:
            with self.assertRaises(WorkflowError):self.save(body)
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(reviews.view(self.store,self.config,self.project['id'],self.workspace)['items'][0]['version'],0)
        self.assertEqual(len(GapTransport.calls),3)
    def test_candidate_tamper_blocks_review_and_resume_before_another_request(self):
        path=self.store.root/'jobs'/self.job['id']/'analysis'/self.asset['id']/'transcript-candidate.json';path.write_bytes(path.read_bytes()+b'corruption')
        with self.assertRaisesRegex(WorkflowError,'CHECKPOINT_ARTIFACT_CHANGED'):self.save(self.body())
        with self.assertRaisesRegex(WorkflowError,'CHECKPOINT_ARTIFACT_CHANGED'):self.store.resume(self.job['id'])
        self.assertEqual(len(GapTransport.calls),3)

    def test_explicit_word_removal_keeps_provider_original_and_only_changes_human_transcript(self):
        body=self.body();body['words'][1]['removed']=True;self.save(body);self.store.resume(self.job['id'])
        with patch.object(asr.connection,'status',side_effect=AssertionError('No provider status needed')):
            Runner(self.store,Pipeline(self.config)).run_one()
        self.assertEqual(self.store.get_job(self.job['id'])['status'],'succeeded')
        record=self.store.get(self.project['id'])['document']['media_analysis'][0]
        self.assertEqual(len(record['provider_pcm_transcript']['segments'][0]['words']),2)
        self.assertEqual(record['transcript']['segments'][0]['text'],'Trước');self.assertEqual(len(record['transcript']['segments'][0]['words']),1)
        self.assertIsNone(record['transcript']['segments'][0]['words'][0]['confidence']);self.assertEqual(len(GapTransport.calls),3)
