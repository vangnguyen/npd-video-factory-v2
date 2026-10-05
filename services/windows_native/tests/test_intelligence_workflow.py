"""Fixtures verify contracts only; never presented as actual provider/human acceptance."""
from pathlib import Path
import tempfile
import unittest
import uuid
from services.windows_native.contracts import WorkflowError, digest
from services.windows_native.idea_engine import IdeaProvider
from services.windows_native.intelligence_lineage import projection
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.pipeline import Config
from services.windows_native.research import PublicWebResearchProvider
from services.windows_native.store import Store
from services.windows_native.tests.test_intelligence_engines import receipt


class FixtureIdeas(IdeaProvider):
    def generate(self,query,context,findings,sources,out):
        factual=next(f for f in findings if f['kind']=='SOURCED_FACT'); source=factual['source_references'][0]['source_id']
        return [{'title':'Test fixture idea '+str(i),'hook':'Fixture hook for a human contract test','angle':'Editorial fixture angle '+str(i),'target_audience':context['profile']['target_audience'],'format':'Checklist','estimated_duration':30,'cta':'Nhận checklist','supporting_research':[factual['id']],'evidence_references':[source],'key_points':['Fixture only, no real world claim'],'rationale':'Explicit test fixture, never a provider PASS'} for i in range(5)],{'provider':'test_fixture','actual_provider_calls':0}


class IntelligenceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.config=Config(data_root=self.root)
        self.production=Store(self.root)
        self.service=IntelligenceService(self.config,self.production,research_provider=PublicWebResearchProvider(self.root/'research-sources',fetch=lambda url:receipt()),idea_provider=FixtureIdeas())
        self.original=self.production.create('Preserved owner project','Existing input')

    def tearDown(self): self.temp.cleanup()

    def candidates(self):
        bundle=self.service.create('housing research','vietnam-property',['https://example.com/test'])
        for action in ('research','ideas'):
            operation=self.service.enqueue(bundle['run']['id'],bundle['run']['version'],action,uuid.uuid4().hex)
            self.assertTrue(self.service.run_one())
            bundle=self.service.bundle(bundle['run']['id'])
            self.assertEqual(bundle['operations'][0]['status'],'SUCCEEDED')
        return bundle

    def selected(self):
        b=self.candidates(); i=b['ideas'][0]
        self.service.select(i['id'],i['version'],b['opportunity']['version'],'TEST FIXTURE reviewer')
        return self.service.bundle(b['run']['id'])

    def test_research_five_scores_selection_brief_bridge_and_preserved_production(self):
        b=self.selected(); self.assertEqual(len(b['ideas']),5)
        self.assertTrue(all(i['score']['scoring_type']=='HEURISTIC_SCORING' for i in b['ideas']))
        brief=b['brief']
        with self.assertRaisesRegex(WorkflowError,'APPROVED_BRIEF'): self.service.send(brief['id'],brief['version'])
        with self.assertRaisesRegex(WorkflowError,'HUMAN_REVIEW'): self.service.approve_brief(brief['id'],brief['version'],'TEST FIXTURE reviewer',False)
        brief=self.service.approve_brief(brief['id'],brief['version'],'TEST FIXTURE reviewer',True,'Unit contract approval; not human acceptance')
        project=self.service.send(brief['id'],brief['version']); again=self.service.send(brief['id'],brief['version'])
        self.assertEqual(again['id'],project['id']); self.assertIsNone(project['approval']); self.assertEqual(project['jobs'],[])
        self.assertEqual(projection(project['document'])['content_idea_id'],brief['idea_id'])
        with self.assertRaisesRegex(WorkflowError,'HUMAN_APPROVAL'): self.production.enqueue(project['id'],1,'render',uuid.uuid4().hex)
        self.assertEqual(self.production.get(self.original['id']),self.original)
        doc=project['document']; doc['content_intelligence']['brief']['hook']='Tampered'
        with self.assertRaisesRegex(WorkflowError,'LINEAGE_CHANGED'): projection(doc)

    def test_editing_brief_invalidates_approval_and_immutable_history_retains_decision(self):
        b=self.selected(); brief=self.service.approve_brief(b['brief']['id'],b['brief']['version'],'TEST FIXTURE reviewer',True)
        changed=self.service.edit_brief(brief['id'],brief['version'],{'hook':'Updated editorial hook'},'TEST FIXTURE reviewer')
        self.assertEqual(changed['status'],'DRAFT'); self.assertIsNone(changed['approval'])
        with self.assertRaisesRegex(WorkflowError,'APPROVED_BRIEF'): self.service.send(changed['id'],changed['version'])
        self.assertTrue(any(v['status']=='APPROVED' for v in self.service.store.history(brief['id'])))

    def test_change_candidate_supersedes_brief_and_rejection_requires_reason(self):
        b=self.selected(); old=b['brief']; second=next(i for i in b['ideas'] if i['id']!=old['idea_id'])
        self.service.select(second['id'],second['version'],b['opportunity']['version'],'TEST FIXTURE reviewer')
        self.assertEqual(self.service.store.get(old['id'])['status'],'SUPERSEDED')
        with self.assertRaisesRegex(WorkflowError,'REJECTION_REASON'): self.service.edit_idea(second['id'],second['version']+1,{'note':''},'TEST FIXTURE reviewer','reject')
        idea=self.service.store.get(second['id']); self.service.edit_idea(idea['id'],idea['version'],{'note':'Fixture rejection'},'TEST FIXTURE reviewer','reject')
        b=self.service.bundle(b['run']['id']); self.assertIsNone(b['brief']); self.assertEqual(b['opportunity']['status'],'REJECTED')

    def test_regeneration_retains_old_candidates_and_refuses_stale_selection(self):
        b=self.selected(); old=b['ideas'][0]; brief=b['brief']
        self.service.enqueue(b['run']['id'],b['run']['version'],'ideas',uuid.uuid4().hex); self.service.run_one()
        b=self.service.bundle(b['run']['id']); self.assertEqual(len(b['ideas']),10)
        self.assertEqual(sum(i['generation']==2 for i in b['ideas']),5)
        self.assertEqual(self.service.store.get(brief['id'])['status'],'SUPERSEDED')
        old=self.service.store.get(old['id'])
        with self.assertRaisesRegex(WorkflowError,'SUPERSEDED'): self.service.select(old['id'],old['version'],b['opportunity']['version'],'TEST FIXTURE reviewer')

    def test_source_file_tampering_blocks_approval(self):
        b=self.selected(); source=b['sources'][0]
        (self.root/'research-sources'/source['id']/'source.html').write_text('Changed',encoding='utf-8')
        with self.assertRaisesRegex(WorkflowError,'SOURCE_CHANGED'): self.service.approve_brief(b['brief']['id'],b['brief']['version'],'TEST FIXTURE reviewer',True)

    def test_windows_crlf_source_bytes_are_retained_without_line_ending_conversion(self):
        raw=receipt();raw['html']=raw['html'].replace('<p>','\r\n<p>').replace('</p>','</p>\r\n')
        self.service.research_provider.fetch=lambda url:raw
        b=self.candidates(); source=b['sources'][0]
        self.assertEqual((self.root/'research-sources'/source['id']/'source.html').read_bytes(),raw['html'].encode('utf-8'))
        self.service.verify_sources(b['sources'],b['findings'])

    def test_early_text_mode_sources_require_hash_proven_line_ending_reconstruction(self):
        b=self.candidates();source=b['sources'][0]; directory=self.root/'research-sources'/source['id']
        source['raw_provenance'].pop('storage_format')
        from services.windows_native.contracts import canonical
        (directory/'retrieval.json').write_bytes(canonical(source['raw_provenance']))
        for filename in ('source.html','source-text.txt'):
            raw=(directory/filename).read_bytes();(directory/filename).write_bytes(raw.replace(b'\n',b'\r\n'))
        self.service.verify_sources([source],b['findings'])
        (directory/'source-text.txt').write_bytes(b'Invented source text')
        with self.assertRaisesRegex(WorkflowError,'SOURCE_CHANGED'):self.service.verify_sources([source],b['findings'])

    def test_failed_research_has_explicit_error_and_no_fabricated_results(self):
        def fail(url): raise WorkflowError('RESEARCH_HTTP_ERROR',http_status=403)
        self.service.research_provider.fetch=fail
        b=self.service.create('housing','vietnam-property',['https://example.com/test'])
        self.service.enqueue(b['run']['id'],1,'research',uuid.uuid4().hex); self.service.run_one()
        b=self.service.bundle(b['run']['id']); self.assertEqual(b['run']['status'],'FAILED'); self.assertEqual(b['findings'],[])
        self.assertEqual(b['run']['error']['http_status'],403); self.assertFalse(b['run']['error']['automatic_replay'])

    def test_idempotent_request_conflict_and_restart_unknown_outcome_refusal(self):
        b=self.service.create('housing','vietnam-property',['https://example.com/test']); key=uuid.uuid4().hex
        first=self.service.enqueue(b['run']['id'],1,'research',key)
        self.assertEqual(self.service.enqueue(b['run']['id'],1,'research',key)['id'],first['id'])
        with self.assertRaisesRegex(WorkflowError,'KEY_CONFLICT'): self.service.enqueue(b['run']['id'],2,'research',key)
        with self.service.store.transaction() as con: con.execute("UPDATE operations SET status='RUNNING' WHERE id=?",(first['id'],))
        self.service.start(); self.service.stop.set(); self.service.wake.set(); self.service.thread.join(2)
        b=self.service.bundle(b['run']['id']); self.assertEqual(b['operations'][0]['status'],'FAILED'); self.assertFalse(self.service.run_one())
        self.assertIn('OUTCOME_UNKNOWN',b['run']['error']['code'])

    def test_idea_edit_cannot_replace_research_or_approve_by_editing(self):
        b=self.candidates(); idea=b['ideas'][0]
        for field in ('supporting_research','provenance','status'):
            with self.assertRaisesRegex(WorkflowError,'EDIT_FIELDS'): self.service.edit_idea(idea['id'],idea['version'],{field:'Injected'},'TEST FIXTURE reviewer')
        changed=self.service.edit_idea(idea['id'],idea['version'],{'hook':'Updated human fixture hook'},'TEST FIXTURE reviewer')
        self.assertEqual(changed['status'],'CANDIDATE')
        self.assertEqual(self.service.bundle(b['run']['id'])['ideas'][0]['score']['scoring_type'],'HEURISTIC_SCORING')
