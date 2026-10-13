"""Explicit local derivative operation, no startup IO or implicit execution."""
import asyncio
import copy
from .sql_variant_derivation_repository import target_key
from .sql_variant_repository import SqlVariantError
from .local_video_transcription_provider import completed_io


class SqlStoryboardDerivationService:
    def __init__(self, repository, copier):
        self.repository, self.copier = repository, copier

    async def derive(self, workspace, master, family_id, payload, *, actor_ref):
        receipt, claim, replayed = await self.repository.claim(workspace, master, family_id, payload, actor_ref=actor_ref)
        if replayed:
            # Pending/unknown receipts are observations, never another copy/inference attempt.
            if receipt.state == 'ready':
                await self.copier.verify_all(receipt.result['copies'])
                current = await self.repository.get(workspace, master, family_id, receipt.receipt_id)
                if current != receipt:
                    raise SqlVariantError('SQL_VARIANT_DERIVATION_CONFLICT')
            return receipt, True
        claim_id = claim['claim_id']
        try:
            await self.repository.guard(workspace, master, family_id, receipt.receipt_id, claim_id)
            value = claim['input']
            items = {old: {**copy.deepcopy(source), 'target_key': target_key(workspace,
                value['planned_project_id'], value['member_id'], old, source['content_type'])}
                for old, source in value['source_assets'].items()}
            copies = await self.copier.copy(items)
            await self.repository.guard(workspace, master, family_id, receipt.receipt_id, claim_id)
            async def verify(copied):
                await self.copier.verify_all(copied, source_items=items)
            ready = await self.repository.complete(workspace, master, family_id, receipt.receipt_id, claim_id,
                copies, verify=verify)
            return ready, False
        except asyncio.CancelledError:
            try:
                await completed_io(self.repository.unknown(workspace, master, family_id, receipt.receipt_id,
                    claim_id, 'SQL_VARIANT_COPY_CANCELLED'))
            except BaseException:
                pass  # No file IO remains; retain original cancellation even if SQL is unavailable.
            raise
        except Exception as exc:
            code = exc.code if isinstance(exc, SqlVariantError) else 'SQL_VARIANT_DERIVATION_FAILED'
            await self.repository.unknown(workspace, master, family_id, receipt.receipt_id, claim_id, code)
            if isinstance(exc, SqlVariantError):
                raise
            raise SqlVariantError('SQL_VARIANT_DERIVATION_FAILED') from None
