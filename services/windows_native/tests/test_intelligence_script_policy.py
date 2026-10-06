"""Protect accepted generation defaults while honoring approved intelligence briefs."""
import unittest
from services.windows_native.pipeline import content_instructions


class IntelligenceScriptPolicyTests(unittest.TestCase):
    def test_existing_native_generation_keeps_original_defaults_and_guards(self):
        instructions = content_instructions({'prompt': 'Original project'})
        self.assertIn('video khoảng 25–45 giây', instructions)
        self.assertIn('Dùng ảnh dự án do người dùng cung cấp', instructions)
        self.assertIn('Không tự duyệt, không tự xuất bản', instructions)
        self.assertNotIn('theo thời lượng trong brief', instructions)

    def test_intelligence_brief_duration_and_human_review_override_old_default(self):
        instructions = content_instructions({'content_intelligence': {'brief': {'constraints': ['45–60 giây']}}})
        self.assertNotIn('video khoảng 25–45 giây', instructions)
        self.assertIn('theo thời lượng trong brief đã duyệt', instructions)
        self.assertIn('Không mở đầu bằng lời cảnh báo nguồn máy móc', instructions)
        self.assertIn('Tách ngày công bố, kỳ báo cáo', instructions)
        self.assertIn('không giả định đã có asset hoặc quyền sử dụng', instructions)
        self.assertIn('Không tự duyệt, không tự xuất bản', instructions)
