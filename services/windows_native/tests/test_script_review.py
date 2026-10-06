"""An actual script decision cannot become media or production approval."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from services.windows_native.contracts import WorkflowError, digest
from services.windows_native.store import Store
from services.windows_native.tests.test_workflow import proposal


class ScriptReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.store=Store(self.root)
        self.project=self.store.create('Script review fixture','Fixture only; no actual provider')
        self.project=self.store.save(self.project['id'],1,proposal=proposal())
        self.sha=hashlib.sha256(self.project['document']['proposal']['narration'].encode('utf-8')).hexdigest()

    def tearDown(self): self.temp.cleanup()

    def test_script_decision_is_durable_idempotent_and_never_approves_production(self):
        before=digest(self.project['document']);reference={'receipt_sha256':'fixture receipt'}
        for _ in range(2):
            after=self.store.review_script(self.project['id'],self.project['revision'],'TEST FIXTURE',True,self.sha,reference)
            self.assertEqual(after['revision'],self.project['revision']);self.assertEqual(digest(after['document']),before)
            self.assertIsNone(after['approval']);self.assertEqual(after['jobs'],[])
        fresh=Store(self.root)
        with fresh.transaction() as con:
            reviews=con.execute("SELECT payload FROM events WHERE action='human_script_approved'").fetchall()
            self.assertEqual(len(reviews),1)
            current=fresh.current_script_review(con,fresh.project(con.execute('SELECT * FROM projects WHERE id=?',(after['id'],)).fetchone()))
            self.assertTrue(current['current']);self.assertFalse(current['production_approved'])
        with self.assertRaisesRegex(WorkflowError,'HUMAN_APPROVAL_REQUIRED_BEFORE_TTS'):
            fresh.enqueue(after['id'],after['revision'],'render','fixture-only-script-approval')

    def test_stale_hash_unacknowledged_and_stale_revision_are_rejected(self):
        for ack,sha,code in [(False,self.sha,'HUMAN_SCRIPT_REVIEW_REQUIRED'),(True,'0'*64,'SCRIPT_REVIEW_STALE_RELOAD'),(True,'missing','SCRIPT_REVIEW_HASH_REQUIRED')]:
            with self.assertRaisesRegex(WorkflowError,code):
                self.store.review_script(self.project['id'],self.project['revision'],'TEST FIXTURE',ack,sha)
        with self.assertRaisesRegex(WorkflowError,'STALE_VERSION_RELOAD'):
            self.store.review_script(self.project['id'],1,'TEST FIXTURE',True,self.sha)

    def test_scene_only_edit_keeps_script_decision_but_narration_edit_invalidates_it(self):
        self.store.review_script(self.project['id'],self.project['revision'],'TEST FIXTURE',True,self.sha)
        revised=self.project['document']['proposal'];revised['visual_brief'][0]['on_screen_text']='Changed visual only'
        after=self.store.save(self.project['id'],self.project['revision'],proposal=revised)
        with self.store.transaction() as con: self.assertTrue(self.store.current_script_review(con,after)['current'])
        after=self.store.save(after['id'],after['revision'],proposal=proposal('Lời đọc khác'))
        with self.store.transaction() as con: self.assertFalse(self.store.current_script_review(con,after)['current'])
        self.assertIsNone(after['approval']);self.assertEqual(after['jobs'],[])

    def test_production_review_retains_actual_chat_source_and_is_not_a_dispatch(self):
        p=self.store.save(self.project['id'],self.project['revision'],
            asset={'id':'fixture.jpg','sha256':'fixture-only','rights_confirmed':True,'illustration':False})
        reference={'source':'human_user_reply_in_codex','authorization_sha256':'fixture-receipt'}
        for _ in range(2):
            approved=self.store.approve(p['id'],p['revision'],'TEST FIXTURE',True,review_reference=reference)
            self.assertEqual(approved['approval']['source'],'human_user_reply_in_codex')
            self.assertEqual(approved['approval']['review_reference'],reference)
            self.assertEqual(approved['approval']['snapshot_sha256'],digest(p['document']))
            self.assertEqual(approved['jobs'],[])
        with self.store.transaction() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM events WHERE action='human_content_approved'").fetchone()[0],1)
        fresh=Store(self.root).get(p['id']);self.assertEqual(fresh['approval'],approved['approval'])

    def test_invalid_production_reference_and_missing_ack_do_not_approve(self):
        for ref in [[],{}, {'source':'unsupported'}, {'source':'human_user_reply_in_codex','note':'x'*5000}]:
            with self.assertRaisesRegex(WorkflowError,'HUMAN_REVIEW_REFERENCE_INVALID'):
                self.store.approve(self.project['id'],self.project['revision'],'TEST FIXTURE',True,review_reference=ref)
        with self.assertRaisesRegex(WorkflowError,'HUMAN_REVIEW_REQUIRED'):
            self.store.approve(self.project['id'],self.project['revision'],'TEST FIXTURE',False,
                review_reference={'source':'human_user_reply_in_codex'})
        self.assertIsNone(self.store.get(self.project['id'])['approval'])
