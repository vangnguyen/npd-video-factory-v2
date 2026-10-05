"""Transport/checkpoint fixtures are not human review or actual media QC."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.hardening import Artifacts
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.tests.test_workflow import proposal


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.config=Config(data_root=self.root); self.server=LocalServer(0,self.config,start_worker=False)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start(); self.store=self.server.store
        self.p=self.store.create("Dashboard fixture","No dispatch")
        self.p=self.store.save(self.p["id"],1,proposal=proposal(),asset={"id":"fixture.jpg","rights_confirmed":True,"sha256":"transport-only"})
        self.p=self.store.approve(self.p["id"],2,"UNIT FIXTURE — NOT HUMAN ACCEPTANCE",True)

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()

    def request(self,method,path,body=None,headers=None):
        con=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=30)
        con.request(method,path,body=json.dumps(body) if body is not None else None,headers={
            "Content-Type":"application/json","Cookie":f"vf_native_session={self.server.session}","X-VF-CSRF":self.server.csrf,**(headers or {})})
        response=con.getresponse(); raw=response.read(); con.close(); return response.status,raw

    def candidate(self):
        job=self.store.enqueue(self.p["id"],self.p["revision"],"render",uuid.uuid4().hex)
        out=self.root/"jobs"/job["id"]; out.mkdir(parents=True); (out/"final.mp4").write_bytes(b"TRANSPORT FIXTURE NOT REAL VIDEO")
        result={"video_url":f"/api/jobs/{job['id']}/video","qc":{"passed":True,"final_sha256":file_sha(out/"final.mp4")},"explicit_transport_fixture":True}
        Artifacts(out,job).commit("render",[out/"final.mp4"],result)
        self.store.claim(); self.store.finish(job,result=result); return self.store.get_job(job["id"])

    def test_duplicate_is_unapproved_with_original_bytes_and_lineage_retained(self):
        before=self.store.get(self.p["id"])
        duplicate=self.store.duplicate(self.p["id"],2)
        self.assertIsNone(duplicate["approval"]); self.assertEqual(duplicate["revision"],1); self.assertEqual(duplicate["jobs"],[])
        self.assertEqual(duplicate["document"]["proposal"],before["document"]["proposal"])
        self.assertEqual(duplicate["document"]["duplication"]["document_sha256"],digest(before["document"]))
        self.assertEqual(self.store.get(self.p["id"]),before)
        self.assertEqual(len(self.store.versions(duplicate["id"])),1)

    def test_archive_restore_restart_preserves_approval_document_and_history(self):
        before=self.store.get(self.p["id"]); history=self.store.versions(self.p["id"])
        p=self.store.archive(self.p["id"],2,True)
        self.assertTrue(p["archived"]); self.assertEqual(self.store.list(),[])
        self.assertEqual(len(self.store.list(True)),1)
        with self.assertRaisesRegex(WorkflowError,"ARCHIVED"): self.store.save(p["id"],2,proposal=proposal())
        self.assertTrue(Store(self.root).get(p["id"])["archived"])
        restored=self.store.archive(p["id"],2,False)
        for field in ("document","approval","revision"): self.assertEqual(restored[field],before[field])
        self.assertEqual(self.store.versions(p["id"]),history)

    def test_busy_stale_archive_and_foreign_origin_refuse(self):
        self.assertEqual(self.request("POST",f"/api/projects/{self.p['id']}/duplicate",{"revision":2},{"X-VF-CSRF":"wrong"})[0],403)
        self.assertEqual(self.request("POST",f"/api/projects/{self.p['id']}/archive",{"revision":2,"archived":True},{"Origin":"https://untrusted.invalid"})[0],403)
        with self.assertRaisesRegex(WorkflowError,"STALE"): self.store.archive(self.p["id"],1,True)
        self.store.enqueue(self.p["id"],2,"content",uuid.uuid4().hex)
        with self.assertRaisesRegex(WorkflowError,"BUSY"): self.store.archive(self.p["id"],2,True)

    def test_final_ack_required_hash_bound_idempotent_and_restart_safe(self):
        job=self.candidate()
        repeated=self.store.approve(self.p["id"],2,"UNIT FIXTURE — NOT HUMAN ACCEPTANCE",True)
        self.assertEqual(repeated["approval"],self.p["approval"])
        with self.assertRaisesRegex(WorkflowError,"HUMAN_FINAL_VIDEO"): self.store.final_video(job["id"])
        with self.assertRaisesRegex(WorkflowError,"WATCH_LISTEN"): self.store.review_render(job["id"],2,"UNIT FIXTURE",False,"approve")
        self.store.review_render(job["id"],2,"UNIT FIXTURE — NOT HUMAN ACCEPTANCE",True,"approve","Transport test")
        self.store.review_render(job["id"],2,"UNIT FIXTURE — NOT HUMAN ACCEPTANCE",True,"approve","Transport test")
        with self.store.transaction() as con: self.assertEqual(con.execute("select count(*) from render_reviews").fetchone()[0],1)
        reviewed=Store(self.root).final_video(job["id"])
        self.assertEqual(reviewed["final_review"]["artifact_sha256"],job["result"]["qc"]["final_sha256"])
        self.assertEqual(self.request("GET",f"/api/jobs/{job['id']}/final")[0],200)
        (self.root/"jobs"/job["id"]/"final.mp4").write_bytes(b"changed")
        self.assertEqual(self.request("GET",f"/api/jobs/{job['id']}/final")[0],409)

    def test_reject_requires_reason_advances_version_and_never_transfers_acceptance(self):
        job=self.candidate()
        with self.assertRaisesRegex(WorkflowError,"DECISION_REASON"): self.store.review_render(job["id"],2,"UNIT FIXTURE",False,"reject")
        self.store.review_render(job["id"],2,"UNIT FIXTURE",True,"approve")
        p=self.store.review_render(job["id"],2,"UNIT FIXTURE",False,"reject","Need changed layout")
        self.assertEqual(p["revision"],3); self.assertIsNone(p["approval"])
        self.assertEqual(self.request("GET",f"/api/jobs/{job['id']}/final")[0],409)
        self.assertTrue((self.root/"jobs"/job["id"]/"final.mp4").exists())
        self.assertEqual(self.store.get_job(job["id"])["final_review"]["decision"],"reject")
        duplicate=self.store.duplicate(p["id"],3)
        self.assertIsNone(duplicate["approval"]); self.assertEqual(duplicate["jobs"],[])

    def test_script_reorder_changes_narration_hash_and_invalidates_old_approval(self):
        value=proposal(); value["visual_brief"]=list(reversed(value["visual_brief"]))
        for i,scene in enumerate(value["visual_brief"]): scene["scene"]=i+1
        value["narration"]=" ".join(s["narration_excerpt"] for s in value["visual_brief"])
        p=self.store.save(self.p["id"],2,proposal=value)
        self.assertIsNone(p["approval"]); self.assertNotEqual(digest(value),digest(self.p["document"]["proposal"]))
        self.assertEqual(self.store.versions(p["id"])[-1]["revision"],1)
        p=self.store.reject_content(p["id"],p["revision"],"UNIT FIXTURE","Check reordered narration")
        self.assertIsNone(p["approval"]); self.assertEqual(p["revision"],4)

    def test_artifact_metadata_session_and_archive_filter_http(self):
        job=self.candidate(); status,raw=self.request("GET",f"/api/jobs/{job['id']}/artifacts")
        self.assertEqual(status,200); self.assertEqual(json.loads(raw)["artifacts"][0]["sha256"],job["result"]["qc"]["final_sha256"])
        self.assertEqual(self.request("GET",f"/api/jobs/{job['id']}/artifacts",headers={"Cookie":""})[0],401)
        self.store.archive(self.p["id"],2,True)
        self.assertEqual(json.loads(self.request("GET","/api/projects")[1]),[])
        self.assertEqual(len(json.loads(self.request("GET","/api/projects?archived=include")[1])),1)

    def test_open_folder_is_csrf_guarded_and_derived_from_verified_job(self):
        job=self.candidate(); endpoint=f"/api/jobs/{job['id']}/open-folder"
        with patch("services.windows_native.server.os.startfile") as open_folder:
            self.assertEqual(self.request("POST",endpoint,{},headers={"X-VF-CSRF":"wrong"})[0],403)
            open_folder.assert_not_called()
            self.assertEqual(self.request("POST",endpoint,{"path":"C:/unrelated"})[0],400)
            open_folder.assert_not_called()
            self.assertEqual(self.request("POST",endpoint,{})[0],200)
            open_folder.assert_called_once_with(str((self.root/"jobs"/job["id"]).resolve()))
