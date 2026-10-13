"""Scoped family API orchestration; GET/configuration never stages bytes or AI."""
from typing import Annotated, Literal

from pydantic import Field

from .object_storage import LocalObjectStorageProvider
from .sql_variant_models import Contract, VariantAvailability, FamilyRead, MasterBinding
from .sql_variant_repository import SqlVariantFamilyRepository, SqlVariantError
from .sql_variant_derivation_models import DeriveStoryboardRequest, StoryboardDerivationRead
from .sql_variant_uploaded_models import DeriveUploadedRequest, UploadedDerivationRead
from .sql_variant_derivation_repository import SqlStoryboardDerivationRepository
from .sql_variant_uploaded_repository import SqlUploadedDerivationRepository
from .sql_variant_derivation_service import SqlStoryboardDerivationService
from .sql_variant_storyboard_copy import LocalStoryboardCopier
from .sql_variant_uploaded_copy import LocalEvidenceCopier


DerivationRequest = Annotated[DeriveStoryboardRequest | DeriveUploadedRequest,
    Field(discriminator='schema_version')]
DerivationReceipt = Annotated[StoryboardDerivationRead | UploadedDerivationRead,
    Field(discriminator='schema_version')]


class DerivationStatus(Contract):
    schema_version: Literal['sql-variant-api-dispatch.v1'] = 'sql-variant-api-dispatch.v1'
    engine: Literal['storyboard', 'uploaded_evidence', 'unsupported']
    state: Literal['CONFIGURED', 'NOT_CONFIGURED', 'UNSUPPORTED']
    reason_code: str | None
    provider_calls: Literal[0] = 0
    automatic_execution: Literal[False] = False


class ApiAvailability(Contract):
    schema_version: Literal['sql-variant-api-availability.v1'] = 'sql-variant-api-availability.v1'
    availability: VariantAvailability
    derivation: DerivationStatus


class FamilyMutationRead(Contract):
    schema_version: Literal['sql-variant-api-family-result.v1'] = 'sql-variant-api-family-result.v1'
    family: FamilyRead
    replayed: bool


class DerivationMutationRead(Contract):
    schema_version: Literal['sql-variant-api-derive-result.v1'] = 'sql-variant-api-derive-result.v1'
    receipt: DerivationReceipt
    replayed: bool


