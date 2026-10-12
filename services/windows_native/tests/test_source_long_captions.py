"""Full Vietnamese words survive bounded labels and source edit timing."""
import copy
import unittest
from app.production_logic import derive_subtitle_cues, validate_subtitles, ProductionContractError
from app.production_models import SubtitleStyle
from app.timeline_models import TimelineSnapshot


def snapshot():
    tokens = ('Vang Nguyễn chia sẻ cách kiểm tra nguồn thông tin về trí tuệ nhân tạo. '
        'Hai ví dụ tên riêng là Vinhomes Green Paradise Cần Giờ và Vinhomes Saigon Park.').split()
    words = [{'text': text, 'start_seconds': 1 + i * .25, 'end_seconds': 1.2 + i * .25}
        for i, text in enumerate(tokens)]
    end = words[-1]['end_seconds']
    return TimelineSnapshot.model_validate({'duration_seconds': end + 1,
        'width': 1080, 'height': 1920, 'fps': 30, 'aspect_ratio': '9:16', 'tracks': [{
            'track_id': 'trk_subtitles', 'type': 'text', 'kind': 'subtitles', 'order': 0,
            'label': 'Subtitles', 'clips': [{'clip_id': 'clip_source_long_caption', 'kind': 'subtitle',
                'label': ' '.join(tokens)[:120], 'source_start': 1, 'source_end': end,
                'timeline_start': 1, 'duration': end - 1, 'metadata': {
                    'timing_source': 'provider_native_word_intervals', 'measured_source_words': words}}]}]})


class LongSourceCaptionTests(unittest.TestCase):
    def test_sentence_karaoke_and_word_by_word_keep_every_original_interval(self):
        for animation in ('none', 'karaoke', 'word_by_word'):
            with self.subTest(animation=animation):
                source = snapshot()
                original = copy.deepcopy(source)
                style = SubtitleStyle(animation=animation, font_size=64, max_lines=2)
                cues = derive_subtitle_cues(source, style=style)
                self.assertGreater(len(cues), 1)
                words = source.tracks[0].clips[0].metadata['measured_source_words']
                self.assertEqual([word.model_dump(mode='json') for cue in cues for word in cue.words], words)
                self.assertEqual(' '.join(cue.text for cue in cues), ' '.join(word['text'] for word in words))
                self.assertTrue(' '.join(cue.text for cue in cues).endswith('Vinhomes Saigon Park.'))
                self.assertEqual(validate_subtitles(cues, style, source.duration_seconds)['status'], 'passed')
                self.assertEqual(source, original)

    def test_speed_and_source_offset_project_measured_words_without_new_alignment(self):
        source = snapshot()
        clip = source.tracks[0].clips[0]
        clip.speed = 2
        clip.timeline_start = .25
        clip.duration /= 2
        source.duration_seconds = clip.timeline_start + clip.duration
        words = clip.metadata['measured_source_words']
        cues = derive_subtitle_cues(source)
        actual = [word for cue in cues for word in cue.words]
        for old, new in zip(words, actual, strict=True):
            self.assertEqual(new.text, old['text'])
            self.assertAlmostEqual(new.start_seconds, .25 + (old['start_seconds'] - 1) / 2)
            self.assertAlmostEqual(new.end_seconds, .25 + (old['end_seconds'] - 1) / 2)

    def test_changed_label_cannot_silently_reuse_old_word_text(self):
        source = snapshot()
        source.tracks[0].clips[0].label = 'Nội dung sửa khác'
        with self.assertRaisesRegex(ProductionContractError, 'TEXT_MISMATCH'):
            derive_subtitle_cues(source, style=SubtitleStyle(animation='word_by_word'))

    def test_unmeasured_human_text_does_not_gain_word_timestamps(self):
        source = snapshot()
        clip = source.tracks[0].clips[0]
        clip.metadata['subtitle_text'] = 'Nội dung người dùng đã sửa dài hơn bản nhãn hiển thị. ' * 3
        clip.metadata['measured_source_words'] = []
        cues = derive_subtitle_cues(source)
        self.assertTrue(all(not cue.words for cue in cues))
        with self.assertRaisesRegex(ProductionContractError, 'WORD_ALIGNMENT_UNAVAILABLE'):
            derive_subtitle_cues(source, style=SubtitleStyle(animation='karaoke'))

    def test_more_than_forty_words_remain_complete_and_bounded(self):
        source = snapshot()
        clip = source.tracks[0].clips[0]
        words = [{'text': 'AI', 'start_seconds': i * .1, 'end_seconds': i * .1 + .08} for i in range(85)]
        clip.metadata['measured_source_words'] = words
        clip.source_start = clip.timeline_start = 0
        clip.source_end = clip.duration = source.duration_seconds = 8.48
        clip.label = ' '.join(word['text'] for word in words)[:120]
        cues = derive_subtitle_cues(source)
        self.assertEqual(sum(len(cue.words) for cue in cues), 85)
        self.assertTrue(all(len(cue.words) <= 40 for cue in cues))


if __name__ == '__main__':
    unittest.main()
