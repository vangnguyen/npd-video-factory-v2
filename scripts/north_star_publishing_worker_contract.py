"""Actual synthetic media/QC/AES/SQLite; all identity/account/transport inputs are fixtures."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api/tests'))
from app.db import CostRecordORM, ProviderUsageORM
from app.production_qc import FullProductionQC
from app.publishing_db import PublicationEventORM
from app.publishing_wire import PublishingWireError
from test_publishing_dispatch import fixture_stack
from test_publishing_worker import configured_worker


def sha(path):
    with path.open('rb') as handle: return hashlib.file_digest(handle, 'sha256').hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2); handle.write('\n')


def restarted(fixture, root, target, received_path):
    source = '''import asyncio,json,sys,hashlib
from datetime import datetime,timedelta
import httpx
from app.db import create_engine,create_session_factory
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from app.object_storage import LocalObjectStorageProvider
from app.publishing_artifact import PublishingArtifactGuard
from app.publishing_credentials import PublishingOAuthCredential,UPLOAD,READ
from app.publishing_dispatch import PublishingDispatchJournal
from app.publishing_models import PublishingTargetBinding
from app.publishing_operations import PublishingOperationMeter
from app.publishing_session_vault import PublishingSessionVault,SessionEncryptionKey
from app.publishing_wire import OfficialHTTPClient
from app.publishing_worker import YouTubePublishingWorker
from pathlib import Path
p=json.load(sys.stdin); now=datetime.fromisoformat(p['now']); target=PublishingTargetBinding.model_validate(p['target'])
engine=create_engine(p['database']); factory=create_session_factory(engine)
verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(p['registry']),max_token_ttl_seconds=86400)
journal=PublishingDispatchJournal(factory,identity_provider=lambda:verifier,target_provider=lambda workspace,profile:target,
    require_target_binding=True,clock=lambda:now)
vault=PublishingSessionVault(factory,key_provider=lambda _:SessionEncryptionKey('explicit_fixture',bytes(range(32))),clock=lambda:now)
guard=PublishingArtifactGuard(journal,LocalObjectStorageProvider(Path(p['root'])/'objects'),Path(p['root'])/'private-work')
meter=PublishingOperationMeter(factory,clock=lambda:now); requests=[]
async def handle(request):
    requests.append(request.method)
    if request.method=='GET':
        return httpx.Response(200,json={'items':[{'id':target.target_account_id}]})
    if request.method!='PUT' or not request.headers['content-range'].startswith('bytes */') or request.content:
        raise AssertionError('Restart attempted another mutation')
    raw=Path(p['received']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==p['source_sha256']
    return httpx.Response(200,json={'id':'AbcD_12-345'})
credential=PublishingOAuthCredential(target,now+timedelta(hours=1),frozenset({UPLOAD,READ}),'EXPLICIT_OAUTH_FIXTURE_NOT_A_REAL_TOKEN_1234')
worker=YouTubePublishingWorker(journal=journal,vault=vault,artifact_guard=guard,meter=meter,
    client=OfficialHTTPClient('youtube',transport=httpx.MockTransport(handle)),credential_resolver=lambda _:credential,
    policy_provider=lambda:{'publish_enabled':True,'publish_external_execution_enabled':True,'publish_owner_gate_enabled':True},
    category_id='27',made_for_kids=False,contains_synthetic_media=True)
async def run():
    try:
        result=await worker.step(p['workspace'],p['publication'])
        assert result['phase']=='uploaded'
        print(json.dumps({'state':result,'mock_requests':requests,'separate_process':True,'new_initializations':0,'published':False}))
    finally:
        await engine.dispose()
asyncio.run(run())
'''
    payload = {'database': 'sqlite+aiosqlite:///' + str(fixture['db']), 'now': fixture['clock'][0].isoformat(),
        'target': target.model_dump(mode='json'), 'registry': fixture['verifier'].registry.model_dump(mode='json'),
        'root': str(root), 'received': str(received_path), 'source_sha256': sha(received_path),
        'workspace': fixture['workspace'], 'publication': fixture['publication'].publication_id}
    return json.loads(subprocess.check_output([sys.executable, '-c', source], input=json.dumps(payload).encode(),
        cwd=ROOT / 'apps/api', timeout=60))


async def run(root, output, source, ffmpeg, ffprobe):
    root.mkdir(parents=True, exist_ok=False); output.mkdir(parents=True, exist_ok=False)
    original_sha = sha(source)
    assert original_sha == '80de36cef34e3945a196e32928ee8d77e6a67100810501acfd38c35d99ebca2d'
    generator = fixture_stack.__wrapped__(root / 'project-fixture'); fixture = await anext(generator)
    try:
        worker, _options, receiver, grant, work, _policy = await configured_worker(fixture, root,
            source_bytes=source.read_bytes(), lose_final=True)
        worker.chunk_size = 8 * 1024 * 1024
        worker.guard.qc = FullProductionQC(ffprobe_path=str(ffprobe), ffmpeg_path=str(ffmpeg))
        inspect = worker.guard.qc.inspect; reports = []
        async def recording_qc(*args, **kwargs):
            report = await inspect(*args, **kwargs); reports.append(report); return report
        worker.guard.qc.inspect = recording_qc
        workspace, pub = fixture['workspace'], fixture['publication'].publication_id
        initialized = await worker.step(workspace, pub); assert initialized['phase'] == 'upload_ready'
        try:
            await worker.step(workspace, pub)
        except PublishingWireError as error:
            assert error.code == 'PUBLISHING_NETWORK_OUTCOME_UNKNOWN'
        else: raise AssertionError('Fixture did not lose the final response')
        uncertain = await worker.journal.get(workspace, pub); assert uncertain['phase'] == 'chunk_uncertain'
        assert bytes(receiver.received) == source.read_bytes() and receiver.initializations == 1
        received = root / 'explicit-mock-receiver.mp4'; received.write_bytes(receiver.received)
        await worker.journal.revoke(workspace, grant['publish_approval_id'], principal=fixture['principals']['owner'])
        await fixture['stack'].engine.dispose()
        restart = restarted(fixture, root, receiver.target, received)
        assert restart['new_initializations'] == 0 and restart['mock_requests'] == ['GET', 'PUT']
        assert len(reports) == 2 and all(report['status'] == 'passed' and report['width'] == 1080 and report['height'] == 1920 for report in reports)
        assert sha(source) == original_sha and list(work.iterdir()) == []
        write(output / 'media-qc.json', {'reports': reports, 'actual_av_quality': True, 'approval_timeline_subtitle_inputs_are_fixtures': True})
        write(output / 'wire-restart.json', {'initialized': initialized, 'lost_final': uncertain, 'restart': restart,
            'parent_mock_requests': receiver.requests, 'initializations': receiver.initializations, 'received_sha256': sha(received)})
        async with fixture['stack'].repository.session_factory() as session:
            usage = (await session.scalars(select(ProviderUsageORM).where(ProviderUsageORM.capability == 'publishing'))).all()
            costs = (await session.scalars(select(CostRecordORM).where(CostRecordORM.provenance['source'].as_string() == 'publishing-wire-admission'))).all()
            events = (await session.scalars(select(PublicationEventORM).where(PublicationEventORM.publication_id == pub))).all()
        assert len(costs) == 6 and all(cost.actual_cost is None for cost in costs)
        write(output / 'cost-operations.json', {'requests': [{'usage_id': row.usage_id, 'operation': row.operation, 'status': row.status,
            'model': row.model, 'job_id': row.job_id, 'metadata': row.metadata_json} for row in usage],
            'costs': [{'cost_id': row.cost_id, 'estimated_cost': None, 'actual_cost': None, 'currency': row.currency,
                'needs_approval': row.needs_approval, 'provenance': row.provenance} for row in costs]})
        write(output / 'events.json', [{'type': row.event_type, 'actor': row.actor_ref, 'payload': row.payload_json} for row in events])
        write(output / 'source.json', {'path': str(source), 'sha256': original_sha, 'bytes': source.stat().st_size,
            'receiver': str(received), 'receiver_sha256': sha(received), 'synthetic_pattern_and_sine_only': True,
            'source_unchanged': True, 'not_a_video_factory_final_render': True, 'not_owner_uat': True})
    finally: await generator.aclose()
    serialized = ''.join(path.read_text(encoding='utf-8') for path in output.glob('*.json'))
    assert 'Bearer ' not in serialized and 'EXPLICIT_PRIVATE_FIXTURE' not in serialized and 'private_session_ref' not in serialized
    write(output / 'receipt.json', {'schema': 'north-star-publishing-worker-contract-v1', 'status': 'PASS',
        'actual_full_media_qc_runs': 2, 'actual_byte_range_verification': True, 'actual_aes_and_sqlite': True,
        'separate_process_reconciliation': True, 'mock_requests': 6, 'initializations': 1,
        'actual_provider_requests': 0, 'real_credentials_read': 0, 'paid_operations': 0, 'actual_costs': None,
        'fixture_only': ['identity', 'account', 'OAuth/key', 'production/publish approval', 'provider receipt', 'timeline/subtitle QC inputs'],
        'processing_acceptance': 'NOT_CHECKED', 'published': False, 'owner_uat_accepted': False, 'publishing_ready': False,
        'production_deployed': False, 'exports_sha256': {path.name: sha(path) for path in sorted(output.glob('*.json'))}})
    print(json.dumps({'status': 'PASS', 'exports': 6, 'media_bytes': source.stat().st_size, 'mock_requests': 6,
        'initializations': 1, 'separate_process_reconciliation': True, 'published': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('fixture-root', 'output-root', 'source', 'ffmpeg', 'ffprobe'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.fixture_root.resolve(), args.output_root.resolve(), args.source.resolve(), args.ffmpeg.resolve(), args.ffprobe.resolve()))
