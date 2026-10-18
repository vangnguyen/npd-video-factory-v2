"""Real HTTP save + production Studio callback. Owned fixtures only; no browser claim."""
import os,shutil,subprocess,tempfile,threading,unittest
from pathlib import Path
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer

ROOT=Path(__file__).resolve().parents[3]

class DramaSaveStudioIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node.js required for Studio/Native callback integration')
    def test_real_http_and_production_studio_save_callback(self):
        with tempfile.TemporaryDirectory(prefix='vf-drama-save-integration-') as folder:
            base=Path(folder)
            server=LocalServer(0,Config(data_root=base/'data',runtime_root=base/'no-model',secret_file=base/'private/no-secret',assemblyai_secret_file=base/'private/no-asr-secret'),start_worker=False)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                result=subprocess.run([shutil.which('node'),'--test','apps/studio-web/tests/drama-save-native.integration.mjs'],cwd=ROOT,
                    env={**os.environ,'VF_DRAMA_TEST_ORIGIN':f'http://127.0.0.1:{server.server_port}'},capture_output=True,text=True,encoding='utf-8',timeout=120)
                self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
                print(result.stdout)
            finally:
                server.shutdown();server.server_close();thread.join()
