"""HTTP-only campaign preparation and append-only evidence; never human acceptance.

Read commands issue GETs only. ``prepare`` and ``scripts`` require an explicit
authority reference and use a visibly agent-labelled actor. They cannot approve
scripts, media, final videos, or dispatch TTS/render. No provider replay occurs
after an uncertain request. Session/CSRF credentials are held only in memory.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from http.cookiejar import CookieJar
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPCookieProcessor, ProxyHandler, Request, build_opener
import uuid


REPO = Path(__file__).resolve().parents[1]
ACTOR = 'Codex — chuẩn bị UAT theo task Owner; chưa nghiệm thu'
SCHEMA = 'phase10-final-uat-http-evidence-v1'
IDENTIFIER = re.compile(r'[0-9a-f]{32}')
MAX_RESPONSE = 64 * 1024 * 1024
READ_ROUTES = (
    r'/api/(session|health|projects(?:\?archived=include)?|brand-templates\?formats=all)',
    r'/api/intelligence/(runs|records/[0-9a-f]{32}/history|projects/[0-9a-f]{32}/lineage)',
    r'/api/projects/[0-9a-f]{32}(?:/versions|/shots)?',
    r'/api/jobs/[0-9a-f]{32}/(?:logs|artifacts)',
    r'/api/production/(?:queue|calendar|profiles|library|planning/[0-9a-f]{32}(?:/history)?|briefs/[0-9a-f]{32}/preflight|batches/[A-Za-z0-9_-]{8,100})',
)
WRITE_ROUTES = (
    r'/api/intelligence/ideas/[0-9a-f]{32}/select',
    r'/api/production/(?:planning/[0-9a-f]{32}|briefs/[0-9a-f]{32}/approve|batch)',
)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(canonical(value))


def stamp():
    return datetime.now(timezone.utc).isoformat()


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError('INVALID_STABLE_ID')
    return value


class EvidenceError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise EvidenceError('REDIRECT_REFUSED_NO_REPLAY')


class Ledger:
    def __init__(self, root, command):
        root = Path(root).resolve()
        self.root = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + command + '-' + uuid.uuid4().hex[:8])
        self.root.mkdir(parents=True, exist_ok=False)
        self.entries = []

    def save(self, name, value):
        if not re.fullmatch(r'[A-Za-z0-9._-]+', name):
            raise ValueError('EVIDENCE_FILENAME_INVALID')
        path = self.root / name
        with path.open('xb') as handle:
            handle.write(canonical(value))
        return {'path': str(path), 'sha256': digest(value), 'bytes': path.stat().st_size}

    def receipt(self, value):
        stored = self.save(f'{len(self.entries) + 1:04d}-http.json', value)
        self.entries.append(stored)
        return stored


class Client:
    def __init__(self, base_url, ledger, *, writes=False, timeout=45):
        parts = urlsplit(base_url)
        if (parts.scheme != 'http' or parts.hostname not in {'127.0.0.1', 'localhost'}
                or parts.username or parts.password or parts.path not in {'', '/'} or parts.query or parts.fragment
                or not parts.port or not 1 <= parts.port <= 65535):
            raise ValueError('EXPLICIT_LOOPBACK_HTTP_PORT_REQUIRED')
        self.base_url = f'http://{parts.hostname}:{parts.port}'
        self.ledger, self.writes, self.timeout = ledger, writes, timeout
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()), NoRedirect())
        self.csrf = None
        self.capabilities = {}
        self.read_count = self.write_count = 0
        self.uncertain_write = False

    def request(self, method, path, body=None, *, optional=False):
        patterns = READ_ROUTES if method == 'GET' else WRITE_ROUTES if method == 'POST' and self.writes else ()
        if not any(re.fullmatch(pattern, path) for pattern in patterns):
            raise EvidenceError('HTTP_ACTION_OUTSIDE_EXPLICIT_PREPARATION_SCOPE')
        if method == 'POST':
            if self.uncertain_write:
                raise EvidenceError('UNCERTAIN_WRITE_REQUIRES_EXTERNAL_READ_AND_DECISION_NO_REPLAY')
            if not self.csrf or body.get('reviewer') != ACTOR:
                raise EvidenceError('SESSION_AND_AGENT_ACTOR_REQUIRED')
            if path == '/api/production/batch' and body.get('action') != 'scripts':
                raise EvidenceError('ONLY_SCRIPT_DISPATCH_AUTHORIZED')
        started = stamp()
        request_sha = digest(body) if body is not None else None
        base = {'schema_version': SCHEMA, 'method': method, 'base_url': self.base_url, 'path': path,
                'requested_at': started, 'request_body_sha256': request_sha,
                'request_body': body, 'automatic_retry': False}
        if method == 'POST':
            self.ledger.save(f'{len(self.ledger.entries) + 1:04d}-intent.json', base)
            self.write_count += 1
        else:
            self.read_count += 1
        headers = {'Accept': 'application/json', 'Origin': self.base_url, 'Sec-Fetch-Site': 'same-origin'}
        raw_body = canonical(body) if body is not None else None
        if raw_body is not None:
            headers.update({'Content-Type': 'application/json', 'X-VF-CSRF': self.csrf})
        request = Request(self.base_url + path, data=raw_body, headers=headers, method=method)
        try:
            try:
                response = self.opener.open(request, timeout=self.timeout)
            except HTTPError as error:
                response = error
            with response:
                status, content_type = response.status, response.headers.get('Content-Type', '')
                raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE or not content_type.startswith('application/json'):
                raise EvidenceError('HTTP_RESPONSE_SIZE_OR_TYPE_INVALID')
            value = json.loads(raw)
        except (OSError, URLError, ValueError, EvidenceError) as error:
            if method == 'POST':
                self.uncertain_write = True
            self.ledger.receipt({**base, 'completed_at': stamp(), 'http_status': None,
                                 'outcome': 'OUTCOME_UNKNOWN_NO_REPLAY' if method == 'POST' else 'READ_FAILED',
                                 'error_type': type(error).__name__})
            raise EvidenceError('REQUEST_OUTCOME_UNKNOWN_NO_REPLAY' if method == 'POST' else 'READ_FAILED') from None
        # The actual session response digest is retained; the reusable secret is never persisted.
        saved_value = {'capabilities': value.get('capabilities', {}), 'csrf_present': bool(value.get('csrf'))} if path == '/api/session' else value
        self.ledger.receipt({**base, 'completed_at': stamp(), 'http_status': status,
                             'response_bytes': len(raw), 'response_raw_sha256': sha(raw),
                             'snapshot_sha256': digest(saved_value), 'snapshot': saved_value,
                             'redacted_session': path == '/api/session',
                             'outcome': 'HTTP_SUCCESS' if 200 <= status < 300 else
                             'OUTCOME_UNKNOWN_NO_REPLAY' if method == 'POST' and status >= 500 else 'HTTP_ERROR'})
        if not 200 <= status < 300:
            if method == 'POST' and status >= 500:
                self.uncertain_write = True
            if optional and method == 'GET':
                return {'http_status': status, 'error': value}
            raise EvidenceError(f'HTTP_{status}_{value.get("code", "ERROR")}' if isinstance(value, dict) else f'HTTP_{status}')
        return value

    def connect(self):
        session = self.request('GET', '/api/session')
        self.csrf = session.get('csrf')
        self.capabilities = session.get('capabilities', {})
        if not isinstance(self.csrf, str) or not self.csrf:
            raise EvidenceError('SESSION_CSRF_MISSING')
        if self.writes and self.capabilities.get('production_intelligence') is not True:
            raise EvidenceError('PHASE10_CAPABILITY_REQUIRED')
        return {'capabilities': self.capabilities, 'session_acquired': True, 'secrets_persisted': False}

    def get(self, path, **kwargs):
        return self.request('GET', path, **kwargs)

    def post(self, path, body):
        return self.request('POST', path, body)


def latest(client, record_id):
    history = client.get('/api/intelligence/records/' + identifier(record_id) + '/history')
    if (not isinstance(history, list) or not history or any(r.get('id') != record_id for r in history)
            or [r.get('version') for r in history] != list(range(1, len(history) + 1))):
        raise EvidenceError('IMMUTABLE_HISTORY_SHAPE_INVALID')
    return history[-1]


def capture_run(client, run_id):
    run = latest(client, run_id)
    required = {'source_ids', 'finding_ids', 'idea_ids', 'opportunity_id', 'context'}
    if not required <= set(run):
        raise EvidenceError('RESEARCH_RUN_SHAPE_INVALID')
    source = [latest(client, i) for i in run['source_ids']]
    for value in source:
        if digest(value['text']) != value['content_sha256']:
            raise EvidenceError('RESEARCH_SOURCE_TEXT_HASH_CHANGED')
    opportunity = latest(client, run['opportunity_id']) if run['opportunity_id'] else None
    result = {'run': run, 'sources': source, 'findings': [latest(client, i) for i in run['finding_ids']],
              'ideas': [latest(client, i) for i in run['idea_ids']], 'opportunity': opportunity,
              'brief': latest(client, opportunity['brief_id']) if opportunity and opportunity.get('brief_id') else None,
              'new_research_performed': False, 'publication_dates_preserved': True}
    client.ledger.save('run-' + run_id + '.json', result)
    return result


def capture_project(client, project_id):
    project = client.get('/api/projects/' + identifier(project_id))
    versions = client.get('/api/projects/' + project_id + '/versions')
    shots = client.get('/api/projects/' + project_id + '/shots', optional=True)
    lineage = client.get('/api/intelligence/projects/' + project_id + '/lineage', optional=True)
    jobs = []
    for job in project['jobs']:
        receipts = {'job': job, 'logs': client.get('/api/jobs/' + job['id'] + '/logs')}
        if job['kind'] == 'render' and job['status'] == 'succeeded':
            receipts['artifacts'] = client.get('/api/jobs/' + job['id'] + '/artifacts')
        jobs.append(receipts)
    result = {'project': project, 'versions': versions, 'shots': shots, 'lineage': lineage, 'jobs': jobs,
              'new_human_acceptance_recorded_by_helper': False}
    client.ledger.save('project-' + project_id + '.json', result)
    return result


def manifest_cases(path):
    raw = Path(path).read_bytes()
    value = json.loads(raw)
    cases = value.get('campaign_cases', value.get('cases'))
    if not isinstance(cases, list) or not cases:
        raise EvidenceError('CAMPAIGN_MANIFEST_CASES_REQUIRED')
    ids = [identifier(case['run_id']) for case in cases]
    if len(set(ids)) != len(ids):
        raise EvidenceError('CAMPAIGN_DUPLICATE_RUN')
    return cases, {'path': str(Path(path).resolve()), 'raw_sha256': sha(raw), 'snapshot_sha256': digest(value)}


def capture_campaign(client, cases, campaign=None):
    queue = client.get('/api/production/queue')
    if campaign is not None:
        queue = {**queue, 'items': [r for r in queue['items'] if r['planning']['campaign'] == campaign]}
    runs = [capture_run(client, case['run_id']) for case in cases]
    project_ids = list(dict.fromkeys(r['opportunity']['production_project_id'] for r in runs if r['opportunity'] and r['opportunity'].get('production_project_id')))
    projects = [capture_project(client, i) for i in project_ids]
    reviews = [p['project'].get('script_review') for p in projects if (p['project'].get('script_review') or {}).get('current')]
    delegated_reviews = [r for r in reviews if str(r.get('reviewer', '')).startswith('Codex')]
    result = {'captured_at': stamp(), 'campaign': campaign, 'queue': queue, 'cases': runs, 'projects': projects,
              'counts': {'research_runs': len(runs), 'candidates': sum(len(r['ideas']) for r in runs),
                         'selected_ideas': sum(bool(r['opportunity'] and r['opportunity'].get('selected_idea_id')) for r in runs),
                         'approved_brief_records': sum(bool(r['brief'] and r['brief']['status'] == 'APPROVED' and r['brief']['approval']) for r in runs),
                         'projects': len(projects), 'scripts_present': sum(bool(p['project']['document'].get('proposal')) for p in projects),
                         'current_script_review_records': len(reviews),
                         'delegated_codex_script_review_records': len(delegated_reviews),
                         'non_codex_script_review_records_requiring_authority_check': len(reviews) - len(delegated_reviews),
                         'genuine_owner_script_reviews_verified_by_helper': 0,
                         'render_jobs': sum(j['job']['kind'] == 'render' for p in projects for j in p['jobs'])},
              'approval_counts_are_records_not_owner_quality_acceptance': True,
              'human_final_uat_acceptance': 'PENDING', 'publishing_performed': False}
    client.ledger.save('campaign.json', result)
    return result


def prepare(client, cases, selections, campaign, authority):
    if len(cases) != 10 or {int(c['case']) for c in cases} != set(range(1, 11)):
        raise EvidenceError('EXACT_TEN_CASE_MANIFEST_REQUIRED')
    selection_map = {int(c['case']): c for c in selections}
    if set(selection_map) != set(range(1, 11)):
        raise EvidenceError('EXACT_TEN_SELECTIONS_REQUIRED')
    client.ledger.save('preparation-authority.json', {'recorded_at': stamp(), 'authority_reference': authority,
        'actor': ACTOR, 'campaign': campaign, 'scope': ['select_10_ideas', 'plan_10', 'approve_5_briefs_for_script_preparation'],
        'owner_watch_listen_acceptance': False, 'human_script_review': 'PENDING', 'human_media_review': 'PENDING',
        'human_final_review': 'PENDING', 'selection_plan': selections})
    results = []
    for case in sorted(cases, key=lambda v: int(v['case'])):
        choice = selection_map[int(case['case'])]
        if not isinstance(choice.get('rationale'), str) or not choice['rationale'].strip():
            raise EvidenceError('GROUNDED_SELECTION_RATIONALE_REQUIRED')
        run = latest(client, case['run_id']); opportunity = latest(client, run['opportunity_id'])
        idea = latest(client, identifier(choice['idea_id']))
        if idea['run_id'] != run['id'] or idea['id'] not in run['idea_ids'] or opportunity.get('production_project_id'):
            raise EvidenceError('SELECTION_PLAN_BINDING_CHANGED')
        if opportunity.get('selected_idea_id'):
            raise EvidenceError('ALREADY_SELECTED_NO_IMPLICIT_REPLAY')
        client.post('/api/intelligence/ideas/' + idea['id'] + '/select', {'version': idea['version'],
            'opportunity_version': opportunity['version'], 'reviewer': ACTOR})
        opportunity = latest(client, run['opportunity_id']); brief = latest(client, opportunity['brief_id'])
        row = next(r for r in client.get('/api/production/queue')['items'] if r['run_id'] == run['id'])
        priority = 90 if choice.get('prepare_script') is True else 60
        changes = {'campaign': campaign, 'project_priority': priority, 'campaign_priority': 90,
                   'planned_date': '2026-10-06', 'format': '9:16', 'duration_seconds': 60,
                   'assigned_to': ACTOR, 'assigned_status': 'ASSIGNED'}
        if row['similarity']['warnings']:
            changes['similarity_override'] = {'warning_sha256': row['similarity']['warning_sha256'],
                'note': 'UAT tái biên tập từ nguồn thật đã lưu, kiểm tra góc nhìn/cách trình bày và tạo bản render mới; không coi là tin mới. ' + choice['rationale']}
        client.post('/api/production/planning/' + row['id'], {'version': row['planning']['version'], 'reviewer': ACTOR, 'changes': changes})
        if choice.get('prepare_script') is True:
            check = client.get('/api/production/briefs/' + brief['id'] + '/preflight')
            if check['human_override_required']:
                raise EvidenceError('SIMILARITY_OVERRIDE_NOT_CURRENT')
            client.post('/api/production/briefs/' + brief['id'] + '/approve', {'version': check['brief_version'],
                'binding_sha256': check['binding_sha256'], 'reviewer': ACTOR, 'acknowledged': True,
                'note': 'Task Owner cho phép chuẩn bị UAT; Codex duyệt brief để tạo bản nháp kịch bản theo phạm vi được giao. Chưa có nghiệm thu, duyệt lời đọc/media/video của Owner. ' + choice['rationale']})
        results.append({'case': int(case['case']), 'run_id': run['id'], 'idea_id': idea['id'], 'brief_id': brief['id'],
                        'queue_item_id': row['id'], 'script_preparation_requested': choice.get('prepare_script') is True,
                        'rationale': choice['rationale'], 'actor': ACTOR})
    if sum(r['script_preparation_requested'] for r in results) != 5:
        raise EvidenceError('EXACT_FIVE_SCRIPT_PREPARATIONS_REQUIRED')
    client.ledger.save('prepared.json', {'campaign': campaign, 'results': results, 'human_acceptance': 'PENDING'})
    return results


def scripts(client, cases, campaign, request_key, authority):
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', request_key):
        raise EvidenceError('EXPLICIT_DURABLE_REQUEST_KEY_REQUIRED')
    queue = client.get('/api/production/queue')
    run_ids = {c['run_id'] for c in cases}
    rows = [r for r in queue['items'] if r['run_id'] in run_ids and r['planning']['campaign'] == campaign and r['actions']['script']]
    if len(rows) != 5:
        raise EvidenceError('EXACT_FIVE_APPROVED_BRIEFS_WITHOUT_SCRIPT_REQUIRED')
    known = client.get('/api/production/batches/' + request_key, optional=True)
    if known.get('http_status') != 404:
        raise EvidenceError('BATCH_KEY_ALREADY_EXISTS_READ_RECEIPT_NO_REPLAY')
    client.ledger.save('script-dispatch-authority.json', {'recorded_at': stamp(), 'authority_reference': authority,
        'actor': ACTOR, 'request_key': request_key, 'campaign': campaign, 'scope': 'explicit_5_draft_scripts_only',
        'human_script_review': 'PENDING', 'tts_render_dispatch_authorized': False})
    receipt = client.post('/api/production/batch', {'action': 'scripts', 'items': [
        {'id': r['id'], 'planning_version': r['planning']['version'], 'binding_sha256': r['binding_sha256']} for r in rows],
        'request_key': request_key, 'reviewer': ACTOR, 'acknowledged': True})
    client.ledger.save('script-batch.json', receipt)
    if receipt.get('status') != 'COMPLETED' or len(receipt.get('items', [])) != 5 or any(i.get('status') != 'QUEUED' for i in receipt['items']):
        raise EvidenceError('SCRIPT_BATCH_PARTIAL_OR_UNKNOWN_READ_RECEIPT_NO_REPLAY')
    return receipt


def script_bundle(client, cases, campaign):
    runs = [capture_run(client, c['run_id']) for c in cases]
    lines = ['# Phase 10 Final UAT — lời đọc và nguồn để Owner kiểm tra', '',
             'Đây là bản nháp chuẩn bị bởi Codex theo task Owner. Chưa duyệt kịch bản, storyboard/media hoặc video cuối; chưa tạo giọng/video.', '',
             'Nguồn nghiên cứu đã lưu từ Phase 9; ngày công bố được giữ nguyên. Không coi lượt đọc lại nguồn là nghiên cứu mới.', '']
    results = []
    for case, bundle in zip(cases, runs):
        opportunity = bundle['opportunity']
        if not opportunity or not opportunity.get('production_project_id'):
            continue
        captured = capture_project(client, opportunity['production_project_id'])
        project = captured['project']; proposal = project['document'].get('proposal')
        job = next((j for j in project['jobs'] if j['kind'] == 'content'), None)
        results.append({'case': case['case'], 'run_id': bundle['run']['id'], 'project_id': project['id'],
                        'revision': project['revision'], 'job_id': job['id'] if job else None,
                        'job_status': job['status'] if job else None, 'job_error': job['error'] if job else None,
                        'script_present': bool(proposal), 'narration_sha256': sha(proposal['narration'].encode('utf-8')) if proposal else None,
                        'human_script_review': project.get('script_review'), 'production_approval': project['approval']})
        lines += [f"## Ca {int(case['case']):02d} — {project['document']['name']}", '',
                  f"[Mở Studio]({client.base_url}/?project={project['id']}) · Dự án `{project['id']}` · Phiên bản {project['revision']}", '',
                  'Trạng thái kịch bản: ' + (job['status'] if job else 'chưa có job') + '.', '']
        if proposal:
            lines += ['### Lời đọc', '', proposal['narration'], '', '### Các cảnh', '']
            for n, scene in enumerate(proposal['visual_brief'], 1):
                lines += [f"{n}. {scene['narration_excerpt']}", '',
                          '   Chữ trên hình: ' + scene['on_screen_text'], '',
                          '   Hình đề xuất: ' + scene['visual'], '']
        else:
            lines += ['Chưa có bản nháp hoàn tất. Lỗi ghi đúng trong project/job receipt.', '']
        lines += ['### Nguồn và giới hạn', '']
        for source in bundle['sources']:
            lines += ['- ' + source['title'] + ' — ' + source['reference'] + ' — ngày công bố: ' +
                      (source.get('timestamp') or 'chưa rõ') + ' — lấy nguồn: ' + source['retrieved_at']]
        lines += ['', 'Dữ kiện nguồn đã lưu (chưa xác minh độc lập):', '']
        for finding in bundle['findings']:
            lines += ['- [' + finding['kind'] + '] ' + finding['claim']]
        lines += ['', 'Giới hạn brief:', ''] + ['- ' + c for c in (bundle['brief'] or {}).get('constraints', [])] + ['']
    summary = {'campaign': campaign, 'recorded_at': stamp(), 'scripts': results,
               'human_script_acceptance': 'PENDING', 'helper_tts_dispatches': 0, 'helper_render_dispatches': 0}
    client.ledger.save('script-review-manifest.json', summary)
    path = client.ledger.root / 'script-source-review-bundle.md'
    with path.open('x', encoding='utf-8') as handle:
        handle.write('\n'.join(lines) + '\n')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['inventory', 'queue', 'run', 'project', 'campaign', 'prepare', 'scripts', 'script-bundle'])
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--output-dir', type=Path, default=REPO / 'evidence/post-mvp-roadmap/phase-10/final-uat/campaign')
    parser.add_argument('--id')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--selection-plan', type=Path)
    parser.add_argument('--campaign')
    parser.add_argument('--authority-reference')
    parser.add_argument('--request-key')
    args = parser.parse_args(argv)
    mutating = args.command in {'prepare', 'scripts'}
    if mutating and (not args.authority_reference or not args.campaign):
        parser.error('Preparation requires explicit --authority-reference and --campaign; it does not record Owner acceptance.')
    ledger = Ledger(args.output_dir, args.command)
    client = Client(args.base_url, ledger, writes=mutating)
    result = None
    try:
        client.connect()
        cases, manifest = manifest_cases(args.manifest) if args.manifest else (None, None)
        if manifest:
            ledger.save('input-manifest.json', manifest)
        if args.command == 'inventory':
            result = {'health': client.get('/api/health'), 'capabilities': client.capabilities,
                      'projects': client.get('/api/projects?archived=include'), 'runs': client.get('/api/intelligence/runs'),
                      'queue': client.get('/api/production/queue'), 'profiles': client.get('/api/production/profiles')}
            ledger.save('inventory.json', result)
        elif args.command == 'queue':
            result = client.get('/api/production/queue')
            if args.campaign:
                result = {**result, 'items': [r for r in result['items'] if r['planning']['campaign'] == args.campaign]}
            ledger.save('queue.json', result)
        elif args.command == 'run':
            result = capture_run(client, identifier(args.id))
        elif args.command == 'project':
            result = capture_project(client, identifier(args.id))
        else:
            if not cases:
                raise EvidenceError('MANIFEST_REQUIRED')
            if args.command == 'campaign':
                result = capture_campaign(client, cases, args.campaign)
            elif args.command == 'prepare':
                if not args.selection_plan:
                    raise EvidenceError('SELECTION_PLAN_REQUIRED')
                choices = json.loads(args.selection_plan.read_bytes())
                ledger.save('selection-plan-input.json', {'path': str(args.selection_plan.resolve()),
                    'raw_sha256': sha(args.selection_plan.read_bytes()), 'selections': choices})
                if not isinstance(choices, list) or sum(c.get('prepare_script') is True for c in choices) != 5:
                    raise EvidenceError('EXACT_FIVE_PREPARATION_CHOICES_REQUIRED')
                result = prepare(client, cases, choices, args.campaign, args.authority_reference)
            elif args.command == 'scripts':
                result = scripts(client, cases, args.campaign, args.request_key or '', args.authority_reference)
            elif args.command == 'script-bundle':
                result = script_bundle(client, cases, args.campaign)
        summary = {'schema_version': SCHEMA, 'completed_at': stamp(), 'command': args.command,
                   'status': 'COMPLETED', 'evidence_directory': str(ledger.root), 'http_reads': client.read_count,
                   'http_writes': client.write_count, 'receipts': ledger.entries, 'result_sha256': digest(result),
                   'new_human_acceptance_recorded_by_helper': False, 'publishing_performed': False}
        ledger.save('receipt-index.json', summary)
        print(json.dumps({k: v for k, v in summary.items() if k != 'receipts'}, ensure_ascii=False))
        return 0
    except Exception as error:
        failure = {'schema_version': SCHEMA, 'completed_at': stamp(), 'command': args.command, 'status': 'STOPPED',
                   'error': str(error) if isinstance(error, (EvidenceError, ValueError)) else type(error).__name__,
                   'automatic_retry': False, 'evidence_directory': str(ledger.root), 'http_reads': client.read_count,
                   'http_writes': client.write_count, 'receipts': ledger.entries, 'new_human_acceptance_recorded_by_helper': False}
        ledger.save('receipt-index.json', failure)
        print(json.dumps({k: v for k, v in failure.items() if k != 'receipts'}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
