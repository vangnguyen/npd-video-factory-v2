"""Actual signed loopback rendered-QC contract; no real provider or spend."""
import http.client,json,threading,unittest
from unittest.mock import patch
from pathlib import Path
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.tests import test_render_vision as runtime_fixture
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer,Handler,Runner
from services.windows_native.render_vision_registry import RenderVisionRegistry,NativeRenderVisionFactory
from services.windows_native.render_vision import NativeRenderVision
from services.windows_native.observability import Observer
from services.windows_native.contracts import WorkflowError,digest


class NativeRenderVisionHTTPTests(unittest.TestCase):
    runtime=runtime_fixture.NativeRenderVisionTests.runtime
    bridge=runtime_fixture.NativeRenderVisionTests.bridge
    request=runtime_fixture.NativeRenderVisionTests.request
    response=runtime_fixture.NativeRenderVisionTests.response
    @classmethod
    def setUpClass(cls):runtime_fixture.NativeRenderVisionTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):runtime_fixture.NativeRenderVisionTests.tearDownClass.__func__(cls)

    def setUp(self):
        runtime_fixture.NativeRenderVisionTests.setUp(self);self.logs=[];self.pipeline=NoProviderPipeline()
        self.server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=NativeAccess(self.verifier,self.workspace),observer=Observer(self.logs.append),
            render_vision_directory=self.vault.directory,render_vision_enabled=True,render_vision_factories={self.factory.profile.profile_id:self.factory})
        self.service=self.server.render_vision;self.raw='vf1.explicit-fixture.'+'x'*48;self.cookie,session=self.server.access.login(self.raw);self.csrf=session.csrf
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='/api/projects/'+self.project['id']+'/render-vision'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();runtime_fixture.NativeRenderVisionTests.tearDown(self)
    def change_owner(self,**changes):
        runtime_fixture.NativeRenderVisionTests.change_owner(self,**changes)
        if hasattr(self,'server'):
            access=NativeAccess(self.verifier,self.workspace);access.bind_root(self.root);self.server.access=access
    def account(self,role):
        self.raw,data=human_fixture(role,workspace=self.workspace);self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400)
        access=NativeAccess(self.verifier,self.workspace);access.bind_root(self.root);self.server.access=access
        self.cookie,session=access.login(self.raw);self.csrf=session.csrf;self.principal=session.principal
    def http(self,method,path,body=None,headers=None):
        con=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=125)
        con.request(method,path,body=json.dumps(body) if body is not None else None,
            headers={'Content-Type':'application/json','Cookie':'vf_native_session='+self.cookie,'X-VF-CSRF':self.csrf,**(headers or {})})
        response=con.getresponse();metadata=dict(response.getheaders());raw=response.read();con.close()
        return response.status,json.loads(raw) if metadata.get('Content-Type','').startswith('application/json') else raw,metadata
    def create_http(self,**changes):
        status,value,headers=self.http('POST',self.base,self.request(**changes).model_dump(mode='json'))
        self.assertEqual(status,200,value);self.assertEqual(headers['Cache-Control'],'no-store');self.pending=value;return value
    def process_http(self,row):
        status,value,headers=self.http('POST',self.base+'/'+row['vision_id']+'/process',{'expected_snapshot_sha256':row['snapshot_sha256']})
        self.assertEqual(status,200,value);self.assertEqual(headers['Cache-Control'],'no-store');return value

    def test_signed_actual_input_finite_mock_dispatch_exact_history_project_and_no_worker_or_secret_leak(self):
        before=self.store.get(self.project['id']);status,input_view,headers=self.http('GET',self.base+'/input/'+self.job['id'])
        self.assertEqual(status,200,input_view);self.assertEqual(input_view['input_sha256'],digest(input_view['binding']));self.assertFalse(input_view['provider_authorized'])
        self.assertEqual(len(input_view['binding']['record']['observation']['frames']),8);self.assertEqual(headers['Cache-Control'],'no-store')
        session=self.http('GET','/api/session')[1];row=self.create_http();self.assertEqual(row['status'],'approved');self.assertEqual(self.calls,[])
        self.assertFalse(self.server.runner.run_one());done=self.process_http(row);self.assertEqual(done['status'],'succeeded',done['failure_code'])
        self.assertEqual(len(self.calls),1);self.assertFalse(done['result']['semantic_inference_performed']);self.assertFalse(done['result']['hard_qc_replaced'])
        replay=self.process_http(row);self.assertEqual(replay,done);self.assertEqual(len(self.calls),1)
        self.assertEqual(self.http('GET',self.base+'/'+row['vision_id'])[1],done);self.assertEqual(self.http('GET','/api/session')[1],session)
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(self.pipeline.calls,0)
        public=json.dumps(done)+json.dumps(self.logs);self.assertNotIn(self.raw,public);self.assertNotIn('sk-explicit-synthetic',public)
        self.assertIsNone(self.service.costs.summary(self.project['id'])['records'][0]['actual_cost'])

    def test_non_owner_writes_are_denied_before_body_read_but_scoped_history_and_input_remain_readable(self):
        row=self.create_http()
        for role in ('editor','reviewer','viewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('NO NON-OWNER BODY READ')):
                for route in (self.base,self.base+'/'+row['vision_id']+'/process',self.base+'/'+row['vision_id']+'/cancel'):
                    self.assertEqual(self.http('POST',route,{'role':'owner'})[0],403)
            self.assertEqual(self.http('GET',self.base)[0],200);self.assertEqual(self.http('GET',self.base+'/'+row['vision_id'])[0],200)
            self.assertEqual(self.http('GET',self.base+'/input/'+self.job['id'])[0],200);self.assertEqual(self.http('GET','/api/connections/render-vision')[0],403)
        self.assertEqual(self.calls,[])

    def test_csrf_origin_auth_and_cross_scope_guards_precede_body_or_provider(self):
        for headers,code in (({'X-VF-CSRF':''},403),({'Cookie':''},401),({'Origin':'https://untrusted.invalid'},403)):
            with patch.object(Handler,'read_body',side_effect=AssertionError('NO UNTRUSTED BODY READ')):self.assertEqual(self.http('POST',self.base,{},headers)[0],code)
        self.assertEqual(self.http('GET',self.base+'/input/'+'0'*32)[0],409)
        self.assertEqual(self.http('GET','/api/projects/'+'0'*32+'/render-vision/input/'+self.job['id'])[0],409)
        self.assertEqual(self.calls,[])

    def test_raw_fields_cost_source_scope_configuration_extra_authority_and_secret_refused(self):
        body=self.request().model_dump(mode='json')
        for changes in ({'acknowledged_rendered_frame_analysis':1},{'acknowledged_protocol_mock':1},{'revision':True},
            {'profile_id':'nvip_'+'a'*32},{'max_operation_cost_vnd':500.0},{'max_operation_cost_vnd':'100'},
            {'acknowledged_external_image_analysis':True},{'authority':{}},{'api_key':'NO CLIENT KEY'},{'enabled':True},
            {'expected_render_input_sha256':'0'*64},{'expected_configuration_sha256':'0'*64}):
            self.assertIn(self.http('POST',self.base,{**body,**changes})[0],(400,409),changes)
        self.assertEqual(self.calls,[])

    def test_immutable_idempotency_cancel_bound_history_and_queries_refuse(self):
        row=self.create_http();replay=self.create_http();self.assertEqual(row['vision_id'],replay['vision_id']);self.assertTrue(replay['idempotent_replay'])
        self.assertEqual(self.http('POST',self.base+'/'+row['vision_id']+'/process',{'expected_snapshot_sha256':'0'*64})[0],409)
        status,done,_=self.http('POST',self.base+'/'+row['vision_id']+'/cancel',{'expected_snapshot_sha256':row['snapshot_sha256']});self.assertEqual(status,200);self.assertEqual(done['status'],'cancelled')
        self.assertEqual(self.process_http(row),done);self.assertEqual(self.calls,[])
        for suffix in ('?limit=0','?limit=25&limit=25','?extra=1','?cursor=bad'):
            self.assertEqual(self.http('GET',self.base+suffix)[0],400)
        self.assertEqual(self.http('GET',self.base+'/input/'+self.job['id']+'?extra=1')[0],400)

    def test_late_owner_revoke_retains_original_response_and_blocks_semantic_acceptance(self):
        row=self.create_http();self.mode='revoke';done=self.process_http(row)
        self.assertEqual(done['status'],'review_required');self.assertIsNotNone(done['response']);self.assertIsNone(done['result']);self.assertEqual(len(self.calls),1)
        self.assertEqual(self.service.costs.summary(self.project['id'])['records'][0]['status'],'response_received')

    def test_server_history_without_profile_or_private_key_is_default_disabled_no_request_replay(self):
        row=self.create_http();done=self.process_http(row)
        with LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=NativeAccess(self.verifier,self.workspace)) as reopened:
            self.assertFalse(reopened.render_vision.states()['enabled']);self.assertEqual(reopened.render_vision.states()['profiles'],[])
            self.assertEqual(reopened.render_vision.get(self.project['id'],row['vision_id']),done)
            self.assertFalse(reopened.runner.run_one());self.assertEqual(len(self.calls),1)

    def test_protected_registry_disabled_startup_has_no_decryption_and_configuration_conflicts_fail_closed(self):
        path=Path(self.temp.name)/'public-render-vision.json';registry=RenderVisionRegistry(version=1,workspace_id=self.workspace,profiles=[self.factory.profile])
        path.write_text(registry.model_dump_json(),encoding='utf-8')
        with patch.object(self.vault,'key',side_effect=AssertionError('NO STATUS DECRYPT')):
            with LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=NativeAccess(self.verifier,self.workspace),
                render_vision_registry=path,render_vision_directory=self.vault.directory) as disabled:
                self.assertFalse(disabled.render_vision.states()['enabled']);self.assertEqual(disabled.render_vision.states()['profiles'][0]['status'],'NOT_CONFIGURED')
        for changes in ({'render_vision_enabled':1},{'render_vision_enabled':True},{'render_vision_directory':self.vault.directory},
            {'render_vision_registry':path},{'render_vision_registry':path,'render_vision_directory':self.vault.directory,'render_vision_factories':{}},
            {'render_vision_factories':{self.factory.profile.profile_id:self.factory},'render_vision_directory':self.vault.directory}):
            with self.assertRaises(WorkflowError):LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=NativeAccess(self.verifier,self.workspace),**changes)
        with self.assertRaisesRegex(WorkflowError,'HUMAN_AUTH_REQUIRED'):LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,render_vision_registry=path,render_vision_directory=self.vault.directory)
        live=NativeRenderVisionFactory(self.factory.profile,self.vault,operator_enabled=True)
        with self.assertRaisesRegex(WorkflowError,'MOCK_INJECTION_REQUIRED'):
            LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=NativeAccess(self.verifier,self.workspace),
                render_vision_factories={live.profile.profile_id:live},render_vision_directory=self.vault.directory,render_vision_enabled=True)
        self.assertEqual(self.calls,[])

    def test_runner_start_recovers_claim_without_decryption_retry_or_consent_renewal(self):
        row=self.create_http();claim='nrvc_'+'c'*32
        cost=digest({'project':self.project['id'],'job':self.job['id'],'provider':'openai-vision','operation':'render-vision.'+claim})
        with self.store.transaction() as con:
            con.execute("UPDATE native_render_vision_intents SET status='claimed',claim_id=?,cost_operation_id=? WHERE vision_id=?",(claim,cost,row['vision_id']))
        with patch.object(self.server.runner.thread,'start'),patch.object(self.vault,'key',side_effect=AssertionError('NO STARTUP KEY')):
            self.server.runner.start()
        done=self.service.get(self.project['id'],row['vision_id']);self.assertEqual(done['status'],'outcome_unknown')
        self.assertEqual(done['snapshot']['deadline'],row['snapshot']['deadline']);self.assertEqual(self.calls,[])


if __name__=='__main__':unittest.main()
