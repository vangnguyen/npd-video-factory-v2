"""Isolated localhost harness for the EXISTING API/Studio/production worker.

Not deployment, ASR acceptance, malware acceptance or human voice acceptance.
All state is confined to a new explicit --root. No provider credentials loaded.
"""
from __future__ import annotations
import argparse
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import os
import socket
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "apps/api"), str(REPO / "apps/api/tests")]

parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--tools", type=Path, required=True)
parser.add_argument("--port", type=int, default=8017)
parser.add_argument("--renderer-port", type=int, default=3017)
parser.add_argument("--resume", action="store_true", help="reload this harness's persisted dev DB without resetting it")
args = parser.parse_args()
root, tools = args.root.resolve(), args.tools.resolve()
marker = root / ".isolated-mvp1-dev"
if root.exists() and (not args.resume or not marker.is_file() or marker.read_text().strip() != "ZERO_EXTERNAL_PROVIDER_DEV_ONLY"):
    parser.error("fresh root required, or --resume for an existing isolated harness root")
if any(str(root).startswith(prefix) for prefix in ("/etc/", "/opt/", "/run/", "/var/lib/npd-video-factory/")):
    parser.error("runtime/discovery locations are forbidden")
root.mkdir(mode=0o700, parents=True, exist_ok=args.resume)
if not args.resume:
    marker.write_text("ZERO_EXTERNAL_PROVIDER_DEV_ONLY")
# Block outbound IP connections in this harness. Only local renderer/API/SQLite are used.
real_connect = socket.socket.connect
def local_connect(sock, address):
    if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1"}:
        raise RuntimeError("isolated dev harness blocks external network")
    return real_connect(sock, address)
socket.socket.connect = local_connect

from fastapi.staticfiles import StaticFiles
from app.main import app
from app.config import Settings
from app.db import Base, create_engine, create_session_factory
from app.repositories import PlatformRepository
from app.auto_edit_repository import AutoEditRepository
from app.auto_edit_providers import FFprobeMediaProbe, FFmpegMediaSignalProvider, ContractOnlyTranscriptionProvider, ProviderNotConfigured
from app.auto_edit_service import AutoEditAnalysisService, UploadService
from app.content_service import ContentService
from app.content_generation import ContentGenerationService, content_provider_definition
from app.repositories import PostgresJobStore
from app.object_storage import LocalObjectStorageProvider
from app.media_security import DeterministicMediaMalwareScanner
from app.media_intelligence_repository import MediaIntelligenceRepository
from app.media_intelligence_service import MediaPlanningService, create_media_provider_bundle
from app.vision_repository import VisionRepository
from app.timeline_repository import TimelineRepository
from app.timeline_service import TimelineService, TimelineContractValidator
from app.production_repository import ProductionRepository
from app.production_service import ProductionPackageService, ProductionRenderProcessor, RemotionTimelineRenderEngine, PRODUCTION_RENDER_QUEUE_KEY
from app.production_audio import AudioMixEngine
from app.production_qc import FullProductionQC
from app.production_logic import TimelineRenderContractValidator
from app.providers import EspeakVietnameseTTSProvider
from app.publishing_repository import PublishingRepository
from app.publishing_service import PublishingService
from app.publishing_providers import PublishingProviderRegistry
from app.publishing_logic import PublishingCapabilityRegistry
from app.analytics_repository import AnalyticsRepository
from app.analytics_service import AnalyticsService
from app.analytics_providers import AnalyticsProviderRegistry
from auth_test_support import install_test_human_auth, TEST_HUMAN_TOKEN

class NoProviderBoundary:
    async def execute(self, *a, **kw):
        raise ProviderNotConfigured("ASR_BLOCKED_ZERO_EXTERNAL_PROVIDER_AUTHORITY")

class LocalQueue:
    """Test queue replaces Redis transport ONLY. Production repository/worker unchanged."""
    def __init__(self):
        self.queue = asyncio.Queue()
        self.pending = set()
        self.processor = None
    async def rpush(self, key, value):
        if key != PRODUCTION_RENDER_QUEUE_KEY:
            raise RuntimeError("unsupported job in isolated harness")
        if value not in self.pending:
            self.pending.add(value)
            await self.queue.put(value)
        return self.queue.qsize()
    async def work(self):
        while True:
            value = await self.queue.get()
            try:
                await self.processor.process(value)
            finally:
                self.pending.discard(value)
                self.queue.task_done()

