"""Explicit API-only repairs of rejected UAT candidates; never Owner acceptance.

Each invocation prepares and enqueues at most one candidate. All requests use
the existing authenticated loopback transport, durable intent receipts and no
automatic replay. Original videos and research/provider evidence are retained.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import uuid
from http.cookiejar import CookieJar
from urllib.request import build_opener, HTTPCookieProcessor, ProxyHandler

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
spec=importlib.util.spec_from_file_location('ux_repair_transport',REPO/'scripts/phase10-final-uat-render.py')
transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
transport.AUTHORITY='VF-PHASE10-STUDIO-UX-STANDARDIZATION-02'
support=transport.support
from services.windows_native.contracts import Proposal,digest,file_sha
from services.windows_native.intelligence_lineage import projection
from services.windows_native.voice_quality import policy_reference,registered_policy
from services.windows_native.warm_voice import build_plan,cache_key,POLICY_ID
from services.windows_native.branding import FIT_NARRATION_POLICY
from services.windows_native.media import project_assets

CASES={
 '01':{'project':'d3aa854ed0ed552091f513c66642d8a0','old_job':'2cdfd4778c834bb68847e80397445626',
       'replace':('tại Green Paradise.','tại Vinhomes Green Paradise Cần Giờ.')},
 '02':{'project':'206a81364b2e5d0d98fa0cfdf2b5bedb','old_job':'f221cf0bbf7e480a9de40f65f96d8bf6',
       'replace':('nêu Green Paradise khởi động','nêu Vinhomes Green Paradise Cần Giờ khởi động')},
 '04':{'project':'ec5a3d1cf3cf5ec3a1debaf97c189139','old_job':'87b374a1ae2f49969fb2b5646e2e8458',
       'replace':('khởi động dự án nêu','khởi động dự án Vinhomes Sài Gòn Park nêu')},
 '06':{'project':'5e9d204790f551eb8afadee33a67a8f6','old_job':'9bd7e74329f542c3b859d98bceaecbc6'},
 '08':{'project':'7f13a515100d5c07aae9760d665ad2f8','old_job':'8b2aeb294d144c5f8d7377357b7c5073'},
}

class API(transport.API):
    def __init__(self):
        self.base='http://127.0.0.1:8030'
        self.ledger=support.Ledger(REPO/'evidence/post-mvp-roadmap/phase-10/studio-ux-02/video-repair','execution')
        self.opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()),support.NoRedirect())
        self.csrf=None
        self.session=self.request('GET','/api/session')
        self.csrf=self.session['csrf']
        if self.session.get('capabilities',{}).get('native_studio_ux') is not True:
            raise RuntimeError('ISOLATED_NEW_RUNTIME_REQUIRED')

def plans(project):
    return build_plan(Proposal.model_validate(project['document']['proposal']),registered_policy(POLICY_ID))

def binding_rows(project):
    return [{'scene':p['scene'],'key':cache_key(p),'target_text':p['target_text'],'context_text':p['context_text'],
             'phonemes':p['phonemes'],'normalized_text':p['normalized_text']} for p in plans(project)]

def check_project(project):
    if project['document'].get('voice_quality')!=policy_reference(POLICY_ID):
        raise RuntimeError('EXISTING_ACCEPTED_VOICE_B_BINDING_REQUIRED')
    if any(j['status'] in ('queued','running','retrying') for j in project.get('jobs',[])):
        raise RuntimeError('PROJECT_BUSY_NO_REPLAY')
    if not project['document'].get('brand_template'):
        raise RuntimeError('EXISTING_STYLE_SNAPSHOT_REQUIRED')
    return projection(project['document'])

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['inspect','observe','repair-and-render','repair02-prefix-and-render'])
    parser.add_argument('--case',required=True,choices=CASES)
    parser.add_argument('--job')
    parser.add_argument('--execute-task-authorization',action='store_true')
    args=parser.parse_args()
    if args.action in ('repair-and-render','repair02-prefix-and-render') and not args.execute_task_authorization:
        parser.error('Explicit task execution flag required')
    if args.action=='repair02-prefix-and-render' and args.case!='02':
        parser.error('The newly authorized source-prefix repair is only case02')
    api=API(); selected=copy.deepcopy(CASES[args.case]); base='/api/projects/'+selected['project']
    if args.action=='repair02-prefix-and-render':
        selected['old_job']='8ae69c0e60404b2496d93b227a9a0715'
        selected['replace']=('Bài viết Vinhomes nêu Vinhomes Green Paradise Cần Giờ',
                             'Bài viết cho biết Vinhomes Green Paradise Cần Giờ')
    before=api.request('GET',base)
    if args.action=='observe':
        if not args.job:parser.error('Explicit job ID required for read-only observation')
        support.identifier(args.job)
        job=next((j for j in before.get('jobs',[]) if j['id']==args.job and j['kind']=='render'),None)
        if job is None:raise RuntimeError('EXPLICIT_RENDER_JOB_NOT_IN_PROJECT')
        logs=api.request('GET','/api/jobs/'+args.job+'/logs')
        api.ledger.save('actual-job-observation.json',{'case':args.case,'project_id':before['id'],
            'project_revision':before['revision'],'job':job,'logs':logs,'observed_at':support.stamp(),
            'app_mutations':0,'provider_calls_by_observer':0,'automatic_retry':False,'Owner_watch_listen':'PENDING'})
        print(json.dumps({'case':args.case,'job_id':args.job,'status':job['status'],'stage':job['stage'],
            'error':job.get('error'),'evidence':str(api.ledger.root)},ensure_ascii=False));return
    cards=api.request('GET',base+'/shots')['shot_timeline']['shots']
    if args.action=='repair02-prefix-and-render' and not cards[1]['narration'].startswith(selected['replace'][0]):
        raise RuntimeError('EXPLICIT_PREFIX_REPAIR_INPUT_CHANGED_NO_REPLAY')
    lineage=check_project(before)
    old_final=Path('C:/NPD-Video-Factory/phase10-uat/jobs')/selected['old_job']/'final.mp4'
    baseline_videos=json.loads((REPO/'evidence/post-mvp-roadmap/phase-10/baseline.json').read_bytes())['accepted_videos']
    initial_rejected=Path('C:/NPD-Video-Factory/phase10-uat/jobs')/CASES[args.case]['old_job']/'final.mp4'
    old_hashes={str(p):file_sha(p) for p in [old_final,initial_rejected]+[Path(v['path']) for v in baseline_videos]}
    before_bindings=binding_rows(before)
    api.ledger.save('before-state.json',{'project':before,'shots':cards,'source_lineage':lineage,
         'cache_bindings':before_bindings,'original_video_hashes':old_hashes,'actor':transport.ACTOR,
         'actor_type':'agent','Owner_personal_watch_listen':'PENDING','pronunciation_quality_confirmed':False})
    if args.action=='inspect':
        print(json.dumps({'case':args.case,'project_id':before['id'],'revision':before['revision'],'evidence':str(api.ledger.root)},ensure_ascii=False));return
    if any(j['kind']=='render' and j['revision']==before['revision'] for j in before.get('jobs',[])):
        # A rejected previous revision is repaired below; a current repaired
        # revision that already dispatched is never automatically repeated.
        if args.action!='repair02-prefix-and-render' and before['document']['brand_template']['template']['duration_policy']==FIT_NARRATION_POLICY:
            raise RuntimeError('CURRENT_FIT_REVISION_ALREADY_DISPATCHED_NO_REPLAY')
    connection=api.request('GET','/api/connections/assemblyai')
    if connection.get('connected') is not True:
        raise RuntimeError('EXISTING_ASSEMBLYAI_CONNECTION_NOT_READY')
    project=before
    if 'replace' in selected:
        source,target=selected['replace']; narration=cards[1]['narration']
        if source in narration:
            if narration.count(source)!=1: raise RuntimeError('SOURCE_PHRASE_NOT_UNIQUE')
            project=api.request('POST',base+'/shots',{'revision':project['revision'],'operation':{
                'type':'update','shot_id':cards[1]['shot_id'],'values':{'narration':narration.replace(source,target)}}})
        elif target not in narration:
            raise RuntimeError('CURRENT_SOURCE_NARRATION_CHANGED_OWNER_DECISION_REQUIRED')
    if args.case=='02':
        current=api.request('GET',base+'/shots')['shot_timeline']['shots'][0]
        if current['requested_duration'] is not None:
            if current['requested_duration']!=9: raise RuntimeError('UNEXPECTED_EXPLICIT_DURATION_PRESERVE_USER_CHOICE')
            project=api.request('POST',base+'/shots',{'revision':project['revision'],'operation':{
                'type':'update','shot_id':current['shot_id'],'values':{'requested_duration':None}}})
    style=project['document']['brand_template']
    template_id=style['template']['id']
    if args.case=='08':template_id=template_id.removesuffix('-landscape')
    if style['template']['duration_policy']!=FIT_NARRATION_POLICY or template_id!=style['template']['id']:
        project=api.request('POST',base+'/brand-template',{'revision':project['revision'],
            'brand_id':style['brand']['id'],'template_id':template_id,'duration_mode':FIT_NARRATION_POLICY})
    after=api.request('GET',base); after_cards=api.request('GET',base+'/shots')['shot_timeline']['shots']
    assert after['revision']==project['revision']
    assert check_project(after)==lineage
    assert after['document']['proposal']['facts_needing_source']==before['document']['proposal']['facts_needing_source']
    assert project_assets(after['document'])==project_assets(before['document'])
    for old,new in zip(cards,after_cards):
        assert all(old[k]==new[k] for k in ('shot_id','visual','on_screen_text','asset_id','crop_strategy','motion','source_start','transition','narration_enabled'))
    if args.case=='08':assert (after['document']['brand_template']['template']['width'],after['document']['brand_template']['template']['height'])==(1080,1920)
    after_bindings=binding_rows(after)
    cache_comparison=[{'scene':a['scene'],'before_key':b['key'],'after_key':a['key'],'unchanged':a['key']==b['key']}
                       for b,a in zip(before_bindings,after_bindings)]
    api.ledger.save('prepared-repair.json',{'case':args.case,'before_revision':before['revision'],'after_revision':after['revision'],
        'after_project':after,'after_shots':after_cards,'source_lineage_exact':True,'cache_comparison':cache_comparison,
        'new_tts_inputs':after_bindings,'exact_research_and_graphics_preserved':True,'duration_policy':FIT_NARRATION_POLICY,
        'pronunciation_override_applied':False,'actual_audio_pronunciation_requires_Owner_listening':True,
        'task_execution_authority':transport.AUTHORITY,'actor':transport.ACTOR,'actor_type':'agent',
        'personal_Owner_script_media_acceptance':'PENDING','personal_Owner_final_watch_listen':'PENDING'})
    narration=after['document']['proposal']['narration']
    project=api.request('POST',base+'/script-review',{'revision':after['revision'],'reviewer':transport.ACTOR,
        'acknowledged':True,'script_sha256':hashlib.sha256(narration.encode('utf-8')).hexdigest()})
    project=api.request('POST',base+'/approve',{'revision':project['revision'],'reviewer':transport.ACTOR,'acknowledged':True})
    assert project['approval']['reviewer']==transport.ACTOR
    job=api.request('POST',base+'/jobs',{'revision':project['revision'],'kind':'render',
        'request_key':'phase10-ux-repair-'+args.case+'-'+uuid.uuid4().hex})
    after_hashes={p:file_sha(p) for p in old_hashes}
    assert after_hashes==old_hashes
    api.ledger.save('render-request.json',{'case':args.case,'project_id':project['id'],'revision':project['revision'],'job':job,
        'original_video_hashes_unchanged':True,'old_hashes':after_hashes,'Owner_watch_listen':'PENDING',
        'prepared_by_agent_not_human_acceptance':True,'automatic_retry':False})
    print(json.dumps({'case':args.case,'project_id':project['id'],'revision':project['revision'],'job_id':job['id'],
        'cache_scenes_unchanged':[r['scene'] for r in cache_comparison if r['unchanged']],
        'cache_scenes_changed':[r['scene'] for r in cache_comparison if not r['unchanged']],
        'evidence':str(api.ledger.root)},ensure_ascii=False))

if __name__=='__main__':main()
