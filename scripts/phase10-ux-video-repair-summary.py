"""Read-only current-five evidence, keeping historical repairs and actual costs."""
import importlib.util
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
spec=importlib.util.spec_from_file_location('ux_video_repair',REPO/'scripts/phase10-ux-video-repair.py')
repair=importlib.util.module_from_spec(spec);spec.loader.exec_module(repair)
from services.windows_native.contracts import file_sha
from services.windows_native.intelligence_lineage import projection
from services.windows_native.media import project_assets

JOBS={'01':'24cc405c95eb4a4a9b3d68b665cbc45e','02':'6ac1fa1d462746dbab5538979dc47c40',
      '04':'b1eaffa4c70d4cdca5f38750f6061cc8','06':'4bbaf04f737249ccb28358467fc050a3','08':'bb9b5668627c4a8681e23549e92679da'}
FIRST_02='8ae69c0e60404b2496d93b227a9a0715'
DATA=Path('C:/NPD-Video-Factory/phase10-uat/jobs')
def read(path):return json.loads(Path(path).read_bytes())
def counts(voice):
    p=voice['provider_requests_this_attempt']
    return {'fresh_inference':voice['new_inference_calls'],'reused_inference':voice['reused_inference_calls'],
            'uploads':p['upload_requests'],'transcript_creates':p['transcript_create_requests'],'observes':p['observe_requests']}
def add(total,value):
    for key in total:total[key]+=value[key]

