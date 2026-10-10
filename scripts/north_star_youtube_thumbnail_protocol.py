"""Pure mock wire rehearsal with a retained original PNG; no application dispatch."""
import argparse,asyncio,hashlib,json,re,sys
from dataclasses import asdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'apps/api'))
import httpx
from app.publishing_wire import OfficialHTTPClient,PublishingWireError
from app.youtube_thumbnail import thumbnail_set_request,thumbnail_set_observation


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as handle:json.dump(value,handle,ensure_ascii=False,indent=2);handle.write('\n')
def tree(root):
    result={}
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise ValueError('Linked evidence not admitted')
        if path.is_file():result[path.relative_to(root).as_posix()]={'sha256':sha(path),'bytes':path.stat().st_size}
    return result


async def run(args):
    source=args.source_root.resolve();out=args.output.resolve();image=args.image.resolve()
    if (source.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-[a-z0-9-]+',source.name) or not source.is_dir()
        or image.is_symlink() or getattr(image,'is_junction',lambda:False)() or source not in image.parents
        or out.exists() or out==ROOT or ROOT in out.parents or out==source or source in out.parents):raise ValueError('Original owned source and distinct fresh evidence required')
    before=tree(source);content=image.read_bytes();expected=args.expected_image_sha256
    if hashlib.sha256(content).hexdigest()!=expected:raise ValueError('Original PNG SHA mismatch')
    out.mkdir(parents=True)
    # Explicit synthetic ID/token/response, never a real account or remote image.
    remote='AbcD_12-345';token='explicit-thumbnail-protocol-fixture-'+'x'*48;calls=[]
    request=thumbnail_set_request(remote,content,token,expected_sha256=expected)
    value={'kind':'youtube#thumbnailSetResponse','etag':'EXPLICIT-SYNTHETIC-ETAG','items':[{
        'default':{'url':f'https://i.ytimg.com/vi/{remote}/default.jpg','width':120,'height':90},
        'high':{'url':f'https://i.ytimg.com/vi/{remote}/hqdefault.jpg'}}]}
    def mock(wire):
        assert wire.method=='POST' and wire.content==content and wire.headers['content-type']=='image/png'
        calls.append({'method':wire.method,'url_sha256':hashlib.sha256(str(wire.url).encode()).hexdigest(),
            'body_sha256':hashlib.sha256(wire.content).hexdigest(),'bytes':len(wire.content),'transport':'in_process_mock'})
        return httpx.Response(200,json=value)
    observed=thumbnail_set_observation(await OfficialHTTPClient('youtube',transport=httpx.MockTransport(mock)).request(request),request)
    assert len(calls)==1 and observed.original_image.sha256==expected and observed.variants[1].width is None
    write(out/'acknowledgement.json',asdict(observed));write(out/'request-observation.json',calls)
    failures=[]
    for mode in ('429','timeout'):
        count=[0]
        def failed(wire):
            count[0]+=1
            if mode=='timeout':raise httpx.ReadTimeout('explicit fixture response lost',request=wire)
            return httpx.Response(429,headers={'Retry-After':'60'},json={'error':{'message':'EXPLICIT_FIXTURE'}})
        try:
            result=await OfficialHTTPClient('youtube',transport=httpx.MockTransport(failed)).request(request)
            thumbnail_set_observation(result,request)
        except PublishingWireError as error:
            assert error.uncertain and count==[1]
            failures.append({'fixture':mode,'code':error.code,'uncertain':error.uncertain,'mock_posts':count[0],'automatic_replay':False})
        else:raise AssertionError('Unconfirmed fixture must not succeed')
    try:await OfficialHTTPClient('youtube').request(request)
    except PublishingWireError as error:assert error.code=='EXTERNAL_PUBLISHING_NOT_ACTIVATED'
    else:raise AssertionError('Default transport must remain off')
    assert tree(source)==before
    write(out/'uncertain-observations.json',failures)
    sources=('apps/api/app/youtube_thumbnail.py','apps/api/tests/test_youtube_thumbnail.py','scripts/north_star_youtube_thumbnail_protocol.py')
    evidence={'schema_version':'north-star-youtube-thumbnail-protocol-rehearsal-v1','status':'PASS','source_sha256':{name:sha(ROOT/name) for name in sources},
        'original_image':asdict(observed.original_image),'original_fixture_tree_sha256':hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
        'original_source_database_media_journals_exact':True,'successful_mock_posts':1,'uncertain_mock_posts':2,'automatic_replays':0,
        'dimensions_missing_are_null':True,'response_bound_to_exact_outgoing_png_and_synthetic_video':True,'default_live_transport_disabled':True,
        'application_dispatch_integrated':False,'durable_intent_response_integrated':False,'official_thumbnail_transport_configured':False,
        'external_calls':0,'paid_operations':0,'remote_image_bytes_verified':False,'rights_independently_verified':False,
        'publishing_authorized':False,'live_credentials_read':False,'real_provider_tested':False,'owner_uat_accepted':False,'production_deployed':False}
    write(out/'evidence.json',evidence)
    print(json.dumps({'status':'PASS','successful_mock_posts':1,'uncertain_mock_posts':2,'original_png_sha256':expected,'external_calls':0}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source-root',type=Path,required=True);parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--expected-image-sha256',required=True);parser.add_argument('--output',type=Path,required=True)
    asyncio.run(run(parser.parse_args()))
