"""Retain local PCM/QC and offline recovery proof; fixtures never grant Owner UAT."""
from dataclasses import replace
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import wave
from unittest.mock import patch

from services.windows_native import audio_balance
from services.windows_native.backup import create_backup, restore_backup
from services.windows_native.contracts import digest, file_sha, write_json
from services.windows_native.pipeline import Config, Pipeline, REPO
from services.windows_native.server import Runner
from services.windows_native.store import Store


def replay(path,output=None):
    output=output or path.parent/'new-process-replay.json'
    assert not output.exists()
    record=json.loads(path.read_bytes());config=Config.load(record['config'])
    store=Store(config.data_root);job=store.get_job(record['job_id'])
    with patch('services.windows_native.pipeline.verify_runtime'),patch(
            'services.windows_native.pipeline.synthesize',side_effect=AssertionError('No new inference allowed')):
        result=Pipeline(config).run(job,lambda _:None)
    assert result==job['result'] and file_sha(config.data_root/'jobs'/job['id']/'final.mp4')==record['final_sha256']
    measured=audio_balance.validate_qc(config.data_root/'jobs'/job['id'],result['qc'],digest(job['snapshot']['document']))
    assert measured['status']=='passed'
    store.final_video(job['id'])
    write_json(output,{'status':'PASS','final_sha256':record['final_sha256'],
        'recomputed_preserved_pcm':True,'new_decodes':0,'new_inference_calls':0,'external_provider_calls':0,
        'paid_operations':0,'owner_uat_accepted':False})


def synthetic(root,mode):
    if mode=='source':
        from services.windows_native.tests.test_source_render import NativeSourceRenderTests
        case=NativeSourceRenderTests('test_real_source_worker_qc_checkpoint_keeps_media_immutable_and_requires_final_review')
    else:
        from services.windows_native.tests.test_narrated_music import NarratedMusicTests
        case=NarratedMusicTests('test_preview_and_final_use_exact_same_music_bed_and_pcm_source_without_inference')
    case.setUp()
    try:
        if mode=='source':case.review_fixture()
        else:
            case.ready();case.audible(case.project)
            case.project=case.store.approve(case.project['id'],case.project['revision'],'EXPLICIT TONE/MUSIC FIXTURE; NOT OWNER UAT',True)
        job=case.store.enqueue(case.project['id'],case.project['revision'],'render',uuid.uuid4().hex)
        with patch('services.windows_native.pipeline.verify_runtime'),patch(
                'services.windows_native.pipeline.synthesize',side_effect=AssertionError('No new inference allowed')):
            assert Runner(case.store,Pipeline(case.config)).run_one()
        job=case.store.get_job(job['id']);assert job['status']=='succeeded',job['error']
        case.store.review_render(job['id'],job['revision'],'AUTOMATED FIXTURE; NOT OWNER UAT',True,'approve')
        job=case.store.get_job(job['id']);folder=case.root/'jobs'/job['id']
        measured=audio_balance.validate_qc(folder,job['result']['qc'],digest(job['snapshot']['document']))
        assert measured['status']=='passed'
        destination=root/mode;destination.mkdir()
        archive=destination/'offline-backup.zip';receipt=create_backup(case.config,archive)
        write_json(destination/'backup.json',receipt)
        restored=destination/'restored';restore_backup(archive,restored,expected_sha256=file_sha(archive))
        config=replace(case.config,data_root=restored,secret_file=destination/'disabled-no-keys'/'openai.env',
            assemblyai_secret_file=destination/'disabled-no-keys'/'assemblyai.dpapi')
        write_json(destination/'replay-config.json',config.dump())
        record={'config':str(destination/'replay-config.json'),'job_id':job['id'],'project_id':job['project_id'],
            'final_sha256':file_sha(folder/'final.mp4'),'audio_balance_sha256':file_sha(folder/audio_balance.REPORT)}
        write_json(destination/'replay.json',record)
        process=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--replay',str(destination/'replay.json')],
            cwd=REPO,capture_output=True,timeout=180)
        (destination/'new-process-replay.log').write_bytes(process.stdout+process.stderr)
        assert process.returncode==0,process.stderr[-1000:]
        return {**record,'status':'PASS','backup_sha256':file_sha(archive),'backup_bytes':archive.stat().st_size,
            'reference_role':measured['reference_role'],'original_pcm_and_media_exact':True,
            'new_process_keyless_recovery_exact':True,'asr_fixture':mode=='source','tts_tone_fixture':mode!='source',
            'human_review_fixture':True,'owner_uat_accepted':False,'real_provider_tested':False}
    finally:case.tearDown()


