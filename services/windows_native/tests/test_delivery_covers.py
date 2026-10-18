"""Actual bounded images and local covers. No generated-provider or Owner claim."""
import io
import json
import unittest
from pathlib import Path
from PIL import Image
from pydantic import ValidationError
from services.windows_native.tests import test_manual_delivery as fixture
from services.windows_native.delivery_covers import CoverOptions,checked_image,MAX_BYTES
from services.windows_native.manual_delivery import DeliveryCreate
from services.windows_native.contracts import WorkflowError,digest,file_sha


class DeliveryCoverTests(unittest.TestCase):
    setUpClass=classmethod(fixture.ManualDeliveryTests.setUpClass.__func__)
    tearDownClass=classmethod(fixture.ManualDeliveryTests.tearDownClass.__func__)
    setUp=fixture.ManualDeliveryTests.setUp
    tearDown=fixture.ManualDeliveryTests.tearDown
    request=fixture.ManualDeliveryTests.request
    create=fixture.ManualDeliveryTests.create

    def pixels(self):
        image=Image.new('RGB',(1000,600),'#165e9e');image.paste('#d02c2c',(0,0,500,600));out=io.BytesIO();image.save(out,format='PNG');return out.getvalue()

    def upload(self):return self.service.covers.upload(self.project['id'],self.project['revision'],self.pixels(),'tên ảnh bìa.png','image/png')

    def test_upload_magic_hash_dedupe_and_approval_are_unchanged(self):
        original=self.store.get(self.project['id']);one=self.upload();two=self.upload()
        self.assertFalse(one['idempotent_replay']);self.assertTrue(two['idempotent_replay']);self.assertEqual(one['cover_id'],two['cover_id'])
        self.assertEqual(one['rights_status'],'unknown');self.assertEqual(self.store.get(self.project['id']),original)
        path,row=self.service.covers.read(self.project['id'],one['cover_id']);self.assertEqual(file_sha(path),one['checksum_sha256'])
        self.assertEqual(row['content_type'],'image/png')
        with self.assertRaisesRegex(WorkflowError,'NOT_FOUND'):self.service.covers.read('0'*32,one['cover_id'])

    def test_invalid_magic_mime_and_size_cannot_register_a_cover(self):
        for raw,mime in [(b'<svg>bad</svg>','image/png'),(self.pixels(),'image/jpeg'),(b'0'*(MAX_BYTES+1),'image/png')]:
            with self.subTest(mime=mime),self.assertRaises(WorkflowError):checked_image(raw,mime)
        # Actual bytes, rather than a misleading extension, determine MIME.
        value=self.service.covers.upload(self.project['id'],self.project['revision'],self.pixels(),'name.mp4','image/png')
        self.assertEqual(value['content_type'],'image/png')

    def test_uploaded_cover_crop_png_title_and_provenance_are_in_package(self):
        original=self.store.get(self.project['id']);upload=self.upload()
        done=self.create(cover_settings=CoverOptions(source='uploaded_cover',source_id=upload['cover_id'],format='png',center_x=1.,center_y=.5,title='Vang Nguyễn · Cần Giờ'))
        directory=Path(done['output_location']);manifest=done['manifest'];self.assertIn('cover.png',manifest['files'])
        with Image.open(directory/'cover.png') as image:
            self.assertEqual(image.size,(1080,1920));self.assertEqual(image.getpixel((100,100)),(22,94,158))
        provenance=json.loads((directory/'cover-provenance.json').read_bytes())
        self.assertEqual(provenance['source_sha256'],upload['checksum_sha256']);self.assertEqual(provenance['rights_status'],'unknown')
        self.assertEqual(provenance['title'],'Vang Nguyễn · Cần Giờ');self.assertEqual(provenance['output_sha256'],file_sha(directory/'cover.png'))
        self.assertGreater(provenance['crop_pixels'][0],500);self.assertEqual(self.store.get(self.project['id']),original)

    def test_existing_project_image_and_original_render_candidate_reuse_no_provider(self):
        from services.windows_native.render_thumbnails import NativeRenderThumbnails,Create
        from services.windows_native.render_vision_frame_bridge import NativeRenderEvidenceFrameExtractor
        thumbnails=NativeRenderThumbnails(self.store,self.config)
        binding=NativeRenderEvidenceFrameExtractor(self.store,self.config,self.project['id'],self.job_id).binding()
        frame=next(f for f in binding['record']['observation']['frames'] if not f['pixel_facts']['black_sample'])
        selected,_=thumbnails.create(self.project['id'],Create(revision=self.project['revision'],render_job_id=self.job_id,
            expected_render_input_sha256=digest(binding),frame_id=frame['frame_id'],expected_frame_sha256=frame['sha256'],
            acknowledged_thumbnail=True,request_key='explicit-manual-cover-candidate-key'),actor='SYNTHETIC COVER SELECTION, NOT OWNER UAT')
        done=self.create(cover_settings=CoverOptions(source='render_thumbnail',source_id=selected['thumbnail_asset_id']))
        source=json.loads((Path(done['output_location'])/'cover-provenance.json').read_bytes())
        self.assertEqual(source['source_sha256'],frame['sha256']);self.assertEqual(source['source_type'],'render_thumbnail')
        assets=self.service.covers.page(self.project['id']);self.assertEqual(len(assets['candidates']),1)

    def test_geometry_variants_use_crop_before_resizing(self):
        upload=self.upload()
        for width,height in [(1080,1920),(1920,1080),(1080,1080),(1080,1350)]:
            stage=self.root/f'cover-{width}-{height}';stage.mkdir()
            name=self.service.covers.export(self.project['id'],self.job,CoverOptions(source='uploaded_cover',source_id=upload['cover_id'],center_x=1.),
                self.root/'jobs'/self.job_id/'final.mp4',stage,width=width,height=height,timestamp=0)
            with Image.open(stage/name) as image:self.assertEqual(image.size,(width,height))
            crop=json.loads((stage/'cover-provenance.json').read_bytes())['crop_pixels']
            self.assertLess(abs((crop[2]-crop[0])/(crop[3]-crop[1])-width/height),.005)

    def test_unconfigured_logo_and_invalid_crop_cannot_claim_success(self):
        for changes in [{'zoom':0},{'center_x':True},{'source':'uploaded_cover'},{'source_id':'unwanted-id'}]:
            with self.subTest(changes=changes),self.assertRaises(ValidationError):CoverOptions.model_validate(changes)
        with self.assertRaisesRegex(WorkflowError,'LOGO_NOT_CONFIGURED'):self.create(cover_settings=CoverOptions(logo=True))

    def test_old_v1_request_fingerprint_survives_optional_cover_settings(self):
        payload=self.request(cover=False);old=payload.model_dump(mode='json');old.pop('cover_settings')
        self.assertEqual(digest(old),digest(DeliveryCreate.model_validate(old).model_dump(mode='json',exclude_none=True)))
