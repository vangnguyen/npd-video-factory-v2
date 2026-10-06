"""Record real provider receipts, edit native drafts, and prepare an Owner review."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import Proposal, canonical, digest, file_sha, write_json
from services.windows_native.intelligence_lineage import projection
from services.windows_native.pipeline import Config
from services.windows_native.store import Store

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO / 'evidence/post-mvp-roadmap/phase-9/9k'


def read(path):
    return json.loads(path.read_bytes())


def preserve(path, value):
    raw = canonical(value)
    if path.exists():
        assert path.read_bytes() == raw, 'Immutable evidence conflict: ' + str(path)
    else:
        with path.open('xb') as handle:
            handle.write(raw)


def provider_receipts():
    ledger = []
    for item in read(EVIDENCE/'handoffs.json')['cases']:
        folder = EVIDENCE/f"case-{item['number']:02}"
        script = read(folder/'script-v1.json')
        job = Store(Config().data_root).get_job(script['native_content_job_id'])
        assert job['status'] == 'awaiting_review' and job['result'] == script['actual_provider']
        directory = Config().data_root/'jobs'/job['id']
        artifacts = {}
        for name, expected in [('content-request.json', 'provider_request_sha256'),
                               ('content-provider-response.json', 'provider_response_sha256'),
                               ('content-result.json', 'native_result_sha256')]:
            assert file_sha(directory/name) == script[expected]
            raw = (directory/name).read_bytes()
            target = folder/name
            if target.exists():
                assert target.read_bytes() == raw
            else:
                with target.open('xb') as handle:
                    handle.write(raw)
            artifacts[name] = file_sha(target)
        response = read(folder/'content-provider-response.json')
        assert response['status'] == 'completed' and response['id'] == job['result']['response_id']
        ledger.append({'case':item['number'], 'job_id':job['id'], 'provider':'openai',
                       'model':response['model'], 'response_id':response['id'],
                       'actual_provider_calls':job['result']['provider_calls'],
                       'usage':response['usage'], 'status':'ACTUAL_COMPLETED_NATIVE_SCRIPT_RESPONSE',
                       'artifact_hashes':artifacts, 'human_script_review':'PENDING',
                       'facts_independently_verified':False, 'render_dispatches':0})
    preserve(EVIDENCE/'actual-script-provider-ledger.json', {'cases':ledger,
        'total_actual_script_calls':sum(i['actual_provider_calls'] for i in ledger),
        'fixture_calls':0, 'editorial_revision_provider_calls':0})
    print('Retained five actual provider request/response/result receipts.', flush=True)


def edit(production):
    directions = read(EVIDENCE/'editorial-script-directions.json')
    for instruction in directions['cases']:
        number = instruction['number']
        folder = EVIDENCE/f'case-{number:02}'
        original = read(folder/'script-v1.json')
        proposal = Proposal.model_validate({
            'narration':' '.join(s[0] for s in instruction['scenes']),
            'visual_brief':[{'scene':n+1, 'narration_excerpt':s[0], 'on_screen_text':s[1], 'visual':s[2]}
                            for n,s in enumerate(instruction['scenes'])],
            'facts_needing_source':original['proposal']['facts_needing_source']}).model_dump()
        project = production.get(original['project_id'])
        if (folder/'script-v2.json').exists():
            saved = read(folder/'script-v2.json')
            assert project['revision'] == saved['project_revision'] and digest(project['document']) == saved['project_document_sha256']
            continue
        intent = {'project_id':project['id'], 'expected_revision':original['project_revision'],
                  'original_document_sha256':original['project_document_sha256'],
                  'original_script_sha256':original['script_sha256'], 'new_proposal_sha256':digest(proposal),
                  'editorial_direction_sha256':file_sha(EVIDENCE/'editorial-script-directions.json'),
                  'editor':'Codex', 'reason':instruction['reason'], 'human_approval':False,
                  'provider_calls':0, 'render_dispatches':0}
        preserve(folder/'editorial-revision-intent.json', intent)
        if project['revision'] == original['project_revision']:
            assert digest(project['document']) == original['project_document_sha256']
            project = production.save(project['id'], project['revision'], proposal=proposal)
        else:
            assert project['revision'] == original['project_revision']+1 and project['document']['proposal'] == proposal
        assert project['approval'] is None and not project['document'].get('scene_media')
        assert all(j['kind']=='content' for j in project['jobs'])
        assert projection(project['document']) == original['research_lineage']
        edited = {**original, 'script_version':2, 'project_revision':project['revision'],
                  'proposal':proposal, 'script_sha256':hashlib.sha256(proposal['narration'].encode('utf-8')).hexdigest(),
                  'proposal_sha256':digest(proposal), 'project_document_sha256':digest(project['document']),
                  'created_at':datetime.now(timezone.utc).isoformat(),
                  'editorial_revision':intent, 'original_provider_script_artifact_sha256':file_sha(folder/'script-v1.json'),
                  'actual_provider_result_is_original_v1':True, 'human_script_review':'PENDING'}
        preserve(folder/'script-v2.json', edited)
        preserve(folder/'storyboard-v1.json', read(folder/'storyboard.json'))
        write_json(folder/'storyboard.json', {'status':'UNAPPROVED_EDITORIAL_PROPOSAL', 'script_version':2,
            'script_sha256':edited['script_sha256'], 'project_revision':project['revision'],
            'scenes':proposal['visual_brief'], 'human_approved':False, 'media_selected':False})
        acceptance = read(folder/'acceptance.json')
        acceptance.update({'latest_script_version':2, 'latest_script_sha256':edited['script_sha256'],
                           'project_revision':project['revision'], 'editorial_revision_by':'Codex'})
        write_json(folder/'acceptance.json', acceptance)
        print(json.dumps({'case':number, 'version':2, 'native_revision':project['revision'],
                          'syllable_like_tokens':len(proposal['narration'].split()),
                          'script_sha256':edited['script_sha256'], 'human_approval':False}), flush=True)


def review(production):
    directions = read(EVIDENCE/'owner-brief-directions.json')
    lines = ['# Phase 9K — Năm kịch bản chờ Owner duyệt', '',
        'PHASE9K_SCRIPT_REVIEW_REQUIRED', '',
        '05 brief đã được Owner chọn/duyệt và chuyển vào 05 dự án Native thật. Mỗi dự án đã nhận một phản hồi OpenAI thật. '
        'Bản v1 và request/response được giữ nguyên; v2 được Codex biên tập bằng thao tác lưu bản nháp của pipeline hiện có, không gọi thêm provider.', '',
        'Đây là lời đọc v2 cần duyệt. Chưa duyệt storyboard/media, chưa chạy TTS/render, chưa có MP4 mới. '
        'Thời lượng dưới đây là mục tiêu của brief, chưa được đo. Nguồn được trích đúng nội dung đã lưu; không phải xác minh độc lập mọi thông tin của bài.', '',
        'Ca 01 dùng bản nghiên cứu được sao chép có provenance từ generation hiện tại sau thao tác Studio của Owner. '
        'Dự án/brief mà Owner đã chuyển trước đó được giữ nguyên; chi tiết tại owner-authorization.json.', '']
    manifest = []
    for item in read(EVIDENCE/'handoffs.json')['cases']:
        number = item['number']; folder = EVIDENCE/f'case-{number:02}'
        script = read(folder/'script-v2.json'); brief = read(folder/'brief.json')
        research = read(folder/'research.json'); scored = read(folder/'idea.json')
        project = production.get(script['project_id'])
        assert project['document']['proposal'] == script['proposal'] and project['approval'] is None
        assert digest(project['document']) == script['project_document_sha256']
        assert projection(project['document']) == script['research_lineage'] == item['lineage']
        assert all(j['kind']=='content' for j in project['jobs'])
        assert not any((folder/name).exists() for name in ['final.mp4','ffprobe.json'])
        duration = next(c['duration'] for c in directions['cases'] if c['number']==number)
        lines += [f"## Ca {number:02} — {scored['idea']['title']}", '',
                  f"Bản cần duyệt: **v2**, mục tiêu **{duration}**, project revision **{project['revision']}**.", '',
                  script['proposal']['narration'], '',
                  f"[Mở dự án thật trong Studio](http://127.0.0.1:8026/?project={project['id']})", '',
                  f"Brief `{brief['id']}` v{brief['version']} · Idea `{scored['idea']['id']}` · "
                  f"Score {scored['score']['final_score']} (**HEURISTIC_SCORING**).", '',
                  f"Script SHA256 `{script['script_sha256']}`.", '', 'Nguồn để đối chiếu:', '']
        for source in research['sources']:
            publication = source['timestamp'] or 'unknown trong record đã lưu; không dùng ngày lấy thay ngày đăng'
            lines += [f"- [{source['title']}]({source['reference']}) — publication: {publication}; "
                      f"retrieved: {source['retrieved_at']}; content SHA256 `{source['content_sha256']}`."]
        lines += ['', 'Các cảnh trong storyboard.json chỉ là đề xuất chưa duyệt. '
                  'Không dùng nút duyệt sản xuất để thay cho việc duyệt riêng lời đọc khi media chưa được xem.', '']
        manifest.append({'case':number, 'script_version':2, 'project_id':project['id'],
            'project_revision':project['revision'], 'script_sha256':script['script_sha256'],
            'proposal_sha256':script['proposal_sha256'], 'project_document_sha256':script['project_document_sha256'],
            'script_artifact_sha256':file_sha(folder/'script-v2.json'),
            'brief_id':brief['id'], 'brief_version':brief['version'], 'brief_artifact_sha256':file_sha(folder/'brief.json'),
            'approved_brief_sha256':item['approved_brief_sha256'], 'run_id':item['run_id'],
            'idea_id':item['idea_id'], 'score_sha256':digest(scored['score']),
            'lineage_sha256':digest(script['research_lineage']),
            'source_hashes':{s['id']:s['content_sha256'] for s in research['sources']},
            'native_content_job_id':script['native_content_job_id'], 'human_script_review':'PENDING',
            'human_approval':False, 'new_video_generated':False})
    lines += ['## Quyết định cần ghi nhận', '',
        'Owner có thể duyệt v2 của 01/02/04/06/08, yêu cầu sửa từng ca hoặc từ chối. '
        'Cần ghi rõ số ca và phiên bản; một quyết định chỉ duyệt brief không được xem là duyệt lời đọc. '
        'Sau script review, storyboard và media vẫn cần duyệt riêng trước sản xuất.', '',
        'INTERNAL_PRODUCTION_READY = YES', '', 'CONTENT_INTELLIGENCE_READY = NO', '']
    target = EVIDENCE/'script-review-bundle.md'
    raw = '\n'.join(lines).encode('utf-8')
    if target.exists():
        assert target.read_bytes() == raw
    else:
        with target.open('xb') as handle: handle.write(raw)
    preserve(EVIDENCE/'script-review-manifest.json', {'status':'PHASE9K_SCRIPT_REVIEW_REQUIRED',
        'review_bundle_sha256':file_sha(target), 'cases':manifest, 'render_dispatches':0,
        'human_script_approvals':0, 'new_video_count':0, 'CONTENT_INTELLIGENCE_READY':'NO'})
    print('Five exact v2 scripts frozen for Owner review; no TTS/render requested.', flush=True)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('action', choices=['provider-receipts','edit','review'])
    action=parser.parse_args().action
    if action=='provider-receipts': provider_receipts()
    elif action=='edit': edit(Store(Config().data_root))
    else: review(Store(Config().data_root))


if __name__=='__main__': main()
