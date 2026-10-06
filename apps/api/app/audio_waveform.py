"""Bounded, streamed local waveform measurement; no synthetic amplitude fallback."""
from __future__ import annotations

import asyncio
import math
import struct
from pathlib import Path


async def measure_waveform(path: Path, *, executable: str, duration_seconds: float,
                           timeout_seconds: int = 300, max_bins: int = 1600) -> dict:
    sample_rate = 8000
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("positive measured duration required for waveform")
    samples_per_bin = max(400, math.ceil(duration_seconds * sample_rate / max_bins))
    process = await asyncio.create_subprocess_exec(executable, '-v', 'error', '-nostdin', '-i', str(path),
        '-map', '0:a:0', '-vn', '-ac', '1', '-ar', str(sample_rate), '-f', 'f32le', '-',
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
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
    try:
        total = await asyncio.wait_for(consume(), timeout=timeout_seconds)
    finally:
        if process.returncode is None:
            process.kill(); await process.wait()
    return {'schema_version':1,'method':'ffmpeg-mono-pcm-peak-rms-v1','sample_rate':sample_rate,
            'channel_mix':'mono','duration_seconds':round(total/sample_rate,6),
            'bin_seconds':round(samples_per_bin/sample_rate,6),'bins':bins,'measured':True}
