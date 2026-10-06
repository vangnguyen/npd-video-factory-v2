"""Read-only comparison with the frozen certified live release."""
from datetime import datetime,timezone
import importlib.metadata as metadata
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.phase10_baseline_support import tables
from services.windows_native.contracts import canonical,file_sha,digest
from services.windows_native.pipeline import Config,REPO,verify_runtime
from services.windows_native.store import Store
from services.windows_native.production_intelligence import ProductionIntelligence
from services.windows_native.intelligence_service import IntelligenceService

def main():
    output=REPO/'evidence/post-mvp-roadmap/phase-10';baseline=json.loads((output/'baseline.json').read_bytes());cfg=Config()
    comparisons={name:tables(cfg.data_root/(name+'.sqlite3'))==value['tables'] for name,value in baseline['backups'].items()}
    evidence={p:file_sha(REPO/p)==sha for p,sha in baseline['frozen_evidence'].items()}
    videos=[{**v,'unchanged':file_sha(v['path'])==v['sha256']} for v in baseline['accepted_videos']]
    dependencies=sorted([{'name':d.metadata['Name'],'version':d.version} for d in metadata.distributions()],key=lambda d:d['name'].lower())
    uat_cfg=Config.load('C:/NPD-Video-Factory/phase10-uat/config.json');uat=Store(uat_cfg.data_root)
    identifier=json.loads((uat_cfg.data_root/'phase10-technical-project.json').read_bytes())['project_id']
    project=uat.shot_view(identifier)
    production=ProductionIntelligence(uat_cfg,uat,IntelligenceService(uat_cfg,uat))
    approved=[v for v in production.library()['items'] if v['approved']]
    result={'verified_at':datetime.now(timezone.utc).isoformat(),'baseline_sha':baseline['head_sha'],
            'live_table_comparisons':comparisons,'frozen_evidence_files':len(evidence),'frozen_evidence_unchanged':all(evidence.values()),
            'accepted_videos':videos,'runtime_dependencies_unchanged':dependencies==baseline['runtime_dependencies'],
            'runtime_verification':verify_runtime(cfg,full=True),'fresh_process_canonical_read':{'project_id':identifier,
            'revision':project['revision'],'timeline_version':project['shot_timeline']['version'],
            'timeline_sha256':project['shot_timeline']['sha256'],'stable_shot_ids':[s['shot_id'] for s in project['shot_timeline']['shots']],
            'persisted':project['shot_timeline']['persisted'],'approval':project['approval'],'jobs':len(project['jobs'])},
            'isolated_approved_library_count':len(approved),'human_phase10_acceptance':'PENDING','live_mutations':0,'provider_calls':0}
    result['passed']=all(comparisons.values()) and all(evidence.values()) and all(v['unchanged'] for v in videos) and result['runtime_dependencies_unchanged'] and len(approved)==15
    target='final-preservation-verification.json' if '--final' in sys.argv else 'preservation-verification.json'
    (output/target).write_bytes(canonical(result))
    print(json.dumps({'passed':result['passed'],'live_tables':comparisons,'evidence_files':len(evidence),'accepted_videos':len(videos),
                      'canonical_fresh_process_version':project['shot_timeline']['version'],'isolated_approved_videos':len(approved)}))
    assert result['passed']

if __name__=='__main__':main()
