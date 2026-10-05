"""Prepare real, unapproved release drafts; never sign human approvals or run TTS.

Uses the running production worker and existing provider/voice configuration.
Creates append-only review projects and an incremental recovery manifest.
"""
import copy
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

REPO=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(REPO))
from services.windows_native.contracts import digest,file_sha,write_json
from services.windows_native.ingestion import ingest_document
from services.windows_native.media import ingest_media,media_path,project_assets
from services.windows_native.pipeline import Config
from services.windows_native.store import Store,now

MANIFEST=REPO/'evidence/post-mvp-roadmap/phase-8/review-drafts.json'
SOURCE=Path(r'C:\NPD-Video-Factory\outputs\MVP1')
ASR_ROOT=Path(r'C:\NPD-Video-Factory\post-mvp-validation\phase4-real-asr-20261005-2025')
ASR_PROJECT='0f6e5be8c2a64ed6b6bf71abc684ccfb'
OWNER_PROJECT='3a9a98846f14467fba72a6da18ca6276'

CASES=[
 ('prompt','Prompt — đọc đúng ghi chú minh họa','prompt','ngoc-phuong-dong','property-30','Cách xem ghi chú phối cảnh minh họa trong video giới thiệu. Không mô tả hay suy đoán nội dung cụ thể của ảnh.',('portrait',)),
 ('idea','Ý tưởng — giữ bản nháp rõ ràng','idea','vang-nguyen','personal-30','Ý tưởng: chia sẻ cách phân biệt bản nháp nội dung với một video đã được con người kiểm tra. Không khẳng định độ chính xác của dữ kiện.',('portrait',)),
 ('script','Kịch bản có sẵn — đối chiếu bản MVP','script','ngoc-phuong-dong','property-30','',('portrait',)),
 ('image','Ảnh — trình bày nguồn minh họa','prompt','ngoc-phuong-dong','property-30','Có một ảnh minh họa đã được xác nhận quyền sử dụng. Chia sẻ cách đọc chú thích nguồn, giữ nhãn minh họa và đặt câu hỏi khi chưa có dữ kiện. Không nhận diện vật thể hay vị trí trong ảnh.',('portrait',)),
 ('multiple_images','Nhiều ảnh — đối chiếu nguồn','prompt','ngoc-phuong-dong','property-30','Hai nguồn ảnh minh họa: ảnh của bản MVP và một khung hình trích từ video người dùng đã tải. Giới thiệu cách giữ ghi chú xuất xứ và đối chiếu từng nguồn; không mô tả nội dung ảnh từ tên file.',('portrait','frame')),
 ('silent_video','Video không lời — kiểm tra cảnh và chữ','prompt','vang-nguyen','news-30','Video nguồn đã tắt âm thanh. Chia sẻ cách kiểm tra thứ tự cảnh và chữ trước khi thêm lời đọc mới. Không mô tả vật thể, thời điểm hay sự kiện từ video.',('silent',)),
 ('speech_video','Video có lời — duyệt transcript thật','media','ngoc-phuong-dong','property-30','',('speech',)),
 ('mixed_media','Nguồn hỗn hợp — giữ xuất xứ rõ ràng','prompt','ngoc-phuong-dong','property-30','Ảnh, video không lời và ghi chú nguồn được dùng chung. Chia sẻ cách giữ xuất xứ, nhãn minh họa, kiểm tra lời đọc và chữ cho từng cảnh; không suy đoán nội dung hình.',('portrait','silent')),
 ('document','Tài liệu — lời đọc theo ghi chú nguồn','prompt','vang-nguyen','personal-30','Dựa vào ghi chú nguồn đính kèm, tạo lời đọc giới thiệu cách đội nội dung kiểm tra bản nháp trước khi duyệt. Không bổ sung dữ kiện về dự án, thị trường hay sự kiện.',('portrait',)),
 ('multiple_videos','Nhiều video — kiểm tra từng nguồn','prompt','vang-nguyen','personal-30','Hai video minh họa: nguồn người dùng đã xác nhận quyền sử dụng và bản MVP đã nghiệm thu. Lời nói gốc không dùng làm lời đọc mới. Chia sẻ cách kiểm tra ghi chú nguồn và trật tự cảnh trước khi duyệt; không suy đoán nội dung hình.',('silent','speech')),
]