@asynccontextmanager
async def lifespan(_app):
    engine = create_engine(f"sqlite+aiosqlite:///{root / 'dev.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    platform, assets = PlatformRepository(factory), AutoEditRepository(factory)
    await platform.seed_providers([{"provider_key":key,"display_name":key,"capability":cap,
        "adapter":"isolated-dev","routing_mode":"primary","status":"healthy","enabled":True,
        "supports_dry_run":True,"metadata":{"paid":False,"dev_only":True}}
        for key,cap in [("espeak","tts"),("remotion","rendering")]])
    await platform.seed_providers([content_provider_definition("fixture")])
    storage = LocalObjectStorageProvider(root / "objects")
    await storage.ensure_ready()
    ff = tools / "ffmpeg-master-latest-linux64-gpl/bin"
    # Reuse offline adapter. Restrict PATH to explicitly installed local tools, not host executor.
    os.environ["PATH"] = f"{tools / 'espeak-root/usr/bin'}:{ff}:/usr/bin:/bin"
    libs = tools / "espeak-root/usr/lib/x86_64-linux-gnu"
    os.environ["LD_LIBRARY_PATH"] = f"{libs}:{libs / 'pulseaudio'}"
    os.environ["ESPEAK_DATA_PATH"] = str(tools / "espeak-root/usr/lib/x86_64-linux-gnu")
    settings = Settings(_env_file=None, contracts_root=REPO / "packages/contracts",
        audio_tts_provider="espeak", transcription_provider="contract",
        provider_external_execution_enabled=False, provider_paid_execution_enabled=False,
        provider_global_kill_switch_engaged=True)
    timelines, production, media = TimelineRepository(factory), ProductionRepository(factory), MediaIntelligenceRepository(factory)
    queue = LocalQueue()
    generation_queue = LocalQueue()
    app.state.platform_repository = platform
    app.state.auto_edit_repository = assets
    app.state.object_storage = storage
    app.state.media_intelligence_repository = media
    app.state.media_planning_service = MediaPlanningService(repository=media,auto_edit_repository=assets,
        vision_repository=VisionRepository(factory),platform=platform,providers=create_media_provider_bundle(settings),
        allow_external_execution=False,allow_paid_execution=False)
    app.state.timeline_repository = timelines
    app.state.production_repository = production
    app.state.content_service = ContentService(platform)
    app.state.content_generation_service = ContentGenerationService(platform=platform,
        store=PostgresJobStore(factory, generation_queue, platform=platform), queue=generation_queue, mode="fixture")
    generation_queue.processor = app.state.content_generation_service
    app.state.upload_service = UploadService(repository=assets,platform=platform,object_storage=storage,
        media_probe=FFprobeMediaProbe(str(ff / "ffprobe")),malware_scanner=DeterministicMediaMalwareScanner(),
        staging_root=root / "uploads",default_part_size_bytes=1024*1024,max_part_size_bytes=32*1024*1024,max_upload_size_bytes=25000000)
    app.state.auto_edit_analysis_service = AutoEditAnalysisService(repository=assets, platform=platform,
        object_storage=storage, transcription_provider=ContractOnlyTranscriptionProvider(),
        signal_provider=FFmpegMediaSignalProvider(str(ff / "ffmpeg")), staging_root=root / "analyses",
        provider_safety=NoProviderBoundary(), derived_timing_enabled=False)
    app.state.timeline_service = TimelineService(repository=timelines,platform=platform,auto_edit_repository=assets,
        media_repository=media,object_storage=storage,validator=TimelineContractValidator(REPO / "packages/contracts/timeline.schema.json"))
    app.state.production_package_service = ProductionPackageService(repository=production,
        timeline_repository=timelines,asset_repository=assets,queue=queue,settings=settings)
    app.state.production_render_download_root = root / "downloads"
    publishing = PublishingRepository(factory)
    app.state.publishing_service = PublishingService(repository=publishing,production_repository=production,
        asset_repository=assets,capabilities=PublishingCapabilityRegistry(REPO / "packages/contracts/publishing-capabilities.json"),
        providers=PublishingProviderRegistry(settings),settings=settings)
    app.state.analytics_service = AnalyticsService(repository=AnalyticsRepository(factory),
        publishing_repository=publishing,platform_repository=platform,providers=AnalyticsProviderRegistry(settings),queue=queue,settings=settings)
    queue.processor = ProductionRenderProcessor(repository=production,platform=platform,asset_repository=assets,
        object_storage=storage,renderer=RemotionTimelineRenderEngine(renderer_url=f"http://127.0.0.1:{args.renderer_port}",timeout_seconds=600),
        qc=FullProductionQC(ffmpeg_path=str(ff / "ffmpeg"),ffprobe_path=str(ff / "ffprobe")),
        tts_provider=EspeakVietnameseTTSProvider(voice="vi",rate=175),audio_engine=AudioMixEngine(ffmpeg_path=str(ff / "ffmpeg")),
        manifest_validator=TimelineRenderContractValidator(REPO / "packages/contracts/timeline-render.schema.json"),
        staging_root=root / "renders",brand_name="Isolated MVP dev")
    install_test_human_auth(app,platform_repository=platform)
    # Short-lived LOCAL synthetic owner session, never a provider credential. Excluded from evidence/commit.
    token_file = root / ".dev-session"
    token_file.write_text(TEST_HUMAN_TOKEN)
    token_file.chmod(0o600)
    task = asyncio.create_task(queue.work())
    generation_task = asyncio.create_task(generation_queue.work())
    await generation_queue.processor.recover()
    await queue.processor.recover_incomplete(queue)
    try:
        yield
    finally:
        task.cancel()
        generation_task.cancel()
        token_file.unlink(missing_ok=True)
        await engine.dispose()

app.router.lifespan_context = lifespan
app.mount("/", StaticFiles(directory=REPO / "apps/studio-web", html=True), name="isolated-studio")
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app,host="127.0.0.1",port=args.port)