def sample(root,source):
    import numpy as np
    job=json.loads((source/'render-job.json').read_bytes());old=json.loads((source/'render-manifest.json').read_bytes())
    assert old['music'] is None and old['voice_audio_file']=='render-voice.wav'
    original={name:file_sha(source/name) for name in ('final.mp4','render-voice.wav','render-manifest.json','render-job.json')}
    destination=root/'prior-local-tts-sample';destination.mkdir()
    for name in ('final.mp4','render-voice.wav'):shutil.copyfile(source/name,destination/name)
    shutil.copyfile(source/'render-manifest.json',destination/'source-render-manifest.json')
    with wave.open(str(destination/'render-voice.wav'),'rb') as f:
        assert f.getsampwidth()==2
        data=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(np.float64)/32768
    gain=min(10**(-19/20)/float(np.sqrt(np.mean(data**2))),.90/float(np.max(np.abs(data))))
    duration=old['duration_seconds']
    filters=audio_balance.narrated_stems(Config(),destination,duration=duration,voice_file='render-voice.wav',music_file=None,
        voice_filters=f'[1:a]volume={gain:.8f},adelay=0,apad,atrim=duration={duration:.4f}[a]',music_gain=.12,canonical_fades=False)
    write_json(destination/'render-manifest.json',{'schema':'prior-local-tts-independent-audio-audit-v1',
        'source_render_manifest_sha256':original['render-manifest.json'],'source_final_sha256':original['final.mp4'],
        'duration_seconds':duration,'audio_balance_inputs':{'reference_role':'narrated_voice',
        'reference_sha256':file_sha(destination/audio_balance.REFERENCE),'music_sha256':None,
        'filter_graph_sha256':digest(filters),'diagnostic_filter_threads':1,
        'diagnostic_pass':'independent_audio_only_same_source_and_dsp'},'owner_uat_accepted':False})
    measured=audio_balance.inspect(Config(),destination,duration=duration,document_sha256=digest(job['snapshot']['document']),
        manifest_name='render-manifest.json',reference_role='narrated_voice')
    audio_balance.validate(destination,measured,duration=duration,document_sha256=digest(job['snapshot']['document']),
        manifest_name='render-manifest.json',reference_role='narrated_voice')
    assert original=={name:file_sha(source/name) for name in original}
    return {'status':'PASS','source_directory':str(source),'source_sha256':original,'duration_seconds':duration,
        'audio_balance_sha256':file_sha(destination/audio_balance.REPORT),'prior_local_tts_pcm_reused':True,
        'new_render_performed':False,'new_inference_calls':0,'new_provider_calls':0,'owner_listening_accepted':False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);parser.add_argument('--sample-directory',type=Path)
    parser.add_argument('--replay',type=Path);parser.add_argument('--replay-output',type=Path);args=parser.parse_args()
    if args.replay:replay(args.replay,args.replay_output);return
    assert args.output and args.sample_directory and not args.output.exists()
    root=args.output.absolute();assert REPO!=root and REPO not in root.parents
    root.mkdir(parents=True)
    report={'schema':'north-star-measured-audio-balance-local-proof-v1','status':'PASS',
        'source':synthetic(root,'source'),'narrated':synthetic(root,'narrated'),'prior_local_tts':sample(root,args.sample_directory),
        'external_provider_calls':0,'new_paid_operations':0,'owner_uat_accepted':False,'production_deployed':False,
        'full_mode_a_b_accepted':False}
    write_json(root/'evidence.json',report);print(json.dumps({'status':report['status'],'evidence':str(root/'evidence.json')}))


if __name__=='__main__':main()
