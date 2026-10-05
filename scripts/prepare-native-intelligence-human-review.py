"""Present concrete ranked candidates/brief previews; never select or approve for Owner."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
from services.windows_native.contracts import canonical,digest,file_sha
from services.windows_native.pipeline import Config
from services.windows_native.store import Store
from services.windows_native.intelligence_service import IntelligenceService,draft_brief_fields

repo=Path(__file__).resolve().parents[1];directory=repo/'evidence/post-mvp-roadmap/phase-9'; config=Config()
review=directory/'idea-brief-review-bundle.md';manifest=directory/'idea-brief-review-manifest.json'
if review.exists() or manifest.exists(): raise SystemExit('Human review bundle is immutable; create a new named revision if needed')
records=json.loads((directory/'practical-cases.json').read_bytes());service=IntelligenceService(config,Store(config.data_root))
lines=['# Phase 9 — chọn ý tưởng và duyệt brief','',
       'Đây là bộ mới của Phase 9. Chưa có ý tưởng hay brief nào được Owner duyệt. Không kế thừa quyết định duyệt 10 video Phase 8.',
       '', 'Đề nghị xem đủ 10 ca và chọn ít nhất 5 để thử sản xuất. Nhóm đề xuất ban đầu: **01, 02, 04, 06, 08**, mỗi ca chọn **ý tưởng xếp hạng 1**. Có thể chọn ca/ý tưởng khác hoặc sửa trực tiếp trong Studio.',
       '', 'Điểm là HEURISTIC_SCORING, chưa dự đoán lượt xem/lead. Nguồn đã nêu không có nghĩa đã xác minh độc lập. Ngày lấy mới không biến nguồn cũ thành tin mới. Cần duyệt riêng kịch bản/media và xem/nghe video cuối sau bước này.', '']
items=[]
for record in records:
    b=service.bundle(record['run_id']);assert len(b['ideas'])==5 and b['run']['status']=='IDEAS'
    idea=b['ideas'][0];fields=draft_brief_fields(idea,b['findings'])
    item={'number':record['number'],'run_id':b['run']['id'],'run_version':b['run']['version'],'proposed_idea_id':idea['id'],'idea_version':idea['version'],'opportunity_version':b['opportunity']['version'],'proposed_rank':1,'brief_preview':fields,'brief_preview_sha256':digest(fields),'bundle_sha256':digest(b),'source_hashes':{s['id']:s['content_sha256'] for s in b['sources']},'human_selection':'PENDING','human_brief_approval':'PENDING'}
    items.append(item)
    lines+= [f"## {record['number']:02} — {b['run']['context']['profile']['name']}",'',b['run']['query'],'',f"[Mở ca này trong Studio](http://127.0.0.1:8026/intelligence?run={b['run']['id']})",'', '| Hạng | Tiêu đề | Hook | Điểm |','|---|---|---|---|']
    for rank,c in enumerate(b['ideas'],1): lines.append(f"| {rank} | {c['title'].replace('|','/')} | {c['hook'].replace('|','/')} | {c['score']['final_score']:.1f} |")
    lines+=['','### Brief đề xuất cho ý tưởng hạng 1','',f"**Người xem:** {fields['audience']}",f"**Mục tiêu:** {fields['objective']}",f"**Góc nhìn:** {fields['angle']}",f"**Hook:** {fields['hook']}",f"**Định dạng/thời lượng:** {idea['format']} · {idea['estimated_duration']} giây",f"**CTA:** {fields['cta']}",'','**Ý chính đề xuất:**','']+['- '+p for p in fields['talking_points']]
    lines+=['','**Dữ kiện nguyên văn của nguồn cần kiểm tra:**','']+['> '+f.replace('\n','\n> ') for f in fields['key_facts']]
    lines+=['','**Nguồn và thời điểm:**','']+[f"- [{s['title']}]({s['reference']}) · ngày công bố {s['timestamp'] or 'chưa rõ'} · lấy {s['retrieved_at']}" for s in b['sources']]
    lines+=['','**Giới hạn:**','']+['- '+c for c in fields['constraints']]+['']
    record['agent_evaluation']={'reviewer':'Codex editorial assessment; NOT human acceptance','research_usefulness':'Provides attributable excerpts and unresolved limits; not comprehensive market research','factual_grounding':'Exact quotation/hash/source checks PASS; independent truth verification not claimed','idea_usefulness':'Five distinct candidate titles with evidence; human suitability PENDING','ranking_usefulness':'Transparent ten proxies; unknown dates penalized; human usefulness PENDING','hook_quality':'Candidate wording is inspectable; human quality judgment PENDING','cta_relevance':'Profile keyword heuristic; conversion not predicted','production_feasibility':'Native short-video format compatible; source media/rights and measured voice duration still need review'}
review.write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
manifest.write_bytes(canonical({'scope':'Phase 9 idea selection and brief review only','proposed_case_numbers':[1,2,4,6,8],'cases':items,'review_bundle_sha256':file_sha(review),'human_acceptance':'PENDING','production_dispatches':0}))
(directory/'practical-cases.json').write_bytes(canonical(records))
print(json.dumps({'cases':len(items),'candidates':sum(5 for _ in items),'human_acceptance':'PENDING','review_bundle_sha256':file_sha(review)}))
