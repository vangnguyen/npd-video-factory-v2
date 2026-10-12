"""Bounded measured source audio clock before timeline trim/tempo/mixing."""
import asyncio,hashlib,math
from pathlib import Path
from .decoded_audio_clock import parse_audio_clock,audio_clock_lines

INPUT_TIMESTAMP_OPTIONS=('-copyts','-start_at_zero')
SOURCE_ALIGNMENT_FILTER='aresample=48000:async=1:first_pts=0:min_comp=0:min_hard_comp=0:max_soft_comp=0'
POLICY='observed-source-pts-before-trim-tempo-v1'


async def measure_source_audio_clock(path:Path,*,executable:str,source_sha256:str,end_seconds:float,
                                     is_cancelled=None,timeout_seconds:float=300):
    if not math.isfinite(end_seconds) or not 0<end_seconds<=3600 or len(source_sha256)!=64:
        raise ValueError('SOURCE_AUDIO_CLOCK_CONFIGURATION_INVALID')
    async def cancelled():return bool(is_cancelled and await is_cancelled())
    def checksum():
        with path.open('rb') as h:return hashlib.file_digest(h,'sha256').hexdigest()
    if await cancelled():raise ValueError('SOURCE_AUDIO_CLOCK_CANCELLED')
    if await asyncio.to_thread(checksum)!=source_sha256:raise ValueError('SOURCE_AUDIO_CLOCK_SOURCE_CHANGED')
    process=await asyncio.create_subprocess_exec(executable,'-hide_banner','-nostdin',*INPUT_TIMESTAMP_OPTIONS,
        '-protocol_whitelist','file,pipe','-i',str(path),'-map','0:a:0','-vn','-ac','2',
        '-af','aresample=48000,asettb=1/48000,ashowinfo','-t',f'{end_seconds:.9f}','-f','null','-',
        stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.PIPE)
    async def consume():
        chunks=[];size=0
        while chunk:=await process.stderr.read(65536):
            size+=len(chunk)
            if size>16*1024*1024:raise ValueError('SOURCE_AUDIO_CLOCK_LOG_BOUND_EXCEEDED')
            chunks.append(chunk)
        await process.wait()
        if process.returncode:raise ValueError('SOURCE_AUDIO_CLOCK_DECODE_FAILED')
        return audio_clock_lines(b''.join(chunks).decode('utf-8','strict'))
    task=asyncio.create_task(consume());loop=asyncio.get_running_loop();deadline=loop.time()+timeout_seconds
    try:
        while not task.done():
            if await cancelled():raise ValueError('SOURCE_AUDIO_CLOCK_CANCELLED')
            if loop.time()>=deadline:raise ValueError('SOURCE_AUDIO_CLOCK_TIMEOUT')
            await asyncio.wait([task],timeout=.1)
        log=await task
    finally:
        if process.returncode is None:process.kill();await process.wait()
        if not task.done():task.cancel()
        await asyncio.gather(task,return_exceptions=True)
    clock=parse_audio_clock(log,sample_rate=48000,expected_channels=2,allow_gaps=True)
    if await asyncio.to_thread(checksum)!=source_sha256:raise ValueError('SOURCE_AUDIO_CLOCK_SOURCE_CHANGED')
    return {'schema_version':POLICY,'source_sha256':source_sha256,'verified_source_end_seconds':end_seconds,
            'clock':clock,'decoder_clock_log':log,'decoder_clock_log_sha256':hashlib.sha256(log.encode()).hexdigest(),
            'normalization':'copyts_start_at_zero','alignment_filter':SOURCE_ALIGNMENT_FILTER,
            'original_media_mutated':False,'soft_time_compensation_enabled':False,'overlap_removal_authorized':False}


async def verify_audio_inputs(snapshot,assets,*,executable,is_cancelled=None):
    needed={}
    for track in snapshot.tracks:
        if track.type!='audio' or track.disabled or track.muted:continue
        for clip in track.clips:
            if clip.disabled or clip.volume==0:continue
            if not clip.asset_id or clip.asset_id not in assets or clip.source_end is None:raise ValueError('SOURCE_AUDIO_CLOCK_ASSET_UNAVAILABLE')
            needed[clip.asset_id]=max(needed.get(clip.asset_id,0),clip.source_end)
    result={}
    for identifier,end in sorted(needed.items()):
        asset,path=assets[identifier]
        result[identifier]=await measure_source_audio_clock(path,executable=executable,source_sha256=asset.checksum_sha256,
            end_seconds=end,is_cancelled=is_cancelled)
    return {'schema_version':POLICY,'assets':result,'verified_before_audio_processing':True,'external_provider_calls':0}
