"""Immutable owner definitions, exact CAS/idempotency and workspace boundaries."""
import copy,json,sqlite3,tempfile,unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from services.windows_native.store import Store
from services.windows_native.channel_registry import NativeChannelRegistry,Mutation
from services.windows_native.channel_profiles import catalog,select,resolve
from services.windows_native.contracts import WorkflowError
from unittest.mock import patch

class ChannelRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name));self.registry=NativeChannelRegistry(self.store,'wsp_channel_test')
        self.profile=copy.deepcopy(catalog()['profiles'][0]);self.profile.update(profile_ref='owned-ai@1',name='Owned AI channel')
        self.profile['niche_profile'].update(profile_ref='owned-ai-niche@1',target_audience='Người học mới của kênh',tone='Giải thích cụ thể',keywords=['kiểm chứng'])
    def tearDown(self):self.temp.cleanup()
    def payload(self,*,action='save',current=None,profile=None,key='owned-ai',request='owned-channel-request-0001'):
        return Mutation.model_validate({'profile_key':key,'action':action,'expected_revision':current['revision'] if current else 0,
            'expected_binding_sha256':current['binding_sha256'] if current else None,'profile':profile if profile is not None else self.profile if action=='save' else None,'request_key':request})
    def save(self,payload=None):return self.registry.mutate(payload or self.payload(),actor='explicit-owner-fixture')
    def test_custom_audience_tone_freeze_and_builtin_catalog_stays_exact(self):
        before=catalog();item=self.save()['item'];selection=select('owned-ai@1',store=self.store,workspace_id='wsp_channel_test')
        self.assertEqual(selection['content_profile']['target_audience'],'Người học mới của kênh');self.assertEqual(selection['content_profile']['tone'],'Giải thích cụ thể')
        project=self.store.create('Frozen owner profile','Owned script',channel_profile=selection)
        self.assertEqual(resolve(project['document']),selection);self.assertEqual(catalog(),before);self.assertEqual(len(self.registry.catalog()['profiles']),3)
        self.assertFalse(item['archived']);self.assertEqual(project['jobs'],[])
    def test_update_keeps_existing_project_and_immutable_versions_then_rejects_stale(self):
        first=self.save()['item'];selection=select('owned-ai@1',store=self.store,workspace_id='wsp_channel_test');project=self.store.create('Old frozen project','Owned script',channel_profile=selection)
        next_profile=copy.deepcopy(self.profile);next_profile.update(profile_ref='owned-ai@2',name='Updated channel')
        second=self.save(self.payload(current=first,profile=next_profile,request='owned-channel-request-0002'))['item']
        self.assertEqual(second['version'],2);self.assertEqual(self.store.get(project['id']),project)
        self.assertEqual([r['version'] for r in self.registry.history('owned-ai')['items']],[2,1])
        self.assertEqual(self.registry.history('owned-ai',limit=1)['next_before_version'],2)
        with self.assertRaisesRegex(WorkflowError,'NOT_CURRENT'):select('owned-ai@1',store=self.store,workspace_id='wsp_channel_test')
        with self.assertRaisesRegex(WorkflowError,'STALE'):self.save(self.payload(current=first,profile=next_profile,request='owned-channel-request-0003'))
    def test_archive_restore_and_exact_replay_never_reset_current_state(self):
        original=self.payload();first=self.save(original)['item'];archived=self.save(self.payload(action='archive',current=first,request='owned-channel-archive-001'))['item']
        self.assertTrue(archived['archived']);self.assertEqual(len(self.registry.catalog()['profiles']),2)
        with self.assertRaisesRegex(WorkflowError,'NOT_CURRENT'):select('owned-ai@1',store=self.store,workspace_id='wsp_channel_test')
        replay=self.save(original);self.assertTrue(replay['idempotent_replay']);self.assertEqual(self.registry.page()['items'][0],archived)
        restored=self.save(self.payload(action='restore',current=archived,request='owned-channel-restore-001'))['item'];self.assertFalse(restored['archived'])
        self.assertEqual(restored['version'],1);self.assertEqual(restored['revision'],3)
    def test_foreign_workspace_and_reserved_builtin_key_are_unavailable(self):
        self.save();foreign=NativeChannelRegistry(self.store,'wsp_other_channel');self.assertEqual(foreign.page()['items'],[])
        with self.assertRaisesRegex(WorkflowError,'NOT_FOUND'):select('owned-ai@1',store=self.store,workspace_id=foreign.workspace)
        with self.assertRaisesRegex(WorkflowError,'READ_ONLY'):self.save(self.payload(key='ai-education-reference'))
    def test_concurrent_exact_key_creates_only_one_version(self):
        payload=self.payload()
        with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(lambda _:self.save(payload),range(2)))
        self.assertEqual(sorted(r['idempotent_replay'] for r in results),[False,True]);self.assertEqual(len(self.registry.history('owned-ai')['items']),1)
        changed=self.profile.copy();changed['name']='Conflict'
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.save(self.payload(profile=changed))
    def test_late_receipt_write_failure_rolls_back_version_state_and_request(self):
        with self.store.transaction() as con:
            con.execute("CREATE TRIGGER owned_fail_channel_receipt BEFORE INSERT ON native_channel_profile_requests BEGIN SELECT RAISE(ABORT,'explicit-fixture-failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.save()
        self.assertEqual(self.registry.page()['items'],[]);self.assertEqual(self.registry.history('owned-ai')['items'],[])
    def test_invalid_reference_or_configuration_is_atomic(self):
        for extra in [{'profile_ref':'owned-ai@2'},{'brand_id':'unknown-brand'},{'video_template_id':'unknown-template'}]:
            p={**self.profile,**extra}
            with self.assertRaises(WorkflowError):self.save(self.payload(profile=p))
            self.assertEqual(self.registry.page()['items'],[])
    def test_corrupt_record_is_not_used_by_catalog_or_new_projects(self):
        self.save()
        with self.store.transaction() as con:
            row=con.execute('SELECT record_json FROM native_channel_profile_versions').fetchone();value=json.loads(row[0]);value['profile']['name']='Corrupt'
            con.execute('UPDATE native_channel_profile_versions SET record_json=?',(json.dumps(value),))
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):self.registry.catalog()
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):select('owned-ai@1',store=self.store,workspace_id='wsp_channel_test')
    def test_historical_receipt_cannot_hide_a_missing_immutable_definition(self):
        payload=self.payload();self.save(payload)
        with self.store.transaction() as con:con.execute('DELETE FROM native_channel_profile_versions')
        with self.assertRaisesRegex(WorkflowError,'REQUEST_EVIDENCE_CHANGED'):self.save(payload)
        with self.store.transaction() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM native_channel_profile_versions').fetchone()[0],0)
            self.assertEqual(con.execute('SELECT revision FROM native_channel_profile_states').fetchone()[0],1)
    def english_document(self):
        self.profile['niche_profile'].update(language='en',locale='en-US',country='US');self.save()
        return self.store.create('English draft','An educational script',channel_profile=select('owned-ai@1',store=self.store,workspace_id='wsp_channel_test'))['document']
    def test_unapproved_english_project_still_checks_human_approval_first(self):
        from services.windows_native.pipeline import synthesize
        with patch('services.windows_native.pipeline.verify_runtime') as runtime:
            with self.assertRaisesRegex(WorkflowError,'HUMAN_APPROVAL_REQUIRED_BEFORE_TTS'):synthesize(None,{'approval':None,'document':self.english_document()},None)
            runtime.assert_not_called()
    def test_approved_unconfigured_english_narration_never_loads_voice_runtime(self):
        from services.windows_native.pipeline import synthesize
        from services.windows_native.contracts import digest
        doc=self.english_document()
        with patch('services.windows_native.pipeline.verify_runtime') as runtime:
            with self.assertRaisesRegex(WorkflowError,'CHANNEL_NARRATION_LANGUAGE_NOT_CONFIGURED'):synthesize(None,{'approval':{'snapshot_sha256':digest(doc)},'document':doc},None)
            runtime.assert_not_called()

if __name__=='__main__':unittest.main()
