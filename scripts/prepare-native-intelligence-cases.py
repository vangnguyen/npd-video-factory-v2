"""Actual Phase 9 practical cases. No human selections, approvals or production dispatch."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import json
import uuid
from services.windows_native.contracts import canonical, digest
from services.windows_native.pipeline import Config
from services.windows_native.store import Store
from services.windows_native.intelligence_service import IntelligenceService

parser=argparse.ArgumentParser(); parser.add_argument('--limit',type=int,default=10); parser.add_argument('--retry-local-failures',action='store_true'); args=parser.parse_args()
repo=Path(__file__).resolve().parents[1]; config=Config()
directory=repo/'evidence/post-mvp-roadmap/phase-9'; directory.mkdir(parents=True,exist_ok=True)
receipt_path=directory/'practical-cases.json'
cases=json.loads((repo/'services/windows_native/profiles/intelligence-cases.json').read_bytes())
records=json.loads(receipt_path.read_bytes()) if receipt_path.exists() else []
service=IntelligenceService(config,Store(config.data_root))
for case in cases[:args.limit]:
    existing=next((r for r in records if r['number']==case['number']),None)
    if existing:
        code=existing.get('operations',[{}])[0].get('error') or {}
        safe_local_failure=code.get('code')=='RESEARCH_PERSISTED_SOURCE_CHANGED' or (code.get('code')=='RESEARCH_SOURCE_SIZE_LIMIT' and existing['source_urls']!=case['source_urls'])
        if args.retry_local_failures and existing['status']=='FAILED' and safe_local_failure:
            previous=json.loads((directory/f"case-{case['number']:02}.json").read_bytes())
            archive=directory/f"case-{case['number']:02}-local-failure-{existing['run_id']}.json"
            if not archive.exists(): archive.write_bytes(canonical(previous))
            existing['preserved_previous_attempt']=dict(existing)
        else:
            print(json.dumps({'number':case['number'],'preserved_status':existing['status'],'no_replay':True}),flush=True)
            continue
    bundle=service.create(case['query'],case['profile_id'],case['source_urls'])
    record={**case,'run_id':bundle['run']['id'],'status':'CREATED','human_acceptance':'PENDING','selected_ideas':0,'actual_provider_calls':0}
    if existing:
        record['preserved_previous_attempt']=existing['preserved_previous_attempt']; records[records.index(existing)]=record
    else: records.append(record)
    receipt_path.write_bytes(canonical(records))
    for action in ('research','ideas'):
        service.enqueue(bundle['run']['id'],bundle['run']['version'],action,uuid.uuid4().hex)
        service.run_one()
        bundle=service.bundle(bundle['run']['id']); record['status']=bundle['run']['status']
        record['operations']=bundle['operations']; record['bundle_sha256']=digest(bundle)
        record['source_ids']=[s['id'] for s in bundle['sources']]; record['finding_ids']=[f['id'] for f in bundle['findings']]; record['idea_ids']=[i['id'] for i in bundle['ideas']]
        record['actual_provider_calls']=bundle['run']['provider_metadata'].get('last_idea_generation',{}).get('actual_provider_calls',0)
        record['research_provider_metadata']=bundle['run']['provider_metadata']
        (directory/f"case-{case['number']:02}.json").write_bytes(canonical(bundle))
        receipt_path.write_bytes(canonical(records))
        print(json.dumps({'number':case['number'],'action':action,'status':record['status'],'sources':len(bundle['sources']),'findings':len(bundle['findings']),'ideas':len(bundle['ideas']),'error':bundle['run']['error']},ensure_ascii=True),flush=True)
        if bundle['run']['status']=='FAILED': break
print(json.dumps({'cases':len(records),'five_candidate_cases':sum(len(r.get('idea_ids',[]))==5 for r in records),'human_acceptance':'PENDING','production_dispatches':0}),flush=True)
