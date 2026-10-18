"""Read-only installed preset metadata and mocked child transport. No TTS inference."""
import json,subprocess,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from services.windows_native.pipeline import Config
from services.windows_native.contracts import MODEL,WorkflowError
from services.windows_native.dialogue_vieneu import catalog,VieNeuDialoguePresetAdapter

class DialogueVieNeuTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'state';self.root.mkdir()
        self.config=Config(data_root=self.root);self.adapter=VieNeuDialoguePresetAdapter(self.config)
        self.voice={'provider':'vieneu-local','model':MODEL,'provider_voice_id':'Thùy Dung','locale':'vi-VN','source_type':'provider_preset',
            'rights_status':'owner_declared','license':'EXPLICIT TRANSPORT FIXTURE ONLY','source_reference':'fixture://metadata-test','permission_reference':'not a real permission or voice audition'}
        self.line={'speed':1.0,'style':'neutral'}
    def tearDown(self):self.temp.cleanup()
    def target(self,name='attempt'):
        directory=self.root/name;directory.mkdir();return directory/'line.wav'

    def test_pinned_preset_catalog_is_metadata_only_source_licensed_and_no_default_selection(self):
        with patch('services.windows_native.dialogue_vieneu.subprocess.run',side_effect=AssertionError('Catalog must not launch inference')):
            result=catalog(self.config)
        self.assertEqual(result['status'],'METADATA_AVAILABLE');self.assertEqual(len(result['voices']),25)
        self.assertIsNone(result['default_voice']);self.assertEqual(result['inference_calls'],0);self.assertFalse(result['custom_reference_cloning'])
        self.assertTrue(all(v['rights_status']=='source_licensed' for v in result['voices']));self.assertTrue(result['requires_runtime_validation'])
        self.assertEqual(result['model'],'vieneu-v3-turbo');self.assertTrue(all(v['human_listening_accepted'] is False for v in result['voices']))

    def test_unknown_voice_reference_cloning_language_style_and_speed_fail_without_fallback(self):
        for voice,line in [({**self.voice,'provider_voice_id':'UNKNOWN PRESET'},self.line),({**self.voice,'source_type':'licensed_reference'},self.line),
            ({**self.voice,'locale':'en-US'},self.line),(self.voice,{'speed':1.2,'style':'neutral'}),(self.voice,{'speed':True,'style':'neutral'}),
            (self.voice,{'speed':1.0,'style':'warm'})]:
            with self.subTest(voice=voice,line=line),self.assertRaises(WorkflowError):self.adapter.validate(voice,line)
        with self.assertRaisesRegex(WorkflowError,'RIGHTS_CONFIRMATION_REQUIRED'):self.adapter.validate({**self.voice,'rights_status':'unknown'},self.line)

    def test_mocked_child_transport_uses_hidden_offline_process_and_safe_structured_receipt(self):
        target=self.target();calls=[]
        def transport(command,**options):
            calls.append((command,options));(target.parent/'provider-receipt.json').write_text(json.dumps({'operation_id':'explicit-mock-transport-not-provider-evidence'}))
            return SimpleNamespace(returncode=0,stdout=b'private SDK output must be discarded',stderr=b'')
        with patch('services.windows_native.dialogue_vieneu.subprocess.run',side_effect=transport):
            result=self.adapter.synthesize(text='Explicit transport fixture.',voice=self.voice,line=self.line,take=None,request_key='a'*64,target=target)
        self.assertEqual(result['operation_id'],'explicit-mock-transport-not-provider-evidence');self.assertFalse(target.exists())
        command,options=calls[0];self.assertEqual(options['env']['HF_HUB_OFFLINE'],'1');self.assertEqual(options['env']['TRANSFORMERS_OFFLINE'],'1')
        self.assertTrue(options['capture_output']);self.assertNotIn('Explicit transport fixture.',' '.join(command));self.assertFalse((target.parent/'provider.log').exists())
        request=json.loads((target.parent/'provider-request.json').read_bytes());self.assertEqual(request['seed'],int('aaaaaaaa',16))

    def test_child_failure_or_timeout_never_exposes_raw_private_output(self):
        for i,result in enumerate((SimpleNamespace(returncode=1,stdout=b'PRIVATE SCRIPT FROM SDK',stderr=b'PRIVATE DATA'),subprocess.TimeoutExpired('mock-child',300))):
            target=self.target('failure-'+str(i))
            with patch('services.windows_native.dialogue_vieneu.subprocess.run',side_effect=result if isinstance(result,Exception) else None,return_value=result):
                with self.assertRaises(WorkflowError) as error:self.adapter.synthesize(text='Private transport fixture.',voice=self.voice,line=self.line,take=None,request_key='b'*64,target=target)
            self.assertNotIn('PRIVATE',str(error.exception));self.assertFalse(target.exists())

    def test_changed_preset_manifest_fails_discovery_without_starting_core_services(self):
        with patch('services.windows_native.dialogue_vieneu.file_sha',return_value='0'*64):self.assertEqual(catalog(self.config)['status'],'NOT_CONFIGURED')

    def test_invalid_receipt_is_rejected_and_target_scope_checked_before_transport(self):
        target=self.target()
        def transport(*args,**kwargs):
            (target.parent/'provider-receipt.json').write_text(json.dumps({'operation_id':'mock','unexpected_private_field':'not allowed'}));return SimpleNamespace(returncode=0,stdout=b'',stderr=b'')
        with patch('services.windows_native.dialogue_vieneu.subprocess.run',side_effect=transport):
            with self.assertRaisesRegex(WorkflowError,'RECEIPT_INVALID'):self.adapter.synthesize(text='Fixture.',voice=self.voice,line=self.line,take=None,request_key='c'*64,target=target)
        with patch('services.windows_native.dialogue_vieneu.subprocess.run',side_effect=AssertionError('No process for foreign output')):
            with self.assertRaisesRegex(WorkflowError,'OUTPUT_SCOPE_INVALID'):self.adapter.synthesize(text='Fixture.',voice=self.voice,line=self.line,take=None,request_key='d'*64,target=Path(self.temp.name)/'outside.wav')

if __name__=='__main__':unittest.main()
