"""Prepare static graphics and a human media review; never dispatch production."""
from pathlib import Path
import copy
from datetime import datetime, timezone
import hashlib
import html
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw,ImageFont
from services.windows_native.contracts import Proposal,digest,file_sha,write_json
from services.windows_native.pipeline import Config,wrap_text
from services.windows_native.store import Store

REPO=Path(__file__).resolve().parents[1]
EVIDENCE=REPO/'evidence/post-mvp-roadmap/phase-9/9k'
GALLERY=EVIDENCE/'storyboard-media-review'
FONTS=Path(r'C:\Windows\Fonts')
FONT_FILES={'heading':FONTS/'seguisb.ttf','body':FONTS/'segoeui.ttf'}


def read(path): return json.loads(path.read_bytes())


def font(size,bold=False): return ImageFont.truetype(str(FONT_FILES['heading' if bold else 'body']),size)


def text(draw,value,x,y,width,size,color,bold=False,max_lines=None):
    face=font(size,bold);lines=wrap_text(value,face,width)
    if max_lines and len(lines)>max_lines:
        if size<=30: raise ValueError('Graphic text does not fit: '+value)
        return text(draw,value,x,y,width,size-2,color,bold,max_lines)
    draw.multiline_text((x,y),'\n'.join(lines),font=face,fill=color,spacing=12)
    box=draw.multiline_textbbox((x,y),'\n'.join(lines),font=face,spacing=12)
    assert box[2]<=901,'Graphic text exceeds the safe right margin'
    return box[3]


def graphic(card,palette,source_label):
    image=Image.new('RGB',(1080,830),palette['background']);draw=ImageDraw.Draw(image)
    draw.line((90,50,900,50),fill=palette['accent'],width=3)
    text(draw,card['tag'],90,77,810,27,palette['muted'],True,2)
    kind=card['kind'];items=card['items']
    if kind=='statement':
        bottom=text(draw,items[0],90,160,810,66,palette['text'],True,4)
        text(draw,items[1],90,max(465,bottom+38),810,43,palette['accent'],False,3)
    elif kind=='date':
        draw.rounded_rectangle((90,155,900,475),radius=28,fill=palette['panel'])
        text(draw,items[0],125,200,730,88,palette['accent'],True,1)
        text(draw,items[1],125,345,730,40,palette['text'],False,2)
        text(draw,items[2],90,550,810,34,palette['muted'],False,2)
    elif kind=='list':
        height=112 if len(items)==4 else 146
        for index,value in enumerate(items):
            y=153+index*height
            draw.rounded_rectangle((90,y,900,y+height-18),radius=20,fill=palette['panel'])
            text(draw,f'{index+1:02}',115,y+20,60,30,palette['accent'],True,1)
            text(draw,value,194,y+17,690,42,palette['text'],True,2)
    elif kind=='compare':
        for index,value in enumerate(items):
            x=90+index*417
            draw.rounded_rectangle((x,165,x+393,535),radius=25,fill=palette['panel'])
            text(draw,value,x+24,207,345,41,palette['text'],True,5)
        text(draw,card.get('note',''),90,580,810,38,palette['accent'],False,3)
    elif kind=='metrics':
        text(draw,items[0],90,146,810,104,palette['accent'],True,1)
        text(draw,items[1],90,275,810,35,palette['text'],False,2)
        for index,row in enumerate(card['comparison_rows']):
            assert 0<=row['value']<=1
            y=390+index*150
            text(draw,row['label'],90,y,810,31,palette['muted'],False,1)
            draw.rounded_rectangle((90,y+58,720,y+91),radius=9,fill=palette['panel'])
            draw.rounded_rectangle((90,y+58,90+round(630*row['value']),y+91),radius=9,fill=palette['accent'])
            text(draw,row['display'],750,y+42,150,36,palette['text'],True,1)
    else: raise ValueError('Unknown graphic kind')
    if kind=='list' and card.get('note'):
        text(draw,card['note'],90,635,810,31,palette['accent'],False,2)
    text(draw,source_label,90,740,810,27,palette['muted'],False,2)
    return image


