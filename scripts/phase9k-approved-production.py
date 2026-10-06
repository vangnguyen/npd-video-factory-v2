"""Apply the actual Owner media decision and use the existing single Native worker.

No provider substitutes, script regeneration, automatic final acceptance or publishing.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import copy
import hashlib
import json
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import canonical,digest,file_sha,write_json
from services.windows_native.editor import SceneOptions,validate_plan
from services.windows_native.intelligence_lineage import projection
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.media import ingest_media,media_path,verify_selected_files
from services.windows_native.pipeline import Config,verify_runtime
from services.windows_native.store import Store

REPO=Path(__file__).resolve().parents[1]
EVIDENCE=REPO/'evidence/post-mvp-roadmap/phase-9/9k'
GALLERY=EVIDENCE/'storyboard-media-review'
MESSAGE='Duyệt storyboard/media: 01, 02, 04, 06, 08'
QUESTION='Bạn xem [bộ 25 cảnh](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/storyboard-media-review-bundle.md) rồi cho biết có duyệt storyboard, cách dựng và quyền dùng các đồ họa tự tạo cho 01, 02, 04, 06, 08 để tiếp tục tạo giọng đọc và video nội bộ không? Task 9K yêu cầu duyệt phần này riêng; 5 lời đọc v2 đã được duyệt. Video cuối vẫn cần bạn xem/nghe và duyệt sau.'
REVIEWER='Owner — duyệt storyboard/media qua Codex'


def read(path): return json.loads(path.read_bytes())


def preserve(path,value):
    raw=canonical(value)
    if path.exists(): assert path.read_bytes()==raw,'Immutable evidence changed: '+str(path)
    else:
        with path.open('xb') as handle: handle.write(raw)


def archive(path,target,sha):
    assert file_sha(path)==sha
    with target.open('xb') as handle: handle.write(path.read_bytes())


def prepare():
    assert not (EVIDENCE/'production-approval-manifest.json').exists(),'Already prepared; do not re-import reviewed assets'
    assert not (EVIDENCE/'owner-media-authorization.json').exists(),'Preparation receipt exists; inspect a partial operation before continuing'
    config=Config();store=Store(config.data_root);service=IntelligenceService(config,store)
    media=read(GALLERY/'review-manifest.json');scripts=read(EVIDENCE/'script-review-manifest.json')
    script_decisions=read(EVIDENCE/'script-approval-manifest.json')
    assert file_sha(EVIDENCE/'storyboard-media-review-bundle.md')==media['review_bundle_sha256']
    assert file_sha(GALLERY/'index.html')==media['review_html_sha256']
    assert file_sha(EVIDENCE/'script-approval-manifest.json')==media['owner_script_approval_sha256']
    assert [c['case'] for c in media['cases']]==[1,2,4,6,8] and media['asset_count']==25
    with sqlite3.connect(store.db) as con:
        assert con.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','retrying')").fetchone()[0]==0
    verify_runtime(config,full=True)
    prepared=[]
    for item,reviewed in zip(media['cases'],scripts['cases']):
        folder=EVIDENCE/f"case-{item['case']:02}"
        p=store.get(item['project_id']);proposal=read(folder/'proposed-production-proposal.json')
        script=read(folder/'script-v2.json');board=read(folder/'storyboard.json')
        assert p['revision']==item['native_project_revision']==reviewed['project_revision']==3
        assert digest(p['document'])==reviewed['project_document_sha256'] and p['approval'] is None
        assert not p['document']['assets'] and not p['document']['scene_media']
        assert proposal['narration']==p['document']['proposal']['narration']==script['proposal']['narration']
        assert hashlib.sha256(proposal['narration'].encode('utf-8')).hexdigest()==item['script_sha256']
        assert digest(proposal)==item['proposed_proposal_sha256']
        assert file_sha(folder/'storyboard.json')==item['storyboard_sha256']
        assert file_sha(folder/'asset-lineage.json')==item['asset_lineage_sha256']
        assert p['script_review']['current'] and p['script_review']['review_id']==item['script_review_id']
        bundle=service.bundle(reviewed['run_id']);service.verify_sources(bundle['sources'],bundle['findings'])
        assert projection(p['document'])==script['research_lineage']
        assert len(item['assets'])==len(board['scenes'])==5
        for asset,scene in zip(item['assets'],board['scenes']):
            assert file_sha(asset['path'])==asset['sha256']==scene['asset_sha256']
            assert file_sha(asset['preview_path'])==asset['preview_sha256']
            assert asset['script_sha256']==item['script_sha256']
            SceneOptions.model_validate({'scene':scene['scene'],**scene['production_options']})
        prepared.append((item,p,proposal,board))
    backup_root=Path(r'C:\NPD-Video-Factory\post-mvp-validation')
    backups=[]
    for name in ['workflow.sqlite3','intelligence.sqlite3']:
        target=backup_root/('owner-before-phase9k-media-'+name.replace('.sqlite3','')+'-20261006.sqlite3')
        assert not target.exists(),'Preserve existing backup; select a fresh checkpoint name'
        with sqlite3.connect(config.data_root/name) as source,sqlite3.connect(target) as dest: source.backup(dest)
        backups.append({'path':str(target),'sha256':file_sha(target)})
    with (EVIDENCE/'owner-media-decision.txt').open('xb') as handle: handle.write(MESSAGE.encode('utf-8'))
    authorization={'recorded_at':datetime.now(timezone.utc).isoformat(),'source':'Direct human send_user_message_question_reply in this Codex chat',
        'owner_message':MESSAGE,'owner_message_sha256':file_sha(EVIDENCE/'owner-media-decision.txt'),'question':QUESTION,
        'question_item_id':'["request_user_input_async","call_vZqddxSdCivxaLK1wL2Q4YiF",0]',
        'reviewer':REVIEWER,'scope':'APPROVED_STORYBOARD_MEDIA_RIGHTS_AND_INTERNAL_PRODUCTION',
        'final_video_approved':False,'publishing_approved':False,'backups':backups,
        'review_bundle_sha256':media['review_bundle_sha256'],'review_manifest_sha256':file_sha(GALLERY/'review-manifest.json'),
        'script_approval_manifest_sha256':file_sha(EVIDENCE/'script-approval-manifest.json'),
        'cases':[{'case':item['case'],'project_id':p['id'],'reviewed_native_revision':3,'reviewed_native_document_sha256':digest(p['document']),
                  'script_version':2,'script_sha256':item['script_sha256'],'script_review_id':item['script_review_id'],
                  'proposed_proposal_sha256':item['proposed_proposal_sha256'],'storyboard_sha256':item['storyboard_sha256'],
                  'asset_lineage_sha256':item['asset_lineage_sha256'],'assets':[{'proposed_asset_id':a['proposed_asset_id'],'sha256':a['sha256']} for a in item['assets']],
                  'storyboard_approved':True,'media_rights_approved':True,'internal_production_approved':True} for item,p,_,_ in prepared]}
    preserve(EVIDENCE/'owner-media-authorization.json',authorization)
    auth_sha=file_sha(EVIDENCE/'owner-media-authorization.json')
    reference={'source':'human_user_reply_in_codex','authorization_sha256':auth_sha,
               'owner_message_sha256':authorization['owner_message_sha256'],'review_bundle_sha256':media['review_bundle_sha256'],
               'review_manifest_sha256':authorization['review_manifest_sha256'],'scope':authorization['scope']}
    results=[]
    for item,p,proposal,reviewed_board in prepared:
        number=item['case'];folder=EVIDENCE/f'case-{number:02}'
        archive(folder/'storyboard.json',folder/'storyboard-reviewed-v3.json',item['storyboard_sha256'])
        archive(folder/'asset-lineage.json',folder/'asset-lineage-reviewed-proposal.json',item['asset_lineage_sha256'])
        imported=[]
        for source in item['assets']:
            asset=ingest_media(config,Path(source['path']),'image/png',f'phase9k-{number:02}-{source["proposed_asset_id"]}.png',rights_confirmed=True,illustration=False)
            assert asset['source_sha256']==source['sha256']==file_sha(config.data_root/'originals'/asset['original_id'])
            asset['provenance']={'origin':source['origin'],'proposed_asset_id':source['proposed_asset_id'],
                'recipe_sha256':source['recipe_sha256'],'research_source_references':source['research_source_references'],
                'script_sha256':item['script_sha256'],'owner_authorization_sha256':auth_sha,
                'approved_original_sha256':source['sha256'],'normalization':'Existing Native PNG intake creates a JPEG derivative and retains original PNG'}
            p=store.append_media(p['id'],p['revision'],asset);imported.append(asset)
        bindings=[{'scene':scene['scene'],'asset_id':asset['id']} for scene,asset in zip(reviewed_board['scenes'],imported)]
        options=[{'scene':s['scene'],**s['production_options']} for s in reviewed_board['scenes']]
        p=store.save(p['id'],p['revision'],proposal=proposal,scene_media=bindings,scene_options=options,music_enabled=False)
        assert p['revision']==9 and p['script_review']['current'] and p['script_review']['review_id']==item['script_review_id']
        verify_selected_files(config,p['document']);validate_plan(p['document'])
        assert projection(p['document'])==read(folder/'script-v2.json')['research_lineage']
        assert hashlib.sha256(p['document']['proposal']['narration'].encode('utf-8')).hexdigest()==item['script_sha256']
        with store.transaction() as con:
            store.event(con,p['id'],'owner_storyboard_media_approved',{'source':'human_user_reply_in_codex',
                'revision':p['revision'],'reviewer':REVIEWER,'authorization_sha256':auth_sha,
                'review_manifest_sha256':authorization['review_manifest_sha256'],'project_document_sha256':digest(p['document']),
                'asset_original_sha256':[a['source_sha256'] for a in imported],'final_video_approved':False,'publishing_approved':False})
        p=store.approve(p['id'],p['revision'],REVIEWER,True,review_reference=reference)
        preserve(folder/'production-snapshot.json',p)
        board=copy.deepcopy(reviewed_board)
        board.update(version=4,status='OWNER_APPROVED_NATIVE_PLAN',human_approved=True,native_project_revision=9,
                     owner_authorization_sha256=auth_sha,reviewed_storyboard_sha256=item['storyboard_sha256'],
                     actual_edit_plan=p['document']['edit_plan'])
        for scene,asset in zip(board['scenes'],imported):
            scene.update(human_approved=True,native_asset_id=asset['id'],native_derivative_sha256=asset['sha256'],original_id=asset['original_id'])
        write_json(folder/'storyboard.json',board)
        write_json(folder/'asset-lineage.json',{'status':'OWNER_APPROVED_NATIVE_IMPORTED','owner_authorization_sha256':auth_sha,
            'reviewed_proposal_sha256':item['asset_lineage_sha256'],'rights_confirmation_recorded':True,
            'native_import_complete':True,'assets':imported,'reviewed_original_assets':item['assets'],'music':'NONE'})
        acceptance=read(folder/'acceptance.json')
        acceptance.update(storyboard_review='OWNER_APPROVED',media_review='OWNER_APPROVED',project_revision=9,
                          production_approved=True,production_authorization_sha256=auth_sha,
                          human_watch_listen_decision=None,new_video_generated=False,technical_video_pass=False)
        write_json(folder/'acceptance.json',acceptance)
        result={'case':number,'project_id':p['id'],'revision':9,'project_document_sha256':digest(p['document']),
            'snapshot_sha256':digest({'document':p['document'],'approval':p['approval']}),'script_version':2,
            'script_sha256':item['script_sha256'],'script_review_id':item['script_review_id'],'approval':p['approval'],
            'research_lineage':projection(p['document']),'native_assets':imported,'reviewed_original_assets':item['assets']}
        results.append(result)
        print(json.dumps({'case':number,'native_revision':9,'imported_reviewed_graphics':5,'production_approved':True,'render_dispatched':False}),flush=True)
    preserve(EVIDENCE/'production-approval-manifest.json',{'status':'OWNER_APPROVED_READY_FOR_EXISTING_NATIVE_WORKER',
        'owner_authorization_sha256':auth_sha,'cases':results,'actual_script_approvals':5,'actual_media_approvals':5,
        'native_media_imports':25,'final_video_approvals':0,'publishing_approved':False})


def dispatch():
    config=Config();store=Store(config.data_root);manifest=read(EVIDENCE/'production-approval-manifest.json')
    assert file_sha(EVIDENCE/'owner-media-authorization.json')==manifest['owner_authorization_sha256']
    for item in manifest['cases']:
        p=store.get(item['project_id'])
        assert p['revision']==item['revision'] and digest(p['document'])==item['project_document_sha256'] and p['approval']==item['approval']
        verify_selected_files(config,p['document']);validate_plan(p['document'])
    target=EVIDENCE/'real-production-jobs.json'
    if target.exists(): report=read(target)
    else: report={'status':'RUNNING_REAL_NATIVE_TTS_AND_RENDER','production_approval_manifest_sha256':file_sha(EVIDENCE/'production-approval-manifest.json'),
        'fixture_audio':False,'automatic_failed_job_replay':False,'automatic_final_approval':False,'publishing':False,'cases':[]}
    assert report['production_approval_manifest_sha256']==file_sha(EVIDENCE/'production-approval-manifest.json')
    for item in manifest['cases']:
        key=f"phase9k-real-render-{item['project_id']}-{item['revision']}"
        job=store.enqueue(item['project_id'],item['revision'],'render',key)
        entry=next((c for c in report['cases'] if c['case']==item['case']),None)
        if entry: assert entry['job_id']==job['id']
        else:
            report['cases'].append({'case':item['case'],'project_id':item['project_id'],'revision':item['revision'],
                'job_id':job['id'],'request_key':key,'snapshot_sha256':digest(job['snapshot']),'script_sha256':item['script_sha256']})
            write_json(target,report)
        print(json.dumps({'case':item['case'],'job_id':job['id'],'status':job['status'],'stage':job['stage']}),flush=True)


def status():
    store=Store(Config().data_root);target=EVIDENCE/'real-production-jobs.json';report=read(target)
    for item in report['cases']:
        job=store.get_job(item['job_id'])
        item.update(status=job['status'],stage=job['stage'],error=job['error'],result=job['result'],final_review=job['final_review'])
    terminal=all(c['status'] in {'succeeded','failed','interrupted'} for c in report['cases'])
    successful=sum(c['status']=='succeeded' for c in report['cases'])
    report.update(successful_jobs=successful,terminal=terminal,final_video_approvals=0,
        status='WAITING_ACTUAL_HUMAN_WATCH_LISTEN_REVIEW' if successful==5 else 'REAL_RENDER_FAILURES_REQUIRE_REVIEW' if terminal else 'RUNNING_REAL_NATIVE_TTS_AND_RENDER')
    write_json(target,report)
    print(json.dumps({'status':report['status'],'cases':[{k:c.get(k) for k in ['case','job_id','status','stage','error']} for c in report['cases']]},ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','dispatch','status'])
    globals()[parser.parse_args().action]()
