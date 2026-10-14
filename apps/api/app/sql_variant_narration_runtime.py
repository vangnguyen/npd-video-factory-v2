"""Pure paired runtime construction; defaults disabled, no storage/provider IO."""
from dataclasses import dataclass
from .sql_variant_repository import SqlVariantFamilyRepository, SqlVariantError
from .sql_variant_narration_repository import SqlVariantNarrationRepository
from .sql_variant_narration_copy import LocalNarrationCopier
from .sql_variant_narration_service import SqlVariantNarrationService
from .sql_variant_narration_render import VariantNarrationReviewLoader, VariantNarrationTerminalFence
from .sql_variant_narration_activation import VariantNarrationAdmission
from .object_storage import LocalObjectStorageProvider


@dataclass(frozen=True)
class VariantNarrationRuntime:
    reason_code: str | None
    service: object = None
    loader: object = None
    fence: object = None
    admission: object = None

    def require(self):
        if (self.reason_code is not None or type(self.admission) is not VariantNarrationAdmission
                or self.loader is not self.admission.loader or self.fence is not self.admission.fence
                or type(self.service) is not SqlVariantNarrationService
                or self.service.repository is not self.admission.repository or self.service.copier is not self.admission.copier
                or self.service.enabled is not True):
            raise SqlVariantError('SQL_VARIANT_NARRATION_NOT_CONFIGURED')
        self.admission.configured()
        return self

    def availability(self):
        try:
            self.require()
        except SqlVariantError:
            return {'state': 'NOT_CONFIGURED', 'reason_code': self.reason_code or 'SQL_VARIANT_NARRATION_NOT_CONFIGURED',
                'new_inferences': 0, 'human_review_required': True, 'production_accepted': False}
        return {'state': 'CONFIGURED', 'reason_code': None, 'new_inferences': 0,
            'human_review_required': True, 'production_accepted': False}


def create_variant_narration_runtime(*, session_factory, object_storage, assets, enabled=False):
    if type(enabled) is not bool:
        raise ValueError('SQL_VARIANT_NARRATION_ENABLED_BOOL_REQUIRED')
    if not enabled:
        return VariantNarrationRuntime('SQL_VARIANT_NARRATION_DISABLED')
    if type(object_storage) is not LocalObjectStorageProvider:
        return VariantNarrationRuntime('SQL_VARIANT_NARRATION_STORAGE_NOT_CONFIGURED')
    repository = SqlVariantNarrationRepository(SqlVariantFamilyRepository(session_factory))
    copier = LocalNarrationCopier(object_storage)
    loader = VariantNarrationReviewLoader(repository, copier, assets, enabled=True)
    fence = VariantNarrationTerminalFence(repository, copier)
    admission = VariantNarrationAdmission(repository, copier, loader, fence)
    result = VariantNarrationRuntime(None, SqlVariantNarrationService(repository, copier, enabled=True), loader, fence, admission)
    return result.require()


def register_variant_narration_routes(app):
    from .sql_variant_narration_routes import router
    if not getattr(app.state, 'sql_variant_narration_routes_registered', False):
        app.include_router(router)
        app.state.sql_variant_narration_routes_registered = True
