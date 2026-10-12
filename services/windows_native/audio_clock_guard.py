"""Native adapter to the shared measured audio-clock boundary."""
import asyncio
from .contracts import WorkflowError
from .hardening import durable_json
from app.source_audio_clock import verify_audio_inputs,INPUT_TIMESTAMP_OPTIONS,POLICY


def verify(config,snapshot,assets,directory=None,event=None):
    async def cancelled():return bool(event and event.is_set())
    try:value=asyncio.run(verify_audio_inputs(snapshot,assets,executable=str(config.ffmpeg_bin/'ffmpeg.exe'),is_cancelled=cancelled))
    except ValueError as error:
        if str(error)=='SOURCE_AUDIO_CLOCK_CANCELLED':raise WorkflowError('PREVIEW_CANCELLED') from None
        raise WorkflowError('SOURCE_AUDIO_CLOCK_INVALID_OR_CHANGED') from None
    if directory is not None:durable_json(directory/'source-audio-clocks.json',value)
    return value
