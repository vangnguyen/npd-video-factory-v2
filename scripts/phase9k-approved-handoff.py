"""Apply the actual Owner brief decision and dispatch only native script jobs."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import canonical, digest, file_sha
from services.windows_native.intelligence_service import IntelligenceService, brief_content
from services.windows_native.intelligence_lineage import projection
from services.windows_native.pipeline import Config, load_key
from services.windows_native.store import Store

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO / 'evidence/post-mvp-roadmap/phase-9/9k'


def preserve(path, value):
    raw = canonical(value)
    if path.exists():
        if path.read_bytes() != raw:
            raise RuntimeError('Preserve earlier evidence: ' + str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as handle:
            handle.write(raw)


def prepare(owner_path, service, production):
    if (EVIDENCE / 'handoffs.json').exists() or (EVIDENCE / 'owner-authorization.json').exists():
        raise RuntimeError('Owner decision already applied or partially applied; inspect receipts before any additional action')
    directions = json.loads((EVIDENCE / 'owner-brief-directions.json').read_bytes())
    raw = owner_path.read_bytes()
    decision_text = raw.decode('utf-8-sig')
    assert directions['task'] in decision_text and 'PHASE9K_SCRIPT_REVIEW_REQUIRED' in decision_text
    manifest_path = REPO / 'evidence/post-mvp-roadmap/phase-9/idea-brief-review-manifest.json'
    manifest = json.loads(manifest_path.read_bytes())
    assert file_sha(manifest_path.parent/'idea-brief-review-bundle.md') == manifest['review_bundle_sha256']
    resolved = []
    for case in directions['cases']:
        previous = next(c for c in manifest['cases'] if c['number'] == case['number'])
        bundle = service.bundle(previous['run_id'])
        service.verify_sources(bundle['sources'], bundle['findings'])
        current = [i for i in bundle['ideas'] if i['generation'] == bundle['run']['generation'] and i['status'] not in {'REJECTED','SUPERSEDED'}]
        current.sort(key=lambda i: i['score']['final_score'], reverse=True)
        chosen = current[0]
        for literal in case['required_source_literals']:
            assert any(literal in s['text'] for s in bundle['sources']), 'Unsupported source literal: ' + literal
        if case['number'] != 1:
            assert chosen['id'] == previous['proposed_idea_id'] and chosen['version'] == previous['idea_version']
        resolved.append((case, bundle, chosen, previous))
    with sqlite3.connect(service.config.data_root/'workflow.sqlite3') as con:
        assert con.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','retrying')").fetchone()[0] == 0
    with service.store.transaction() as con:
        assert con.execute("SELECT count(*) FROM operations WHERE status IN ('QUEUED','RUNNING')").fetchone()[0] == 0
    backups = []
    for name in ['workflow','intelligence']:
        target = Path(r'C:\NPD-Video-Factory\post-mvp-validation') / ('owner-before-phase9k-' + name + '-20261006.sqlite3')
        assert not target.exists()
        with sqlite3.connect(service.config.data_root/(name+'.sqlite3')) as source, sqlite3.connect(target) as destination:
            source.backup(destination)
        backups.append({'path':str(target),'sha256':file_sha(target)})
    (EVIDENCE/'owner-decision.txt').write_bytes(raw)
    authorization = {'task':directions['task'],'received_via':'User-pasted request in this Codex chat',
        'owner_decision_sha256':hashlib.sha256(raw).hexdigest(),'owner_decision_path':str(EVIDENCE/'owner-decision.txt'),
        'review_bundle_sha256':manifest['review_bundle_sha256'],'original_review_manifest_sha256':file_sha(manifest_path),
        'directions_sha256':file_sha(EVIDENCE/'owner-brief-directions.json'),'recorded_at':datetime.now(timezone.utc).isoformat(),
        'authority':'Select/edit/approve five idea briefs and generate five native scripts only',
        'not_approved':['scripts','storyboard','media','TTS/render','final video','publishing'],
        'backups':backups,'case01_resolution':'The original reviewed generation was superseded by Studio regeneration and a different brief was already handed off. Latest Rank #1 instruction uses the current generation rank 1 in a retained-research fork; the earlier Studio project, selection and approval remain intact.',
        'resolved_selections':[{'number':c['number'],'run_id':b['run']['id'],'run_version':b['run']['version'],'idea_id':i['id'],'idea_version':i['version'],'generation':i['generation'],'rank':1,'original_manifest_idea_id':p['proposed_idea_id'],'prior_brief_id':b['brief']['id'] if b['brief'] else None} for c,b,i,p in resolved]}
    preserve(EVIDENCE/'owner-authorization.json', authorization)
    items = []
    for case, bundle, idea, original in resolved:
        if bundle['opportunity']['production_project_id']:
            original_idea_id=idea['id']
            bundle=service.fork_research_snapshot(bundle['run']['id'],bundle['run']['version'],directions['reviewer'],directions['task']+' requires a new script candidate with edited brief; preserve the existing imported project.')
            idea=next(i for i in bundle['ideas'] if i['provenance']['original_idea_id']==original_idea_id)
        if case.get('idea_changes'):
            idea = service.edit_idea(idea['id'],idea['version'],case['idea_changes'],directions['reviewer'])
        opportunity = service.store.get(bundle['opportunity']['id'],'Opportunity')
        brief = service.select(idea['id'],idea['version'],opportunity['version'],directions['reviewer'])
        constraints = [v for v in brief['constraints'] if not v.startswith('Thời lượng đề xuất:')]
        changes = {**case.get('brief_changes',{}),'constraints':constraints + directions['common_constraints'] + [
            'Thời lượng mục tiêu: '+case['duration']+'; chưa đo TTS, giữ preset giọng đã nghiệm thu.']}
        brief = service.edit_brief(brief['id'],brief['version'],changes,directions['reviewer'])
        brief = service.approve_brief(brief['id'],brief['version'],directions['reviewer'],True,
            'Owner approval '+case['decision']+' under '+directions['task']+'; receipt SHA256 '+digest(authorization)+'; scripts/storyboard/media/video/publishing NOT approved.')
        project = service.send(brief['id'],brief['version'])
        assert project['approval'] is None and project['document']['proposal'] is None and not project['jobs']
        final_bundle = service.bundle(bundle['run']['id'])
        selected = next(i for i in final_bundle['ideas'] if i['id']==idea['id'])
        folder = EVIDENCE / f"case-{case['number']:02}"
        preserve(folder/'research.json', {'run':final_bundle['run'],'sources':final_bundle['sources'],'findings':final_bundle['findings'],'source_integrity':'PASS'})
        preserve(folder/'idea.json', {'idea':{k:v for k,v in selected.items() if k!='score'},'score':selected['score'],'owner_selection_rank_before_edit':1,'original_manifest_idea_id':original['proposed_idea_id']})
        preserve(folder/'brief.json', brief)
        preserve(folder/'source-claim-map.json', {'source_hashes':{s['id']:s['content_sha256'] for s in final_bundle['sources']},
            'required_literals_verified_in_retained_source':case['required_source_literals'],'source_backed_finding_ids':[f['id'] for f in final_bundle['findings'] if f['kind']=='SOURCED_FACT'],
            'editorial_direction':case,'independent_source_truth_verification':False,'owner_authorization_sha256':digest(authorization)})
        item = {'number':case['number'],'run_id':bundle['run']['id'],'idea_id':idea['id'],'brief_id':brief['id'],
            'brief_version':brief['version'],'approved_brief_sha256':digest(brief_content(brief)),
            'project_id':project['id'],'dispatch_project_revision':project['revision'],'lineage':projection(project['document'])}
        preserve(folder/'handoff.json', item)
        items.append(item)
        print(json.dumps({'case':case['number'],'brief':'APPROVED','handoff':'REAL_NATIVE_PROJECT','project_id':project['id'],'script_approval':False}),flush=True)
    preserve(EVIDENCE/'handoffs.json', {'task':directions['task'],'owner_authorization_sha256':digest(authorization),'cases':items,'render_dispatches':0})


def dispatch(production):
    handoffs = json.loads((EVIDENCE/'handoffs.json').read_bytes())
    load_key(Config().secret_file)  # Presence check only; never print any value.
    for item in handoffs['cases']:
        job = production.enqueue(item['project_id'],item['dispatch_project_revision'],'content',f"vf-phase9k-{item['number']:02}-native-script-v1")
        preserve(EVIDENCE/f"case-{item['number']:02}"/'script-dispatch.json', {'job_id':job['id'],'kind':'content','request_key':job['request_key'],'initial_project_revision':item['dispatch_project_revision']})
        print(json.dumps({'case':item['number'],'script_job_id':job['id'],'render_enqueued':False}),flush=True)


def collect(production):
    handoffs = json.loads((EVIDENCE/'handoffs.json').read_bytes())
    pending = {item['number']:item for item in handoffs['cases']}
    deadline = time.monotonic()+900
    while pending and time.monotonic()<deadline:
        for number,item in list(pending.items()):
            folder = EVIDENCE/f'case-{number:02}'
            dispatch_receipt = json.loads((folder/'script-dispatch.json').read_bytes())
            job = production.get_job(dispatch_receipt['job_id'])
            if job['status'] in {'failed','interrupted','blocked'}:
                preserve(folder/'script-failure.json',{'job_id':job['id'],'status':job['status'],'error':job['error'],'automatic_replay':False})
                raise RuntimeError('Actual native script job stopped: '+json.dumps({'number':number,'error':job['error']}))
            if job['status']!='awaiting_review': continue
            project = production.get(item['project_id']);proposal = project['document']['proposal']
            assert project['approval'] is None and proposal == job['result']['proposal']
            assert all(j['kind']=='content' for j in project['jobs'])
            directory = production.root/'jobs'/job['id']
            lineage = projection(project['document'])
            assert lineage == item['lineage']
            script = {'case':number,'script_version':1,'project_id':project['id'],'project_revision':project['revision'],
                'brief_id':item['brief_id'],'brief_version':item['brief_version'],'research_lineage':lineage,
                'proposal':proposal,'script_sha256':hashlib.sha256(proposal['narration'].encode('utf-8')).hexdigest(),
                'proposal_sha256':digest(proposal),'project_document_sha256':digest(project['document']),
                'native_content_job_id':job['id'],'actual_provider':job['result'],'native_result_sha256':file_sha(directory/'content-result.json'),
                'provider_request_sha256':file_sha(directory/'content-request.json'),'provider_response_sha256':file_sha(directory/'content-provider-response.json'),
                'human_script_review':'PENDING','human_approval':False,'render_requested':False}
            preserve(folder/'script-v1.json', script)
            preserve(folder/'storyboard.json',{'status':'UNAPPROVED_GENERATED_PROPOSAL','native_content_job_id':job['id'],'scenes':proposal['visual_brief'],'human_approved':False,'media_selected':False})
            preserve(folder/'asset-lineage.json',{'status':'ASSET_SELECTION_NOT_STARTED','assets':[],'human_approved':False})
            preserve(folder/'render-manifest.json',{'status':'NOT_REQUESTED_SCRIPT_REVIEW_REQUIRED','job_id':None,'final_mp4':None,'ffprobe_status':'NOT_RUN','human_approved':False})
            preserve(folder/'acceptance.json',{'brief':'OWNER_APPROVED','handoff':'REAL_NATIVE_PROJECT','script_generated':True,'script_review':'PENDING','storyboard_review':'PENDING','media_review':'PENDING','new_video_generated':False,'technical_video_pass':False,'human_watch_listen_decision':None,'CONTENT_INTELLIGENCE_READY':'NO'})
            print(json.dumps({'case':number,'status':'PHASE9K_SCRIPT_REVIEW_REQUIRED','script_sha256':script['script_sha256'],'words':len(proposal['narration'].split()),'actual_provider_calls':job['result']['provider_calls']}),flush=True)
            del pending[number]
        if pending: time.sleep(2)
    if pending: raise RuntimeError('Still running; inspect existing jobs, do not replay: '+str(sorted(pending)))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','dispatch','collect']);parser.add_argument('--owner-decision',type=Path)
    args=parser.parse_args();config=Config();production=Store(config.data_root)
    if args.action=='prepare':
        assert args.owner_decision is not None
        prepare(args.owner_decision,IntelligenceService(config,production),production)
    elif args.action=='dispatch': dispatch(production)
    else: collect(production)


if __name__=='__main__': main()
