"""Local quality trials on Owner-approved text; never claim production acceptance."""
from pathlib import Path
import argparse
import copy
import importlib.util
import json
import sys

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.windows_native import pipeline
from services.windows_native.contracts import normalize,write_json,file_sha


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('case',type=int);parser.add_argument('--seed',type=int,default=604)
    parser.add_argument('--temperature',type=float)
    args=parser.parse_args();config=pipeline.Config()
    evidence=pipeline.REPO/'evidence/post-mvp-roadmap/phase-9/9k'
    manifest=json.loads((evidence/'final-video-review-manifest.json').read_bytes())
    case=next(c for c in manifest['cases'] if c['case']==args.case)
    snapshot=json.loads((evidence/f'case-{args.case:02}'/'production-snapshot.json').read_bytes())
    if 'snapshot' in snapshot: snapshot=snapshot['snapshot']
    suffix='' if args.temperature is None else f'-temperature{args.temperature:g}'
    output=Path('C:/NPD-Video-Factory/post-mvp-validation/phase9k-audio-repair-20261006')/f'trial-scene-case{args.case:02}-seed{args.seed}{suffix}'
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'input.json',snapshot)
    write_json(output/'trial.json',{'classification':'EXPERIMENTAL_LOCAL_AUDIO_NOT_NATIVE_PRODUCTION_JOB','case':args.case,
        'seed':args.seed,'base_voice_profile_file_unchanged':True,'scene_grouped':True,'sampling_temperature_override':args.temperature,
        'owner_feedback_scope':'Check all five for voice roughness and pitch changes',
        'human_audio_accepted':False})
    pipeline.sentence_units=lambda p:[{'scene':s.scene,'text':normalize(s.narration_excerpt)} for s in p.visual_brief]
    if args.temperature is not None:
        original_profile=pipeline.profile
        def trial_profile():
            p=copy.deepcopy(original_profile());p['parameters']['temperature']=args.temperature;return p
        pipeline.profile=trial_profile
    from vieneu._v3_turbo_engine.onnx_runtime_lite import OnnxV3LiteEngine
    original_frame=OnnxV3LiteEngine._acoustic_frame
    terminal=[]
    def observed_frame(self,*a,**kw):
        codes,eos=original_frame(self,*a,**kw)
        if eos: terminal.append([int(c) for c in codes])
        return codes,eos
    OnnxV3LiteEngine._acoustic_frame=observed_frame
    np.random.seed(args.seed)
    pipeline.synthesize(config,snapshot,output)
    write_json(output/'terminal-frames.json',{'eos_frame_codes':terminal,'note':'SDK includes this terminal frame in codec decoding; inspection only, no trim applied'})
    spec=importlib.util.spec_from_file_location('diagnostics',pipeline.REPO/'scripts/phase9k-audio-diagnostics.py')
    diagnostics=importlib.util.module_from_spec(spec);spec.loader.exec_module(diagnostics)
    result=diagnostics.inspect(output/'voice.wav',output/'voice.json')
    write_json(output/'signal-diagnostics.json',result)
    write_json(evidence/'audio-repair-01'/f'scene-trial-case{args.case:02}-seed{args.seed}{suffix}.json',{
        'classification':'EXPERIMENT_NOT_PRODUCTION_PASS','path':str(output),'wave_sha256':file_sha(output/'voice.wav'),'diagnostics':result})
    print(json.dumps({'case':args.case,'trial':str(output),'duration_seconds':result['duration_seconds'],
        'unit_f0_hz':[u['median_f0_hz'] for u in result['units']],'range_semitones':result['unit_median_range_semitones'],
        'human_audio_accepted':False}),flush=True)
