"""Current rights restriction fences historical pre-approved dry-run dispatch."""
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from PIL import Image
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.pipeline import Config
from services.windows_native.media import ingest_media
from services.windows_native.store import Store
from services.windows_native.rights import NativeRights
from services.windows_native.publication_models import NativePublicationCreate,NativePublishApproval
from services.windows_native.publications import NativePublications
from services.windows_native.tests.test_publications import render_fixture,CAPABILITIES


class NativeRightsPublicationTests(unittest.TestCase):
    def test_current_unverified_claim_blocks_new_approval_and_preapproved_historical_render_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'state';store=Store(root);settings=Config(data_root=root)
            source=Path(directory)/'explicit-synthetic-source.png';Image.new('RGB',(320,240),(40,60,80)).save(source)
            asset=ingest_media(settings,source,'image/png','EXPLICIT GENERATED RIGHTS FIXTURE',rights_confirmed=True,illustration=False)
            # Synthetic test pixels have known ownership. This is confined to
            # the fresh test root, never a user assertion verification path.
            asset.update(source_type='generated_fixture',rights_status='owned',license='EXPLICIT TEST PIXELS, NO PROVIDER',provider='local-test-fixture')
            project,job=render_fixture(store,asset=asset);service=NativePublications(store,CAPABILITIES);rights=NativeRights(store,workspace_id=service.workspace_id)
            payload=NativePublicationCreate(revision=job['revision'],final_job_id=job['id'],platform='youtube',
                metadata={'title':'EXPLICIT OWNED DRY-RUN FIXTURE','privacy':'private'},request_key='native-rights-publication-fixture-key')
            value,_=service.create(project['id'],payload,actor='fixture-editor');review=NativePublishApproval(expected_fingerprint=value['request_fingerprint'],
                expected_artifact_sha256=value['snapshot']['final_sha256'],acknowledged=True);service.approve(project['id'],value['publication_id'],review,actor='fixture-owner')
            frozen=store.get_job(job['id']);media_sha=file_sha(root/'assets'/asset['id'])
            rights.declare(project['id'],asset['id'],{'revision':project['revision'],'asset_sha256':asset['sha256'],
                'claimed_source_type':'user_upload','claimed_rights':'restricted','acknowledged':True,'request_key':'native-rights-publication-restrict-key'},actor='fixture-owner')
            self.assertIsNone(store.get(project['id'])['approval']);self.assertEqual(store.get_job(job['id']),frozen)
            self.assertEqual(file_sha(root/'assets'/asset['id']),media_sha)
            with self.assertRaises(WorkflowError):service.approve(project['id'],value['publication_id'],review,actor='fixture-owner')
            with patch.object(service.provider,'publish',side_effect=AssertionError('Restricted media must not reach even fixture publish')) as publish:
                blocked=service.process();self.assertEqual(blocked['status'],'blocked');publish.assert_not_called()
            with self.assertRaises(WorkflowError):
                service.create(project['id'],payload.model_copy(update={'request_key':'native-rights-publication-new-key'}),actor='fixture-editor')


if __name__=='__main__':unittest.main()
