"""Real WAV upload/decoding, explicit ASR protocol fixtures, immutable normalized edits."""
import copy,json,subprocess,unittest,uuid
from unittest.mock import patch
from services.windows_native import asr,audio_transcripts
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.ingestion import provider_context,transcript_script
from services.windows_native.multipart_ingestion import NativeMultipartIngestion
from services.windows_native.tests import test_asr as fixture
from services.windows_native.store import Store

class AudioTranscriptTests(unittest.TestCase):
    parent_setup=fixture.AsrTests.setUp
    parent_teardown=fixture.AsrTests.tearDown
    run_job=fixture.AsrTests.run_job
    def setUp(self):
        fixture.AsrTests.setUp(self);self.owned_folder=self.root;self.root=self.owned_folder/'state'
        self.config=fixture.Config(data_root=self.root);self.store=Store(self.root)
        self.project=self.store.create('Actual owned WAV and mock recognition','','media')
        source=self.root/'owned-audio.wav';subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n',
            '-f','lavfi','-i','sine=frequency=440:duration=2','-c:a','pcm_s16le','-ar','16000','-ac','1',str(source)],check=True,capture_output=True,timeout=20)
        self.speech_source=source;self.service=NativeMultipartIngestion(self.store,self.config,workspace_id='wsp_audio_transcript_fixture')
        self.asset=self.upload(source.read_bytes(),'audio','audio/wav');self.project=self.store.get(self.project['id'])
    def tearDown(self):fixture.AsrTests.tearDown(self)
    def upload(self,raw,kind,mime):
        current=self.store.get(self.project['id']);row=self.service.create(current['id'],{'revision':current['revision'],'kind':kind,'content_type':mime,
            'filename':'Actual owned source with untrusted extension.bin','total_bytes':len(raw),'rights_confirmed':True,'request_key':'audio-owned-'+uuid.uuid4().hex},actor='fixture-editor')[0]
        row=self.service.chunk(current['id'],row['upload_id'],0,__import__('hashlib').sha256(raw).hexdigest(),raw)[0]
        result=self.service.complete(current['id'],row['upload_id'],{'revision':current['revision'],'expected_parts_sha256':row['parts_sha256']})[0]
        return result['result']['asset']
    def collected(self):
        self.project=self.store.get(self.project['id']);job=self.run_job();self.assertEqual(job['status'],'succeeded',job.get('error'))
        self.project=self.store.get(self.project['id']);return audio_transcripts.view(self.store,self.project['id'],'wsp_audio_transcript_fixture')
    def request_body(self,row,text='Cần Giờ được người dùng sửa.'):
        return {'expected_version':row['current']['version'],'base_transcript_id':row['current']['transcript_id'],
            'expected_timeline_version':None,'segments':[{'segment_id':row['current']['segments'][0]['segment_id'],'text':text}],'note':'Explicit fixture human edit, no Owner UAT'}
    def edit(self,row,body=None):
        return audio_transcripts.edit(self.store,self.project['id'],self.store.get(self.project['id'])['revision'],row['asset_id'],body or self.request_body(row),
            asset_sha256=row['asset_sha256'],analysis_sha256=row['analysis_sha256'],actor_ref='fixture-editor')
    def test_actual_audio_metadata_normalized_words_and_reopen_have_no_visual_guess(self):
        before=file_sha(self.speech_source);view=self.collected();row=view['items'][0];record=self.project['document']['media_analysis'][0]
        self.assertEqual(record['media']['media_kind'],'audio');self.assertEqual(record['media']['metadata_source'],'ffprobe_audio_stream')
        for key in ['width','height','orientation','average_rgb','fps']:self.assertIsNone(record['media'][key])
        self.assertEqual(record['media']['audio_streams'][0]['channels'],2);self.assertEqual(record['media']['audio_streams'][0]['sample_rate'],48000)
        self.assertEqual(record['audio']['channels'],1);self.assertEqual(record['audio']['sample_rate'],16000)
        self.assertEqual(row['current']['segments'][0]['words'][1]['start_seconds'],.21);self.assertTrue(row['original']['is_original_evidence'])
        self.assertEqual(self.project['input']['metadata']['workflow'],'REVIEW_TRANSCRIPT');self.assertEqual(len(self.project['input']['audio_assets']),1)
        self.assertEqual(transcript_script(self.project['document']),'Xin chào.');self.assertIn('audio nguồn',provider_context(self.project['document']))
        self.assertEqual(audio_transcripts.view(Store(self.root),self.project['id'],'wsp_audio_transcript_fixture'),view)
        self.assertEqual(file_sha(self.speech_source),before);self.assertFalse(view['publishing_enabled']);self.assertTrue(fixture.FixtureTransport.calls)
    def test_music_and_subtitle_are_excluded_from_speech_and_image_analysis(self):
        self.upload(self.speech_source.read_bytes(),'music','audio/wav');self.upload(b'1\n00:00:00,000 --> 00:00:01,000\nOnly subtitle\n','subtitle','application/x-subrip')
        doc=self.store.get(self.project['id'])['document'];self.assertEqual([a['id'] for a in asr.pending_speech(doc)],[self.asset['id']])
        self.assertEqual([a['id'] for a in asr.pending_assets(doc)],[self.asset['id']]);self.assertEqual(len(self.collected()['items']),1)
        self.assertEqual(len(self.store.get(self.project['id'])['document']['media_analysis']),1)
    def test_unavailable_provider_creates_no_transcript_or_placeholder(self):
        self.project=self.store.get(self.project['id'])
        with patch.object(asr.connection,'status',return_value={'connected':False}):
            job=self.run_job();self.assertEqual(job['status'],'failed');self.assertIn('ASR_PROVIDER_UNAVAILABLE',str(job))
        current=self.store.get(self.project['id']);self.assertEqual(current['input']['metadata']['workflow'],'ASR_REQUIRED')
        self.assertEqual(audio_transcripts.view(self.store,current['id'],'wsp_audio_transcript_fixture')['items'],[]);self.assertEqual(fixture.FixtureTransport.calls,[])
    def test_edit_preserves_raw_provider_and_timestamps_uses_new_text_and_can_restore(self):
        original=self.collected();row=original['items'][0];doc=copy.deepcopy(self.project['document']);before=file_sha(self.root/'assets'/self.asset['id']);calls=list(fixture.FixtureTransport.calls)
        self.assertTrue(self.edit(row));changed=audio_transcripts.view(self.store,self.project['id'],'wsp_audio_transcript_fixture');new=changed['items'][0]
        self.assertEqual(new['original'],row['original']);self.assertEqual(new['current']['version'],2);self.assertEqual(new['current']['segments'][0]['words'],[])
        self.assertIsNone(new['current']['segments'][0]['confidence']);self.assertEqual(new['current']['segments'][0]['start_seconds'],row['current']['segments'][0]['start_seconds'])
        current=self.store.get(self.project['id']);self.assertEqual(current['document']['media_analysis'],doc['media_analysis']);self.assertIn('Cần Giờ',transcript_script(current['document']))
        self.assertIn('Cần Giờ',provider_context(current['document']));self.assertIn('bản chỉnh sửa của người dùng',provider_context(current['document']));self.assertIsNone(current['approval'])
        body=self.request_body(new,row['original']['segments'][0]['text']);body['base_transcript_id']=row['original']['transcript_id'];body['segments'][0]['segment_id']=row['original']['segments'][0]['segment_id']
        self.assertTrue(self.edit(new,body));restored=audio_transcripts.view(Store(self.root),self.project['id'],'wsp_audio_transcript_fixture')['items'][0]
        self.assertEqual(restored['current']['version'],3);self.assertEqual(len(restored['current']['segments'][0]['words']),2);self.assertEqual(restored['original'],row['original'])
        self.assertEqual(file_sha(self.root/'assets'/self.asset['id']),before);self.assertEqual(fixture.FixtureTransport.calls,calls)
    def test_noop_stale_revision_version_source_and_unknown_segment_are_closed(self):
        row=self.collected()['items'][0];before=self.store.get(self.project['id']);body=self.request_body(row,row['current']['segments'][0]['text']);self.assertFalse(self.edit(row,body))
        self.assertEqual(self.store.get(self.project['id']),before)
        for change in [{'expected_version':2},{'expected_timeline_version':1},{'base_transcript_id':'trn_unknown'},
                       {'segments':[{'segment_id':'seg_unknown','text':'No source'}]}]:
            with self.assertRaises(WorkflowError):self.edit(row,{**self.request_body(row),**change})
        for key in ['asset_sha256','analysis_sha256']:
            foreign={**row,key:'a'*64}
            with self.assertRaisesRegex(WorkflowError,'SOURCE_CHANGED'):self.edit(foreign)
        self.assertEqual(self.store.get(self.project['id']),before)
    def test_altered_normalized_evidence_and_history_are_rejected(self):
        row=self.collected()['items'][0];doc=copy.deepcopy(self.project['document']);bad=copy.deepcopy(doc)
        r=bad['media_analysis'][0];r['normalized_transcript']['segments'][0]['text']='Unverified replacement';r['analysis_sha256']=digest({k:v for k,v in r.items() if k!='analysis_sha256'})
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):audio_transcripts.original(bad,self.asset)
        self.edit(row);doc=self.store.get(self.project['id'])['document'];bad=copy.deepcopy(doc);bad['audio_transcript_versions'][0]['segments'][0]['text']='Changed journal'
        with self.assertRaisesRegex(WorkflowError,'HISTORY_CHANGED'):audio_transcripts.selected(bad,self.asset)
    def test_current_transcript_and_original_file_are_retained_by_backup_restore(self):
        row=self.collected()['items'][0];self.edit(row)
        from services.windows_native.backup import create_backup,restore_backup
        receipt=create_backup(self.config,self.owned_folder/'backup-audio.zip');destination=self.owned_folder/'audio-restored'
        restore_backup(receipt['backup_path'],destination,expected_sha256=receipt['sha256'])
        restored=audio_transcripts.view(Store(destination),self.project['id'],'wsp_audio_transcript_fixture')
        self.assertEqual(restored,audio_transcripts.view(self.store,self.project['id'],'wsp_audio_transcript_fixture'))
        self.assertEqual(file_sha(destination/'originals'/self.asset['original_id']),self.asset['source_sha256'])
    def test_changed_source_file_blocks_edit_and_preserves_original_recognition(self):
        row=self.collected()['items'][0];before=self.store.get(self.project['id'])
        (self.root/'assets'/self.asset['id']).write_bytes(b'Altered owned fixture bytes')
        with self.assertRaises(WorkflowError):self.edit(row)
        self.assertEqual(self.store.get(self.project['id']),before)
