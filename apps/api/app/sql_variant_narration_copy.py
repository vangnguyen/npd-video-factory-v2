"""Independent local WAV copies and PCM verification, without inference or DSP."""
import asyncio
from pathlib import Path, PurePosixPath
from .sql_variant_storyboard_copy import LocalStoryboardCopier, plain
from .sql_variant_narration_projection import source_asset_limit
from .sql_tts_artifact_reuse import prepared_pcm, pcm, validate_evidence
from .frozen_storage_read import completed_read
from .sql_variant_narration_repository import target_key
from .verified_artifact_delivery import RecordedArtifactRead,verified_output_handle,unchanged_descriptor


class HeldNarrationBytes:
    def __init__(self,handles):self.handles=handles
    def guard(self):
        for handle,info in self.handles:unchanged_descriptor(handle,info)
    def close(self):
        for handle,_ in self.handles:handle.close()


class LocalNarrationCopier:
    def __init__(self,storage):
        # One file per bounded copy: avoid shrinking the legal aggregate unit
        # count with the storyboard copier's visual inventory byte ceiling.
        maximum=source_asset_limit('narration-track',600)
        self.copier=LocalStoryboardCopier(storage,max_file_bytes=maximum,max_total_bytes=maximum)
        self.storage=storage

    def path(self,key):
        return plain(self.storage._io_root/Path(*PurePosixPath(key).parts))

    def verify_pcm(self,path,source,value):
        if source['kind']=='narration-track':
            prepared_pcm(path,value['projection']['duration_seconds'])
        else:
            unit=next(u for u in value['original_narration']['timing'] if u['provider_audio_asset_id']==source['asset_id'])
            pcm(path,validate_evidence(unit['provider_evidence']))

    async def copy(self,value,receipt_id,*,guard):
        copied={}
        for old,source in value['source_assets'].items():
            await guard()
            item={**source,'target_key':target_key(value['workspace_id'],value['child_project_id'],receipt_id,old)}
            result=await self.copier.copy({old:item})
            await completed_read(asyncio.to_thread(self.verify_pcm,self.path(result[old]['object_key']),source,value))
            await guard()
            copied.update(result)
        return copied

    async def verify_all(self,copies,value):
        # Parent and copied bytes remain distinct. A ready row isn't byte proof.
        await self.copier.verify_all(copies,source_items=value['source_assets'])
        def check():
            for old,source in value['source_assets'].items():
                self.verify_pcm(self.path(source['object_key']),source,value)
                self.verify_pcm(self.path(copies[old]['object_key']),source,value)
        await completed_read(asyncio.to_thread(check))

    async def hold(self,copies,value):
        await self.verify_all(copies,value)
        def opened():
            handles=[]
            try:
                for old,source in value['source_assets'].items():
                    for key,project in ((source['object_key'],value['master_project_id']),
                            (copies[old]['object_key'],value['child_project_id'])):
                        proof=RecordedArtifactRead(key,value['workspace_id'],project,source['size_bytes'],
                            source['checksum_sha256'],'local')
                        handles.append(verified_output_handle(self.path(key),proof))
                return HeldNarrationBytes(handles)
            except BaseException:
                for handle,_ in handles:handle.close()
                raise
        return await completed_read(asyncio.to_thread(opened),dispose_cancelled_result=lambda held:held.close())
