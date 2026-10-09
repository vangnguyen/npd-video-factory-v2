from __future__ import annotations

import argparse
import base64
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import socket
import threading
import time
import uuid
from urllib.parse import unquote, parse_qs

from .contracts import WorkflowError, file_sha
from .pipeline import Config, LOCKS, Pipeline, REPO, verify_runtime
from .store import Store
from .hardening import failure
from .ingestion import DOCUMENT_TYPES, DOCUMENT_MAX_BYTES, ingest_document
from . import assemblyai_connection
from .music import MUSIC_TYPES, MUSIC_MAX_BYTES, ingest_music
from .observability import Observer, configure_logging, readiness, route_context, step_context
from .media import CONTENT_TYPES, IMAGE_MAX_BYTES, VIDEO_MAX_BYTES, discard_media, ingest_media, library_assets, library_file, media_path, project_assets


class Runner:
    def __init__(self, store, pipeline, *, observer=None):
        self.store, self.pipeline = store, pipeline
        self.publications = None
        self.analytics = None
        self.official_accounts = None
        self.official_publish_worker = None
        self.official_publish_queue = None
        self.official_analytics = None
        self.official_analytics_refresh = None
        self.google_oauth = None
        self.official_vision = None
        self.vision = None
        self.observer = observer or Observer()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = threading.Thread(target=self.work, daemon=True, name="native-single-worker")

    def start(self):
        self.store.recover()
        if self.official_accounts is not None:self.official_accounts.recover()
        if self.official_publish_worker is not None:self.official_publish_worker.recover()
        if self.official_publish_queue is not None:self.official_publish_queue.recover()
        if self.official_analytics is not None:self.official_analytics.recover()
        if self.official_analytics_refresh is not None:self.official_analytics_refresh.recover()
        if self.google_oauth is not None:self.google_oauth.recover()
        if self.official_vision is not None:self.official_vision.recover()
        self.thread.start()

    def run_one(self):
        if self.vision is not None:
            try:
                if self.vision.process() is not None: return True
            except WorkflowError:
                self.observer.emit('worker_failed',stage='media_analysis',duration=0)
        if self.analytics is not None:
            try:
                if self.analytics.refresh is not None:self.analytics.refresh.tick()
                if self.analytics.process() is not None: return True
            except WorkflowError:
                self.observer.emit('worker_failed',stage='analytics',duration=0)
        if self.publications is not None:
            try:
                if self.publications.process() is not None: return True
            except WorkflowError:
                self.observer.emit('worker_failed', stage='publishing', provider='mock-publishing', duration=0)
        if self.official_accounts is not None:
            started=time.monotonic()
            try:
                value=self.official_accounts.process()
                if value is not None:
                    self.observer.emit('worker_step',job_id=value['check_id'],project_id=value['project_id'],stage='official_account_read',
                        provider=value['snapshot']['target']['provider_key'],duration=time.monotonic()-started)
                    return True
            except WorkflowError:self.observer.emit('worker_failed',stage='official_account_read',duration=time.monotonic()-started)
        if self.official_analytics is not None:
            started=time.monotonic()
            try:
                refreshed=self.official_analytics_refresh.tick() if self.official_analytics_refresh is not None else None
                value=self.official_analytics.process()
                if value is not None:
                    self.observer.emit('worker_step',job_id=value['sync_id'],project_id=value['project_id'],stage='official_analytics_read',provider='youtube-analytics-api',duration=time.monotonic()-started)
                    return True
                if refreshed is not None:
                    self.observer.emit('worker_step',job_id=refreshed['plan_id'],project_id=refreshed['project_id'],stage='official_analytics_refresh',provider='local-scheduler',duration=time.monotonic()-started)
                    return True
            except WorkflowError:self.observer.emit('worker_failed',stage='official_analytics_read',duration=time.monotonic()-started)
        if self.official_publish_queue is not None:
            started=time.monotonic()
            try:
                value=self.official_publish_queue.process()
                if value is not None:
                    self.observer.emit('worker_step',job_id=value['plan_id'],project_id=value['project_id'],stage='official_publish_queue',provider='youtube-data-api-publishing',duration=time.monotonic()-started)
                    return True
            except WorkflowError:self.observer.emit('worker_failed',stage='official_publish_queue',duration=time.monotonic()-started)
        job = self.store.claim()
        if not job:
            return False
        step, started = "starting", time.monotonic()
        def log_step(error=False):
            category, provider = step_context(step)
            self.observer.emit('worker_failed' if error else 'worker_step', request_id=job['id'],
                job_id=job['id'], project_id=job['project_id'], stage=category, provider=provider,
                duration=time.monotonic() - started)
        def stage(value):
            nonlocal step, started
            self.store.log_step(job, step, time.monotonic() - started)
            log_step()
            self.store.stage(job["id"], value)
            step, started = value, time.monotonic()
        try:
            result = self.pipeline.run(job, stage)
            self.store.log_step(job, step, time.monotonic() - started)
            log_step()
            self.store.finish(job, result=result)
        except Exception as error:
            safe = {"code": error.code if isinstance(error, WorkflowError) else type(error).__name__, "automatic_retry": False}
            if isinstance(error, WorkflowError) and error.http_status:
                safe["http_status"] = error.http_status
            self.store.log_step(job, step, time.monotonic() - started, safe["code"])
            log_step(error=True)
            self.store.finish(job, error=safe)
        return True

    def work(self):
        while not self.stop.is_set():
            if not self.run_one():
                self.wake.wait(1)
                self.wake.clear()


