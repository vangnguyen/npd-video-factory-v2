"""Canonical preview audio contracts and actual local tone-media verification."""
import array
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import wave

import pytest

from app.platform_models import AssetRegister
from app.timeline_audio import build_timeline_audio_graph, tempo_filters
from app.timeline_models import TimelineClip, TimelineSnapshot, TimelineTrack, PreviewCreateRequest
from app.timeline_service import FFmpegProxyRenderer, PreviewService, PreviewCancelledError
from test_mvp1_multi_input import env, image, author


def snapshot(asset_id="ast_audio_source"):
    return TimelineSnapshot(duration_seconds=4, tracks=[
        TimelineTrack(track_id="trk_audio_source", type="audio", kind="original_audio", label="Source", order=0,
            clips=[TimelineClip(clip_id="clip_audio_source", kind="original_audio", label="Speech",
                                asset_id=asset_id, source_start=1, source_end=3, speed=2,
                                timeline_start=.5, duration=1, volume=.5)]),
    ])


@pytest.mark.parametrize("speed", [.1, .25, .5, 1, 1.5, 4, 8])
def test_tempo_chain_is_bounded_and_preserves_requested_rate(speed):
    factors = [float(item.split("=")[1]) for item in tempo_filters(speed)]
    assert all(.5 <= factor <= 2 for factor in factors)
    assert math.prod(factors) == pytest.approx(speed)


@pytest.mark.parametrize("speed", [0, .01, 9, math.inf, math.nan])
def test_tempo_rejects_unbounded_preview_rate(speed):
    with pytest.raises(ValueError, match="SPEED_RANGE"):
        tempo_filters(speed)


def test_muted_disabled_or_zero_volume_audio_requires_no_asset():
    source = snapshot()
    for field, value in (("muted", True), ("disabled", True)):
        changed = source.model_copy(deep=True)
        setattr(changed.tracks[0], field, value)
        graph = build_timeline_audio_graph(changed, {}, first_input_index=2)
        assert graph.inputs == graph.filters == graph.clips == []
        assert graph.muted_clip_ids == ["clip_audio_source"]
    source.tracks[0].clips[0].volume = 0
    assert not build_timeline_audio_graph(source, {}, first_input_index=2).clips
    source.tracks[0].clips[0].volume = .5
    with pytest.raises(ValueError, match="UNAVAILABLE"):
        build_timeline_audio_graph(source, {}, first_input_index=2)


async def register_tone(env, amplitude=6500):
    path = env.tmp / "source.wav"
    values = array.array("h", (round(amplitude * math.sin(2 * math.pi * (440 if n < 48000 else 880) * n / 48000))
                              for n in range(4 * 48000)))
    if sys.byteorder != "little":
        values.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        output.writeframes(values.tobytes())
    stored = await env.storage.put_file(object_key=f"projects/{env.project.project_id}/source.wav", path=path,
                                        content_type="audio/wav")
    asset = await env.platform.register_asset(env.project.project_id, AssetRegister(
        asset_class="source", kind="audio", filename="source.wav", object_key=stored.object_key,
        content_type="audio/wav", size_bytes=stored.size_bytes, checksum_sha256=stored.checksum_sha256,
        storage_provider="local", provenance={"fixture": True, "rights_status": "owned"}))
    return asset, path


async def test_preview_worker_fetches_audio_only_assets_and_checks_hash(env):
    source, path = await register_tone(env)
    content = await author(env)
    await env.timeline.create_timeline(project_id=env.project.project_id, source_analysis_id=None,
        source_media_plan_id=None, source_content_version_id=content.project_version_id,
        snapshot=snapshot(source.asset_id), actor_ref="synthetic-test")
    class Renderer:
        async def render(self, *, assets, output_path, **kwargs):
            assert set(assets) == {source.asset_id}
            assert assets[source.asset_id][1].read_bytes() == path.read_bytes()
            from app.timeline_service import ProxyRenderResult
            output_path.write_bytes(b"explicit nonplayable fixture")
            return ProxyRenderResult(output_path, {"fixture": True, "playable": False, "audio_included": False})
    service = PreviewService(repository=env.timeline, platform=env.platform, auto_edit_repository=env.assets,
        object_storage=env.storage, queue=env.queue, renderer=Renderer(), staging_root=env.tmp / "preview")
    preview = await service.enqueue(env.project.project_id, PreviewCreateRequest())
    assert (await service.process(preview.preview_id)).status == "ready"
    # Keep registered metadata intact while changing only isolated test object bytes.
    target = env.storage.root / source.object_key
    target.write_bytes(b"changed source")
    changed = snapshot(source.asset_id)
    changed.tracks[0].clips[0].volume = .4
    await env.timeline.commit_mutation(project_id=env.project.project_id, expected_version=1,
        snapshot=changed, mutation={"type": "synthetic-test"}, actor_ref="synthetic-test")
    retry = await service.enqueue(env.project.project_id, PreviewCreateRequest())
    failed = await service.process(retry.preview_id)
    assert failed.status == "failed" and "CHECKSUM_MISMATCH" in failed.failure_reason


