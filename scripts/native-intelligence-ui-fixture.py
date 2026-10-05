"""Isolated UI contract test, with clearly labeled fixtures and zero provider calls."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer
from services.windows_native.research import PublicWebResearchProvider
from services.windows_native.tests.test_intelligence_engines import receipt
from services.windows_native.tests.test_intelligence_workflow import FixtureIdeas

root=Path(r'C:\NPD-Video-Factory\post-mvp-validation\phase9-ui-fixture-20261006')
server=LocalServer(8032,Config(data_root=root),start_worker=False)
service=server.intelligence
service.research_provider=PublicWebResearchProvider(root/'research-sources',fetch=lambda url:receipt())
service.idea_provider=FixtureIdeas()
service.start()
print('Isolated intelligence UI fixture ready on 8032; zero actual provider calls; no native production worker.',flush=True)
try: server.serve_forever()
finally: server.server_close()
