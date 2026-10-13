"""Fresh-process read-only SQL/Local restore proof for owned variant fixtures."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path,PurePosixPath
import shutil
import stat
import sys
import zipfile

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'scripts'),str(REPO/'apps/api'),str(REPO/'apps/api/tests')]
from north_star_sql_variant_source_render import owned_root,plain,sha,write,rows
from app.auto_edit_source_custody import staged_trusted_video
from app.auto_edit_repository import AutoEditRepository
from app.repositories import PlatformRepository
from app.production_repository import ProductionRepository
from app.sql_variant_repository import SqlVariantFamilyRepository
from app.sql_variant_uploaded_repository import SqlUploadedDerivationRepository
from app.sql_variant_models import canonical
from app.object_storage import LocalObjectStorageProvider,validate_object_key
from app.db import create_engine,create_session_factory
from types import SimpleNamespace


def extract(backup,root):
    with zipfile.ZipFile(backup) as archive:
        entries=archive.infolist()
        if len(entries)>10000 or sum(i.file_size for i in entries)>512*1024*1024:
            raise ValueError('S6_RESTORE_ARCHIVE_LIMIT')
        if len({i.filename for i in entries})!=len(entries):raise ValueError('S6_RESTORE_DUPLICATE_ENTRY')
        required={'dev.db','fixture-configuration.json'}
        if not required.issubset({i.filename for i in entries}):raise ValueError('S6_RESTORE_SCHEMA_REQUIRED')
        for item in entries:
            name=PurePosixPath(item.filename)
            if name.is_absolute() or '..' in name.parts or '\\' in item.filename or item.is_dir() \
                    or stat.S_ISLNK(item.external_attr>>16):raise ValueError('S6_RESTORE_ENTRY_UNSAFE')
            if item.filename not in required:
                if not item.filename.startswith('objects/'):raise ValueError('S6_RESTORE_ENTRY_UNKNOWN')
                validate_object_key(item.filename.removeprefix('objects/'))
            target=root.joinpath(*name.parts)
            target.parent.mkdir(parents=True,exist_ok=True);plain(target.parent)
            with archive.open(item) as source,target.open('xb') as destination:
                shutil.copyfileobj(source,destination,1024*1024)
            if target.stat().st_size!=item.file_size:raise ValueError('S6_RESTORE_SIZE_MISMATCH')
        return len(entries)


async def verify(args):
    backup=plain(Path(args.backup))
    if sha(backup)!=args.sha:raise ValueError('S6_RESTORE_TRUSTED_HASH_REQUIRED')
    result=json.loads(Path(args.mode_result).read_text(encoding='utf-8'))
    if result['backup_sha256']!=args.sha or result['owner_uat'] is not False or result['tts_calls']!=0:
        raise ValueError('S6_RESTORE_FIXTURE_BINDING_REQUIRED')
    root=owned_root(args.root);count=extract(backup,root)
    config=json.loads((root/'fixture-configuration.json').read_text())
    if config!={key:value for key,value in result.items() if key!='backup_sha256'}:
        raise ValueError('S6_RESTORE_ARCHIVE_RESULT_BINDING_CHANGED')
    expected=json.loads(Path(args.sql_rows).read_text(encoding='utf-8'))
    db=root/'dev.db';database_before=sha(db)
    # URI read-only mode; no DDL, worker, seed, dispatch or provider construction.
    engine=create_engine('sqlite+aiosqlite:///file:'+db.as_posix()+'?mode=ro&uri=true')
    factory=create_session_factory(engine)
    value=SimpleNamespace(factory=factory)
    assets=AutoEditRepository(factory);platform=PlatformRepository(factory);production=ProductionRepository(factory)
    families=SqlVariantFamilyRepository(factory);derivations=SqlUploadedDerivationRepository(families)
    storage=LocalObjectStorageProvider(root/'objects')
    staged=[];verified=[]
    try:
        if await rows(value)!=expected:raise ValueError('S6_RESTORE_SQL_ROWS_CHANGED')
        family=await families.get(result['workspace_id'],result['master_project_id'],result['family_id'])
        if family is None or not family.source_current:raise ValueError('S6_RESTORE_MASTER_FAMILY_CHANGED')
        for child in result['children']:
            package=await production.get_package(child['project_id'])
            if package is None or package.workspace_id!=result['workspace_id'] or package.approval is None:
                raise ValueError('S6_RESTORE_CHILD_PACKAGE_CHANGED')
            final=package.latest_final_render;review=package.latest_review_render
            if final is None or final.status!='ready' or final.qc_status!='passed' or review is None \
                    or review.qc_status!='passed' or final.approval_id!=package.approval.approval_id:
                raise ValueError('S6_RESTORE_FINAL_REVIEW_PROOF_CHANGED')
            if package.approval.reviewer_ref!='fixture-reviewer-no-human-listening-claim' \
                    or 'AUTOMATED FIXTURE DECISION ONLY' not in package.approval.decision_comment:
                raise ValueError('S6_RESTORE_APPROVAL_FIXTURE_REQUIRED')
            final_asset=await assets.get_asset(final.output_asset_id);review_asset=await assets.get_asset(review.output_asset_id)
            if sha(storage._path(final_asset.object_key))!=child['final_sha256'] \
                    or sha(storage._path(review_asset.object_key))!=child['review_sha256']:
                raise ValueError('S6_RESTORE_ACCEPTED_FIXTURE_BYTES_CHANGED')
            warm_receipt=json.loads((Path(child['path'])/'derivation-receipt.json').read_text())
            receipt=await derivations.get(result['workspace_id'],result['master_project_id'],result['family_id'],warm_receipt['receipt_id'])
            if receipt is None or receipt.model_dump(mode='json')!=warm_receipt:
                raise ValueError('S6_RESTORE_DERIVATION_RECEIPT_CHANGED')
            for original,imported in receipt.result['asset_map'].items():
                asset=await assets.get_asset(imported)
                if asset.provenance.get('rights_status')!='unknown':raise ValueError('S6_RESTORE_RIGHTS_TRANSFERRED')
                async with staged_trusted_video(assets,storage,child['project_id'],imported,root/'cold-stage',8*1024*1024) as (path,snapshot):
                    if sha(path)!=asset.checksum_sha256 or snapshot['upload_id'] is not None \
                            or snapshot['derivative_custody']['new_scan_claimed'] is not False:
                        raise ValueError('S6_RESTORE_DERIVATIVE_SOURCE_CHANGED')
                    staged.append(dict(asset_id=imported,source_asset_id=original,sha256=sha(path),
                        source_clock=snapshot['media_metadata'],historical_scan_only=True,provider_calls=0))
            verified.append(dict(project_id=child['project_id'],final_sha256=child['final_sha256'],
                review_sha256=child['review_sha256'],profile=final.profile,qc_status=final.qc_status,
                child_fixture_approval_independent=True,publishing_allowed=final.publishing_allowed))
        if await rows(value)!=expected:raise ValueError('S6_RESTORE_READ_MUTATED_SQL')
    finally:await engine.dispose()
    if sha(db)!=database_before:raise ValueError('S6_RESTORE_DATABASE_BYTES_CHANGED')
    output=dict(schema_version='sql-variant-source-cold-restore.v1',result='PASS',
        backup_sha256=args.sha,archive_entries=count,owned_root=str(root),
        restored_database_sha256=database_before,sqlite_read_only=True,sql_rows_byte_equivalent=True,
        verified_children=verified,source_staging=staged,provider_calls=0,model_inferences=0,
        renderer_calls=0,external_network_calls=0,worker_started=False,ddl_executed=False,
        original_source_rewritten=False,owner_uat=False,fixture_approval_only=True,
        production_deployed=False,protected_roots_touched=False,deleted_paths=[])
    write(args.output,output)
    print(json.dumps(dict(result='PASS',children=len(verified),archive_entries=count,
        output_sha256=sha(args.output),provider_calls=0,owner_uat=False)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('backup','sha','mode-result','sql-rows','root','output'):parser.add_argument('--'+name,required=True)
    asyncio.run(verify(parser.parse_args()))
