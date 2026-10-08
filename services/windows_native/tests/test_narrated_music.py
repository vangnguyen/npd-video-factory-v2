"""Actual stereo PCM/music/preview/QC with explicit tone and approval fixtures."""
import copy,json,unittest,uuid,wave
from unittest.mock import patch
from services.windows_native.tests import test_narration as fixture,test_source_music as music_fixture
from services.windows_native.narration import apply
from services.windows_native.narrated_music import materialize,verify_bundle
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.shot_adapter import validate_document
from services.windows_native.pipeline import Pipeline
from services.windows_native.hardening import Artifacts

class NarratedMusicTests(unittest.TestCase):
    tearDown=fixture.NarrationTests.tearDown
    def setUp(self):
        fixture.NarrationTests.setUp(self)
        from services.windows_native.north_star_quality import policy_reference
        with self.store.transaction() as con:
            document=self.project['document'];document['production_quality']=policy_reference()
            con.execute('UPDATE projects SET revision=revision+1,document=?,approval=NULL WHERE id=?',(json.dumps(document),self.project['id']));self.store.version(con,self.project['id'])
        self.project=self.store.shot_view(self.project['id'])
    start=fixture.NarrationTests.start;finish=fixture.NarrationTests.finish;body=fixture.NarrationTests.body;audible=fixture.NarrationTests.audible
    music=music_fixture.SourceMusicTests.music
    def ready(self,fade=.25):
        self.source,self.voice_out,self.result=self.finish();self.project=apply(self.store,self.project['id'],self.source['id'],self.body(self.result));self.asset=self.music()
        self.project=self.store.set_music(self.project['id'],self.project['revision'],self.asset,loop_crossfade_seconds=fade);return self.project
    def bed(self,document=None,name='measured-bed'):
        out=self.root/name;out.mkdir();path,receipt=materialize(self.config,document or self.project['document'],out);return out,path,receipt
    def test_zero_preserves_original_music_document_and_canonical_video_track_only(self):
        self.ready(0);self.assertEqual(self.project['document']['music'],self.asset);self.assertEqual(len(self.project['document']['canonical_timeline']['snapshot']['tracks']),1)
        self.assertNotIn('narrated_music_loop',self.project['document']['canonical_timeline']['snapshot']['metadata'])
    def test_measured_overlap_plan_uses_actual_frames_and_normalized_unclipped_source_preserving_pcm(self):
        self.ready();before=file_sha(self.root/'assets'/self.asset['id']);state=self.project['document']['canonical_timeline'];track=state['snapshot']['tracks'][-1]
        self.assertEqual([c['timeline_start'] for c in track['clips']],[0,.75,1.5,2.25,3]);self.assertEqual(track['clips'][1]['transition_in']['kind'],'crossfade')
        self.assertEqual(self.project['document']['music']['narrated_loop']['source_frames'],48000);self.assertIsNone(self.project['approval'])
        out,path,receipt=self.bed();self.assertEqual(receipt['output_frames'],158400);self.assertEqual(receipt['pre_pcm_clipped_samples'],0);self.assertIsNotNone(receipt['input_rms_db'])
        self.assertEqual(file_sha(self.root/'assets'/self.asset['id']),before);self.assertFalse(receipt['speech_quality_accepted']);self.assertFalse(receipt['rights_independently_verified'])
        with wave.open(str(path),'rb') as audio:self.assertEqual((audio.getnchannels(),audio.getframerate(),audio.getnframes()),(2,48000,158400))
    def test_reversible_timing_and_disable_rebuild_same_canonical_music_track_without_input_mutation(self):
        self.ready();before=copy.deepcopy(self.project);shot=self.store.shot_view(self.project['id'])['shot_timeline']['shots'][0]
        changed=self.store.mutate_shots(self.project['id'],self.project['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'duration':3.3}})
        self.assertGreater(len(changed['document']['canonical_timeline']['snapshot']['tracks'][-1]['clips']),len(before['document']['canonical_timeline']['snapshot']['tracks'][-1]['clips']))
        self.assertEqual(changed['document']['music'],before['document']['music']);self.assertEqual(file_sha(self.root/'assets'/self.asset['id']),self.asset['sha256'])
        disabled=self.store.save(changed['id'],changed['revision'],music_enabled=False);self.assertEqual(len(disabled['document']['canonical_timeline']['snapshot']['tracks']),1)
        enabled=self.store.save(disabled['id'],disabled['revision'],music_enabled=True);self.assertEqual(len(enabled['document']['canonical_timeline']['snapshot']['tracks']),2)
    def test_strict_invalid_fade_and_too_many_clips_fail_without_changing_project_or_pcm(self):
        asset=self.music();before=self.store.get(self.project['id'])
        for fade in [True,False,'0.2',float('nan'),float('inf'),-1,.75,2]:
            with self.assertRaises(WorkflowError):self.store.set_music(self.project['id'],self.project['revision'],asset,loop_crossfade_seconds=fade)
            self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(file_sha(self.root/'assets'/asset['id']),asset['sha256'])
        self.ready();from services.windows_native.narrated_music import track
        with self.assertRaisesRegex(WorkflowError,'AUDIO_CLIP_LIMIT'):track(self.project['document'],180)
    def test_rehashed_edited_track_or_numeric_safety_flag_cannot_change_mix_without_document_edit(self):
        self.ready();doc=copy.deepcopy(self.project['document']);doc['canonical_timeline']['snapshot']['tracks'][-1]['clips'][0]['volume']=.8;doc['canonical_timeline']['sha256']=digest(doc['canonical_timeline']['snapshot'])
        with self.assertRaisesRegex(WorkflowError,'SOURCE_OR_CLIPS_CHANGED'):validate_document(doc)
        doc=copy.deepcopy(self.project['document']);doc['music']['narrated_loop']['input_mutated']=0
        with self.assertRaisesRegex(WorkflowError,'LOOP_POLICY_INVALID'):validate_document(doc)
    def test_preview_and_final_use_exact_same_music_bed_and_pcm_source_without_inference(self):
        self.ready();preview=self.audible(self.project);preview_folder=self.root/'shot-previews'/preview['id'];preview_sha=file_sha(preview_folder/'music-loop.wav')
        verified=verify_bundle(self.config,self.project['document'],preview_folder);self.assertEqual(verified['output_sha256'],preview_sha)
        self.project=self.store.approve(self.project['id'],self.project['revision'],'EXPLICIT MUSIC FIXTURE',True);self.store.enqueue(self.project['id'],self.project['revision'],'render',uuid.uuid4().hex);job=self.store.claim()
        with patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('No inference')):result=Pipeline(self.config).run(job,lambda _:None)
        out=self.root/'jobs'/job['id'];self.assertTrue(result['qc']['passed']);self.assertEqual(file_sha(out/'music-loop.wav'),preview_sha);self.assertEqual(file_sha(out/'voice.wav'),file_sha(self.voice_out/'voice.wav'))
        names={i['path'] for i in Artifacts(out,job).load('render')['artifacts']};self.assertTrue({'music-loop.json','music-loop.wav'}<=names)
        self.assertEqual(result['qc']['full_quality']['full_production_qc']['canonical_music_loop']['output_sha256'],preview_sha)
    def test_changed_music_after_preview_prevents_approval_and_bundle_acceptance(self):
        self.ready();preview=self.audible(self.project);folder=self.root/'shot-previews'/preview['id']
        (self.root/'assets'/self.asset['id']).write_bytes(b'EXPLICIT CHANGED MUSIC FIXTURE')
        with self.assertRaises(WorkflowError):self.store.approve(self.project['id'],self.project['revision'],'EXPLICIT MUSIC FIXTURE',True)
        with self.assertRaises(WorkflowError):verify_bundle(self.config,self.project['document'],folder)
    def test_corrupted_preview_music_bed_prevents_review_and_approval(self):
        self.ready();preview=self.audible(self.project);folder=self.root/'shot-previews'/preview['id'];path=folder/'music-loop.wav'
        data=bytearray(path.read_bytes());data[-2]^=1;path.write_bytes(data)
        with self.assertRaises(WorkflowError):verify_bundle(self.config,self.project['document'],folder)
        with self.assertRaises(WorkflowError):self.store.approve(self.project['id'],self.project['revision'],'EXPLICIT MUSIC FIXTURE',True)
    def test_actual_changed_rendered_pcm_is_a_hard_full_qc_failure(self):
        self.ready();self.audible(self.project);self.project=self.store.approve(self.project['id'],self.project['revision'],'EXPLICIT MUSIC FIXTURE',True)
        self.store.enqueue(self.project['id'],self.project['revision'],'render',uuid.uuid4().hex);job=self.store.claim()
        def changed(config,document,out):
            path,receipt=materialize(config,document,out);data=bytearray(path.read_bytes());data[-2]^=1;path.write_bytes(data);return path,receipt
        with patch('services.windows_native.narrated_music.materialize',side_effect=changed),self.assertRaisesRegex(WorkflowError,'FULL_MEDIA_QC_FAILED'):
            Pipeline(self.config).run(job,lambda _:None)
        reports=list((self.root/'jobs'/job['id']).rglob('qc-report.json'));self.assertEqual(len(reports),1)
        qc=json.loads(reports[0].read_bytes());self.assertFalse(qc['passed']);self.assertEqual(qc['full_quality']['status'],'failed_qc')
        self.assertEqual(qc['full_quality']['failure_code'],'NARRATED_MUSIC_RENDER_BINDING_CHANGED')
    def test_family_reuses_canonical_music_but_changed_music_blocks_new_family_atomically(self):
        self.ready();from services.windows_native.narrated_variants import NativeNarratedVariants
        from services.windows_native.narrated_variants_models import Create
        service=NativeNarratedVariants(self.store);doc=self.project['document']
        body=Create(revision=self.project['revision'],expected_version=doc['canonical_timeline']['version'],expected_prepared_reference_sha256=digest(doc['prepared_narration']),
            profile_refs=['social-square@1'],request_key='explicit-canonical-music-family-fixture')
        batch,_=service.create(self.project['id'],body,actor='EXPLICIT');child=self.store.get(batch['result']['variants'][0]['project_id'])
        self.assertEqual(child['document']['canonical_timeline']['snapshot']['tracks'][-1],doc['canonical_timeline']['snapshot']['tracks'][-1]);self.assertIsNone(child['approval'])
        with self.store.transaction() as con:before={t:con.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('projects','project_versions','events','native_narrated_variant_batches')}
        (self.root/'assets'/self.asset['id']).write_bytes(b'EXPLICIT MUSIC CHANGE')
        with self.assertRaises(WorkflowError):service.create(self.project['id'],body.model_copy(update={'request_key':'explicit-changed-music-family-fixture'}),actor='EXPLICIT')
        with self.store.transaction() as con:self.assertEqual(before,{t:con.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in before})
    def test_generated_bed_receipt_binding_rejects_foreign_canonical_or_output_hash(self):
        self.ready();out,path,receipt=self.bed();changed={**receipt,'canonical_timeline_sha256':'0'*64};(out/'music-loop.json').write_text(json.dumps(changed),encoding='utf-8')
        with self.assertRaisesRegex(WorkflowError,'RENDER_BINDING_CHANGED'):verify_bundle(self.config,self.project['document'],out,{'canonical_music_loop':changed})
        for name,value in [('external_calls',False),('limiter',1),('input_rms_db',float('nan')),('normalization_gain',float('inf')),('nominal_gain_after_bed',.8),('sample_rate',48000.)]:
            changed={**receipt,name:value};(out/'music-loop.json').write_text(json.dumps(changed),encoding='utf-8')
            with self.assertRaisesRegex(WorkflowError,'RENDER_BINDING_CHANGED'):verify_bundle(self.config,self.project['document'],out,{'canonical_music_loop':changed})
