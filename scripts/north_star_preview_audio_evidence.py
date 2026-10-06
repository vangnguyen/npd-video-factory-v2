"""Measure the explicitly labeled isolated source-tone preview export."""
from __future__ import annotations
import argparse
import array
import json
import math
from pathlib import Path
import subprocess
import sys


def verify(directory: Path):
    evidence = json.loads((directory/'broll-evidence.json').read_text(encoding='utf-8'))
    if evidence.get('fixture_asr') is not True or evidence.get('provider_dispatches') != 0:
        raise ValueError('only the isolated synthetic-tone fixture is supported')
    render = evidence['render']
    assert render['renderer'] == 'ffmpeg-proxy-v2' and render['audio_included'] is True
    assert len(render['audio_clip_receipts']) == 1
    receipt = render['audio_clip_receipts'][0]
    assert (receipt['source_start'],receipt['source_end'],receipt['timeline_start'],receipt['duration'],receipt['speed'],receipt['volume']) == (0,16,0,16,1,1)
    stream = next(s for s in evidence['probe']['streams'] if s['codec_type']=='audio')
    assert stream['codec_name']=='aac' and int(stream['sample_rate'])==48000 and int(stream['channels'])==2
    assert abs(float(stream['duration'])-16)<.05
    raw = subprocess.check_output(['ffmpeg','-v','error','-nostdin','-i',str(directory/'preview.mp4'),
        '-map','0:a:0','-ac','1','-ar','48000','-f','s16le','pipe:1'],timeout=30)
    samples=array.array('h');samples.frombytes(raw)
    if sys.byteorder != 'little': samples.byteswap()
    def window(start,end):
        part=samples[round(start*48000):round(end*48000)]
        rms=math.sqrt(sum(float(v)**2 for v in part)/len(part))/32768
        peak=max(abs(v) for v in part)/32768
        return {'start':start,'end':end,'rms':rms,'peak':peak}
    windows=[window(.5,1),window(4.5,5),window(12.5,13)]
    assert windows[0]['rms'] < .001 and windows[2]['rms'] < .001
    assert windows[1]['rms'] > .02
    result={'fixture_asr':True,'synthetic_tone_not_speech':True,'local_real_media_encoding':True,
        'real_provider_tested':False,'human_approval_claimed':False,'production_deployed':False,
        'timeline_version':evidence['timeline_version'],'render_sha256':evidence['preview_sha256'],
        'codec':stream['codec_name'],'sample_rate':48000,'channels':2,'duration_seconds':float(stream['duration']),
        'audio_clips':render['audio_clip_receipts'],'decoded_windows':windows,
        'limiter_peak_db':render['audio_limiter_peak_db'],'non_broll_tracks_preserved':evidence['non_broll_tracks_preserved'],
        'captions_included':False,'final_render_parity':False,'output_directory':str(directory)}
    (directory/'preview-audio-evidence.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,required=True)
    verify(parser.parse_args().directory)
