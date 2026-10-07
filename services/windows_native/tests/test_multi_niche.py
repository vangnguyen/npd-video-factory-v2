"""Configuration-only technology acceptance contract; providers are fixtures."""
from pathlib import Path
import tempfile
import unittest
import uuid
import hashlib
from PIL import Image
from services.windows_native import branding
from services.windows_native.contracts import WorkflowError, digest
from services.windows_native.idea_engine import IdeaProvider
from services.windows_native.intelligence_lineage import projection
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.media import ingest_media
from services.windows_native.pipeline import Config
from services.windows_native.production_intelligence import ProductionIntelligence
from services.windows_native.research import PublicWebResearchProvider
from services.windows_native.store import Store


class ExplicitAIResearchFixture(PublicWebResearchProvider):
    key = 'explicit-ai-research-fixture-no-network'
    def __init__(self, directory):
        html = '<html><title>EXPLICIT AI TEST FIXTURE; no real research</title><p>AI education test fixture: source checking is an illustrative editorial topic for this test only; this is not a retrieved report or real trend observation.</p></html>'
        super().__init__(directory, fetch=lambda url: {'requested_url': url, 'final_url': url, 'status': 200,
            'content_type': 'text/html', 'raw_sha256': hashlib.sha256(html.encode()).hexdigest(), 'raw_bytes': len(html.encode()),
            'html': html})
    def research(self, query, context):
        sources, findings, metadata = super().research(query, context)
        sources = [s.model_copy(update={'source_type': 'test_fixture', 'provenance': {
            'origin': 'explicit_fixture', 'provider': self.key, 'real_retrieval': False}}) for s in sources]
        return sources, findings, {**metadata, 'provider': self.key, 'actual_retrievals': 0,
            'actual_provider_calls': 0, 'fixture_retrievals': len(sources), 'explicit_fixture': True}


class ExplicitAIIdeasFixture(IdeaProvider):
    def generate(self, query, context, findings, sources, out):
        finding = next(f for f in findings if f['kind'] == 'SOURCED_FACT')
        topics = ['Kiểm chứng nguồn', 'Đọc hướng dẫn', 'Phân biệt ví dụ', 'Hỏi về giới hạn', 'Lưu checklist']
        return [{'title': topic + ' — AI education fixture', 'hook': 'AI dễ hiểu: ví dụ minh họa cần được kiểm chứng.',
            'angle': topic + ': fixture editorial angle', 'target_audience': context['profile']['target_audience'],
            'format': 'Giải thích ngắn', 'estimated_duration': 30, 'cta': 'Lưu checklist và đặt câu hỏi.',
            'supporting_research': [finding['id']], 'evidence_references': [sources[0]['id']],
            'key_points': ['Ví dụ minh họa; chưa phải dữ kiện được xác minh.'],
            'rationale': 'Explicit fixture candidate, no provider or performance claim.'} for topic in topics], {
                'provider': 'explicit-ai-ideas-fixture', 'actual_provider_calls': 0, 'explicit_fixture': True}


