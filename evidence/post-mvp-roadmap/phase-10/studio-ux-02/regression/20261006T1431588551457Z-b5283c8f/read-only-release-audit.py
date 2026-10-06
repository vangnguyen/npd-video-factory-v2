"""Append-only release audit. Live databases use sqlite mode=ro; HTTP is GET only."""
from datetime import datetime, timezone
import hashlib
import http.cookiejar
import importlib.metadata
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import types
import urllib.request
import wave

REPO=Path('C:/NPD-Video-Factory/source')
sys.path.insert(0,str(REPO))
from scripts.phase10_baseline_support import tables
from services.windows_native.contracts import canonical,digest,file_sha,PROFILE_SHA
from services.windows_native.pipeline import Config,verify_runtime
from services.windows_native import branding,warm_voice
from services.windows_native.voice_quality import registered_policy,resolve_policy
OUTPUT=Path(__file__).resolve().parent
BASELINE=REPO/'evidence/post-mvp-roadmap/phase-10/baseline.json'
baseline=json.loads(BASELINE.read_bytes())
cfg=Config()
fixed_receipts=[BASELINE,REPO/'scripts/phase10-verify-preservation.py',
    REPO/'evidence/post-mvp-roadmap/phase-10/preservation-verification.json',
    REPO/'evidence/post-mvp-roadmap/phase-10/final-preservation-verification.json']
fixed_before={str(p):file_sha(p) for p in fixed_receipts}
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
def write(name,value):
    dest=OUTPUT/name
    assert dest.parent==OUTPUT and not dest.exists()
    with dest.open('xb') as f:f.write(canonical(value))
def state():
    return {name:tables(cfg.data_root/(name+'.sqlite3')) for name in baseline['backups']}
before=state()
write('live-tables-before.json',before)
frozen=[{'path':p,'expected_sha256':sha,'actual_sha256':file_sha(REPO/p)}
        for p,sha in baseline['frozen_evidence'].items()]
write('frozen-evidence-comparison.json',frozen)
print(json.dumps({'step':'baseline','tables_equal':{k:v==baseline['backups'][k]['tables'] for k,v in before.items()},
                  'frozen_count':len(frozen),'frozen_equal':all(r['actual_sha256']==r['expected_sha256'] for r in frozen)}),flush=True)
dependencies=sorted([{'name':d.metadata['Name'],'version':d.version} for d in importlib.metadata.distributions()],key=lambda d:d['name'].lower())
runtime=verify_runtime(cfg,full=True)
write('runtime-verification.json',{'dependencies':dependencies,'dependencies_unchanged':dependencies==baseline['runtime_dependencies'],
                                  'runtime':runtime,'runtime_equals_baseline':runtime==baseline['runtime_verification']})
print(json.dumps({'step':'runtime','dependencies_unchanged':dependencies==baseline['runtime_dependencies']}),flush=True)
# Execute only the frozen pure configuration module; no Store/provider/process creation.
source=subprocess.check_output(['git','show',baseline['head_sha']+':services/windows_native/branding.py'],cwd=REPO,text=True)
old=types.ModuleType('services.windows_native._approved_branding_for_readonly_audit')
old.__file__=str(REPO/'services/windows_native/branding.py');old.__package__='services.windows_native'
sys.modules[old.__name__]=old
exec(compile(source,old.__file__,'exec'),old.__dict__)
original_catalog=old.catalog()
now_catalog=branding.catalog()
brand_checks=[]
for brand in original_catalog['brands']:
    for template in original_catalog['templates']:
        previous=old.choose(brand['id'],template['id'])
        current=branding.choose(brand['id'],template['id'])
        brand_checks.append({'brand_id':brand['id'],'template_id':template['id'],
                             'before_sha256':digest(previous),'current_sha256':digest(current),'exact':current==previous})
catalog_bytes=subprocess.check_output(['git','show',baseline['head_sha']+':services/windows_native/profiles/catalog.json'],cwd=REPO)
policy_bytes=subprocess.check_output(['git','show',baseline['head_sha']+':services/windows_native/voice-quality-policies.json'],cwd=REPO)
policies=json.loads(policy_bytes)
current_policies=json.loads((REPO/'services/windows_native/voice-quality-policies.json').read_bytes())
presets={'default_fixed_selections':brand_checks,
         'shared_catalog_brand_template_lists_exact':all(now_catalog[k]==original_catalog[k] for k in ('brands','templates')),
         'business_catalog_config_bytes_unchanged':catalog_bytes==(REPO/'services/windows_native/profiles/catalog.json').read_bytes(),
         'voice_policy_registry_bytes_unchanged':policy_bytes==(REPO/'services/windows_native/voice-quality-policies.json').read_bytes(),
         'voice_policy_registry_objects_unchanged':policies==current_policies,
         'warm_policy_sha256':digest(registered_policy(warm_voice.POLICY_ID)),
         'warm_policy_expected_sha256':'d4194a33720ee9def789d05d2cedaaf2e9775f3b4702be9b429e1b4ceb8bcce2',
         'missing_voice_quality_uses_legacy_default':resolve_policy({}) is None,'profile_sha256':PROFILE_SHA}
