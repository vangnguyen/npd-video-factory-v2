"""Bounded local luminance measurements. Pixel change is a motion proxy, not tracking."""
from __future__ import annotations

import asyncio
import hashlib
import math
from pathlib import Path
import re
from .decoded_frame_clock import parse_showinfo,select_filter,targets,BASIS

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
    requested=targets(duration_seconds,min(maximum_frames,max(1,math.ceil(duration_seconds*rate))))
    process=await asyncio.create_subprocess_exec(executable,'-hide_banner','-nostdin','-copyts','-start_at_zero',
        '-protocol_whitelist','file,pipe','-i',str(path),'-map','0:v:0','-an',
        '-vf',select_filter(requested)+f',scale={WIDTH}:{HEIGHT},format=gray,showinfo','-fps_mode','passthrough',
        '-frames:v',str(maximum_frames+1),'-f','rawvideo','-pix_fmt','gray','pipe:1',
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    frames=[]
    async def consume():
        previous=None
        while True:
            try:frame=await process.stdout.readexactly(WIDTH*HEIGHT)
            except asyncio.IncompleteReadError as error:
                if error.partial:raise ValueError('incomplete decoded video frame') from error
                break
            frames.append(frame_signals(frame,previous))
            previous=frame
            if len(frames)>maximum_frames:raise ValueError('visual decoder exceeded sample bound')
        await process.wait()
        if process.returncode!=0 or not frames:raise RuntimeError('visual decode failed or returned no frames')
    async def consume_log():
        chunks=[];size=0
        while chunk:=await process.stderr.read(65536):
            size+=len(chunk)
            if size>2*1024*1024:raise ValueError('visual decoder log exceeded bound')
            chunks.append(chunk)
        # Retain clock/config rows; filenames and arbitrary SEI payloads are excluded.
        text=b''.join(chunks).decode('utf-8','strict')
        return '\n'.join(line for line in text.splitlines() if re.search(r'\[Parsed_showinfo_[^\]]+\].*(?:config in time_base:|\bn:\s*\d+\s+pts:)',line))+'\n'
    tasks=[asyncio.create_task(consume()),asyncio.create_task(consume_log())]
    try:_,clock_log=await asyncio.wait_for(asyncio.gather(*tasks),timeout=timeout_seconds)
    finally:
        if process.returncode is None:
            process.kill();await process.wait()
        for task in tasks:
            if not task.done():task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
    stamps=parse_showinfo(clock_log,maximum_frames=maximum_frames)
    if len(stamps)!=len(frames):raise ValueError('visual pixel/clock counts differ')
    for frame,stamp in zip(frames,stamps,strict=True):
        if (stamp.width,stamp.height)!=(WIDTH,HEIGHT) or stamp.timestamp_seconds>=duration_seconds+.001:raise ValueError('visual decoded clock outside source bounds')
        frame.update(timestamp_seconds=stamp.timestamp_seconds,timestamp_basis=BASIS,decoded_clock=stamp.model_dump(mode='json'))
    return {'schema_version':2,'method':'ffmpeg-gray-temporal-luma-v2','measured':True,
        'sample_width':WIDTH,'sample_height':HEIGHT,'sampling_fps':rate,'maximum_frames':maximum_frames,
        'sampling_fps_basis':'desired upper sampling density; actual VFR samples can be fewer and nonuniform',
        'requested_sample_times':requested,'decoded_pts_verified':True,'timestamp_basis':BASIS,
        'decoder_clock_log':clock_log,'decoder_clock_log_sha256':hashlib.sha256(clock_log.encode()).hexdigest(),
        'motion_semantics':'sampled absolute pixel difference; camera/subject changes and cuts are not separated',
        'edge_semantics':'luminance edge strength; not calibrated optical blur or semantic quality',
        'semantic_vision':False,'frames':frames}