async def test_real_preview_audio_trim_rate_placement_gain_mute_and_bounds(env):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("real local FFmpeg/FFprobe unavailable")
    source, path = await register_tone(env)
    still = await image(env)
    picture = env.tmp / "input.png"
    value = snapshot(source.asset_id)
    value.schema_version = "1.1"
    value.tracks.append(TimelineTrack(track_id="trk_photo_source", type="video", kind="source", label="Photo", order=1,
        clips=[TimelineClip(clip_id="clip_photo_source", kind="image", label="Photo", asset_id=still.asset_id,
                            timeline_start=0, duration=4)]))
    assets = {source.asset_id: (source, path), still.asset_id: (still, picture)}
    async def cancelled(): return False
    renderer = FFmpegProxyRenderer()
    result = await renderer.render(snapshot=value, assets=assets, output_path=env.tmp / "preview.mp4",
                                   width=270, height=480, is_cancelled=cancelled)
    assert result.manifest["audio_included"] and len(result.manifest["audio_clip_receipts"]) == 1
    assert result.manifest["audio_clip_receipts"][0]["speed"] == 2
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                                               "-of", "json", str(result.path)], text=True))
    audio = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    assert audio["codec_name"] == "aac" and int(audio["sample_rate"]) == 48000
    assert abs(float(audio["duration"]) - 4) < .05
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(result.path), "-map", "0:a:0",
                                   "-ac", "1", "-ar", "48000", "-f", "s16le", "pipe:1"])
    samples = array.array("h"); samples.frombytes(raw)
    if sys.byteorder != "little": samples.byteswap()
    def rms(start, end):
        window = samples[round(start * 48000):round(end * 48000)]
        return math.sqrt(sum(float(n) ** 2 for n in window) / len(window)) / 32768
    assert rms(.1, .3) < .001 and rms(1.8, 2) < .001
    assert .03 < rms(.75, 1.1) < .08
    # atempo changes duration while retaining the source 880Hz pitch.
    window = samples[round(.75 * 48000):round(1.1 * 48000)]
    crossings = sum(a <= 0 < b for a, b in zip(window, window[1:]))
    assert 850 < crossings / .35 < 910
    value.tracks[0].muted = True
    muted = await renderer.render(snapshot=value, assets={still.asset_id: (still, picture)},
        output_path=env.tmp / "muted.mp4", width=270, height=480, is_cancelled=cancelled)
    assert muted.manifest["audio_included"] is False
    assert muted.manifest["muted_audio_clip_ids"] == ["clip_audio_source"]
    value.tracks[0].muted = False
    value.tracks[0].clips[0].source_end = 6
    value.tracks[0].clips[0].speed = 5
    with pytest.raises(ValueError, match="WINDOW_UNAVAILABLE"):
        await renderer.render(snapshot=value, assets=assets, output_path=env.tmp / "invalid.mp4",
                              width=270, height=480, is_cancelled=cancelled)
    async def cancelled_now(): return True
    with pytest.raises(PreviewCancelledError):
        await renderer.render(snapshot=value, assets=assets, output_path=env.tmp / "cancelled.mp4",
                              width=270, height=480, is_cancelled=cancelled_now)