def build_tech_project(root):
    config = Config(data_root=root)
    store = Store(root)
    preserved = store.create('Preserved unrelated project', 'Original owner input remains unchanged')
    preserved_before = store.get(preserved['id'])
    service = IntelligenceService(config, store, research_provider=ExplicitAIResearchFixture(root / 'research-sources'),
        idea_provider=ExplicitAIIdeasFixture())
    bundle = service.create('AI education source checking', 'ai-education', ['https://example.com/explicit-fixture'])
    for action in ('research', 'ideas'):
        service.enqueue(bundle['run']['id'], bundle['run']['version'], action, uuid.uuid4().hex)
        assert service.run_one()
        bundle = service.bundle(bundle['run']['id'])
        assert bundle['operations'][0]['status'] == 'SUCCEEDED'
    idea = bundle['ideas'][0]
    brief = service.select(idea['id'], idea['version'], bundle['opportunity']['version'], 'EXPLICIT MOCK REVIEW; NOT OWNER UAT')
    brief = service.approve_brief(brief['id'], brief['version'], 'EXPLICIT MOCK REVIEW; NOT OWNER UAT', True,
        'Fixture validates the gate; not real research, human acceptance or publishing approval.')
    project = service.send(brief['id'], brief['version'])
    narration = 'Đây là ví dụ AI minh họa. Nội dung cần được người xem kiểm chứng.'
    proposal = {'narration': narration, 'visual_brief': [{'scene': 1, 'visual': 'Explicit owned technology fixture card',
        'on_screen_text': 'AI dễ hiểu · ví dụ minh họa', 'narration_excerpt': narration}],
        'facts_needing_source': ['Fixture only; no real-world source verification or AI output claim.']}
    project = store.save(project['id'], project['revision'], proposal=proposal)
    source = root / 'explicit-ai-card.png'
    Image.new('RGB', (640, 360), '#10233b').save(source)
    asset = ingest_media(config, source, 'image/png', source.name, rights_confirmed=True, illustration=True)
    project = store.append_media(project['id'], project['revision'], asset)
    project = store.auto_plan(project['id'], project['revision'])
    project = store.set_brand(project['id'], project['revision'], 'vf-ai-education', 'ai-education-30')
    assert store.get(preserved['id']) == preserved_before and project['approval'] is None and project['jobs'] == []
    return config, store, service, project, service.bundle(bundle['run']['id']), preserved_before


class MultiNicheContractTests(unittest.TestCase):
    def test_configured_technology_flow_reuses_research_idea_production_editor_and_frozen_brand(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            config, store, service, project, bundle, preserved = build_tech_project(root)
            self.assertEqual(bundle['run']['context']['profile']['id'], 'ai-education')
            self.assertEqual(bundle['sources'][0]['source_type'], 'test_fixture')
            self.assertEqual(bundle['run']['provider_metadata']['actual_provider_calls'], 0)
            self.assertEqual(len(bundle['ideas']), 5)
            self.assertTrue(all(i['score']['scoring_type'] == 'HEURISTIC_SCORING' for i in bundle['ideas']))
            self.assertEqual(projection(project['document'])['content_idea_id'], bundle['brief']['idea_id'])
            selected = project['document']['brand_template']
            self.assertEqual(selected['brand']['id'], 'vf-ai-education')
            self.assertEqual(selected['template']['duration_policy'], branding.FIT_NARRATION_POLICY)
            self.assertNotIn('giao dịch', selected['brand']['project_disclaimers'][0])
            self.assertAlmostEqual(branding.measured_duration(project['document'], 5), 7.1)
            self.assertEqual(project['document']['edit_plan']['cta'], selected['brand']['primary_cta'])
            reopened = Store(root).get(project['id'])
            self.assertEqual(reopened['document'], project['document'])
            self.assertIsNone(reopened['approval']); self.assertEqual(reopened['jobs'], [])
            with self.assertRaisesRegex(WorkflowError, 'HUMAN_APPROVAL'):
                store.enqueue(project['id'], project['revision'], 'render', uuid.uuid4().hex)
            self.assertEqual(store.get(preserved['id']), preserved)

    def test_existing_profile_and_template_families_coexist_with_reference_ai_configuration(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); config = Config(data_root=root); store = Store(root)
            service = IntelligenceService(config, store, idea_provider=ExplicitAIIdeasFixture())
            profiles = ProductionIntelligence(config, store, service).profiles()
            self.assertEqual(len(profiles['profiles']), 6)
            technology = next(p for p in profiles['profiles'] if p['id'] == 'ai-education')
            self.assertEqual(technology['brand_id'], 'vf-ai-education')
            self.assertEqual(technology['template_family'], 'ai-education')
            self.assertEqual(technology['project_references'], [])
            templates = profiles['brand_templates']['templates']
            self.assertEqual(len(templates), 30)
            self.assertEqual(len([t for t in templates if t['id'].startswith('ai-education-')]), 6)
            self.assertTrue(all(t['duration_policy'] == branding.FIT_NARRATION_POLICY for t in templates if t['id'].startswith('ai-education-')))


if __name__ == '__main__':
    unittest.main()
