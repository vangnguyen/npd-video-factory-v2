"""Separate QC profile/frozen admission with actual PNGs and protected mock keys."""
import asyncio,base64,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from pydantic import ValidationError
from services.windows_native.contracts import WorkflowError
from services.windows_native.vision_credentials import NativeVisionKeyVault,PrivateVisionKey
from services.windows_native.vision_registry import VisionProfile
from services.windows_native.render_vision_registry import RenderVisionProfile,RenderVisionRegistry,NativeRenderVisionFactory,load
from services.windows_native.tests import test_render_vision_frame_bridge as frames_fixture
from services.windows_native.tests.test_vision_frame_bridge import response_payload


def profile(receipt,**changes):
    return RenderVisionProfile.model_validate({'profile_id':'nrvp_'+'a'*32,'enabled':True,'key_receipt':receipt,
        'estimated_cost_vnd':'200','input_vnd_per_million_tokens':'10000','cached_input_vnd_per_million_tokens':'1000',
        'output_vnd_per_million_tokens':'20000',**changes})


class RenderVisionRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.root=self.folder/'state';self.root.mkdir()
        self.vault=NativeVisionKeyVault(self.folder/'private',self.root,'wsp_native_local')
        self.receipt=self.vault.save(PrivateVisionKey(workspace_id='wsp_native_local',credential_alias='explicit-render-vision-key',
            api_key='sk-explicit-synthetic-render-vision-not-a-real-key'))
    def tearDown(self):self.temp.cleanup()
    def registry(self,p=None):
        path=self.folder/'render-vision-public.json';path.write_text(json.dumps({'version':1,'workspace_id':'wsp_native_local',
            'profiles':[(profile(self.receipt) if p is None else p).model_dump(mode='json')]}),encoding='utf-8');return path

    def test_defaults_disable_without_startup_decryption_or_source_profile_compatibility(self):
        p=profile(self.receipt,enabled=False)
        with patch.object(self.vault,'key',side_effect=AssertionError('No startup key read')):
            factory=NativeRenderVisionFactory(p,self.vault,operator_enabled=True);state=factory.public()
            self.assertEqual(state['status'],'NOT_CONFIGURED');self.assertFalse(state['startup_decryption'])
            for key in ('asset_analysis_consent_reused','provider_authorized','automatic_dispatch','publishing_enabled','real_provider_tested'):
                self.assertIs(state[key],False)
            self.assertEqual(NativeRenderVisionFactory(profile(self.receipt),self.vault).public()['status'],'NOT_CONFIGURED')
        source=VisionProfile.model_validate({**profile(self.receipt).model_dump(mode='json',exclude={'purpose','schema_version'}),'profile_id':'nvip_'+'a'*32})
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_INVALID'):NativeRenderVisionFactory(source,self.vault)
        with self.assertRaises(ValidationError):profile(self.receipt,purpose='asset_analysis')
        with self.assertRaises(ValidationError):profile(self.receipt,estimated_cost_vnd=1.5)

    def test_registry_unique_raw_boolean_zero_live_rates_and_frozen_configuration(self):
        path=self.registry();factory=next(iter(load(path,self.vault,operator_enabled=True).values()))
        self.assertEqual(factory.public()['status'],'CONFIGURED')
        factory.operator_enabled=False
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):factory.public()
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_INVALID'):NativeRenderVisionFactory(profile(self.receipt),self.vault,operator_enabled=1)
        state=NativeRenderVisionFactory(profile(self.receipt,input_vnd_per_million_tokens='0'),self.vault,operator_enabled=True).public()
        self.assertEqual(state['status'],'NOT_CONFIGURED')
        p=profile(self.receipt)
        with self.assertRaises(ValidationError):RenderVisionRegistry(version=1,workspace_id='wsp_native_local',profiles=[p,p])
        path.write_text('{"version":1,"version":1,"workspace_id":"wsp_native_local","profiles":[]}',encoding='utf-8')
        with self.assertRaisesRegex(WorkflowError,'REGISTRY_INVALID'):load(path,self.vault)

    def test_original_registry_bytes_cannot_change_between_parse_and_binding(self):
        path=self.registry();original=Path.read_bytes;changed=False
        def drift(file):
            nonlocal changed
            raw=original(file)
            if file==path and not changed:
                changed=True;file.write_bytes(raw+b' ')
            return raw
        with patch.object(Path,'read_bytes',new=drift):
            with self.assertRaisesRegex(WorkflowError,'REGISTRY_INVALID'):load(path,self.vault,operator_enabled=True)


