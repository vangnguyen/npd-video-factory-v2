"""Bounded, streamed local waveform measurement; no synthetic amplitude fallback."""
from __future__ import annotations

import asyncio
import math
import struct
import hashlib
import tempfile
from pathlib import Path
from .decoded_audio_clock import parse_audio_clock,audio_clock_lines,audio_clock_segments


async def measure_waveform(path: Path, *, executable: str, duration_seconds: float,
                           timeout_seconds: int = 300, max_bins: int = 1600) -> dict:
    sample_rate = 8000
    if not math.isfinite(duration_seconds) or not 0<duration_seconds<=3600:
        raise ValueError("positive measured duration required for waveform")
    if type(max_bins) is not int or not 1<=max_bins<=10000:raise ValueError('waveform bin bound invalid')
    # A bounded disk spool permits exact segment boundaries without retaining
    # decoded samples in RAM or inventing amplitudes inside absent audio.
    with tempfile.TemporaryFile() as pcm:
        process = await asyncio.create_subprocess_exec(executable, '-hide_banner', '-nostdin','-copyts','-start_at_zero',
            '-protocol_whitelist','file,pipe','-i', str(path),'-map', '0:a:0', '-vn', '-ac', '1',
            '-af',f'aresample={sample_rate},asettb=1/{sample_rate},ashowinfo','-f', 'f32le', '-',
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        async def consume():
            size=0
            while chunk:=await process.stdout.read(32768):
                size+=len(chunk)
                if size>sample_rate*3600*4:raise ValueError('waveform PCM bound exceeded')
                pcm.write(chunk)
            await process.wait()
            if process.returncode!=0 or not size:raise RuntimeError('waveform decode failed or produced no audio')
            if size%4:raise ValueError('incomplete decoded audio sample')
            return size//4
        async def consume_log():
            chunks=[];size=0
            while chunk:=await process.stderr.read(65536):
                size+=len(chunk)
                if size>16*1024*1024:raise ValueError('waveform decoder log bound exceeded')
                chunks.append(chunk)
            return audio_clock_lines(b''.join(chunks).decode('utf-8','strict'))
        tasks=[asyncio.create_task(consume()),asyncio.create_task(consume_log())]
        try:total,clock_log=await asyncio.wait_for(asyncio.gather(*tasks),timeout=timeout_seconds)
        finally:
            if process.returncode is None:process.kill();await process.wait()
            for task in tasks:
                if not task.done():task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
        clock=parse_audio_clock(clock_log,sample_rate=sample_rate,allow_gaps=True)
        if clock['pcm_samples']!=total:raise ValueError('waveform PCM/clock sample counts differ')
        segments=audio_clock_segments(clock)
        if len(segments)>max_bins:raise ValueError('waveform segment bound exceeded')
        samples_per_bin=max(400,math.ceil(duration_seconds*sample_rate/max_bins),math.ceil(total/(max_bins-len(segments)+1)))
        bins=[]
        for segment in segments:
            pcm.seek(segment['pcm_start_sample']*4);remaining=segment['pcm_end_sample']-segment['pcm_start_sample'];consumed=0
            while remaining:
                count=min(remaining,samples_per_bin);left=count;peak=0.;power=0.
                while left:
                    chunk_count=min(left,8192);data=pcm.read(chunk_count*4)
                    if len(data)!=chunk_count*4:raise ValueError('waveform PCM segment incomplete')
                    for (value,) in struct.iter_unpack('<f',data):
                        if not math.isfinite(value):raise ValueError('non-finite decoded audio sample')
                        peak=max(peak,abs(value));power+=value*value
                    left-=chunk_count
                start=(segment['source_start_sample']+consumed)/sample_rate
                bins.append({'start_seconds':round(start,6),'end_seconds':round(start+count/sample_rate,6),
                             'peak':round(peak,6),'rms':round(math.sqrt(power/count),6)})
                consumed+=count;remaining-=count
        if len(bins)>max_bins+1:raise ValueError('waveform bin bound exceeded')
    version=2 if clock['contiguous'] else 3;origin=clock['source_start_seconds']
    result={'schema_version':version,'method':f'ffmpeg-mono-pcm-peak-rms-v{version}','sample_rate':sample_rate,
            'channel_mix':'mono','duration_seconds':round(total/sample_rate,6),
            'bin_seconds':round(samples_per_bin/sample_rate,6),'bins':bins,'measured':True,
            'decoded_source_clock':clock,'source_start_seconds':origin,'source_end_seconds':clock['source_end_seconds'],
            'decoded_pts_verified':True,'decoder_clock_log':clock_log,'decoder_clock_log_sha256':hashlib.sha256(clock_log.encode()).hexdigest()}
    if not clock['contiguous']:result['missing_audio_intervals']=[{'start_seconds':g['source_start_sample']/sample_rate,'end_seconds':g['source_end_sample']/sample_rate,'kind':'missing_audio; not measured silence'} for g in clock['gaps']]
    return result
