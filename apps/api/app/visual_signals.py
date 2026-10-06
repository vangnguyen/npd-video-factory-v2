"""Bounded local luminance measurements. Pixel change is a motion proxy, not tracking."""
from __future__ import annotations

import asyncio
import hashlib
import math
from pathlib import Path

WIDTH, HEIGHT = 160, 90


def frame_signals(frame: bytes, previous: bytes | None) -> dict:
    if len(frame) != WIDTH * HEIGHT:
        raise ValueError('incomplete grayscale frame')
    count = len(frame)
    edge = sum(abs(a-b) for row in range(HEIGHT) for a,b in zip(
        frame[row*WIDTH:(row+1)*WIDTH],frame[row*WIDTH+1:(row+1)*WIDTH])) / (HEIGHT*(WIDTH-1)*255)
    temporal = sum(abs(a-b) for a,b in zip(frame,previous))/count/255 if previous is not None else None
    dark = sum(value<=8 for value in frame)/count
    bright = sum(value>=247 for value in frame)/count
    return {
        'sha256':hashlib.sha256(frame).hexdigest(), 'mean_luma':round(sum(frame)/count/255,6),
        'dark_fraction':round(dark,6), 'bright_fraction':round(bright,6),
        'edge_strength':round(edge,6), 'temporal_difference':round(temporal,6) if temporal is not None else None,
        'identical_to_previous':previous == frame if previous is not None else None,
        'black_frame':dark>=.98, 'overexposure_candidate':bright>=.9,
        'underexposure_candidate':dark>=.9,
    }


async def measure_visual_signals(path: Path, *, executable: str, duration_seconds: float,
                                 timeout_seconds: int = 300, maximum_frames: int = 360) -> dict:
    if not math.isfinite(duration_seconds) or duration_seconds<=0:
        raise ValueError('positive measured video duration required')
    if not 2<=maximum_frames<=1000:
        raise ValueError('visual sample bound must be between 2 and 1000')
    rate=min(2.,maximum_frames/duration_seconds)
    process=await asyncio.create_subprocess_exec(executable,'-v','error','-nostdin','-i',str(path),
        '-map','0:v:0','-an','-vf',f'fps={rate:.12f}:start_time=0,scale={WIDTH}:{HEIGHT},format=gray',
        '-frames:v',str(maximum_frames),'-f','rawvideo','-pix_fmt','gray','pipe:1',
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
    frames=[]
    async def consume():
        previous=None
        while True:
            try:frame=await process.stdout.readexactly(WIDTH*HEIGHT)
            except asyncio.IncompleteReadError as error:
                if error.partial:raise ValueError('incomplete decoded video frame') from error
                break
            timestamp=round(len(frames)/rate,6)
            frames.append({'timestamp_seconds':timestamp,**frame_signals(frame,previous)})
            previous=frame
            if len(frames)>maximum_frames:raise ValueError('visual decoder exceeded sample bound')
        await process.wait()
        if process.returncode!=0 or not frames:raise RuntimeError('visual decode failed or returned no frames')
    try:await asyncio.wait_for(consume(),timeout=timeout_seconds)
    finally:
        if process.returncode is None:
            process.kill();await process.wait()
    return {'schema_version':1,'method':'ffmpeg-gray-temporal-luma-v1','measured':True,
        'sample_width':WIDTH,'sample_height':HEIGHT,'sampling_fps':rate,'maximum_frames':maximum_frames,
        'motion_semantics':'sampled absolute pixel difference; camera/subject changes and cuts are not separated',
        'edge_semantics':'luminance edge strength; not calibrated optical blur or semantic quality',
        'semantic_vision':False,'frames':frames}
