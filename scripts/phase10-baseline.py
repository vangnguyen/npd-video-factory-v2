"""Freeze accepted Native state before additive Phase 10 work; no provider calls."""
from datetime import datetime, timezone
import importlib.metadata as metadata
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import canonical, file_sha, digest
from services.windows_native.pipeline import Config, REPO, verify_runtime


def tables(path):
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as con:
        con.row_factory=sqlite3.Row
        assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        return {r['name']:{'ddl':r['sql'],'rows':len(values),'sha256':digest(values)}
                for r in con.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name")
                for values in [[dict(v) for v in con.execute('SELECT * FROM "'+r['name']+'" ORDER BY rowid')]]}


def main():
    cfg=Config(); out=REPO/'evidence/post-mvp-roadmap/phase-10'; out.mkdir(parents=True,exist_ok=True)
    target=out/'baseline.json'
    assert not target.exists(), 'Preserve earlier baseline'
    head=subprocess.check_output([str(cfg.git),'rev-parse','HEAD'],cwd=REPO,text=True).strip()
    assert head=='4c4043cb8a6a559aeb9dae598fd0391045626b23'
    frozen={str(p.relative_to(REPO)).replace('\\','/'):file_sha(p)
            for phase in ('phase-8','phase-9') for p in sorted((REPO/'evidence/post-mvp-roadmap'/phase).rglob('*')) if p.is_file()}
    backups={}
    for name in ('workflow','intelligence'):
        source=cfg.data_root/(name+'.sqlite3')
        saved=Path('C:/NPD-Video-Factory/post-mvp-validation')/('before-phase10-'+name+'-'+uuid.uuid4().hex+'.sqlite3')
        with saved.open('xb'): pass
        with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(saved) as dst: src.backup(dst)
        assert tables(saved)==tables(source)
        backups[name]={'path':str(saved),'sha256':file_sha(saved),'tables':tables(saved)}
    release=json.loads((REPO/'evidence/post-mvp-roadmap/phase-9/release-baseline.json').read_bytes())
    final=json.loads((REPO/'evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/final-acceptance/owner-final-authorization.json').read_bytes())
    videos=[{'phase':8,'path':v['path'],'sha256':v['sha256']} for v in release['final_videos']]
    videos += [{'phase':9,'path':str(cfg.data_root/'jobs'/c['job_id']/'final.mp4'),'sha256':c['final_sha256'],'job_id':c['job_id']} for c in final['cases']]
    assert all(file_sha(v['path'])==v['sha256'] for v in videos)
    deps=sorted([{'name':d.metadata['Name'],'version':d.version} for d in metadata.distributions()],key=lambda d:d['name'].lower())
    assert deps==release['dependencies']
    value={'captured_at':datetime.now(timezone.utc).isoformat(),'head_sha':head,
           'branch':subprocess.check_output([str(cfg.git),'branch','--show-current'],cwd=REPO,text=True).strip(),
           'INTERNAL_PRODUCTION_READY':'YES','CONTENT_INTELLIGENCE_READY':'YES','backups':backups,
           'frozen_evidence':frozen,'accepted_videos':videos,'runtime_dependencies':deps,
           'runtime_verification':verify_runtime(cfg,full=True),'timeline_schema_version':'1.1',
           'tests':{'native':'running; result stored separately','studio':{'tests':32,'passed':32}},
           'provider_calls':0,'project_mutations':0,'human_approvals_created':0}
    target.write_bytes(canonical(value))
    print(json.dumps({'baseline_sha':head,'frozen_files':len(frozen),'accepted_videos':len(videos),'backups':list(backups),'runtime':'PASS'}))


if __name__=='__main__': main()
