import copy,unittest
from unittest.mock import patch
from pydantic import ValidationError
from services.windows_native.tests.test_official_vision import OfficialVisionFixture
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.official_vision_evidence import ReviewedVision,build_context,validate_saved,ranking_inputs

class ReviewedVisionEvidenceTests(OfficialVisionFixture,unittest.TestCase):
    def complete(self):return self.process(self.create())
    def ref(self,row,**change):return ReviewedVision.model_validate({'vision_id':row['vision_id'],'expected_snapshot_sha256':row['snapshot_sha256'],
        'expected_result_sha256':row['result_sha256'],'acknowledged_reviewed_result':True,'acknowledged_protocol_mock':True,**change})
    def select(self,row,**change):
        value=self.store.get(self.project['id'])
        with self.store.transaction() as con:return build_context(self.official,value,[self.ref(row,**change)],source_con=con)
    def test_current_original_mock_lineage_uses_same_transaction_no_mutation_or_second_call(self):
        row=self.complete();before=self.store.get(self.project['id']);value=self.select(row)
        self.assertFalse(value['semantic_vision_used']);self.assertTrue(value['mock_present']);item=value['items'][0]
        self.assertEqual(item['response_sha256'],row['response']['response_sha256']);self.assertEqual(item['cost_operation_id'],row['cost_operation_id'])
        self.assertEqual(item['source_frame_evidence'],row['snapshot']['input_binding']['source_frame_evidence']);self.assertIsNone(item['observed_actual_billed_cost_vnd'])
        self.assertEqual(ranking_inputs(item)['semantic_tokens'],set());self.assertIsNone(ranking_inputs(item)['predicted_sample_quality'])
        self.assertEqual(len(self.calls),1);self.assertEqual(self.store.get(self.project['id']),before)
        with self.store.transaction() as con:self.assertEqual(validate_saved(self.official,before,value,source_con=con,current=True),value)
    def test_original_deadline_can_expire_without_renewal_or_current_credentials_for_read(self):
        row=self.complete();self.clock[0]+=__import__('datetime').timedelta(hours=3);self.revoke()
        value=self.select(row);self.assertEqual(value['items'][0]['original_deadline'],row['snapshot']['deadline']);self.assertEqual(len(self.calls),1)
        disabled=self.runtime(enabled=False,factories={});current=self.store.get(self.project['id'])
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No projection key access')):
            with self.store.transaction() as con:self.assertEqual(validate_saved(disabled,current,value,source_con=con),value)
    def test_source_change_refuses_current_reuse_but_original_history_remains_readable(self):
        row=self.complete();saved=self.select(row);path=self.config.data_root/'assets'/row['snapshot']['source']['asset']['id']
        raw=path.read_bytes();path.write_bytes(raw+b'changed fixture')
        with self.assertRaises(WorkflowError):self.select(row)
        current=self.store.get(self.project['id'])
        with self.store.transaction() as con:self.assertEqual(validate_saved(self.official,current,saved,source_con=con),saved)
        self.assertEqual(len(self.calls),1)
    def test_hash_mock_and_raw_review_changes_are_not_admitted(self):
        row=self.complete()
        for change in ({'expected_snapshot_sha256':'0'*64},{'expected_result_sha256':'0'*64},{'acknowledged_protocol_mock':False}):
            with self.assertRaises(WorkflowError):self.select(row,**change)
        for value in (1,'true',False):
            with self.assertRaises(ValidationError):self.ref(row,acknowledged_reviewed_result=value)
        for value in (1,'false',None):
            with self.assertRaises(ValidationError):self.ref(row,acknowledged_protocol_mock=value)
        self.assertEqual(len(self.calls),1)
    def test_duplicate_and_foreign_selection_fail_without_dispatch(self):
        row=self.complete();current=self.store.get(self.project['id']);other=self.store.create('Other fixture','No provider')
        with self.store.transaction() as con:
            with self.assertRaises(WorkflowError):build_context(self.official,current,[self.ref(row),self.ref(row)],source_con=con)
            with self.assertRaises(WorkflowError):build_context(self.official,other,[self.ref(row)],source_con=con)
        self.assertEqual(len(self.calls),1)
    def test_saved_projection_rehash_cannot_promote_mock_or_modify_original_confidence(self):
        row=self.complete();value=self.select(row);current=self.store.get(self.project['id'])
        for field,change in [('semantic_vision_used',True),('original_provider_consent_renewed',True),('paid_operations',1),
            ('owner_uat_accepted',0),('mock_present',1),('external_dispatches',False)]:
            forged=copy.deepcopy(value);forged[field]=change
            with self.store.transaction() as con:
                with self.assertRaises(WorkflowError):validate_saved(self.official,current,forged,source_con=con)
        forged=copy.deepcopy(value);forged['items'][0]['frames'][0]['confidence']=.99
        with self.store.transaction() as con:
            with self.assertRaises(WorkflowError):validate_saved(self.official,current,forged,source_con=con)
        self.assertEqual(len(self.calls),1)
    def test_pure_nonmock_ranking_contract_uses_labels_not_an_actual_provider_acceptance(self):
        # This typed synthetic vector exercises the pure consumer calculation only.
        # It is never admitted as an actual stored response by build_context().
        row=self.complete();item=copy.deepcopy(self.select(row)['items'][0]);item['mock']=False;item['semantic_inference_performed']=True
        item['frames'][0]['caption']='Educational explanation of neural network technology'
        result=ranking_inputs(item);self.assertIn('neural',result['semantic_tokens']);self.assertEqual(result['predicted_sample_quality'],.5)
        self.assertEqual(result['uncalibrated_min_confidence'],.5);self.assertEqual(len(self.calls),1)

    def test_constructed_or_mutated_selection_cannot_bypass_raw_ack_or_extra_fields(self):
        row=self.complete();current=self.store.get(self.project['id'])
        for field,value in [('acknowledged_reviewed_result',1),('acknowledged_protocol_mock','true'),('provider','forged')]:
            request=self.ref(row);request.__dict__[field]=value
            with self.store.transaction() as con:
                with self.assertRaises(WorkflowError):build_context(self.official,current,[request],source_con=con)
        self.assertEqual(len(self.calls),1)