def main():
    config=Config(); store=Store(config.data_root)
    MANIFEST.parent.mkdir(parents=True,exist_ok=True)
    if MANIFEST.exists():
        state=json.loads(MANIFEST.read_bytes())
        assert state['data_root']==str(config.data_root)
    else:
        assert not any(p['document']['name'].startswith('Release 0') or p['document']['name'].startswith('Release 10') for p in store.list(True)), 'Existing release drafts need explicit recovery inventory'
        state={'schema_version':'release-review-v1','data_root':str(config.data_root),'status':'PREPARING','human_approvals':0,'new_tts_inferences':0,'cases':[],'sources':{}}
        write_json(MANIFEST,state)
    owner=store.get(OWNER_PROJECT); assert owner['revision']==9 and owner['approval'] is None
    oldvideo=next(a for a in project_assets(owner['document']) if a['kind']=='video')
    assert oldvideo['rights_confirmed'] is True and oldvideo['illustration'] is True
    assert file_sha(media_path(config,oldvideo['id']))==oldvideo['sha256']
    assert file_sha(SOURCE/'final.mp4')=='c0bbcf029554cfd2e7c29e05d595379abb6d894babc78154a16537f7fba1a47a'
    work=Path(r'C:\NPD-Video-Factory\post-mvp-validation\phase8-review-inputs-20261005'); work.mkdir(exist_ok=True)
    sources=state['sources']
    if 'portrait' not in sources:
        sources['portrait']=ingest_media(config,SOURCE/'portrait-source.jpg','image/jpeg','MVP — ảnh minh họa.jpg',rights_confirmed=True,illustration=True)
        sources['portrait']['release_source_lineage']={'path':str(SOURCE/'portrait-source.jpg'),'sha256':file_sha(SOURCE/'portrait-source.jpg'),'rights_source':'existing accepted MVP Owner media receipt'}
        write_json(MANIFEST,state)
    for kind in ('frame','silent'):
        if kind in sources: continue
        target=work/('source-frame.jpg' if kind=='frame' else 'source-silent.mp4')
        if not target.exists():
            args=['-ss','1','-i',str(media_path(config,oldvideo['id'])),'-frames:v','1'] if kind=='frame' else ['-i',str(media_path(config,oldvideo['id'])),'-t','6','-map','0:v:0','-an','-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-movflags','+faststart']
            subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error',*args,str(target)],check=True)
        sources[kind]=ingest_media(config,target,'image/jpeg' if kind=='frame' else 'video/mp4',target.name,rights_confirmed=True,illustration=True)
        sources[kind]['release_source_lineage']={'project_id':OWNER_PROJECT,'source_sha256':oldvideo['sha256'],'operation':'frame at 1 second' if kind=='frame' else 'first 6 seconds, audio removed','historical_original_upload_bytes_missing':not bool(oldvideo.get('original_id')),'rights_source':'existing Owner uploaded media rights confirmation'}
        write_json(MANIFEST,state)
    if 'speech' not in sources:
        real=Store(ASR_ROOT).get(ASR_PROJECT)
        speech=next(a for a in project_assets(real['document']) if a['kind']=='video')
        assert file_sha(ASR_ROOT/'assets'/speech['id'])==speech['sha256']==file_sha(SOURCE/'final.mp4')
        for field,folder in (('id','assets'),('thumbnail_id','assets'),('original_id','originals')):
            if speech.get(field):
                origin=ASR_ROOT/folder/speech[field]; dest=config.data_root/folder/speech[field]; dest.parent.mkdir(exist_ok=True)
                if dest.exists(): assert file_sha(dest)==file_sha(origin)
                else: shutil.copyfile(origin,dest)
        sources['speech']=speech
        state['speech_analysis']=copy.deepcopy(next(r for r in real['document']['media_analysis'] if r['asset_id']==speech['id']))
        state['speech_analysis_lineage']={'source_root':str(ASR_ROOT),'source_project':ASR_PROJECT,'source_job':'6ce8ff08f2d74dbabfbdb1171a5b2e64','new_provider_requests':0,'copied_record_without_edit':True,'source_sha256':speech['sha256'],'original_transcript_unverified':True}
        write_json(MANIFEST,state)
    if 'document' not in sources:
        target=work/'ghi-chu-nguon.md'
        if not target.exists(): target.write_text('Ghi chú cho đợt duyệt nội bộ: media dùng để minh họa; không có dữ kiện dự án mới được xác minh. Giữ xuất xứ từng nguồn. Kiểm tra chữ, lời đọc, nhãn minh họa và quyền sử dụng trước khi duyệt. Đổi nguồn hoặc sửa nội dung thì cần duyệt lại. Video cuối phải được xem và nghe trước khi nghiệm thu. Hồ sơ thương hiệu hiện là cấu hình tham chiếu, chưa có logo chính thức.',encoding='utf-8')
        sources['document']=ingest_document(config,target,'text/markdown',target.name); write_json(MANIFEST,state)
    for index,(family,title,input_kind,brand,template,brief,assets) in enumerate(CASES,1):
        entry=next((e for e in state['cases'] if e['number']==index),None)
        if entry is None:
            text=json.loads((SOURCE/'content-proposal.json').read_bytes())['narration'] if input_kind=='script' else '' if input_kind=='media' else brief+' Viết 75–95 từ tiếng Việt cho video 30 giây, ba cảnh, chữ mỗi cảnh tối đa 7 từ; nội dung bình tĩnh, không thêm số liệu, giá, pháp lý, tiến độ, lời hứa hoặc tin tức chưa có nguồn. Dùng giọng Thùy Dung và CTA tham chiếu của hồ sơ đã chọn. Đây là bản nháp để con người kiểm tra.'
            p=store.create(f'Release {index:02} · {title}',text,input_kind)
            entry={'number':index,'input_family':family,'title':p['document']['name'],'project_id':p['id'],'source_keys':list(assets),'brand_id':brand,'template_id':template,'state':'CREATED_UNAPPROVED'}
            state['cases'].append(entry); write_json(MANIFEST,state)
        p=store.get(entry['project_id'])
        if entry['state']=='CREATED_UNAPPROVED':
            for key in assets:
                if sources[key]['id'] not in {a['id'] for a in project_assets(p['document'])}: p=store.append_media(p['id'],p['revision'],copy.deepcopy(sources[key]))
            if family in ('mixed_media','document') and not p['document']['documents']: p=store.append_document(p['id'],p['revision'],sources['document'])
            if 'speech' in assets and not p['document'].get('media_analysis'):
                with store.transaction() as con:
                    current=store.editable(con,p['id'],p['revision']); doc=current['document']
                    doc['media_analysis']=[copy.deepcopy(state['speech_analysis'])]
                    doc['release_analysis_import']=state['speech_analysis_lineage']
                    con.execute('UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?',(p['revision']+1,json.dumps(doc,ensure_ascii=False),now(),p['id']))
                    store.version(con,p['id']); store.event(con,p['id'],'release_existing_real_analysis_imported',state['speech_analysis_lineage'])
                p=store.get(p['id'])
            if not p['document'].get('brand_template'): p=store.set_brand(p['id'],p['revision'],brand,template)
            request_key='phase8-review-'+p['id']
            job=store.enqueue(p['id'],p['revision'],'content',request_key)
            entry.update(state='CONTENT_DISPATCHED',job_id=job['id']); write_json(MANIFEST,state)
        if entry['state']=='CONTENT_DISPATCHED':
            deadline=time.monotonic()+240
            while time.monotonic()<deadline:
                job=store.get_job(entry['job_id'])
                if job['status'] not in ('queued','running','retrying'): break
                time.sleep(.5)
            if job['status']!='awaiting_review':
                entry.update(state='CONTENT_FAILED_NEEDS_EXPLICIT_REVIEW',error_code=(job.get('error') or {}).get('code'),revision=p['revision'],provider_calls=len(list((config.data_root/'jobs'/job['id']).glob('content*.intent.json'))),human_script_approved=False,human_final_approved=False,render_jobs=0)
                write_json(MANIFEST,state)
                print(json.dumps({'number':index,'state':entry['state'],'error_code':entry['error_code'],'automatic_paid_replay':False}),flush=True)
                continue
            p=store.get(p['id'])
            if not p['document'].get('edit_plan'): p=store.auto_plan(p['id'],p['revision'])
            assert p['approval'] is None and p['document']['edit_plan']
            entry.update(state='WAITING_ACTUAL_HUMAN_SCRIPT_REVIEW',revision=p['revision'],document_sha256=digest(p['document']),narration=p['document']['proposal']['narration'],facts_needing_source=p['document']['proposal']['facts_needing_source'],provider_calls=job['result'].get('provider_calls',0),provider_response_id=job['result'].get('response_id'),human_script_approved=False,human_final_approved=False,render_jobs=0)
            write_json(MANIFEST,state)
        print(json.dumps({'number':index,'state':entry['state'],'provider_calls':entry.get('provider_calls',0)}),flush=True)
    state['status']='WAITING_ACTUAL_HUMAN_SCRIPT_REVIEW_WITH_PROVIDER_FAILURE_PRESERVED' if any(e.get('error_code') for e in state['cases']) else 'WAITING_ACTUAL_HUMAN_SCRIPT_REVIEW'; state['new_content_provider_calls']=sum(e['provider_calls'] for e in state['cases']); write_json(MANIFEST,state)


if __name__=='__main__': main()
