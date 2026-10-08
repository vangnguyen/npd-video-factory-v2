"""Retain dedicated OAuth protocol proofs over four explicit synthetic token wires."""
import argparse,asyncio,hashlib,json,sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode,parse_qs
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.tests.test_google_oauth_protocol import client,NOW,TOKEN,REFRESH,SECRET,CODE
from app.google_oauth_protocol import authorization,exchange_request,refresh_request,parse_tokens,GoogleOAuthTokenClient,TOKEN_URL
from services.windows_native.contracts import digest,file_sha
import httpx

def write(path,value):
    raw=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    for private in (TOKEN,REFRESH,SECRET,CODE):assert private not in raw
    with path.open('x',encoding='utf-8',newline='\n') as h:h.write(raw)
async def run(out):
    out=out.resolve()
    if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('Fresh external OAuth fixture evidence required')
    out.mkdir(parents=True);proofs=[];operations=[];calls=[]
    for purpose in ('analytics','publishing'):
        c=client(purpose);flow=authorization(c,'http://127.0.0.1:18047/oauth/google/callback',now=NOW)
        public_url=flow.url(NOW);params=parse_qs(public_url.partition('?')[2]);assert params['code_challenge_method']==['S256']
        assert set(params['scope'][0].split())==c.scopes and params['state']==[flow.state]
        for private in (TOKEN,REFRESH,SECRET,CODE,flow.verifier):assert private not in public_url
        request=exchange_request(flow,urlencode({'state':flow.state,'code':CODE}),now=NOW)
        def wire(r):
            assert r.method=='POST' and str(r.url)==TOKEN_URL and 'authorization' not in r.headers
            body=dict(parse_qs(r.content.decode('ascii')));assert body['client_id']==[c.client_id] and body['client_secret']==[SECRET]
            calls.append({'purpose':purpose,'operation':body['grant_type'][0],'request_sha256':hashlib.sha256(r.content).hexdigest(),'endpoint':'google-fixed-token-endpoint','mock':True})
            result={'access_token':TOKEN,'expires_in':3600,'token_type':'Bearer','scope':' '.join(sorted(c.scopes))}
            if body['grant_type']==['authorization_code']:result['refresh_token']=REFRESH
            else:assert body['refresh_token']==[REFRESH]
            return httpx.Response(200,json=result)
        http=GoogleOAuthTokenClient(transport=httpx.MockTransport(wire));response=await http.send(c,request,now=NOW);initial=parse_tokens(c,request,response,now=NOW)
        stamp=NOW+timedelta(hours=2);refresh=refresh_request(c,initial,now=stamp);response=await http.send(c,refresh,now=stamp);renewed=parse_tokens(c,refresh,response,now=stamp,previous=initial)
        assert renewed.refresh_token==initial.refresh_token==REFRESH and renewed.expires_at==stamp+timedelta(hours=1) and initial.expires_at==NOW+timedelta(hours=1)
        assert renewed.refresh_expires_at is None and initial.refresh_expires_at is None
        assert type(initial.credential(c,now=NOW)).__name__==('AnalyticsOAuthCredential' if purpose=='analytics' else 'PublishingOAuthCredential')
        for g in (initial,renewed):
            proof=g.public(c);assert proof['mock'] and all(proof[k] is False for k in ('token_returned','account_verified','publishing_enabled','production_consent_renewed','real_provider_tested'));proofs.append(proof)
        operations.append({'purpose':purpose,'initial_grant_sha256':digest(initial.public(c)),'renewed_grant_sha256':digest(renewed.public(c)),
            'refresh_without_returned_refresh_token_preserves_original':True,'original_access_expiry_unchanged':True,'new_production_consent_created':False,'automatic_retry':False,
            'state_sha256':hashlib.sha256(flow.state.encode()).hexdigest(),'s256_challenge_sha256':digest(params['code_challenge'][0])})
    assert len(calls)==4 and len(proofs)==4
    write(out/'grant-proofs.json',proofs);write(out/'protocol-operations.json',operations);write(out/'mock-wire-summary.json',calls)
    sources=('apps/api/app/google_oauth_protocol.py','services/windows_native/tests/test_google_oauth_protocol.py','scripts/north_star_google_oauth_protocol.py')
    write(out/'evidence.json',{'schema_version':'google-oauth-protocol-rehearsal-v1','dedicated_purposes':['analytics','publishing'],'grant_proofs':4,'mock_token_requests':4,
        'state_pkce_exact_target_client_scope_expiry_and_original_refresh_preserved':True,'account_verified':False,'production_consent_renewed':False,'token_returned':False,
        'default_runtime_activated':False,'new_secret_custody_or_callback_claims_implemented':False,'real_secret_reads':0,'external_provider_calls':0,'paid_operations':0,'real_publications':0,
        'real_audience_observations':0,'new_media_operations':0,'browser_owner_provider_production_acceptance':False,'explicit_synthetic_protocol_credentials':True,
        'source_sha256':{name:file_sha(ROOT/name) for name in sources},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status':'PASS','mock_token_requests':4,'grant_proofs':4,'external_calls':0,'real_secret_reads':0,'production_consent_renewed':False}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();asyncio.run(run(args.output))