class SqlVariantApiService:
    def __init__(self, families: SqlVariantFamilyRepository, *, object_storage=None,
                 uploaded_enabled=False, max_file_bytes=64 * 1024 * 1024,
                 max_total_bytes=256 * 1024 * 1024, timeout_seconds=120):
        if type(uploaded_enabled) is not bool:
            raise ValueError('SQL_VARIANT_UPLOADED_CONFIGURATION_INVALID')
        if (type(max_file_bytes) is not int or not 1 <= max_file_bytes <= 256 * 1024 * 1024
                or type(max_total_bytes) is not int or not max_file_bytes <= max_total_bytes <= 1024 * 1024 * 1024
                or type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 600):
            raise ValueError('SQL_VARIANT_COPY_LIMIT_INVALID')
        self.families = families
        self.storyboards = SqlStoryboardDerivationRepository(families)
        self.uploaded = SqlUploadedDerivationRepository(families)
        self.object_storage = object_storage
        self.uploaded_enabled = uploaded_enabled
        self._uploaded_enabled = uploaded_enabled
        self._storage_binding = self._storage_identity(object_storage)
        self._limits = dict(max_file_bytes=max_file_bytes, max_total_bytes=max_total_bytes,
                            timeout_seconds=timeout_seconds)

    @staticmethod
    def _storage_identity(storage):
        # Metadata only: constructor/GET never accesses a file or provider.
        return (type(storage), id(storage), getattr(storage, 'name', None),
                str(getattr(storage, 'root', None)), str(getattr(storage, '_io_root', None)))

    def dispatch(self, binding: MasterBinding):
        graph = any(p.table in {'auto_edit_analyses', 'uploaded_audio_transcriptions'} and p.count > 0
                    for p in binding.records)
        if graph:
            engine = 'uploaded_evidence'
        elif binding.source_mode == 'storyboard_media':
            engine = 'storyboard'
        else:
            # A valid unanalysed mixed upload is an explicit remaining S3 gap.
            return DerivationStatus(engine='unsupported', state='UNSUPPORTED',
                                    reason_code='SQL_VARIANT_SOURCE_GRAPH_REQUIRED')
        reason = None
        if (self.uploaded_enabled != self._uploaded_enabled
                or self._storage_identity(self.object_storage) != self._storage_binding):
            reason = 'SQL_VARIANT_API_CONFIGURATION_CHANGED'
        elif type(self.object_storage) is not LocalObjectStorageProvider:
            reason = 'SQL_VARIANT_STORAGE_NOT_CONFIGURED'
        elif engine == 'uploaded_evidence' and not self._uploaded_enabled:
            reason = 'SQL_VARIANT_UPLOADED_NOT_CONFIGURED'
        return DerivationStatus(engine=engine, state='NOT_CONFIGURED' if reason else 'CONFIGURED',
                                reason_code=reason)

    async def availability(self, workspace, master):
        result = await self.families.availability(workspace, master)
        return ApiAvailability(availability=result, derivation=self.dispatch(result.binding))

    async def list(self, workspace, master, *, limit=25, cursor=None):
        return await self.families.list(workspace, master, limit=limit, cursor=cursor)

    async def get(self, workspace, master, family_id):
        value = await self.families.get(workspace, master, family_id)
        if value is None:
            raise KeyError('SQL_VARIANT_FAMILY_NOT_FOUND')
        return value

    async def reserve(self, workspace, master, payload, *, actor_ref):
        value, replayed = await self.families.reserve(workspace, master, payload, actor_ref=actor_ref)
        return FamilyMutationRead(family=value, replayed=replayed)

    async def cancel(self, workspace, master, family_id, payload, *, actor_ref):
        value, replayed = await self.families.cancel(workspace, master, family_id, payload, actor_ref=actor_ref)
        return FamilyMutationRead(family=value, replayed=replayed)

    async def derive(self, workspace, master, family_id, payload, *, actor_ref):
        family = await self.get(workspace, master, family_id)
        state = self.dispatch(family.snapshot.binding)
        if state.state != 'CONFIGURED':
            raise SqlVariantError(state.reason_code)
        expected = DeriveUploadedRequest if state.engine == 'uploaded_evidence' else DeriveStoryboardRequest
        if type(payload) is not expected:
            raise SqlVariantError('SQL_VARIANT_DERIVATION_SCHEMA_MISMATCH')
        # Only an explicit authenticated derive constructs a copier. Claim itself
        # revalidates current source/family/actor/CAS; unknown is never recopied.
        repository = self.uploaded if state.engine == 'uploaded_evidence' else self.storyboards
        copier = (LocalEvidenceCopier if state.engine == 'uploaded_evidence' else LocalStoryboardCopier)(
            self.object_storage, **self._limits)
        value, replayed = await SqlStoryboardDerivationService(repository, copier).derive(
            workspace, master, family_id, payload, actor_ref=actor_ref)
        return DerivationMutationRead(receipt=value, replayed=replayed)

    async def receipt(self, workspace, master, family_id, receipt_id):
        # Observe stored receipts even if copying has subsequently been disabled.
        # Repository kind filters prevent interpreting one contract as another.
        await self.get(workspace, master, family_id)
        for repository in (self.storyboards, self.uploaded):
            value = await repository.get(workspace, master, family_id, receipt_id)
            if value is not None:
                return value
        raise KeyError('SQL_VARIANT_RECEIPT_NOT_FOUND')


def register_sql_variant_routes(app):
    """Idempotent router registration outside lifespan; no storage/SQL IO."""
    from .sql_variant_routes import router
    if not getattr(app.state, 'sql_variant_routes_registered', False):
        app.include_router(router)
        app.state.sql_variant_routes_registered = True


def configure_sql_variant_api(app, *, session_factory, object_storage=None,
                              uploaded_enabled=False, register_routes=True, **copy_limits):
    """Root registration hook: no DDL, filesystem/provider IO or authentication setup.

    The router authenticates itself before reading a body. Register without an
    additional authorize_human_request dependency to avoid duplicate rate counts.
    Actual platform_repository and human auth emergency switches must be installed
    by the host app; missing authentication stays fail-closed.
    """
    if type(register_routes) is not bool:
        raise ValueError('SQL_VARIANT_API_CONFIGURATION_INVALID')
    service = SqlVariantApiService(SqlVariantFamilyRepository(session_factory),
        object_storage=object_storage, uploaded_enabled=uploaded_enabled, **copy_limits)
    app.state.sql_variant_api_service = service
    if register_routes:
        register_sql_variant_routes(app)
    return service
