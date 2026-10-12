"""Only owned local media fixtures; independent SFX tone, no provider call."""
import json,subprocess
from pathlib import Path
from services.windows_native.contracts import file_sha
from services.windows_native.hardening import durable_json
from services.windows_native.tests.test_source_media_tracks import upload

def run_sfx_controller(case,server,cookie,csrf,context,out,original):
    path=case.owned/'owned-synthetic-3000hz-SFX.wav'
    subprocess.run([str(case.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i',
        'sine=frequency=3000:duration=1','-ar','48000','-ac','1','-c:a','pcm_s16le',str(path)],check=True,capture_output=True,timeout=20)
    asset=upload(case,path.read_bytes(),'audio','audio/wav');current=case.store.get(case.project['id'])
    after={p.relative_to(case.root).as_posix():file_sha(p) for name in ('assets','originals') for p in (case.root/name).rglob('*') if p.is_file()}
    if any(after.get(p)!=digest for p,digest in original.items()):raise AssertionError('Earlier physical source changed while uploading SFX')
    durable_json(context,{'fixture_human':True,'origin':'http://127.0.0.1:'+str(server.server_port),'workspace_id':case.workspace,
        'project':{'id':current['id'],'revision':current['revision']},'cookie':cookie,'csrf':csrf,'sfx_asset_id':asset['id'],'sfx_asset_sha256':asset['sha256']})
    repo=Path(__file__).resolve().parents[1]
    result=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(repo/'scripts/native_media_sfx_http_ui.mjs'),str(context)],capture_output=True,timeout=60)
    if result.returncode:raise AssertionError(result.stderr.decode('utf-8',errors='replace')[:6000])
    proof=json.loads(result.stdout);durable_json(out/'sfx-controller.json',proof)
    if len(proof['requests'])!=2 or proof['saved']['mutation']['asset_sha256']!=asset['sha256']:raise AssertionError('SFX controller receipt differs from uploaded source')
    return after,proof
