"""The already existing planning DB must be preserved, never ignored as an unknown file."""
import tempfile,unittest
from pathlib import Path
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.contracts import WorkflowError
from services.windows_native.pipeline import Config
from services.windows_native.planning_store import PlanningStore
from services.windows_native.store import Store

class PlanningBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name);self.config=Config(data_root=self.base/'data',secret_file=self.base/'secrets/absent',assemblyai_secret_file=self.base/'secrets/absent-asr')
        Store(self.config.data_root).create('Backup fixture','No provider calls');self.planning=PlanningStore(self.config.data_root)
    def test_existing_planning_database_and_history_survive_offline_restore(self):
        before=self.planning.save('fixture-item',{'version':0,'provenance':{}},0,{'campaign':'Fixture only'},'AUTOMATED FIXTURE',{})
        receipt=create_backup(self.config,self.base/'backup.zip');self.assertIn('localplanning.sqlite3',receipt['database_status'])
        restored=restore_backup(self.base/'backup.zip',self.base/'restored',expected_sha256=receipt['sha256'])
        after=PlanningStore(Path(restored['destination'])).get('fixture-item',{})
        self.assertEqual(before,after);self.assertEqual(database_status(self.config.data_root/'localplanning.sqlite3')['active_operations'],0)
    def test_running_planning_batch_blocks_offline_backup_without_replaying_or_dropping_it(self):
        self.planning.begin_batch('explicit-backup-busy-fixture',{'reviewer':'AUTOMATED FIXTURE','action':'prepare_scripts'})
        with self.assertRaisesRegex(WorkflowError,'ACTIVE_OPERATIONS'):create_backup(self.config,self.base/'busy.zip')
        self.assertFalse((self.base/'busy.zip').exists())