write('fixed-defaults-and-voice-policy.json',presets)
# Recompute reviewed boundaries from actual archived ASR + original waveforms, without calls or writes.
onsets=REPO/'evidence/post-mvp-roadmap/phase-9/9k/audio-repair-02'
manifest=json.loads((onsets/'onset-review-manifest.json').read_bytes())
import numpy as np
b_checks=[]
for pair in manifest['pairs']:
    folder=onsets/f"case-{pair['case']:02}"/f"scene-{pair['scene']:02}"
    trial=json.loads((folder/'trial.json').read_bytes())
    transcript=json.loads((folder/'transcript.json').read_bytes())
    previous=json.loads((folder/'boundary.json').read_bytes())
    original_wave=Path('C:/NPD-Video-Factory/post-mvp-validation/phase9k-onset-20261006')/f"warm-sentence-case-{pair['case']:02}"/f"scene-{pair['scene']:02}"/'with-context.wav'
    plan={'target_text':trial['target_text'],'context_text':trial['approved_previous_sentence_context']}
    measured=warm_voice.trim_boundary(plan,warm_voice.read_wave(original_wave),{'transcript':transcript})
    expected=round(pair['B_context_cut_seconds']*warm_voice.RATE)
    actual=measured['removed_samples']
    b_checks.append({'case':pair['case'],'scene':pair['scene'],'source_path':str(original_wave),
                     'source_sha256':file_sha(original_wave),'expected_source_sha256':pair['B_source_voice_sha256'],
                     'expected_cut_samples':expected,'archived_cut_samples':previous['removed_samples'],
                     'current_cut_samples':actual,'difference_samples':actual-expected,
                     'source_exact':file_sha(original_wave)==pair['B_source_voice_sha256'],
                     'cut_exact':actual==expected==previous['removed_samples'],'method':measured['method'],
                     'new_provider_calls':0})
write('eight-reviewed-b-boundaries.json',{'manifest_path':str(onsets/'onset-review-manifest.json'),
      'manifest_sha256':file_sha(onsets/'onset-review-manifest.json'),'checks':b_checks,
      'all_exact_zero_sample_difference':all(r['source_exact'] and r['cut_exact'] for r in b_checks)})
# Authentication remains in memory; neither cookie nor CSRF token is persisted.
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
jar=http.cookiejar.CookieJar()
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar),NoRedirect())
base='http://127.0.0.1:8026'
def get(path,headers=None):
    assert path.startswith('/api/') and '?' not in path
    req=urllib.request.Request(base+path,headers={'Origin':base,**(headers or {})},method='GET')
    with opener.open(req,timeout=90) as response:
        return response.status,dict(response.headers),response.read()
status,headers,raw=get('/api/session')
session=json.loads(raw)
write('session-metadata.json',{'status':status,'session_acquired':bool(list(jar)),'capabilities':session.get('capabilities'),
       'cookie_persisted':False,'csrf_persisted':False,'base_url':base})
