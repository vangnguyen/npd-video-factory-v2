"""Prepare a recoverable isolated campaign, preserving the certified live data."""
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import canonical,digest,file_sha
from services.windows_native.pipeline import Config,REPO
from services.windows_native.store import Store
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.production_intelligence import ProductionIntelligence,item_id


def main():
    source=Config(); target=Path('C:/NPD-Video-Factory/phase10-uat'); output=REPO/'evidence/post-mvp-roadmap/phase-10'
    assert not target.exists(),'UAT directory exists; preserve it and resume from receipt'
    target.mkdir()
    baseline=json.loads((output/'baseline.json').read_bytes())
    for name,b in baseline['backups'].items():
        assert file_sha(b['path'])==b['sha256'];shutil.copy2(b['path'],target/(name+'.sqlite3'))
    files=[]
    for name in ('assets','documents','intelligence-operations','jobs','originals','research-sources','voice-context-cache'):
        directory=source.data_root/name
        shutil.copytree(directory,target/name)
        for p in sorted(directory.rglob('*')):
            if p.is_file():
                rel=p.relative_to(source.data_root);sha=file_sha(p)
                assert file_sha(target/rel)==sha
                files.append({'relative_path':str(rel).replace('\\','/'),'sha256':sha,'bytes':p.stat().st_size})
    cfg=Config(data_root=target)
    (target/'config.json').write_bytes(canonical(cfg.dump()))
    store=Store(target); intelligence=IntelligenceService(cfg,store); production=ProductionIntelligence(cfg,store,intelligence)
    with sqlite3.connect(store.db) as con:
        assert con.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','retrying')").fetchone()[0]==0
    with sqlite3.connect(intelligence.store.db) as con:
        assert con.execute("SELECT count(*) FROM operations WHERE status IN ('QUEUED','RUNNING')").fetchone()[0]==0
    cases=json.loads((REPO/'evidence/post-mvp-roadmap/phase-9/idea-brief-review-manifest.json').read_bytes())['cases']
    candidates=[]
    for case in cases:
        original=intelligence.store.get(case['run_id'],'ResearchRun')
        fork=intelligence.fork_research_snapshot(original['id'],original['version'],'Codex — chuẩn bị UAT theo task Phase10',
            'Reuse actual retained research/candidates for isolated human campaign review. No new factual research, selection or approval.')
        bundle=intelligence.bundle(fork['run']['id']);opportunity=bundle['opportunity'];identifier=item_id('opportunity',opportunity['id'])
        row=production.find(identifier)
        production.save_planning(identifier,row['planning']['version'],{'campaign':'Phase10 · thử nghiệm Studio','project_priority':70,'campaign_priority':70},'Codex — chỉ chuẩn bị kế hoạch, chưa nghiệm thu')
        candidates.append({'case':case['number'],'source_run_id':original['id'],'run_id':fork['run']['id'],'opportunity_id':opportunity['id'],
                           'queue_item_id':identifier,'ideas':[{'id':i['id'],'title':i['title'],'score':i['score']['final_score'] if i.get('score') else None} for i in bundle['ideas']],
                           'human_selection':'PENDING','human_brief_approval':'PENDING','cached_research':True,'source_dates_preserved':True})
    accepted=json.loads((REPO/'evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/final-acceptance/owner-final-authorization.json').read_bytes())
    copies=[]
    for c in accepted['cases']:
        prior=store.get(c['project_id']);clone=store.duplicate(prior['id'],prior['revision'])
        row=production.find(item_id('project',clone['id']))
        production.save_planning(row['id'],row['planning']['version'],{'campaign':'Phase10 · luyện thao tác cảnh','project_priority':50},'Codex — chuẩn bị bản sao thao tác, không duyệt nội dung')
        copies.append({'case':c['case'],'source_project_id':prior['id'],'project_id':clone['id'],'revision':clone['revision'],
                       'url':'http://127.0.0.1:8030/?project='+clone['id'],'source_final_sha256':c['final_sha256'],
                       'script_review':'PENDING','production_approval':'PENDING','final_review':'PENDING'})
    receipt={'prepared_at':datetime.now(timezone.utc).isoformat(),'baseline_sha':baseline['head_sha'],
             'source_data_root':str(source.data_root),'uat_data_root':str(target),'config_path':str(target/'config.json'),
             'port':8030,'copied_files':files,'campaign_cases':candidates,'editing_practice_projects':copies,
             'human_campaign_acceptance':'PENDING','new_provider_calls':0,'tts_calls':0,'render_calls':0,
             'live_projects_mutated':0,'live_certified_artifacts_modified':False,'publish_enabled':False}
    (output/'uat-preparation.json').write_bytes(canonical(receipt))
    print(json.dumps({'isolated_ideas':len(candidates)*5,'campaign_cases':len(candidates),'practice_projects':len(copies),'provider_calls':0,'human_acceptance':'PENDING'}))


if __name__=='__main__':main()
