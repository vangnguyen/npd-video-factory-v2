from __future__ import annotations

from typing import Any

from .publishing_logic import (
    PublishingCapabilityRegistry,
    hash_idempotency_key,
    request_fingerprint,
    validate_platform,
    validate_rights,
    validation_check,
)
from .publishing_models import (
    PlatformValidationRead,
    ProviderValidationRead,
    PublicationCreateRequest,
    PublicationEventRead,
    PublicationRead,
    PublishingPlatformStateRead,
    RightsValidationRead,
)
from .publishing_providers import (
    ExternalPublishingNotActivated,
    PublishingContext,
    PublishingProviderRegistry,
)
from .publishing_repository import PublishingRepository
from .timeline_models import TimelineSnapshot


class PublishingBoundaryError(RuntimeError):
    def __init__(self, publication: PublicationRead):
        self.publication = publication
        super().__init__(publication.failure_reason or "publication is blocked")


class PublishingPreconditionError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class PublishingService:
    def __init__(
        self,
        *,
        repository: PublishingRepository,
        production_repository,
        asset_repository,
        capabilities: PublishingCapabilityRegistry,
        providers: PublishingProviderRegistry,
        settings,
    ):
        self.repository = repository
        self.production_repository = production_repository
        self.asset_repository = asset_repository
        self.capabilities = capabilities
        self.providers = providers
        self.settings = settings

    async def create(
        self,
        *,
        project_id: str,
        payload: PublicationCreateRequest,
        idempotency_key: str,
    ) -> tuple[PublicationRead, bool]:
        key_hash = hash_idempotency_key(idempotency_key)
        fingerprint = request_fingerprint(payload)
        package = await self.production_repository.get_package(project_id)
        if package is None:
            raise KeyError("production-package")
        render = await self.production_repository.get_render(payload.final_render_id)
        if render is None or render.project_id != project_id:
            raise KeyError("final-render")
        if package.approval is None:
            raise PublishingPreconditionError(
                "APPROVAL_REQUIRED",
                "A current approved production package is required.",
            )
        if render.output_asset_id is None:
            raise KeyError("final-render-output")

        capability = self.capabilities.get(payload.platform)
        provider = (
            self.providers.for_dry_run()
            if payload.mode == "dry_run"
            else self.providers.for_live(payload.platform)
        )
        publication, replay = await self.repository.reserve(
            workspace_id=package.workspace_id,
            project_id=project_id,
            package_id=package.package_id,
            approval_id=package.approval.approval_id,
            final_render_id=render.render_id,
            output_asset_id=render.output_asset_id,
            platform=payload.platform,
            provider_key=provider.provider_key,
            capability_version=capability.version,
            mode=payload.mode,
            idempotency_key_hash=key_hash,
            request_fingerprint=fingerprint,
            metadata=payload.metadata,
            actor_ref=payload.actor_ref,
        )
        if replay:
            if publication.status == "blocked":
                raise PublishingBoundaryError(publication)
            return publication, True

        context = await self.production_repository.get_render_context(render.render_id)
        if context is None:
            raise KeyError("final-render-context")
        _, _, audio_mix, snapshot_json = context
        snapshot = TimelineSnapshot.model_validate(snapshot_json)
        output_asset = await self.asset_repository.get_asset(render.output_asset_id)
        if output_asset is None:
            raise KeyError("final-render-output-asset")

        source_asset_ids = {
            clip.asset_id
            for track in snapshot.tracks
            for clip in track.clips
            if clip.asset_id and not clip.disabled
        }
        if audio_mix.config.music.asset_id:
            source_asset_ids.add(audio_mix.config.music.asset_id)
        if payload.metadata.thumbnail_asset_id:
            source_asset_ids.add(payload.metadata.thumbnail_asset_id)
        source_assets: list[Any] = []
        missing_assets: list[str] = []
        for asset_id in sorted(source_asset_ids):
            asset = await self.asset_repository.get_asset(asset_id)
            if asset is None or asset.project_id != project_id:
                missing_assets.append(asset_id)
            else:
                source_assets.append(asset)
        rights = validate_rights(source_assets)
        if missing_assets:
            rights = RightsValidationRead(
                status="failed",
                policy_version=rights.policy_version,
                asset_ids=rights.asset_ids,
                checks=[
                    *rights.checks,
                    *[
                        validation_check(
                            f"asset:{asset_id}",
                            False,
                            "RIGHTS_ASSET_NOT_FOUND",
                            "Referenced source or thumbnail asset was not found in this project.",
                            asset_id=asset_id,
                        )
                        for asset_id in missing_assets
                    ],
                ],
            )

        platform_validation = validate_platform(
            capability=capability,
            metadata=payload.metadata,
            render=render,
            output_asset=output_asset,
            mode=payload.mode,
        )
        if payload.metadata.thumbnail_asset_id:
            thumbnail = next(
                (item for item in source_assets if item.asset_id == payload.metadata.thumbnail_asset_id),
                None,
            )
            thumbnail_ok = bool(thumbnail and str(thumbnail.content_type).startswith("image/"))
            platform_validation = PlatformValidationRead(
                status=(
                    "passed"
                    if platform_validation.status == "passed" and thumbnail_ok
                    else "failed"
                ),
                capability=platform_validation.capability,
                checks=[
                    *platform_validation.checks,
                    validation_check(
                        "thumbnail-content-type",
                        thumbnail_ok,
                        "THUMBNAIL_CONTENT_SUPPORTED"
                        if thumbnail_ok
                        else "THUMBNAIL_CONTENT_UNSUPPORTED",
                        "Thumbnail is a project image asset."
                        if thumbnail_ok
                        else "Thumbnail must be an image asset in the same project.",
                    ),
                ],
            )

        provider_validation = provider.validate()
        provider_validation = provider_validation.model_copy(
            update={
                "checks": [
                    *self._production_checks(package, render),
                    *provider_validation.checks,
                ]
            }
        )

        all_checks = [
            *provider_validation.checks,
            *rights.checks,
            *platform_validation.checks,
        ]
        failed = next((item for item in all_checks if not item.passed), None)
        if failed is not None:
            blocked = await self.repository.finalize(
                publication.publication_id,
                status="blocked",
                rights_validation=rights,
                platform_validation=platform_validation,
                provider_validation=provider_validation,
                receipt=None,
                failure_code=failed.code,
                failure_reason=failed.message,
                actor_ref=payload.actor_ref,
            )
            raise PublishingBoundaryError(blocked)

        context_payload = PublishingContext(
            platform=payload.platform,
            project_id=project_id,
            final_render_id=render.render_id,
            output_asset_id=render.output_asset_id,
            request_fingerprint=fingerprint,
            metadata=payload.metadata,
        )
        try:
            receipt = await provider.publish(context_payload)
        except ExternalPublishingNotActivated as exc:
            blocked = await self.repository.finalize(
                publication.publication_id,
                status="blocked",
                rights_validation=rights,
                platform_validation=platform_validation,
                provider_validation=provider_validation,
                receipt=None,
                failure_code="EXTERNAL_PUBLISHING_NOT_ACTIVATED",
                failure_reason=str(exc),
                actor_ref=payload.actor_ref,
            )
            raise PublishingBoundaryError(blocked) from exc

        completed = await self.repository.finalize(
            publication.publication_id,
            status="dry_run_succeeded" if payload.mode == "dry_run" else "published",
            rights_validation=rights,
            platform_validation=platform_validation,
            provider_validation=provider_validation,
            receipt=receipt,
            failure_code=None,
            failure_reason=None,
            actor_ref=payload.actor_ref,
        )
        return completed, False

    async def get(self, project_id: str, publication_id: str) -> PublicationRead | None:
        return await self.repository.get(project_id, publication_id)

    async def list(self, project_id: str) -> list[PublicationRead]:
        return await self.repository.list(project_id)

    async def history(self, project_id: str) -> list[PublicationEventRead]:
        return await self.repository.list_events(project_id)

    def platform_states(self) -> list[PublishingPlatformStateRead]:
        dry_run = self.providers.for_dry_run().validate()
        states: list[PublishingPlatformStateRead] = []
        for capability in self.capabilities.list():
            official = self.providers.official_status(capability.platform)
            states.append(
                PublishingPlatformStateRead(
                    platform=capability.platform,
                    capability=capability,
                    dry_run_provider=dry_run,
                    official_provider=official,
                    live_execution_enabled=bool(
                        self.settings.publish_enabled
                        and self.settings.publish_external_execution_enabled
                        and self.settings.publish_owner_gate_enabled
                        and official.supports_live_publish
                    ),
                )
            )
        return states

    def _production_checks(self, package, render) -> list:
        approval = package.approval
        return [
            validation_check(
                "production-package-current",
                package.current_for_timeline,
                "PACKAGE_CURRENT" if package.current_for_timeline else "PACKAGE_STALE",
                "Production package matches the current timeline."
                if package.current_for_timeline
                else "Production package is stale for the current timeline.",
            ),
            validation_check(
                "approval-current",
                bool(
                    approval
                    and approval.status == "approved"
                    and render.approval_id == approval.approval_id
                    and render.timeline_version_id == approval.timeline_version_id
                    and render.subtitle_version_id == approval.subtitle_version_id
                    and render.audio_version_id == approval.audio_version_id
                ),
                "APPROVAL_CURRENT"
                if approval
                and approval.status == "approved"
                and render.approval_id == approval.approval_id
                and render.timeline_version_id == approval.timeline_version_id
                and render.subtitle_version_id == approval.subtitle_version_id
                and render.audio_version_id == approval.audio_version_id
                else "APPROVAL_NOT_CURRENT",
                "Final render is bound to the current approved review package."
                if approval
                and approval.status == "approved"
                and render.approval_id == approval.approval_id
                and render.timeline_version_id == approval.timeline_version_id
                and render.subtitle_version_id == approval.subtitle_version_id
                and render.audio_version_id == approval.audio_version_id
                else "Final render is not bound to the current approved package.",
            ),
            validation_check(
                "final-render",
                bool(
                    package.latest_final_render
                    and package.latest_final_render.render_id == render.render_id
                    and render.render_kind == "final"
                    and render.status == "ready"
                    and render.qc_status == "passed"
                ),
                "FINAL_RENDER_READY"
                if package.latest_final_render
                and package.latest_final_render.render_id == render.render_id
                and render.render_kind == "final"
                and render.status == "ready"
                and render.qc_status == "passed"
                else "FINAL_RENDER_NOT_READY",
                "Latest final render is ready and passed QC."
                if package.latest_final_render
                and package.latest_final_render.render_id == render.render_id
                and render.render_kind == "final"
                and render.status == "ready"
                and render.qc_status == "passed"
                else "Only the latest ready final render with passing QC is eligible.",
            ),
        ]
