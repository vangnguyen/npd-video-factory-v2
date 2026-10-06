"""Create original sourced campaign graphics and prepare drafts via native HTTP.

This helper cannot approve scripts/media/final videos or dispatch providers,
TTS, or final render. It can prepare silent visual previews. All native writes
use session/origin/CSRF HTTP APIs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('phase10_support', Path(__file__).with_name('phase10-final-uat-support.py'))
support = importlib.util.module_from_spec(spec); spec.loader.exec_module(support)
ACTOR = support.ACTOR
SOURCE_BUNDLE = ROOT / 'evidence/post-mvp-roadmap/phase-10/final-uat/campaign/20261006T120444468268Z-script-bundle-589e2695'
DEFAULT_OUTPUT = ROOT / 'evidence/post-mvp-roadmap/phase-10/final-uat/campaign/media-originals'
FONT_ROOT = Path('C:/Windows/Fonts')
DEFINITIONS = {
    1: {'project_id': 'd3aa854ed0ed552091f513c66642d8a0', 'brand_id': 'ngoc-phuong-dong', 'template_id': 'news-45',
        'topic': 'Green Paradise · IHG', 'title': 'Lời kỳ vọng hay dữ kiện?',
        'sentences': [
            'Lời kỳ vọng có phải là kết quả thực tế? Hãy đọc đúng phạm vi của một phát biểu.',
            'Theo bài viết trên trang Vinhomes, đại diện IHG nêu kỳ vọng về hệ sinh thái lưu trú tại Green Paradise.',
            'Đó là lời nguồn dẫn lại, chưa phải xác nhận khách sạn đã vận hành.',
            'Trang nguồn chưa rõ ngày công bố; trích dẫn này không chứng minh giá, tiến độ hay pháp lý.',
            'Bạn muốn đối chiếu phát biểu nào? Gửi câu hỏi để cùng kiểm tra nguồn.'],
        'overlays': ['Lời kỳ vọng hay dữ kiện?', 'Theo bài viết Vinhomes', 'Chưa xác nhận vận hành', 'Ngày công bố chưa rõ', 'Cùng đối chiếu nguồn'],
        'cards': [('KỲ VỌNG', 'Kết quả thực tế cần bằng chứng riêng.'),
                  ('THEO LỜI ĐƯỢC DẪN', 'Đại diện IHG nêu kỳ vọng về hệ sinh thái lưu trú.'),
                  ('PHẠM VI PHÁT BIỂU', 'Lời trích dẫn chưa xác nhận khách sạn đã vận hành.'),
                  ('NGUỒN CHƯA RÕ NGÀY', 'Không suy ra giá, tiến độ hoặc pháp lý từ trích dẫn.'),
                  ('BẠN MUỐN KIỂM TRA GÌ?', 'Gửi câu hỏi để cùng đối chiếu nguồn.')]},
    2: {'project_id': '206a81364b2e5d0d98fa0cfdf2b5bedb', 'brand_id': 'ngoc-phuong-dong', 'template_id': 'property-45',
        'topic': 'Green Paradise · chứng nhận', 'title': 'Khởi động chưa phải đã đạt',
        'sentences': [
            'Khởi động một dự án chứng nhận có đồng nghĩa đã được cấp chứng nhận không?',
            'Bài viết Vinhomes nêu Green Paradise khởi động dự án chứng nhận đô thị thông minh ngày ba tháng ba năm hai nghìn không trăm hai mươi sáu.',
            'Đây là mốc bắt đầu và mục tiêu được nguồn giới thiệu, chưa phải kết quả đã đạt.',
            'Ngày công bố trang chưa rõ; nguồn này không xác nhận tình trạng chứng nhận hiện tại.',
            'Bạn muốn kiểm tra tiêu chí hay kết quả? Gửi câu hỏi để cùng đối chiếu.'],
        'overlays': ['Khởi động chưa phải đã đạt', 'Mốc nguồn nêu: 03/03/2026', 'Mục tiêu khác kết quả', 'Chưa xác nhận hiện tại', 'Kiểm tra tiêu chí và kết quả'],
        'cards': [('KHỞI ĐỘNG', 'Bắt đầu dự án chứng nhận khác với kết quả được cấp.'),
                  ('03 / 03 / 2026', 'Mốc khởi động được bài viết Vinhomes nêu.'),
                  ('MỤC TIÊU', 'Thông tin về mục tiêu chưa chứng minh đã đạt.'),
                  ('CẦN ĐỐI CHIẾU', 'Chưa xác nhận tình trạng chứng nhận hiện tại.'),
                  ('TIÊU CHÍ / KẾT QUẢ', 'Gửi câu hỏi để cùng kiểm tra tài liệu nguồn.')]},
    4: {'project_id': 'ec5a3d1cf3cf5ec3a1debaf97c189139', 'brand_id': 'ngoc-phuong-dong', 'template_id': 'event-45-landscape',
        'topic': 'Vinhomes Sài Gòn Park', 'title': 'Con số sự kiện nói lên điều gì?',
        'sentences': [
            'Con số sự kiện có cho biết số giao dịch không? Hãy phân biệt đúng chỉ số.',
            'Bài Kick-Off Vinhomes Sài Gòn Park nêu gần mười hai nghìn người tham dự và hơn một trăm tám mươi nghìn lượt xem trực tiếp.',
            'Đây là số liệu bài viết tường thuật, chưa được đối chiếu độc lập.',
            'Số người và lượt xem không xác nhận giao dịch; ngày công bố trang chưa rõ.',
            'Bạn muốn kiểm tra phạm vi số liệu? Gửi câu hỏi để cùng đối chiếu nguồn.'],
        'overlays': ['Đọc đúng chỉ số sự kiện', 'Theo số liệu bài tường thuật', 'Chưa đối chiếu độc lập', 'Không suy ra giao dịch', 'Kiểm tra phạm vi số liệu'],
        'cards': [('CHỈ SỐ SỰ KIỆN', 'Người tham dự và lượt xem khác với giao dịch.'),
                  ('GẦN 12.000 / HƠN 180.000', 'Người tham dự / lượt xem trực tiếp, theo bài viết.'),
                  ('BÀI VIẾT TƯỜNG THUẬT', 'Số liệu được nguồn nêu; chưa đối chiếu độc lập.'),
                  ('KHÔNG SUY RA GIAO DỊCH', 'Ngày công bố trang nguồn chưa rõ.'),
                  ('ĐỌC ĐÚNG PHẠM VI', 'Gửi câu hỏi để cùng đối chiếu nguồn.')]},
    6: {'project_id': '5e9d204790f551eb8afadee33a67a8f6', 'brand_id': 'vang-nguyen', 'template_id': 'personal-45',
        'topic': 'Vang Nguyễn · đọc nguồn', 'title': 'Đọc tin theo thời điểm',
        'sentences': [
            'Tách ngày đăng khỏi ngày lấy nguồn để đọc đúng thời điểm.',
            'Báo Điện tử Chính phủ đăng bài ngày hai mươi bốn tháng tư năm hai nghìn không trăm hai mươi sáu.',
            'Nguồn được lấy ngày sáu tháng mười theo giờ Việt Nam, khác với ngày đăng bài.',
            'Bài tường thuật quý một năm hai nghìn không trăm hai mươi sáu, chưa xác nhận thị trường hiện tại.',
            'Gửi câu hỏi để cùng kiểm tra ngày bài và kỳ dữ liệu.'],
        'overlays': ['Ngày đăng và ngày lấy nguồn', 'Ngày bài: 24/04/2026', 'Lấy nguồn: 06/10/2026 giờ VN', 'Bối cảnh: quý I/2026', 'Kiểm tra thời điểm dữ liệu'],
        'cards': [('HAI MỐC RIÊNG', 'Ngày đăng bài khác với ngày lấy nguồn.'),
                  ('24 / 04 / 2026', 'Ngày công bố bài trên Báo Điện tử Chính phủ.'),
                  ('06 / 10 / 2026', 'Ngày lấy nguồn theo giờ Việt Nam (UTC+7).'),
                  ('QUÝ I / 2026', 'Bối cảnh bài tường thuật; chưa xác nhận hiện tại.'),
                  ('ĐỌC NGUỒN THEO THỜI ĐIỂM', 'Gửi câu hỏi để cùng đối chiếu ngày bài và kỳ dữ liệu.')]},
    8: {'project_id': '7f13a515100d5c07aae9760d665ad2f8', 'brand_id': 'ngoc-phuong-dong', 'template_id': 'news-60-landscape',
        'topic': 'Việt Nam · thị trường nhà ở', 'title': 'Một góc nhìn lịch sử quý II',
        'sentences': [
            'Đây là góc nhìn lịch sử về quý hai, không phải bản tin hôm nay.',
            'Bài trên Chinhphu.vn công bố ngày hai mươi mốt tháng tám năm hai nghìn không trăm hai mươi sáu.',
            'Theo bài viết, nguồn cung tăng trong quý hai, còn giao dịch giảm và tồn kho tăng nhẹ.',
            'Đây là lời nguồn báo cáo về kỳ cũ, không xác nhận giá hay tình hình thị trường hiện tại.',
            'Đọc nguồn và gửi câu hỏi nếu muốn đối chiếu thêm.'],
        'overlays': ['Góc nhìn lịch sử quý II', 'Ngày bài: 21/08/2026', 'Cung, giao dịch và tồn kho', 'Chưa xác nhận hiện tại', 'Đọc nguồn để đối chiếu'],
        'cards': [('QUÝ II / 2026', 'Thông tin lịch sử; không gọi là bản tin hôm nay.'),
                  ('21 / 08 / 2026', 'Ngày công bố bài trên Chinhphu.vn.'),
                  ('CUNG / GIAO DỊCH / TỒN KHO', 'Bài nêu: cung tăng, giao dịch giảm, tồn kho tăng nhẹ.'),
                  ('PHẠM VI KỲ CŨ', 'Nguồn không xác nhận giá hay thị trường hiện tại.'),
                  ('ĐỌC NGUỒN', 'Gửi câu hỏi nếu muốn đối chiếu tài liệu khác.')]},
}


def source_context(case):
    manifest = json.loads((SOURCE_BUNDLE / 'script-review-manifest.json').read_bytes())
    ref = next(c for c in manifest['scripts'] if c['case'] == case)
    run = json.loads((SOURCE_BUNDLE / ('run-' + ref['run_id'] + '.json')).read_bytes())
    project = json.loads((SOURCE_BUNDLE / ('project-' + ref['project_id'] + '.json')).read_bytes())['project']
    if project['id'] != DEFINITIONS[case]['project_id']:
        raise support.EvidenceError('SOURCE_PROJECT_BINDING_CHANGED')
    source = run['sources'][0]
    if support.digest(source['text']) != source['content_sha256']:
        raise support.EvidenceError('ACTUAL_RESEARCH_SOURCE_HASH_CHANGED')
    fetched = datetime.fromisoformat(source['retrieved_at'].replace('Z', '+00:00'))
    return {'source': source, 'run': run['run'], 'findings': run['findings'], 'brief': run['brief'], 'provider_project': project,
            'retrieved_utc': fetched.isoformat(), 'retrieved_vietnam': fetched.astimezone(timezone(timedelta(hours=7))).isoformat()}


def proposal(case, context):
    item = DEFINITIONS[case]
    result = {'narration': ' '.join(item['sentences']),
              'visual_brief': [{'scene': n, 'narration_excerpt': text, 'on_screen_text': item['overlays'][n - 1],
                               'visual': 'Đồ họa chữ gốc có nguồn: ' + item['cards'][n - 1][1] + ' Không dùng ảnh hiện trạng dự án.'}
                              for n, text in enumerate(item['sentences'], 1)],
              'facts_needing_source': ['Nguồn đã lưu: ' + context['source']['reference'],
                                      'Thông tin là nội dung nguồn tường thuật, chưa xác minh độc lập; cần đối chiếu trước khi kết luận hiện tại.',
                                      'Ngày công bố: ' + (context['source']['timestamp'] or 'chưa rõ') + '. Không dùng ngày lấy nguồn thay ngày công bố.',
                                      'Đồ họa chữ gốc, không phải ảnh hiện trạng hoặc logo chính thức. Chưa có nghiệm thu Owner cho lời đọc/media/video.']}
    if case == 6:
        result['facts_needing_source'].append('Mốc lấy nguồn gốc UTC: ' + context['retrieved_utc'] + '; giờ Việt Nam: ' + context['retrieved_vietnam'] + '. Đã sửa cách đọc ngày địa phương.')
    words = len(result['narration'].split())
    if not 80 <= words <= 100 or any(len(s['on_screen_text']) > 35 for s in result['visual_brief']):
        raise support.EvidenceError(f'COMPACT_NARRATION_OR_OVERLAY_LIMIT_CASE_{case:02d}_{words}')
    return result


def wrapped(draw, text, font, width):
    lines, line = [], ''
    for word in text.split():
        trial = (line + ' ' + word).strip()
        if draw.textlength(trial, font=font) > width and line:
            lines.append(line); line = word
        else:
            line = trial
    return lines + ([line] if line else [])


def text_block(draw, text, xy, font, width, color, leading=1.25):
    x, y = xy
    for line in wrapped(draw, text, font, width):
        draw.text((x, y), line, font=font, fill=color)
        y += int(font.size * leading)
    return y


def graphic(path, case, scene, variant, context):
    definition = DEFINITIONS[case]; wide = definition['template_id'].endswith('-landscape')
    width, height = (1920, 1080) if wide else (1080, 1920)
    light = variant == 'alternative-light'
    bg, ink, accent, muted = ('#fffaf0', '#15352c', '#826a32', '#405a50') if light else ('#15352c', '#fffaf0', '#dfc987', '#d2dfca')
    image = Image.new('RGB', (width, height), bg); draw = ImageDraw.Draw(image)
    fonts = {size: ImageFont.truetype(str(FONT_ROOT / ('seguisb.ttf' if size >= 44 else 'segoeui.ttf')), size)
             for size in (22, 26, 30, 38, 44, 54, 72, 88)}
    margin = 105 if wide else 90
    draw.rounded_rectangle((margin, 68 if wide else 226, width - margin, 132 if wide else 302), radius=16, outline=accent, width=2)
    draw.text((margin + 24, 79 if wide else 244), 'NPD' if case != 6 else 'VANG NGUYỄN', font=fonts[38], fill=accent)
    draw.text((width - margin - 402, 92 if wide else 257), 'NỘI DUNG CÓ NGUỒN', font=fonts[22], fill=muted)
    draw.line((margin, 190 if wide else 360, width - margin, 190 if wide else 360), fill=accent, width=3)
    draw.text((margin, 203 if wide else 392), definition['topic'], font=fonts[30], fill=muted)
    heading, body = definition['cards'][scene - 1]
    if variant == 'alternative-context':
        heading, body = 'ĐỐI CHIẾU NGUỒN', definition['title'] + '. ' + definition['cards'][scene - 1][1]
    y = text_block(draw, heading, (margin, 269 if wide else 514), fonts[72 if wide else 88], width - 2 * margin, ink, 1.18)
    y = text_block(draw, body, (margin, y + (16 if wide else 54)), fonts[38 if wide else 44], width - 2 * margin, muted, 1.35)
    if y > (485 if wide else 1040):
        raise support.EvidenceError('GRAPHIC_CONTENT_OVERFLOW_' + path.name)
    top, bottom = (505, 717) if wide else (1135, 1500)
    draw.rounded_rectangle((margin - 12, top, width - margin + 12, bottom), radius=18, outline=accent, width=2)
    source = context['source']
    source_title = source['title']
    sy = text_block(draw, 'NGUỒN: ' + source_title, (margin + 16, top + 18), fonts[26 if wide else 30], width - 2 * margin - 30, ink, 1.25)
    draw.text((margin + 16, sy + 10), urlsplit(source['reference']).hostname, font=fonts[26], fill=muted)
    date = datetime.fromisoformat(source['timestamp'].replace('Z', '+00:00')).astimezone(timezone(timedelta(hours=7))).strftime('%d/%m/%Y') if source['timestamp'] else 'chưa rõ'
    draw.text((margin + 16, sy + 48), 'Ngày công bố: ' + date, font=fonts[26], fill=muted)
    if case == 6:
        draw.text((margin + 16, sy + 85), 'Lấy nguồn: 06/10/2026 (UTC+7) · 05/10/2026 (UTC)', font=fonts[22 if wide else 26], fill=muted)
    if sy + (112 if case == 6 else 81) > bottom:
        raise support.EvidenceError('GRAPHIC_SOURCE_OVERFLOW_' + path.name)
    draw.text((margin, 768 if wide else 1550), 'Đồ họa biên tập · nội dung nguồn chưa xác minh độc lập', font=fonts[22], fill=muted)
    image.save(path, format='PNG')
    return {'path': str(path.resolve()), 'source_sha256': support.sha(path.read_bytes()), 'bytes': path.stat().st_size,
            'width': width, 'height': height, 'scene': scene, 'variant': variant,
            'rights': 'Original typography/layout created for the authorized internal campaign; no third-party photos or official logos.',
            'illustration': True, 'reference': source['reference'], 'research_source_id': source['id'],
            'research_source_sha256': source['content_sha256'], 'publication_date': source['timestamp']}


def build(output):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    cases = []
    for case, definition in DEFINITIONS.items():
        context = source_context(case); compact = proposal(case, context)
        folder = output / f'case-{case:02d}'; folder.mkdir()
        cards = [graphic(folder / f'case-{case:02d}-scene-{n:02d}-source.png', case, n, 'primary', context) for n in range(1, 6)]
        cards += [graphic(folder / f'case-{case:02d}-alternative-{n}.png', case, 1, variant, context)
                  for n, variant in enumerate(('alternative-light', 'alternative-context'), 1)]
        tile_width = 240
        tiles = []
        for card in cards:
            im = Image.open(card['path']); im.thumbnail((tile_width, 430))
            tile = Image.new('RGB', (tile_width + 16, 478), '#e7e5dc'); tile.paste(im, ((tile.width - im.width) // 2, 8))
            ImageDraw.Draw(tile).text((8, 449), Path(card['path']).stem, font=ImageFont.truetype(str(FONT_ROOT / 'segoeui.ttf'), 14), fill='#15352c')
            tiles.append(tile)
        contact = Image.new('RGB', (len(tiles) * tiles[0].width, 478), '#e7e5dc')
        for n, tile in enumerate(tiles): contact.paste(tile, (n * tile.width, 0))
        contact.save(folder / 'contact-sheet.png')
        cases.append({'case': case, 'project_id': definition['project_id'], 'proposal': compact,
                      'narration_words': len(compact['narration'].split()), 'narration_sha256': support.sha(compact['narration'].encode('utf-8')),
                      'original_provider_proposal_sha256': support.digest(context['provider_project']['document']['proposal']),
                      'lineage_sha256': context['provider_project']['document']['content_intelligence']['sha256'],
                      'source_context': {k: v for k, v in context.items() if k != 'provider_project'},
                      'suggested_brand_id': definition['brand_id'], 'suggested_template_id': definition['template_id'], 'media': cards})
    manifest = {'schema_version': 'phase10-original-sourced-media-v1', 'created_at': support.stamp(), 'actor': ACTOR,
                'source_bundle': str(SOURCE_BUNDLE), 'cases': cases, 'new_provider_calls': 0,
                'new_human_script_media_final_acceptance': False}
    with (output / 'manifest.json').open('xb') as f: f.write(support.canonical(manifest))
    print(json.dumps({'generated_original_cards': sum(len(c['media']) for c in cases), 'cases': len(cases),
                      'word_counts': {c['case']: c['narration_words'] for c in cases}, 'manifest': str(output / 'manifest.json')}))
    return manifest


class NativePreparationClient:
    def __init__(self, base_url, ledger):
        self.reader = support.Client(base_url, ledger)
        self.reader.connect()
        if self.reader.capabilities.get('voice_quality_selection') is not True:
            raise support.EvidenceError('RESTARTED_VOICE_SELECTION_RUNTIME_REQUIRED')
        self.ledger, self.uncertain, self.writes = ledger, False, 0

    def get(self, path):
        return self.reader.get(path)

    def post(self, path, body=None, media=None, revision=None):
        if self.uncertain or not re.fullmatch(r'/api/projects/[0-9a-f]{32}/(draft|media|voice-quality)', path):
            raise support.EvidenceError('PREPARATION_SCOPE_OR_UNCERTAIN_OUTCOME_NO_REPLAY')
        binary = media is not None
        raw = Path(media['path']).read_bytes() if binary else support.canonical(body)
        if binary and support.sha(raw) != media['source_sha256']:
            raise support.EvidenceError('ORIGINAL_MEDIA_HASH_CHANGED')
        headers = {'Origin': self.reader.base_url, 'Sec-Fetch-Site': 'same-origin', 'Accept': 'application/json', 'X-VF-CSRF': self.reader.csrf,
                   'Content-Type': 'image/png' if binary else 'application/json'}
        if binary:
            headers.update({'X-VF-Revision': str(revision), 'X-VF-Rights': 'confirmed', 'X-VF-Illustration': 'true',
                            'X-VF-Filename': quote(Path(media['path']).name)})
        intent = {'schema_version': 'phase10-native-media-http-v1', 'requested_at': support.stamp(), 'actor': ACTOR,
                  'method': 'POST', 'base_url': self.reader.base_url, 'path': path, 'body_sha256': support.sha(raw),
                  'revision': revision if binary else body.get('revision'), 'body': None if binary else body,
                  'media': media, 'automatic_retry': False, 'human_acceptance': 'PENDING'}
        self.ledger.save(f'{len(self.ledger.entries) + 1:04d}-intent.json', intent); self.writes += 1
        try:
            try:
                response = self.reader.opener.open(Request(self.reader.base_url + path, data=raw, headers=headers, method='POST'), timeout=45)
            except HTTPError as error:
                response = error
            with response:
                status = response.status; raw_reply = response.read(support.MAX_RESPONSE + 1)
            value = json.loads(raw_reply)
        except Exception as error:
            self.uncertain = True
            self.ledger.receipt({**intent, 'completed_at': support.stamp(), 'http_status': None,
                                 'outcome': 'OUTCOME_UNKNOWN_NO_REPLAY', 'error_type': type(error).__name__})
            raise support.EvidenceError('PREPARATION_WRITE_OUTCOME_UNKNOWN_NO_REPLAY') from None
        self.ledger.receipt({**intent, 'completed_at': support.stamp(), 'http_status': status,
                             'response_raw_sha256': support.sha(raw_reply), 'snapshot_sha256': support.digest(value), 'snapshot': value,
                             'outcome': 'HTTP_SUCCESS' if status == 200 or status == 201 else 'OUTCOME_UNKNOWN_NO_REPLAY' if status >= 500 else 'HTTP_ERROR'})
        if status not in {200, 201}:
            self.uncertain = status >= 500
            raise support.EvidenceError(f'HTTP_{status}_{value.get("code", "ERROR")}')
        return value


def apply(base_url, output, authority):
    manifest = json.loads((Path(output) / 'manifest.json').read_bytes())
    ledger = support.Ledger(output, 'api-preparation')
    ledger.save('authority.json', {'reference': authority, 'actor': ACTOR, 'scope': 'compact_drafts_original_media_existing_voice_policy',
                                  'script_media_final_approval': False, 'tts_render_dispatch': False, 'manifest_sha256': support.digest(manifest)})
    client = NativePreparationClient(base_url, ledger); results = []
    try:
        for case in manifest['cases']:
            project = client.get('/api/projects/' + case['project_id']); old = project
            if (project['document']['content_intelligence']['sha256'] != case['lineage_sha256'] or project['approval'] is not None
                    or project.get('script_review') is not None or project['document'].get('assets') or
                    support.digest(project['document']['proposal']) != case['original_provider_proposal_sha256']):
                raise support.EvidenceError('PROJECT_CHANGED_RESUME_FROM_RECEIPTS_NO_REPLAY')
            ledger.save(f"case-{case['case']:02d}-before.json", project)
            endpoint = '/api/projects/' + project['id']
            project = client.post(endpoint + '/draft', {'revision': project['revision'], 'proposal': case['proposal']})
            uploads = []
            for card in case['media']:
                project = client.post(endpoint + '/media', media=card, revision=project['revision'])
                asset = next(a for a in project['document']['assets'] if a['filename'] == Path(card['path']).name)
                if asset['source_sha256'] != card['source_sha256'] or asset['illustration'] is not True or asset['rights_confirmed'] is not True:
                    raise support.EvidenceError('UPLOADED_MEDIA_PROVENANCE_MISMATCH')
                uploads.append({'original': card, 'asset': asset})
            bindings = [{'scene': u['original']['scene'], 'asset_id': u['asset']['id']} for u in uploads if u['original']['variant'] == 'primary']
            project = client.post(endpoint + '/draft', {'revision': project['revision'], 'scene_media': bindings,
                'scene_options': [{'scene': n, 'crop_strategy': 'contain', 'motion': 'none', 'source_start': 0, 'transition': 'cut'} for n in range(1, 6)]})
            if case['case'] != 1:
                project = client.post(endpoint + '/voice-quality', {'revision': project['revision'], 'policy_id': 'warm-scene-context-v1'})
            if project['document']['content_intelligence'] != old['document']['content_intelligence'] or project['approval'] is not None or project.get('script_review') is not None:
                raise support.EvidenceError('LINEAGE_OR_APPROVAL_BOUNDARY_CHANGED')
            if any(j['kind'] == 'render' for j in project['jobs']):
                raise support.EvidenceError('UNEXPECTED_RENDER_DISPATCH')
            record = {'case': case['case'], 'project_id': project['id'], 'revision': project['revision'],
                      'narration_words': case['narration_words'], 'narration_sha256': case['narration_sha256'],
                      'lineage_sha256': case['lineage_sha256'], 'voice_quality': project['document'].get('voice_quality'),
                      'suggested_brand_id': case['suggested_brand_id'], 'suggested_template_id': case['suggested_template_id'],
                      'media_uploads': uploads, 'scene_media': bindings, 'project': project,
                      'script_media_final_acceptance': 'PENDING'}
            results.append(record); ledger.save(f"case-{case['case']:02d}-prepared.json", record)
        summary = {'schema_version': 'phase10-sourced-media-preparation-v1', 'prepared_at': support.stamp(), 'actor': ACTOR,
                   'results': results, 'http_writes': client.writes, 'new_provider_calls': 0, 'new_tts_render_dispatch': 0,
                   'owner_acceptance': 'PENDING', 'receipt_index': ledger.entries}
        ledger.save('prepared-manifest.json', summary)
        lines = ['# Năm bản biên tập gọn và đồ họa gốc có nguồn', '',
                 'Chuẩn bị bởi Codex theo task Owner. Chưa duyệt lời đọc/media/video cuối. Giữ nguyên nguồn và lineage; bản provider gốc nằm trong lịch sử và bundle trước.', '',
                 'Mỗi dự án có năm thẻ cảnh chính và hai bố cục thay thế. Đây là đồ họa biên tập, không phải ảnh hiện trạng hay logo chính thức.', '']
        for case, result in zip(manifest['cases'], results):
            lines += [f"## Ca {case['case']:02d} — {DEFINITIONS[case['case']]['title']}", '',
                      f"[Mở Studio]({base_url}/?project={result['project_id']}) · Phiên bản {result['revision']} · {case['narration_words']} từ theo khoảng trắng", '',
                      case['proposal']['narration'], '', '### Cảnh và chữ trên hình', '']
            for scene in case['proposal']['visual_brief']:
                lines += [f"{scene['scene']}. **{scene['on_screen_text']}** — {scene['narration_excerpt']}", '']
            source = case['source_context']['source']
            lines += ['### Nguồn và thời điểm', '', '- ' + source['title'] + ' — ' + source['reference'],
                      '- Ngày công bố: ' + (source['timestamp'] or 'chưa rõ'),
                      '- Lấy nguồn UTC: ' + case['source_context']['retrieved_utc'],
                      '- Lấy nguồn giờ Việt Nam: ' + case['source_context']['retrieved_vietnam'], '',
                      '### Đồ họa', '', f"![Các thẻ gốc]({Path(output).resolve() / ('case-' + str(case['case']).zfill(2)) / 'contact-sheet.png'})", '',
                      'Preset: ' + ('để nguyên mặc định; root chọn Giọng B trực tiếp trong UI' if case['case'] == 1 else 'Giọng B · warm-scene-context-v1'),
                      '', 'Mẫu đề xuất: ' + case['suggested_brand_id'] + ' / ' + case['suggested_template_id'] + '.', '',
                      'Kết luận chất lượng và nghiệm thu Owner: **PENDING**.', '']
        with (ledger.root / 'compact-script-media-review.md').open('x', encoding='utf-8') as f: f.write('\n'.join(lines) + '\n')
        print(json.dumps({'prepared_cases': len(results), 'uploaded_original_cards': sum(len(r['media_uploads']) for r in results),
                          'http_writes': client.writes, 'evidence': str(ledger.root), 'owner_acceptance': 'PENDING'}))
    except Exception as error:
        ledger.save('stopped.json', {'status': 'STOPPED', 'error': str(error), 'automatic_retry': False,
                                   'http_writes': client.writes, 'completed_cases': results, 'receipt_index': ledger.entries})
        raise


def plan_previews(output, authority):
    """Only existing brand selection and silent visual previews, via root's HTTP ledger."""
    render_spec = importlib.util.spec_from_file_location('phase10_render_support', Path(__file__).with_name('phase10-final-uat-render.py'))
    render = importlib.util.module_from_spec(render_spec); render_spec.loader.exec_module(render)
    api = render.API('campaign/baseline-previews')
    api.ledger.save('preparation-authority.json', {'reference': authority, 'actor': render.ACTOR,
        'scope': 'brand_templates_and_silent_visual_preview_only_cases02_04_06_08', 'owner_quality_acceptance': False,
        'tts_render_dispatch': False})
    manifest = json.loads((Path(output) / 'manifest.json').read_bytes())
    results = []
    for case in manifest['cases']:
        if case['case'] == 1: continue
        endpoint = '/api/projects/' + case['project_id']; before = api.request('GET', endpoint)
        if (before['document']['content_intelligence']['sha256'] != case['lineage_sha256']
                or before['document']['proposal'] != case['proposal'] or before['approval'] is not None):
            raise support.EvidenceError('BASELINE_PROJECT_CHANGED_DO_NOT_REPLAY')
        bindings = before['document']['scene_media']
        options = [{k: s[k] for k in ('scene', 'crop_strategy', 'motion', 'source_start', 'transition')}
                   for s in before['document']['edit_plan']['scenes']]
        project = api.request('POST', endpoint + '/brand-template', {'revision': before['revision'],
            'brand_id': case['suggested_brand_id'], 'template_id': case['suggested_template_id']})
        after_options = [{k: s[k] for k in ('scene', 'crop_strategy', 'motion', 'source_start', 'transition')}
                         for s in project['document']['edit_plan']['scenes']]
        if project['document']['scene_media'] != bindings or after_options != options or project['document']['content_intelligence'] != before['document']['content_intelligence']:
            raise support.EvidenceError('SOURCE_OPTIONS_OR_LINEAGE_CHANGED')
        shots = api.request('GET', endpoint + '/shots')
        preview = api.request('POST', endpoint + '/preview', {'revision': project['revision'], 'action': 'generate'})
        record = {'case': case['case'], 'project_id': project['id'], 'revision': project['revision'],
                  'brand_template': project['document']['brand_template'], 'shots': shots['shot_timeline'],
                  'scene_media': bindings, 'options': options, 'project_snapshot': project, 'preview_request': preview}
        results.append(record); api.ledger.save(f"case-{case['case']:02d}-baseline-request.json", record)
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        pending = []
        for result in results:
            if result.get('preview') is not None: continue
            state = api.request('GET', '/api/projects/' + result['project_id'] + '/preview')
            if state['status'] in {'QUEUED', 'RUNNING'}:
                pending.append(result['case']); continue
            result['preview'] = state
            api.ledger.save(f"case-{result['case']:02d}-baseline-preview.json", result)
            print(json.dumps({'case': result['case'], 'baseline_preview': state['status'], 'sha256': state.get('sha256'),
                              'revision': result['revision']}), flush=True)
        if not pending: break
        time.sleep(3)
    if any(r.get('preview', {}).get('status') != 'READY' for r in results):
        api.ledger.save('baseline-preview-stopped.json', {'results': results, 'automatic_retry': False})
        raise support.EvidenceError('BASELINE_PREVIEW_INCOMPLETE_NO_AUTOMATIC_REPLAY')
    final = {'recorded_at': support.stamp(), 'actor': render.ACTOR, 'authority_reference': authority, 'results': results,
             'provider_calls': 0, 'tts_calls': 0, 'owner_quality_acceptance': 'PENDING', 'receipts': api.ledger.entries}
    api.ledger.save('baseline-previews.json', final)
    print(json.dumps({'baseline_previews': len(results), 'evidence': str(api.ledger.root), 'owner_acceptance': 'PENDING'}))
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'apply', 'plan-previews'])
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--base-url')
    parser.add_argument('--authority-reference')
    args = parser.parse_args()
    if args.action == 'build': return build(args.output)
    if not args.base_url or not args.authority_reference:
        parser.error('Apply requires explicit restarted loopback URL and task authority reference.')
    if args.action == 'plan-previews':
        if args.base_url != 'http://127.0.0.1:8030': parser.error('Root helper targets the isolated 8030 service only.')
        return plan_previews(args.output, args.authority_reference)
    return apply(args.base_url, args.output, args.authority_reference)


if __name__ == '__main__': main()
