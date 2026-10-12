"""Isolated actual-browser Mode B fixture with live local workers and mock ASR.

Reuses the preserved CI input, never a historical accepted artifact. All content
and final approvals in this environment are CI actions, not Owner UAT. Real
external dispatch is forbidden; the stop marker exports a recoverable archive.
"""
import argparse
import copy
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'apps/api')]
from app.human_identity import HumanAuthRegistry, HumanAuthVerifier
from services.windows_native import asr
from services.windows_native.access import NativeAccess
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import file_sha, digest
from services.windows_native.hardening import durable_json
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.source_assets import canonical_assets
from services.windows_native.tests.test_human_identity import fixture


def export_candidates(state,out,projects,store):
    for current in projects:
        render=next((job for job in current['jobs'] if job['kind']=='render' and job['status']=='succeeded'
            and job['revision']==current['revision']),None)
        if render is None:continue
        assert render['result']['qc']['passed'] and not render['result']['qc']['human_final_video_accepted']
        bundle=out/'artifact-A-ci'/current['id'];bundle.mkdir(parents=True)
        jobdir=state/'jobs'/render['id']
        for name in ('final.mp4','timeline.json','timeline-render.json','subtitles.json','audio-analysis.json',
                'audio-balance.json','source-audio-clocks.json','render-manifest.json','cost.json',
                'checkpoint-render.json','canonical-audio-mux.json','render-frame-qc.json','source-media-imports.json'):
            shutil.copyfile(jobdir/name,bundle/name)
        shutil.copyfile(jobdir/'qc-report.json',bundle/'qc.json')
        shutil.copytree(jobdir/'render-frame-qc',bundle/'render-frame-qc')
        binding=current['approval']['reviewed_preview']
        preview=state/'shot-previews'/binding['id']/'preview.mp4'
        assert file_sha(preview)==binding['sha256']
        shutil.copyfile(preview,bundle/'preview.mp4')
        selected=current['document']['canonical_timeline']['snapshot']['metadata']['source_analysis_id']
        analysis=next(row['analysis'] for row in current['document']['auto_edit_analyses']
            if row['analysis']['analysis_id']==selected)
        for name,value in [('transcript',analysis['transcript']),('scene-analysis',analysis['scenes']),
                ('highlight-analysis',analysis['highlights']),('silence-decisions',analysis['silence_decisions'])]:
            durable_json(bundle/(name+'.json'),value)
        durable_json(bundle/'asset-provenance.json',{'assets':canonical_assets(current['document']),
            'source_pixels':'generated fixture','speech':'reused local-real TTS; not Owner accepted',
            'ASR':'explicit transport fixture; synthetic word intervals','publishing_enabled':False})
        with store.transaction() as con:
            events=[{**dict(row),'payload':json.loads(row['payload'])} for row in con.execute(
                'SELECT * FROM events WHERE project_id=? ORDER BY id',(current['id'],))]
        durable_json(bundle/'job-events.json',events)
        durable_json(bundle/'project.json',current)
        durable_json(bundle/'render-job.json',render)
        durable_json(bundle/'scope.json',{'actual_browser_worker_render_QC':True,'Owner_UAT':False,
            'artifact_A_real_acceptance':False,'full_Mode_B_ready':False,'real_provider_calls':0,
            'paid_calls':0,'new_TTS_inferences':0,'publishing_enabled':False,'production_deployed':False})
        durable_json(bundle/'exports.json',{str(path.relative_to(bundle)).replace('\\','/'):file_sha(path)
            for path in bundle.rglob('*') if path.is_file()})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--restore-helper',type=Path)
    args=parser.parse_args()
    candidate=args.candidate.resolve();out=args.output.resolve()
    assert not out.exists() and out!=ROOT and ROOT not in out.parents
    original=json.loads((candidate/'evidence.json').read_bytes())
    assert original['ci_chain_passed'] and not original['artifact_A_real_acceptance']
    for relative,sha in original['exports'].items():assert file_sha(candidate/relative)==sha,relative
    project=json.loads((candidate/'project.json').read_bytes())
    words=json.loads((candidate/'fixture-word-intervals.json').read_bytes())['words']
    assets=project['document']['assets']
    video=next(a for a in assets if a['canonical_role']=='video' and a['has_audio'])
    broll=next(a for a in assets if a['canonical_role']=='video' and not a['has_audio'])
    music=next(a for a in assets if a['canonical_role']=='music')
    out.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='vf-mode-b-browser-') as temporary,ExitStack() as stack:
        owned=Path(temporary);state=owned/'state';workspace='wsp_mode_b_browser_fixture'
        config=Config(data_root=state,secret_file=owned/'secrets/absent.env',
            assemblyai_secret_file=owned/'secrets/absent.dpapi')
        inputs=[]
        for role,asset,mime in [('video',video,'video/mp4'),('broll',broll,'video/mp4'),('music',music,'audio/wav')]:
            source=candidate/'originals'/asset['original_id']
            destination=owned/'inputs'/role/source.name
            destination.parent.mkdir(parents=True);shutil.copyfile(source,destination)
            assert file_sha(destination)==asset['source_sha256']
            inputs.append({'role':role,'path':str(destination),'mime':mime,'source_sha256':file_sha(destination)})
        calls=[]
        class FixtureTransport(asr.DurableTransport):
            async def request(self,method,path,credential,timeout,**kwargs):
                calls.append({'method':method,'path':path,'fixture':True})
                durable_json(out/'fixture-provider-calls.json',calls)
                if path=='/v2/upload':return {'upload_url':'https://cdn.assemblyai.com/mode-b-browser-fixture.wav'}
                if path=='/v2/transcript':return {'id':'mode-b-browser-explicit-fixture'}
                assert method=='GET' and path=='/v2/transcript/mode-b-browser-explicit-fixture'
                return {'id':'mode-b-browser-explicit-fixture','status':'completed','language_code':'vi',
                    'speech_model_used':'universal-3-5-pro','text':' '.join(word['text'] for word in words),
                    'words':words,'explicit_test_fixture':True,'alignment_is_not_measured':True}
        original_analyze=asr.analyze
        stack.enter_context(patch.object(asr.connection,'status',return_value={'connected':True,'fixture':True}))
        stack.enter_context(patch.object(asr.connection,'load_credential',return_value='EXPLICIT_BROWSER_FIXTURE_NOT_A_SECRET'))
        stack.enter_context(patch.object(asr.DurableTransport,'request',side_effect=AssertionError('Real ASR forbidden')))
        stack.enter_context(patch.object(asr,'analyze',side_effect=lambda c,j,o,s:original_analyze(c,j,o,s,transport_factory=FixtureTransport)))
        stack.enter_context(patch('services.windows_native.pipeline.generate',side_effect=AssertionError('New AI dispatch forbidden')))
        if args.restore_helper:
            previous=json.loads(args.restore_helper.read_bytes())['backup']
            restore_backup(previous['backup_path'],state,expected_sha256=previous['sha256'])
        raw,registry=fixture('editor',workspace=workspace)
        reviewer_token='vf1.explicit-ci-reviewer.'+'x'*48
        reviewer=copy.deepcopy(registry['tokens']['explicit-fixture'])
        reviewer.update(token_id='explicit-ci-reviewer',token_sha256=hashlib.sha256(reviewer_token.encode()).hexdigest(),
            subject='usr:explicit-ci-reviewer',display_name='CI reviewer fixture — NOT OWNER UAT',workspace_roles={workspace:'reviewer'})
        registry['tokens']['explicit-ci-reviewer']=reviewer
        access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),workspace)
        server=LocalServer(0,config,start_worker=True,access=access)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        durable_json(out/'browser.json',{'url':'http://127.0.0.1:'+str(server.server_port)+'/?new=1',
            'token':raw,'reviewer_fixture_token':reviewer_token,'owned_root':str(owned),'workspace_id':workspace,'inputs':inputs,
            'fixture_human':True,'ASR_fixture':True,'word_intervals_synthetic':True,'worker_started':True,
            'real_provider_calls':0,'paid_calls':0,'new_TTS_inferences':0,'Owner_UAT':False,
            'publishing_enabled':False,'production_deployed':False})
        durable_json(out/'fixture-provider-calls.json',calls)
        print('MODE_B_BROWSER_FIXTURE_READY',flush=True)
        seen=set();deadline=time.monotonic()+2700;failure=None
        try:
            while not (out/'stop').exists():
                if time.monotonic()>deadline:raise TimeoutError('Owned browser fixture deadline reached')
                for row in server.store.list():
                    value=server.store.get(row['id']);key=digest(value)
                    if key not in seen:
                        seen.add(key);target=out/'snapshots'/str(row['id'])/(str(value['revision'])+'-'+key[:12]+'.json')
                        target.parent.mkdir(parents=True,exist_ok=True)
                        durable_json(target,value)
                time.sleep(1)
            projects=[server.store.get(row['id']) for row in server.store.list()]
            assert not any(job['status'] in {'queued','running','retrying'} for p in projects for job in p['jobs']), 'Wait for current worker before stop'
            durable_json(out/'projects.json',projects)
            export_candidates(state,out,projects,server.store)
            backup=create_backup(config,out/'owned-browser-state.zip')
            durable_json(out/'helper.json',{'backup':backup,'project_count':len(projects),'fixture_ASR_requests':len(calls),
                'real_provider_calls':0,'paid_calls':0,'new_TTS_inferences':0,'Owner_UAT':False,
                'publishing_enabled':False,'production_deployed':False,'owned_root_cleanup':'TemporaryDirectory lifecycle after export'})
        except BaseException as error:
            failure={'type':type(error).__name__,'message':str(error),'Owner_UAT':False}
            durable_json(out/'helper-failure.json',failure)
            raise
        finally:
            server.shutdown();server.server_close();thread.join(timeout=10)
            if server.runner.thread.is_alive():server.runner.thread.join(timeout=60)
            if failure is not None:
                durable_json(out/'failed-projects.json',[server.store.get(row['id']) for row in server.store.list()])
                if not server.runner.thread.is_alive():create_backup(config,out/'failed-owned-browser-state.zip')
    print('MODE_B_BROWSER_EXPORTED_AND_OWNED_ROOT_CLEANED',flush=True)


if __name__=='__main__':main()
