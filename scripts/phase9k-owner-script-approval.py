"""Bind the Owner's actual v2 approval to five unchanged native script drafts."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import canonical,digest,file_sha,write_json
from services.windows_native.intelligence_lineage import projection
from services.windows_native.pipeline import Config
from services.windows_native.store import Store

REPO=Path(__file__).resolve().parents[1]
EVIDENCE=REPO/'evidence/post-mvp-roadmap/phase-9/9k'
MESSAGE='Duyệt v2: 01, 02, 04, 06, 08'


def read(path): return json.loads(path.read_bytes())


def preserve(path,value):
    raw=canonical(value)
    if path.exists(): assert path.read_bytes()==raw,'Immutable receipt changed'
    else:
        with path.open('xb') as handle: handle.write(raw)


def main():
    manifest=read(EVIDENCE/'script-review-manifest.json')
    assert file_sha(EVIDENCE/'script-review-bundle.md')==manifest['review_bundle_sha256']
    assert [c['case'] for c in manifest['cases']]==[1,2,4,6,8]
    production=Store(Config().data_root)
    for case in manifest['cases']:
        folder=EVIDENCE/f"case-{case['case']:02}"
        script=read(folder/'script-v2.json');project=production.get(case['project_id'])
        assert file_sha(folder/'script-v2.json')==case['script_artifact_sha256']
        assert project['revision']==case['project_revision'] and digest(project['document'])==case['project_document_sha256']
        assert script['proposal']==project['document']['proposal']
        assert hashlib.sha256(script['proposal']['narration'].encode('utf-8')).hexdigest()==case['script_sha256']
        assert digest(projection(project['document']))==case['lineage_sha256']
        assert project['approval'] is None and all(j['kind']=='content' for j in project['jobs'])
    message_path=EVIDENCE/'owner-script-decision-v2.txt'
    raw=MESSAGE.encode('utf-8')
    if message_path.exists(): assert message_path.read_bytes()==raw
    else:
        with message_path.open('xb') as handle: handle.write(raw)
    authorization_path=EVIDENCE/'owner-script-authorization-v2.json'
    if authorization_path.exists():
        authorization=read(authorization_path)
        assert authorization['owner_message_sha256']==file_sha(message_path)
    else:
        authorization={'owner_message':MESSAGE,'owner_message_sha256':file_sha(message_path),
            'source':'Direct human user reply in this Codex chat','received_identity':'Owner',
            'recorded_at':datetime.now(timezone.utc).isoformat(),'reviewer':'Owner — duyệt v2 qua Codex',
            'review_bundle_sha256':manifest['review_bundle_sha256'],
            'review_manifest_sha256':file_sha(EVIDENCE/'script-review-manifest.json'),
            'script_version':2,'cases':manifest['cases'],'scope':'SCRIPT_ONLY',
            'not_approved':['storyboard','media selection/rights','TTS/render','final video','publishing'],
            'writing_block_changes_received':[]}
        preserve(authorization_path,authorization)
    reference={'source':'human_user_reply_in_codex','authorization_sha256':file_sha(authorization_path),
               'owner_message_sha256':file_sha(message_path),'review_bundle_sha256':manifest['review_bundle_sha256'],
               'script_version':2,'production_authorized':False}
    approvals=[]
    for case in manifest['cases']:
        project=production.review_script(case['project_id'],case['project_revision'],authorization['reviewer'],True,
                                         case['script_sha256'],reference)
        review=project['script_review'];assert review['current'] and not review['production_approved']
        assert project['approval'] is None and all(j['kind']=='content' for j in project['jobs'])
        folder=EVIDENCE/f"case-{case['case']:02}"
        preserve(folder/'script-review.json',{'case':case['case'],'script_version':2,
            'script_sha256':case['script_sha256'],'project_id':project['id'],'native_review':review,
            'owner_authorization_sha256':file_sha(authorization_path),'human_script_review':'OWNER_APPROVED',
            'storyboard_review':'PENDING','media_review':'PENDING','production_approved':False})
        acceptance=read(folder/'acceptance.json')
        acceptance.update({'script_review':'OWNER_APPROVED','script_review_id':review['review_id'],
            'script_review_authorization_sha256':file_sha(authorization_path),'approved_script_version':2,
            'approved_script_sha256':case['script_sha256']})
        write_json(folder/'acceptance.json',acceptance)
        approvals.append({'case':case['case'],'project_id':project['id'],'script_version':2,
            'script_sha256':case['script_sha256'],'review_id':review['review_id'],'reviewer':review['reviewer'],
            'approved_at':review['approved_at'],'current':True,'scope':'SCRIPT_ONLY','render_dispatched':False})
        print(json.dumps({'case':case['case'],'script':'OWNER_APPROVED_V2','native_review_id':review['review_id'],
                          'production_approval':False,'render_dispatches':0}),flush=True)
    preserve(EVIDENCE/'script-approval-manifest.json',{'status':'PHASE9K_STORYBOARD_MEDIA_REVIEW_REQUIRED',
        'owner_authorization_sha256':file_sha(authorization_path),'cases':approvals,
        'human_script_approvals':5,'render_dispatches':0,'new_video_count':0,'CONTENT_INTELLIGENCE_READY':'NO'})


if __name__=='__main__': main()
