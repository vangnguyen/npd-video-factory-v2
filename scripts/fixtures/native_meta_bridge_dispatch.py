"""Fresh producer process for a marked synthetic local Meta Bridge rehearsal."""
import argparse,http.client,json,math,os,sys
from pathlib import Path
from unittest.mock import patch
REPO=Path(__file__).resolve().parents[2];sys.path[:0]=[str(REPO),str(REPO/'apps/api')]
from app.bridge_auth import SigningKeyring
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from app.publishing_wire import OfficialHTTPClient
from services.windows_native.access import NativeAccess
from services.windows_native.bridge_transport import FixtureWebhookTransport,BridgeResponse
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer
from services.windows_native.tests.test_human_identity import fixture as human_fixture

KEYS={'fixture-v1':b'explicit-meta-webhook-fixture-key-only-001',
      'fixture-v2':b'explicit-meta-webhook-fixture-key-only-002'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True)
    parser.add_argument('--workspace',required=True);parser.add_argument('--port',required=True,type=int)
    parser.add_argument('--clock',required=True,type=float);parser.add_argument('--key-id',choices=tuple(KEYS),default='fixture-v1')
    parser.add_argument('--crash-after-accept',action='store_true');args=parser.parse_args()
    root=Path(args.root).resolve();marker=json.loads((root/'.vf-meta-bridge-fixture.json').read_bytes())
    assert marker=={'workspace':args.workspace,'nonplayable_media_fixture':True,'real_provider_calls':0,'Owner_UAT':False}
    assert 0<args.port<65536 and math.isfinite(args.clock)
    config=Config(data_root=root,runtime_root=root.parent/'dispatch-runtime',secret_file=root.parent/'dispatch-private/missing.env',
        assemblyai_secret_file=root.parent/'dispatch-private/missing.dpapi',ffmpeg_bin=root.parent/'missing-ffmpeg')
    with (patch.object(OfficialHTTPClient,'request',side_effect=AssertionError('No provider dispatch')),
          patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No credential decryption'))):
        _,registry=human_fixture('owner',workspace=args.workspace)
        verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400)
        server=LocalServer(0,config,start_worker=False,access=NativeAccess(verifier,args.workspace))
        bridge=server.bridge;bridge.clock=lambda:args.clock
        def send(body,headers):
            con=http.client.HTTPConnection('127.0.0.1',args.port,timeout=10)
            try:
                con.request('POST','/agent-hub/events/v1',body=body,headers=headers);response=con.getresponse()
                assert len(response.read(65537))<=65536
                if args.crash_after_accept and 200<=response.status<300:
                    print(json.dumps({'fixture':True,'interrupted_after_recipient_commit':True,'pid':os.getpid()}),flush=True)
                    os._exit(71)
                retry=response.getheader('Retry-After','')
                return BridgeResponse(response.status,min(3600,int(retry)) if retry.isdigit() else None)
            finally:con.close()
        transport=FixtureWebhookTransport(send);transport.endpoint=f'fixture-http://127.0.0.1:{args.port}/agent-hub/events/v1'
        bridge.configure_delivery(transport=transport,signing=SigningKeyring(args.key_id,KEYS),enabled=True)
        try:
            identity=bridge.process()
            print(json.dumps({'fixture':True,'event_id':identity,'pid':os.getpid(),'key_id':args.key_id,'real_provider_calls':0}),flush=True)
        finally:server.server_close()


if __name__=='__main__':main()
