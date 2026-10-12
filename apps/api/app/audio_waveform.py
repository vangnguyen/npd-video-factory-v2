"""Bounded, streamed local waveform measurement; no synthetic amplitude fallback."""
from __future__ import annotations

import asyncio
import math
import struct
import hashlib
from pathlib import Path
from .decoded_audio_clock import parse_audio_clock,audio_clock_lines


async def measure_waveform(path: Path, *, executable: str, duration_seconds: float,
                           timeout_seconds: int = 300, max_bins: int = 1600) -> dict:
    sample_rate = 8000
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("positive measured duration required for waveform")
    samples_per_bin = max(400, math.ceil(duration_seconds * sample_rate / max_bins))
    if type(max_bins) is not int or not 1<=max_bins<=10000:raise ValueError('waveform bin bound invalid')
    process = await asyncio.create_subprocess_exec(executable, '-hide_banner', '-nostdin','-copyts','-start_at_zero',
        '-protocol_whitelist','file,pipe','-i', str(path),'-map', '0:a:0', '-vn', '-ac', '1',
        '-af',f'aresample={sample_rate},asettb=1/{sample_rate},ashowinfo','-f', 'f32le', '-',
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    bins = []
    async def consume():
        carry = b''; count = 0; total = 0; peak = 0.; power = 0.
        def emit():
            bins.append({'start_seconds':round((total-count)/sample_rate,6),
                         'end_seconds':round(total/sample_rate,6),'peak':round(peak,6),
                         'rms':round(math.sqrt(power/count),6)})
        while chunk := await process.stdout.read(32768):
            data = carry + chunk; end = len(data)//4*4; carry = data[end:]
            for (value,) in struct.iter_unpack('<f', data[:end]):
                if not math.isfinite(value):raise ValueError('non-finite decoded audio sample')
                peak = max(peak, abs(value)); power += value*value; count += 1; total += 1
                if count == samples_per_bin:
                    emit(); count = 0; peak = 0.; power = 0.
                    if len(bins)>max_bins+1:raise ValueError('decoded duration exceeds bounded waveform metadata')
        if carry:raise ValueError('incomplete decoded audio sample')
        if count:emit()
        await process.wait()
        if process.returncode != 0 or not bins:raise RuntimeError('waveform decode failed or produced no audio')
        return total
    async def consume_log():
        chunks=[];size=0
        while chunk:=await process.stderr.read(65536):
            size+=len(chunk)
            if size>16*1024*1024:raise ValueError('waveform decoder log bound exceeded')
            chunks.append(chunk)
        return audio_clock_lines(b''.join(chunks).decode('utf-8','strict'))
    tasks=[asyncio.create_task(consume()),asyncio.create_task(consume_log())]
    try:
        total,clock_log = await asyncio.wait_for(asyncio.gather(*tasks), timeout=timeout_seconds)
    finally:
        if process.returncode is None:
            process.kill(); await process.wait()
        for task in tasks:
            if not task.done():task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
    clock=parse_audio_clock(clock_log,sample_rate=sample_rate)
    if clock['pcm_samples']!=total:raise ValueError('waveform PCM/clock sample counts differ')
    origin=clock['source_start_seconds']
    for item in bins:item.update(start_seconds=round(origin+item['start_seconds'],6),end_seconds=round(origin+item['end_seconds'],6))
    return {'schema_version':2,'method':'ffmpeg-mono-pcm-peak-rms-v2','sample_rate':sample_rate,
            'channel_mix':'mono','duration_seconds':round(total/sample_rate,6),
            'bin_seconds':round(samples_per_bin/sample_rate,6),'bins':bins,'measured':True,
            'decoded_source_clock':clock,'source_start_seconds':origin,'source_end_seconds':clock['source_end_seconds'],
            'decoded_pts_verified':True,'decoder_clock_log':clock_log,'decoder_clock_log_sha256':hashlib.sha256(clock_log.encode()).hexdigest()}
