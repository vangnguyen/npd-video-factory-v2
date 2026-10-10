"""Actual signed loopback intake and real local media; fixture human identity only."""
import copy,hashlib,http.client,json,os,threading,unittest
from pathlib import Path
from unittest.mock import patch
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer,Handler
from services.windows_native.store import Store
from services.windows_native.contracts import file_sha
from services.windows_native.multipart_ingestion import CHUNK_BYTES
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests import test_access_http as access_fixture,test_multipart_ingestion as intake_fixture

class MultipartHTTPTests(unittest.TestCase):
    parent_setup=intake_fixture.MultipartIngestionTests.setUp
    parent_teardown=intake_fixture.MultipartIngestionTests.tearDown
    body=intake_fixture.MultipartIngestionTests.body
    assets=intake_fixture.MultipartIngestionTests.assets
    request=access_fixture.NativeAccessHTTPTests.request
    workspace='wsp_multipart_fixture'
    def setUp(self):
        self.parent_setup();self.start_server();self.base='/api/projects/'+self.project['id']+'/uploads'
    def start_server(self):
        raw,data=human_fixture('editor',workspace=self.workspace)
        access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.workspace)
        self.server=LocalServer(0,self.config,start_worker=False,access=access)
        self.cookie,session=access.login(raw);self.csrf=session.csrf
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def stop_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
    def tearDown(self):
        self.stop_server();self.parent_teardown()
    def account(self,role):
        raw,data=human_fixture(role,workspace=self.workspace)
        access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.workspace)
        access.bind_root(self.root);self.server.access=access;self.cookie,session=access.login(raw);self.csrf=session.csrf
    def binary(self,session,raw,offset=0,extra=None):
        part=raw[offset:offset+CHUNK_BYTES]
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        conn.request('POST',self.base+'/'+session['upload_id']+'/chunks',part,headers={
            'Cookie':'vf_native_session='+self.cookie,'X-VF-CSRF':self.csrf,'Content-Type':'application/octet-stream',
            'X-VF-Offset':str(offset),'X-VF-SHA256':hashlib.sha256(part).hexdigest(),**(extra or {})})
        response=conn.getresponse();headers=dict(response.getheaders());value=json.loads(response.read());conn.close()
        return response.status,value,headers
    def create(self,raw,kind='subtitle',mime='application/x-subrip',**kw):
        body=self.body(raw,kind,mime,expected_sha256=None,**kw);status,value,headers=self.request('POST',self.base,body)
        self.assertEqual(status,200,value);self.assertEqual(headers['Cache-Control'],'no-store');return value
    def finish(self,session):
        status,value,headers=self.request('POST',self.base+'/'+session['upload_id']+'/complete',{
            'revision':self.server.store.get(self.project['id'])['revision'],'expected_parts_sha256':session['parts_sha256']})
        self.assertEqual(status,200,value);self.assertEqual(headers['Cache-Control'],'no-store');return value
    def test_all_six_signed_intakes_reopen_bytes_deduplicate_and_keep_unknown_rights(self):
        records=[]
        for kind,mime,raw in self.assets():
            before=self.server.store.get(self.project['id']);session=self.create(raw,kind,mime);initial=copy.deepcopy(session)
            status,sent,headers=self.binary(session,raw);self.assertEqual(status,200,sent);self.assertEqual(headers['Cache-Control'],'no-store')
            self.stop_server();self.start_server();self.store=self.server.store
            status,resumed,headers=self.request('GET',self.base+'/'+session['upload_id']);self.assertEqual(status,200,resumed)
            self.assertEqual(resumed['parts'],sent['parts']);self.assertEqual(resumed['received_bytes'],len(raw));done=self.finish(resumed)
            self.assertFalse(done['result']['duplicate']);self.assertFalse(done['publishing_enabled']);asset=done['result']['asset']
            self.assertEqual(asset['source_sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(asset['rights_status'],'unknown')
            self.assertEqual((self.root/'originals'/asset['original_id']).read_bytes(),raw)
            self.assertEqual(done['result']['attached_revision'],before['revision']+1)
            status,file_bytes,file_headers=self.request('GET','/api/assets/'+asset['id']+'/file');self.assertEqual(status,200)
            self.assertEqual(hashlib.sha256(file_bytes).hexdigest(),asset['sha256']);self.assertEqual(file_headers['Cache-Control'],'no-store')
            duplicate=self.create(raw,kind,mime);status,duplicate,_=self.binary(duplicate,raw);self.assertEqual(status,200);duplicate=self.finish(duplicate)
            self.assertTrue(duplicate['result']['duplicate']);self.assertEqual(duplicate['result']['asset'],asset)
            self.assertEqual(self.server.store.get(self.project['id'])['revision'],before['revision']+1)
            records.append({'kind':kind,'source_hex':raw.hex(),'initial':initial,'received':resumed,'completed':done,'duplicate':duplicate})
        self.assertEqual(len(self.server.store.get(self.project['id'])['document']['assets']),6)
        for kind,total in [('all',6),('visual',3),('audio',2),('subtitle',1)]:
            status,listing,_=self.request('GET','/api/assets?kind='+kind);self.assertEqual(status,200);self.assertEqual(listing['total'],total)
        path=os.environ.get('VF_MULTIPART_HTTP_EVIDENCE')
        if path:
            with Path(path).open('x',encoding='utf-8',newline='\n') as output:
                json.dump({'schema_version':'native-multipart-owned-http-fixture-v1','fixture_human':True,'provider_calls':0,
                    'browser_rendered':False,'owner_uat':False,'records':records},output,ensure_ascii=False,indent=2);output.write('\n')
    def test_roles_and_csrf_are_enforced_before_JSON_and_chunk_reads(self):
        raw=b'1\n00:00:00,000 --> 00:00:01,000\nWords\n';session=self.create(raw)
        for role in ('viewer','reviewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Forbidden JSON body consumed')):
                for path in (self.base,self.base+'/'+session['upload_id']+'/complete',self.base+'/'+session['upload_id']+'/cancel'):
                    self.assertEqual(self.request('POST',path,{})[0],403)
            self.assertEqual(self.binary(session,raw)[0],403);self.assertEqual(self.request('GET',self.base)[0],200)
        self.account('editor');self.assertEqual(self.binary(session,raw,extra={'X-VF-CSRF':''})[0],403)
        self.assertEqual(self.request('GET',self.base+'/'+session['upload_id'])[1]['received_bytes'],0)
        self.assertEqual(self.binary(session,raw)[0],200)
    def test_bad_chunk_headers_checksum_offsets_and_queries_do_not_attach(self):
        raw=b'x'*(CHUNK_BYTES+31);session=self.create(raw,'video','video/mp4')
        for changes in ({'Content-Type':'video/mp4'},{'X-VF-Offset':'-1'},{'X-VF-SHA256':'a'*64},{'X-VF-Offset':'1048576'}):
            self.assertIn(self.binary(session,raw,extra=changes)[0],(400,409))
        self.assertEqual(self.request('GET',self.base+'/'+session['upload_id'])[1]['received_bytes'],0)
        status,sent,_=self.binary(session,raw);self.assertEqual(status,200)
        replay=self.binary(session,raw)[1];self.assertTrue(replay['idempotent_replay']);self.assertEqual(replay['parts'],sent['parts'])
        self.assertEqual(self.request('GET',self.base+'?token=unused')[0],400)
        self.assertEqual(self.request('GET',self.base+'/nup_'+'a'*32)[0],404)
        other=self.server.store.create('Other owned project','','media')
        self.assertEqual(self.request('GET','/api/projects/'+other['id']+'/uploads/'+session['upload_id'])[0],404)
        self.assertEqual(self.server.store.get(self.project['id'])['document']['assets'],[])
    def test_MAGIC_and_declared_rights_do_not_become_publish_authority(self):
        raw=b'This is not an image';session=self.create(raw,'image','image/png');sent=self.binary(session,raw)[1]
        status,value,_=self.request('POST',self.base+'/'+session['upload_id']+'/complete',{
            'revision':self.project['revision'],'expected_parts_sha256':sent['parts_sha256']})
        self.assertEqual(status,400,value);self.assertEqual(self.request('GET',self.base+'/'+session['upload_id'])[1]['status'],'needs_attention')
        for changes in ({'rights_confirmed':1},{'rights_confirmed':False},{'content_type':'application/octet-stream'}, {'filename':'../source.png'},{'total_bytes':True},{'publish_enabled':True}):
            self.assertEqual(self.request('POST',self.base,self.body(raw,'image','image/png',**changes))[0],400)
        self.assertEqual(self.server.store.get(self.project['id'])['document']['assets'],[])
    def test_session_module_and_cancel_are_inert_and_replay_does_not_attach(self):
        status,session,_=self.request('GET','/api/session');self.assertEqual(status,200);self.assertTrue(session['capabilities']['native_multipart_upload'])
        status,module,_=self.request('GET','/native-multipart-upload.mjs');self.assertEqual(status,200);self.assertIn(b'initializeNativeMultipartUpload',module)
        self.assertEqual(self.request('GET',self.base)[1]['items'],[])
        raw=b'1\n00:00:00,000 --> 00:00:01,000\nWords\n';upload=self.create(raw);sent=self.binary(upload,raw)[1]
        path=self.base+'/'+upload['upload_id']+'/cancel';status,cancelled,_=self.request('POST',path,{})
        self.assertEqual(status,200);self.assertEqual(cancelled['status'],'cancelled');self.assertEqual(cancelled['parts'],sent['parts'])
        self.assertEqual(self.request('POST',path,{})[1],cancelled);self.assertEqual(self.binary(upload,raw)[0],409)
        self.assertFalse(any(self.server.multipart_uploads.directory(upload['upload_id']).glob('part-*.bin')))
        self.assertEqual(self.server.store.get(self.project['id'])['document']['assets'],[])
