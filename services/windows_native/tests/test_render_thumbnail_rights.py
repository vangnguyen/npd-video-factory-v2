"""Finite Owner-only exceptions on original PNGs, without a provider or license."""
import copy,json,sqlite3,unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import timedelta
from unittest.mock import patch
from pydantic import ValidationError
from services.windows_native.tests import test_render_thumbnails as fixture
from services.windows_native.render_thumbnail_rights import NativeRenderThumbnailRights,Create
from services.windows_native.render_thumbnails import NativeRenderThumbnails
from services.windows_native.render_vision import NativeRenderVision
from services.windows_native.store import Store
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.backup import create_backup,restore_backup,database_status

class NativeRenderThumbnailRightsTests(unittest.TestCase):
    runtime=fixture.NativeRenderThumbnailTests.runtime
    bridge=fixture.NativeRenderThumbnailTests.bridge
    request=fixture.NativeRenderThumbnailTests.request
    response=fixture.NativeRenderThumbnailTests.response
    payload=fixture.NativeRenderThumbnailTests.payload
    choose=fixture.NativeRenderThumbnailTests.choose
    change_owner=fixture.fixture.NativeRenderVisionTests.change_owner
    @classmethod
    def setUpClass(cls):fixture.NativeRenderThumbnailTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):fixture.NativeRenderThumbnailTests.tearDownClass.__func__(cls)
    def setUp(self):
        fixture.NativeRenderThumbnailTests.setUp(self);self.selected=self.choose()
        self.rights=NativeRenderThumbnailRights(self.thumbnails,enabled=True,identity_provider=lambda:self.verifier,clock=lambda:self.clock[0])
        self.input=self.rights.input(self.project['id'],self.selected['thumbnail_asset_id'])
    def tearDown(self):fixture.NativeRenderThumbnailTests.tearDown(self)
    def review(self,**changes):
        return Create.model_validate({'revision':self.project['revision'],'thumbnail_asset_id':self.selected['thumbnail_asset_id'],
            'expected_thumbnail_snapshot_sha256':self.selected['snapshot_sha256'],'expected_rights_input_sha256':self.input['rights_input_sha256'],
            'action':'grant','reason':'EXPLICIT SYNTHETIC OWNER EXCEPTION — NOT A LICENSE OR OWNER UAT',
            'evidence_reference':'document:explicit-synthetic-thumbnail-rights-fixture','valid_days':7,'allow_publishing_review':True,
            'acknowledged_thumbnail_rights_exception':True,'acknowledged_not_independent_license_verification':True,
            'request_key':'explicit-thumbnail-rights-fixture-key',**changes})
    def grant(self,**changes):return self.rights.record(self.project['id'],self.review(**changes),principal=self.principal)[0]
    def revoke(self,grant,**changes):
        return self.rights.record(self.project['id'],self.review(action='revoke',allow_publishing_review=False,override_id=grant['override_id'],
            expected_override_sha256=grant['snapshot_sha256'],request_key='explicit-thumbnail-revoke-fixture',**changes),principal=self.principal)[0]

    def test_explicit_finite_owner_exception_keeps_image_license_source_timeline_approval_provider_and_cost_exact(self):
        project=self.store.get(self.project['id']);job=self.store.get_job(self.job['id']);cost=self.service.costs.summary(self.project['id'])
        with patch.object(self.vault,'key',side_effect=AssertionError('NO RIGHTS PROVIDER KEY')):grant=self.grant();active=self.rights.active(self.project['id'],self.selected['thumbnail_asset_id'])
        self.assertIsNotNone(active);self.assertEqual(active['override_id'],grant['override_id']);self.assertEqual(active['rights_status'],'unknown');self.assertIsNone(active['license'])
        self.assertFalse(active['rights_independently_verified']);self.assertFalse(active['publishing_authorized']);self.assertFalse(active['source_asset_rights_granted'])
        self.assertFalse(active['final_video_approved']);self.assertFalse(active['owner_uat_accepted']);self.assertTrue(active['original_source_rights_review_still_required'])
        self.assertEqual(self.thumbnails.get(self.project['id'],self.selected['thumbnail_asset_id']),self.selected)
        self.assertEqual(self.store.get(self.project['id']),project);self.assertEqual(self.store.get_job(self.job['id']),job);self.assertEqual(self.service.costs.summary(self.project['id']),cost)
        self.assertEqual(self.calls,[]);self.assertEqual(database_status(self.store.db)['counts']['native_render_thumbnail_rights'],1)

    def test_default_disabled_cannot_grant_and_keyless_readers_preserve_original_review_but_never_reenable(self):
        grant=self.grant();disabled=NativeRenderThumbnailRights(self.thumbnails)
        self.assertFalse(disabled.states()['enabled']);self.assertEqual(disabled.get(self.project['id'],grant['override_id']),grant)
        self.assertIsNone(disabled.active(self.project['id'],self.selected['thumbnail_asset_id']))
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_REQUIRED'):disabled.record(self.project['id'],self.review(request_key='explicit-disabled-new-rights-key'),principal=self.principal)
        off=NativeRenderThumbnailRights(self.thumbnails,identity_provider=lambda:self.verifier,clock=lambda:self.clock[0])
        with self.assertRaisesRegex(WorkflowError,'NOT_ENABLED'):off.record(self.project['id'],self.review(request_key='explicit-off-new-rights-key'),principal=self.principal)
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):
            disabled.enabled=True;disabled.active(self.project['id'],self.selected['thumbnail_asset_id'])

    def test_raw_ack_action_bindings_paid_provider_publish_claims_and_secret_evidence_are_rejected(self):
        body=self.review().model_dump(mode='json')
        for changes in ({'revision':True},{'valid_days':True},{'valid_days':0},{'valid_days':31},{'allow_publishing_review':1},
            {'acknowledged_thumbnail_rights_exception':1},{'acknowledged_not_independent_license_verification':False},{'publishing_authorized':True},
            {'api_key':'PRIVATE'},{'acknowledged_external_image_analysis':True},{'override_id':'nro_'+'a'*32},
            {'evidence_reference':'https://example.invalid/license?api_key=PRIVATE'},{'evidence_reference':'https://example.invalid/license#token=PRIVATE'},
            {'evidence_reference':'https://user:PRIVATE@example.invalid/license'},{'evidence_reference':'https://example.invalid:bad/license'},
            {'evidence_reference':'file:///outside-private'},{'action':'revoke','override_id':'nrto_'+'a'*32,'expected_override_sha256':'a'*64}):
            with self.assertRaises(ValidationError):Create.model_validate({**body,**changes})
        poisoned=self.review();poisoned.__dict__['publishing_authorized']=True
        with self.assertRaisesRegex(WorkflowError,'FIELDS_INVALID'):self.rights.record(self.project['id'],poisoned,principal=self.principal)
        self.assertEqual(self.rights.page(self.project['id'])['items'],[]);self.assertEqual(self.calls,[])

    def test_current_owner_identity_role_expiry_and_registry_rotation_gate_new_and_saved_exceptions(self):
        grant=self.grant()
        for changes in ({'enabled':False},{'workspace_roles':{self.workspace:'editor'}},{'display_name':'ROTATED OWNER IDENTITY'}):
            original=self.verifier;self.change_owner(**changes)
            self.assertIsNone(self.rights.active(self.project['id'],self.selected['thumbnail_asset_id']))
            with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_REQUIRED'):self.rights.record(self.project['id'],self.review(request_key='explicit-current-owner-required-'+digest(changes)[:20]),principal=self.principal)
            self.verifier=original
        self.clock[0]+=timedelta(days=8);self.assertIsNone(self.rights.active(self.project['id'],self.selected['thumbnail_asset_id']))
        self.assertEqual(self.rights.get(self.project['id'],grant['override_id']),grant);self.assertEqual(self.calls,[])

    def test_local_review_only_exception_cannot_be_used_for_publishing_review(self):
        grant=self.grant(allow_publishing_review=False)
        self.assertIsNone(self.rights.active(self.project['id'],self.selected['thumbnail_asset_id']))
        active=self.rights.active(self.project['id'],self.selected['thumbnail_asset_id'],publishing=False)
        self.assertEqual(active['override_id'],grant['override_id']);self.assertFalse(active['allow_publishing_review'])
        with self.assertRaises(WorkflowError):self.rights.active(self.project['id'],self.selected['thumbnail_asset_id'],publishing=1)

    def test_owner_revoked_between_initial_review_and_commit_rolls_back_without_an_exception(self):
        calls=[]
        def current():
            calls.append(True)
            if len(calls)==2:self.change_owner(enabled=False)
            return self.verifier
        self.rights=NativeRenderThumbnailRights(self.thumbnails,enabled=True,identity_provider=current,clock=lambda:self.clock[0])
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_REQUIRED'):self.grant()
        self.assertEqual(len(calls),2);self.assertEqual(self.rights.page(self.project['id'])['items'],[])
        self.assertEqual(self.thumbnails.get(self.project['id'],self.selected['thumbnail_asset_id']),self.selected);self.assertEqual(self.calls,[])

    def test_idempotency_concurrency_and_original_history_do_not_renew_saved_authority(self):
        payload=self.review()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.rights.record(self.project['id'],payload,principal=self.principal),range(2)))
        self.assertEqual(results[0][0],results[1][0]);self.assertEqual(sum(not r[1] for r in results),1);original=results[0][0]
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.grant(reason='EXPLICIT DIFFERENT RIGHT REVIEW')
        self.clock[0]+=timedelta(minutes=1);same,replay=self.rights.record(self.project['id'],payload,principal=self.principal)
        self.assertTrue(replay);self.assertEqual(same,original);self.assertEqual(len(self.rights.page(self.project['id'])['items']),1)

    def test_latest_grant_supersedes_old_and_revocation_never_revives_an_older_exception(self):
        first=self.grant();second=self.grant(request_key='explicit-second-thumbnail-grant',allow_publishing_review=False)
        self.assertIsNone(self.rights.active(self.project['id'],self.selected['thumbnail_asset_id']))
        self.assertEqual(self.rights.active(self.project['id'],self.selected['thumbnail_asset_id'],publishing=False)['override_id'],second['override_id'])
        with self.assertRaisesRegex(WorkflowError,'ORIGINAL_GRANT_REQUIRED'):self.revoke(first)
        revoked=self.revoke(second);self.assertEqual(revoked['snapshot']['previous_record']['override_id'],second['override_id'])
        self.assertIsNone(self.rights.active(self.project['id'],self.selected['thumbnail_asset_id'],publishing=False))
        self.assertEqual(self.rights.get(self.project['id'],first['override_id']),first)
        third=self.grant(request_key='explicit-third-thumbnail-grant');self.assertEqual(self.rights.active(self.project['id'],self.selected['thumbnail_asset_id'])['override_id'],third['override_id'])

    def test_stale_revision_foreign_scope_mismatched_rights_and_thumbnail_sha_cannot_grant(self):
        for changes in ({'revision':self.project['revision']+1},{'expected_thumbnail_snapshot_sha256':'a'*64},{'expected_rights_input_sha256':'a'*64},
            {'thumbnail_asset_id':'ast_rthumb_'+'a'*32}):
            with self.assertRaises(WorkflowError):self.grant(**changes)
        with self.assertRaises(WorkflowError):self.rights.record('a'*32,self.review(),principal=self.principal)
        self.assertEqual(self.rights.page(self.project['id'])['items'],[])

    def test_changed_project_or_missing_png_blocks_active_use_and_new_grant_but_keeps_read_and_revoke(self):
        grant=self.grant();path=self.root/'jobs'/self.job['id']/self.frame['evidence_frame_reference'];path.unlink()
        self.assertEqual(self.rights.get(self.project['id'],grant['override_id']),grant)
        with self.assertRaises(WorkflowError):self.rights.active(self.project['id'],self.selected['thumbnail_asset_id'])
        with self.assertRaises(WorkflowError):self.grant(request_key='explicit-missing-png-new-grant')
        off=NativeRenderThumbnailRights(self.thumbnails,identity_provider=lambda:self.verifier,clock=lambda:self.clock[0]);self.rights=off
        revoked=self.revoke(grant);self.assertEqual(revoked['snapshot']['request']['action'],'revoke');self.assertIsNone(off.active(self.project['id'],self.selected['thumbnail_asset_id']))
        self.assertEqual(off.get(self.project['id'],grant['override_id']),grant)

    def test_project_edit_invalidates_grant_use_without_rewriting_old_review_and_allows_historical_revocation(self):
        grant=self.grant();self.store.save(self.project['id'],self.project['revision'],prompt='EXPLICIT LATER PROJECT EDIT');self.project=self.store.get(self.project['id'])
        with self.assertRaises(WorkflowError):self.rights.active(self.project['id'],self.selected['thumbnail_asset_id'])
        with self.assertRaises(WorkflowError):self.grant(request_key='explicit-after-edit-new-grant')
        self.assertEqual(self.rights.get(self.project['id'],grant['override_id']),grant);self.assertEqual(self.revoke(grant)['snapshot']['request']['action'],'revoke')

    def test_rehashed_authority_private_fields_boolean_sequence_and_changed_original_chains_fail_closed(self):
        first=self.grant();second=self.grant(request_key='explicit-second-integrity-grant');raw=copy.deepcopy(second['snapshot'])
        for mutate in (lambda v:v.update(publishing_authorized=True),lambda v:v.update(paid_operations=False),lambda v:v.update(source_asset_rights_granted=True),
            lambda v:v.update(api_key='PRIVATE'),lambda v:v['previous_record'].update(sequence=True),lambda v:v['rights_input']['image'].update(rights_status='owned')):
            altered=copy.deepcopy(raw);mutate(altered)
            with self.store.transaction() as con:con.execute('UPDATE native_render_thumbnail_rights SET snapshot_json=?,snapshot_sha256=? WHERE override_id=?',(json.dumps(altered),digest(altered),second['override_id']))
            with self.assertRaises(WorkflowError):self.rights.get(self.project['id'],second['override_id'])
        with self.store.transaction() as con:con.execute('UPDATE native_render_thumbnail_rights SET snapshot_json=?,snapshot_sha256=? WHERE override_id=?',(json.dumps(raw),digest(raw),second['override_id']))
        self.assertEqual(self.rights.get(self.project['id'],second['override_id']),second)
        with closing(sqlite3.connect(self.temp.name+'/foreign.sqlite3')) as foreign:
            foreign.execute('CREATE TABLE foreign_scope (id INTEGER)');foreign.execute('INSERT INTO foreign_scope VALUES (1)')
            with self.assertRaises(WorkflowError):self.rights.get(self.project['id'],first['override_id'],con=foreign)

    def test_scoped_bounded_history_and_public_backup_keyless_original_exception_recovery(self):
        first=self.grant();second=self.grant(request_key='explicit-second-recovery-grant');revoked=self.revoke(second);page=self.rights.page(self.project['id'],limit=1)
        self.assertEqual(page['items'][0],revoked);self.assertEqual(self.rights.page(self.project['id'],limit=1,cursor=page['next_cursor'])['items'][0],second)
        for kwargs in ({'limit':0},{'limit':101},{'limit':True},{'cursor':'bad'}):
            with self.assertRaises(WorkflowError):self.rights.page(self.project['id'],**kwargs)
        with self.assertRaises(WorkflowError):self.rights.page('a'*32,cursor=page['next_cursor'])
        archive=self.temp.name+'/rights.zip';receipt=create_backup(self.config,archive);restored=self.root.parent/'restored'
        restore_backup(archive,restored,expected_sha256=receipt['sha256']);store=Store(restored)
        from dataclasses import replace
        config=replace(self.config,data_root=restored);vision=NativeRenderVision(store,config);thumbnails=NativeRenderThumbnails(store,config,render_vision=vision);reader=NativeRenderThumbnailRights(thumbnails)
        for row in (first,second,revoked):self.assertEqual(reader.get(self.project['id'],row['override_id']),row)
        self.assertIsNone(reader.active(self.project['id'],self.selected['thumbnail_asset_id']));self.assertEqual(thumbnails.get(self.project['id'],self.selected['thumbnail_asset_id']),self.selected)
        self.assertEqual(database_status(store.db)['counts']['native_render_thumbnail_rights'],3);self.assertEqual(self.calls,[])
