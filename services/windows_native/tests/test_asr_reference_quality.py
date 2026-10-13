"""Reference metrics preserve Vietnamese text, sample scope and old model identities."""
import io,unittest
from app.asr_reference_quality import normalize_text,assessment,aggregate
from app.local_asr_profile import profile,digest,validate_profile
from services.windows_native.asr_request import bind
from scripts.prepare_local_asr_vi_benchmark import LimitedStream

class ASRReferenceQualityTests(unittest.TestCase):
    def test_canonically_equal_unicode_case_and_punctuation_have_zero_error(self):
        value=assessment('Xin chào, Cần Giờ!','XIN CHA\u0300O CÂ\u0300N GIƠ\u0300')
        self.assertEqual(value['token_edit_distance'],0);self.assertEqual(value['character_edit_distance'],0)
        self.assertFalse(value['timestamps_evaluated']);self.assertFalse(value['approval_granted'])
    def test_diacritics_are_preserved_and_missing_content_is_counted(self):
        self.assertNotEqual(normalize_text('Cần Giờ'),normalize_text('Can Gio'))
        value=assessment('xin chào Việt Nam','xin chào')
        self.assertEqual(value['reference_tokens'],4);self.assertEqual(value['token_edit_distance'],2)
        self.assertEqual(value['whitespace_token_error_rate'],.5)
    def test_insertions_substitutions_and_complete_omission_are_counted(self):
        self.assertEqual(assessment('xin chào','xin chào bạn')['token_edit_distance'],1)
        self.assertEqual(assessment('xin chào','chào bạn')['token_edit_distance'],2)
        self.assertEqual(assessment('xin chào','')['whitespace_token_error_rate'],1)
    def test_weighted_aggregate_is_not_an_unweighted_mean_or_acceptance(self):
        value=aggregate([assessment('a','x'),assessment('a b c','a b c')])
        self.assertEqual(value['reference_tokens'],4);self.assertEqual(value['whitespace_token_error_rate'],.25)
        self.assertTrue(value['sample_scope_only']);self.assertFalse(value['full_ASR_quality_accepted'])
    def test_empty_oversize_reference_and_mixed_normalizers_are_rejected(self):
        with self.assertRaises(ValueError):assessment('','not a reference')
        with self.assertRaises(ValueError):normalize_text('a'*131073)
        with self.assertRaises(ValueError):aggregate([])
        with self.assertRaises(ValueError):aggregate([{'normalizer':'different'}])
    def test_benchmark_reader_stops_before_stream_budget_and_requires_bounded_reads(self):
        stream=LimitedStream(io.BytesIO(b'123456789'),5)
        self.assertEqual(stream.read(4),b'1234');self.assertEqual(stream.bytes_read,4)
        with self.assertRaisesRegex(ValueError,'LIMIT'):stream.read(2)
        with self.assertRaisesRegex(ValueError,'BOUNDED'):stream.read()
        self.assertEqual(stream.bytes_read,4)
    def test_explicit_models_have_separate_profiles_and_legacy_requests_stay_exact(self):
        old=bind({'language':'vi','provider':'local-whisper'})
        base=bind({'language':'vi','provider':'local-whisper','model_key':'base'})
        small=bind({'language':'vi','provider':'local-whisper','model_key':'small'})
        self.assertEqual(base,old);self.assertNotEqual(base['profile_sha256'],small['profile_sha256'])
        self.assertEqual(old['profile_sha256'],'8f69904db4efb6b96b1bd355f7ac1de1c19cde746091bb6ed0421b9a4a773e64')
        self.assertEqual(small['profile']['model'],'Systran/faster-whisper-small')
        self.assertEqual(small['profile']['version'],'local-asr-cpu.v2')
        self.assertIsNone(small['profile']['initial_prompt'])
        self.assertEqual(validate_profile(small['profile']),small['profile'])
        with self.assertRaises(ValueError):profile('vi','unapproved-client-model')
        with self.assertRaises(Exception):bind({'language':'en','provider':'assemblyai','model_key':'small'})
    def test_specialized_Vietnamese_model_preserves_provenance_and_refuses_untested_languages(self):
        value=bind({'language':'vi','provider':'local-whisper','model_key':'phowhisper-small'})
        self.assertEqual(value['profile']['model'],'vinai/PhoWhisper-small')
        self.assertNotEqual(value['profile_sha256'],bind({'language':'vi','provider':'local-whisper'})['profile_sha256'])
        self.assertIsNone(value['profile']['initial_prompt'])
        self.assertTrue(value['profile']['vad_filter']);self.assertTrue(value['profile']['without_timestamps'])
        for language in ('en','auto'):
            with self.assertRaisesRegex(ValueError,'LANGUAGE_UNSUPPORTED'):profile(language,'phowhisper-small')
