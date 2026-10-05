"""Read current release state; produce review material, never certify absent gates."""
import json
from pathlib import Path
import sqlite3
import sys
REPO=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(REPO))
from services.windows_native.contracts import digest,file_sha,write_json
from services.windows_native.media import project_assets
from services.windows_native.pipeline import Config
from services.windows_native.store import Store

def main():
    directory=REPO/'evidence/post-mvp-roadmap/phase-8'
    state=json.loads((directory/'review-drafts.json').read_bytes())
    config=Config(); store=Store(config.data_root); rows=[]; checks=[]
    text=['# Bộ duyệt nội dung — 10 video phát hành nội bộ','',
          '**Trạng thái: chờ người dùng duyệt nội dung. Chưa tạo giọng đọc hoặc video mới cho bộ này. INTERNAL_PRODUCTION_READY = NO.**','',
          'Mở [Studio](http://127.0.0.1:8026/) và chọn từng dự án `Release 01` đến `Release 10`. Đọc lời, xem nguồn từng cảnh, chữ và cách dựng; sửa/lưu nếu cần. Điền tên và xác nhận ở “Duyệt nội dung này”. Sau khi dựng, từng tệp MP4 cần được xem/nghe rồi duyệt ở “Duyệt video cuối”.','',
          'Các nguồn dùng quyền đã xác nhận trong MVP/dự án gốc. Ảnh và video đều có nhãn minh họa; khung hình trích và clip tắt tiếng có xuất xứ lưu riêng. Hồ sơ NPD/Vang Nguyễn là cấu hình tham chiếu, chưa có logo chính thức. Media cũ còn thiếu bản sao byte tải lên đầu tiên; bằng chứng hiện có được giữ rõ, không bổ sung giả.','',
          '**Điểm cần xem:** bản 04 do trợ lý biên tập tại máy sau lỗi `CONTENT_AMBIGUOUS_RESPONSE`, không phải kết quả provider và không gửi lại yêu cầu lỗi. Bản 07 là transcript thật chưa xác minh: “cái kênh” có thể cần sửa thành “cái tên” sau khi nghe nguồn; transcript gốc giữ nguyên. Các mốc 30 giây giữ tốc độ giọng, nên có thể cần rút lời hoặc chọn mẫu dài hơn nếu thời lượng đo vượt giới hạn. Các bản nháp về cách kiểm tra nội dung là ứng viên cho kiểm tra vận hành; bạn cần xác nhận chúng phù hợp mục đích nghiệm thu nội bộ.','',
          '| Bản | Đầu vào | Hồ sơ / mẫu | Trạng thái |','| --- | --- | --- | --- |']
    sections=[]
    for e in state['cases']:
        p=store.get(e['project_id']); doc=p['document']; selected=doc['brand_template']; assets=project_assets(doc)
        content_jobs=[j for j in p['jobs'] if j['kind']=='content']; render_jobs=[j for j in p['jobs'] if j['kind']=='render']
        sources_verified=all((config.data_root/'assets'/a['id']).is_file() and file_sha(config.data_root/'assets'/a['id'])==a['sha256'] for a in assets)
        originals_verified=all(a.get('original_id') and file_sha(config.data_root/'originals'/a['original_id'])==a['source_sha256'] for a in assets)
        documents_verified=all(file_sha(config.data_root/'documents'/d['id'])==d['sha256'] for d in doc['documents'])
        current=digest(doc)==e['document_sha256'] and p['revision']==e['revision']
        checks.append({'number':e['number'],'snapshot_matches_manifest':current,'media_hashes':sources_verified,'new_intake_originals':originals_verified,'document_originals':documents_verified,'plan_present':bool(doc.get('edit_plan')),'approval_integrity':p['approval'] is None or p['approval']['snapshot_sha256']==digest(doc),'render_jobs':len(render_jobs)})
        row={'number':e['number'],'input_family':e['input_family'],'project_id':p['id'],'revision':p['revision'],'document_sha256':digest(doc),'content_job_id':e['job_id'],'content_origin':e.get('content_origin',content_jobs[0]['result'].get('source','actual OpenAI response') if content_jobs[0]['result'] else 'explicit provider failure'),'content_error_preserved':e.get('error_code'),'human_script_approved':p['approval'] is not None,'final_videos':len(render_jobs),'human_final_approved':sum(bool(j.get('final_review') and j['final_review']['decision']=='approve') for j in render_jobs)}
        rows.append(row)
        text.append(f"| {e['number']:02} | {e['input_family']} | {selected['brand']['name']} / {selected['template']['name']} | {'Đã duyệt nội dung; chờ duyệt video' if p['approval'] else 'Chờ duyệt nội dung'} |")
        sections += ['',f"## {e['title']}",'',f"Dự án `{p['id']}` · phiên bản **{p['revision']}** · dấu nội dung `{digest(doc)}`.",'',
                     f"Nguồn lời: {row['content_origin']}." ,'',doc['proposal']['narration'],'','Nguồn/cảnh để kiểm tra:','']
        by_id={a['id']:a for a in assets}
        for scene in doc['edit_plan']['scenes']:
            a=by_id[scene['selected_asset']]
            sections.append(f"- Cảnh {scene['scene']}: **{scene['on_screen_text']}** — {a['filename']}; {scene['motion']}, {scene['crop_strategy']}; nguồn `{a['sha256']}`.")
        sections += ['','Ghi chú cần xác minh:','']+['- '+f for f in doc['proposal']['facts_needing_source']]
    text += sections
    required={'prompt','script','image','multiple_images','silent_video','speech_video','mixed_media'}
    ready_inputs=required.issubset({r['input_family'] for r in rows})
    technical=all(all(c[k] for k in ('snapshot_matches_manifest','media_hashes','new_intake_originals','document_originals','plan_present','approval_integrity')) for c in checks) and len(rows)==10 and ready_inputs
    assert technical,checks
    approved=sum(r['human_script_approved'] for r in rows)
    completed=sum(r['human_final_approved'] for r in rows)
    real=json.loads((directory/'real-candidates.json').read_bytes()) if (directory/'real-candidates.json').exists() else {}
    rendered=real.get('successful_jobs')==10 and real.get('failed_jobs')==0
    blockers=[]
    if completed<10: blockers.append({'severity':'P1','code':'TEN_HUMAN_FINAL_VIDEO_REVIEWS_REQUIRED'})
    if not rendered: blockers.append({'severity':'P1','code':'FULL_RELEASE_TTS_RENDER_FINAL_MATRIX_PENDING'})
    blockers += [{'severity':'P1','code':'LEGACY_WINDOWS_BASELINE_NOT_PASS_SCOPE_DECISION_REQUIRED'},{'severity':'P2','code':'PROVIDER_AMBIGUOUS_RESPONSE_PRESERVED_EXPLICIT_LOCAL_EDITORIAL_DRAFT'},{'severity':'P2','code':'TRANSCRIPT_ACCURACY_PACING_PLATFORM_AND_REFERENCE_ASSETS_REVIEW'}]
    status='WAITING_ACTUAL_HUMAN_SCRIPT_REVIEW' if approved<10 else 'WAITING_ACTUAL_HUMAN_WATCH_LISTEN_REVIEW' if rendered and completed<10 else 'AWAITING_RELEASE_CERTIFICATION' if rendered else real.get('status','WAITING_CANDIDATE_RENDER')
    # This draft capture never issues a certificate. The separate certifier reads
    # the real outputs, checkpoints, decisions and scope authorization afresh.
    report={'INTERNAL_PRODUCTION_READY':'NO','status':status,'certification_report':'release-certification.json','technical_draft_preparation':'PASS','technical_render_matrix':'PASS' if rendered else 'PENDING','required_inputs_present':ready_inputs,'cases':rows,'checks':checks,'new_content_provider_attempts':sum(e['provider_calls'] for e in state['cases']),'valid_new_content_provider_results':sum(bool(e.get('provider_response_id')) for e in state['cases']),'failed_provider_attempts':sum(bool(e.get('error_code')) for e in state['cases']),'automatic_paid_replays':0,'new_tts_inferences':real.get('new_real_tts_inference_calls',0),'new_release_final_videos':real.get('successful_jobs',0),'actual_human_script_reviews':approved,'actual_human_final_reviews':completed,'blockers':blockers}
    # Preserve exactly what the human approved; never rewrite that review bundle.
    if not (directory/'owner-script-authorization.json').exists(): (directory/'review-bundle.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    report['review_bundle_sha256']=file_sha(directory/'review-bundle.md'); write_json(directory/'release-gate.json',report)
    state['status']=report['status']; state['new_content_provider_calls']=report['new_content_provider_attempts']; write_json(directory/'review-drafts.json',state)
    print(json.dumps({'drafts':len(rows),'provider_attempts':report['new_content_provider_attempts'],'valid_results':report['valid_new_content_provider_results'],'human_script_approvals':approved,'human_final_approvals':completed,'release_ready':'NO'}))

if __name__=='__main__': main()
