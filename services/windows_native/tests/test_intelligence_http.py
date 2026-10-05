import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer
from services.windows_native.research import PublicWebResearchProvider
from services.windows_native.tests.test_intelligence_engines import receipt
from services.windows_native.tests.test_intelligence_workflow import FixtureIdeas


class IntelligenceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.server=LocalServer(0,Config(data_root=self.root),start_worker=False)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.service=self.server.intelligence
        self.service.research_provider=PublicWebResearchProvider(self.root/'research-sources',fetch=lambda url:receipt())
        self.service.idea_provider=FixtureIdeas()

    def tearDown(self): self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def request(self,method,path,body=None,headers=None,authenticated=True):
        con=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=20)
        params={'Content-Type':'application/json'}
        if authenticated: params.update(Cookie=f'vf_native_session={self.server.session}',**{'X-VF-CSRF':self.server.csrf})
        params.update(headers or {})
        con.request(method,path,body=json.dumps(body) if body is not None else None,headers=params)
        res=con.getresponse();raw=res.read();status=res.status;con.close()
        return status,json.loads(raw) if path.startswith('/api/') else raw

    def test_intelligence_routes_keep_session_csrf_and_origin_guards(self):
        self.assertEqual(self.request('GET','/api/intelligence/config',authenticated=False)[0],401)
        self.assertEqual(self.request('POST','/api/intelligence/runs',{},headers={'X-VF-CSRF':'invalid'})[0],403)
        self.assertEqual(self.request('POST','/api/intelligence/runs',{},headers={'Origin':'https://other.example'})[0],403)
        self.assertEqual(self.request('GET','/intelligence',authenticated=False)[0],200)
        self.assertEqual(len(self.request('GET','/api/intelligence/config')[1]['profiles']),4)

    def test_http_workflow_links_approved_brief_to_existing_unapproved_project(self):
        status,b=self.request('POST','/api/intelligence/runs',{'query':'housing fixture','profile_id':'vietnam-property','source_urls':['https://example.com/test']});self.assertEqual(status,200)
        for action in ('research','ideas'):
            self.assertEqual(self.request('POST',f"/api/intelligence/runs/{b['run']['id']}/{action}",{'version':b['run']['version'],'request_key':uuid.uuid4().hex})[0],200)
            self.service.run_one();b=self.request('GET',f"/api/intelligence/runs/{b['run']['id']}")[1]
        idea=b['ideas'][0];status,b=self.request('POST',f"/api/intelligence/ideas/{idea['id']}/select",{'version':idea['version'],'opportunity_version':b['opportunity']['version'],'reviewer':'HTTP TEST FIXTURE'});self.assertEqual(status,200)
        brief=b['brief'];path=f"/api/intelligence/briefs/{brief['id']}"
        self.assertEqual(self.request('POST',path+'/send',{'version':brief['version']})[0],409)
        self.assertEqual(self.request('POST',path+'/approve',{'version':brief['version'],'reviewer':'HTTP TEST FIXTURE','acknowledged':False})[0],400)
        status,b=self.request('POST',path+'/approve',{'version':brief['version'],'reviewer':'HTTP TEST FIXTURE','acknowledged':True});self.assertEqual(status,200)
        status,sent=self.request('POST',path+'/send',{'version':b['brief']['version']});self.assertEqual(status,200);self.assertFalse(sent['production_dispatch'])
        project=self.server.store.get(sent['project_id']);self.assertIsNone(project['approval']);self.assertEqual(project['jobs'],[])
        lineage=self.request('GET',f"/api/intelligence/projects/{project['id']}/lineage")[1];self.assertEqual(lineage['content_idea_id'],idea['id'])

    def test_malformed_or_unknown_profile_never_dispatches(self):
        self.assertEqual(self.request('POST','/api/intelligence/runs',{'query':'q','profile_id':'invented','source_urls':[]})[0],400)
        self.assertEqual(self.request('POST','/api/intelligence/runs',{'query':None,'profile_id':'vietnam-property','source_urls':['https://example.com']})[0],400)
        self.assertEqual(self.service.store.list('ResearchRun'),[])
