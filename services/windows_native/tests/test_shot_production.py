"""Actual FFmpeg transport tests; synthetic PCM/provider fixtures are not UAT."""
import copy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import wave
import numpy as np
from PIL import Image
from services.windows_native.contracts import digest,file_sha,WorkflowError
from services.windows_native.pipeline import Config,render
from services.windows_native.branding import resolve,choose,catalog
from services.windows_native.store import Store
from services.windows_native.server import LocalServer
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.shot_render_timing import retime_voice
from services.windows_native.shot_ai_edit import ShotAIEdit
from services.windows_native.asset_association import mutate as asset_mutate


def prepared(root):
    config=Config(data_root=root); store=Store(root)
    project=store.create('Isolated Phase10 fixture','No live provider calls')
    proposal={'narration':'Xin chào. Cảm ơn.','visual_brief':[
        {'scene':1,'visual':'Ảnh thứ nhất','on_screen_text':'Chào bạn','narration_excerpt':'Xin chào.'},
        {'scene':2,'visual':'Ảnh thứ hai','on_screen_text':'Cảm ơn bạn','narration_excerpt':'Cảm ơn.'}], 'facts_needing_source':['Synthetic local fixture, not factual research']}
    project=store.save(project['id'],project['revision'],proposal=proposal)
    (root/'assets').mkdir(exist_ok=True)
    for i,color in enumerate(((20,60,85),(65,45,25),(25,65,50))):
        path=root/'assets'/('fixture'+str(i)+'.jpg'); Image.new('RGB',(480,640),color).save(path)
        project=store.append_media(project['id'],project['revision'],{'id':path.name,'kind':'image','filename':path.name,
            'sha256':file_sha(path),'rights_confirmed':True,'illustration':True})
    project=store.auto_plan(project['id'],project['revision'])
    project=store.mutate_shots(project['id'],project['revision'],{'type':'update','shot_id':store.shot_view(project['id'])['shot_timeline']['shots'][0]['shot_id'],'values':{'duration':4}})
    project=store.mutate_shots(project['id'],project['revision'],{'type':'update','shot_id':project['shot_timeline']['shots'][1]['shot_id'],'values':{'duration':4}})
    return config,store,project


def voice(out):
    out.mkdir(exist_ok=True)
    samples=(np.sin(np.arange(57600)*2*np.pi*220/48000)*6000).astype('<i2')
    with wave.open(str(out/'voice.wav'),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000);wav.writeframes(samples.tobytes())
    from services.windows_native.contracts import PROFILE_SHA
    meta={'profile_sha256':PROFILE_SHA,'audio_sha256':file_sha(out/'voice.wav'),'duration_seconds':1.2,'units':[
        {'index':0,'scene':1,'text':'Xin chào.','start_seconds':0,'end_seconds':.6,'activity_start_seconds':.01,'activity_end_seconds':.59},
        {'index':1,'scene':2,'text':'Cảm ơn.','start_seconds':.6,'end_seconds':1.2,'activity_start_seconds':.61,'activity_end_seconds':1.19}]}
    (out/'voice.json').write_text(json.dumps(meta),encoding='utf-8')
    return meta,samples


class ShotProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.cfg,self.store,self.project=prepared(self.root)
    def tearDown(self): self.temp.cleanup()

    def test_requested_timing_consumes_durations_preserves_pcm_and_original(self):
        out=self.root/'retiming'; meta,samples=voice(out); original=file_sha(out/'voice.wav'); brand,template=resolve(self.project['document'])
        result=retime_voice(self.project['document'],meta,out,brand,template)
        self.assertEqual(result['duration_seconds'],8); self.assertEqual(file_sha(out/'voice.wav'),original)
        with wave.open(str(out/'render-voice.wav'),'rb') as wav: actual=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2')
        self.assertTrue(np.array_equal(actual[52800:81600],samples[:28800]))
        self.assertTrue(np.array_equal(actual[192000:220800],samples[28800:]))
        self.assertEqual(result['scene_layout'][0]['end'],4); self.assertTrue(result['sample_preserving_placement'])
        short=self.store.mutate_shots(self.project['id'],self.project['revision'],{'type':'update','shot_id':self.project['shot_timeline']['shots'][0]['shot_id'],'values':{'duration':.5}})
        with self.assertRaisesRegex(WorkflowError,'NARRATION_OVERFLOW'): retime_voice(short['document'],meta,out,brand,template)
        self.assertIsNone(retime_voice({'proposal':self.project['document']['proposal']},meta,out,brand,template))

    def test_real_portrait_render_consumes_canonical_timing_and_subtitle(self):
        out=self.root/'render-portrait'; meta,_=voice(out)
        project=self.store.mutate_shots(self.project['id'],self.project['revision'],{'type':'update','shot_id':self.project['shot_timeline']['shots'][0]['shot_id'],'values':{'subtitle':'Chữ do người biên tập sửa'}})
        snapshot={'document':project['document'],'approval':{'snapshot_sha256':digest(project['document']),'reviewer':'AUTOMATED SYNTHETIC FIXTURE ONLY'}}
        report=render(self.cfg,snapshot,out)
        self.assertTrue(report['passed']); self.assertAlmostEqual(report['duration_seconds'],8,places=1)
        self.assertFalse(report['human_final_video_accepted'])
        timeline=json.loads((out/'timeline.json').read_bytes())
        self.assertEqual(timeline['metadata']['canonical_timeline']['sha256'],project['document']['canonical_timeline']['sha256'])
        self.assertIn('Chữ do người biên tập sửa',(out/'subtitles.ass').read_text(encoding='utf-8'))
        self.assertEqual(file_sha(out/'voice.wav'),meta['audio_sha256'])

    def test_actual_landscape_template_render_and_canvas_validation(self):
        self.assertEqual(len(catalog()['templates']),12); self.assertEqual(len(catalog(True)['templates']),24)
        project=self.store.set_brand(self.project['id'],self.project['revision'],'vang-nguyen','personal-30-landscape')
        project=self.store.mutate_shots(project['id'],project['revision'],{'type':'update','shot_id':self.project['shot_timeline']['shots'][1]['shot_id'],'values':{'duration':26}})
        self.assertEqual(project['shot_timeline']['snapshot']['width'],1920)
        out=self.root/'render-landscape';voice(out)
        report=render(self.cfg,{'document':project['document'],'approval':{'snapshot_sha256':digest(project['document'])}},out)
        self.assertTrue(report['checks']['landscape_1920x1080'])
        self.assertEqual(json.loads((out/'timeline.json').read_bytes())['aspect_ratio'],'16:9')

    def test_preview_cache_only_rebuilds_changed_shot_and_never_approves(self):
        manager=PreviewManager(self.cfg,self.store); value=manager.generate(self.project['id'],self.project['revision'])
        def wait():
            for _ in range(150):
                value=manager.status(self.project['id'])
                if value['status'] not in {'QUEUED','RUNNING'}: return value
                time.sleep(.1)
            self.fail('Proxy timeout')
        first=wait();self.assertEqual(first['status'],'READY');self.assertEqual(first['new_proxy_shots'],2)
        self.assertFalse(first['final_approval_eligible']);self.assertEqual(first['tts_calls'],0)
        newer=self.store.mutate_shots(self.project['id'],self.project['revision'],{'type':'update','shot_id':self.project['shot_timeline']['shots'][0]['shot_id'],'values':{'asset_id':'fixture2.jpg'}})
        self.assertEqual(manager.status(newer['id'])['status'],'STALE')
        with self.assertRaisesRegex(WorkflowError,'STALE'): manager.video_path(newer['id'],first['timeline_version'])
        manager.generate(newer['id'],newer['revision']); second=wait()
        self.assertEqual(second['status'],'READY');self.assertEqual(second['cached_shots'],1);self.assertEqual(second['new_proxy_shots'],1)
        self.assertIsNone(self.store.get(newer['id'])['approval'])

    def test_asset_tags_soft_remove_and_used_guard_preserve_originals(self):
        before={p.name:file_sha(p) for p in (self.root/'assets').iterdir()}
        project=asset_mutate(self.store,self.project['id'],self.project['revision'],'fixture2.jpg','tag',['Ảnh dự án'])
        project=asset_mutate(self.store,project['id'],project['revision'],'fixture2.jpg','remove')
        self.assertEqual({p.name:file_sha(p) for p in (self.root/'assets').iterdir()},before)
        with self.assertRaisesRegex(WorkflowError,'USED_REPLACE'): asset_mutate(self.store,project['id'],project['revision'],'fixture0.jpg','remove')

    def test_ai_fixture_suggestion_explicit_apply_no_mutation_cached_no_replay(self):
        calls=[]
        def provider(context):
            calls.append(context)
            return {'values':{'visual':None,'narration':'Chào bạn.','on_screen_text':None,'subtitle':None,'duration':None,'asset_id':None},'rationale':'Test-only fixture','uncertainty':'Not real provider integration'},{'fixture':True,'calls':1}
        ai=ShotAIEdit(self.cfg,self.store,provider=provider); shot=self.project['shot_timeline']['shots'][0]['shot_id']; before=self.store.get(self.project['id'])
        value=ai.suggest(before['id'],before['revision'],shot,'Viết ngắn hơn','fixture-request-01')
        self.assertEqual(self.store.get(before['id']),before);self.assertTrue(value['requires_human_apply'])
        self.assertEqual(ai.suggest(before['id'],before['revision'],shot,'Viết ngắn hơn','fixture-request-01'),value);self.assertEqual(len(calls),1)
        applied=self.store.mutate_shots(before['id'],before['revision'],value['operation'])
        self.assertEqual(applied['shot_timeline']['shots'][0]['narration'],'Chào bạn.');self.assertEqual(applied['jobs'],[])
        with self.assertRaisesRegex(WorkflowError,'STALE'): ai.suggest(before['id'],before['revision'],shot,'Thay nguồn','fixture-request-02')