class RenderVisionRegistryInputTests(unittest.TestCase):
    def setUp(self):
        self.fixture=frames_fixture.NativeRenderVisionFrameBridgeTests('test_exact_final_png_decoded_pts_metadata_original_result_and_scope_without_authority_or_mutation')
        self.fixture.setUp();self.root=self.fixture.root;self.bridge=self.fixture.bridge()
        self.private=tempfile.TemporaryDirectory();self.vault=NativeVisionKeyVault(Path(self.private.name),self.root,'wsp_native_local')
        self.receipt=self.vault.save(PrivateVisionKey(workspace_id='wsp_native_local',credential_alias='explicit-render-vision-key',
            api_key='sk-explicit-synthetic-render-vision-not-a-real-key'))
    def tearDown(self):self.private.cleanup();self.fixture.tearDown()

    def test_live_requires_owner_guard_and_result_cost_observer_before_private_key(self):
        factory=NativeRenderVisionFactory(profile(self.receipt),self.vault,operator_enabled=True)
        with patch.object(self.vault,'key',side_effect=AssertionError('No private read without controller')):
            for changes in ({},{'admission_guard':lambda:None},{'response_observer':lambda _:None}):
                with self.assertRaisesRegex(WorkflowError,'OWNER_CONTROLLER_REQUIRED'):factory.provider(self.bridge,**changes)
            with self.assertRaisesRegex(WorkflowError,'PROVIDER_INPUT_INVALID'):factory.provider(object(),admission_guard=lambda:None,response_observer=lambda _:None)
            async def asynchronous():return None
            with self.assertRaisesRegex(WorkflowError,'CONTROLLER_INVALID'):factory.provider(self.bridge,admission_guard=asynchronous,response_observer=lambda _:None)
            with self.assertRaisesRegex(WorkflowError,'CONTROLLER_INVALID'):factory.provider(self.bridge,admission_guard=lambda:True,response_observer=lambda _:None)

    def test_exact_render_factory_png_protocol_mock_with_guard_and_original_response_observation(self):
        calls=[];guards=[];responses=[];binding=self.bridge.binding()
        def mock(request):
            images=[v for v in json.loads(request.content)['input'][0]['content'] if v['type']=='input_image']
            shas=[hashlib.sha256(base64.b64decode(v['image_url'].split(',',1)[1],validate=True)).hexdigest() for v in images]
            self.assertEqual(shas,[v['sha256'] for v in binding['record']['observation']['frames']]);calls.append(shas)
            return httpx.Response(200,json=response_payload(self.bridge.max_frames))
        factory=NativeRenderVisionFactory(profile(self.receipt),self.vault,operator_enabled=True,transport=httpx.MockTransport(mock))
        def guard():guards.append('explicit_mock_controller_fence')
        provider=factory.provider(self.bridge,admission_guard=guard,response_observer=responses.append)
        result=asyncio.run(provider.analyze(self.fixture.directory/'final.mp4',metadata=self.bridge.input_metadata(),scenes=[],
            asset_id=binding['render_artifact_id'],checksum_sha256=binding['record']['observation']['rendered_video_sha256'],
            sample_interval_seconds=binding['record']['observation']['sampling_interval_seconds']))
        self.assertEqual(len(calls),1);self.assertEqual(len(responses),1);self.assertGreater(len(guards),2)
        self.assertTrue(result.provenance['mock_tested']);self.assertFalse(result.provenance['real_provider_tested'])
        self.assertFalse(factory.public()['provider_authorized']);self.assertFalse(factory.public()['asset_analysis_consent_reused'])

    def test_late_guard_denial_and_historical_project_drift_block_without_wire_or_key(self):
        wires=[];factory=NativeRenderVisionFactory(profile(self.receipt),self.vault,operator_enabled=True,transport=httpx.MockTransport(lambda request:wires.append(request)))
        stopped=False
        def guard():
            if stopped:raise WorkflowError('EXPLICIT_MOCK_OWNER_CONSENT_REVOKED')
        provider=factory.provider(self.bridge,admission_guard=guard,response_observer=lambda _:None);stopped=True
        with patch.object(self.vault,'key',side_effect=AssertionError('No private read after revocation')):
            with self.assertRaisesRegex(WorkflowError,'CONSENT_REVOKED'):
                asyncio.run(provider.analyze(self.fixture.directory/'final.mp4',metadata=self.bridge.input_metadata(),scenes=[],asset_id='render:'+self.fixture.job['id'],
                    checksum_sha256=self.fixture.job['result']['qc']['final_sha256'],sample_interval_seconds=self.bridge.binding()['record']['observation']['sampling_interval_seconds']))
        self.assertEqual(wires,[])
        with self.fixture.store.transaction() as con:
            doc=self.fixture.project['document'];doc['name']='EXPLICIT HISTORICAL PROJECT FIXTURE'
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(doc),self.fixture.project['id']))
            self.fixture.store.version(con,self.fixture.project['id'])
        historical=self.fixture.bridge()
        with self.assertRaisesRegex(WorkflowError,'CURRENT_RENDER_REQUIRED'):factory.provider(historical,admission_guard=lambda:None,response_observer=lambda _:None)


if __name__=='__main__':unittest.main()
