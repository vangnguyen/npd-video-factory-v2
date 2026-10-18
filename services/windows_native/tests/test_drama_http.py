"""Signed Native casting/library APIs, no inference or external publishing."""
import copy,http.client,json,threading,unittest
from unittest.mock import patch
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer,Handler
from services.windows_native.tests import test_dialogue_runtime as fixture
from services.windows_native.tests.test_human_identity import fixture as human
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.tests.test_voice_library import definition
from services.windows_native.contracts import digest

class DramaHTTPTests(unittest.TestCase):
    compile=fixture.DialogueRuntimeTests.compile
    cast=fixture.DialogueRuntimeTests.cast
    save_cast=fixture.DialogueRuntimeTests.save_cast
    def setUp(self):
        fixture.DialogueRuntimeTests.setUp(self);self.pipeline=NoProviderPipeline()
        raw,data=human('owner',workspace='wsp_native_local');access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),'wsp_native_local')
        self.server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=access)
        self.cookie,session=access.login(raw);self.csrf=session.csrf;self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='/api/projects/'+self.project['id']+'/drama-casting'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.assertEqual(self.pipeline.calls,0);self.assertEqual(self.adapter.calls,[])
        fixture.DialogueRuntimeTests.tearDown(self)
    def http(self,method,path,body=None,headers=None):
        client=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=15)
        client.request(method,path,body=json.dumps(body) if body is not None else None,headers={'Content-Type':'application/json','Cookie':'vf_native_session='+self.cookie,'X-VF-CSRF':self.csrf,**(headers or {})})
        response=client.getresponse();raw=response.read();meta=dict(response.getheaders());status=response.status;client.close()
        return status,json.loads(raw) if meta.get('Content-Type','').startswith('application/json') else raw,meta
    def account(self,role):
        raw,data=human(role,workspace='wsp_native_local');access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),'wsp_native_local');access.bind_root(self.root)
        self.server.access=access;self.cookie,session=access.login(raw);self.csrf=session.csrf
    def cast_body(self,**changes):
        project=self.store.get(self.project['id'])
        return {'revision':project['revision'],'expected_version':project['document']['drama_casting']['version'],'request_key':'explicit-http-cast-'+str(project['revision']),
            'configuration':self.configuration,**changes}

    def test_read_catalog_library_casting_and_immutable_voice_versions(self):
        code,value,_=self.http('GET','/api/session');self.assertEqual(code,200);self.assertTrue(value['capabilities']['native_drama_voice_casting'])
        code,values,head=self.http('GET','/api/voice-library');self.assertEqual(code,200);self.assertEqual(len(values['items']),3);self.assertEqual(head['Cache-Control'],'no-store')
        code,value,_=self.http('GET',self.base);self.assertEqual(code,200,value);self.assertTrue(value['compiled_current']);self.assertFalse(value['human_voice_uat_complete'])
        code,catalog,_=self.http('GET','/api/voice-library/presets');self.assertEqual(code,200);self.assertIsNone(catalog['default_voice']);self.assertEqual(catalog['inference_calls'],0)
        body={'request_key':'explicit-http-create-voice','definition':definition(display_name='<script>literal</script>')}
        code,created,_=self.http('POST','/api/voice-library',body);self.assertEqual(code,200,created);self.assertEqual(created['definition']['rights_status'],'unknown')
        path='/api/voice-library/'+created['voice_id'];code,updated,_=self.http('POST',path,{'expected_version':1,'request_key':'explicit-http-update-voice','definition':{**created['definition'],'display_name':'New name'}})
        self.assertEqual(code,200,updated);self.assertEqual(updated['version'],2);self.assertEqual(self.http('GET',path)[1]['version'],2)
        replay=self.http('POST','/api/voice-library',body)[1];self.assertEqual(replay['version'],1);self.assertFalse(replay['current'])

    def test_role_cookie_csrf_and_origin_guard_runs_before_mutation_body(self):
        body=self.cast_body()
        for headers,expected in (({'Cookie':''},401),({'X-VF-CSRF':''},403),({'Origin':'https://untrusted.invalid'},403)):
            with patch.object(Handler,'read_body',side_effect=AssertionError('Untrusted body forbidden')):self.assertEqual(self.http('POST',self.base,body,headers)[0],expected)
        for role in ('viewer','reviewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Read-only body forbidden')):
                for path in (self.base,self.base+'/compile',self.base+'/takes',self.base+'/series-save',self.base+'/series-apply','/api/voice-library'):
                    self.assertEqual(self.http('POST',path,{})[0],403,path)
            self.assertEqual(self.http('GET',self.base)[0],200)
        self.account('editor')
        with patch.object(Handler,'read_body',side_effect=AssertionError('Editor cannot assert global voice rights')):self.assertEqual(self.http('POST','/api/voice-library',{})[0],403)
        self.assertEqual(self.http('POST',self.base,body)[0],200)

    def test_explicit_dialogue_save_updates_same_canonical_script_and_invalidates_old_approval(self):
        configuration=copy.deepcopy(self.configuration);configuration['lines'][0]['text']='Xin chào bạn.'
        before=self.store.shot_view(self.project['id']);body=self.cast_body(configuration=configuration,sync_canonical_script=True)
        code,saved,_=self.http('POST',self.base,body);self.assertEqual(code,200,saved)
        after=self.store.shot_view(self.project['id']);self.assertEqual(after['document']['proposal']['narration'],'Xin chào bạn. Cảm ơn.')
        self.assertEqual(after['shot_timeline']['shots'][0]['subtitle'],'Xin chào bạn.');self.assertGreater(after['shot_timeline']['version'],before['shot_timeline']['version'])
        for left,right in zip(before['shot_timeline']['shots'],after['shot_timeline']['shots']):
            for key in ('asset_id','duration','crop_strategy','motion'):self.assertEqual(left[key],right[key])
        self.assertIsNone(after['approval']);self.assertTrue(self.http('POST',self.base,body)[1]['idempotent_replay'])
        code,compiled,_=self.http('POST',self.base+'/compile',{'revision':after['revision'],'expected_version':1,'request_key':'explicit-http-compile-new-dialogue'})
        self.assertEqual(code,200,compiled);self.assertFalse(compiled['human_approval_granted']);self.assertTrue(self.http('GET',self.base)[1]['compiled_current'])

    def test_take_and_series_actions_retain_exact_retry_and_never_dispatch(self):
        project=self.store.get(self.project['id']);body={'revision':project['revision'],'expected_casting_sha256':project['document']['drama_casting']['sha256'],
            'request_key':'explicit-http-take-request','line_ids':[self.configuration['lines'][0]['line_id']]}
        code,take,_=self.http('POST',self.base+'/takes',body);self.assertEqual(code,200,take);self.assertEqual(self.http('POST',self.base+'/takes',body)[1]['takes'],take['takes'])
        project=self.store.get(self.project['id']);body={'revision':project['revision'],'expected_version':0,'name':'Fixture series','request_key':'explicit-http-series-save'}
        code,value,_=self.http('POST',self.base+'/series-save',body);self.assertEqual(code,200,value);series=value['series']
        self.assertEqual(self.http('GET','/api/drama-series')[1]['items'],[series]);self.assertEqual(series['configuration']['lines'],[])
        other=self.store.create('Another fixture','No external effects');code,applied,_=self.http('POST','/api/projects/'+other['id']+'/drama-casting/series-apply',
            {'revision':other['revision'],'request_key':'explicit-http-series-apply','series_id':series['series_id'],'version':series['version'],'expected_sha256':series['sha256']})
        self.assertEqual(code,200,applied);self.assertFalse(applied['approval_inherited'])

    def test_strict_unknown_fields_queries_and_stale_bindings_do_not_mutate_project(self):
        before=self.store.get(self.project['id'])
        for changes in ({'revision':True},{'published':True},{'sync_canonical_script':'yes'},{'expected_version':0}):
            self.assertIn(self.http('POST',self.base,self.cast_body(**changes))[0],(400,409));self.assertEqual(self.store.get(self.project['id']),before)
        for path in (self.base,'/api/voice-library','/api/voice-library/presets','/api/drama-series'):
            self.assertEqual(self.http('GET',path+'?unexpected=1')[0],400)
        self.assertEqual(self.http('POST',self.base+'/compile',{'revision':before['revision'],'expected_version':1,'request_key':'explicit-http-injected-compile','provider':'fake'})[0],400)

    def test_unconfigured_provider_blocks_compile_without_using_legacy_voice(self):
        with patch('services.windows_native.drama_routes.providers_for',return_value={}):
            project=self.store.get(self.project['id']);code,value,_=self.http('POST',self.base+'/compile',{'revision':project['revision'],'expected_version':1,'request_key':'explicit-http-no-provider-compile'})
            self.assertEqual(code,400,value);self.assertEqual(value['code'],'DRAMA_DELIVERY_PLAN_NOT_READY')
            self.assertFalse(self.http('GET',self.base)[1]['compiled_current'])

    def test_conversion_clears_legacy_narrator_policy_only_with_explicit_choice(self):
        from services.windows_native.voice_quality import catalog
        project=self.store.get(self.project['id']);self.store.set_voice_quality(project['id'],project['revision'],catalog()['choices'][0]['id'])
        body=self.cast_body();code,record,_=self.http('POST',self.base,body);self.assertEqual(code,200,record)
        self.assertIn('voice_quality',self.store.get(project['id'])['document'])
        body=self.cast_body(clear_legacy_voice_policy=True);code,record,_=self.http('POST',self.base,body);self.assertEqual(code,200,record)
        self.assertNotIn('voice_quality',self.store.get(project['id'])['document'])
        # The immutable project_versions rows retain the prior policy.
        with self.store.transaction() as con:self.assertGreater(con.execute("SELECT count(*) FROM project_versions WHERE project_id=? AND json_type(document,'$.voice_quality') IS NOT NULL",(project['id'],)).fetchone()[0],0)

    def test_library_revocation_marks_saved_approval_stale_without_rewriting_project_history(self):
        project=self.store.get(self.project['id']);self.store.approve(project['id'],project['revision'],'AUTOMATED HTTP FIXTURE NOT OWNER',True,purpose='narration')
        before=self.store.get(project['id']);voice=self.voices[0]
        code,value,_=self.http('POST','/api/voice-library/'+voice['voice_id'],{'expected_version':1,'request_key':'explicit-http-library-revoke',
            'definition':{**voice['definition'],'rights_status':'blocked'}});self.assertEqual(code,200,value)
        code,after,_=self.http('GET','/api/projects/'+project['id']);self.assertEqual(code,200,after)
        self.assertFalse(after['drama_voice_binding']['current']);self.assertEqual(after['revision'],before['revision']);self.assertEqual(after['approval'],before['approval'])
        code,result,_=self.http('POST','/api/projects/'+project['id']+'/jobs',{'revision':before['revision'],'kind':'narration','request_key':'explicit-http-block-stale-narration'})
        self.assertEqual(code,409,result);self.assertEqual(result['code'],'DRAMA_VOICE_BINDING_CHANGED');self.assertEqual(self.store.get(project['id'])['jobs'],[])