async def test_filter_file_fallback_retries_only_cli_parser_rejection(monkeypatch, tmp_path):
    import app.timeline_service as module
    target = tmp_path / "mock-not-media.mp4"
    calls = []
    failure = ["Unrecognized option '/filter_complex'", "invalid source decode"]
    class MockProcess:
        def __init__(self, index): self.index=index; self.returncode=None
        async def communicate(self):
            self.returncode = 1 if self.index == 0 else 0
            if self.returncode == 0: target.write_bytes(b"contract-only-not-playable")
            return b"", failure[0].encode() if self.returncode else b""
    async def spawn(*args, **kwargs):
        del kwargs
        calls.append(args)
        return MockProcess(len(calls)-1)
    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", spawn)
    value = TimelineSnapshot(duration_seconds=.2, tracks=[TimelineTrack(
        track_id="trk_mock_empty", type="metadata", kind="metadata", label="Mock", order=0)])
    async def cancelled(): return False
    result = await FFmpegProxyRenderer().render(snapshot=value, assets={}, output_path=target,
        width=270, height=480, is_cancelled=cancelled)
    assert len(calls) == 2 and '-/filter_complex' in calls[0] and '-filter_complex_script' in calls[1]
    assert result.manifest['audio_included'] is False
    calls.clear(); failure[0] = failure[1]
    with pytest.raises(RuntimeError, match="invalid source decode"):
        await FFmpegProxyRenderer().render(snapshot=value, assets={}, output_path=tmp_path/'failure.mp4',
            width=270, height=480, is_cancelled=cancelled)
    assert len(calls) == 1


async def test_real_overlap_fades_and_limiter_without_autogain(env):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("real local FFmpeg/FFprobe unavailable")
    source, path = await register_tone(env, amplitude=24000)
    value = snapshot(source.asset_id)
    clip = value.tracks[0].clips[0]
    clip.source_start = 0; clip.source_end = 3; clip.duration = 3; clip.speed = 1; clip.timeline_start = 0; clip.volume = 2
    clip.transition_in.kind = 'fade'; clip.transition_in.duration_seconds = .4
    clip.transition_out.kind = 'fade'; clip.transition_out.duration_seconds = .4
    other = clip.model_copy(deep=True); other.clip_id = 'clip_audio_overlap'
    value.tracks[0].clips.append(other)
    async def cancelled(): return False
    result = await FFmpegProxyRenderer().render(snapshot=value,assets={source.asset_id:(source,path)},
        output_path=env.tmp/'limited.mp4',width=270,height=480,is_cancelled=cancelled)
    raw = subprocess.check_output(['ffmpeg','-v','error','-i',str(result.path),'-map','0:a:0',
                                   '-ac','1','-ar','48000','-f','s16le','pipe:1'])
    samples=array.array('h');samples.frombytes(raw)
    if sys.byteorder!='little':samples.byteswap()
    def rms(start,end):
        part=samples[round(start*48000):round(end*48000)]
        return math.sqrt(sum(float(n)**2 for n in part)/len(part))/32768
    assert rms(.005,.025) < rms(.8,1) * .25
    assert rms(2.975,2.995) < rms(2,2.2) * .25
    assert rms(3.3,3.5) < .001
    assert max(abs(n) for n in samples) / 32768 < .99
    assert result.manifest['audio_limiter_peak_db'] == -1
    assert len(result.manifest['audio_clip_receipts']) == 2


async def test_active_proxy_cancellation_reaps_process_and_partial_output(monkeypatch, tmp_path):
    import asyncio
    import app.timeline_service as module
    output = tmp_path/'partial.mp4'
    class MockProcess:
        returncode = None
        killed = False
        def __init__(self): self.done=asyncio.Event()
        async def communicate(self):
            await self.done.wait()
            return b'', b''
        def kill(self):
            self.killed=True;self.returncode=-9;self.done.set()
    process=MockProcess()
    async def spawn(*args,**kwargs):
        output.write_bytes(b'partial test output')
        return process
    monkeypatch.setattr(module.asyncio,'create_subprocess_exec',spawn)
    polls=0
    async def cancelled():
        nonlocal polls
        polls+=1
        return polls>1
    value=TimelineSnapshot(duration_seconds=.2,tracks=[TimelineTrack(
        track_id='trk_mock_empty',type='metadata',kind='metadata',label='Mock',order=0)])
    with pytest.raises(PreviewCancelledError):
        await FFmpegProxyRenderer().render(snapshot=value,assets={},output_path=output,
            width=270,height=480,is_cancelled=cancelled)
    assert process.killed and process.returncode==-9 and not output.exists()
