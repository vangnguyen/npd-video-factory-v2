"""Explicit disabled-by-default import; unknown receipts never re-copy or synthesize."""
import asyncio
from .frozen_storage_read import completed_read
from .sql_variant_repository import SqlVariantError
from .sql_variant_narration_models import NarrationReuseRequest, NarrationReuseRead


class SqlVariantNarrationService:
    def __init__(self,repository,copier,*,enabled=False):
        if type(enabled) is not bool:raise ValueError('S5_ENABLED_BOOL_REQUIRED')
        self.repository,self.copier,self.enabled=repository,copier,enabled

    async def reuse(self,workspace,master,family_id,payload,*,actor_ref):
        payload=NarrationReuseRequest.model_validate(payload.model_dump())
        self.repository.families.actor(actor_ref)
        if not self.enabled or not payload.enabled:
            return NarrationReuseRead(receipt_id=None,family_id=family_id,member_id=payload.member_id,
                workspace_id=workspace,child_project_id=payload.child_project_id,state='disabled',actor_ref=actor_ref),False
        receipt,claim,replayed=await self.repository.claim(workspace,master,family_id,payload,actor_ref=actor_ref)
        if replayed:
            if receipt.state=='ready':
                current=await self.repository.get(workspace,master,family_id,receipt.receipt_id,require_current=True)
                value=await self.repository.input(workspace,master,family_id,receipt.receipt_id)
                await self.copier.verify_all(current.result['copies'],value)
                if await self.repository.get(workspace,master,family_id,receipt.receipt_id,require_current=True)!=current:
                    raise SqlVariantError('SQL_VARIANT_NARRATION_CHANGED')
            return receipt,True
        async def guard():
            await self.repository.guard(workspace,master,family_id,receipt.receipt_id,claim['claim_id'])
        try:
            await guard()
            copies=await self.copier.copy(claim['input'],receipt.receipt_id,guard=guard)
            await guard()
            result=await self.repository.complete(workspace,master,family_id,receipt.receipt_id,claim['claim_id'],
                copies,verify=self.copier.hold)
            return result,False
        except asyncio.CancelledError:
            try:
                await completed_read(self.repository.unknown(workspace,family_id,receipt.receipt_id,claim['claim_id'],
                    'SQL_VARIANT_NARRATION_CANCELLED'))
            except BaseException:pass
            raise
        except Exception as error:
            code=error.code if isinstance(error,SqlVariantError) else 'SQL_VARIANT_NARRATION_OUTCOME_UNKNOWN'
            await self.repository.unknown(workspace,family_id,receipt.receipt_id,claim['claim_id'],code)
            if isinstance(error,SqlVariantError):raise
            raise SqlVariantError('SQL_VARIANT_NARRATION_OUTCOME_UNKNOWN') from None
