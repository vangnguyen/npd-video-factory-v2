"""Explicit task-authorized draft production over HTTP; never final human acceptance.

The current Owner task requires preparing all candidates and stopping only at
watch/listen decisions. The actor remains Codex; these execution authorizations
must not be counted as the Owner personally reading/hearing the new content.
All project changes use the existing Studio HTTP API. No database edits occur.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from http.cookiejar import CookieJar
import importlib.util
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import build_opener, HTTPCookieProcessor, ProxyHandler, Request
import uuid

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('uat_support',ROOT/'scripts/phase10-final-uat-support.py')
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
ACTOR='Codex — task Owner cho phép chuẩn bị; Owner chưa xem/nghe'
AUTHORITY='VF-PHASE10-FINAL-UAT-CERTIFICATION-01'


class API:
    def __init__(self, category):
        self.base='http://127.0.0.1:8030'
        self.ledger=support.Ledger(ROOT/'evidence/post-mvp-roadmap/phase-10/final-uat'/category,'execution')
        self.opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()),support.NoRedirect())
        self.csrf=None
        self.csrf=self.request('GET','/api/session')['csrf']

    def request(self,method,path,body=None,raw=None,extra=None):
        if not path.startswith('/api/') or '..' in path or '?' in path: raise ValueError('SCOPED_API_PATH_REQUIRED')
        headers={'Accept':'application/json','Origin':self.base,'Sec-Fetch-Site':'same-origin'}
        payload=support.canonical(body) if body is not None else raw
        if method=='POST':
            if self.csrf is None: raise ValueError('SESSION_REQUIRED')
            headers.update({'Content-Type':'application/json','X-VF-CSRF':self.csrf})
        if extra: headers.update(extra)
        receipt={'authority':AUTHORITY,'actor_type':'agent','actor':ACTOR,'human_quality_acceptance':False,
                 'human_watch_listen':False,'method':method,'path':path,'requested_at':support.stamp(),
                 'body':body,'upload_sha256':support.sha(raw) if raw is not None else None,'automatic_retry':False}
        if method=='POST': self.ledger.save(f'{len(self.ledger.entries)+1:04d}-intent.json',receipt)
        try:
            try: response=self.opener.open(Request(self.base+path,data=payload,headers=headers,method=method),timeout=150)
            except HTTPError as error: response=error
            with response: code=response.status; data=response.read(64*1024*1024)
            result=json.loads(data)
        except Exception as error:
            self.ledger.receipt({**receipt,'error_type':type(error).__name__,'outcome':'UNKNOWN_NO_REPLAY'})
            raise RuntimeError('Request outcome unknown; inspect state, never replay blindly') from None
        stored={'capabilities':result.get('capabilities'),'csrf_present':bool(result.get('csrf'))} if path=='/api/session' else result
        self.ledger.receipt({**receipt,'completed_at':support.stamp(),'status':code,'raw_sha256':support.sha(data),'snapshot':stored})
        if code>=300: raise RuntimeError(f'HTTP{code}: {result.get("code")}')
        return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['snapshot','upload','plan','authorize','render'])
    parser.add_argument('--project',required=True);parser.add_argument('--file');parser.add_argument('--brand');parser.add_argument('--template')
    parser.add_argument('--execute-task-authorization',action='store_true')
    args=parser.parse_args();support.identifier(args.project)
    api=API('campaign');base='/api/projects/'+args.project
    project=api.request('GET',base)
    if args.action=='upload':
        path=Path(args.file).resolve();raw=path.read_bytes()
        mime={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.mp4':'video/mp4','.mov':'video/quicktime'}[path.suffix.lower()]
        project=api.request('POST',base+'/media',raw=raw,extra={'Content-Type':mime,'X-VF-Revision':str(project['revision']),
             'X-VF-Rights':'confirmed','X-VF-Illustration':'true','X-VF-Filename':quote(path.name)})
    elif args.action=='plan':
        project=api.request('POST',base+'/auto-plan',{'revision':project['revision']})
        if args.brand and args.template:
            project=api.request('POST',base+'/brand-template',{'revision':project['revision'],'brand_id':args.brand,'template_id':args.template})
    elif args.action=='authorize':
        if not args.execute_task_authorization: parser.error('Explicit task execution flag required')
        proposal=project['document'].get('proposal')
        if not proposal: raise RuntimeError('No script to authorize')
        api.ledger.save('delegated-execution-authority.json',{'authority':AUTHORITY,'actor':ACTOR,'actor_type':'agent',
            'script_sha256':hashlib.sha256(proposal['narration'].encode('utf-8')).hexdigest(),
            'project_revision':project['revision'],'personal_owner_script_review':'PENDING','personal_owner_media_review':'PENDING',
            'personal_owner_final_watch_listen':'PENDING','scope':'Prepare new internal candidates for final Owner review; never certify personal acceptance',
            'source_of_authority':'User explicitly required preparation through final render and stopping only at explicit human watch/listen decisions'})
        project=api.request('POST',base+'/script-review',{'revision':project['revision'],'reviewer':ACTOR,'acknowledged':True,
            'script_sha256':hashlib.sha256(proposal['narration'].encode('utf-8')).hexdigest()})
        project=api.request('POST',base+'/approve',{'revision':project['revision'],'reviewer':ACTOR,'acknowledged':True})
    elif args.action=='render':
        if not args.execute_task_authorization: parser.error('Explicit task execution flag required')
        if not project.get('approval') or project['approval']['reviewer']!=ACTOR: raise RuntimeError('Current delegated preparation authorization required')
        job=api.request('POST',base+'/jobs',{'revision':project['revision'],'kind':'render','request_key':'phase10-final-'+uuid.uuid4().hex})
        api.ledger.save('render-request.json',{'job':job,'human_acceptance':'PENDING'})
        print(json.dumps({'job_id':job['id'],'project_id':project['id'],'evidence':str(api.ledger.root)}));return
    api.ledger.save('project-state.json',project)
    print(json.dumps({'project_id':project['id'],'revision':project['revision'],'action':args.action,'evidence':str(api.ledger.root)}))


if __name__=='__main__':main()
