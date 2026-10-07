"""Actual synthetic QC/SQLite/AES recovery; official account/processing are mocks."""
import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import sys

from sqlalchemy import select

from north_star_publishing_worker_contract import sha, write
from app.db import CostRecordORM
from app.production_qc import FullProductionQC
from app.publishing_db import PublicationEventORM
from test_publishing_dispatch import fixture_stack
from test_publishing_worker import configured_worker


def child(fixture, root, target, mode):
    code = '''import asyncio,json,sys
from datetime import datetime,timedelta
from pathlib import Path
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
p=json.load(sys.stdin); now=datetime.fromisoformat(p['now']); target=PublishingTargetBinding.model_validate(p['target'])
engine=create_engine(p['database']); factory=create_session_factory(engine)
verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(p['registry']),max_token_ttl_seconds=86400)
journal=PublishingDispatchJournal(factory,identity_provider=lambda:verifier,target_provider=lambda workspace,profile:target,
    require_target_binding=True,clock=lambda:now)
vault=PublishingSessionVault(factory,key_provider=lambda _:SessionEncryptionKey('explicit_fixture',bytes(range(32))),clock=lambda:now)
guard=PublishingArtifactGuard(journal,LocalObjectStorageProvider(Path(p['root'])/'objects'),Path(p['root'])/'private-work')
meter=PublishingOperationMeter(factory,clock=lambda:now); calls=[]
def handle(request):
    calls.append(request.method)
    assert p['mode']=='poll' and request.method=='GET'
    if request.url.path.endswith('/channels'): return httpx.Response(200,json={'items':[{'id':target.target_account_id}]})
    assert request.url.params['id']=='AbcD_12-345'
    return httpx.Response(200,json={'items':[{'id':'AbcD_12-345','status':{'privacyStatus':'private'},
        'processingDetails':{'processingStatus':'succeeded'}}]})
credential=PublishingOAuthCredential(target,now+timedelta(hours=1),frozenset({UPLOAD,READ}),'EXPLICIT_OAUTH_FIXTURE_NOT_A_REAL_TOKEN_1234')
worker=YouTubePublishingWorker(journal=journal,vault=vault,artifact_guard=guard,meter=meter,
    client=OfficialHTTPClient('youtube',transport=httpx.MockTransport(handle)),credential_resolver=lambda _:credential,
    policy_provider=lambda:{'publish_enabled':True,'publish_external_execution_enabled':True,'publish_owner_gate_enabled':True},
    category_id='27',made_for_kids=False,contains_synthetic_media=True)
async def run():
    try:
        result=await (worker.step(p['workspace'],p['publication']) if p['mode']=='recover' else worker.poll_processing(p['workspace'],p['publication']))
        assert (result['phase']=='upload_ready' and calls==[]) if p['mode']=='recover' else (result['mock_publication_complete'] and not result['published'] and calls==['GET','GET'])
        print(json.dumps({'result':result,'mock_requests':calls,'separate_process':True,'new_initializations':0}))
    finally: await engine.dispose()
asyncio.run(run())
'''
    payload = {'database': 'sqlite+aiosqlite:///' + str(fixture['db']), 'now': fixture['clock'][0].isoformat(),
        'target': target.model_dump(mode='json'), 'registry': fixture['verifier'].registry.model_dump(mode='json'),
        'root': str(root), 'workspace': fixture['workspace'], 'publication': fixture['publication'].publication_id, 'mode': mode}
    result = subprocess.run([sys.executable, '-c', code], input=json.dumps(payload), text=True,
        capture_output=True, timeout=60, check=True)
    return json.loads(result.stdout)


