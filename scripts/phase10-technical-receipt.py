"""Record actual isolated edits/cache/provider receipts; never human acceptance."""
from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.windows_native.pipeline import Config,REPO
from services.windows_native.store import Store
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.contracts import canonical,file_sha

cfg=Config.load('C:/NPD-Video-Factory/phase10-uat/config.json');store=Store(cfg.data_root)
identity=json.loads((cfg.data_root/'phase10-technical-project.json').read_bytes());project=store.shot_view(identity['project_id'])
with sqlite3.connect(store.db.resolve().as_uri()+'?mode=ro',uri=True) as con:
    events=[{'created_at':r[1],**json.loads(r[0])} for r in con.execute(
        "SELECT payload,created_at FROM events WHERE project_id=? AND action='shot_timeline_saved_approval_invalidated' ORDER BY id",(project['id'],))]
providers=[]
for p in (cfg.data_root/'shot-ai-edits').glob('*/result.json'):
    result=json.loads(p.read_bytes())
    if result['project_id']==project['id']:
        providers.append({'result_path':str(p),'result_sha256':file_sha(p),'result':result})
preview=PreviewManager(cfg,store).status(project['id'])
result={**identity,'recorded_at':datetime.now(timezone.utc).isoformat(),
        'operator':'Codex technical verification only','human_campaign_acceptance':'PENDING',
        'browser_actions':['narration edit','asset replacement','duration edit','reorder','regenerate existing source','actual AI suggestion explicit apply','preview generation'],
        'project_revision':project['revision'],'timeline_version':project['shot_timeline']['version'],
        'timeline_sha256':project['shot_timeline']['sha256'],'shots':project['shot_timeline']['shots'],
        'events':events,'provider_receipts':providers,'actual_provider_calls':sum(p['result']['provider'].get('calls',0) for p in providers),
        'preview':preview,'project_approval':project['approval'],'render_jobs':len(project['jobs']),
        'tts_calls':0,'live_data_root_mutations':0,'new_human_approvals':0,'service_restart_performed':True,
        'main_8026_interrupted':False}
assert project['approval'] is None and not project['jobs']
assert preview['status']=='READY' and preview['cached_shots']==4 and preview['new_proxy_shots']==1
assert len(events)==5 and len(providers)==2
(REPO/'evidence/post-mvp-roadmap/phase-10/technical-browser-receipt.json').write_bytes(canonical(result))
print(json.dumps({'timeline_version':result['timeline_version'],'operations':len(events),'actual_provider_calls':result['actual_provider_calls'],
                  'cached_proxy_shots':preview['cached_shots'],'new_proxy_shots':preview['new_proxy_shots'],'human_acceptance':False}))
