import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pydantic import ValidationError
from services.windows_native.contracts import WorkflowError
from services.windows_native.intelligence_models import ResearchRun, ResearchFinding, stamp
from services.windows_native.intelligence_store import IntelligenceStore


class IntelligenceModelTests(unittest.TestCase):
    def test_source_reported_claim_requires_exact_attributed_quote(self):
        kwargs = dict(provenance={'origin':'test_fixture'}, run_id='r', kind='SOURCED_FACT', claim='Quote', source_references=[], relevance=.5, confidence=.5, timestamp_relevance='unknown', grounding='SOURCE_REPORTED')
        with self.assertRaises(ValidationError): ResearchFinding(**kwargs)
        kwargs['source_references'] = [{'source_id':'a'*32,'quote':'Quote'}]
        self.assertEqual(ResearchFinding(**kwargs).grounding,'SOURCE_REPORTED')
        kwargs['grounding'] = 'INFERENCE'
        with self.assertRaises(ValidationError): ResearchFinding(**kwargs)

    def test_record_rejects_empty_provenance_and_naive_time(self):
        with self.assertRaises(ValidationError): ResearchRun(query='q',context={},provider='fixture',provenance={})
        with self.assertRaises(ValidationError): ResearchRun(query='q',context={},provider='fixture',provenance={'origin':'test'},created_at=stamp().replace(tzinfo=None))

    def test_history_optimistic_edits_and_separate_process_restart(self):
        with tempfile.TemporaryDirectory() as root:
            store=IntelligenceStore(root)
            first=store.put('ResearchRun',ResearchRun(query='q',context={},provider='fixture',provenance={'origin':'test'}).model_dump(mode='json'))
            second=store.put('ResearchRun',{**first,'status':'FAILED','error':{'code':'EXPLICIT_FAILURE'}},1)
            with self.assertRaisesRegex(WorkflowError,'STALE'): store.put('ResearchRun',first,1)
            self.assertEqual(store.history(first['id']),[first,second])
            code="from services.windows_native.intelligence_store import IntelligenceStore; import json,sys; print(json.dumps(IntelligenceStore(sys.argv[1]).get(sys.argv[2])))"
            reopened=json.loads(subprocess.check_output([sys.executable,'-c',code,root,first['id']],text=True))
            self.assertEqual(reopened,second)
            con=sqlite3.connect(store.db)
            try:
                self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0],1)
                con.execute("UPDATE records SET document=replace(document,'EXPLICIT_FAILURE','TAMPERED') WHERE id=?",(first['id'],))
                con.commit()
            finally:
                con.close()
            with self.assertRaisesRegex(WorkflowError,'INTEGRITY'): store.get(first['id'])

    def test_initialization_does_not_open_production_database(self):
        with tempfile.TemporaryDirectory() as root:
            accepted=Path(root)/'workflow.sqlite3'; accepted.write_bytes(b'accepted bytes')
            IntelligenceStore(root)
            self.assertEqual(accepted.read_bytes(),b'accepted bytes')
