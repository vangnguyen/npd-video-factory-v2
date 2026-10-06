"""Read-only intelligence/production projection plus explicit local human actions."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import uuid

from .contracts import WorkflowError, digest, file_sha
from .hardening import Artifacts, version_components
from .planning_store import PlanningStore, human, validate_changes


CONFIG_PATH = Path(__file__).parent / 'profiles' / 'production-intelligence.json'
STAGES = ('IDEA', 'BRIEF_READY', 'SCRIPT_DRAFT', 'SCRIPT_REVIEW', 'STORYBOARD', 'READY_TO_PRODUCE',
          'PRODUCING', 'VIDEO_REVIEW', 'PRODUCED', 'REJECTED', 'FAILED')


def configuration(path=CONFIG_PATH):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    expected = {'relevance', 'freshness', 'campaign_priority', 'project_priority', 'readiness'}
    weights = value['priority']['weights']
    if (value.get('schema_version') != 'production-intelligence-config-v1' or set(weights) != expected
            or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in weights.values())
            or sum(weights.values()) <= 0 or set(value['priority']['readiness']) != set(STAGES)
            or not 0 < value['freshness']['window_days'] or not 0 <= value['similarity']['threshold'] <= 1):
        raise WorkflowError('PRODUCTION_INTELLIGENCE_CONFIG_INVALID')
    return value


def item_id(kind, identifier):
    return uuid.uuid5(uuid.NAMESPACE_URL, 'video-factory/production-queue/' + kind + '/' + identifier).hex


def instant(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def words(value):
    return set(re.findall(r'[^\W_]+', str(value).casefold(), re.UNICODE))


def profile_id(run):
    return run['context'].get('profile', {}).get('id') if run else None


def freshness(sources, config, as_of):
    rows = []
    for source in sources:
        published = instant(source.get('timestamp'))
        fetched = instant(source.get('retrieved_at'))
        age = (as_of - published).total_seconds() / 86400 if published else None
        fetched_age = (as_of - fetched).total_seconds() / 86400 if fetched else None
        known = source.get('publication_date_known', published is not None) and published is not None
        if not known:
            status, score = 'DATE_UNKNOWN', config['unknown_score']
        elif age < 0:
            status, score = 'FUTURE_DATE', 0
        elif age > config['window_days']:
            status, score = 'STALE', 0
        else:
            status, score = 'FRESH', max(0, 100 * (1 - age / config['window_days']))
        needs = status != 'FRESH' or fetched_age is None or fetched_age > config['revalidate_after_days']
        rows.append({'id': source['id'], 'source_type': source.get('source_type'), 'title': source.get('title'),
                     'reference': source.get('reference'), 'published_at': source.get('timestamp'),
                     'publication_date_known': bool(known), 'fetched_at': source.get('retrieved_at'),
                     'age_days': round(age, 2) if age is not None else None, 'status': status,
                     'score': round(score, 2), 'needs_revalidation': needs, 'content_sha256': source.get('content_sha256')})
    statuses = {s['status'] for s in rows}
    status = 'NO_SOURCES' if not rows else ('DATE_UNKNOWN' if 'DATE_UNKNOWN' in statuses else
             'FUTURE_DATE' if 'FUTURE_DATE' in statuses else 'STALE' if 'STALE' in statuses else 'FRESH')
    return {'status': status, 'score': round(sum(s['score'] for s in rows) / len(rows), 2) if rows else 0,
            'needs_revalidation': not rows or any(s['needs_revalidation'] for s in rows),
            'sources': rows, 'as_of': as_of.isoformat(), 'publication_and_retrieval_are_distinct': True}


def similarity(fields, candidates, config):
    warnings = []
    for candidate in candidates:
        matches = []
        for field in ('title', 'hook', 'script', 'topic'):
            a, b = words(fields.get(field, '')), words(candidate['fields'].get(field, ''))
            if min(len(a), len(b)) < config['minimum_tokens']:
                continue
            overlap = len(a & b) / len(a | b)
            if overlap >= config['threshold']:
                matches.append({'field': field, 'similarity': round(overlap, 4)})
        if matches:
            warnings.append({'target': candidate['target'], 'version': candidate['version'], 'title': candidate['fields'].get('title'),
                             'fields': matches, 'reason': 'Lexical overlap; human judgment required, not a plagiarism verdict.'})
    warnings.sort(key=lambda v: (-max(x['similarity'] for x in v['fields']), str(v['target'])))
    warnings = warnings[:config['maximum_warnings']]
    return {'warnings': warnings, 'warning_sha256': digest(warnings), 'method': 'CONFIGURED_LEXICAL_JACCARD',
            'threshold': config['threshold'], 'human_override_supported': True}


def priority(score, fresh, stage, planning, warning_count, config, as_of, config_sha):
    components = {'relevance': score if score is not None else 0, 'freshness': fresh['score'],
                  'campaign_priority': planning['campaign_priority'], 'project_priority': planning['project_priority'],
                  'readiness': config['readiness'][stage]}
    total = sum(components[k] * v for k, v in config['weights'].items()) / sum(config['weights'].values())
    penalty = config['duplicate_penalty'] if warning_count else 0
    return {'score': round(max(0, min(100, total - penalty)), 2), 'components': components,
            'weights': config['weights'], 'duplicate_penalty': penalty, 'scoring_type': 'HEURISTIC_SCORING',
            'rationale': ['Configured weighted average of current metadata; not statistically predictive.',
                          'Publication date determines freshness; fetching does not make old or undated research fresh.',
                          'Duplicate warning penalty applies even when a human chooses to proceed.'],
            'config_sha256': config_sha, 'as_of': as_of.isoformat()}


class ProductionIntelligence:
    schema_version = 'production-intelligence-v1'

    def __init__(self, config, production, intelligence, *, catalog=None, clock=None):
        self.config, self.production, self.intelligence = config, production, intelligence
        self.planning = PlanningStore(config.data_root)
        self.catalog = catalog or configuration()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def profiles(self):
        from .branding import catalog
        brands = catalog(include_landscape=True)
        refs = {p['profile_id']: p for p in self.catalog['profiles']}
        profiles = []
        for profile in self.intelligence.catalog['profiles']:
            profiles.append({**profile, **refs.get(profile['id'], {}), 'source_policy': self.catalog['source_policy'],
                             'voice': self.catalog['voice'], 'supported_aspect_ratios': sorted({t['aspect_ratio'] for t in brands['templates']}),
                             'planning_aspect_ratios': ['9:16', '16:9'], 'defaults_are_configuration': True})
        return {'schema_version': self.schema_version, 'profiles': profiles, 'brand_templates': brands,
                'priority_configuration': self.catalog['priority'], 'freshness_configuration': self.catalog['freshness'],
                'similarity_configuration': self.catalog['similarity'], 'config_sha256': digest(self.catalog)}

    def default_planning(self, row):
        defaults = self.catalog['planning']
        return {'schema_version': PlanningStore.schema_version, 'id': row['id'], 'version': 0,
                'created_at': row['created_at'], 'updated_at': row['created_at'], 'campaign': '', 'planned_date': None,
                'format': row.get('production_format') or defaults['default_format'],
                'duration_seconds': row.get('production_duration_seconds') or defaults['default_duration_seconds'],
                'project_priority': defaults['default_priority'], 'campaign_priority': defaults['default_priority'],
                'assigned_to': '', 'assigned_status': 'UNASSIGNED', 'similarity_override': None,
                'provenance': {'target': row['target'], 'origin': 'derived_default_unpersisted', 'configuration_sha256': digest(self.catalog)}}

    def records(self):
        return {kind: {r['id']: r for r in self.intelligence.store.list(kind)} for kind in
                ('Opportunity', 'ResearchRun', 'ContentIdea', 'ContentBrief', 'IdeaScore', 'ResearchSource')}

    def queue(self):
        records = self.records()
        projects = {p['id']: self.production.get(p['id']) for p in self.production.list(include_archived=True)}
        profiles = {p['id']: p for p in self.intelligence.catalog['profiles']}
        scores = {}
        for score in records['IdeaScore'].values():
            key = (score['idea_id'], score['idea_version'])
            if key not in scores or score['created_at'] > scores[key]['created_at']:
                scores[key] = score
        rows, attached = [], set()
        for opportunity in records['Opportunity'].values():
            run = records['ResearchRun'].get(opportunity['run_id'])
            if run is None:
                raise WorkflowError('PRODUCTION_RESEARCH_RUN_MISSING')
            project_id = opportunity.get('production_project_id')
            if project_id:
                attached.add(project_id)
                if project_id not in projects:
                    raise WorkflowError('PRODUCTION_PROJECT_REFERENCE_MISSING')
            idea = records['ContentIdea'].get(opportunity.get('selected_idea_id'))
            if not idea:
                current = [v for v in records['ContentIdea'].values() if v['run_id'] == run['id'] and v['generation'] == run['generation'] and v['status'] == 'CANDIDATE']
                current.sort(key=lambda v: (-(scores.get((v['id'], v['version'])) or {}).get('final_score', 0), v['id']))
                idea = current[0] if current else None
            brief = records['ContentBrief'].get(opportunity.get('brief_id'))
            project = projects.get(project_id)
            profile = run['context'].get('profile', profiles.get(profile_id(run), {}))
            sources = [records['ResearchSource'][identifier] for identifier in run['source_ids'] if identifier in records['ResearchSource']]
            if len(sources) != len(run['source_ids']):
                raise WorkflowError('PRODUCTION_RESEARCH_SOURCE_MISSING')
            score = scores.get((idea['id'], idea['version'])) if idea else None
            rows.append(self.row('opportunity', opportunity, run, idea, brief, project, profile, sources, score))
        for project in projects.values():
            if project['id'] in attached:
                continue
            lineage = project['document'].get('content_intelligence')
            if lineage:
                from .intelligence_lineage import validate
                validate(lineage)
                run, idea, brief = lineage['run'], lineage['idea'], lineage['brief']
                profile = run['context'].get('profile', profiles.get(profile_id(run), {}))
                sources = lineage['sources']
            else:
                run, idea, brief, profile, sources = None, None, None, {}, []
            rows.append(self.row('project', project, run, idea, brief, project, profile, sources, None))
        candidates = []
        for idea in records['ContentIdea'].values():
            run = records['ResearchRun'].get(idea['run_id'])
            if run and idea['generation'] == run['generation'] and idea['status'] not in {'REJECTED', 'SUPERSEDED'}:
                candidates.append({'target': {'kind': 'idea', 'id': idea['id'], 'opportunity_id': idea['opportunity_id']},
                                   'version': idea['version'], 'fields': {'title': idea['title'], 'hook': idea['hook'], 'topic': idea['angle']}})
        for row in rows:
            candidates.append({'target': {'kind': 'queue', 'id': row['id']}, 'version': digest(row['_fields']), 'fields': row['_fields']})
        # Immutable rendered snapshots contribute to similarity even when their project was later edited.
        rendered = sorted((j for p in projects.values() for j in p['jobs'] if j['kind'] == 'render' and j['status'] == 'succeeded'), key=lambda j: j['created_at'], reverse=True)
        for job in rendered[:self.catalog['similarity']['recent_video_limit']]:
            doc = job['snapshot']['document']; proposal = doc.get('proposal') or {}
            candidates.append({'target': {'kind': 'video', 'id': job['id'], 'project_id': job['project_id']}, 'version': digest(job['snapshot']),
                               'fields': {'title': proposal.get('title', doc['name']), 'hook': proposal.get('hook', ''), 'script': proposal.get('narration', ''), 'topic': doc['name']}})
        as_of = self.clock()
        for row in rows:
            others = [v for v in candidates if not (v['target'].get('id') == row['id'] or v['target'].get('id') == row['idea_id']
                      or v['target'].get('opportunity_id') == row['target']['id']
                      or (row['project_id'] is not None and v['target'].get('project_id') == row['project_id']))]
            row['similarity'] = similarity(row.pop('_fields'), others, self.catalog['similarity'])
            override = row['planning'].get('similarity_override')
            row['similarity']['override_current'] = bool(override and override['warning_sha256'] == row['similarity']['warning_sha256'])
            row['priority'] = priority(row['score'], row['freshness'], row['stage'], row['planning'], len(row['similarity']['warnings']), self.catalog['priority'], as_of, digest(self.catalog))
        rows.sort(key=lambda r: (-r['priority']['score'], r['id']))
        return {'schema_version': self.schema_version, 'items': rows, 'stages': list(STAGES), 'as_of': as_of.isoformat(),
                'scoring_type': 'HEURISTIC_SCORING', 'automatic_dispatch': False}

    def row(self, kind, origin, run, idea, brief, project, profile, sources, score):
        identifier = item_id(kind, origin['id']); doc = project['document'] if project else {}
        proposal = doc.get('proposal') or {}
        selection = doc.get('brand_template') or {}
        profile_config = next((v for v in self.catalog['profiles'] if v['profile_id'] == profile_id(run)), {})
        brand = selection.get('brand') or {}
        stage, diagnostic = self.stage(origin if kind == 'opportunity' else None, run, brief, project)
        target = {'kind': kind, 'id': origin['id']}
        binding = {'target': target, 'target_version': origin.get('version', origin.get('revision')), 'run_version': run['version'] if run else None,
                   'idea_id': idea['id'] if idea else None, 'idea_version': idea['version'] if idea else None,
                   'brief_id': brief['id'] if brief else None, 'brief_version': brief['version'] if brief else None,
                   'project_id': project['id'] if project else None, 'project_revision': project['revision'] if project else None}
        row = {'id': identifier, 'target': target, 'binding': binding, 'binding_sha256': digest(binding),
               'title': proposal.get('title') or (idea['title'] if idea else origin.get('topic', doc.get('name', ''))),
               'profile_id': profile_id(run), 'profile_name': profile.get('name', 'Nội dung trực tiếp'),
               'brand_id': brand.get('id') or profile_config.get('brand_id'), 'brand_name': brand.get('name'),
               'related_project': profile.get('related_project'), 'project_id': project['id'] if project else None,
               'source_titles': [s.get('title', '') for s in sources],
               'production_format': (selection.get('template') or {}).get('aspect_ratio'),
               'production_duration_seconds': (selection.get('template') or {}).get('duration_seconds'),
               'run_id': run['id'] if run else None, 'idea_id': idea['id'] if idea else None, 'brief_id': brief['id'] if brief else None,
               'stage': stage, 'stage_diagnostic': diagnostic, 'intelligence_status': origin.get('status') if kind == 'opportunity' else None,
               'score': score['final_score'] if score else None, 'scoring_type': 'HEURISTIC_SCORING',
               'freshness': freshness(sources, self.catalog['freshness'], self.clock()),
               'created_at': origin['created_at'], 'updated_at': max(origin['updated_at'], project['updated_at'] if project else origin['updated_at']),
               'archived': project.get('archived', False) if project else False,
               'actions': {'script': bool(brief and brief['status'] == 'APPROVED' and not proposal),
                           'storyboard': bool(project and proposal and ((project.get('script_review') or {}).get('current') or not doc.get('content_intelligence')))},
               '_fields': {'title': proposal.get('title') or (idea['title'] if idea else doc.get('name', '')),
                           'hook': idea['hook'] if idea else proposal.get('hook', ''), 'script': proposal.get('narration', ''),
                           'topic': origin.get('topic') or (idea['angle'] if idea else doc.get('name', ''))}}
        row['planning'] = self.planning.get(identifier, self.default_planning(row))
        return row

    def stage(self, opportunity, run, brief, project):
        if opportunity and opportunity['status'] == 'REJECTED':
            return 'REJECTED', None
        if project:
            doc = project['document']; revision = project['revision']; current = [j for j in project['jobs'] if j['revision'] == revision]
            if any(j['status'] in {'queued', 'running', 'retrying'} for j in current):
                return 'PRODUCING' if any(j['kind'] == 'render' for j in current if j['status'] in {'queued', 'running', 'retrying'}) else 'SCRIPT_DRAFT', None
            for job in current:
                if job['kind'] == 'render' and job['status'] == 'succeeded':
                    try:
                        self.video(job['id'])
                        return 'PRODUCED', None
                    except WorkflowError as exc:
                        if exc.code == 'HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED':
                            try:
                                self.validate_video(job, require_approval=False)
                                return 'VIDEO_REVIEW', None
                            except (WorkflowError, OSError, ValueError) as failure:
                                return 'FAILED', getattr(failure, 'code', 'VIDEO_ARTIFACT_UNAVAILABLE')
                        return 'FAILED', exc.code
                    except (OSError, ValueError):
                        return 'FAILED', 'VIDEO_ARTIFACT_UNAVAILABLE'
            if current and current[0]['status'] in {'failed', 'interrupted'}:
                return 'FAILED', (current[0]['error'] or {}).get('code', 'JOB_FAILED')
            approval = project['approval']
            if approval and approval['revision'] == revision and approval['snapshot_sha256'] == digest(doc):
                return 'READY_TO_PRODUCE', None
            if doc.get('proposal'):
                reviewed = (project.get('script_review') or {}).get('current') or not doc.get('content_intelligence')
                return ('STORYBOARD' if reviewed else 'SCRIPT_REVIEW'), None
            return 'SCRIPT_DRAFT', None
        if run and run['status'] == 'FAILED':
            return 'FAILED', (run.get('error') or {}).get('code', 'RESEARCH_FAILED')
        return ('BRIEF_READY' if brief and brief['status'] == 'APPROVED' else 'IDEA'), None

    def find(self, identifier):
        row = next((r for r in self.queue()['items'] if r['id'] == identifier), None)
        if not row:
            raise WorkflowError('PRODUCTION_QUEUE_ITEM_NOT_FOUND', 404)
        return row

    def save_planning(self, identifier, version, changes, reviewer):
        changes = validate_changes(changes)
        row = self.find(identifier)
        if changes.get('similarity_override') and changes['similarity_override'].get('warning_sha256') != row['similarity']['warning_sha256']:
            raise WorkflowError('SIMILARITY_WARNING_CHANGED_RELOAD')
        self.planning.save(identifier, self.default_planning(row), version, changes, reviewer, row['binding'])
        return self.find(identifier)

    def brief_preflight(self, identifier):
        brief = self.intelligence.store.get(identifier, 'ContentBrief')
        row = next((r for r in self.queue()['items'] if r['brief_id'] == identifier and r['run_id'] == brief['run_id']), None)
        if row is None:
            raise WorkflowError('CURRENT_SELECTED_BRIEF_REQUIRED')
        return {'schema_version': self.schema_version, 'brief_id': identifier, 'brief_version': brief['version'],
                'item_id': row['id'], 'binding_sha256': row['binding_sha256'], 'planning_version': row['planning']['version'],
                'freshness': row['freshness'], 'priority': row['priority'], 'similarity': row['similarity'],
                'similarity_override': row['planning'].get('similarity_override'),
                'human_override_required': bool(row['similarity']['warnings'] and not row['similarity']['override_current']),
                'approval_performed': False}

    def approve_brief(self, identifier, body):
        check = self.brief_preflight(identifier)
        if body.get('version') != check['brief_version'] or body.get('binding_sha256') != check['binding_sha256']:
            raise WorkflowError('PRODUCTION_BRIEF_PREFLIGHT_CHANGED_RELOAD')
        if check['human_override_required']:
            raise WorkflowError('DUPLICATE_REVIEW_REQUIRED')
        self.intelligence.approve_brief(identifier, body.get('version'), body.get('reviewer'), body.get('acknowledged'), body.get('note', ''))
        return self.intelligence.bundle(self.intelligence.store.get(identifier, 'ContentBrief')['run_id'])

    def calendar(self):
        queue = self.queue()
        return {'schema_version': self.schema_version, 'items': queue['items'], 'timezone': self.catalog['planning']['timezone'],
                'planning_only': True, 'scheduler_enabled': False, 'publish_enabled': False,
                'campaigns': sorted({r['planning']['campaign'] for r in queue['items'] if r['planning']['campaign']})}

    def batch(self, body):
        reviewer = human(body.get('reviewer'))
        action, entries, request_key = body.get('action'), body.get('items'), body.get('request_key')
        if (body.get('acknowledged') is not True or action not in {'scripts', 'storyboards'} or not isinstance(entries, list)
                or not 1 <= len(entries) <= 50 or not isinstance(request_key, str) or not 8 <= len(request_key) <= 100
                or any(not isinstance(e, dict) or not re.fullmatch('[a-f0-9]{32}', str(e.get('id', ''))) or type(e.get('planning_version')) is not int
                       or not re.fullmatch('[a-f0-9]{64}', str(e.get('binding_sha256', ''))) for e in entries)
                or len({e['id'] for e in entries}) != len(entries)):
            raise WorkflowError('HUMAN_BATCH_ACTION_FIELDS_REQUIRED', 400)
        request = {'action': action, 'items': entries, 'reviewer': reviewer, 'acknowledged': True}
        receipt, created = self.planning.begin_batch(request_key, request)
        if not created:
            if receipt['status'] == 'RUNNING':
                return {**receipt, 'status': 'OUTCOME_UNKNOWN_NO_REPLAY', 'resume_required': True}
            return receipt
        for entry in entries:
            result = {'id': entry['id'], 'action': action, 'status': 'SKIPPED'}
            try:
                row = self.find(entry['id'])
                if row['planning']['version'] != entry['planning_version'] or row['binding_sha256'] != entry['binding_sha256']:
                    raise WorkflowError('BATCH_STALE_ITEM_RELOAD')
                if row['archived']:
                    raise WorkflowError('PROJECT_ARCHIVED_RESTORE_FIRST')
                if action == 'scripts':
                    if row['similarity']['warnings'] and not row['similarity']['override_current']:
                        raise WorkflowError('DUPLICATE_REVIEW_REQUIRED')
                    if not row['actions']['script']:
                        raise WorkflowError('APPROVED_BRIEF_WITHOUT_SCRIPT_REQUIRED')
                    if row['project_id']:
                        project = self.production.get(row['project_id'])
                    else:
                        project = self.intelligence.send(row['brief_id'], row['binding']['brief_version'])
                    result.update(project_id=project['id'], project_revision=project['revision'], brief_imported=True)
                    key = 'planning-' + digest({'batch': request_key, 'item': entry['id'], 'action': action})[:64]
                    job = self.production.enqueue(project['id'], project['revision'], 'content', key)
                    result.update(status='QUEUED', project_id=project['id'], project_revision=project['revision'], job_id=job['id'], next='human_script_review')
                else:
                    if not row['actions']['storyboard']:
                        raise WorkflowError('CURRENT_HUMAN_SCRIPT_REVIEW_REQUIRED')
                    project = self.production.auto_plan(row['project_id'], row['binding']['project_revision'])
                    result.update(status='UPDATED', project_id=project['id'], project_revision=project['revision'], next='human_storyboard_media_review')
            except WorkflowError as exc:
                result.update(code=exc.code, message=exc.code, retry_automatically=False)
            except Exception as exc:
                # A local/provider dispatch may have completed. Never retry it under a new key implicitly.
                result.update(status='OUTCOME_UNKNOWN', code='BATCH_ITEM_OUTCOME_UNKNOWN', error_type=type(exc).__name__, retry_automatically=False)
            receipt['items'].append(result)
            receipt = self.planning.batch_progress(request_key, receipt)
        receipt['status'] = 'COMPLETED'
        return self.planning.batch_progress(request_key, receipt)

    def validate_video(self, job, require_approval=True):
        if job['kind'] != 'render' or job['status'] != 'succeeded':
            raise WorkflowError('VIDEO_NOT_RENDERED')
        snapshot = job['snapshot']; approval = snapshot.get('approval')
        if not approval or approval['revision'] != job['revision'] or approval['snapshot_sha256'] != digest(snapshot['document']):
            raise WorkflowError('VIDEO_SNAPSHOT_APPROVAL_INVALID')
        out = Path(self.config.data_root) / 'jobs' / job['id']
        checkpoint = Artifacts(out, job).load('render')
        result = job['result'] or {}; qc = result.get('qc') or {}
        if not checkpoint or checkpoint['result'] != result or qc.get('passed') is not True:
            raise WorkflowError('RENDER_CHECKPOINT_OR_QC_REQUIRED')
        path = out / 'final.mp4'
        if not path.is_file() or path.is_symlink() or out.resolve() not in path.resolve().parents:
            raise WorkflowError('RENDER_ARTIFACT_UNAVAILABLE')
        sha = file_sha(path)
        if sha != qc.get('final_sha256'):
            raise WorkflowError('RENDER_ARTIFACT_CHANGED')
        review = job.get('final_review')
        if require_approval and (not review or review['decision'] != 'approve' or review['artifact_sha256'] != sha
                                 or review['snapshot_sha256'] != digest(snapshot) or review['revision'] != job['revision']
                                 or review['job_id'] != job['id'] or review['project_id'] != job['project_id']):
            raise WorkflowError('HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED')
        from .intelligence_lineage import projection
        lineage = projection(snapshot['document'])
        return {'path': str(path.resolve()), 'mime': 'video/mp4', 'sha256': sha, 'bytes': path.stat().st_size,
                'job_id': job['id'], 'project_id': job['project_id'], 'revision': job['revision'],
                'snapshot_sha256': digest(snapshot), 'lineage': lineage, 'approval': review, 'qc': qc}

    def video(self, identifier):
        job = self.production.get_job(identifier)
        return self.validate_video(job)

    def library(self):
        items = []
        for summary in self.production.list(include_archived=True):
            project = self.production.get(summary['id'])
            for job in project['jobs']:
                if job['kind'] != 'render' or job['status'] != 'succeeded':
                    continue
                doc = job['snapshot']['document']; proposal = doc.get('proposal') or {}; lineage = doc.get('content_intelligence')
                row = {'id': job['id'], 'project_id': project['id'], 'title': proposal.get('title', doc['name']),
                       'profile_id': profile_id(lineage['run']) if lineage else None,
                       'created_at': job['created_at'], 'render_revision': job['revision'], 'project_revision': project['revision'],
                       'is_current_project_revision': job['revision'] == project['revision'] and digest(doc) == digest(project['document']),
                       'archived': project.get('archived', False), 'snapshot_sha256': digest(job['snapshot']),
                       'versions': {**version_components(doc), 'brief_version': lineage['brief']['version'] if lineage else None,
                                    'idea_version': lineage['idea']['version'] if lineage else None, 'render_job_id': job['id']},
                       'format': ((doc.get('brand_template') or {}).get('template') or {}).get('aspect_ratio', '9:16'),
                       'duration_seconds': (job['result'] or {}).get('qc', {}).get('duration_seconds'),
                       'approval': job.get('final_review'), 'approved': False, 'integrity': 'UNVERIFIED', 'lineage': None,
                       'video_url': None, 'thumbnail_url': None}
                try:
                    checked = self.validate_video(job, require_approval=False)
                    row.update(integrity='PASS', sha256=checked['sha256'], lineage=checked['lineage'])
                    self.validate_video(job)
                    row.update(approved=True, video_url='/api/production/videos/' + job['id'],
                               thumbnail_url='/api/production/videos/' + job['id'] + '/thumbnail')
                except (WorkflowError, OSError, ValueError) as exc:
                    row['diagnostic'] = getattr(exc, 'code', 'RENDER_ARTIFACT_UNAVAILABLE')
                    if row['integrity'] != 'PASS':
                        row['integrity'] = 'FAILED'
                items.append(row)
        items.sort(key=lambda r: (r['created_at'], r['id']), reverse=True)
        return {'schema_version': self.schema_version, 'items': items, 'historical_snapshots_preserved': True}