def main():
    api=repair.API(); rows=[]; total=dict.fromkeys(('fresh_inference','reused_inference','uploads','transcript_creates','observes'),0)
    for case,jid in JOBS.items():
        project=api.request('GET','/api/projects/'+repair.CASES[case]['project'])
        job=next(j for j in project['jobs'] if j['id']==jid)
        assert job['status']=='succeeded' and job.get('final_review') is None
        assert project['revision']==job['revision'] and project['document']==job['snapshot']['document']
        doc=job['snapshot']['document']; folder=DATA/jid
        voice=read(folder/'voice.json'); rendered=read(folder/'render-voice.json'); manifest=read(folder/'render-manifest.json'); probe=read(folder/'ffprobe.json')
        original=DATA/repair.CASES[case]['old_job']; old_voice=read(original/'voice.json'); old_doc=read(original/'input.json')['document']
        assert projection(doc)==projection(old_doc) and project_assets(doc)==project_assets(old_doc)
        assert doc['proposal']['facts_needing_source']==old_doc['proposal']['facts_needing_source']
        comparisons=[]
        for a,b in zip(old_voice['sources'],voice['sources']):
            same=a['plan']==b['plan']
            comparisons.append({'scene':b['plan']['scene'],'plan_binding_unchanged':same,
                'old_source_wave_sha256':a['generated']['source_wave_sha256'],'new_source_wave_sha256':b['generated']['source_wave_sha256'],
                'unchanged_wave_bytes':same and a['generated']['source_wave_sha256']==b['generated']['source_wave_sha256']})
        integrity=list((REPO/'evidence/post-mvp-roadmap/phase-10/studio-ux-02/video-repair/videos').glob('*video-'+jid+'*/video-verification.json'))
        assert len(integrity)==1 and read(integrity[0])['passed']
        stream=next(s for s in probe['streams'] if s['codec_type']=='video')
        name=None; diagnostic={}
        if case in ('01','02','04'):
            source=folder/'attempts/tts-000/context-sources/scene-02'; plan=read(source/'plan.json'); timing=read(source/'timing.json')['transcript']
            text=' '.join(s['text'] for s in timing['segments'])
            name='Vinhomes Green Paradise Cần Giờ' if case in ('01','02') else 'Vinhomes Sài Gòn Park'
            diagnostic={'actual_source_text':text,'full_name_string_match':name.casefold() in text.casefold(),
                'project_core_name_string_match':'Vinhomes Green Paradise'.casefold() in text.casefold() if case in ('01','02') else name.casefold() in text.casefold(),
                'canonical_target':plan['target_text'],'phonemes':plan['phonemes'],'source_wave_sha256':file_sha(source/'source.wav'),
                'provider_response_sha256':timing['provenance']['raw_response_sha256'],'word_accuracy_confirmed':False,
                'ASR_diagnostic_is_human_pronunciation_acceptance':False}
        current_counts=counts(voice);add(total,current_counts)
        rows.append({'case':case,'project_id':project['id'],'job_id':jid,'revision':job['revision'],
            'final_path':str(folder/'final.mp4'),'final_sha256':file_sha(folder/'final.mp4'),
            'duration_seconds':float(probe['format']['duration']),'manifest_duration_seconds':manifest['duration_seconds'],
            'width':stream['width'],'height':stream['height'],'voice_placement':manifest['voice_placement'],
            'voice_policy_sha256':voice['quality_policy_sha256'],'duration_policy':manifest['duration_policy'],
            'canonical_narration':doc['proposal']['narration'],'name_diagnostic':diagnostic,
            'source_cache_comparisons':comparisons,'actual_attempt_counts':current_counts,
            'technical_integrity':{'passed':True,'path':str(integrity[0]),'sha256':file_sha(integrity[0])},
            'old_rejected_mp4_sha256':file_sha(original/'final.mp4'),'facts_graphics_research_lineage_exact':True,
            'preparation_actor':job['snapshot']['approval']['reviewer'],'Owner_watch_listen':'PENDING',
            'pronunciation_quality_confirmed':False,'personal_human_acceptance_created':False})
    historical=DATA/FIRST_02
    historical_counts=counts(read(historical/'voice.json')); all_counts=total.copy();add(all_counts,historical_counts)
    preserved=[{'path':str(DATA/config['old_job']/'final.mp4'),'sha256':file_sha(DATA/config['old_job']/'final.mp4')} for config in repair.CASES.values()]
    baseline=read(REPO/'evidence/post-mvp-roadmap/phase-10/baseline.json')
    prior15=[{**v,'unchanged':file_sha(v['path'])==v['sha256']} for v in baseline['accepted_videos']];assert all(v['unchanged'] for v in prior15)
    summary={'captured_at':repair.support.stamp(),'authority':repair.transport.AUTHORITY,'actual_current_five':rows,
        'current_five_actual_attempt_counts':total,'all_six_actual_repair_attempt_counts_including_superseded02':all_counts,
        'superseded_first02':{'job_id':FIRST_02,'path':str(historical/'final.mp4'),'sha256':file_sha(historical/'final.mp4'),
            'retained':True,'duration_seconds':float(read(historical/'ffprobe.json')['format']['duration']),
            'reason':'Material name ASR repetition; explicit new prefix repair authorized by Owner task'},
        'initial_rejected_five_preserved':preserved,'prior15_accepted_preserved':prior15,
        'five_current_technical_integrity_PASS':True,'name_pronunciation_quality':'OWNER_LISTENING_REQUIRED',
        'case02_remaining_ASR_discrepancies':['Cần Giờ recognized cần chờ','Bài viết recognized Bài tiếp'],
        'no_further_automatic_rerender':True,'provider_calls_by_this_summary':0,'app_mutations_by_summary':0,
        'Owner_final_quality_acceptance':'PENDING','personal_human_acceptance_created':False,'published':False}
    api.ledger.save('current-five-repaired-video-summary.json',summary)
    lines=['# Năm video hiện tại để xem và nghe lại','',
           'Các video mới dài khoảng 20–24 giây, kết thúc sau lời đọc và một giây đoạn kết. Giọng B giữ cấu hình đã khóa. Chưa ghi nhận Owner xem/nghe và nghiệm thu.','',
           'Bản 02 đã bỏ cụm tên thương hiệu lặp ở đầu câu. Cần nghe kỹ tên dự án và địa danh Cần Giờ; nhận diện tự động vẫn có chỗ chưa khớp.','']
    for row in rows:
        lines.extend([f"- **{row['case']}** · {row['duration_seconds']:.2f} giây · {row['width']}×{row['height']}: [mở video]({row['final_path'].replace(chr(92),'/')})",''])
    lines.append('Các nguồn, số liệu, đồ họa và cảnh báo về ngày dữ liệu được giữ lại. Video cũ vẫn còn nguyên.')
    with (api.ledger.root/'current-five-review-bundle.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
    print(json.dumps({'evidence':str(api.ledger.root),'current_five':[{k:r[k] for k in ('case','job_id','duration_seconds','width','height')} for r in rows],
        'current_five_counts':total,'all_six_counts':all_counts,'Owner_watch_listen':'PENDING'},ensure_ascii=False))

if __name__=='__main__':main()