def save_image(config, payload):
    from PIL import Image, ImageOps
    if payload.get("rights_confirmed") is not True or not isinstance(payload.get("illustration"), bool):
        raise WorkflowError("IMAGE_RIGHTS_CONFIRMATION_REQUIRED", 400)
    try:
        raw = base64.b64decode(payload["image_base64"], validate=True)
        if not 1 <= len(raw) <= 15 * 1024 * 1024:
            raise ValueError()
        Image.MAX_IMAGE_PIXELS = 40_000_000
        image = Image.open(io.BytesIO(raw))
        if image.format not in {"JPEG", "PNG"} or image.width * image.height > 40_000_000:
            raise ValueError()
        image.load()
        image = ImageOps.exif_transpose(image).convert("RGB")
        if min(image.size) < 240:
            raise ValueError()
    except Exception:
        raise WorkflowError("INVALID_IMAGE_JPEG_PNG_MAX_15MB_40MP_MIN_240PX", 400) from None
    directory = config.data_root / "assets"
    directory.mkdir(parents=True, exist_ok=True)
    identifier = uuid.uuid4().hex + ".jpg"
    path = directory / identifier
    image.save(path, quality=95)
    return {"id": identifier, "sha256": file_sha(path), "illustration": payload["illustration"],
            "rights_confirmed": True, "width": image.width, "height": image.height,
            "source_type":"user_upload","rights_status":"unknown","license":None,
            "provider":"native-local-upload","source_reference":"upload://"+identifier[:-4],"generation_provenance":{}}


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, config, *, pipeline=None, start_worker=True, observer=None, access=None,
        bridge_auth_registry=None,bridge_webhook_registry=None,bridge_http_enabled=False,
        stock_registry=None,stock_api_enabled=False,stock_factories=None,owner_rights_overrides=False,
        generation_registry=None,generation_api_enabled=False,generation_factory=None,
        trend_feed_registry=None,trend_feed_enabled=False,trend_providers=None,
        official_account_registry=None,official_account_read_enabled=False,official_account_factories=None,
        official_publish_registry=None,official_publish_enabled=False,official_publish_factories=None,official_publish_session_directory=None,official_publish_queue_enabled=False,
        official_analytics_enabled=False,official_analytics_refresh_enabled=False,
        google_oauth_registry=None,google_oauth_directory=None,google_oauth_enabled=False,google_oauth_slots=None,google_oauth_client=None,
        official_vision_registry=None,official_vision_directory=None,official_vision_enabled=False,official_vision_factories=None):
        config.validate_data_root()
        if type(official_vision_enabled) is not bool:raise WorkflowError('NATIVE_OFFICIAL_VISION_CONFIGURATION_INVALID',400)
        if official_vision_registry is not None and official_vision_factories is not None:raise WorkflowError('NATIVE_OFFICIAL_VISION_CONFIGURATION_CONFLICT',400)
        has_vision_config=official_vision_registry is not None or official_vision_factories is not None
        if has_vision_config != (official_vision_directory is not None) or official_vision_enabled and not has_vision_config:
            raise WorkflowError('NATIVE_OFFICIAL_VISION_PROTECTED_REGISTRY_VAULT_REQUIRED',400)
        if has_vision_config and access is None:raise WorkflowError('NATIVE_OFFICIAL_VISION_HUMAN_AUTH_REQUIRED',400)
        if type(google_oauth_enabled) is not bool:raise WorkflowError('NATIVE_GOOGLE_OAUTH_CONFIGURATION_INVALID',400)
        if google_oauth_registry is not None and (google_oauth_slots is not None or google_oauth_client is not None):raise WorkflowError('NATIVE_GOOGLE_OAUTH_CONFIGURATION_CONFLICT',400)
        if (google_oauth_registry is not None or google_oauth_slots is not None or google_oauth_enabled) and access is None:raise WorkflowError('NATIVE_GOOGLE_OAUTH_HUMAN_AUTH_REQUIRED',400)
        if google_oauth_enabled and (google_oauth_directory is None or google_oauth_registry is None and google_oauth_slots is None):raise WorkflowError('NATIVE_GOOGLE_OAUTH_PROTECTED_REGISTRY_VAULT_REQUIRED',400)
        if (google_oauth_slots is None)!=(google_oauth_client is None):raise WorkflowError('NATIVE_GOOGLE_OAUTH_MOCK_INJECTION_REQUIRED',400)
        if google_oauth_slots is not None:
            from .google_oauth_operations import Slot,typed
            from app.google_oauth_protocol import GoogleOAuthTokenClient
            if not isinstance(google_oauth_slots,dict) or type(google_oauth_client) is not GoogleOAuthTokenClient or not google_oauth_client.mock:raise WorkflowError('NATIVE_GOOGLE_OAUTH_MOCK_INJECTION_REQUIRED',400)
            google_oauth_client.check()
            google_oauth_slots={key:typed(value,Slot) for key,value in google_oauth_slots.items()}
            if len(google_oauth_slots)>50 or any(key!=s.slot_id or s.target.workspace_id!=access.workspace_id for key,s in google_oauth_slots.items()):raise WorkflowError('NATIVE_GOOGLE_OAUTH_CONFIGURATION_INVALID',400)
        if google_oauth_directory is not None:
            from .official_account_tokens import protected_path
            directory=protected_path(google_oauth_directory,config.data_root)
            if directory.exists() and not directory.is_dir():raise WorkflowError('NATIVE_GOOGLE_OAUTH_CONFIGURATION_INVALID',400)
        if type(official_analytics_refresh_enabled) is not bool or official_analytics_refresh_enabled and not official_analytics_enabled:
            raise WorkflowError('NATIVE_OFFICIAL_REFRESH_CONFIGURATION_INVALID',400)
        if type(official_analytics_enabled) is not bool:raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_CONFIGURATION_INVALID',400)
        if official_analytics_enabled:
            if access is None or not (official_account_registry is not None and official_account_read_enabled or official_account_factories is not None):
                raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_PROTECTED_READ_RUNTIME_AND_AUTH_REQUIRED',400)
            if official_account_factories is not None:
                from .official_account_registry import AccountFactory
                if (not isinstance(official_account_factories,dict) or any(type(f) is not AccountFactory or not f.client.mock for f in official_account_factories.values())):
                    raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_MOCK_INJECTION_REQUIRED',400)
        if type(official_publish_enabled) is not bool:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_INVALID',400)
        if type(official_publish_queue_enabled) is not bool:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_CONFIGURATION_INVALID',400)
        if official_publish_queue_enabled and (access is None or official_publish_session_directory is None or not (official_publish_registry is not None and official_publish_enabled or official_publish_factories is not None)):
            raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_PROTECTED_RUNTIME_AND_AUTH_REQUIRED',400)
        if official_publish_registry is not None and official_publish_factories is not None:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_CONFLICT',400)
        if (official_publish_registry is not None or official_publish_factories is not None) and access is None:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_HUMAN_AUTH_REQUIRED',400)
        if official_publish_enabled and (access is None or official_publish_registry is None or official_publish_session_directory is None):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_PROTECTED_REGISTRY_VAULT_AND_HUMAN_AUTH_REQUIRED',400)
        if official_publish_factories is not None:
            from .official_publication_registry import PublishingFactory
            if not isinstance(official_publish_factories,dict) or any(type(f) is not PublishingFactory for f in official_publish_factories.values()):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_INVALID',400)
            if any(f.client.transport is None for f in official_publish_factories.values()):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_MOCK_INJECTION_REQUIRED',400)
        if official_publish_session_directory is not None:
            from .official_account_tokens import protected_path
            directory=protected_path(official_publish_session_directory,config.data_root)
            if directory.exists() and not directory.is_dir():raise WorkflowError('NATIVE_OFFICIAL_SESSION_CONFIGURATION_INVALID',400)
        if type(official_account_read_enabled) is not bool:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_CONFIGURATION_INVALID',400)
        if official_account_read_enabled and (access is None or official_account_registry is None):raise WorkflowError('NATIVE_OFFICIAL_PROTECTED_REGISTRY_AND_HUMAN_AUTH_REQUIRED',400)
        if official_account_registry is not None and official_account_factories is not None:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_CONFIGURATION_CONFLICT',400)
        if owner_rights_overrides and access is None:raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_HUMAN_AUTH_REQUIRED',400)
        if generation_api_enabled and (access is None or generation_registry is None):raise WorkflowError('NATIVE_GENERATION_PROTECTED_REGISTRY_AND_HUMAN_AUTH_REQUIRED',400)
        if generation_registry is not None and generation_factory is not None:raise WorkflowError('NATIVE_GENERATION_CONFIGURATION_CONFLICT',400)
        if trend_feed_enabled and (access is None or trend_feed_registry is None):raise WorkflowError('TREND_PROTECTED_FEED_REGISTRY_AND_HUMAN_AUTH_REQUIRED',400)
        if access is not None:
            from .access import NativeAccess
            if not isinstance(access, NativeAccess):
                raise WorkflowError('NATIVE_AUTH_CONFIGURATION_INVALID', 400)
            access.bind_root(config.data_root)
        else:
            from .backup import guard
            if guard(config.data_root / '.vf-auth-workspace.json').exists():
                raise WorkflowError('NATIVE_AUTH_REGISTRY_REQUIRED_FOR_BOUND_STATE', 503)
        from .official_account_registry import load as load_accounts
        loaded_accounts=load_accounts(official_account_registry,config.data_root,access.workspace_id if access is not None else 'wsp_native_local',owner_read_enabled=official_account_read_enabled) if official_account_registry is not None else official_account_factories
        loaded_google=None
        if google_oauth_registry is not None:
            from .google_oauth_registry import load as load_google
            loaded_google=load_google(google_oauth_registry,config.data_root,access.workspace_id)
        loaded_vision=None
        if has_vision_config:
            from .vision_credentials import NativeVisionKeyVault
            from .vision_registry import load as load_vision,NativeVisionFactory
            vault=NativeVisionKeyVault(official_vision_directory,config.data_root,access.workspace_id)
            if official_vision_factories is not None:
                if (type(official_vision_factories) is not dict or len(official_vision_factories)>8
                    or any(type(f) is not NativeVisionFactory or not f.mock or key!=f.profile.profile_id
                        or f.workspace!=access.workspace_id or f.root!=vault.root or f.vault.directory!=vault.directory
                        or f.operator_enabled is not official_vision_enabled for key,f in official_vision_factories.items())):
                    raise WorkflowError('NATIVE_OFFICIAL_VISION_MOCK_INJECTION_REQUIRED',400)
                loaded_vision=dict(official_vision_factories)
                for f in loaded_vision.values():f.check()
            else:loaded_vision=load_vision(official_vision_registry,vault,operator_enabled=official_vision_enabled)
        super().__init__(("127.0.0.1", port), Handler)
        self.config, self.store = config, Store(config.data_root)
        self.access = access
        self.session = secrets.token_urlsafe(32)
        self.csrf = secrets.token_urlsafe(32)
        self.connection_lock = threading.Lock()
        self.observer = observer or Observer()
        self.workers_enabled = start_worker
        self.runner = Runner(self.store, pipeline or Pipeline(config), observer=self.observer)
        from .intelligence_service import IntelligenceService
        self.intelligence = IntelligenceService(config,self.store,observer=self.observer)
        from .shot_preview import PreviewManager
        from .shot_ai_edit import ShotAIEdit
        self.previews=PreviewManager(config,self.store)
        self.shot_ai=ShotAIEdit(config,self.store)
        from .publications import NativePublications
        self.publications = NativePublications(self.store, REPO / 'packages/contracts/publishing-capabilities.json',
            workspace_id=access.workspace_id if access is not None else 'wsp_native_local')
        self.runner.publications = self.publications
        from .analytics import NativeAnalytics
        self.analytics=NativeAnalytics(self.store,self.publications)
        self.analytics_refresh=self.analytics.refresh
        self.runner.analytics=self.analytics
        from .official_accounts import NativeOfficialAccounts
        accounts=loaded_accounts
        if accounts and access is None and any(f.client.wire.network_enabled for f in accounts.values()):raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_HUMAN_AUTH_REQUIRED',400)
        self.official_accounts=NativeOfficialAccounts(self.store,workspace_id=self.publications.workspace_id,factories=accounts)
        self.runner.official_accounts=self.official_accounts
        from .official_publication_registry import load as load_publishing
        from .official_publications import NativeOfficialPublications
        from .official_publication_sessions import SessionVault
        from .official_publication_worker import NativeOfficialPublicationWorker
        publishing=load_publishing(official_publish_registry,self.store.root,self.publications.workspace_id,owner_enabled=official_publish_enabled) if official_publish_registry is not None else official_publish_factories
        self.official_publications=NativeOfficialPublications(self.store,self.publications,self.official_accounts,factories=publishing,identity_provider=self.official_publish_identity)
        self.google_oauth=None
        with self.store.transaction() as con:
            has_google_history=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='native_google_oauth_authorizations'").fetchone() is not None
        if loaded_google is not None or google_oauth_slots is not None or has_google_history:
            from .google_oauth_operations import NativeGoogleOAuthOperations
            from .google_oauth_vault import NativeGoogleOAuthVault
            from app.google_oauth_protocol import GoogleOAuthTokenClient
            registry,path,checksum=loaded_google if loaded_google is not None else (None,None,None)
            enabled=google_oauth_enabled and (registry.token_exchange_enabled if registry is not None else google_oauth_slots is not None)
            slots={s.slot_id:s for s in registry.slots} if registry is not None else google_oauth_slots
            vault=NativeGoogleOAuthVault(google_oauth_directory or config.secret_file.parent/'google-oauth-private',self.store.root,self.publications.workspace_id)
            self.google_oauth=NativeGoogleOAuthOperations(self.official_publications,vault,slots=slots,client=google_oauth_client or GoogleOAuthTokenClient(network_enabled=enabled),enabled=enabled,registry_file=path,registry_sha256=checksum)
            self.runner.google_oauth=self.google_oauth
        # Production network clients come only from the protected, explicitly enabled registry.
        self.official_publish_vault=SessionVault(self.official_publications,official_publish_session_directory)
        self.official_publish_worker=NativeOfficialPublicationWorker(self.official_publications,self.official_publish_vault)
        self.runner.official_publish_worker=self.official_publish_worker
        from .official_publication_queue import NativeOfficialPublicationQueue
        self.official_publish_queue=NativeOfficialPublicationQueue(self.official_publish_worker,enabled=official_publish_queue_enabled)
        self.runner.official_publish_queue=self.official_publish_queue
        from .official_analytics import NativeOfficialAnalytics
        self.official_analytics=NativeOfficialAnalytics(self.official_publications,enabled=official_analytics_enabled)
        self.runner.official_analytics=self.official_analytics
        from .official_analytics_refresh import NativeOfficialAnalyticsRefresh
        self.official_analytics_refresh=NativeOfficialAnalyticsRefresh(self.official_analytics,enabled=official_analytics_refresh_enabled)
        self.runner.official_analytics_refresh=self.official_analytics_refresh
        from .official_winners import NativeOfficialWinners
        self.official_winners=NativeOfficialWinners(self.official_analytics)
        from .official_learning import NativeOfficialLearning
        self.official_learning=NativeOfficialLearning(self.official_winners)
        from .trend_radar import NativeTrendRadar
        self.trends=NativeTrendRadar(self.intelligence,self.analytics,workspace=self.publications.workspace_id,
            providers=trend_providers,feed_registry=trend_feed_registry,owner_enabled=trend_feed_enabled,observer=self.observer)
        from .qualified_learning_feedback import NativeQualifiedLearningFeedback
        self.qualified_learning=NativeQualifiedLearningFeedback(self.official_learning,self.trends)
        self.trends.qualified_learning=self.qualified_learning
        self.intelligence.qualified_learning=self.qualified_learning
        self.store.qualified_learning=self.qualified_learning
        from .vision import NativeVision
        self.vision=NativeVision(self.store,config,workspace_id=self.publications.workspace_id)
        self.runner.vision=self.vision
        self.official_vision=None
        with self.store.transaction() as con:
            has_vision_history=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='native_official_vision_intents'").fetchone() is not None
        if loaded_vision is not None or has_vision_history:
            from .official_vision import NativeOfficialVision
            self.official_vision=NativeOfficialVision(self.vision,factories=loaded_vision,enabled=official_vision_enabled,identity_provider=self.official_publish_identity)
            self.runner.official_vision=self.official_vision
        from .source_variants import SourceVariants
        self.variants=SourceVariants(self.store,workspace_id=self.publications.workspace_id)
        from .narrated_variants import NativeNarratedVariants
        self.narrated_variants=NativeNarratedVariants(self.store,workspace_id=self.publications.workspace_id)
        from .bridge import NativeBridge
        self.bridge=NativeBridge(self.store,workspace_id=self.publications.workspace_id)
        self.bridge.attach_intelligence(self.intelligence.store)
        self.bridge.bind_qualified_sources(analytics=self.official_analytics,winner=self.official_winners,learning=self.official_learning,projection=self.qualified_learning)
        from .rights import NativeRights
        self.rights=NativeRights(self.store,workspace_id=self.publications.workspace_id)
        from .rights_override import NativeRightsOverrides
        self.rights_overrides=NativeRightsOverrides(self.store,workspace_id=self.publications.workspace_id,enabled=owner_rights_overrides)
        from .narration_rights import NativeNarrationRights
        self.narration_rights=NativeNarrationRights(self.store,workspace_id=self.publications.workspace_id,enabled=owner_rights_overrides)
        from .stock import NativeStock
        from .stock_registry import load as load_stock
        if stock_api_enabled and stock_registry is None:raise WorkflowError('NATIVE_STOCK_REGISTRY_REQUIRED',400)
        if stock_registry is not None and stock_factories is not None:raise WorkflowError('NATIVE_STOCK_CONFIGURATION_CONFLICT',400)
        factories=load_stock(stock_registry,self.store.root,self.publications.workspace_id,owner_enabled=stock_api_enabled) if stock_registry is not None else stock_factories
        self.stock=NativeStock(self.store,config,workspace_id=self.publications.workspace_id,factories=factories)
        from .generation_queue import NativeGenerationQueue
        from .generation_worker import NativeGenerationWorker
        from .generation_registry import load as load_generation
        generation=load_generation(generation_registry,self.store.root,self.publications.workspace_id,owner_enabled=generation_api_enabled) if generation_registry is not None else generation_factory
        self.generation=NativeGenerationWorker(NativeGenerationQueue(self.store,workspace_id=self.publications.workspace_id,factory=generation),config)
        from .studio_media_planner import NativeStudioMediaPlanner
        from .generation_routes import providers as generation_providers
        self.media_planner=NativeStudioMediaPlanner(self.store,config,workspace_id=self.publications.workspace_id,
            providers=lambda:{'workspace_id':self.publications.workspace_id,'stock':self.stock.providers(),'generation':generation_providers(self.generation)})
        from .studio_media_resolution import NativeStudioMediaResolution
        self.media_resolution=NativeStudioMediaResolution(self.media_planner,self.generation,self.stock)
        if bridge_auth_registry is not None:self.bridge.load_auth_registry(bridge_auth_registry)
        if bridge_http_enabled and bridge_webhook_registry is None:raise WorkflowError('NATIVE_BRIDGE_WEBHOOK_REGISTRY_REQUIRED',400)
        if bridge_webhook_registry is not None:self.bridge.load_webhook_registry(bridge_webhook_registry,owner_http_enabled=bridge_http_enabled)
        if start_worker:
            self.trends.start()
            self.generation.start(self.observer)
            self.stock.start(self.observer)
            self.bridge.start(self.observer)
            self.runner.start()
            self.intelligence.start()

    def official_publish_identity(self):
        if self.access is None:return None
        self.access.refresh();return self.access.verifier

    def server_close(self):
        self.trends.close()
        self.generation.close()
        self.stock.close()
        self.bridge.close()
        self.runner.stop.set()
        self.runner.wake.set()
        self.previews.close()
        self.intelligence.stop.set()
        self.intelligence.wake.set()
        if self.intelligence.thread.is_alive():
            self.intelligence.thread.join(timeout=2)
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass  # No body, tokens, user content or provider error details in HTTP logs.

    def send_response(self, code, message=None):
        self.response_status = code
        super().send_response(code, message)

    def boundary(self, write=False, session=True):
        port = self.server.server_port
        host = self.headers.get("Host", "")
        if host not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            raise WorkflowError("LOOPBACK_HOST_REQUIRED", 403)
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise WorkflowError("CROSS_SITE_REQUEST_BLOCKED", 403)
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{host}":
            raise WorkflowError("SAME_ORIGIN_REQUIRED", 403)
        if session:
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get("Cookie", ""))
            except Exception:
                raise WorkflowError("LOCAL_SESSION_REQUIRED", 401) from None
            token = cookies.get("vf_native_session")
            if self.server.access is not None:
                self.auth_session = self.server.access.authenticate(token.value if token else None,
                    csrf=self.headers.get('X-VF-CSRF'), write=write)
                self.auth_permission = self.server.access.authorize(self.auth_session, self.command, self.path)
            elif token is None or not secrets.compare_digest(token.value, self.server.session):
                raise WorkflowError("LOCAL_SESSION_REQUIRED", 401)
        if write and self.server.access is None and not secrets.compare_digest(self.headers.get("X-VF-CSRF", ""), self.server.csrf):
            raise WorkflowError("CSRF_TOKEN_REQUIRED", 403)

    def reply(self, value, status=200, headers=None):
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.common("application/json; charset=utf-8", len(raw), headers)
        self.end_headers()
        self.wfile.write(raw)

    def common(self, content_type, size, headers=None):
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        if self.close_connection:
            self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if getattr(self, 'request_id', None):
            self.send_header('X-Request-ID', self.request_id)
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; media-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for name, value in (headers or {}).items():
            self.send_header(name, value)

    def file(self, path, *, video=False, headers=None):
        if not path.is_file():
            raise WorkflowError("ARTIFACT_NOT_FOUND", 404)
        size, start, end = path.stat().st_size, 0, path.stat().st_size - 1
        request_range = self.headers.get("Range") if video else None
        status, extra = 200, dict(headers or {})
        if video:
            extra["Accept-Ranges"] = "bytes"
        if request_range:
            match = re.fullmatch(r"bytes=(\d+)-(\d*)", request_range)
            if not match:
                raise WorkflowError("INVALID_VIDEO_RANGE", 416)
            start = int(match[1])
            end = min(int(match[2]), end) if match[2] else end
            if start > end or start >= size:
                raise WorkflowError("INVALID_VIDEO_RANGE", 416)
            status = 206
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        self.send_response(status)
        self.common(mimetypes.guess_type(path)[0] or "application/octet-stream", end - start + 1, extra)
        self.end_headers()
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = end - start + 1
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def dispatch_get(self):
        path = self.path.split("?", 1)[0]
        if path=='/oauth/google/callback':
            from .google_oauth_callback import dispatch
            return dispatch(self)
        if path.startswith('/v1/'):
            from .bridge_routes import dispatch
            return dispatch(self)
        if self.server.access is not None and path in ('/', '/native.html', '/production', '/intelligence', '/trends', '/settings/assemblyai'):
            try:
                self.boundary(session=True)
            except WorkflowError as error:
                if error.status == 401:
                    return self.reply({'code': 'NATIVE_AUTH_SESSION_REQUIRED'}, 303, {'Location': '/login'})
                raise
        self.boundary(session=path.startswith("/api/") and path != '/api/health'
            and (path != '/api/session' or self.server.access is not None))
        narration_route=re.fullmatch(r'/api/projects/([a-f0-9]{32})/narration(?:/([a-f0-9]{32})/audio)?',self.path)
        if narration_route:
            from .narration import page,load,load_reference
            project_id,job_id=narration_route.groups()
            if job_id:
                with self.server.store.transaction() as con:
                    project=self.server.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone())
                    ref=project['document'].get('prepared_narration')
                    if isinstance(ref,dict) and 'derivation' in ref and ref.get('job_id')==job_id:
                        _,out,_=load_reference(self.server.store,con,project_id,project['document'])
                    else:_,out,_=load(self.server.store,con,project_id,job_id)
                return self.file(out/'voice.wav',headers={'Cache-Control':'no-store'})
            return self.reply(page(self.server.store,project_id),headers={'Cache-Control':'no-store'})
        if path=='/api/narrated/variant-profiles' or re.fullmatch(r'/api/projects/[a-f0-9]{32}/narrated-variants',path):
            from .narrated_variant_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/media-plans',path):
            from .studio_media_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/media-resolutions(?:/nmr_[a-f0-9]{32})?',path):
            from .studio_media_resolution_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        generation_file=re.fullmatch(r'/api/projects/([a-f0-9]{32})/generation/([a-f0-9]{32})/file',path)
        if generation_file:
            if '?' in self.path:raise WorkflowError('NATIVE_GENERATION_PAGE_INVALID',400)
            file,asset=self.server.generation.asset_file(*generation_file.groups())
            return self.file(file,video=asset['kind']=='video')
        if path=='/api/generation/providers' or re.fullmatch(r'/api/projects/[a-f0-9]{32}/generation(?:/[a-f0-9]{32})?',path):
            from .generation_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        stock_file=re.fullmatch(r'/api/projects/([a-f0-9]{32})/stock/(nstk_[a-f0-9]{32})/file',path)
        if stock_file:
            if '?' in self.path:raise WorkflowError('NATIVE_STOCK_PAGE_INVALID',400)
            file,asset=self.server.stock.asset_file(*stock_file.groups())
            return self.file(file,video=asset['kind']=='video')
        if path=='/api/stock/providers' or re.fullmatch(r'/api/projects/[a-f0-9]{32}/stock(?:/nstk_[a-f0-9]{32})?',path):
            from .stock_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        if path.startswith('/api/bridge/'):
            from .bridge_operator_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/rights',path):
            from .rights_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/rights-overrides',path):
            from .rights_override_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/narration-rights',path):
            from .narration_rights_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        if path=='/api/connections/official-accounts' or re.fullmatch(r'/api/projects/[a-f0-9]{32}/account-checks(?:/nack_[a-f0-9]{32})?',path):
            from .official_account_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        if path=='/api/connections/google-oauth' or re.fullmatch(r'/api/projects/[a-f0-9]{32}/google-oauth/(?:authorizations|operations)(?:/(?:ngoa_|ngop_)[a-f0-9]{32})?',path):
            from .google_oauth_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        if path=='/api/connections/official-vision' or re.fullmatch(r'/api/projects/[a-f0-9]{32}/official-vision(?:/nvoi_[a-f0-9]{32})?',path):
            from .official_vision_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        if path=='/api/connections/official-analytics-refresh' or re.fullmatch(r'/api/projects/[a-f0-9]{32}/official-analytics-refresh(?:/noap_[a-f0-9]{32})?',path):
            from .official_analytics_refresh_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        if path=='/api/connections/official-analytics' or re.fullmatch(r'/api/projects/[a-f0-9]{32}/official-analytics(?:/noas_[a-f0-9]{32}|/source/nopu_[a-f0-9]{32})?',path):
            from .official_analytics_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        if path=='/api/connections/official-winners' or re.fullmatch(r'/api/projects/[a-f0-9]{32}/official-winners(?:/nowa_[a-f0-9]{32}|/source/noas_[a-f0-9]{32})?',path):
            from .official_winner_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        if path=='/api/connections/official-learning' or re.fullmatch(r'/api/projects/[a-f0-9]{32}/official-learning(?:/nols_[a-f0-9]{32}|/source/nowa_[a-f0-9]{32})?',path):
            from .official_learning_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        if path == '/healthz':
            return self.reply({'schema': 'vf-native-health-v1', 'status': 'alive', 'scope': 'http_process'})
        if path == '/readyz':
            value, status = readiness(self.server)
            return self.reply(value, status)
        if path.startswith("/api/intelligence/"):
            from .intelligence_routes import get
            return self.reply(get(self,path))
        if path.startswith('/api/trends/'):
            from .trend_radar_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/vision(?:/nvis_[a-f0-9]{32})?',path):
            from .vision_routes import get
            return self.reply(get(self,path))
        if path=='/api/auto-edit/variant-profiles' or re.fullmatch(r'/api/projects/[a-f0-9]{32}/variants',path):
            from .variant_routes import get
            return self.reply(get(self,path))
        if path in ('/api/analytics/providers','/api/analytics/overview') or re.fullmatch(r'/api/projects/[a-f0-9]{32}/analytics(?:/nasy_[a-f0-9]{32})?',path) or re.fullmatch(r'/api/projects/[a-f0-9]{32}/analytics-refresh(?:/narp_[a-f0-9]{32})?',path):
            from .analytics_routes import get
            return self.reply(get(self,path))
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/publications(?:/npub_[a-f0-9]{32})?', path):
            from .publication_routes import get
            return self.reply(get(self, path))
        if path=='/api/connections/official-publish-queue' or re.fullmatch(r'/api/projects/[a-f0-9]{32}/official-publications/nopu_[a-f0-9]{32}/queue(?:/nopq_[a-f0-9]{32})?',path):
            from .official_publication_queue_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        if path=='/api/connections/official-publishing' or re.fullmatch(r'/api/projects/[a-f0-9]{32}/official-publications(?:/nopu_[a-f0-9]{32}(?:/state)?)?',path):
            from .official_publication_routes import get
            return self.reply(get(self,path),headers={'Cache-Control':'no-store'})
        if path.startswith('/api/production/'):
            from .production_routes import get
            thumbnail_match=re.fullmatch(r'/api/production/videos/([0-9a-f]{32})/thumbnail',path)
            if thumbnail_match:
                from .production_thumbnail import thumbnail
                return self.file(thumbnail(self.server.config,get(self,'/api/production/videos/'+thumbnail_match[1])))
            result=get(self,path)
            if re.fullmatch(r'/api/production/videos/[0-9a-f]{32}',path):
                return self.file(Path(result['path']),video=True)
            return self.reply(result)
        if path=='/api/auto-edit/subtitle-templates':
            from app.subtitle_templates import template_catalog
            return self.reply(template_catalog())
        if path=='/api/channel-profiles':
            from .channel_profiles import catalog
            return self.reply(catalog())
        cost_route = re.fullmatch(r'/api/projects/([0-9a-f]{32})/cost-summary', path)
        if cost_route:
            from .costs import CostLedger
            return self.reply(CostLedger(self.server.store).summary(cost_route[1]))
        analysis_route = re.fullmatch(r'/api/projects/([0-9a-f]{32})/auto-edit', path)
        if analysis_route:
            from .auto_edit_analysis import view
            return self.reply(view(self.server.store, analysis_route[1]))
        frame_route=re.fullmatch(r'/api/projects/([0-9a-f]{32})/media-frames(?:/(mfr_[a-f0-9]{24})/image)?',path)
        if frame_route:
            from .media_frame_analysis import view,image_path
            identifier,frame_id=frame_route.groups()
            if frame_id:return self.file(image_path(self.server.store,identifier,frame_id))
            return self.reply(view(self.server.store,identifier))
        source_timeline_route = re.fullmatch(r'/api/projects/([0-9a-f]{32})/auto-edit/timeline', path)
        shorts_route = re.fullmatch(r'/api/projects/([0-9a-f]{32})/auto-edit/shorts',path)
        if shorts_route:
            from .source_shorts import view
            return self.reply(view(self.server.store,shorts_route[1]))
        if source_timeline_route:
            from .auto_edit_timeline import view
            return self.reply(view(self.server.store, source_timeline_route[1]))
        shot_route=re.fullmatch(r'/api/projects/([0-9a-f]{32})/(shots|preview|preview/video)',path)
        if shot_route:
            identifier,action=shot_route.groups()
            if action=='shots': return self.reply(self.server.store.shot_view(identifier))
            if action=='preview': return self.reply(self.server.previews.status(identifier))
            version=parse_qs(self.path.partition('?')[2]).get('version',[''])[0]
            return self.file(self.server.previews.video_path(identifier,version),video=True)
        if path == "/api/session":
            access = self.server.access.public(self.auth_session) if self.server.access is not None else {
                'mode': 'loopback_owner', 'role': 'owner', 'workspace_id': None,
                'permissions': ['read', 'edit', 'review', 'manage']}
            csrf = self.auth_session.csrf if self.server.access is not None else self.server.csrf
            headers = None if self.server.access is not None else {"Set-Cookie": f"vf_native_session={self.server.session}; HttpOnly; SameSite=Strict; Path=/"}
            return self.reply({"csrf": csrf, 'access': access, "capabilities": {"native_shot_studio": True, "production_intelligence": True, "voice_quality_selection": True,
                "native_studio_ux": True, "asset_library": True, "north_star_quality": True, "native_auto_edit_analysis": True,
                "native_source_timeline":True,"native_media_frame_analysis":True,"native_cost_ledger":True,
                "native_publication_review":True,"native_live_publishing":False,"native_official_publication_review":self.server.access is not None,"native_analytics_review":True,
                "native_official_analytics":False,"native_vision_review":True,"native_official_vision":False,"native_source_variants":True,"native_channel_profiles":True,"native_bridge_operator":True,"native_rights_review":True,"native_stock_media":True,"native_generation_media":True,"native_storyboard_media_planner":True,"native_storyboard_media_resolution":True,"native_narration_preparation":True,"native_narrated_workflow":True,"native_trend_radar":True,"native_owner_rights_override_review":True,"native_narration_rights_review":True,"native_source_music_loop_crossfade":True,"native_analytics_refresh":True,"native_narrated_variants":True,"native_narrated_music_loop":True,"native_official_account_review":True}}, headers=headers)
        if path == "/api/health":
            return self.reply({"status": "ready", "model": "gpt-6-luna", "voice": "Thùy Dung", "resolution": "1080x1920", "human_review_required": True})
        if path == "/api/defaults":
            return self.reply({"prompt": (LOCKS / "accepted-prompt.txt").read_text(encoding="utf-8")})
        if path == "/api/projects":
            return self.reply(self.server.store.list(include_archived=parse_qs(self.path.partition("?")[2]).get("archived")==["include"]))
        if path == '/api/assets':
            params=parse_qs(self.path.partition('?')[2],keep_blank_values=True)
            if set(params)-{'kind','q','page','page_size'} or any(len(values)!=1 for values in params.values()):
                raise WorkflowError('ASSET_LIBRARY_FILTER_INVALID',400)
            try:
                page=int(params.get('page',['1'])[0]); size=int(params.get('page_size',['24'])[0])
            except ValueError:
                raise WorkflowError('ASSET_LIBRARY_PAGE_INVALID',400) from None
            return self.reply(library_assets(self.server.store,kind=params.get('kind',['all'])[0],query=params.get('q',[''])[0],page=page,page_size=size))
        library_route=re.fullmatch(r'/api/assets/([A-Za-z0-9][A-Za-z0-9_.-]{0,99})/(thumbnail|file)',path)
        if library_route:
            source,video=library_file(self.server.store,library_route[1],thumbnail=library_route[2]=='thumbnail')
            return self.file(source,video=video)
        if path == "/api/runtime-status":
            ready=verify_runtime(self.server.config,full=False)
            return self.reply({"tts":ready,"ffmpeg_available":True,"openai_key_saved":self.server.config.secret_file.is_file(),
                              "openai_live_check_performed":False,"assemblyai":assemblyai_connection.status(self.server.config)})
        if path == "/api/brand-templates":
            from .branding import catalog
            return self.reply(catalog(include_landscape=parse_qs(self.path.partition('?')[2]).get('formats')==['all']))
        if path == '/api/voice-quality':
            from .voice_quality import catalog
            return self.reply(catalog())
        if path == "/api/connections/assemblyai":
            return self.reply(assemblyai_connection.status(self.server.config))
        versions = re.fullmatch(r"/api/projects/([0-9a-f]{32})/versions", path)
        if versions:
            return self.reply(self.server.store.versions(versions[1]))
        logs = re.fullmatch(r"/api/jobs/([0-9a-f]{32})/logs", path)
        if logs:
            job = self.server.store.get_job(logs[1])
            with self.server.store.transaction() as con:
                rows = con.execute("SELECT payload,created_at FROM events WHERE action='job_step' AND project_id=? AND json_extract(payload,'$.job_id')=? ORDER BY id", (job["project_id"], job["id"]))
                return self.reply([{**json.loads(r["payload"]), "created_at": r["created_at"]} for r in rows])
        match = re.fullmatch(r"/api/projects/([0-9a-f]{32})/media/([0-9a-f]{32}\.(?:jpg|mp4))(/thumbnail)?", path)
        if match:
            project = self.server.store.get(match[1])
            asset = next((a for a in project_assets(project["document"]) if a["id"] == match[2]), None)
            if asset is None:
                raise WorkflowError("MEDIA_NOT_IN_PROJECT", 404)
            identifier = asset.get("thumbnail_id", asset["id"]) if match[3] else asset["id"]
            return self.file(media_path(self.server.config, identifier), video=not match[3] and asset["kind"] == "video")
        match = re.fullmatch(r"/api/projects/([0-9a-f]{32})(/image)?", path)
        if match:
            project = self.server.store.get(match[1])
            if match[2]:
                asset = project["document"]["asset"]
                if not asset:
                    raise WorkflowError("IMAGE_NOT_FOUND", 404)
                return self.file(self.server.config.data_root / "assets" / asset["id"])
            return self.reply(project)
        artifact = re.fullmatch(r"/api/jobs/([0-9a-f]{32})/artifacts", path)
        if artifact:
            from .hardening import Artifacts
            job=self.server.store.get_job(artifact[1])
            checkpoint=Artifacts(self.server.config.data_root/"jobs"/job["id"],job).load("render")
            if not checkpoint: raise WorkflowError("RENDER_ARTIFACTS_NOT_READY",404)
            return self.reply({"job_id":job["id"],"project_id":job["project_id"],"revision":job["revision"],"artifacts":checkpoint["artifacts"],
                              "qc":job["result"]["qc"],"final_review":job["final_review"],"output_directory":str(self.server.config.data_root/"jobs"/job["id"])})
        match = re.fullmatch(r"/api/jobs/([0-9a-f]{32})/(video|final)", path)
        if match:
            if match[2]=="final":
                job=self.server.store.final_video(match[1])
            else:
                with self.server.store.transaction() as con:
                    job,_=self.server.store.verified_render(match[1],con)
            return self.file(self.server.config.data_root / "jobs" / job["id"] / "final.mp4", video=True)
        static = {"/": "native.html", "/native.html": "native.html", "/native.css": "native.css", "/native.mjs": "native.mjs",
                  "/intelligence":"intelligence.html", "/intelligence.mjs":"intelligence.mjs",
                  "/settings/assemblyai": "assemblyai.html", "/assemblyai.mjs": "assemblyai.mjs"}
        static.update({'/shot-studio.mjs':'shot-studio.mjs','/shot-studio.css':'shot-studio.css',
                       '/production':'production.html','/production.mjs':'production.mjs','/production.css':'production.css'})
        static.update({name:name[1:] for name in ('/asset-picker.mjs','/video-preview.mjs','/studio-workspace.css','/studio-shell.mjs','/studio-shell.css','/native-auto-edit.mjs','/native-auto-edit.css')})
        static.update({name:name[1:] for name in ('/native-source-editor.mjs','/native-source-editor.css',
            '/native-source-broll.mjs','/native-media-frames.mjs','/studio-utils.mjs','/waveform.mjs','/timeline-history.mjs')})
        static['/native-costs.mjs'] = 'native-costs.mjs'
        static['/native-publications.mjs'] = 'native-publications.mjs'
        static['/native-analytics.mjs'] = 'native-analytics.mjs'
        static['/native-analytics-refresh.mjs'] = 'native-analytics-refresh.mjs'
        static['/native-vision.mjs'] = 'native-vision.mjs'
        static['/native-rights.mjs'] = 'native-rights.mjs'
        static['/native-rights-override.mjs'] = 'native-rights-override.mjs'
        static['/native-narration-rights.mjs'] = 'native-narration-rights.mjs'
        static['/native-stock.mjs'] = 'native-stock.mjs'
        static['/native-generation.mjs'] = 'native-generation.mjs'
        static['/native-media-resolution.mjs'] = 'native-media-resolution.mjs'
        static['/native-media-planner.mjs'] = 'native-media-planner.mjs'
        static['/native-narration.mjs'] = 'native-narration.mjs'
        static.update({'/trends':'trend-radar.html','/trend-radar.mjs':'trend-radar.mjs','/trend-radar.css':'trend-radar.css'})
        static['/native-variants.mjs'] = 'native-variants.mjs'
        static['/native-narrated-variants.mjs'] = 'native-narrated-variants.mjs'
        static['/native-official-accounts.mjs'] = 'native-official-accounts.mjs'
        static['/native-google-oauth.mjs'] = 'native-google-oauth.mjs'
        static['/native-official-publications.mjs'] = 'native-official-publications.mjs'
        static['/native-official-publication-queue.mjs'] = 'native-official-publication-queue.mjs'
        static['/native-official-analytics.mjs'] = 'native-official-analytics.mjs'
        static['/native-official-refresh.mjs'] = 'native-official-refresh.mjs'
        static['/native-official-winners.mjs'] = 'native-official-winners.mjs'
        static['/native-official-learning.mjs'] = 'native-official-learning.mjs'
        static['/native-qualified-learning.mjs'] = 'native-qualified-learning.mjs'
        static['/native-channel-profiles.mjs'] = 'native-channel-profiles.mjs'
        static['/native-bridge.mjs']='native-bridge.mjs'
        static.update({'/login': 'native-login.html', '/native-login.mjs': 'native-login.mjs',
                       '/native-access.mjs': 'native-access.mjs', '/native-access.css': 'native-access.css'})
        if path in static:
            return self.file(REPO / "apps/studio-web" / static[path])
        raise WorkflowError("ROUTE_NOT_FOUND", 404)

    def read_body(self, max_bytes=22 * 1024 * 1024):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise WorkflowError("INVALID_BODY_LENGTH", 400) from None
        if not 1 <= length <= max_bytes or self.headers.get("Transfer-Encoding") or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise WorkflowError("JSON_BODY_REQUIRED_MAX_22MB", 400)
        try:
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError()
            if getattr(self, 'auth_session', None) is not None and ('reviewer' in body or self.auth_permission == 'review'):
                body['reviewer'] = self.auth_session.principal.token_id
            return body
        except ValueError:
            raise WorkflowError("INVALID_JSON_BODY", 400) from None

    def dispatch_post(self):
        if self.path.startswith('/v1/'):
            from .bridge_routes import dispatch
            return dispatch(self)
        if self.path == '/api/login':
            self.boundary(session=False)
            if self.server.access is None:
                raise WorkflowError('NATIVE_AUTH_NOT_CONFIGURED', 404)
            body = self.read_body(max_bytes=2048)
            if set(body) != {'token'}:
                raise WorkflowError('NATIVE_AUTH_LOGIN_FIELDS_INVALID', 400)
            cookie, session = self.server.access.login(body['token'])
            return self.reply({'csrf': session.csrf, 'access': self.server.access.public(session)}, headers={
                'Set-Cookie': f'vf_native_session={cookie}; HttpOnly; SameSite=Strict; Path=/; Max-Age={self.server.access.session_ttl}'})
        self.boundary(write=True)
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/official-vision(?:/nvoi_[a-f0-9]{32}/(?:process|cancel))?',self.path):
            from .official_vision_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=16000)),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/google-oauth/(?:authorizations(?:/ngoa_[a-f0-9]{32}/(?:authorization-url|exchange|cancel))?|refresh)',self.path):
            from .google_oauth_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=16000)),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/(?:media-plans/nmp_[a-f0-9]{32}/resolve/(?:generate|search|download)|media-resolutions/nmr_[a-f0-9]{32}/import)',self.path):
            from .studio_media_resolution_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=16384)),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/media-plans(?:/nmp_[a-f0-9]{32}/(?:select|revise|apply))?',self.path):
            from .studio_media_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=16384)),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/generation(?:/[a-f0-9]{32}/(?:cancel|recover|import))?',self.path):
            from .generation_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=16384)),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/stock/(search|download|nstk_[a-f0-9]{32}/(?:cancel|import))',self.path):
            from .stock_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=16384)),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/rights/[a-f0-9]{32}\.(jpg|png|mp4|wav|music\.wav)',self.path):
            from .rights_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=16384)),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/rights-overrides/[a-f0-9]{32}\.(jpg|png|mp4|wav|music\.wav)',self.path):
            from .rights_override_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=16384)),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/narration-rights',self.path):
            from .narration_rights_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=16384)),headers={'Cache-Control':'no-store'})
        if self.path.startswith('/api/bridge/'):
            from .bridge_operator_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=8192)),headers={'Cache-Control':'no-store'})
        if self.path == '/api/logout':
            if self.server.access is None:
                raise WorkflowError('NATIVE_AUTH_NOT_CONFIGURED', 404)
            cookies = SimpleCookie(); cookies.load(self.headers.get('Cookie', ''))
            self.server.access.logout(cookies['vf_native_session'].value)
            return self.reply({'status': 'signed_out'}, headers={
                'Set-Cookie': 'vf_native_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
        if self.path.startswith("/api/intelligence/"):
            from .intelligence_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=100000)))
        if self.path.startswith('/api/trends/'):
            from .trend_radar_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=16000)),headers={'Cache-Control':'no-store'})
        narration_route=re.fullmatch(r'/api/projects/([a-f0-9]{32})/narration/([a-f0-9]{32})/apply',self.path)
        if narration_route:
            from .narration import apply
            return self.reply(apply(self.server.store,*narration_route.groups(),self.read_body(max_bytes=4096)),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/vision(?:/nvis_[a-f0-9]{32}/(?:process|cancel))?',self.path):
            from .vision_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=100000)))
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/variants',self.path):
            from .variant_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=20000)))
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/narrated-variants',self.path):
            from .narrated_variant_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=20000)),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/analytics(?:/nasy_[a-f0-9]{32}/(?:process|cancel))?',self.path) or re.fullmatch(r'/api/projects/[a-f0-9]{32}/analytics-refresh(?:/tick|/narp_[a-f0-9]{32}/state)?',self.path):
            from .analytics_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=100000)))
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/official-accounts/npac_[a-f0-9]{32}/verify',self.path):
            from .official_account_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=20000)),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/official-analytics-refresh(?:/noap_[a-f0-9]{32}/cancel)?',self.path):
            from .official_analytics_refresh_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=16000)),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/official-analytics(?:/noas_[a-f0-9]{32}/cancel)?',self.path):
            from .official_analytics_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=16000)),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/official-winners',self.path):
            from .official_winner_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=40000)),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/official-learning',self.path):
            from .official_learning_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=20000)),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/official-publications/nopu_[a-f0-9]{32}/queue(?:/nopq_[a-f0-9]{32}/cancel)?',self.path):
            from .official_publication_queue_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=16000)),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/official-publications(?:/nopu_[a-f0-9]{32}/(?:approve|renew|revoke|cancel|step|poll))?',self.path):
            from .official_publication_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=16000)),headers={'Cache-Control':'no-store'})
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/publications(?:/npub_[a-f0-9]{32}/(?:approve|cancel|dry-run))?', self.path):
            from .publication_routes import post
            return self.reply(post(self, self.path, self.read_body(max_bytes=100000)))
        if self.path.startswith('/api/production/'):
            from .production_routes import post
            return self.reply(post(self,self.path,self.read_body(max_bytes=100000)))
        source_timeline_route = re.fullmatch(r'/api/projects/([0-9a-f]{32})/auto-edit/timeline', self.path)
        broll_route = re.fullmatch(r'/api/projects/([0-9a-f]{32})/auto-edit/broll', self.path)
        shorts_route = re.fullmatch(r'/api/projects/([0-9a-f]{32})/auto-edit/shorts',self.path)
        if shorts_route:
            from .source_shorts import create
            body=self.read_body(max_bytes=100000)
            if set(body)!={'revision','payload'} or type(body.get('revision')) is not int:
                raise WorkflowError('AUTO_SHORTS_REQUEST_INVALID',400)
            return self.reply(create(self.server.store,self.server.config,shorts_route[1],body['revision'],body['payload']))
        if broll_route:
            from . import source_broll
            body = self.read_body(max_bytes=100000)
            if set(body) != {'revision','action','payload'} or type(body.get('revision')) is not int or body.get('action') not in {'create','select','apply'}:
                raise WorkflowError('AUTO_EDIT_BROLL_REQUEST_INVALID',400)
            action = {'create':source_broll.create,'select':source_broll.select,'apply':source_broll.apply}[body['action']]
            return self.reply(action(self.server.store,self.server.config,broll_route[1],body['revision'],body['payload']))
        if source_timeline_route:
            from .auto_edit_timeline import create, edit, restore
            from .source_linked_edit import edit as linked_edit
            from .source_settings import configure
            from .source_reframe import apply as reframe
            body = self.read_body(max_bytes=100000)
            if set(body) != {'revision','action','payload'} or type(body.get('revision')) is not int or body.get('action') not in {'create','edit','restore','linked_edit','configure','reframe'}:
                raise WorkflowError('AUTO_EDIT_TIMELINE_REQUEST_INVALID', 400)
            action = {'create':create,'edit':edit,'restore':restore,'linked_edit':linked_edit,'configure':configure,'reframe':reframe}[body['action']]
            return self.reply(action(self.server.store, source_timeline_route[1], body['revision'], body['payload']))
        analysis_route = re.fullmatch(r'/api/projects/([0-9a-f]{32})/auto-edit/(ana_[a-f0-9]{24})/transcript', self.path)
        if analysis_route:
            from .auto_edit_analysis import edit_transcript
            body = self.read_body(max_bytes=100000)
            if set(body) != {'revision', 'edit'} or type(body.get('revision')) is not int:
                raise WorkflowError('AUTO_EDIT_TRANSCRIPT_REQUEST_INVALID', 400)
            return self.reply(edit_transcript(self.server.store, analysis_route[1], body['revision'], analysis_route[2], body['edit']))
        shot_route=re.fullmatch(r'/api/projects/([0-9a-f]{32})/(shots|preview|ai-edit|asset-association|script-review)',self.path)
        if shot_route:
            identifier,action=shot_route.groups(); body=self.read_body(max_bytes=100000)
            revision=body.get('revision')
            if type(revision) is not int: raise WorkflowError('REVISION_REQUIRED',400)
            if action=='shots': return self.reply(self.server.store.mutate_shots(identifier,revision,body.get('operation')))
            if action=='preview':
                if body.get('action')=='generate': return self.reply(self.server.previews.generate(identifier,revision))
                if body.get('action')=='cancel': return self.reply(self.server.previews.cancel(identifier,revision))
                raise WorkflowError('PREVIEW_ACTION_REQUIRED',400)
            if action=='ai-edit':
                return self.reply(self.server.shot_ai.suggest(identifier,revision,body.get('shot_id'),body.get('instruction'),body.get('request_key')))
            if action=='asset-association':
                from .asset_association import mutate
                return self.reply(mutate(self.server.store,identifier,revision,body.get('asset_id'),body.get('action'),body.get('tags'),asset_ids=body.get('asset_ids')))
            return self.reply(self.server.store.review_script(identifier,revision,body.get('reviewer'),body.get('acknowledged'),body.get('script_sha256')))
        if self.path == "/api/connections/assemblyai":
            body = self.read_body(max_bytes=2048)
            if set(body) not in ({"key"}, {"verify_saved"}) or ("verify_saved" in body and body["verify_saved"] is not True):
                raise WorkflowError("ASSEMBLYAI_CONNECTION_BODY_INVALID", 400)
            if "key" in body and not isinstance(body["key"], str):
                raise WorkflowError("ASSEMBLYAI_KEY_FORMAT_INVALID", 400)
            with self.server.connection_lock:
                with self.server.store.transaction() as con:
                    if con.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','retrying')").fetchone()[0]:
                        raise WorkflowError("ASSEMBLYAI_CONNECTION_WAIT_FOR_JOBS", 409)
                return self.reply(assemblyai_connection.connect(self.server.config, body.get("key")))
        upload_match = re.fullmatch(r"/api/projects/([0-9a-f]{32})/media", self.path)
        if upload_match:
            return self.upload_media(upload_match[1])
        document_match = re.fullmatch(r"/api/projects/([0-9a-f]{32})/documents", self.path)
        if document_match:
            return self.upload_document(document_match[1])
        music_match = re.fullmatch(r"/api/projects/([0-9a-f]{32})/music",self.path)
        if music_match:
            return self.upload_music(music_match[1])
        body = self.read_body()
        resume = re.fullmatch(r"/api/jobs/([0-9a-f]{32})/resume", self.path)
        if resume:
            result = self.server.store.resume(resume[1])
            self.server.runner.wake.set()
            return self.reply(result)
        final_review=re.fullmatch(r"/api/jobs/([0-9a-f]{32})/review",self.path)
        if final_review:
            if type(body.get("revision")) is not int: raise WorkflowError("REVISION_REQUIRED",400)
            return self.reply(self.server.store.review_render(final_review[1],body["revision"],body.get("reviewer"),body.get("acknowledged"),body.get("decision"),body.get("note","")))
        output_folder=re.fullmatch(r"/api/jobs/([0-9a-f]{32})/open-folder",self.path)
        if output_folder:
            if body: raise WorkflowError("OUTPUT_FOLDER_BODY_MUST_BE_EMPTY",400)
            with self.server.store.transaction() as con:
                job,_=self.server.store.verified_render(output_folder[1],con)
            out=(self.server.config.data_root/"jobs"/job["id"]).resolve()
            if self.server.config.data_root.resolve() not in out.parents:
                raise WorkflowError("ARTIFACT_PATH_INVALID")
            os.startfile(str(out))
            return self.reply({"opened":True,"job_id":job["id"]})
        if self.path == "/api/projects":
            profile=None
            channel=None
            if 'channel_profile_ref' in body:
                from .channel_profiles import select
                channel=select(body['channel_profile_ref'])
            if 'content_profile_id' in body:
                identifier=body['content_profile_id']
                if not isinstance(identifier,str): raise WorkflowError('CONTENT_PROFILE_NOT_FOUND',400)
                catalog=self.server.intelligence.catalog
                configured=next((p for p in catalog['profiles'] if p['id']==identifier),None)
                if configured is None: raise WorkflowError('CONTENT_PROFILE_NOT_FOUND',400)
                from .contracts import digest
                keys=('id','name','related_project','target_audience','preferred_formats','channel','tone','duration_seconds','keywords','project_references')
                profile={k:configured[k] for k in keys if k in configured}
                profile['configuration_sha256']=digest(configured)
            return self.reply(self.server.store.create(body.get("name"), body.get("prompt"), body.get("input_kind", "prompt"),content_profile=profile,production_quality=body.get('production_quality',False),channel_profile=channel,narrated_workflow=body.get('narrated_workflow',False)), 201)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{32})/(draft|image|approve|reject|jobs|auto-plan|duplicate|archive|brand-template|voice-quality|cost-policy)", self.path)
        if not match:
            raise WorkflowError("ROUTE_NOT_FOUND", 404)
        identifier, action = match[1], match[2]
        revision = body.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool):
            raise WorkflowError("REVISION_REQUIRED", 400)
        if action == 'cost-policy':
            if set(body) != {'revision', 'max_ai_cost_vnd'}:
                raise WorkflowError('COST_POLICY_FIELDS_INVALID', 400)
            from .costs import CostLedger
            return self.reply(CostLedger(self.server.store).set_budget(identifier, revision, body['max_ai_cost_vnd']))
        if action == "draft":
            result = self.server.store.save(identifier, revision, prompt=body.get("prompt"), proposal=body.get("proposal"), scene_media=body.get("scene_media"), input_kind=body.get("input_kind"),scene_options=body.get("scene_options"),music_enabled=body.get("music_enabled"))
        elif action == "auto-plan":
            result = self.server.store.auto_plan(identifier,revision)
        elif action == "duplicate":
            result = self.server.store.duplicate(identifier,revision)
        elif action == "brand-template":
            result = self.server.store.set_brand(identifier,revision,body.get("brand_id"),body.get("template_id"),duration_mode=body.get('duration_mode'))
        elif action == 'voice-quality':
            result = self.server.store.set_voice_quality(identifier, revision, body.get('policy_id'))
        elif action == "archive":
            result = self.server.store.archive(identifier,revision,body.get("archived"))
        elif action == "reject":
            result = self.server.store.reject_content(identifier,revision,body.get("reviewer"),body.get("note"))
        elif action == "image":
            asset = save_image(self.server.config, body)
            try:
                result = self.server.store.save(identifier, revision, asset=asset)
            except Exception:
                (self.server.config.data_root / "assets" / asset["id"]).unlink(missing_ok=True)
                raise
        elif action == "approve":
            result = self.server.store.approve(identifier, revision, body.get("reviewer"), body.get("acknowledged"),purpose=body.get('purpose','production'))
        else:
            if body.get("kind") == "asr":
                from .asr import pending_speech
                doc = self.server.store.get(identifier)["document"]
                if pending_speech(doc) and not assemblyai_connection.status(self.server.config)["connected"]:
                    raise WorkflowError("ASR_PROVIDER_UNAVAILABLE_NO_TRANSCRIPT", 503)
            result = self.server.store.enqueue(identifier, revision, body.get("kind"), body.get("request_key"))
            self.server.runner.wake.set()
        return self.reply(result)

    def upload_music(self, identifier):
        content_type=self.headers.get("Content-Type","").split(";")[0]
        try:
            length=int(self.headers.get("Content-Length","0")); revision=int(self.headers.get("X-VF-Revision","0"))
        except ValueError:
            raise WorkflowError("MUSIC_UPLOAD_HEADERS_INVALID",400) from None
        if content_type not in MUSIC_TYPES or not 0<length<=MUSIC_MAX_BYTES or self.headers.get("Transfer-Encoding") or self.headers.get("X-VF-Rights")!="confirmed":
            raise WorkflowError("MUSIC_RIGHTS_TYPE_SIZE_REQUIRED_MAX_25MB",400)
        fade_text=self.headers.get('X-VF-Music-Loop-Crossfade','0')
        if not re.fullmatch(r'(?:0(?:\.\d{1,3})?|1(?:\.0{1,3})?)',fade_text):raise WorkflowError('MUSIC_LOOP_CROSSFADE_INVALID',400)
        loop_crossfade=float(fade_text)
        with self.server.store.transaction() as con:
            project=self.server.store.editable(con,identifier,revision)
            if loop_crossfade:
                from .auto_edit_timeline import is_auto_edit
                if not is_auto_edit(project['document']) and not project['document'].get('canonical_timeline'):raise WorkflowError('MUSIC_LOOP_CROSSFADE_SOURCE_TIMELINE_REQUIRED',400)
        directory=self.server.config.data_root/"uploads"; directory.mkdir(parents=True,exist_ok=True)
        source=directory/(uuid.uuid4().hex+".part")
        try:
            raw=self.rfile.read(length)
            if len(raw)!=length:
                raise WorkflowError("MUSIC_UPLOAD_INCOMPLETE",400)
            source.write_bytes(raw)
            music=ingest_music(self.server.config,source,content_type,unquote(self.headers.get("X-VF-Filename","Nhạc nền")),rights_confirmed=True)
            try:
                result=self.server.store.set_music(identifier,revision,music,loop_crossfade_seconds=loop_crossfade) if loop_crossfade else self.server.store.set_music(identifier,revision,music)
            except Exception:
                (self.server.config.data_root/"assets"/music["id"]).unlink(missing_ok=True)
                (self.server.config.data_root/"originals"/music["original_id"]).unlink(missing_ok=True)
                raise
            return self.reply(result,201)
        finally:
            source.unlink(missing_ok=True)

    def upload_media(self, identifier):
        content_type = self.headers.get("Content-Type", "").split(";")[0]
        try:
            length = int(self.headers.get("Content-Length", "0"))
            revision = int(self.headers.get("X-VF-Revision", "0"))
        except ValueError:
            raise WorkflowError("INVALID_MEDIA_UPLOAD_HEADERS", 400) from None
        limit = VIDEO_MAX_BYTES if content_type.startswith("video/") else IMAGE_MAX_BYTES
        if content_type not in CONTENT_TYPES or not 0 < length <= limit or self.headers.get("Transfer-Encoding"):
            raise WorkflowError("MEDIA_FILE_TOO_LARGE_OR_TYPE_UNSUPPORTED", 400)
        rights = self.headers.get("X-VF-Rights") == "confirmed"
        illustration_value = self.headers.get("X-VF-Illustration")
        if not rights or illustration_value not in {"true", "false"}:
            raise WorkflowError("MEDIA_RIGHTS_CONFIRMATION_REQUIRED", 400)
        # Early optimistic check, then recheck in the append transaction after validation.
        with self.server.store.transaction() as con:
            self.server.store.editable(con, identifier, revision)
        directory = self.server.config.data_root / "uploads"
        directory.mkdir(parents=True, exist_ok=True)
        source = directory / (uuid.uuid4().hex + ".part")
        try:
            remaining = length
            with source.open("xb") as dest:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise WorkflowError("MEDIA_UPLOAD_INCOMPLETE", 400)
                    dest.write(chunk)
                    remaining -= len(chunk)
            asset = ingest_media(self.server.config, source, content_type, unquote(self.headers.get("X-VF-Filename", "Media")),
                                 rights_confirmed=True, illustration=illustration_value == "true")
            try:
                result = self.server.store.append_media(identifier, revision, asset)
            except Exception:
                discard_media(self.server.config, asset)
                raise
            from .auto_edit_timeline import is_auto_edit
            if is_auto_edit(result['document']):result=self.server.store.shot_view(identifier)
            return self.reply(result, 201)
        finally:
            source.unlink(missing_ok=True)

    def upload_document(self, identifier):
        content_type = self.headers.get("Content-Type", "").split(";")[0]
        try:
            length = int(self.headers.get("Content-Length", "0"))
            revision = int(self.headers.get("X-VF-Revision", "0"))
        except ValueError:
            raise WorkflowError("DOCUMENT_HEADERS_INVALID", 400) from None
        if content_type not in DOCUMENT_TYPES or not 0 < length <= DOCUMENT_MAX_BYTES or self.headers.get("Transfer-Encoding"):
            raise WorkflowError("DOCUMENT_TYPE_OR_SIZE_INVALID_MAX_5MB", 400)
        with self.server.store.transaction() as con:
            self.server.store.editable(con, identifier, revision)
        directory = self.server.config.data_root / "uploads"; directory.mkdir(parents=True, exist_ok=True)
        source = directory / (uuid.uuid4().hex + ".part")
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise WorkflowError("DOCUMENT_UPLOAD_INCOMPLETE", 400)
            with source.open("xb") as handle: handle.write(raw)
            asset = ingest_document(self.server.config, source, content_type, unquote(self.headers.get("X-VF-Filename", "Document")))
            try:
                result = self.server.store.append_document(identifier, revision, asset)
            except Exception:
                (self.server.config.data_root / "documents" / asset["id"]).unlink(missing_ok=True)
                raise
            return self.reply(result, 201)
        finally:
            source.unlink(missing_ok=True)

    def refuse(self, value, status):
        self.close_connection = True
        self.reply(value, status)
        self.wfile.flush()
        # Send the complete error before closing. On Windows, closing a socket
        # with unread upload bytes can reset it and hide the JSON response.
        # Discard only bounded bytes/time; never parse, persist or dispatch them.
        try:
            self.connection.shutdown(socket.SHUT_WR)
            deadline = time.monotonic() + .25
            remaining = 1024 * 1024
            while remaining and time.monotonic() < deadline:
                self.connection.settimeout(max(.001, deadline - time.monotonic()))
                chunk = self.connection.recv(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
        except OSError:
            pass

    def handle_request(self, method):
        self.request_id = uuid.uuid4().hex
        self.response_status = None
        self.auth_session = None
        self.auth_permission = None
        started = time.monotonic()
        try:
            self.connection.settimeout(30)
            if method == "GET":
                self.dispatch_get()
            else:
                self.dispatch_post()
        except WorkflowError as error:
            self.refuse({"code": error.code, "failure": failure(error.code, http_status=error.http_status)}, error.status)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception:
            self.refuse({"code": "LOCAL_REQUEST_FAILED"}, 500)
        finally:
            route, project_id, job_id = route_context(self.path)
            self.server.observer.emit('http_request', request_id=self.request_id,
                project_id=project_id, job_id=job_id, stage='http', provider=None,
                duration=time.monotonic() - started, status=self.response_status, method=method, route=route)

    def do_GET(self):
        self.handle_request("GET")

    def do_POST(self):
        self.handle_request("POST")


def main():
    configure_logging()
    parser = argparse.ArgumentParser(description="Video Factory Windows Native Studio")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--port", type=int, default=8026)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument('--auth-registry', type=Path)
    parser.add_argument('--workspace-id')
    parser.add_argument('--bridge-auth-registry',type=Path)
    parser.add_argument('--bridge-webhook-registry',type=Path)
    parser.add_argument('--enable-bridge-http',action='store_true')
    parser.add_argument('--stock-provider-registry',type=Path)
    parser.add_argument('--enable-stock-api',action='store_true')
    parser.add_argument('--generation-provider-registry',type=Path)
    parser.add_argument('--enable-generation-api',action='store_true')
    parser.add_argument('--official-account-registry',type=Path)
    parser.add_argument('--enable-official-account-reads',action='store_true')
    parser.add_argument('--enable-official-analytics',action='store_true')
    parser.add_argument('--enable-official-analytics-refresh',action='store_true')
    parser.add_argument('--google-oauth-registry',type=Path)
    parser.add_argument('--google-oauth-directory',type=Path)
    parser.add_argument('--enable-google-oauth',action='store_true')
    parser.add_argument('--official-vision-registry',type=Path)
    parser.add_argument('--official-vision-directory',type=Path)
    parser.add_argument('--enable-official-vision',action='store_true')
    parser.add_argument('--official-publish-registry',type=Path)
    parser.add_argument('--official-publish-session-directory',type=Path)
    parser.add_argument('--enable-official-publishing',action='store_true')
    parser.add_argument('--enable-official-publish-queue',action='store_true')
    parser.add_argument('--trend-feed-registry',type=Path)
    parser.add_argument('--enable-trend-feeds',action='store_true')
    parser.add_argument('--enable-owner-rights-overrides',action='store_true')
    args = parser.parse_args()
    config = Config.load(args.config)
    try:
        if (args.auth_registry is None) != (args.workspace_id is None):
            raise WorkflowError('NATIVE_AUTH_CONFIGURATION_INVALID', 400)
        access = None
        if args.auth_registry is not None:
            from .access import NativeAccess
            access = NativeAccess.from_file(args.auth_registry, args.workspace_id, config.data_root)
        ready = verify_runtime(config, full=True)
        if args.preflight:
            print(json.dumps(ready, ensure_ascii=False))
            return
        from .windows_job import contain_process_tree, lock_data_root
        contain_process_tree()
        lock = lock_data_root(config.data_root)
        with LocalServer(args.port, config, access=access,bridge_auth_registry=args.bridge_auth_registry,
            bridge_webhook_registry=args.bridge_webhook_registry,bridge_http_enabled=args.enable_bridge_http,
            stock_registry=args.stock_provider_registry,stock_api_enabled=args.enable_stock_api,owner_rights_overrides=args.enable_owner_rights_overrides,
            generation_registry=args.generation_provider_registry,generation_api_enabled=args.enable_generation_api,
            official_account_registry=args.official_account_registry,official_account_read_enabled=args.enable_official_account_reads,
            official_analytics_enabled=args.enable_official_analytics,official_analytics_refresh_enabled=args.enable_official_analytics_refresh,
            google_oauth_registry=args.google_oauth_registry,google_oauth_directory=args.google_oauth_directory,google_oauth_enabled=args.enable_google_oauth,
            official_vision_registry=args.official_vision_registry,official_vision_directory=args.official_vision_directory,official_vision_enabled=args.enable_official_vision,
            official_publish_registry=args.official_publish_registry,official_publish_session_directory=args.official_publish_session_directory,official_publish_enabled=args.enable_official_publishing,official_publish_queue_enabled=args.enable_official_publish_queue,
            trend_feed_registry=args.trend_feed_registry,trend_feed_enabled=args.enable_trend_feeds) as server:
            print(f"Video Factory: http://127.0.0.1:{server.server_port}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        lock.close()
    except Exception as error:
        print(json.dumps({"code": error.code if isinstance(error, WorkflowError) else type(error).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