def preview(asset,scene,number):
    palette=read(EVIDENCE/'storyboard-graphic-directions.json')['style']
    image=Image.new('RGB',(1080,1920),palette['background']);draw=ImageDraw.Draw(image)
    text(draw,f"VIDEO FACTORY  /  {scene['scene']:02}",90,160,810,28,palette['accent'],False,1)
    face=font(60,True);lines=wrap_text(scene['on_screen_text'],face,810)
    assert len(lines)<=2
    title_bottom=text(draw,scene['on_screen_text'],90,225,810,60,palette['text'],True,2)
    assert title_bottom<390
    image.paste(asset,(0,390))
    draw.rounded_rectangle((80,1320,910,1550),radius=18,fill='#071918',outline='#5d6653',width=2)
    caption=scene['narration_excerpt']
    face=font(46);lines=wrap_text(caption,face,790)
    sample='\n'.join(lines[:3])+('…' if len(lines)>3 else '')
    draw.multiline_text((100,1350),sample,font=face,fill=palette['text'],spacing=12)
    return image


def main():
    assert not (GALLERY/'review-manifest.json').exists(),'Review already frozen; create a new version for edits'
    directions=read(EVIDENCE/'storyboard-graphic-directions.json')
    approval=read(EVIDENCE/'script-approval-manifest.json')
    assert approval['human_script_approvals']==5
    GALLERY.mkdir(parents=True,exist_ok=True)
    production=Store(Config().data_root);case_records=[];markup=[]
    font_hashes={key:file_sha(path) for key,path in FONT_FILES.items()}
    for config in directions['cases']:
        number=config['number'];folder=EVIDENCE/f'case-{number:02}';output=GALLERY/f'case-{number:02}'
        (output/'assets').mkdir(parents=True,exist_ok=True)
        script=read(folder/'script-v2.json');research=read(folder/'research.json')
        project=production.get(script['project_id']);review=project['script_review']
        assert review['current'] and review['script_sha256']==script['script_sha256']
        assert project['document']['proposal']==script['proposal'] and project['approval'] is None
        assert all(j['kind']=='content' for j in project['jobs'])
        candidate=copy.deepcopy(script['proposal']);scene_records=[];assets=[];previews=[];rows=[]
        source=research['sources'][0]
        source_label='Nguồn: '+('Báo Điện tử Chính phủ' if 'baochinhphu.vn' in source['reference'] else 'Vinhomes Market')
        for original,card in zip(candidate['visual_brief'],config['cards'],strict=True):
            scene_number=original['scene'];original['on_screen_text']=card['heading']
            original['visual']='Đồ họa chữ/số liệu tự tạo; giữ toàn khung, không chuyển động; '+card['tag']
            asset=graphic(card,directions['style'],source_label)
            path=output/'assets'/f'scene-{scene_number:02}.png';asset.save(path)
            preview_path=output/f'scene-{scene_number:02}-preview.png'
            frame=preview(asset,original,number);frame.save(preview_path);previews.append(frame)
            identifier=f'phase9k-{number:02}-scene-{scene_number:02}-graphic-v1'
            metadata={'proposed_asset_id':identifier,'native_asset_id':None,'path':str(path),
                'sha256':file_sha(path),'kind':'image','mime':'image/png','width':1080,'height':830,
                'preview_path':str(preview_path),'preview_sha256':file_sha(preview_path),
                'origin':'locally_authored_text_and_shape_graphic','authoring_tool':'Pillow, deterministic local drawing',
                'recipe':card,'recipe_sha256':digest(card),'font_hashes':font_hashes,
                'fonts_included_in_deliverable':False,'photo_or_official_logo_used':False,
                'research_source_references':[{'id':s['id'],'reference':s['reference'],'content_sha256':s['content_sha256']} for s in research['sources']],
                'script_sha256':script['script_sha256'],'rights_review':'PENDING_OWNER','media_approved':False,
                'uploaded_to_native':False,'illustration':False,'description':'Original text graphic, not a project rendering/photo'}
            assets.append(metadata)
            scene_records.append({**original,'proposed_asset_id':identifier,'asset_sha256':metadata['sha256'],
                'production_options':directions['production_options'],'human_approved':False,
                'source_references':metadata['research_source_references'],
                'narration_is_unchanged_approved_script_excerpt':True,'duration_status':'WAITING_FOR_MEASURED_VOICE'})
            rows.append(f'<article class="scene"><img src="case-{number:02}/scene-{scene_number:02}-preview.png" alt="Ca {number:02}, cảnh {scene_number}" loading="lazy"><div><b>Cảnh {scene_number} · {html.escape(card["heading"])}</b><p>{html.escape(original["narration_excerpt"])}</p></div></article>')
        Proposal.model_validate(candidate)
        assert candidate['narration']==script['proposal']['narration']
        write_json(folder/'proposed-production-proposal.json',candidate)
        write_json(folder/'storyboard.json',{'status':'PROPOSED_FOR_HUMAN_REVIEW','version':3,
            'approved_script_version':2,'script_sha256':script['script_sha256'],'script_review_id':review['review_id'],
            'native_project_id':project['id'],'native_project_revision_before_media':project['revision'],
            'proposed_proposal_sha256':digest(candidate),'scenes':scene_records,'human_approved':False,
            'duration_target':config['duration_target'],'timing_measured':False,'production_dispatched':False})
        write_json(folder/'asset-lineage.json',{'status':'PROPOSED_GRAPHICS_PENDING_OWNER_REVIEW','version':1,
            'assets':assets,'human_approved':False,'rights_confirmation_recorded':False,
            'proposed_music':'NONE','proposed_native_import':False})
        write_json(folder/'render-manifest.json',{'status':'NOT_REQUESTED_STORYBOARD_MEDIA_REVIEW_REQUIRED',
            'job_id':None,'final_mp4':None,'ffprobe_status':'NOT_RUN','human_approved':False,'script_approved':True})
        contact=Image.new('RGB',(1350,480),directions['style']['background'])
        for index,frame in enumerate(previews): contact.paste(frame.resize((270,480),Image.Resampling.LANCZOS),(index*270,0))
        contact_path=output/'contact-sheet.png';contact.save(contact_path)
        case_records.append({'case':number,'project_id':project['id'],'native_project_revision':project['revision'],
            'script_version':2,'script_sha256':script['script_sha256'],'script_review_id':review['review_id'],
            'storyboard_sha256':file_sha(folder/'storyboard.json'),'asset_lineage_sha256':file_sha(folder/'asset-lineage.json'),
            'proposed_proposal_sha256':digest(candidate),'contact_sheet_path':str(contact_path),
            'contact_sheet_sha256':file_sha(contact_path),'asset_count':5,'assets':assets,
            'human_storyboard_review':'PENDING','human_media_review':'PENDING','production_approval':False})
        markup.append(f'<section id="case-{number:02}"><h2>Ca {number:02} · {html.escape(config["title"])}</h2><p class="meta">Lời đọc v2 đã duyệt · mục tiêu {config["duration_target"]} · 5 cảnh chờ duyệt hình ảnh/cách dựng</p><div class="grid">'+''.join(rows)+f'</div><p>Nguồn: <a href="{html.escape(source["reference"],quote=True)}">{html.escape(source["title"])}</a> · <a href="http://127.0.0.1:8026/?project={project["id"]}">Dự án trong Studio</a></p></section>')
        print(json.dumps({'case':number,'script':'OWNER_APPROVED_V2','proposed_graphics':5,
                          'native_media_imports':0,'human_media_review':'PENDING','tts_render_dispatches':0}),flush=True)
    page='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Phase 9K · Duyệt hình ảnh và storyboard</title><style>
    *{box-sizing:border-box}body{margin:0;background:#f5f6f2;color:#173a31;font:16px/1.6 "Segoe UI",sans-serif}header,main{max-width:1480px;margin:auto;padding:28px}header{background:#e8eee7}h1{font-size:30px;margin:0}h2{font-size:24px}nav{display:flex;flex-wrap:wrap;gap:12px}a{color:#176d55}nav a{padding:8px 14px;background:white;border-radius:8px}.meta{color:#4b635a}.note{padding:15px;background:#fff7dd;border-radius:12px}.grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px}.scene{background:white;border-radius:14px;overflow:hidden;box-shadow:0 3px 13px #0c332113}.scene img{width:100%;display:block}.scene div{padding:14px}.scene b{font-size:15px}.scene p{font-size:14px;margin-bottom:0}section{margin-bottom:45px;scroll-margin-top:18px}@media(max-width:1100px){.grid{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:700px){.grid{grid-template-columns:1fr}header,main{padding:18px}.scene img{max-height:650px;object-fit:contain;background:#09211f}}@media print{.grid{grid-template-columns:repeat(3,1fr)}section{break-before:page}.scene{break-inside:avoid}}
    </style><header><h1>25 cảnh cho 5 kịch bản đã duyệt</h1><p>Lời đọc v2: 01 · 02 · 04 · 06 · 08 đã được Owner duyệt.</p><nav>'''+''.join(f'<a href="#case-{c["case"]:02}">Ca {c["case"]:02}</a>' for c in case_records)+'''</nav><p class="note">Đây là ảnh bố cục tĩnh để duyệt storyboard và hình ảnh. Chưa có giọng đọc/video; phụ đề hiển thị mẫu, chưa đo thời gian. Đồ họa chữ/số liệu được tạo tại máy; không dùng ảnh dự án, logo chính thức hoặc chân dung. Đề xuất giữ hình yên, chuyển cảnh mờ nhẹ, không nhạc nền.</p></header><main>'''+''.join(markup)+'''<p class="note">Sau khi xem, Owner có thể duyệt storyboard/media 01, 02, 04, 06, 08 hoặc yêu cầu sửa từng cảnh. Quyền sử dụng đồ họa và việc đưa chúng vào sản xuất đang chờ quyết định này. Chưa có hành động xuất bản.</p></main></html>'''
    (GALLERY/'index.html').write_text(page,encoding='utf-8',newline='\n')
    review_manifest={'status':'PHASE9K_STORYBOARD_MEDIA_REVIEW_REQUIRED',
        'created_at':datetime.now(timezone.utc).isoformat(),'owner_script_approval_sha256':file_sha(EVIDENCE/'script-approval-manifest.json'),
        'graphic_directions_sha256':file_sha(EVIDENCE/'storyboard-graphic-directions.json'),
        'review_html_sha256':file_sha(GALLERY/'index.html'),'cases':case_records,'asset_count':25,
        'native_media_imports':0,'human_media_approvals':0,'tts_runs':0,'render_dispatches':0,'new_video_count':0}
    lines=['# Phase 9K — Duyệt storyboard và hình ảnh','',
        'PHASE9K_STORYBOARD_MEDIA_REVIEW_REQUIRED','',
        'Năm lời đọc v2 đã được Owner duyệt. Đây là 25 cảnh đồ họa chữ/số liệu để duyệt tiếp. '
        'Lời đọc giữ nguyên; chữ trên cảnh được rút gọn cho vùng an toàn. Chưa có TTS/video. '
        'Đề xuất giữ toàn hình, không chuyển động, chuyển cảnh mờ nhẹ và không nhạc nền.','',
        f'[Mở bộ 25 cảnh](<{GALLERY.as_posix()}/index.html>)','']
    for record in case_records:
        case=record['case']; config=next(c for c in directions['cases'] if c['number']==case)
        lines += [f'## Ca {case:02} — {config["title"]}','',
            f'![Năm cảnh đề xuất](<{Path(record["contact_sheet_path"]).as_posix()}>)','',
            f'Mục tiêu {config["duration_target"]}; thời gian chưa đo. Script v2 SHA256 `{record["script_sha256"]}`.','',
            '| Cảnh | Chữ trên cảnh | Hình xem trước |','|---|---|---|']
        for index,card in enumerate(config['cards'],1):
            path=(GALLERY/f'case-{case:02}'/f'scene-{index:02}-preview.png').as_posix()
            lines.append(f'| {index} | {card["heading"]} | [Mở hình]({path}) |')
        lines += ['']
    lines += ['Owner có thể trả lời “Duyệt storyboard/media đồ họa: 01, 02, 04, 06, 08” hoặc nêu ca/cảnh cần sửa. '
              'Quyết định gồm quyền dùng các đồ họa tự tạo đã xem, cách dựng đề xuất và cho phép tiếp tục sản xuất nội bộ theo pipeline hiện có. '
              'Video cuối vẫn cần Owner xem/nghe và duyệt riêng; không có publishing.','',
              'INTERNAL_PRODUCTION_READY = YES','','CONTENT_INTELLIGENCE_READY = NO','']
    (EVIDENCE/'storyboard-media-review-bundle.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    review_manifest['review_bundle_sha256']=file_sha(EVIDENCE/'storyboard-media-review-bundle.md')
    write_json(GALLERY/'review-manifest.json',review_manifest)


if __name__=='__main__': main()
