"""Cache is a measured computation reuse, never a physical or authority bypass."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from services.windows_native import render_frame_qc as qc
from services.windows_native.render_frame_evidence_cache import RenderFrameEvidenceCache
from services.windows_native.contracts import WorkflowError,file_sha


class RenderFrameEvidenceCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.directory=self.root/'one';self.directory.mkdir()
        self.path=self.directory/'0.png';Image.new('RGB',(16,9),'orange').save(self.path);self.cache=RenderFrameEvidenceCache(self.directory,'wsp_explicit_cache_fixture')
    def tearDown(self):self.temp.cleanup()
    def test_byte_exact_hit_reuses_actual_decoded_metrics_without_retaining_pixels_or_mutable_results(self):
        with patch.object(qc,'image_evidence',wraps=qc.image_evidence) as measure:
            first=self.cache.measure(self.path);first['width']=0
            second=self.cache.measure(self.path);self.assertEqual(measure.call_count,1);self.assertEqual(second,qc.image_evidence(self.path))
        self.assertEqual(len(self.cache._entries),1);self.assertEqual(second['sha256'],file_sha(self.path))
    def test_changed_physical_bytes_measure_again_including_corruption_rejection(self):
        first=self.cache.measure(self.path);Image.new('RGB',(16,9),'blue').save(self.path)
        second=self.cache.measure(self.path);self.assertNotEqual(first['sha256'],second['sha256']);self.assertEqual(second,qc.image_evidence(self.path))
        self.path.write_bytes(b'EXPLICIT INVALID PNG')
        with self.assertRaises(WorkflowError):self.cache.measure(self.path)
    def test_content_change_during_decode_is_rejected_before_inserting_a_cache_entry(self):
        original=qc.image_evidence
        def changed(path):
            value=original(path);Image.new('RGB',(16,9),'blue').save(path);return value
        with patch.object(qc,'image_evidence',side_effect=changed):
            with self.assertRaisesRegex(WorkflowError,'CACHE_INPUT_CHANGED'):self.cache.measure(self.path)
        self.assertEqual(len(self.cache._entries),0)
    def test_foreign_directory_scope_workspace_mutation_or_untyped_physical_cache_reject(self):
        outside=self.root/'other.png';Image.new('RGB',(16,9),'orange').save(outside)
        with self.assertRaises(WorkflowError):self.cache.measure(outside)
        with self.assertRaises(WorkflowError):self.cache.check(self.root)
        self.cache.workspace='wsp_foreign'
        with self.assertRaises(WorkflowError):self.cache.measure(self.path)
        with self.assertRaises(WorkflowError):qc.validate(self.directory,{},frame_cache={})
        with self.assertRaises(WorkflowError):qc.validate(self.directory,{},physical=False,frame_cache=RenderFrameEvidenceCache(self.directory,'wsp_fixture'))
    def test_bound_is_eight_small_measurements_and_an_evicted_file_is_remeasured(self):
        with patch.object(qc,'image_evidence',wraps=qc.image_evidence) as measure:
            for index in range(9):
                path=self.directory/f'{index}.png';Image.new('RGB',(16,9),(index*10,100,90)).save(path);self.cache.measure(path)
            self.assertEqual(len(self.cache._entries),8);self.cache.measure(self.path);self.assertEqual(measure.call_count,10)
        self.assertTrue(all(type(result) is dict for _,result in self.cache._entries.values()))
    def test_two_readers_do_not_share_measurements_even_for_identical_bytes(self):
        other=RenderFrameEvidenceCache(self.directory,'wsp_explicit_cache_fixture')
        with patch.object(qc,'image_evidence',wraps=qc.image_evidence) as measure:
            self.cache.measure(self.path);other.measure(self.path);self.assertEqual(measure.call_count,2)


if __name__=='__main__':unittest.main()
