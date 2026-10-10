"""Actual bounded stereo sample facts; synthetic tones are not speech acceptance."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from services.windows_native import audio_balance as balance
from services.windows_native.contracts import WorkflowError,file_sha,digest,write_json

class AudioBalanceTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def signals(self,reference=.1,music=.01,missing=False,opposite=False):
        t=np.arange(balance.RATE)/balance.RATE;voice=reference*np.sin(2*np.pi*880*t);bed=music*np.sin(2*np.pi*220*t)
        left=voice;right=-voice if opposite else voice
        for name,data in [(balance.REFERENCE,np.column_stack((left,right))),(balance.MUSIC,np.column_stack((bed,bed))),
            (balance.FINAL,np.zeros((len(t),2)) if missing else np.column_stack((left+bed,right+bed)))]:
            (self.root/name).write_bytes(data.astype('<f4').tobytes())
    def measure(self,role='narrated_voice'):
        return balance.measure(self.root,duration=1,final_sha256='a'*64,document_sha256='b'*64,manifest_sha256='c'*64,reference_role=role)
    def test_actual_stereo_margin_and_original_hashes_pass_without_claiming_speech_rights_or_uat(self):
        self.signals();before={p.name:file_sha(p) for p in self.root.iterdir()};value=self.measure()
        self.assertEqual(value['status'],'passed');self.assertAlmostEqual(value['minimum_reference_to_music_db'],20,places=3);self.assertEqual(value['reference_active_seconds'],1)
        self.assertEqual(value['overpowering_fraction'],0);self.assertFalse(value['speech_intelligibility_accepted']);self.assertFalse(value['human_listening_accepted'])
        self.assertFalse(value['publishing_authorized']);self.assertEqual(value['external_provider_calls'],0)
        for name,sha in before.items():self.assertEqual(file_sha(self.root/name),sha)
    def test_music_over_voice_is_measured_even_when_final_output_is_audible(self):
        self.signals(music=.3);value=self.measure();self.assertEqual(value['status'],'failed_qc');self.assertIn('MUSIC_OVERPOWERS_REFERENCE',value['failures'])
        self.assertEqual(value['overpowering_fraction'],1);self.assertLess(value['overall_rms_dbfs']['final'],0);self.assertEqual(len(value['worst_windows']),8)
    def test_reference_silenced_by_gain_cannot_be_hidden_by_music(self):
        self.signals(reference=0,music=.3);value=self.measure();self.assertIn('REFERENCE_AUDIO_INAUDIBLE',value['failures']);self.assertIsNone(value['overpowering_fraction'])
    def test_lost_final_audio_during_reference_is_a_failure(self):
        self.signals(missing=True);value=self.measure();self.assertIn('FINAL_AUDIO_MISSING_DURING_REFERENCE',value['failures']);self.assertEqual(value['missing_mix_fraction'],1)
    def test_stereo_phase_opposition_is_not_downmixed_into_false_silence(self):
        self.signals(opposite=True,music=0);value=self.measure();self.assertEqual(value['status'],'passed');self.assertTrue(value['stereo_energy_preserved'])
        self.assertEqual(value['reference_active_seconds'],1);self.assertIsNone(value['minimum_reference_to_music_db'])
    def test_original_footage_reference_does_not_claim_source_voice_separation(self):
        self.signals();value=self.measure('canonical_original_audio');self.assertEqual(value['status'],'passed');self.assertFalse(value['source_voice_separated']);self.assertFalse(value['speech_detection_performed'])
    def test_no_planned_reference_is_explicit_not_applicable(self):
        self.signals();(self.root/balance.REFERENCE).unlink();value=self.measure('no_reference');self.assertEqual(value['status'],'not_applicable');self.assertEqual(value['reference_active_seconds'],0)
    def test_nan_misaligned_and_wrong_duration_bytes_fail_instead_of_missing_metrics(self):
        self.signals();path=self.root/balance.REFERENCE;original=path.read_bytes()
        for data in [b'bad',np.full(balance.RATE*2,np.nan,dtype='<f4').tobytes(),original[:balance.FRAME_BYTES*100]]:
            path.write_bytes(data)
            with self.assertRaises(WorkflowError):self.measure()
    def test_changed_sample_during_measurement_is_detected(self):
        self.signals();original=balance.file_sha;reads=[0]
        def fingerprint(path):
            value=original(path);reads[0]+=1
            if reads[0]==3:
                p=self.root/balance.REFERENCE;data=bytearray(p.read_bytes());data[-1]^=1;p.write_bytes(data)
            return value
        with patch.object(balance,'file_sha',side_effect=fingerprint):
            with self.assertRaisesRegex(WorkflowError,'PCM_CHANGED'):self.measure()
    def test_untyped_duration_and_unknown_reference_cannot_claim_a_policy_result(self):
        self.signals()
        for value in [True,0,float('inf'),1801]:
            with self.assertRaises(WorkflowError):balance.measure(self.root,duration=value,final_sha256='a'*64,document_sha256='b'*64,manifest_sha256='c'*64,reference_role='narrated_voice')
        with self.assertRaises(WorkflowError):self.measure('owner_accepted_voice')
    def test_missing_tail_is_not_skipped_by_shortest_stem_comparison(self):
        self.signals();path=self.root/balance.MUSIC;path.write_bytes(path.read_bytes()[:-balance.FRAME_BYTES*2400])
        with self.assertRaisesRegex(WorkflowError,'PCM_BINDING_INVALID'):self.measure()
        self.assertFalse((self.root/balance.REPORT).exists())
    def test_boolean_string_nonfinite_and_extra_policy_are_rejected(self):
        for body in [{'maximum_overpowering_fraction':True},{'minimum_reference_to_music_db':'6'},
            {'activity_threshold_dbfs':float('nan')},{'speech_accepted':True}]:
            with self.assertRaises(ValueError):balance.Policy.model_validate(body)
    def test_offline_revalidation_recomputes_facts_and_rejects_forged_metrics_or_filter_binding(self):
        self.signals();video=self.root/'final.mp4';video.write_bytes(b'EXPLICIT HASH-ONLY VIDEO FIXTURE; NOT DECODED MEDIA')
        filters={}
        for role,name in [('reference',balance.REFERENCE),('music',balance.MUSIC)]:
            path=self.root/('audio-'+role+'-filter.txt');path.write_text('EXPLICIT FILTER BINDING FIXTURE',encoding='utf-8');filters[role]=file_sha(path)
        manifest=self.root/'render-manifest.json'
        write_json(manifest,{'audio_balance_inputs':{'reference_role':'narrated_voice',
            'reference_sha256':file_sha(self.root/balance.REFERENCE),'music_sha256':file_sha(self.root/balance.MUSIC),
            'filter_graph_sha256':digest(filters),'diagnostic_filter_threads':1,'diagnostic_pass':'independent_audio_only_same_source_and_dsp'}})
        value=balance.measure(self.root,duration=1,final_sha256=file_sha(video),document_sha256='b'*64,
            manifest_sha256=file_sha(manifest),reference_role='narrated_voice')
        original=file_sha(self.root/balance.REPORT)
        checked=balance.validate(self.root,value,duration=1,document_sha256='b'*64,manifest_name=manifest.name,reference_role='narrated_voice')
        self.assertEqual(checked,value);self.assertEqual(file_sha(self.root/balance.REPORT),original)
        body=json.loads(manifest.read_bytes());body['audio_balance_inputs']['diagnostic_filter_threads']=True
        write_json(manifest,body)
        with self.assertRaisesRegex(WorkflowError,'STEM_BINDING_CHANGED'):
            balance.validate(self.root,value,duration=1,document_sha256='b'*64,manifest_name=manifest.name,reference_role='narrated_voice')
        body['audio_balance_inputs']['diagnostic_filter_threads']=1;write_json(manifest,body)
        bad=copy.deepcopy(value);bad['reference_active_seconds']=.1;write_json(self.root/balance.REPORT,bad)
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):
            balance.validate(self.root,bad,duration=1,document_sha256='b'*64,manifest_name=manifest.name,reference_role='narrated_voice')
        write_json(self.root/balance.REPORT,value);(self.root/'audio-music-filter.txt').write_bytes(b'EXPLICIT FILTER CHANGE')
        with self.assertRaisesRegex(WorkflowError,'STEM_BINDING_CHANGED'):
            balance.validate(self.root,value,duration=1,document_sha256='b'*64,manifest_name=manifest.name,reference_role='narrated_voice')

if __name__=='__main__':unittest.main()
