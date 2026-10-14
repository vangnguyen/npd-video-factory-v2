"""Original video playback after coherent intake/analysis custody checks.

This is a point-in-time read admission, not an edit, model result, lease, rights
override or human acceptance. The verified private response owns its byte copy.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from pathlib import Path
import re

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from sqlalchemy import text
from starlette.responses import Response

from .auto_edit_db import AutoEditAnalysisORM, UploadSessionORM
from .auto_edit_models import AutoEditAnalysisRequest, MediaMetadata
from .auto_edit_source_custody import trusted_video_in_session
from .db import AssetORM, ProjectVersionORM, VideoProjectORM, WorkspaceORM
from .frozen_storage_read import MAX_SOURCE_BYTES, asset_custody, completed_read
from .human_auth import (
    HumanPrincipal, InvalidHumanCredential, authorize_human_request,
    authorize_project, principal_from,
)
from .repositories import _asset_read
from .source_asset_delivery import deliver_source_asset


def reject(code: str, status: int = 409):
    raise HTTPException(status, detail={'code': code}, headers={'Cache-Control': 'no-store'})


class VideoAnalysisSourceRoute(APIRoute):
    """Include dependency/authentication failures in the no-store contract."""
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def no_store(request):
            try:
                response = await handler(request)
            except HTTPException as exc:
                exc.headers = {**(exc.headers or {}), 'Cache-Control': 'no-store'}
                raise
            response.headers['Cache-Control'] = 'no-store'
            return response

        return no_store


def _finite_digest(value):
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
            allow_nan=False).encode('utf-8')
        return hashlib.sha256(raw).hexdigest()
    except (TypeError, ValueError, RecursionError):
        reject('VIDEO_SOURCE_METADATA_INVALID')


def _runtime_binding(service):
    """Freeze adapter identity and public custody settings, never credentials."""
    storage = service.object_storage
    # These are the existing local/S3 adapter's public custody settings. Unknown
    # adapters still bind by instance/name and must honor the bounded contract.
    locations = tuple((name, str(getattr(storage, name))) for name in
        ('root', '_io_root', '_download_root', 'bucket', 'region') if hasattr(storage, name))
    return (id(service), id(service.repository), id(service.repository.session_factory),
        id(storage), storage.name, id(getattr(storage, 'client', None)), locations,
        str(Path(service.staging_root).absolute()))


def _principal_binding(principal):
    return _finite_digest({'token_id': principal.token_id, 'subject': principal.subject,
        'display_name': principal.display_name, 'platform_role': principal.platform_role,
        'workspace_roles': dict(principal.workspace_roles), 'expires_at': principal.expires_at.isoformat()})


def _assert_request_current(request, service, runtime, principal, actor):
    try:
        current_runtime = _runtime_binding(service)
    except (AttributeError, ValueError, TypeError, OSError):
        reject('VIDEO_SOURCE_RUNTIME_CHANGED')
    if (getattr(request.app.state, 'auto_edit_analysis_service', None) is not service
        or current_runtime != runtime
        or principal_from(request) is not principal
        or _principal_binding(principal) != actor
        or not getattr(request.app.state, 'human_api_enabled', False)):
        reject('VIDEO_SOURCE_RUNTIME_CHANGED')
    try:
        current_principal = request.app.state.human_auth_verifier.verify(request.headers.get('Authorization'))
    except (InvalidHumanCredential, AttributeError):
        reject('VIDEO_SOURCE_SESSION_CHANGED', 401)
    if _principal_binding(current_principal) != actor:
        reject('VIDEO_SOURCE_SESSION_CHANGED', 401)


async def source_snapshot(repository, project_id, analysis_id, *, principal, storage_name,
    maximum=MAX_SOURCE_BYTES):
    """Read analysis, intake/derivative graph and source in one owned SQL view."""
    async with repository.session_factory() as session:
        dialect = session.get_bind().dialect.name
        if dialect == 'sqlite':
            await session.execute(text('BEGIN'))
        elif dialect == 'postgresql':
            await session.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
            await session.execute(text('SET TRANSACTION READ ONLY'))
        else:
            reject('VIDEO_SOURCE_SNAPSHOT_NOT_CONFIGURED', 503)
        project = await session.get(VideoProjectORM, project_id)
        workspace = await session.get(WorkspaceORM, project.workspace_id) if project else None
        if workspace is None or principal.role_for(workspace.workspace_id, workspace.slug) is None:
            reject('VIDEO_SOURCE_NOT_FOUND', 404)
        analysis = await session.get(AutoEditAnalysisORM, analysis_id)
        if (analysis is None or analysis.project_id != project_id
            or analysis.workspace_id != project.workspace_id):
            reject('VIDEO_SOURCE_NOT_FOUND', 404)
        if analysis.status != 'succeeded':
            reject('VIDEO_SOURCE_ANALYSIS_NOT_SUCCEEDED')
        asset = await session.get(AssetORM, analysis.asset_id)
        if (asset is None or asset.project_id != project_id
            or asset.workspace_id != project.workspace_id):
            reject('VIDEO_SOURCE_NOT_FOUND', 404)
        try:
            configuration = AutoEditAnalysisRequest.model_validate(analysis.configuration_json)
            custody = await trusted_video_in_session(session, project_id, analysis.asset_id, storage_name, maximum)
            media = MediaMetadata.model_validate(analysis.source_media_json)
            if (configuration.asset_id != analysis.asset_id
                or re.fullmatch(r'[a-f0-9]{64}', analysis.fingerprint) is None
                or analysis.provenance_json.get('source_asset_checksum') != asset.checksum_sha256
                or media.model_dump(mode='json') != custody['media_metadata']):
                reject('VIDEO_SOURCE_ANALYSIS_BINDING_CHANGED')
            for version_id in {analysis.project_version_id, asset.project_version_id} - {None}:
                version = await session.get(ProjectVersionORM, version_id)
                if (version is None or version.project_id != project_id
                    or version.workspace_id != project.workspace_id):
                    reject('VIDEO_SOURCE_ANALYSIS_BINDING_CHANGED')
            readable = _asset_read(asset)
            upload = await session.get(UploadSessionORM, custody['upload_id']) if custody['upload_id'] else None
            upload_binding = {name: copy.deepcopy(getattr(upload, name)) for name in (
                'upload_id', 'workspace_id', 'project_id', 'asset_id', 'status', 'quarantine_state',
                'scan_checksum_sha256', 'media_metadata_json', 'scan_verdict', 'scan_provider',
                'scan_signature_version', 'scan_result_code')} if upload else None
            if upload_binding is not None:
                upload_binding['trusted_at'] = upload.trusted_at.isoformat()
            # Current transcript edits are independent from source playback;
            # source/analysis provenance remains bound without changing its clock.
            binding = {
                'project': {'project_id': project_id, 'workspace_id': project.workspace_id,
                    'version': project.version, 'current_version_id': project.current_version_id,
                    'status': project.status},
                'workspace': {'workspace_id': workspace.workspace_id, 'slug': workspace.slug,
                    'version': workspace.version},
                'analysis': {'analysis_id': analysis.analysis_id, 'asset_id': analysis.asset_id,
                    'project_version_id': analysis.project_version_id, 'status': analysis.status,
                    'fingerprint': analysis.fingerprint, 'configuration': configuration.model_dump(mode='json'),
                    'source_media': media.model_dump(mode='json'),
                    'provenance_sha256': _finite_digest(analysis.provenance_json)},
                'asset': asset_custody(readable), 'intake': custody, 'upload': upload_binding,
            }
            _finite_digest(binding)
            return readable, copy.deepcopy(binding)
        except HTTPException:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            reject('VIDEO_SOURCE_CUSTODY_INVALID')


async def video_analysis_source(project_id: str, analysis_id: str, request: Request):
    """GET/HEAD original video; never prepare/analyze or dispatch a provider."""
    # Normal main dependencies already authenticate. A standalone router still
    # authenticates before source SQL reads, without double rate-limiting main.
    if not isinstance(getattr(request.state, 'human_principal', None), HumanPrincipal):
        await authorize_human_request(request)
    principal = await authorize_project(request, project_id, 'viewer')
    if request.url.query:
        reject('VIDEO_SOURCE_QUERY_NOT_SUPPORTED', 422)
    service = getattr(request.app.state, 'auto_edit_analysis_service', None)
    if service is None:
        reject('VIDEO_SOURCE_NOT_CONFIGURED', 503)
    try:
        repository, storage = service.repository, service.object_storage
        runtime, actor = _runtime_binding(service), _principal_binding(principal)
        staging_root = Path(service.staging_root)
    except (AttributeError, ValueError, TypeError, OSError):
        reject('VIDEO_SOURCE_NOT_CONFIGURED', 503)
    asset, frozen = await source_snapshot(repository, project_id, analysis_id,
        principal=principal, storage_name=storage.name)
    _assert_request_current(request, service, runtime, principal, actor)
    response = None
    handed_off = False
    try:
        response = await completed_read(deliver_source_asset(request, asset=asset,
            object_storage=storage, staging_root=staging_root),
            dispose_cancelled_result=lambda owned: owned.close())
        _assert_request_current(request, service, runtime, principal, actor)
        _, current = await source_snapshot(repository, project_id, analysis_id,
            principal=principal, storage_name=storage.name)
        if current != frozen:
            reject('VIDEO_SOURCE_CUSTODY_CHANGED')
        _assert_request_current(request, service, runtime, principal, actor)
        if request.method == 'HEAD':
            headers, status = dict(response.headers), response.status_code
            await completed_read(asyncio.to_thread(response.close))
            return Response(content=b'', status_code=status, headers=headers)
        handed_off = True
        return response
    finally:
        if response is not None and not handed_off:
            await completed_read(asyncio.to_thread(response.close))
