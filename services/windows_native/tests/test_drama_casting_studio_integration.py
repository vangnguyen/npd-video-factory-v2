"""Owned metadata fixtures, real Native HTTP + production callbacks; never TTS or browser QA."""
import os,shutil,subprocess,tempfile,threading,unittest
from pathlib import Path
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer
from services.windows_native.tests.test_voice_library import definition
ROOT=Path(__file__).resolve().parents[3]
class DramaCastingStudioIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node.js required for casting Studio/Native integration')
    def test_http_casting_to_scenes_with_production_callback(self):
        with tempfile.TemporaryDirectory(prefix='vf-casting-next-integration-') as directory:
            base=Path(directory);server=LocalServer(0,Config(data_root=base/'data',runtime_root=base/'no-runtime',secret_file=base/'private/no-secret',assemblyai_secret_file=base/'private/no-asr'),start_worker=False)
            for index in range(2):
                server.voice_library.create({'request_key':'explicit-casting-metadata-voice-'+str(index),'definition':definition(display_name='METADATA FIXTURE '+str(index),provider_voice_id='fixture-'+str(index),rights_status='owner_declared',license='Owned synthetic metadata test fixture; no voice/audio asserted',source_reference='fixture://metadata-only',permission_reference='EXPLICIT TEST FIXTURE ONLY')},actor_ref='explicit-owned-fixture')
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                result=subprocess.run([shutil.which('node'),'--test','apps/studio-web/tests/drama-casting-next.integration.mjs'],cwd=ROOT,env={**os.environ,'VF_DRAMA_TEST_ORIGIN':f'http://127.0.0.1:{server.server_port}'},capture_output=True,text=True,encoding='utf-8',timeout=120)
                self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr);print(result.stdout)
            finally:server.shutdown();server.server_close();thread.join()