# Existing projects are opened through the already running main service. Never instantiate its Store.
with sqlite3.connect((cfg.data_root/'workflow.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as con:
    con.row_factory=sqlite3.Row
    project_rows=[dict(r) for r in con.execute('SELECT id,revision,document,approval FROM projects ORDER BY id')]
project_checks=[]
for row in project_rows:
    code,_,body=get('/api/projects/'+row['id'])
    response=json.loads(body); saved_doc=json.loads(row['document'])
    saved_approval=json.loads(row['approval']) if row['approval'] else None
    project_checks.append({'project_id':row['id'],'http_status':code,'expected_revision':row['revision'],
        'actual_revision':response['revision'],'document_sha256':digest(response['document']),
        'expected_document_sha256':digest(saved_doc),'document_exact':response['document']==saved_doc,
        'approval_exact':response.get('approval')==saved_approval,'jobs_read':len(response.get('jobs',[])),
        'write_requests':0})
write('original-projects-open.json',project_checks)
videos=[]
for index,value in enumerate(baseline['accepted_videos'],1):
    path=Path(value['path']); jid=path.parent.name
    original=path.read_bytes(); sha=hashlib.sha256(original).hexdigest()
    probe_raw=subprocess.check_output([str(cfg.ffmpeg_bin/'ffprobe.exe'),'-v','error','-show_streams','-show_format','-of','json',str(path)],timeout=30)
    probe=json.loads(probe_raw)
    with (OUTPUT/f'{index:02}-{jid}-ffprobe.json').open('xb') as f:f.write(probe_raw)
    video=next(s for s in probe['streams'] if s['codec_type']=='video')
    audio=next(s for s in probe['streams'] if s['codec_type']=='audio')
    code,headers,body=get('/api/jobs/'+jid+'/final')
    rcode,rheaders,rbody=get('/api/jobs/'+jid+'/final',{'Range':'bytes=0-1023'})
    checks={'source_hash_unchanged':sha==value['sha256'],'http200_byte_exact':code==200 and body==original,
            'range206_byte_exact':rcode==206 and rbody==original[:1024],
            'canvas_portrait':(video['width'],video['height'])==(1080,1920),
            'h264_aac':(video['codec_name'],audio['codec_name'])==('h264','aac'),
            'fps_30':video['avg_frame_rate']=='30/1','audio_48khz':audio['sample_rate']=='48000'}
    videos.append({'job_id':jid,'phase':value['phase'],'path':str(path),'expected_sha256':value['sha256'],'actual_sha256':sha,
                   'bytes':len(original),'duration_seconds':float(probe['format']['duration']),'checks':checks,
                   'http':{'status':code,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()},
                   'range':{'status':rcode,'bytes':len(rbody),'sha256':hashlib.sha256(rbody).hexdigest(),
                            'content_range':rheaders.get('Content-Range')},
                   'ffprobe_raw_sha256':hashlib.sha256(probe_raw).hexdigest(),'passed':all(checks.values()),
                   'technical_accessibility_only':True,'new_human_listening_performed':False})
    print(json.dumps({'step':'video','number':index,'passed':videos[-1]['passed']}),flush=True)
write('prior15-accessibility.json',videos)
after=state();write('live-tables-after.json',after)
fixed_after={str(p):file_sha(p) for p in fixed_receipts}
comparisons={k:after[k]==before[k]==baseline['backups'][k]['tables'] for k in before}
passed=all(comparisons.values()) and all(r['actual_sha256']==r['expected_sha256'] for r in frozen) and all(v['passed'] for v in videos) and dependencies==baseline['runtime_dependencies'] and runtime==baseline['runtime_verification'] and all(r['exact'] for r in brand_checks) and all(presets[k] for k in ('shared_catalog_brand_template_lists_exact','business_catalog_config_bytes_unchanged','voice_policy_registry_bytes_unchanged','voice_policy_registry_objects_unchanged','missing_voice_quality_uses_legacy_default')) and presets['warm_policy_sha256']==presets['warm_policy_expected_sha256'] and all(r['source_exact'] and r['cut_exact'] for r in b_checks) and all(r['http_status']==200 and r['actual_revision']==r['expected_revision'] and r['document_exact'] and r['approval_exact'] for r in project_checks) and fixed_before==fixed_after
summary={'verified_at':datetime.now(timezone.utc).isoformat(),'baseline_sha':baseline['head_sha'],'current_head_sha':head,
         'uncommitted_code_audit':True,'regression_status':'PASS' if passed else 'FAIL',
         'original_main_live_tables_exact_before_after':comparisons,'frozen_evidence_files':len(frozen),
         'frozen_evidence_unchanged':all(r['actual_sha256']==r['expected_sha256'] for r in frozen),
         'old_accepted_videos':len(videos),'old_accepted_hashes_ffprobe_http200_range206_passed':sum(v['passed'] for v in videos),
         'existing_projects_opened_unchanged':sum(r['document_exact'] and r['approval_exact'] and r['actual_revision']==r['expected_revision'] for r in project_checks),
         'locked_runtime_dependencies_unchanged':dependencies==baseline['runtime_dependencies'] and runtime==baseline['runtime_verification'],
         'default_fixed_selection_comparisons':len(brand_checks),'default_fixed_selections_exact':all(r['exact'] for r in brand_checks),
         'voice_policy_sha256':presets['warm_policy_sha256'],'accepted_eight_b_cuts_exact_zero_samples':all(r['source_exact'] and r['cut_exact'] for r in b_checks),
         'original_helper_and_fixed_receipts_unchanged':fixed_before==fixed_after,'fixed_receipt_hashes':fixed_after,
         'prior_phase8_INTERNAL_PRODUCTION_READY':'YES','prior_phase9_CONTENT_INTELLIGENCE_READY':'YES',
         'new_phase10_owner_audio_acceptance':'REJECTED_PENDING_REPAIR','new_human_acceptance':False,
         'http_write_requests':0,'main_application_writes':0,'main_service_restarts':0,'provider_calls':0,'production_calls':0,
         'preservation_only_no_new_quality_certification':True,'passed':passed}
write('summary.json',summary)
print(json.dumps(summary),flush=True)
assert passed

