"""Isolated Native browser harness: synthetic media and explicit ASR fixture only."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.hardening import durable_json
from services.windows_native.media import ingest_media
from services.windows_native.pipeline import Config, Pipeline
from services.windows_native.server import LocalServer, Runner
from services.windows_native.tests.test_auto_edit_analysis import saved_asr
from services.windows_native.windows_job import contain_process_tree, lock_data_root


class LocalOnlyPipeline(Pipeline):
    def run(self, job, stage):
        if job['kind'] != 'auto_edit_analysis':
            raise WorkflowError('EXPLICIT_FIXTURE_LOCAL_ANALYSIS_ONLY')
        return super().run(job, stage)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    root = args.data_root.resolve()
    if root.parent != Path('C:/') or not root.name.startswith('vf-native-fixture-') or root.exists():
        raise ValueError('fresh isolated Native fixture root required')
    absent_secrets = root.parent / (root.name + '-absent-secrets')
    config = Config(data_root=root, secret_file=absent_secrets/'absent-openai.env', assemblyai_secret_file=absent_secrets/'absent-asr.dpapi')
    contain_process_tree()
    root.mkdir()
    with lock_data_root(root), LocalServer(args.port, config, pipeline=LocalOnlyPipeline(config), start_worker=False) as server:
        source = root/'synthetic-tone-not-speech.mp4'
        subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'), '-v', 'error', '-nostdin', '-n',
            '-f', 'lavfi', '-i', 'testsrc2=s=320x240:r=30:d=6', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3',
            '-af', 'adelay=1000,apad=whole_dur=6', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-t', '6', str(source)], check=True, timeout=30)
        asset = ingest_media(config, source, 'video/mp4', 'Synthetic footage — fixture only.mp4', rights_confirmed=True, illustration=False)
        project = server.store.create('Auto Edit — explicit local fixture', '', 'media', production_quality=True)
        project = server.store.append_media(project['id'], project['revision'], asset)
        with server.store.transaction() as con:
            document=project['document']; document['media_analysis']=[saved_asr(asset)]
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?', (json.dumps(document,ensure_ascii=False),project['id']))
            server.store.version(con,project['id'])
        project=server.store.get(project['id'])
        job=server.store.enqueue(project['id'],project['revision'],'auto_edit_analysis',uuid.uuid4().hex)
        assert server.runner.run_one()
        job=server.store.get_job(job['id'])
        if job['status']!='succeeded':raise RuntimeError(job['error'])
        durable_json(root/'fixture.json', {'explicit_fixture':True,'provider_dispatch':False,'new_tts_inference':False,
            'human_acceptance':False,'project_id':project['id'],'job_id':job['id'],'source_sha256':file_sha(source),
            'url':f'http://127.0.0.1:{args.port}/?project={project["id"]}'})
        print(f'Isolated Native analysis fixture ready at http://127.0.0.1:{args.port}/?project={project["id"]}',flush=True)
        server.serve_forever()


if __name__=='__main__':
    main()
