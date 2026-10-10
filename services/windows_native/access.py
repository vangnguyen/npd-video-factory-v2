"""Native sessions and route permissions over the existing human identity contract."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time

from . import ingestion  # Established pure-contract import path; no API service import.
from .backup import guard
from .contracts import WorkflowError
from app.human_identity import HumanAuthRegistry, HumanAuthVerifier, HumanPrincipal, InvalidHumanCredential

PERMISSIONS = {'owner': frozenset({'read', 'edit', 'review', 'manage'}),
    'editor': frozenset({'read', 'edit'}), 'reviewer': frozenset({'read', 'review'}),
    'viewer': frozenset({'read'})}
ID = '[a-f0-9]{32}'
PROFILE_MAX_BYTES = 256 * 1024


def permission_for(method, path):
    path = path.split('?', 1)[0]
    if method == 'GET':
        return 'manage' if path in ('/api/runtime-status', '/settings/assemblyai') or path.startswith('/api/connections/') else 'read'
    if method != 'POST':
        return None
    if path == '/api/logout':
        return 'read'
    if re.fullmatch(r'/api/projects/'+ID+r'/official-publications/nopu_'+ID+r'/queue(?:/nopq_'+ID+r'/cancel)?',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/official-publications(?:/nopu_'+ID+r'/(approve|renew|revoke|cancel|step|poll))?',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/official-accounts/npac_'+ID+r'/verify',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/official-analytics(?:/noas_'+ID+r'/cancel)?',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/official-analytics-refresh(?:/noap_'+ID+r'/cancel)?',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/google-oauth/(?:authorizations(?:/ngoa_'+ID+r'/(?:authorization-url|exchange|cancel))?|refresh)',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/google-oauth/selections(?:/ngosel_'+ID+r'/(?:verify|revoke))?',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/google-oauth/analytics-selections(?:/ngasel_'+ID+r'/(?:verify|revoke))?',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/tiktok-creators/(?:checks(?:/ntcr_'+ID+r'/(fetch|cancel))?|drafts)',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/official-vision(?:/nvoi_'+ID+r'/(process|cancel))?',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/render-vision(?:/nrvi_'+ID+r'/(process|cancel))?',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/render-thumbnails',path):return 'edit'
    if re.fullmatch(r'/api/projects/'+ID+r'/render-thumbnail-rights',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/official-winners',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/official-learning',path):return 'manage'
    if path in ('/api/trends/collections','/api/trends/learning','/api/trends/learning/qualified') or re.fullmatch(r'/api/trends/collections/'+ID+'/cancel',path):return 'manage'
    if path in ('/api/trends/refresh','/api/trends/handoff'):return 'edit'
    if re.fullmatch(r'/api/bridge/events/bevt_[a-f0-9]{48}/(enqueue|cancel)',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/rights/[a-f0-9]{32}\.(jpg|png|mp4|wav|music\.wav)',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/rights-overrides/[a-f0-9]{32}\.(jpg|png|mp4|wav|music\.wav)',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/narration-rights',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/stock/nstk_'+ID+r'/import',path):return 'edit'
    if re.fullmatch(r'/api/projects/'+ID+r'/stock/(search|download|nstk_'+ID+r'/cancel)',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/generation(?:/'+ID+r'/(cancel|recover|import))?',path):return 'edit'
    if re.fullmatch(r'/api/projects/'+ID+r'/media-plans/nmp_'+ID+r'/resolve/(search|download)',path):return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/media-plans/nmp_'+ID+r'/resolve/generate',path):return 'edit'
    if re.fullmatch(r'/api/projects/'+ID+r'/media-resolutions/nmr_'+ID+r'/import',path):return 'edit'
    if re.fullmatch(r'/api/projects/'+ID+r'/media-plans(?:/nmp_'+ID+r'/(select|revise|apply))?',path):return 'edit'
    if re.fullmatch(r'/api/projects/'+ID+r'/narration/'+ID+r'/apply',path):return 'edit'
    if re.fullmatch(r'/api/projects/' + ID + r'/vision(?:/nvis_' + ID + r'/(process|cancel))?',path):
        return 'manage'
    if re.fullmatch(r'/api/projects/' + ID + r'/analytics(?:/nasy_' + ID + r'/(process|cancel))?', path):
        return 'manage'
    if re.fullmatch(r'/api/projects/'+ID+r'/analytics-refresh(?:/tick|/narp_'+ID+r'/state)?',path):return 'manage'
    if re.fullmatch(r'/api/projects/' + ID + r'/publications/npub_' + ID + r'/(approve|cancel|dry-run)', path):
        return 'manage'
    if re.fullmatch(r'/api/projects/' + ID + r'/publications', path):
        return 'edit'
    if re.fullmatch(r'/api/projects/' + ID + r'/(variants|narrated-variants)',path):
        return 'edit'
    if path == '/api/connections/assemblyai' or re.fullmatch(r'/api/projects/' + ID + '/cost-policy', path) or re.fullmatch(r'/api/jobs/' + ID + '/open-folder', path):
        return 'manage'
    review = [r'/api/projects/' + ID + '/(approve|reject|script-review)', r'/api/jobs/' + ID + '/review',
        r'/api/intelligence/briefs/' + ID + '/approve', r'/api/intelligence/opportunities/' + ID + '/(reject|review)',
        r'/api/production/briefs/' + ID + '/approve']
    if any(re.fullmatch(pattern, path) for pattern in review):
        return 'review'
    edit = [r'/api/projects', r'/api/projects/' + ID + '/(draft|image|jobs|auto-plan|duplicate|archive|brand-template|voice-quality|shots|preview|ai-edit|asset-association|media|documents|music)',
        r'/api/projects/' + ID + '/auto-edit/(timeline|broll|shorts|scene-reviews|thumbnail-reviews(?:/select)?)',
        r'/api/projects/' + ID + '/auto-edit/ana_[a-f0-9]{24}/transcript', r'/api/jobs/' + ID + '/resume',
        r'/api/intelligence/runs', r'/api/intelligence/runs/' + ID + '/(research|ideas)',
        r'/api/intelligence/ideas/' + ID + '/(select|edit|reject)',
        r'/api/intelligence/briefs/' + ID + '/(edit|send)', r'/api/production/batch',
        r'/api/production/planning/' + ID]
    return 'edit' if any(re.fullmatch(pattern, path) for pattern in edit) else None


@dataclass(frozen=True)
class Session:
    principal: HumanPrincipal
    role: str
    csrf: str
    deadline: float


class NativeAccess:
    """All credentials/sessions stay private; profile changes invalidate all sessions."""
    def __init__(self, verifier, workspace_id, *, profile_path=None, data_root=None,
                 session_ttl=3600, max_sessions=256, login_per_minute=10, requests_per_minute=600,
                 clock=time.monotonic):
        if not isinstance(verifier, HumanAuthVerifier) or not isinstance(workspace_id, str) or not re.fullmatch(r'wsp_[A-Za-z0-9_-]{4,64}', workspace_id):
            raise WorkflowError('NATIVE_AUTH_CONFIGURATION_INVALID', 400)
        if any(type(value) is not int or not low <= value <= high for value, low, high in
            [(session_ttl, 60, 3600), (max_sessions, 1, 256), (login_per_minute, 1, 60), (requests_per_minute, 1, 1200)]):
            raise WorkflowError('NATIVE_AUTH_CONFIGURATION_INVALID', 400)
        self.verifier, self.workspace_id = verifier, workspace_id
        self.profile_path = guard(profile_path, exists=True) if profile_path is not None else None
        self.data_root = Path(data_root).absolute() if data_root is not None else None
        if self.profile_path is not None and (self.data_root is None or self.data_root == self.profile_path or self.data_root in self.profile_path.parents):
            raise WorkflowError('NATIVE_AUTH_PROFILE_MUST_BE_OUTSIDE_STATE', 400)
        self.session_ttl, self.max_sessions = session_ttl, max_sessions
        self.login_per_minute, self.requests_per_minute, self.clock = login_per_minute, requests_per_minute, clock
        self.sessions, self.requests, self.attempts = {}, {}, deque()
        self.lock = threading.RLock()
        self.profile_sha = None
        self.root_bound = False
        if self.profile_path is not None:
            self.refresh()

    @classmethod
    def from_file(cls, profile_path, workspace_id, data_root, **options):
        # An explicit but missing/invalid registry fails closed; never local-owner fallback.
        path = guard(profile_path, exists=True)
        verifier, _checksum = cls.load_profile(path)
        return cls(verifier, workspace_id, profile_path=path, data_root=data_root, **options)

    def bind_root(self, data_root):
        with self.lock:
            root = guard(data_root)
            if self.data_root is not None and self.data_root != root:
                raise WorkflowError('NATIVE_AUTH_STATE_SCOPE_MISMATCH', 400)
            for name in ('workflow.sqlite3', 'workflow.sqlite3-wal', 'workflow.sqlite3-shm',
                         'intelligence.sqlite3', 'intelligence.sqlite3-wal', 'intelligence.sqlite3-shm'):
                guard(root / name)
            marker = guard(root / '.vf-auth-workspace.json')
            root.mkdir(parents=True, exist_ok=True)
            expected = {'schema': 'vf-native-workspace-binding-v1', 'workspace_id': self.workspace_id}
            try:
                with marker.open('x', encoding='utf-8') as handle:
                    handle.write(json.dumps(expected) + '\n'); handle.flush(); os.fsync(handle.fileno())
            except FileExistsError:
                self.validate_binding(root)
            except OSError:
                raise WorkflowError('NATIVE_AUTH_STATE_BINDING_UNAVAILABLE', 503) from None
            self.data_root = root
            self.root_bound = True

    def validate_binding(self, root):
        try:
            marker = guard(root / '.vf-auth-workspace.json', exists=True)
            if not marker.is_file() or marker.stat().st_size > 512:
                raise ValueError()
            with marker.open('rb') as handle:
                value = json.loads(handle.read(513))
            if value != {'schema': 'vf-native-workspace-binding-v1', 'workspace_id': self.workspace_id}:
                raise ValueError()
        except (OSError, ValueError, TypeError, WorkflowError):
            raise WorkflowError('NATIVE_AUTH_STATE_BINDING_UNAVAILABLE', 503) from None

    def ready(self):
        with self.lock:
            try:
                self.refresh()
                return True
            except WorkflowError:
                return False

    @staticmethod
    def load_profile(path):
        try:
            path = guard(path, exists=True)
            if not path.is_file() or path.stat().st_size > PROFILE_MAX_BYTES:
                raise ValueError()
            with path.open('rb') as handle:
                raw = handle.read(PROFILE_MAX_BYTES + 1)
            if len(raw) > PROFILE_MAX_BYTES:
                raise ValueError()
            registry = HumanAuthRegistry.model_validate(json.loads(raw))
            if len(registry.tokens) > 512:
                raise ValueError()
            return HumanAuthVerifier(registry, max_token_ttl_seconds=86400), hashlib.sha256(raw).hexdigest()
        except (OSError, ValueError, TypeError, WorkflowError):
            raise WorkflowError('NATIVE_AUTH_PROFILE_UNAVAILABLE', 503) from None

    def refresh(self):
        if self.root_bound:
            try:
                self.validate_binding(self.data_root)
            except WorkflowError:
                self.sessions.clear(); self.requests.clear()
                raise
        if self.profile_path is None:
            return
        try:
            verifier, checksum = self.load_profile(self.profile_path)
        except WorkflowError:
            self.sessions.clear(); self.requests.clear()
            raise
        if checksum != self.profile_sha:
            self.verifier, self.profile_sha = verifier, checksum
            self.sessions.clear(); self.requests.clear()

    def expire(self):
        current, utc = self.clock(), datetime.now(timezone.utc)
        expired = [key for key, value in self.sessions.items() if current >= value.deadline or utc >= value.principal.expires_at]
        for key in expired:
            self.sessions.pop(key, None); self.requests.pop(key, None)

    @staticmethod
    def key(value):
        if not isinstance(value, str) or not 32 <= len(value) <= 128:
            raise WorkflowError('NATIVE_AUTH_SESSION_REQUIRED', 401)
        return hashlib.sha256(value.encode()).hexdigest()

    def login(self, raw_token):
        with self.lock:
            self.refresh(); self.expire()
            now = self.clock()
            while self.attempts and self.attempts[0] <= now - 60:
                self.attempts.popleft()
            if len(self.attempts) >= self.login_per_minute:
                raise WorkflowError('NATIVE_AUTH_LOGIN_RATE_LIMITED', 429)
            self.attempts.append(now)
            try:
                if not isinstance(raw_token, str) or len(raw_token) > 512:
                    raise InvalidHumanCredential()
                principal = self.verifier.verify('Bearer ' + raw_token)
            except InvalidHumanCredential:
                raise WorkflowError('NATIVE_AUTH_CREDENTIAL_REQUIRED', 401) from None
            role = principal.role_for(self.workspace_id)
            if role not in PERMISSIONS:
                raise WorkflowError('NATIVE_AUTH_WORKSPACE_NOT_FOUND', 404)
            if len(self.sessions) >= self.max_sessions:
                raise WorkflowError('NATIVE_AUTH_SESSION_CAPACITY', 429)
            cookie = secrets.token_urlsafe(32)
            session = Session(principal, role, secrets.token_urlsafe(32), now + self.session_ttl)
            self.sessions[self.key(cookie)] = session
            return cookie, session

    def authenticate(self, cookie, *, csrf=None, write=False):
        with self.lock:
            self.refresh(); self.expire()
            key = self.key(cookie)
            session = self.sessions.get(key)
            if session is None:
                raise WorkflowError('NATIVE_AUTH_SESSION_REQUIRED', 401)
            now = self.clock()
            requests = self.requests.setdefault(key, deque())
            while requests and requests[0] <= now - 60:
                requests.popleft()
            if len(requests) >= self.requests_per_minute:
                raise WorkflowError('NATIVE_AUTH_REQUEST_RATE_LIMITED', 429)
            requests.append(now)
            if write and (not isinstance(csrf, str) or not csrf.isascii() or not secrets.compare_digest(csrf, session.csrf)):
                raise WorkflowError('CSRF_TOKEN_REQUIRED', 403)
            return session

    def authorize(self, session, method, path):
        with self.lock:
            self.refresh(); self.expire()
            if not any(value is session for value in self.sessions.values()):
                raise WorkflowError('NATIVE_AUTH_SESSION_REQUIRED', 401)
            permission = permission_for(method, path)
            if permission is None or permission not in PERMISSIONS.get(session.role, frozenset()):
                raise WorkflowError('NATIVE_AUTH_FORBIDDEN', 403)
            return permission

    def logout(self, cookie):
        with self.lock:
            key = self.key(cookie)
            self.sessions.pop(key, None); self.requests.pop(key, None)

    def public(self, session):
        return {'mode': 'registry', 'workspace_id': self.workspace_id, 'role': session.role,
            'display_name': session.principal.display_name, 'permissions': sorted(PERMISSIONS[session.role])}
