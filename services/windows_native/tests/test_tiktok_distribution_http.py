"""Actual owned startup/CSRF HTTP; provider, final and Owner evidence are mocks."""
import json,subprocess,sys,threading,unittest
from datetime import timedelta
from unittest.mock import patch
import httpx
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from app.google_oauth_protocol import GoogleOAuthTokenClient
from services.windows_native.access import NativeAccess
from services.windows_native.contracts import WorkflowError
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer,Handler
from services.windows_native import tiktok_connection as connection
from services.windows_native.tiktok_distribution import DistributionRegistry,DistributionBinding
from services.windows_native.tests import test_tiktok_distribution as admission_fixture
from services.windows_native.tests import test_tiktok_publish_worker as worker_fixture
from services.windows_native.tests import test_access_http as access_fixture
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.observability import Observer

class TikTokDistributionHTTPTests(unittest.TestCase):
    request=access_fixture.NativeAccessHTTPTests.request
    response=worker_fixture.TikTokPublishWorkerTests.response
    def setUp(self):
        self.publish_wires=[];self.mode=None;self.status='PROCESSING_UPLOAD';self.uploaded=None;self.ids=[]
        self.c=admission_fixture.TikTokDistributionAdmissionTests('test_draft_and_dry_run_require_separate_owner_publication_approval');self.c.response=self.response;self.c.setUp()
        c=self.c;self.pipeline=NoProviderPipeline();self.config=Config(data_root=c.root,runtime_root=c.folder/'runtime',secret_file=c.folder/'private'/'absent.env',assemblyai_secret_file=c.folder/'private'/'absent.dpapi',ffmpeg_bin=c.folder/'absent-ffmpeg')
        self.access=NativeAccess(c.verifier,c.workspace)
        self.options={'pipeline':self.pipeline,'start_worker':False,'access':self.access,'tiktok_creator_factories':{c.target.profile_id:c.factory},'tiktok_creator_reads_enabled':True,
            'tiktok_distribution_factories':{c.target.profile_id:c.distribution},'tiktok_distribution_enabled':True,'official_publish_session_directory':c.folder/'private'/'sessions','publishing_capabilities_file':c.capabilities}
        with patch.object(connection,'load_token',side_effect=AssertionError('Startup must not decrypt')):self.server=LocalServer(0,self.config,**self.options)
        self.service=self.server.official_publications;self.service.clock=lambda:c.clock[0];self.server.publications.clock=lambda:c.clock[0]
        self.cookie,session=self.access.login(c.raw);self.csrf=session.csrf;self.base='/api/projects/'+c.project['id']+'/official-publications'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5);self.assertEqual(self.pipeline.calls,0);self.c.tearDown()
    def prepare(self):
        status,value,_=self.request('POST',self.base,self.c.publication_body().model_dump(mode='json'));self.assertEqual(status,200,value);return value
    def action(self,value,name,**changes):
        body={'expected_snapshot_sha256':value['snapshot_sha256'],**changes};status,result,_=self.request('POST',self.base+'/'+value['publication_id']+'/'+name,body);self.assertEqual(status,200,result);return result
    def state(self,value):
        status,result,_=self.request('GET',self.base+'/'+value['publication_id']+'/state');self.assertEqual(status,200,result);return result
    def step(self,value,name='step'):
        return self.action(value,name,expected_dispatch_version=self.state(value)['dispatch']['version'])
    def approve(self,value):return self.action(value,'approve',acknowledged_official_publication=True,valid_for_seconds=900)
    def reopen(self,**changes):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
        self.server=LocalServer(0,self.config,**{**self.options,**changes});self.service=self.server.official_publications
        self.service.clock=lambda:self.c.clock[0];self.server.publications.clock=lambda:self.c.clock[0];self.server.official_publish_queue.clock=lambda:self.c.clock[0]
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def test_owned_startup_binds_same_creator_service_and_signed_private_pipeline(self):
        original=self.server.store.get(self.c.project['id']);runtime=self.request('GET','/api/connections/official-publishing')[1]
        self.assertIs(self.service.tiktok_creators,self.server.tiktok_creators);self.assertIs(self.server.tiktok_creators.publications,self.service)
        self.assertEqual(runtime['profiles'][0]['target']['platform'],'tiktok');self.assertTrue(runtime['profiles'][0]['execution_supported']);self.assertFalse(runtime['profiles'][0]['external_actions_enabled'])
        value=self.prepare();self.assertEqual(value['status'],'awaiting_publish_approval');self.assertEqual(self.publish_wires,[])
        self.approve(value);self.assertEqual(self.step(value)['dispatch']['phase'],'uploading');self.assertEqual(self.step(value)['dispatch']['phase'],'uploaded')
        self.assertEqual(self.step(value,'poll')['status'],'queued');self.status='PUBLISH_COMPLETE';done=self.step(value,'poll');self.assertEqual(done['status'],'completed')
        self.assertTrue(done['mock_publication_complete']);self.assertFalse(done['published']);self.assertIsNone(done['receipt']['remote_post_id']);self.assertEqual(done['receipt']['public_post_ids'],[])
        self.assertEqual(self.server.store.get(original['id']),original);self.assertEqual(sum(x['path'].endswith('/init/') for x in self.publish_wires),1);self.assertEqual(sum(x['method']=='PUT' for x in self.publish_wires),1)
        self.assertNotIn(worker_fixture.UPLOAD_TOKEN,json.dumps([runtime,done,self.state(value)]));self.assertFalse(self.server.official_publish_queue.enabled)
    def test_creator_reads_and_default_off_distribution_never_grant_publication(self):
        options={**self.options,'tiktok_distribution_enabled':False}
        with patch.object(connection,'load_token',side_effect=AssertionError('Disabled startup must not decrypt')):
            server=LocalServer(0,self.config,**options)
            try:
                state=server.official_publications.states()['profiles'][0];self.assertEqual(state['status'],'NOT_CONFIGURED');self.assertFalse(any(state['gates'].values()));self.assertFalse(state['external_actions_enabled'])
                self.assertTrue(server.tiktok_creators.enabled);self.assertFalse(server.official_publish_queue.enabled)
            finally:server.server_close()
        self.assertEqual(self.publish_wires,[])
    def test_queue_runtime_accepts_tiktok_without_youtube_configuration(self):
        server=LocalServer(0,self.config,**{**self.options,'official_publish_queue_enabled':True})
        try:self.assertTrue(server.official_publish_queue.enabled);self.assertEqual(set(server.official_publications.factories),{self.c.target.profile_id})
        finally:server.server_close()
        self.assertEqual(self.publish_wires,[])
    def test_signed_queue_runs_original_tiktok_steps_and_logs_actual_provider(self):
        from services.windows_native.official_publication_queue import QueueCreate
        self.reopen(official_publish_queue_enabled=True);records=[];self.server.runner.observer=Observer(records.append)
        value=self.prepare();self.approve(value);queue_base=self.base+'/'+value['publication_id']+'/queue'
        body=QueueCreate(expected_snapshot_sha256=value['snapshot_sha256'],expected_dispatch_version=self.state(value)['dispatch']['version'],
            acknowledged_background_steps=True,max_steps=10,interval_seconds=30,start_at=self.c.clock[0],deadline=self.c.clock[0]+timedelta(seconds=600),request_key='explicit-tiktok-http-queue-fixture').model_dump(mode='json')
        status,plan,_=self.request('POST',queue_base,body);self.assertEqual(status,200,plan);self.assertEqual(self.publish_wires,[])
        for i in range(4):
            if i==3:self.status='PUBLISH_COMPLETE'
            self.assertTrue(self.server.runner.run_one());self.assertFalse(self.server.runner.run_one());self.c.clock[0]+=timedelta(seconds=30)
        status,done,_=self.request('GET',queue_base+'/'+plan['plan_id']);self.assertEqual(status,200);self.assertEqual(done['status'],'completed');self.assertEqual(done['step_count'],4)
        steps=[json.loads(raw) for raw in records if json.loads(raw)['stage']=='official_publish_queue'];self.assertEqual(len(steps),4)
        self.assertTrue(all(x['provider']=='tiktok-content-posting-api' and x['job_id']==plan['plan_id'] for x in steps));self.assertNotIn(worker_fixture.UPLOAD_TOKEN,json.dumps(records))
        self.assertEqual(sum(x['path'].endswith('/init/') for x in self.publish_wires),1);self.assertEqual(sum(x['method']=='PUT' for x in self.publish_wires),1)
    def test_cold_server_reads_original_history_without_configuration_or_private_load(self):
        value=self.prepare();self.approve(value);self.step(value);self.step(value);self.status='PUBLISH_COMPLETE';done=self.step(value,'poll');dispatch=self.state(value);wire_count=len(self.publish_wires)
        with patch.object(connection,'load_token',side_effect=AssertionError('Cold history must not decrypt')):
            server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.access,publishing_capabilities_file=self.c.capabilities)
            try:
                self.assertEqual(server.official_publications.get(self.c.project['id'],value['publication_id']),done);self.assertEqual(server.official_publications.state(self.c.project['id'],value['publication_id']),dispatch)
                self.assertEqual(server.official_publications.states()['profiles'],[]);self.assertFalse(server.official_publish_queue.enabled);self.assertFalse(server.runner.run_one())
            finally:server.server_close()
        self.assertEqual(len(self.publish_wires),wire_count)
    def test_runtime_capabilities_drift_blocks_grant_before_any_provider(self):
        value=self.prepare();self.c.capabilities.write_bytes(self.c.capabilities.read_bytes()+b'\n')
        status,_,_=self.request('POST',self.base+'/'+value['publication_id']+'/approve',{'expected_snapshot_sha256':value['snapshot_sha256'],'acknowledged_official_publication':True,'valid_for_seconds':900})
        self.assertEqual(status,409);self.assertEqual(self.publish_wires,[])
    def test_cli_exposes_independent_default_off_distribution_and_capabilities_flags(self):
        result=subprocess.run([sys.executable,'-X','utf8','-m','services.windows_native.server','--help'],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        for flag in ('--tiktok-publishing-registry','--enable-tiktok-creator-reads','--tiktok-distribution-registry','--enable-tiktok-distribution','--publishing-capabilities-file','--enable-official-publishing'):
            self.assertIn(flag,result.stdout)
        self.assertEqual(self.publish_wires,[])
    def test_empty_google_oauth_runtime_and_tiktok_can_coexist_without_binding_mix(self):
        client=GoogleOAuthTokenClient(transport=httpx.MockTransport(lambda _:(_ for _ in ()).throw(AssertionError('No OAuth wire'))))
        with patch.object(connection,'load_token',side_effect=AssertionError('No startup decrypt')):
            server=LocalServer(0,self.config,**{**self.options,'google_oauth_slots':{},'google_oauth_client':client})
            try:self.assertIsNotNone(server.google_oauth);self.assertIs(server.official_publications.factories[self.c.target.profile_id],self.c.distribution)
            finally:server.server_close()
    def test_raw_flags_protected_prerequisites_and_wrong_mock_links_fail_before_secret(self):
        for changes in ({'tiktok_distribution_enabled':1},{'tiktok_creator_reads_enabled':False},{'official_publish_session_directory':None},
            {'tiktok_distribution_registry':self.c.folder/'private'/'unused.json'},{'tiktok_creator_factories':{}},{'tiktok_distribution_factories':{self.c.target.profile_id:self.c.factory}}):
            with self.subTest(changes=list(changes)),patch.object(connection,'load_token',side_effect=AssertionError('Invalid startup must not decrypt')):
                with self.assertRaises(WorkflowError):LocalServer(0,self.config,**{**self.options,**changes})
        self.assertEqual(self.publish_wires,[])
    def test_capabilities_configuration_is_protected_and_does_not_enable_any_gate(self):
        self.assertEqual(self.server.publications.capabilities_path,self.c.capabilities)
        for change in ({'publishing_capabilities_file':self.c.root/'inside-state.json'},{'publishing_capabilities_file':self.c.folder/'private'/'absent.json'},{'access':None}):
            with self.subTest(change=list(change)),self.assertRaises(WorkflowError):LocalServer(0,self.config,**{**self.options,**change})
        self.assertEqual(self.publish_wires,[])
    def test_missing_owner_or_csrf_rejects_all_publication_actions_before_body(self):
        value=self.prepare();self.approve(value)
        for role in ('viewer','editor','reviewer'):
            raw,data=human_fixture(role,workspace=self.c.workspace);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.c.workspace)
            access.bind_root(self.c.root);self.server.access=access;self.cookie,session=access.login(raw);self.csrf=session.csrf
            with patch.object(Handler,'read_body',side_effect=AssertionError('Forbidden body must not be read')):
                for suffix in ('','/'+value['publication_id']+'/approve','/'+value['publication_id']+'/renew','/'+value['publication_id']+'/revoke','/'+value['publication_id']+'/cancel','/'+value['publication_id']+'/step','/'+value['publication_id']+'/poll'):
                    self.assertEqual(self.request('POST',self.base+suffix,{})[0],403)
            self.assertEqual(self.request('GET','/api/connections/official-publishing')[0],403)
        self.server.access=self.access;self.cookie,session=self.access.login(self.c.raw);self.csrf=session.csrf
        with patch.object(Handler,'read_body',side_effect=AssertionError('Missing CSRF body must not be read')):self.assertEqual(self.request('POST',self.base+'/'+value['publication_id']+'/step',{},headers={'X-VF-CSRF':''})[0],403)
        self.assertEqual(self.publish_wires,[])
    def test_tag_scope_and_private_inputs_do_not_override_original_draft(self):
        body=self.c.publication_body().model_dump(mode='json')
        for change in ({'schema_version':'unknown'},{'metadata':{'title':'Override'}},{'upload_url':worker_fixture.URI},{'token':'EXPLICIT_NEVER_READ'},{'creator_draft_id':'ntpd_'+'f'*32}):
            self.assertIn(self.request('POST',self.base,body|change)[0],(400,404,409))
        value=self.prepare();other=self.server.store.create('Foreign','No providers')
        self.assertEqual(self.request('GET','/api/projects/'+other['id']+'/official-publications/'+value['publication_id'])[0],404);self.assertEqual(self.publish_wires,[])
    def test_live_registry_can_be_loaded_default_off_without_decryption_or_network(self):
        c=self.c;creator_path=c.folder/'private'/'creator-registry.json';creator_path.write_text(json.dumps(connection.Registry(version=1,workspace_id=c.workspace,bindings=[c.binding]).model_dump(mode='json')),encoding='utf8')
        # The non-mock connection receives its own configuration fingerprint.
        real=connection.load(creator_path,c.root,c.workspace,owner_read_enabled=True)
        path=c.folder/'private'/'distribution-registry.json';path.write_text(json.dumps(DistributionRegistry(version=1,workspace_id=c.workspace,bindings=[DistributionBinding(profile_id=c.target.profile_id,
            expected_creator_configuration_sha256=real[c.target.profile_id].sha256,gates=c.distribution.gates)]).model_dump(mode='json')),encoding='utf8')
        options={**self.options,'tiktok_creator_factories':None,'tiktok_publishing_registry':creator_path,'tiktok_distribution_factories':None,'tiktok_distribution_registry':path,'tiktok_distribution_enabled':False}
        with patch.object(connection,'load_token',side_effect=AssertionError('Protected registry startup must not decrypt')):
            server=LocalServer(0,self.config,**options)
            try:
                state=server.official_publications.states()['profiles'][0];self.assertFalse(state['mock']);self.assertFalse(state['external_actions_enabled']);self.assertEqual(state['status'],'NOT_CONFIGURED')
                self.assertFalse(server.official_publications.factories[c.target.profile_id].client.network_enabled)
            finally:server.server_close()

if __name__=='__main__':unittest.main()
