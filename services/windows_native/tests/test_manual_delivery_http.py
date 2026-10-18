"""Signed loopback API with actual MP4/package download; no social transport."""
import http.client
import json
import threading
import unittest
from unittest.mock import patch
from urllib.parse import quote
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer,Handler
from services.windows_native.tests import test_manual_delivery as fixture
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests.test_phase10_http import NoProviderPipeline


class ManualDeliveryHTTPTests(unittest.TestCase):
    setUpClass=classmethod(fixture.ManualDeliveryTests.setUpClass.__func__)
    tearDownClass=classmethod(fixture.ManualDeliveryTests.tearDownClass.__func__)
    request=fixture.ManualDeliveryTests.request

    def setUp(self):
        fixture.ManualDeliveryTests.setUp(self)
        raw,data=human_fixture('owner',workspace='wsp_native_local')
        verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400)
        self.pipeline=NoProviderPipeline()
        self.server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=NativeAccess(verifier,'wsp_native_local'))
        self.cookie,session=self.server.access.login(raw);self.csrf=session.csrf
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='/api/projects/'+self.project['id']+'/exports'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();fixture.ManualDeliveryTests.tearDown(self)

    def http(self,method,path,body=None,headers=None):
        client=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=90)
        client.request(method,path,body=body if isinstance(body,bytes) else json.dumps(body) if body is not None else None,
            headers={'Content-Type':'application/json','Cookie':'vf_native_session='+self.cookie,'X-VF-CSRF':self.csrf,**(headers or {})})
        response=client.getresponse();raw=response.read();head=dict(response.getheaders());status=response.status;client.close()
        return status,json.loads(raw) if head.get('Content-Type','').startswith('application/json') else raw,head

    def account(self,role):
        raw,data=human_fixture(role,workspace='wsp_native_local')
        verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400)
        access=NativeAccess(verifier,'wsp_native_local');access.bind_root(self.root);self.server.access=access
        self.cookie,session=access.login(raw);self.csrf=session.csrf

    def test_export_caption_history_download_and_capabilities_use_real_bytes(self):
        code,session,_=self.http('GET','/api/session');self.assertEqual(code,200)
        self.assertTrue(session['capabilities']['native_manual_delivery'])
        copybase='/api/projects/'+self.project['id']+'/delivery-copy'
        code,saved,_=self.http('POST',copybase,{'expected_version':0,'request_key':'explicit-http-caption-key','variants':{'master':{'caption':'Cần Giờ · đăng thủ công'}}})
        self.assertEqual(code,200,saved)
        body=self.request(cover=False,filename='bản cuối.mp4',caption_version=saved['version']).model_dump(mode='json')
        code,value,head=self.http('POST',self.base,body);self.assertEqual(code,200,value)
        self.assertEqual(head['Cache-Control'],'no-store');self.assertFalse(value['externally_posted'])
        self.assertEqual(self.http('POST',self.base,body)[1]['export_id'],value['export_id'])
        self.assertEqual(len(self.http('GET',self.base)[1]['items']),1)
        url=self.base+'/'+value['export_id']+'/files/'
        code,video,head=self.http('GET',url+quote('bản cuối.mp4'));self.assertEqual(code,200)
        import hashlib
        self.assertEqual(hashlib.sha256(video).hexdigest(),self.video_hash)
        self.assertIn('attachment;',head['Content-Disposition'])
        self.assertTrue(self.http('GET',url+'delivery-package.zip')[1].startswith(b'PK'))
        self.assertIn('Cần Giờ',self.http('GET',url+'caption.txt')[1].decode())
        self.assertEqual(self.pipeline.calls,0)

    def test_roles_csrf_origin_and_strict_fields_fail_before_export(self):
        body=self.request(cover=False).model_dump(mode='json')
        for headers,expected in [({'Cookie':''},401),({'X-VF-CSRF':''},403),({'Origin':'https://untrusted.invalid'},403)]:
            with patch.object(Handler,'read_body',side_effect=AssertionError('No untrusted body')):
                self.assertEqual(self.http('POST',self.base,body,headers)[0],expected)
        for role in ('viewer','reviewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('No reader write body')):
                self.assertEqual(self.http('POST',self.base,body)[0],403)
            self.assertEqual(self.http('GET',self.base)[0],200)
        self.account('editor')
        self.assertEqual(self.http('POST',self.base,{**body,'published':True})[0],400)
        self.assertEqual(self.http('POST',self.base,{**body,'revision':True})[0],400)
        self.assertEqual(self.http('GET',self.base+'?extra=1')[0],400)
        self.assertEqual(self.http('POST',self.base,body)[0],200)
        self.assertEqual(self.pipeline.calls,0)

    def test_new_module_served_and_folder_action_only_opens_verified_local_export(self):
        self.assertEqual(self.http('GET','/native-manual-delivery.mjs')[0],200)
        code,value,_=self.http('POST',self.base,self.request(cover=False).model_dump(mode='json'));self.assertEqual(code,200,value)
        import os
        if os.name=='nt':
            with patch('services.windows_native.manual_delivery_routes.os.startfile') as opened:
                code,value,_=self.http('POST',self.base+'/'+value['export_id']+'/open-folder',{})
                self.assertEqual(code,200,value);self.assertTrue(value['opened']);opened.assert_called_once()
        self.assertEqual(self.pipeline.calls,0)

    def test_cover_upload_is_binary_magic_checked_private_and_keeps_video_approval(self):
        import io
        from PIL import Image
        image=io.BytesIO();Image.new('RGB',(320,400),'#246b83').save(image,format='PNG');raw=image.getvalue()
        before=self.store.get(self.project['id']);base='/api/projects/'+self.project['id']+'/delivery-covers'
        headers={'Content-Type':'image/png','X-VF-Revision':str(self.project['revision']),'X-VF-Filename':'cover.jpg'}
        code,uploaded,_=self.http('POST',base,raw,headers);self.assertEqual(code,200,uploaded)
        self.assertEqual(uploaded['content_type'],'image/png');self.assertEqual(uploaded['rights_status'],'unknown')
        code,data,head=self.http('GET',base+'/'+uploaded['cover_id']+'/image');self.assertEqual(code,200);self.assertEqual(data,raw);self.assertEqual(head['Content-Type'],'image/png')
        self.assertTrue(self.http('POST',base,raw,headers)[1]['idempotent_replay'])
        self.assertEqual(self.http('POST',base,b'<svg>not a PNG</svg>',headers)[0],400)
        self.assertEqual(self.store.get(self.project['id']),before)
        self.account('viewer');self.assertEqual(self.http('POST',base,raw,headers)[0],403)
        self.assertEqual(self.http('GET',base)[0],200)

    def test_history_resume_and_abandon_are_scoped_and_never_cancel_ready_export(self):
        body=self.request(cover=False).model_dump(mode='json');code,done,_=self.http('POST',self.base,body);self.assertEqual(code,200,done)
        with self.store.transaction() as con:con.execute("UPDATE native_manual_exports SET status='preparing' WHERE export_id=?",(done['export_id'],))
        code,resumed,_=self.http('POST',self.base+'/'+done['export_id']+'/resume',{});self.assertEqual(code,200,resumed);self.assertEqual(resumed['export_id'],done['export_id'])
        self.assertEqual(self.http('POST',self.base+'/'+done['export_id']+'/abandon',{})[0],409)
        with patch('services.windows_native.manual_delivery.shutil.copyfile',side_effect=OSError('owned local disk failure')):
            self.assertEqual(self.http('POST',self.base,{**body,'request_key':'explicit-http-abandon-failed-key'})[0],503)
        failed=next(r for r in self.http('GET',self.base)[1]['items'] if r['status']=='failed')
        self.assertEqual(self.http('POST',self.base+'/'+failed['export_id']+'/abandon',{})[1]['status'],'abandoned')
        self.assertEqual(self.http('POST',self.base+'/'+failed['export_id']+'/resume',{})[0],409)
        self.assertEqual(self.pipeline.calls,0)
