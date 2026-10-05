import http.client
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid
import zipfile

from PIL import Image
from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.ingestion import DOCUMENT_TYPES, existing_script, ingest_document, project_input, provider_context
from services.windows_native.media import ingest_media
from services.windows_native.pipeline import Config, Pipeline
from services.windows_native.server import LocalServer, Runner
from services.windows_native.store import Store

SCRIPT = "Xin chào Vinhomes Green Paradise Cần Giờ. Hãy kiểm chứng thông tin dự án. Cảm ơn bạn đã xem."
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.config = Config(data_root=self.root); self.store = Store(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_prompt_idea_and_script_use_existing_content_contract_and_hash(self):
        for kind in ("prompt", "idea", "script"):
            p = self.store.create(kind, SCRIPT, kind)
            inputs = p["input"]
            self.assertEqual(inputs["text_inputs"][0]["kind"], kind)
            self.assertEqual(inputs["text_inputs"][0]["text"], SCRIPT)
            self.assertEqual(len(inputs["hash"]), 64)
            self.assertEqual(Store(self.root).get(p["id"])["input"], inputs)
        with self.assertRaises(WorkflowError): self.store.create("invalid", "text", "unsupported")

    def test_existing_script_prepares_without_key_or_provider_and_keeps_exact_words(self):
        p = self.store.create("User script", SCRIPT, "script")
        self.store.enqueue(p["id"], 1, "content", uuid.uuid4().hex)
        with patch("services.windows_native.pipeline.load_key") as key, patch("services.windows_native.pipeline.generate") as provider:
            Runner(self.store, Pipeline(self.config)).run_one()
            key.assert_not_called(); provider.assert_not_called()
        p = self.store.get(p["id"])
        self.assertEqual(p["document"]["proposal"]["narration"], SCRIPT)
        self.assertEqual(p["jobs"][0]["result"]["source"], "existing_user_script")
        self.assertEqual(p["jobs"][0]["result"]["provider_calls"], 0)
        self.assertIsNone(p["approval"])
        self.assertEqual(existing_script({"prompt": "Một câu ngắn có sẵn."})["narration"], "Một câu ngắn có sẵn.")

    def test_single_multiple_images_preserve_upload_original_bytes_and_mime_validation(self):
        p = self.store.create("Images", "", "media")
        for index in range(2):
            source = self.root / f"photo-{index}.png"; Image.new("RGB", (320, 240), (0, 100+index, 0)).save(source)
            before = file_sha(source)
            asset = ingest_media(self.config, source, "image/png", "misleading-name.bin", rights_confirmed=True, illustration=True)
            self.assertEqual(file_sha(source), before)
            self.assertEqual(file_sha(self.root / "originals" / asset["original_id"]), before)
            self.assertEqual(asset["source_sha256"], before)
            p = self.store.append_media(p["id"], p["revision"], asset)
            self.assertEqual(len(p["input"]["image_assets"]), index+1)
        with self.assertRaisesRegex(WorkflowError, "INVALID_IMAGE"):
            ingest_media(self.config, source, "image/jpeg", "photo.jpg", rights_confirmed=True, illustration=True)

    def test_single_multiple_videos_keep_original_and_speech_capability_error(self):
        p = self.store.create("Videos", "", "media")
        for index in range(2):
            source = self.root / f"clip-{index}.mp4"
            command = [str(self.config.ffmpeg_bin / "ffmpeg.exe"), "-v", "error", "-nostdin", "-n", "-f", "lavfi", "-i", "color=c=green:s=320x240:r=30:d=0.3"]
            if index: command += ["-f", "lavfi", "-i", "sine=frequency=440:duration=0.3", "-c:a", "aac"]
            command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", "0.3", str(source)]
            subprocess.run(command, check=True, timeout=20, capture_output=True)
            before = file_sha(source)
            asset = ingest_media(self.config, source, "video/mp4", "image.jpg", rights_confirmed=True, illustration=False)
            self.assertEqual(file_sha(source), before)
            self.assertEqual(file_sha(self.root / "originals" / asset["original_id"]), before)
            self.assertEqual(asset["has_audio"], bool(index))
            self.assertEqual(asset["fps"], 30)
            p = self.store.append_media(p["id"], p["revision"], asset)
            self.assertEqual(len(p["input"]["video_assets"]), index+1)
        self.assertEqual(p["input"]["metadata"]["workflow"], "ASR_REQUIRED")
        with self.assertRaisesRegex(WorkflowError, "ASR_PROVIDER_UNAVAILABLE_NO_TRANSCRIPT"):
            provider_context(p["document"])
        self.assertNotIn("transcript", p["document"])

    def test_txt_markdown_docx_originals_extraction_and_wrong_content_rejected(self):
        for mime, suffix in (("text/plain", ".txt"), ("text/markdown", ".md"), (DOCX_MIME, ".docx")):
            source = self.root / ("source"+suffix)
            if suffix == ".docx":
                with zipfile.ZipFile(source, "w") as package:
                    package.writestr("[Content_Types].xml", '<Types><Override ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
                    package.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'+SCRIPT+'</w:t></w:r></w:p></w:body></w:document>')
            else: source.write_text(SCRIPT, encoding="utf-8")
            before = file_sha(source)
            asset = ingest_document(self.config, source, mime, "wrong.extension")
            self.assertEqual(file_sha(source), before)
            self.assertEqual(file_sha(self.root / "documents" / asset["id"]), before)
            self.assertEqual(asset["extracted_text"], SCRIPT)
        source = self.root / "binary.txt"; source.write_bytes(b"\x00\x01%PDF")
        for mime in ("text/plain", DOCX_MIME, "application/pdf"):
            with self.assertRaises(WorkflowError): ingest_document(self.config, source, mime, "safe.txt")

    def test_mixed_input_restart_versions_and_script_workflow(self):
        p = self.store.create("Mixed", SCRIPT, "script")
        image = self.root / "photo.png"; Image.new("RGB", (320,240), "green").save(image)
        asset = ingest_media(self.config, image, "image/png", "photo.png", rights_confirmed=True, illustration=True)
        p = self.store.append_media(p["id"], p["revision"], asset)
        document = self.root / "facts.txt"; document.write_text("Tài liệu chưa được xác minh.", encoding="utf-8")
        doc = ingest_document(self.config, document, "text/plain", "facts.txt")
        p = self.store.append_document(p["id"], p["revision"], doc)
        expected = p["input"]
        self.assertTrue(expected["metadata"]["mixed"])
        self.assertEqual(Store(self.root).get(p["id"])["input"], expected)
        self.assertEqual([v["revision"] for v in self.store.versions(p["id"])], [3,2,1])
        self.store.enqueue(p["id"], p["revision"], "content", uuid.uuid4().hex)
        Runner(self.store, Pipeline(self.config)).run_one()
        after = self.store.get(p["id"])
        self.assertEqual(after["jobs"][0]["status"], "awaiting_review")
        self.assertEqual(after["document"]["proposal"]["narration"], SCRIPT)
        self.assertEqual(after["document"]["documents"][0], doc)

    def test_document_context_and_limit_are_explicit_not_truncated(self):
        doc = {"prompt": "Yêu cầu", "documents": [{"extracted_text": SCRIPT}], "assets": []}
        self.assertIn(SCRIPT, provider_context(doc))
        doc["documents"][0]["extracted_text"] = "x"*20001
        with self.assertRaisesRegex(WorkflowError, "INPUT_CONTEXT_EXCEEDS"):
            provider_context(doc)

    def test_docx_external_entities_never_processed(self):
        source = self.root / "entity.docx"
        with zipfile.ZipFile(source, "w") as package:
            package.writestr("[Content_Types].xml", "wordprocessingml.document.main+xml")
            package.writestr("word/document.xml", '<!DOCTYPE document [<!ENTITY x SYSTEM="file:///secret">]><document>&x;</document>')
        with self.assertRaisesRegex(WorkflowError, "DOCUMENT_CONTENT_INVALID"):
            ingest_document(self.config, source, DOCX_MIME, "entity.docx")

    def test_http_document_upload_persists_canonical_input_and_revision(self):
        server = LocalServer(0, self.config, start_worker=False)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            p = server.store.create("HTTP documents", "", "media")
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
            conn.request("POST", f"/api/projects/{p['id']}/documents", SCRIPT.encode("utf-8"), headers={
                "Cookie": f"vf_native_session={server.session}", "X-VF-CSRF": server.csrf,
                "X-VF-Revision": "1", "Content-Type": "text/plain", "X-VF-Filename": "document.txt"})
            response = conn.getresponse(); result = json.loads(response.read()); conn.close()
            self.assertEqual(response.status, 201)
            self.assertEqual(result["revision"], 2)
            self.assertEqual(result["input"]["document_assets"][0]["extracted_text"], SCRIPT)
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__":
    unittest.main()
