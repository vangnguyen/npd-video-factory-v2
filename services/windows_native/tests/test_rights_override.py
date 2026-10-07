"""Explicit synthetic human exceptions: no real Owner clearance, provider or post."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from services.windows_native.tests import test_rights as fixture
from services.windows_native.rights_override import NativeRightsOverrides,rights_sha,validate_publication_rights
from services.windows_native.source_assets import canonical_assets
from services.windows_native.source_broll import shared_assets
from app.publishing_logic import validate_rights
from services.windows_native.contracts import WorkflowError,digest,file_sha


class NativeRightsOverrideTests(unittest.TestCase):
    # Reuse only setup helpers, not the declaration suite under a second name.
    setUp_parent=fixture.NativeRightsTests.setUp
    tearDown=fixture.NativeRightsTests.tearDown
    declare=fixture.NativeRightsTests.declare
    def setUp(self):
        self.setUp_parent();self.clock=[datetime.now(timezone.utc)]
        self.overrides=NativeRightsOverrides(self.store,workspace_id=self.service.workspace,enabled=True,clock=lambda:self.clock[0])
        self.request={'revision':self.project['revision'],'asset_sha256':self.asset['sha256'],'expected_rights_sha256':rights_sha(self.asset),
            'action':'grant','reason':'EXPLICIT SYNTHETIC OWNER EXCEPTION TEST, NOT LEGAL CLEARANCE',
            'evidence_reference':'document://explicit-synthetic-fixture','valid_days':7,'allow_publishing_review':True,'acknowledged':True,
            'request_key':'native-owner-override-explicit-fixture'}

    def grant(self,**changes):return self.overrides.record(self.project['id'],self.asset['id'],{**self.request,**changes},actor='explicit-owner-fixture')
    def active(self,publishing=False):
        doc=self.store.get(self.project['id'])['document'];return self.overrides.active(doc,self.project['id'],canonical_assets(doc)[0],publishing=publishing)
    def validation(self):
        doc=self.store.get(self.project['id'])['document'];assets=canonical_assets(doc)
        return validate_publication_rights(self.store,doc,self.project['id'],assets,{self.asset['id']},
            validate_rights([SimpleNamespace(asset_id=a['id'],provenance=a) for a in assets]))

    def test_exception_preserves_actual_unknown_provenance_separate_from_rights_and_approval(self):
        before=self.store.get(self.project['id']);physical=file_sha(self.root/'assets'/self.asset['id']);receipt=self.grant()
        current=self.store.get(self.project['id']);self.assertEqual(canonical_assets(current['document'])[0],self.asset)
        self.assertIsNone(current['approval']);self.assertEqual(current['revision'],before['revision']+1)
        self.assertEqual(file_sha(self.root/'assets'/self.asset['id']),physical);self.assertFalse(receipt['record']['publishing_authorized'])
        self.assertFalse(receipt['record']['rights_independently_verified']);self.assertIsNotNone(self.active(publishing=True))
        result=self.validation();self.assertEqual(result.status,'passed');self.assertEqual(result.checks[0].code,'RIGHTS_EXPLICIT_OWNER_EXCEPTION')
        self.assertEqual(result.checks[0].evidence['rights_status'],'unknown');self.assertFalse(result.checks[0].evidence['rights_independently_verified'])
        value=next(iter(shared_assets(current,self.config,rights_overrides=self.overrides).values()))
        self.assertEqual(value.provenance['rights_status'],'unknown');self.assertIsNotNone(value.provenance['owner_rights_override'])

    def test_expiry_disabled_restart_and_local_only_never_allow_publishing_review(self):
        self.grant(allow_publishing_review=False);self.assertIsNotNone(self.active());self.assertIsNone(self.active(publishing=True));self.assertEqual(self.validation().status,'failed')
        self.clock[0]+=timedelta(days=7);self.assertIsNone(self.active());self.assertEqual(self.validation().status,'failed')
        self.clock[0]-=timedelta(days=7)
        self.overrides.enabled=False;self.assertIsNone(self.active());self.assertEqual(self.validation().status,'failed')
        with self.assertRaises(WorkflowError):self.grant(request_key='different-disabled-fixture-key',revision=self.store.get(self.project['id'])['revision'])
        restarted=NativeRightsOverrides(self.store,workspace_id=self.service.workspace);self.assertFalse(restarted.page(self.project['id'])['enabled'])

    def test_revoke_after_disable_frozen_replay_and_changed_request_conflict(self):
        receipt=self.grant();self.overrides.enabled=False;current=self.store.get(self.project['id'])
        revoke=self.grant(action='revoke',revision=current['revision'],allow_publishing_review=False,override_id=receipt['record']['override_id'],
            expected_override_sha256=receipt['record']['sha256'],request_key='native-owner-revoke-fixture-key')
        self.overrides.enabled=True;self.assertIsNone(self.active());self.assertEqual(self.validation().status,'failed')
        replay=self.grant();self.assertTrue(replay['idempotent_replay']);self.assertEqual(replay['record'],receipt['record'])
        with self.assertRaises(WorkflowError):self.grant(reason='Explicit changed synthetic reason')
        self.assertEqual(revoke['record']['request']['action'],'revoke')

    def test_rights_declaration_change_invalidates_active_exception_without_rewriting_history(self):
        receipt=self.grant();self.declare(revision=self.store.get(self.project['id'])['revision'],claimed_rights='restricted')
        self.assertIsNone(self.active());self.assertEqual(self.validation().status,'failed')
        self.assertEqual(self.overrides.page(self.project['id'])['history'][0],receipt['record'])
        with self.assertRaises(WorkflowError):self.grant(revision=self.store.get(self.project['id'])['revision'],request_key='native-new-restricted-fixture-key')

    def test_bad_hash_cas_ack_secret_reference_extra_fields_and_fixture_promotion_fail_atomic(self):
        before=self.store.get(self.project['id'])
        for change in [{'revision':1},{'asset_sha256':'0'*64},{'expected_rights_sha256':'0'*64},{'acknowledged':False},{'acknowledged':1},
            {'valid_days':0},{'valid_days':31},{'valid_days':True},{'allow_publishing_review':1},
            {'evidence_reference':'https://u:p@example.com/secret'},{'evidence_reference':'https://example.com/?api_key=secret'},
            {'evidence_reference':'javascript:fixture'},{'verified':True},{'production_eligible':True}]:
            with self.assertRaises(WorkflowError):self.grant(**change)
        self.assertEqual(self.store.get(self.project['id']),before)
        doc=deepcopy(before['document']);doc['assets'][0]['generation_provenance']={'fixture':True}
        with self.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(doc),self.project['id']))
        with self.assertRaises(WorkflowError):self.grant(expected_rights_sha256=rights_sha(doc['assets'][0]))
        self.assertEqual(self.store.get(self.project['id'])['document'],doc)

    def test_event_failure_rolls_back_history_receipt_and_approval(self):
        before=self.store.get(self.project['id']);versions=self.store.versions(self.project['id'])
        with patch.object(self.store,'event',side_effect=RuntimeError('EXPLICIT JOURNAL FAILURE FIXTURE')):
            with self.assertRaises(RuntimeError):self.grant()
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(self.store.versions(self.project['id']),versions)
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_rights_override_requests').fetchone()[0],0)

    def test_approved_dry_run_cannot_dispatch_after_exception_expiry(self):
        from services.windows_native.tests.test_publications import render_fixture,CAPABILITIES
        from services.windows_native.publications import NativePublications
        from services.windows_native.publication_models import NativePublicationCreate,NativePublishApproval
        self.grant();current=self.store.get(self.project['id'])
        project,job=render_fixture(self.store,asset=self.asset,project=current)
        service=NativePublications(self.store,CAPABILITIES,workspace_id=self.service.workspace,clock=lambda:self.clock[0])
        request=NativePublicationCreate(revision=project['revision'],final_job_id=job['id'],platform='youtube',
            metadata={'title':'EXPLICIT NONPLAYABLE OVERRIDE EXPIRY FIXTURE','privacy':'private'},request_key='native-override-expiry-publication-fixture')
        value,_=service.create(project['id'],request,actor='explicit-editor-fixture');self.assertEqual(value['status'],'awaiting_publish_approval')
        service.approve(project['id'],value['publication_id'],NativePublishApproval(expected_fingerprint=value['request_fingerprint'],
            expected_artifact_sha256=value['snapshot']['final_sha256'],acknowledged=True),actor='explicit-owner-fixture')
        self.clock[0]+=timedelta(days=7)
        with patch.object(service.provider,'publish',side_effect=AssertionError('Expired exception cannot dispatch even a mock post')) as publish:
            result=service.process();publish.assert_not_called();self.assertEqual(result['status'],'blocked');self.assertIsNone(result['receipt'])
        self.assertEqual(result['failure_code'],'NATIVE_PUBLICATION_VALIDATION_FAILED');self.assertEqual(self.store.get_job(job['id'])['snapshot'],job['snapshot'])

    def test_narrated_duplicate_drops_exception_and_physical_corruption_rejects_grant(self):
        from services.windows_native.tests.test_workflow import proposal
        self.project=self.store.save(self.project['id'],self.project['revision'],proposal=proposal(),asset=self.asset)
        self.request['revision']=self.project['revision'];self.grant();current=self.store.get(self.project['id'])
        copied=self.store.duplicate(self.project['id'],current['revision']);self.assertNotIn('media_rights_overrides',copied['document'])
        self.assertEqual(canonical_assets(copied['document'])[0]['rights_status'],'unknown');self.assertIsNotNone(self.active())
        physical=self.root/'assets'/self.asset['id'];original=physical.read_bytes();physical.write_bytes(original+b'EXPLICIT CORRUPTION FIXTURE')
        with self.assertRaises(WorkflowError):self.grant(revision=current['revision'],request_key='native-corrupted-physical-fixture-key')
        self.assertEqual(self.store.get(self.project['id']),current);physical.write_bytes(original)

    def test_foreign_rehashed_semantic_history_and_forged_receipt_fail_closed(self):
        self.grant();saved=self.store.get(self.project['id'])['document']
        for mutation in [lambda r:r.update(project_id='a'*32),lambda r:r.update(expires_at=(self.clock[0]+timedelta(days=50)).isoformat()),
            lambda r:r.update(rights_independently_verified=True),lambda r:r['request'].update(override_id='nro_'+'b'*32)]:
            doc=deepcopy(saved);row=doc['media_rights_overrides'][0];mutation(row);row['sha256']=digest({k:v for k,v in row.items() if k!='sha256'})
            with self.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(doc),self.project['id']))
            with self.assertRaises(WorkflowError):self.overrides.page(self.project['id'])
        with self.store.transaction() as con:
            con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(saved),self.project['id']))
            row=con.execute('SELECT * FROM native_rights_override_requests').fetchone();result=json.loads(row['result_json']);result['record']['actor_ref']='forged fixture'
            result['record']['sha256']=digest({k:v for k,v in result['record'].items() if k!='sha256'})
            con.execute('UPDATE native_rights_override_requests SET result_json=?,result_sha256=?',(json.dumps(result),digest(result)))
        with self.assertRaises(WorkflowError):self.grant()
