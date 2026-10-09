"""Actual verified render PNGs and isolated structured HTTP protocol mocks."""
import asyncio,base64,copy,hashlib,json,tempfile,unittest,uuid
from pathlib import Path
import httpx
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.pipeline import Pipeline,Config
from services.windows_native.server import Runner
from services.windows_native.render_vision_frame_bridge import NativeRenderEvidenceFrameExtractor
from services.windows_native.tests import test_source_render as source_fixture
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from app.openai_vision_provider import OpenAIVisionProvider


class NativeRenderVisionFrameBridgeTests(unittest.TestCase):
    def setUp(self):
        self.fixture=source_fixture.NativeSourceRenderTests('test_real_source_worker_qc_checkpoint_keeps_media_immutable_and_requires_final_review')
        self.fixture.setUp();self.fixture.config.secret_file=self.fixture.root/'absent-key';self.fixture.config.assemblyai_secret_file=self.fixture.root/'absent-asr'
        self.fixture.review_fixture();self.store,self.config,self.root=self.fixture.store,self.fixture.config,self.fixture.root
        self.project=self.fixture.project
        queued=self.store.enqueue(self.project['id'],self.project['revision'],'render',uuid.uuid4().hex)
        assert Runner(self.store,Pipeline(self.config)).run_one()
        self.job=self.store.get_job(queued['id']);assert self.job['status']=='succeeded',self.job['error']
        self.directory=self.root/'jobs'/queued['id']

    def tearDown(self):self.fixture.tearDown()

    def bridge(self,**changes):
        values={'project_id':self.project['id'],'job_id':self.job['id'],**changes}
        return NativeRenderEvidenceFrameExtractor(self.store,self.config,**values)

    def extract(self,bridge,**changes):
        binding=bridge.binding();values={'metadata':bridge.input_metadata(),'scenes':[],'asset_id':'render:'+self.job['id'],
            'sample_interval_seconds':binding['record']['observation']['sampling_interval_seconds'],**changes}
        return asyncio.run(bridge.extract(self.directory/'final.mp4',**values))

    def test_exact_final_png_decoded_pts_metadata_original_result_and_scope_without_authority_or_mutation(self):
        before=self.store.get(self.project['id']);bridge=self.bridge();binding=bridge.binding();frames=self.extract(bridge)
        self.assertEqual(len(frames),8);self.assertEqual(binding['original_result_sha256'],digest(self.job['result']))
        self.assertEqual(binding['original_document_sha256'],digest(self.job['snapshot']['document']))
        self.assertEqual(binding['record']['observation']['rendered_video_sha256'],self.job['result']['qc']['final_sha256'])
        self.assertTrue(binding['matches_current_project_document']);self.assertTrue(binding['separate_owner_provider_consent_required'])
        self.assertFalse(binding['source_asset_analysis_consent_reused']);self.assertFalse(binding['owner_uat_accepted'])
        self.assertFalse(binding['publishing_authorized']);self.assertFalse(binding['semantic_inference_performed'])
        for frame,original in zip(frames,binding['record']['observation']['frames']):
            self.assertEqual(frame.payload,(self.directory/original['evidence_frame_reference']).read_bytes())
            self.assertEqual(frame.timestamp_seconds,original['timestamp_seconds']);self.assertEqual(frame.sha256,original['sha256'])
            self.assertEqual(frame.evidence_frame_reference,f"render-frame://{self.project['id']}/{self.job['id']}/{Path(original['evidence_frame_reference']).name}")
        binding['record']['observation']['frames'][0]['sha256']='0'*64
        self.assertNotEqual(bridge.binding()['record'],binding['record'])
        self.assertEqual(self.store.get(self.project['id']),before)

    def test_foreign_job_workspace_original_source_metadata_interval_context_and_reader_mutation_block(self):
        for changes in ({'project_id':uuid.uuid4().hex},{'job_id':uuid.uuid4().hex},{'workspace_id':'foreign-workspace'}):
            with self.assertRaisesRegex(WorkflowError,'BINDING_INVALID'):self.bridge(**changes)
        bridge=self.bridge()
        for changes in ({'asset_id':self.fixture.asset['id']},{'sample_interval_seconds':True},{'sample_interval_seconds':0},
            {'metadata':Config()},{'scenes':[{'source_video_scene_cannot_replace_render_context':True}]}):
            with self.assertRaisesRegex(WorkflowError,'REQUEST_INVALID'):self.extract(bridge,**changes)
        bridge.max_frames+=1
        with self.assertRaisesRegex(WorkflowError,'INPUT_CHANGED'):bridge.binding()

    def test_changed_original_png_checkpoint_and_current_project_invalidate_frozen_input(self):
        bridge=self.bridge();image=self.directory/'render-frame-qc/0.png';original=image.read_bytes()
        image.write_bytes(b'EXPLICIT ISOLATED PNG CORRUPTION')
        with self.assertRaisesRegex(WorkflowError,'BINDING_INVALID'):self.extract(bridge)
        image.write_bytes(original)
        self.assertEqual(len(self.extract(bridge)),8)
        with self.store.transaction() as con:
            doc=copy.deepcopy(self.project['document']);doc['name']='EXPLICIT CURRENT PROJECT DRIFT'
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(doc),self.project['id']))
            self.store.version(con,self.project['id'])
        with self.assertRaisesRegex(WorkflowError,'INPUT_CHANGED'):self.extract(bridge)
        historical=self.bridge().binding();self.assertFalse(historical['matches_current_project_document'])
        self.assertFalse(historical['publishing_authorized']);self.assertTrue(historical['separate_owner_provider_consent_required'])

    def test_existing_structured_adapter_receives_exact_render_pngs_with_final_checksum_and_explicit_mock_provenance(self):
        bridge=self.bridge();binding=bridge.binding();calls=[];before=self.store.get(self.project['id'])
        def handler(request):
            body=json.loads(request.content);calls.append(body);self.assertFalse(body['store'])
            images=[item for item in body['input'][0]['content'] if item['type']=='input_image']
            self.assertEqual(len(images),8)
            for image,original in zip(images,binding['record']['observation']['frames']):
                payload=base64.b64decode(image['image_url'].split(',',1)[1],validate=True)
                self.assertEqual(hashlib.sha256(payload).hexdigest(),original['sha256'])
            return httpx.Response(200,json=response_payload(bridge.max_frames))
        provider=OpenAIVisionProvider(credential_alias='explicit-synthetic-render-vision',credential_resolver=lambda _: 'contract-key-not-real',
            frame_extractor=bridge,transport=httpx.MockTransport(handler),allow_zero_cost_contract_test=True)
        result=asyncio.run(provider.analyze(self.directory/'final.mp4',metadata=bridge.input_metadata(),scenes=[],asset_id='render:'+self.job['id'],
            checksum_sha256=self.job['result']['qc']['final_sha256'],sample_interval_seconds=binding['record']['observation']['sampling_interval_seconds']))
        self.assertEqual(len(calls),1);self.assertTrue(result.provenance['mock_tested']);self.assertFalse(result.provenance['real_provider_tested'])
        self.assertEqual(result.provenance['source_checksum'],self.job['result']['qc']['final_sha256'])
        self.assertEqual(result.frames[0].evidence_frame_reference,f"render-frame://{self.project['id']}/{self.job['id']}/0.png")
        self.assertEqual(self.store.get(self.project['id']),before);self.assertFalse(bridge.binding()['semantic_inference_performed'])

    def test_original_asset_analysis_factory_rejects_render_bridge_before_provider_or_key_resolution(self):
        from services.windows_native.vision_credentials import NativeVisionKeyVault,PrivateVisionKey
        from services.windows_native.vision_registry import NativeVisionFactory
        from services.windows_native.tests.test_vision_registry import profile
        bridge=self.bridge()
        with tempfile.TemporaryDirectory() as private:
            vault=NativeVisionKeyVault(Path(private),self.root,'wsp_native_local')
            saved=vault.save(PrivateVisionKey.model_validate({'workspace_id':'wsp_native_local','credential_alias':'explicit-vision-key',
                'api_key':'sk-explicit-synthetic-render-vision-not-a-real-key'}))
            factory=NativeVisionFactory(profile(saved),vault,operator_enabled=True,transport=httpx.MockTransport(lambda _: self.fail('No protocol request permitted')))
            self.assertEqual(factory.public()['status'],'CONFIGURED')
            with self.assertRaisesRegex(WorkflowError,'PROVIDER_INPUT_INVALID'):factory.provider(bridge)


if __name__=='__main__':unittest.main()