async def run(root, output, source, ffmpeg, ffprobe):
    root.mkdir(parents=True, exist_ok=False); output.mkdir(parents=True, exist_ok=False)
    source_sha = sha(source)
    assert source_sha == '80de36cef34e3945a196e32928ee8d77e6a67100810501acfd38c35d99ebca2d'
    generator = fixture_stack.__wrapped__(root / 'project-fixture'); fixture = await anext(generator)
    try:
        worker, _options, receiver, grant, work, _policy = await configured_worker(fixture, root, source_bytes=source.read_bytes())
        worker.chunk_size = 8 * 1024 * 1024
        worker.guard.qc = FullProductionQC(ffprobe_path=str(ffprobe), ffmpeg_path=str(ffmpeg))
        inspect = worker.guard.qc.inspect; reports = []
        async def qc(*args, **kwargs):
            report = await inspect(*args, **kwargs); reports.append(report); return report
        worker.guard.qc.inspect = qc
        original_finish = worker.journal.finish
        async def crash(ticket, **kwargs):
            if kwargs.get('session_ref'): raise RuntimeError('EXPLICIT FIXTURE crash after sealed receipt')
            return await original_finish(ticket, **kwargs)
        worker.journal.finish = crash
        workspace, pub = fixture['workspace'], fixture['publication'].publication_id
        try: await worker.step(workspace, pub)
        except RuntimeError as error: assert str(error).startswith('EXPLICIT FIXTURE')
        else: raise AssertionError('No crash gap simulated')
        worker.journal.finish = original_finish
        orphan = await worker.journal.get(workspace, pub); assert orphan['phase'] == 'init_uncertain'
        await fixture['stack'].engine.dispose()
        recovered = child(fixture, root, receiver.target, 'recover')
        assert recovered['mock_requests'] == [] and receiver.initializations == 1
        uploaded = await worker.step(workspace, pub); assert uploaded['phase'] == 'uploaded'
        received = root / 'explicit-mock-receiver.mp4'; received.write_bytes(receiver.received)
        assert sha(received) == source_sha
        await worker.journal.revoke(workspace, grant['publish_approval_id'], principal=fixture['principals']['owner'])
        await fixture['stack'].engine.dispose()
        processed = child(fixture, root, receiver.target, 'poll')
        assert processed['result']['receipt']['mock'] and processed['result']['receipt']['remote_url'] is None
        assert len(reports) == 2 and all(value['status'] == 'passed' for value in reports)
        assert sha(source) == source_sha and list(work.iterdir()) == []
        async with worker.journal.session_factory() as session:
            costs = (await session.scalars(select(CostRecordORM).where(CostRecordORM.provenance['source'].as_string() == 'publishing-wire-admission'))).all()
            events = (await session.scalars(select(PublicationEventORM).where(PublicationEventORM.publication_id == pub))).all()
        assert len(costs) == 6 and all(cost.actual_cost is None for cost in costs)
        write(output / 'recovery.json', {'orphan': orphan, 'separate_process_recovery': recovered, 'one_initialization': True})
        write(output / 'processing.json', {'uploaded': uploaded, 'separate_process_processing': processed, 'official_response_is_mock': True})
        write(output / 'media-qc.json', {'reports': reports, 'actual_av_quality': True, 'timeline_subtitle_approval_inputs_are_fixtures': True})
        write(output / 'source.json', {'source': str(source), 'sha256': source_sha, 'bytes': source.stat().st_size,
            'receiver_sha256': sha(received), 'source_unchanged': True, 'synthetic_pattern_and_sine_only': True,
            'not_a_video_factory_final_render': True, 'not_owner_uat': True})
        write(output / 'cost.json', {'request_intents': len(costs), 'actual_costs': None, 'all_mock': True})
        write(output / 'events.json', [{'type': value.event_type, 'payload': value.payload_json} for value in events])
    finally: await generator.aclose()
    exported = ''.join(path.read_text(encoding='utf-8') for path in output.glob('*.json'))
    assert all(value not in exported for value in ('Bearer ', 'EXPLICIT_PRIVATE_FIXTURE', 'private_session_ref'))
    write(output / 'receipt.json', {'schema': 'publishing-completion-contract-v1', 'status': 'PASS',
        'actual_full_qc_runs': 2, 'separate_processes': 2, 'mock_requests': 6, 'initializations': 1,
        'actual_provider_requests': 0, 'paid_operations': 0, 'real_credentials_read': 0,
        'mock_publication_complete': True, 'published': False, 'owner_uat_accepted': False,
        'publishing_ready': False, 'production_deployed': False,
        'exports_sha256': {path.name: sha(path) for path in sorted(output.glob('*.json'))}})
    print(json.dumps({'status': 'PASS', 'exports': 7, 'separate_processes': 2, 'mock_requests': 6,
        'initializations': 1, 'published': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('fixture-root', 'output-root', 'source', 'ffmpeg', 'ffprobe'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.fixture_root.resolve(), args.output_root.resolve(), args.source.resolve(), args.ffmpeg.resolve(), args.ffprobe.resolve()))
