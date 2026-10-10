"""Resolve shipped Studio module dependencies over an isolated signed server.

This exercises browser file transport; it is not a browser layout/UAT test.
"""
import hashlib,json,os,re,tempfile,threading,unittest
from pathlib import Path
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.access import NativeAccess
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer
from services.windows_native.tests import test_access_http as access_fixture
from services.windows_native.tests.test_human_identity import fixture

class StudioStaticHTTPTests(unittest.TestCase):
    request=access_fixture.NativeAccessHTTPTests.request
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='vf-static-');self.root=Path(self.temp.name)/'state';self.config=Config(data_root=self.root)
        raw,data=fixture('viewer',workspace='wsp_studio_static_fixture')
        access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),'wsp_studio_static_fixture')
        self.server=LocalServer(0,self.config,start_worker=False,access=access);self.cookie,session=access.login(raw);self.csrf=session.csrf
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def test_studio_entrypoint_module_dependency_closure(self):
        pending=['/native.mjs','/production.mjs','/intelligence.mjs','/trend-radar.mjs'];seen={}
        pattern=re.compile(r'''(?:from\s*|import\s*\()\s*['"](\./[^'"]+\.mjs)['"]''')
        while pending:
            path=pending.pop()
            if path in seen:continue
            status,raw,headers=self.request('GET',path);self.assertEqual(status,200,path)
            self.assertIsInstance(raw,bytes,path);self.assertIn(headers['Content-Type'].split(';')[0],('text/javascript','application/javascript'),path)
            seen[path]=hashlib.sha256(raw).hexdigest()
            pending.extend('/'+name[2:] for name in pattern.findall(raw.decode('utf-8')))
        self.assertIn('/native-narrated-timeline.mjs',seen);self.assertIn('/native-visual-properties.mjs',seen)
        evidence=os.environ.get('VF_STUDIO_STATIC_HTTP_EVIDENCE')
        if evidence:
            with Path(evidence).open('x',encoding='utf-8',newline='\n') as f:
                json.dump({'schema_version':'native-studio-static-http-proof-v1','isolated_signed_HTTP':True,'viewer_fixture':True,
                    'module_sha256':seen,'modules':len(seen),'browser_rendered':False,'owner_UAT':False,'provider_calls':0},f,indent=2);f.write('\n')
    def test_visual_modules_and_style_match_saved_source(self):
        repo=Path(__file__).resolve().parents[3]
        for name in ['native-narrated-timeline.mjs','native-narrated-timeline.css','native-visual-properties.mjs']:
            status,raw,headers=self.request('GET','/'+name);self.assertEqual(status,200,name)
            self.assertEqual(raw,(repo/'apps/studio-web'/name).read_bytes());self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
            self.assertEqual(headers['Content-Type'].split(';')[0],'text/css' if name.endswith('.css') else 'text/javascript')
    def test_static_router_keeps_unknown_files_and_traversal_closed(self):
        for path in ['/native-visual-properties.test.mjs','/package.json','/../native-visual-properties.mjs','/%2e%2e/native-visual-properties.mjs','/apps/studio-web/native-visual-properties.mjs']:
            self.assertIn(self.request('GET',path)[0],(400,403,404),path)

if __name__=='__main__':unittest.main()
