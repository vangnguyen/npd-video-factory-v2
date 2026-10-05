"""Real native MP4 integration using declared test doubles and cached accepted audio.

This tests lineage/pipeline contracts, NOT actual provider integration or human acceptance.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import shutil
import sqlite3
import subprocess
import uuid
from unittest.mock import patch
from PIL import Image,ImageDraw
from services.windows_native.contracts import canonical,digest,file_sha
from services.windows_native.hardening import Artifacts
from services.windows_native.intelligence_lineage import projection
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.media import ingest_media
from services.windows_native.research import PublicWebResearchProvider
from services.windows_native.server import Runner
from services.windows_native.store import Store
from services.windows_native.tests.test_intelligence_workflow import FixtureIdeas

repo=Path(__file__).resolve().parents[1]
root=Path(r'C:\NPD-Video-Factory\post-mvp-validation\phase9-render-contract-20261006-repair1')
report=repo/'evidence/post-mvp-roadmap/phase-9/render-contract.json'
if root.exists() or report.exists(): raise SystemExit('Fresh isolated fixture root required; do not replace evidence')
config=Config(data_root=root);production=Store(root)
proposal=json.loads(Path(r'C:\NPD-Video-Factory\outputs\MVP1\content-proposal.json').read_bytes())
source=Path(r'C:\NPD-Video-Factory\outputs\MVP1\voice.wav')
timing=Path(r'C:\NPD-Video-Factory\phase2-validation\single-media-regression\voice.json')
assert json.loads(timing.read_bytes())['audio_sha256']==file_sha(source)
query='TEST FIXTURE — '+ ' '.join(proposal['narration'].split()[:7])
fixture={'requested_url':'https://example.com/test','final_url':'https://example.com/test','status':200,'content_type':'text/html','raw_sha256':'a'*64,'raw_bytes':len(proposal['narration'].encode('utf-8')),
         'html':'<title>TEST FIXTURE — cached narration, not real market research</title><p>'+proposal['narration']+'</p>'}
service=IntelligenceService(config,production,research_provider=PublicWebResearchProvider(root/'research-sources',fetch=lambda url:fixture),idea_provider=FixtureIdeas())
b=service.create(query,'vietnam-property',['https://example.com/test'])
for action in ('research','ideas'):
    service.enqueue(b['run']['id'],b['run']['version'],action,uuid.uuid4().hex); service.run_one(); b=service.bundle(b['run']['id'])
    assert b['operations'][0]['status']=='SUCCEEDED'
assert len(b['ideas'])==5
idea=b['ideas'][0]; service.select(idea['id'],idea['version'],b['opportunity']['version'],'INTEGRATION FIXTURE — NOT HUMAN ACCEPTANCE')
b=service.bundle(b['run']['id']);brief=service.approve_brief(b['brief']['id'],b['brief']['version'],'INTEGRATION FIXTURE — NOT HUMAN ACCEPTANCE',True,'Contract test only')
p=service.send(brief['id'],brief['version']);assert p['approval'] is None and not p['jobs']
content=production.enqueue(p['id'],p['revision'],'content',uuid.uuid4().hex)
def fixture_generate(config,job,out,stage):
    result={'proposal':proposal,'provider_calls':0,'fixture':True,'human_review_required':True,'facts_verified':False}
    (out/'content-request.json').write_bytes(canonical({'provider':'test_fixture','actual_provider_calls':0}))
    (out/'content-result.json').write_bytes(canonical(result))
    return result
with patch('services.windows_native.pipeline.generate',fixture_generate):
    Runner(production,Pipeline(config)).run_one()
p=production.get(p['id']);assert p['approval'] is None and p['document']['proposal'] is not None,p['jobs'][0].get('error')
fixture_image=root/'fixture-card.png';im=Image.new('RGB',(1080,1920),(31,67,92));draw=ImageDraw.Draw(im)
draw.rectangle((80,280,1000,1400),fill=(64,104,136));draw.text((140,400),'INTELLIGENCE\nLINEAGE TEST\nFIXTURE ONLY',fill='white',font_size=60);im.save(fixture_image)
asset=ingest_media(config,fixture_image,'image/png',fixture_image.name,rights_confirmed=True,illustration=True)
p=production.append_media(p['id'],p['revision'],asset)
p=production.save(p['id'],p['revision'],scene_media=[{'scene':s['scene'],'asset_id':asset['id']} for s in proposal['visual_brief']])
p=production.auto_plan(p['id'],p['revision']);p=production.approve(p['id'],p['revision'],'INTEGRATION FIXTURE — NOT HUMAN ACCEPTANCE',True)
job=production.enqueue(p['id'],p['revision'],'render',uuid.uuid4().hex);out=root/'jobs'/job['id'];out.mkdir(parents=True)
artifacts=Artifacts(out,job);wav=artifacts.publish(source,'voice.wav');meta=artifacts.publish(timing,'voice.json')
artifacts.commit('tts',[wav,meta],{'fixture_seed':'exact cached accepted audio','new_inference':False})
Runner(production,Pipeline(config)).run_one();job=production.get_job(job['id'])
assert job['status']=='succeeded' and job['result']['qc']['passed'],job.get('error')
lineage=projection(job['snapshot']['document']);timeline=json.loads((out/'timeline.json').read_bytes())
assert timeline['metadata']['content_intelligence']==lineage
code="from services.windows_native.store import Store; from services.windows_native.intelligence_lineage import projection; import json,sys; j=Store(sys.argv[1]).get_job(sys.argv[2]); print(json.dumps({'status':j['status'],'lineage':projection(j['snapshot']['document']),'sha':j['result']['qc']['final_sha256']}))"
reopened=json.loads(subprocess.check_output([sys.executable,'-c',code,str(root),job['id']],text=True))
assert reopened['status']=='succeeded' and reopened['lineage']==lineage and reopened['sha']==file_sha(out/'final.mp4')
result={'status':'PASS — technical fixture only','research_input_to_mp4':True,'five_candidates':True,'transparent_scores':True,'human_decisions':'EXPLICIT TEST FIXTURES — NOT OWNER ACCEPTANCE',
        'actual_provider_calls':0,'new_tts_inference_calls':0,'actual_ffmpeg_render':True,'qc':job['result']['qc'],'lineage':lineage,'fresh_process_restart':reopened,
        'final_mp4':str(out/'final.mp4'),'final_sha256':file_sha(out/'final.mp4'),'timeline_sha256':file_sha(out/'timeline.json'),'project_id':p['id'],'job_id':job['id'],'human_final_accepted':False,
        'counts_towards_phase9_practical_production':False}
report.write_bytes(canonical(result)); print(json.dumps({'status':result['status'],'job_id':job['id'],'actual_ffmpeg_render':True,'human_acceptance':False}))
