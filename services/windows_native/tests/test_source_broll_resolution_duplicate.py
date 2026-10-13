"""Actual saved reviewed-plan lineage; every ASR/Vision/identity is fixture."""
import copy,unittest
from services.windows_native.contracts import digest,WorkflowError
from services.windows_native.stock import NativeStock
from services.windows_native.generation_queue import NativeGenerationQueue
from services.windows_native.generation_worker import NativeGenerationWorker
from services.windows_native.source_broll_resolution import NativeSourceBrollResolution
from services.windows_native.source_broll_resolution_models import Create,Step,Apply
from services.windows_native import source_duplicate
from services.windows_native.tests import test_source_broll_vision as fixture


class ReviewedDerivativeDuplicateTests(unittest.TestCase):
    def prepared(self):
        v=fixture.SourceBrollVisionTests('test_reviewed_mock_retains_lineage_without_changing_semantic_scores_or_source_timeline')
        v.setUp();self.addCleanup(v.tearDown);self.addCleanup(v.doCleanups)
        row=v.complete();v.create(row);record=v.project['document']['source_broll_plans'][-1]
        stock=NativeStock(v.store,v.config,workspace_id=v.workspace)
        generation=NativeGenerationWorker(NativeGenerationQueue(v.store,workspace_id=v.workspace),v.config)
        self.addCleanup(stock.close);self.addCleanup(generation.close)
        engine=NativeSourceBrollResolution(v.store,v.config,stock,generation,workspace_id=v.workspace,official_vision=lambda:v.official)
        session,_=engine.create(v.project['id'],Create(revision=v.project['revision'],expected_timeline_version=1,
            media_plan_id=record['plan']['media_plan_id'],expected_plan_version=record['plan']['version'],expected_plan_sha256=record['sha256'],
            item_ids=[record['plan']['items'][0]['media_plan_item_id']],request_key='duplicate-reviewed-resolution-fixture'),actor='fixture-editor')
        return v,engine,session

    def test_duplicate_archives_derivative_and_original_verbatim_without_transferring_authority(self):
        v,engine,session=self.prepared()
        engine.step(v.project['id'],session['resolution_id'],Step(revision=session['state']['expected']['revision'],
            expected_resolution_version=session['version'],request_key='duplicate-reviewed-resolution-step'),actor='fixture-editor')
        session=engine.get(v.project['id'],session['resolution_id']);self.assertEqual(session['state']['status'],'ready')
        engine.apply(v.project['id'],session['resolution_id'],Apply(revision=session['state']['expected']['revision'],
            expected_resolution_version=session['version'],expected_timeline_version=1,acknowledged=True,
            request_key='duplicate-reviewed-resolution-apply'),actor='fixture-editor')
        parent=copy.deepcopy(v.store.get(v.project['id']));records=copy.deepcopy(parent['document']['source_broll_plans'])
        calls=copy.deepcopy(v.calls);child=v.store.duplicate(parent['id'],parent['revision'])
        self.assertEqual(v.store.get(parent['id']),parent);self.assertEqual(v.calls,calls)
        self.assertEqual(child['document']['source_broll_plans'],[]);self.assertIsNone(child['approval'])
        archived=child['document']['source_broll_inherited_reviewed_history']
        self.assertEqual([r['original_record'] for r in archived],records)
        self.assertTrue(all(r['original_record_sha256']==digest(r['original_record']) and r['authority_transferred'] is False and r['new_plan_required'] is True for r in archived))
        clips=[c for t in child['document']['canonical_timeline']['snapshot']['tracks'] if t['kind']=='broll' for c in t['clips']]
        self.assertTrue(clips)
        self.assertTrue(all(c['metadata']['inherited_reviewed_vision']['authority_transferred'] is False for c in clips))
        with v.store.transaction() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM native_source_broll_resolutions WHERE project_id=?',(child['id'],)).fetchone()[0],0)

    def test_rehashed_outer_plan_cannot_hide_corrupted_nested_original_history(self):
        v,_,session=self.prepared();parent=v.store.get(v.project['id']);doc=copy.deepcopy(parent['document'])
        record=doc['source_broll_plans'][-1];record['plan']['provenance']['inherited_reviewed_source_history']['original_plan']['fingerprint']='0'*64
        record['sha256']=digest(record['plan']);before=v.store.list()
        with self.assertRaisesRegex(WorkflowError,'INHERITED_HISTORY_INVALID'):
            source_duplicate.rebind(doc,parent['id'],'f'*32,parent['revision'],'2026-10-13T00:00:00Z')
        self.assertEqual(v.store.list(),before)


if __name__=='__main__':unittest.main()
