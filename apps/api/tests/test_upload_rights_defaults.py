"""Upload labels never infer ownership; old explicit claims remain unchanged.

Owned SQLite/storage and real WAV bytes/stdlib decode; no external provider or
legal verification. This is a default-policy test, not rights certification.
"""
import hashlib

import pytest

from app.auto_edit_models import UploadCompleteRequest, UploadInitRequest
from app.publishing_logic import validate_rights
from test_auto_edit_analysis import setup_services, bytes_stream
from test_uploaded_audio import WaveProbe, wav_bytes


@pytest.mark.parametrize('kind,mime', [
    ('video','video/mp4'), ('audio','audio/wav'), ('image','image/png'),
    ('logo','image/png'), ('music','audio/mpeg'), ('subtitle','text/vtt'),
])
def test_omitted_upload_rights_never_claim_ownership(kind, mime):
    payload=UploadInitRequest(project_id='prj_rights_default',filename='fixture.bin',
        media_kind=kind,content_type=mime,size_bytes=100)
    assert payload.rights_status=='unknown'
    assert 'rights_status' not in payload.model_fields_set


async def complete_audio(uploads, project, raw, rights=None):
    checksum=hashlib.sha256(raw).hexdigest()
    body=dict(project_id=project.project_id,filename='right-use-not-ownership.wav',
        media_kind='audio',content_type='audio/wav',size_bytes=len(raw),checksum_sha256=checksum)
    if rights is not None:body.update(rights_status=rights,license='explicit-fixture-claim')
    upload=await uploads.initialize(UploadInitRequest(**body))
    for part in range(1,upload.total_parts+1):
        value=raw[(part-1)*upload.part_size_bytes:part*upload.part_size_bytes]
        await uploads.store_part(upload.upload_id,part,bytes_stream(value),
            expected_part_sha256=hashlib.sha256(value).hexdigest())
    return await uploads.complete(upload.upload_id,UploadCompleteRequest(checksum_sha256=checksum))


@pytest.mark.asyncio
async def test_default_unknown_persists_through_chunk_commit_and_reopen_and_blocks_publish(tmp_path):
    engine,sessions,platform,repo,uploads,_,project,_=await setup_services(tmp_path)
    try:
        uploads.media_probe=WaveProbe();raw=wav_bytes()
        completed=await complete_audio(uploads,project,raw)
        assert completed.upload.rights_status=='unknown'
        asset=await repo.get_asset(completed.asset_id)
        assert asset.provenance['rights_status']=='unknown'
        assert asset.provenance['source_type']=='user_upload'
        assert asset.checksum_sha256==hashlib.sha256(raw).hexdigest()
        assert asset.provenance['media_metadata']['audio_sample_rate']==16000
        assert validate_rights([asset]).status=='failed'
        # Fresh repository/session reads the persisted source, not the request DTO.
        from app.auto_edit_repository import AutoEditRepository
        reopened=await AutoEditRepository(sessions).get_asset(asset.asset_id)
        assert reopened.model_dump()==asset.model_dump()
        assert (await AutoEditRepository(sessions).get_upload(completed.upload.upload_id)).rights_status=='unknown'
        assert validate_rights([reopened]).checks[0].code=='RIGHTS_NOT_VERIFIED'
    finally:await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('rights',['owned','licensed'])
async def test_explicit_claims_remain_explicit_and_unclaimed_duplicate_cannot_relabel_old_asset(tmp_path,rights):
    engine,sessions,platform,repo,uploads,_,project,_=await setup_services(tmp_path)
    try:
        uploads.media_probe=WaveProbe();raw=wav_bytes()
        original=await complete_audio(uploads,project,raw,rights)
        old=await repo.get_asset(original.asset_id)
        duplicate=await complete_audio(uploads,project,raw)
        assert duplicate.duplicate is True and duplicate.asset_id==old.asset_id
        assert duplicate.upload.rights_status=='unknown'
        after=await repo.get_asset(old.asset_id)
        assert after.model_dump()==old.model_dump()
        assert after.provenance['rights_status']==rights
        assert validate_rights([after]).status=='passed'
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_explicit_claim_on_duplicate_cannot_upgrade_original_unknown_asset(tmp_path):
    engine,sessions,platform,repo,uploads,_,project,_=await setup_services(tmp_path)
    try:
        uploads.media_probe=WaveProbe();raw=wav_bytes()
        original=await complete_audio(uploads,project,raw)
        before=await repo.get_asset(original.asset_id)
        duplicate=await complete_audio(uploads,project,raw,'owned')
        assert duplicate.duplicate is True and duplicate.asset_id==original.asset_id
        after=await repo.get_asset(original.asset_id)
        assert after.model_dump()==before.model_dump()
        assert after.provenance['rights_status']=='unknown'
        assert validate_rights([after]).status=='failed'
    finally:await engine.dispose()
