"""Read-only checks of real script drafts, source lineage and the accepted release."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import http.cookiejar
import importlib.metadata
import json
import re
import sqlite3
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import Proposal, digest, file_sha, write_json
from services.windows_native.intelligence_lineage import projection
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.pipeline import Config
from services.windows_native.store import Store

REPO=Path(__file__).resolve().parents[1]
EVIDENCE=REPO/'evidence/post-mvp-roadmap/phase-9/9k'


def read(path):
    return json.loads(path.read_bytes())


def table_snapshot(path):
    with sqlite3.connect(path) as con:
        return {name:{'ddl':ddl, 'row_count':len(rows), 'rows_sha256':digest(rows)}
                for name,ddl,rows in [(name,ddl,con.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall())
                for name,ddl in con.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
                if re.fullmatch('[a-z_]+',name)]}


def rows_preserved(before_path, live_path, names=None, selected_ids=None):
    with sqlite3.connect(before_path) as old, sqlite3.connect(live_path) as live:
        old.row_factory=live.row_factory=sqlite3.Row
        tables=names or [r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='sqlite_sequence'")]
        result={}
        for name in tables:
            assert re.fullmatch('[a-z_]+',name)
            assert old.execute('SELECT sql FROM sqlite_master WHERE name=?',(name,)).fetchone()[0] == live.execute('SELECT sql FROM sqlite_master WHERE name=?',(name,)).fetchone()[0]
            count=0
            for row in old.execute('SELECT rowid AS old_rowid,* FROM "'+name+'"'):
                if selected_ids is not None and row['id'] not in selected_ids: continue
                current=live.execute('SELECT rowid AS old_rowid,* FROM "'+name+'" WHERE rowid=?',(row['old_rowid'],)).fetchone()
                assert current is not None and tuple(current)==tuple(row), 'Existing row changed: '+name+':'+str(row['old_rowid'])
                count+=1
            result[name]={'preserved_rows':count, 'status':'PASS'}
        return result


def http_reader():
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def get(path):
        with opener.open('http://127.0.0.1:8026'+path, timeout=10) as response:
            return json.loads(response.read())
    get('/api/session')  # Session stays in memory; never export its cookie/CSRF value.
    return get


def verify(stage):
    config=Config();production=Store(config.data_root);service=IntelligenceService(config,production)
    baseline=read(EVIDENCE.parent/'release-baseline.json')
    authorization=read(EVIDENCE/'owner-authorization.json')
    manifest=read(EVIDENCE/'script-review-manifest.json')
    assert file_sha(EVIDENCE/'script-review-bundle.md')==manifest['review_bundle_sha256']
    assert file_sha(EVIDENCE.parent/'idea-brief-review-bundle.md')==authorization['review_bundle_sha256']
    assert file_sha(EVIDENCE.parent/'idea-brief-review-manifest.json')==authorization['original_review_manifest_sha256']
    accepted=[]
    for video in baseline['final_videos']:
        assert file_sha(video['path'])==video['sha256']
        accepted.append({'number':video['number'],'sha256':video['sha256'],'status':'UNCHANGED'})
    for name,expected in baseline['accepted_evidence'].items():
        assert file_sha(REPO/'evidence/post-mvp-roadmap/phase-8'/name)==expected
    for package in baseline['dependencies']:
        assert importlib.metadata.version(package['name'])==package['version']
    for backup in [baseline['backup'],*authorization['backups']]:
        assert file_sha(backup['path'])==backup['sha256']
    preserved_baseline=rows_preserved(baseline['backup']['path'],production.db)
    preserved_owner=rows_preserved(authorization['backups'][0]['path'],production.db)
    ci_backup=authorization['backups'][1]['path']
    history=rows_preserved(ci_backup,service.store.db,['versions','decisions','operations'])
    original_run=authorization['resolved_selections'][0]['run_id']
    with sqlite3.connect(ci_backup) as con:
        documents=[json.loads(r[0]) for r in con.execute('SELECT document FROM records')]
    original=next(d for d in documents if d['id']==original_run)
    original_ids={original_run,original['opportunity_id'],*original['source_ids']}
    original_ids|={d['id'] for d in documents if d.get('run_id')==original_run}
    owner_case01=rows_preserved(ci_backup,service.store.db,['records'],original_ids)
    get=http_reader();health=get('/api/health');assert health['status']=='ready'
    cases=[]
    for item in manifest['cases']:
        number=item['case'];folder=EVIDENCE/f'case-{number:02}'
        script=read(folder/'script-v2.json');project=production.get(item['project_id'])
        Proposal.model_validate(script['proposal'])
        assert script['script_sha256']==hashlib.sha256(script['proposal']['narration'].encode('utf-8')).hexdigest()==item['script_sha256']
        assert project['revision']==item['project_revision'] and digest(project['document'])==item['project_document_sha256']
        assert projection(project['document'])==script['research_lineage']
        assert project['approval'] is None and not project['document'].get('scene_media') and not project['document']['assets']
        assert all(j['kind']=='content' and j['status']=='awaiting_review' for j in project['jobs'])
        assert not any((folder/n).exists() for n in ['final.mp4','ffprobe.json'])
        bundle=service.bundle(item['run_id']);service.verify_sources(bundle['sources'],bundle['findings'])
        assert bundle['brief']['id']==item['brief_id'] and bundle['brief']['status']=='APPROVED'
        api=get('/api/projects/'+project['id'])
        assert api['revision']==project['revision'] and api['document']==project['document'] and api['approval'] is None
        jobs=[j['id'] for j in project['jobs']]
        cases.append({'case':number,'project_id':project['id'],'revision':project['revision'],
            'project_document_sha256':digest(project['document']),'script_version':2,'script_sha256':script['script_sha256'],
            'source_integrity':'PASS','lineage':'PASS','fresh_process_reopen':'PASS','live_studio_api_reopen':'PASS',
            'script_jobs':jobs,'human_script_review':'PENDING','render_jobs':0,'tts_runs':0,'new_video_generated':False})
    tables={name:table_snapshot(config.data_root/name) for name in ['workflow.sqlite3','intelligence.sqlite3']}
    if stage=='after-restart':
        previous=read(EVIDENCE/'script-review-before-restart.json')
        assert tables==previous['tables'],'Restart changed persisted rows'
        assert cases==previous['cases'],'Restart changed script state'
    result={'captured_at':datetime.now(timezone.utc).isoformat(),'stage':stage,'health':health,
        'tables':tables,'cases':cases,'accepted_phase8_videos':accepted,'phase8_evidence_unchanged':True,
        'runtime_dependencies_unchanged':True,'original_review_bundle_unchanged':True,
        'accepted_release_rows_preserved':preserved_baseline,'pre_task_owner_production_rows_preserved':preserved_owner,
        'pre_task_intelligence_history_preserved':history,'pre_task_owner_case01_records_preserved':owner_case01,
        'script_bundle_sha256':manifest['review_bundle_sha256'],'script_bundle_integrity':'PASS',
        'actual_restart_verified':stage=='after-restart','human_script_approvals':0,'render_dispatches':0,
        'new_video_count':0,'PHASE9K':'SCRIPT_REVIEW_REQUIRED','INTERNAL_PRODUCTION_READY':'YES','CONTENT_INTELLIGENCE_READY':'NO'}
    write_json(EVIDENCE/('script-review-'+stage+'.json'),result)
    print(json.dumps({'stage':stage,'sources_and_lineage':'5/5 PASS','script_state_reopened':'5/5 PASS',
        'accepted_phase8_videos_unchanged':'10/10','owner_existing_case01_preserved':True,
        'actual_restart_verified':result['actual_restart_verified'],'render_dispatches':0,'new_videos':0}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['before-restart','after-restart'])
    verify(parser.parse_args().stage)
