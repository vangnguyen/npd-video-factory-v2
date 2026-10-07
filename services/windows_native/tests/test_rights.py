"""Physical owned fixture assertions remain unverified; no legal override or provider."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from services.windows_native.contracts import WorkflowError,file_sha,digest
from services.windows_native.media import ingest_media
from services.windows_native.pipeline import Config
from services.windows_native.rights import NativeRights
from services.windows_native.store import Store
from services.windows_native.tests.test_workflow import proposal
from services.windows_native.source_assets import canonical_assets
from app.publishing_logic import validate_rights
from types import SimpleNamespace


class NativeRightsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'state';self.config=Config(data_root=self.root)
        self.store=Store(self.root);self.service=NativeRights(self.store,workspace_id='wsp_native_rights_fixture')
        source=Path(self.temp.name)/'explicit-generated-source.png';Image.new('RGB',(320,240),(44,90,130)).save(source)
        self.asset=ingest_media(self.config,source,'image/png','EXPLICIT SYNTHETIC RIGHTS FIXTURE',rights_confirmed=True,illustration=False)
        self.project=self.store.create('Owned fixture','Private fixture input');self.project=self.store.append_media(self.project['id'],self.project['revision'],self.asset)
        self.body={'revision':self.project['revision'],'asset_sha256':self.asset['sha256'],'claimed_source_type':'user_upload',
            'claimed_rights':'owned','license':'EXPLICIT DECLARATION FIXTURE, NOT VERIFIED','provider':'owner-fixture',
            'source_reference':'upload://explicit-fixture','acknowledged':True,'request_key':'native-rights-fixture-declaration-key'}

    def tearDown(self):self.temp.cleanup()

    def declare(self,**changes):return self.service.declare(self.project['id'],self.asset['id'],{**self.body,**changes},actor='explicit-owner-fixture')

    def test_ingest_default_metadata_and_owner_claim_never_verifies_or_publishes(self):
        self.assertEqual(self.asset['rights_status'],'unknown');self.assertEqual(self.asset['source_type'],'user_upload');self.assertIsNone(self.asset['license'])
        old=deepcopy(self.project);sha=file_sha(self.root/'assets'/self.asset['id']);receipt=self.declare()
        current=self.store.get(self.project['id']);row=self.service.page(self.project['id'])['items'][0]
        self.assertEqual(current['revision'],old['revision']+1);self.assertFalse(receipt['declaration']['verified']);self.assertIsNone(current['approval'])
        self.assertEqual(row['rights_status'],'unknown');self.assertEqual(row['provider'],'native-local-upload');self.assertIsNone(row['license'])
        self.assertEqual(row['declaration']['request']['provider'],'owner-fixture');self.assertFalse(row['declaration']['owner_override_recorded'])
        self.assertEqual(file_sha(self.root/'assets'/self.asset['id']),sha);self.assertEqual(self.store.versions(self.project['id'])[1]['document'],old['document'])
        result=validate_rights([SimpleNamespace(asset_id=self.asset['id'],provenance=row)]);self.assertEqual(result.status,'failed')

    def test_replay_frozen_receipt_after_later_revision_and_changed_body_conflict(self):
        first=self.declare();current=self.store.get(self.project['id'])
        second=self.declare(revision=current['revision'],claimed_rights='restricted',request_key='native-rights-restricted-second-key')
        replay=self.declare();self.assertTrue(replay['idempotent_replay']);self.assertEqual(replay['declaration'],first['declaration'])
        self.assertEqual(self.service.page(self.project['id'])['items'][0]['rights_status'],'restricted')
        with self.assertRaises(WorkflowError):self.declare(license='Changed fixture')
        fresh=NativeRights(Store(self.root),workspace_id='wsp_native_rights_fixture');self.assertEqual(fresh.page(self.project['id']),self.service.page(self.project['id']))

    def test_cas_ack_physical_hash_license_secret_url_and_extra_override_reject_without_mutation(self):
        before=self.store.get(self.project['id'])
        for changes in [{'revision':1},{'asset_sha256':'0'*64},{'acknowledged':False},{'acknowledged':1},
            {'claimed_rights':'licensed','license':None},{'source_reference':'https://u:p@example.com/proof'},
            {'source_reference':'https://example.com/proof?api_key=PRIVATE'},{'source_reference':'javascript:alert(1)'},
            {'owner_override':True},{'verified':True},{'rights_status':'owned'}]:
            with self.assertRaises(WorkflowError):self.declare(**changes)
        self.assertEqual(self.store.get(self.project['id']),before)
        path=self.root/'assets'/self.asset['id'];original=path.read_bytes();path.write_bytes(original+b'fixture-corruption')
        with self.assertRaises(WorkflowError):self.declare()
        self.assertEqual(self.store.get(self.project['id']),before);path.write_bytes(original)

    def test_receipt_event_failure_rolls_back_document_approval_history_and_request(self):
        before=self.store.get(self.project['id']);versions=self.store.versions(self.project['id'])
        with patch.object(self.store,'event',side_effect=RuntimeError('Explicit fixture journal failure')):
            with self.assertRaises(RuntimeError):self.declare()
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(self.store.versions(self.project['id']),versions)
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_rights_requests').fetchone()[0],0)

    def test_narrated_duplicate_keeps_physical_restriction_and_drops_project_receipt_scope(self):
        self.project=self.store.save(self.project['id'],self.project['revision'],proposal=proposal(),asset=self.asset)
        self.body['revision']=self.project['revision'];self.declare(claimed_rights='restricted')
        before=self.store.get(self.project['id']);copied=self.store.duplicate(self.project['id'],before['revision'])
        self.assertNotIn('media_rights_declarations',copied['document']);self.assertEqual(canonical_assets(copied['document'])[0]['rights_status'],'restricted')
        self.assertNotIn('rights_declaration_ref',canonical_assets(copied['document'])[0]);self.assertEqual(self.store.get(self.project['id']),before)
        self.assertEqual(self.service.page(copied['id'])['declaration_count'],0)

    def test_record_digest_and_rehashed_semantic_status_corruption_fail_read(self):
        self.declare()
        with self.store.transaction() as con:
            doc=json.loads(con.execute('SELECT document FROM projects WHERE id=?',(self.project['id'],)).fetchone()[0])
            record=doc['media_rights_declarations'][0];record['effective_rights_status']='restricted';record['sha256']=digest({k:v for k,v in record.items() if k!='sha256'})
            con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(doc),self.project['id']))
        with self.assertRaises(WorkflowError):self.store.get(self.project['id'])

    def test_rehashed_receipt_must_match_immutable_version_and_record_scope(self):
        self.declare()
        with self.store.transaction() as con:
            row=con.execute('SELECT * FROM native_rights_requests').fetchone();value=json.loads(row['result_json'])
            value['declaration']['actor_ref']='Forged actor fixture';value['declaration']['sha256']=digest({k:v for k,v in value['declaration'].items() if k!='sha256'})
            con.execute('UPDATE native_rights_requests SET result_json=?,result_sha256=?',(json.dumps(value),digest(value)))
        with self.assertRaises(WorkflowError):self.declare()

    def test_missing_record_binding_foreign_scope_and_non_object_history_fail_safe(self):
        self.declare();saved=self.store.get(self.project['id'])['document']
        for mutate in [lambda doc:doc.update(media_rights_declarations=[None]),
            lambda doc:doc['media_rights_declarations'][0].update(project_id='a'*32),
            lambda doc:doc['assets'][0].update(rights_status='owned'),
            lambda doc:doc['assets'][0].pop('rights_declaration_ref')]:
            doc=deepcopy(saved);mutate(doc)
            with self.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(doc),self.project['id']))
            with self.assertRaises(WorkflowError):self.service.page(self.project['id'])
        with self.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(saved),self.project['id']))
        foreign=NativeRights(Store(self.root),workspace_id='wsp_native_other_fixture')
        with self.assertRaises(WorkflowError):foreign.page(self.project['id'])


if __name__=='__main__':unittest.main()
