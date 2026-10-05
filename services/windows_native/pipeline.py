from __future__ import annotations

from dataclasses import dataclass
import importlib.metadata
import json
import logging
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import wave

from .contracts import MODEL, PROFILE_SHA, RUNTIME_VERSIONS, Proposal, WorkflowError, canonical, digest, file_sha, normalize, write_json
from .media import media_path, verify_selected_files
from .hardening import Artifacts, durable_json, retry_io
from .ingestion import existing_script, provider_context, transcript_script

REPO = Path(__file__).resolve().parents[2]
LOCKS = Path(__file__).resolve().parent / "locks"


@dataclass
class Config:
    runtime_root: Path = Path(r"C:\NPD-Video-Factory\runtime")
    secret_file: Path = Path(r"C:\NPD-Video-Factory\secrets\openai.env")
    assemblyai_secret_file: Path = Path(r"C:\NPD-Video-Factory\secrets\assemblyai.dpapi")
    data_root: Path = Path(r"C:\NPD-Video-Factory\phase2")
    sdk_source: Path = Path(r"C:\NPD-Video-Factory\runtime\sdk\vieneu-85344322")
    git: Path = Path(r"C:\Users\PC\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe")
    ffmpeg_bin: Path = Path(r"C:\Users\PC\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin")

    @classmethod
    def load(cls, path=None):
        if path is None:
            return cls()
        values = json.loads(Path(path).read_text(encoding="utf-8"))
        if set(values) - set(cls.__dataclass_fields__):
            raise WorkflowError("UNKNOWN_CONFIG_FIELD", 400)
        return cls(**{k: Path(v).resolve() for k, v in values.items()})

    def dump(self):
        return {k: str(getattr(self, k)) for k in self.__dataclass_fields__}

    def validate_data_root(self):
        root = self.data_root.resolve()
        protected = [Path(r"C:\NPD-Video-Factory\outputs\MVP1"), self.runtime_root, self.secret_file.parent, self.assemblyai_secret_file.parent, REPO]
        if "sources" in {part.lower() for part in root.parts} or any(root == p.resolve() or p.resolve() in root.parents for p in protected):
            raise WorkflowError("DATA_ROOT_MUST_NOT_TOUCH_ACCEPTED_MVP1_RUNTIME_SECRETS_OR_SOURCE")


def load_key(path):
    # Secret is used only in the SDK constructor; never returned through API/logs.
    if not path.is_file():
        raise WorkflowError("OPENAI_KEY_UNAVAILABLE", 503)
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == "OPENAI_API_KEY":
            key = value.strip().strip("\"'")
            if key.startswith("sk-"):
                return key
    raise WorkflowError("OPENAI_KEY_UNAVAILABLE", 503)


def profile():
    locked = json.loads((LOCKS / "voice-profile.json").read_bytes())
    if digest(locked) != PROFILE_SHA:
        raise WorkflowError("LOCKED_VOICE_PROFILE_CHANGED")
    return locked


def verify_runtime(config, full=True):
    config.validate_data_root()
    locked = profile()
    if {k: importlib.metadata.version(k) for k in RUNTIME_VERSIONS} != RUNTIME_VERSIONS:
        raise WorkflowError("LOCKED_TTS_RUNTIME_VERSION_CHANGED")
    for executable in ("ffmpeg.exe", "ffprobe.exe"):
        if not (config.ffmpeg_bin / executable).is_file():
            raise WorkflowError("FFMPEG_TOOLS_UNAVAILABLE", 503)
    if full:
        import vieneu
        sdk = Path(vieneu.__file__).parent
        if subprocess.check_output([str(config.git), "rev-parse", "HEAD"], cwd=config.sdk_source, text=True).strip() != locked["sdk_commit"]:
            raise WorkflowError("LOCKED_SDK_COMMIT_CHANGED")
        if subprocess.check_output([str(config.git), "status", "--porcelain"], cwd=config.sdk_source, text=True).strip():
            raise WorkflowError("LOCKED_SDK_SOURCE_DIRTY")
        if file_sha(config.sdk_source / "LICENSE") != locked["rights"]["sdk_license_sha256"]:
            raise WorkflowError("SDK_LICENSE_CHANGED")
        for folder in (sdk, sdk.parent / "vieneu_utils"):
            for path in folder.rglob("*.py"):
                if file_sha(path) != file_sha(config.sdk_source / "src" / path.relative_to(sdk.parent)):
                    raise WorkflowError("INSTALLED_SDK_BYTES_MISMATCH")
        if file_sha(sdk / "assets/voices_v3_turbo.json") != locked["rights"]["preset_asset_sha256"]:
            raise WorkflowError("LOCKED_VOICE_PRESET_CHANGED")
        manifest = json.loads((LOCKS / "tts-artifacts.json").read_bytes())
        if manifest["profile_sha256"] != PROFILE_SHA:
            raise WorkflowError("MODEL_MANIFEST_PROFILE_MISMATCH")
        for artifact in manifest["files"]:
            folder = "vieneu-v3-turbo" if artifact["repository"] == locked["rights"]["model_repository"] else "moss-codec"
            path = config.runtime_root / "models" / folder / artifact["file"]
            if file_sha(path) != artifact["sha256"]:
                raise WorkflowError("LOCKED_MODEL_ARTIFACT_CHANGED")
    return {"voice": locked["voice_id"], "profile_sha256": PROFILE_SHA, "model": MODEL,
            "resolution": "1080x1920", "native_windows": os.name == "nt", "provider_calls": 0}


def provider_request(client, request, job, out, stage, openai):
    """Only a recorded 429 rejection is eligible for one bounded retry."""
    for attempt in range(2):
        name = "content" if attempt == 0 else "content-1"
        intent, rejected = out / (name + ".intent.json"), out / (name + ".rejected.json")
        if intent.exists():
            if rejected.exists() and json.loads(rejected.read_bytes()).get("http_status") == 429:
                continue
            raise WorkflowError("OPENAI_OUTCOME_UNKNOWN_NO_REPLAY")
        with intent.open("xb") as handle:
            handle.write(canonical({"model": MODEL, "max_attempts": 2, "job_id": job["id"],
                                    "snapshot_sha256": digest(job["snapshot"]), "attempt": attempt + 1}))
            handle.flush(); os.fsync(handle.fileno())
        try:
            return client.responses.create(**request), attempt + 1
        except openai.APIStatusError as error:
            if error.status_code != 429:
                raise
            durable_json(rejected, {"http_status": 429, "safe_rejection": True, "attempt": attempt + 1})
            if attempt == 1:
                raise WorkflowError("OPENAI_RATE_LIMIT_RETRY_EXHAUSTED", http_status=429) from None
            stage("retrying:content_request")
            time.sleep(1)
            stage("content_request")
    raise WorkflowError("OPENAI_RATE_LIMIT_RETRY_EXHAUSTED", http_status=429)


def generate(config, job, out, stage=lambda _: None):
    context = provider_context(job["snapshot"]["document"])
    import httpx2
    import openai
    from openai import OpenAI

    logging.getLogger("openai").disabled = True
    logging.getLogger("httpx2").disabled = True
    os.environ.pop("OPENAI_LOG", None)
    timeout = httpx2.Timeout(90.0, connect=15.0)
    provider_schema = Proposal.model_json_schema()
    provider_schema["properties"]["visual_brief"]["minItems"] = 3
    client = OpenAI(api_key=load_key(config.secret_file), max_retries=0, timeout=timeout,
                    base_url="https://api.openai.com/v1",
                    http_client=httpx2.Client(trust_env=False, timeout=timeout, follow_redirects=False))
    request = {"model": MODEL, "reasoning": {"effort": "none"}, "max_output_tokens": 2048, "store": False,
               "input": context,
               "instructions": (
                   "Trả JSON đúng schema, bằng tiếng Việt, narration cho video khoảng 25–45 giây. "
                   "visual_brief gồm 3–5 cảnh đánh số liên tiếp, on_screen_text ngắn gọn tối đa 150 ký tự. "
                   "narration_excerpt là đoạn nguyên văn liên tục, ghép theo thứ tự phủ đầy đủ narration. "
                   "Prompt và mọi dữ kiện người dùng cung cấp chưa được xác minh. Không tự bịa hoặc "
                   "khẳng định giá, chính sách, pháp lý, tiến độ, quy hoạch, ưu đãi, tiện ích, kết nối "
                   "hoặc lợi nhuận khi không có nguồn. facts_needing_source ghi rõ nguồn cần kiểm tra. "
                   "Dùng ảnh dự án do người dùng cung cấp; phối cảnh phải ghi rõ minh họa. "
                   "Không giả định dự án đã hoàn thành, không đề nghị AI/stock không liên quan. "
                   "Không tự duyệt, không tự xuất bản. Đây là bản đề xuất cho con người review."),
               "text": {"format": {"type": "json_schema", "name": "native_content_proposal", "strict": True,
                                    "schema": provider_schema}}}
    try:
        retry_io(lambda: durable_json(out / "content-request.json", request), stage, "storage_content_request")
        response, attempts = provider_request(client, request, job, out, stage, openai)
        if response.status != "completed" or response.model != MODEL or response.usage is None:
            raise WorkflowError("CONTENT_RESPONSE_INCOMPLETE_OR_MODEL_MISMATCH")
        texts = []
        for item in response.output:
            if item.type == "reasoning":
                continue
            if item.type != "message":
                raise WorkflowError("CONTENT_UNEXPECTED_RESPONSE_ITEM")
            for part in item.content:
                if part.type != "output_text":
                    raise WorkflowError("CONTENT_REFUSAL_OR_UNEXPECTED_CONTENT")
                texts.append(part.text)
        if len(texts) != 1:
            raise WorkflowError("CONTENT_AMBIGUOUS_RESPONSE")
        try:
            proposal = Proposal.model_validate_json(texts[0]).model_dump()
        except ValueError:
            raise WorkflowError("CONTENT_SCHEMA_OR_COVERAGE_INVALID") from None
        result = {"proposal": proposal, "model": response.model, "response_id": response.id,
                  "usage": response.usage.model_dump(), "provider_calls": attempts, "retries": attempts - 1,
                  "facts_verified": False, "human_review_required": True}
        write_json(out / "content-result.json", result)
        return result
    except openai.APIStatusError as error:
        raise WorkflowError(type(error).__name__, http_status=error.status_code) from None
    except openai.APITimeoutError:
        raise WorkflowError("OPENAI_TIMEOUT_OUTCOME_UNKNOWN_NO_RETRY") from None
    except openai.APIConnectionError:
        raise WorkflowError("OPENAI_CONNECTION_ERROR_NO_RETRY") from None
    finally:
        client.close()


def sentence_units(proposal):
    # The accepted MVP policy: exact sentence boundaries, no proper-name rewrites.
    return [{"scene": scene.scene, "text": text}
            for scene in proposal.visual_brief
            for text in re.split(r"(?<=[.!?])\s+", normalize(scene.narration_excerpt))]


def measured_scene_units(proposal, meta):
    groups = [[u for u in meta["units"] if u.get("scene") == scene.scene] for scene in proposal.visual_brief]
    if any(not group or normalize(" ".join(u["text"] for u in group)) != normalize(scene.narration_excerpt)
           for scene, group in zip(proposal.visual_brief, groups)):
        raise WorkflowError("VOICE_SCENE_BINDING_MISMATCH")
    if [u for group in groups for u in group] != meta["units"]:
        raise WorkflowError("VOICE_SCENE_ORDER_MISMATCH")
    previous = 0
    for unit in meta["units"]:
        start, active_start, active_end, end = (unit[k] for k in ("start_seconds", "activity_start_seconds", "activity_end_seconds", "end_seconds"))
        if not all(math.isfinite(t) for t in (start, active_start, active_end, end)) or not previous <= start <= active_start < active_end <= end <= meta["duration_seconds"] + .001:
            raise WorkflowError("VOICE_TIMING_INVALID")
        previous = end
    return groups


def synthesize(config, snapshot, out):
    """Runs in a separate process, with outbound networking blocked during local inference."""
    approval, doc = snapshot["approval"], snapshot["document"]
    if not approval or approval["snapshot_sha256"] != digest(doc):
        raise WorkflowError("HUMAN_APPROVAL_REQUIRED_BEFORE_TTS")
    proposal = Proposal.model_validate(doc["proposal"])
    verify_runtime(config)
    import numpy as np
    import socket
    import vieneu
    from vieneu._v3_turbo_engine.onnx_runtime_lite import OnnxV3LiteEngine
    from vieneu_utils.phonemize_text import normalize_to_chunks_v3_with_gaps, phonemize_text_with_emotions
    from vieneu_utils.core_utils import join_audio_chunks, gaps_to_silence, pause_pad_samples, edge_silence

    locked, rate = profile(), 48000
    plan = []
    for unit in sentence_units(proposal):
        text = unit["text"]
        chunks, gaps = normalize_to_chunks_v3_with_gaps(text, max_chars=locked["parameters"]["max_chars"])
        plan.append({**unit, "chunks": chunks, "gaps": gaps,
                     "phonemes": [phonemize_text_with_emotions(c) for c in chunks]})
    write_json(out / "tts-plan.json", {"profile_sha256": PROFILE_SHA, "units": plan})

    def blocked_connect(*args, **kwargs):
        raise WorkflowError("LOCAL_TTS_OUTBOUND_NETWORK_BLOCKED")

    socket.socket.connect = blocked_connect

    class PresetEngine(OnnxV3LiteEngine):
        def _load_denoiser(self):
            return None

        def _acoustic_frame(self, *args, **kwargs):
            codes, eos = super()._acoustic_frame(*args, **kwargs)
            self.observed_frames += int(not eos)
            self.observed_eos = bool(eos)
            return codes, eos

    engine = PresetEngine(checkpoint_path=str(config.runtime_root / "models/vieneu-v3-turbo"),
                          onnx_dir=str(config.runtime_root / "models/vieneu-v3-turbo/onnx_update"),
                          codec_dir=str(config.runtime_root / "models/moss-codec"), threads=4)
    engine.babble_retries = 0
    preset = json.loads((Path(vieneu.__file__).parent / "assets/voices_v3_turbo.json").read_bytes())["presets"][locked["voice_id"]]
    params = {k: locked["parameters"][k] for k in ("temperature", "top_k", "top_p", "repetition_penalty", "max_new_frames")}
    waves, records, offset, calls = [], [], 0, 0
    for i, unit in enumerate(plan):
        chunks = []
        for phonemes in unit["phonemes"]:
            engine.observed_frames, engine.observed_eos = 0, False
            audio = engine.infer(phonemes=phonemes, speaker_emb=np.array(preset["speaker_emb"], dtype=np.float32),
                                 ref_codes=np.array(preset["codes"], dtype=np.int64), **params)
            if not engine.observed_eos:
                raise WorkflowError("SYNTHESIS_FRAME_CAP_WITHOUT_EOS_STOP")
            if not np.isfinite(audio).all() or audio.size == 0:
                raise WorkflowError("INVALID_TTS_AUDIO")
            chunks.append(audio)
            calls += 1
        audio = join_audio_chunks(chunks, rate, silence_ps=gaps_to_silence(unit["gaps"]))
        if i:
            offset += pause_pad_samples(waves[-1], audio, rate, gaps_to_silence(["sentence"])[0])
        lead, tail = edge_silence(audio, rate)
        records.append({"index": i, "scene": unit["scene"], "text": unit["text"], "start_seconds": offset / rate,
                        "end_seconds": (offset + len(audio)) / rate,
                        "activity_start_seconds": (offset + lead) / rate,
                        "activity_end_seconds": (offset + len(audio) - tail) / rate})
        offset += len(audio)
        if offset > rate * locked["max_audio_seconds"]:
            raise WorkflowError("VOICE_DURATION_EXCEEDS_LOCKED_LIMIT")
        waves.append(audio)
    audio = join_audio_chunks(waves, rate, silence_ps=gaps_to_silence(["sentence"] * (len(waves) - 1)))
    if offset != len(audio):
        raise WorkflowError("TTS_TIMING_MISMATCH")
    with (out / "voice.wav").open("xb") as dest:
        with wave.open(dest, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    write_json(out / "voice.json", {"audio_sha256": file_sha(out / "voice.wav"), "profile_sha256": PROFILE_SHA,
                                    "duration_seconds": len(audio) / rate, "units": records,
                                    "inference_calls": calls, "retries": 0, "network_blocked": True,
                                    "word_alignment": "none", "voice": "Thùy Dung", "speed": 1})


def ass_time(t):
    cs = round(t * 100)
    return f"{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}"


def ass_escape(text):
    # Strip all ASS override/control syntax from human/provider text.
    return text.replace("\\", "＼").replace("{", "｛").replace("}", "｝").replace("\r", " ").replace("\n", " ")


def wrap_text(text, font, width):
    lines, current = [], ""
    for word in normalize(text).split():
        if font.getlength(word) > width:
            raise WorkflowError("TEXT_TOO_WIDE_FOR_PORTRAIT_LAYOUT")
        candidate = f"{current} {word}".strip()
        if current and font.getlength(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def render(config, snapshot, out):
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np

    doc = snapshot["document"]
    proposal = Proposal.model_validate(doc["proposal"])
    meta = json.loads((out / "voice.json").read_bytes())
    if meta["profile_sha256"] != PROFILE_SHA or file_sha(out / "voice.wav") != meta["audio_sha256"]:
        raise WorkflowError("VOICE_ARTIFACT_BINDING_MISMATCH")
    if normalize(" ".join(u["text"] for u in meta["units"])) != normalize(proposal.narration):
        raise WorkflowError("VOICE_NARRATION_BINDING_MISMATCH")
    grouped = measured_scene_units(proposal, meta)
    chosen = verify_selected_files(config, doc)
    intro = 1.1
    duration = max(25.0, intro + meta["duration_seconds"] + 1.0)
    if duration > 180:
        raise WorkflowError("VIDEO_DURATION_EXCEEDS_180_SECONDS")
    fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    title_font = ImageFont.truetype(str(fonts / "seguisb.ttf"), 60)
    sub_font = ImageFont.truetype(str(fonts / "segoeui.ttf"), 46)
    label_font = ImageFont.truetype(str(fonts / "segoeui.ttf"), 28)
    captions, frames = [], []
    for i, (scene, units) in enumerate(zip(proposal.visual_brief, grouped)):
        asset = chosen[scene.scene]
        source = media_path(config, asset["id"])
        start = 0 if i == 0 else intro + units[0]["start_seconds"]
        end = duration if i == len(grouped) - 1 else intro + grouped[i + 1][0]["start_seconds"]
        count = round(end * 30) - round(start * 30)
        if count <= 0:
            raise WorkflowError("SCENE_TOO_SHORT_FOR_VIDEO")
        frame = Image.new("RGBA", (1080, 1920), (9, 33, 31, 255))
        draw = ImageDraw.Draw(frame)
        if asset["kind"] == "image":
            with Image.open(source) as original:
                image = original.convert("RGB")
            image.thumbnail((1080, 1000), Image.Resampling.LANCZOS)
            frame.paste(image, ((1080 - image.width) // 2, 390 + (1000 - image.height) // 2))
        else:
            draw.rectangle((0, 390, 1079, 1389), fill=(0, 0, 0, 0))
        draw.text((70, 90), f"VIDEO FACTORY   /   {i+1:02}", font=label_font, fill="#e2cb9c")
        lines = wrap_text(scene.on_screen_text, title_font, 940)
        if len(lines) > 3:
            raise WorkflowError("SCENE_HEADING_TOO_LONG")
        draw.multiline_text((70, 155), "\n".join(lines), font=title_font, spacing=12, fill="#fcf9f1")
        if asset["illustration"]:
            draw.text((70, 1390), "Phối cảnh minh họa", font=label_font, fill="#e2cb9c")
        draw.rounded_rectangle((58, 1485, 1022, 1740), radius=18, fill="#071918", outline="#5d6653", width=2)
        draw.text((70, 1800), "Thông tin cần được kiểm chứng trước khi giao dịch", font=label_font, fill="#bed3cc")
        filename = f"scene-{i:02}.png"
        frame.save(out / filename)
        segment = f"scene-{i:02}.mp4"
        command = [str(config.ffmpeg_bin / "ffmpeg.exe"), "-hide_banner", "-nostdin", "-n"]
        if asset["kind"] == "image":
            command += ["-loop", "1", "-framerate", "30", "-i", filename]
        else:
            command += ["-stream_loop", "-1", "-protocol_whitelist", "file,pipe", "-i", str(source),
                        "-loop", "1", "-framerate", "30", "-i", filename, "-filter_complex",
                        f"[0:{asset.get('video_stream_index', 0)}]fps=30,setpts=PTS-STARTPTS,scale=1080:1000:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                        "pad=1080:1000:(ow-iw)/2:(oh-ih)/2:color=0x09211f,setsar=1,"
                        "pad=1080:1920:0:390:color=0x09211f[media];[media][1:v]overlay=0:0:shortest=1,format=yuv420p[v]",
                        "-map", "[v]"]
        command += ["-frames:v", str(count), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-r", "30", "-video_track_timescale", "15360", segment]
        with (out / f"scene-{i:02}.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        if result.returncode:
            raise WorkflowError("FFMPEG_SCENE_RENDER_FAILED")
        frames.append({"scene": scene.scene, "file": segment, "start": round(start * 30) / 30,
                       "end": round(end * 30) / 30, "frames": count, "asset_id": asset["id"],
                       "kind": asset["kind"], "source_sha256": asset["sha256"], "filename": asset["filename"],
                       "short_video_policy": "loop_from_start" if asset["kind"] == "video" else None,
                       "source_audio": "muted" if asset["kind"] == "video" else None})
        for unit in units:
            lines = wrap_text(unit["text"], sub_font, 900)
            phrases = ["\n".join(lines[j:j+2]) for j in range(0, len(lines), 2)]
            weights = [len(normalize(p)) for p in phrases]
            t = intro + unit["activity_start_seconds"]
            speech_end = intro + unit["activity_end_seconds"]
            if speech_end <= t:
                raise WorkflowError("EMPTY_SPEECH_ACTIVITY")
            for phrase, weight in zip(phrases, weights):
                finish = t + (speech_end - intro - unit["activity_start_seconds"]) * weight / sum(weights)
                captions.append({"start": t, "end": finish, "text": phrase})
                t = finish
    if normalize(" ".join(c["text"] for c in captions)) != normalize(proposal.narration):
        raise WorkflowError("SUBTITLE_COVERAGE_MISMATCH")
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Subtitle,Segoe UI,46,&H00F1F9FC,&H00FFFFFF,&H00101D1B,&H00000000,0,0,0,0,100,100,0,0,1,1,0,5,80,80,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for cue in captions:
        text = "\\N".join(ass_escape(line) for line in cue["text"].splitlines())
        events.append(f"Dialogue: 0,{ass_time(cue['start'])},{ass_time(cue['end'])},Subtitle,,0,0,0,,{{\\pos(540,1610)}}{text}")
    (out / "subtitles.ass").write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    concat = "ffconcat version 1.0\n" + "".join(f"file {f['file']}\n" for f in frames)
    (out / "frames.txt").write_text(concat, encoding="ascii")
    with wave.open(str(out / "voice.wav"), "rb") as wav:
        audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float64) / 32768
    rms, peak = np.sqrt(np.mean(audio ** 2)), np.max(np.abs(audio))
    if not np.isfinite(audio).all() or rms < 1e-5:
        raise WorkflowError("VOICE_SIGNAL_INVALID_OR_SILENT")
    gain = min(10 ** (-19 / 20) / rms, .90 / peak)
    filters = (f"[0:v]fps=30,ass=subtitles.ass,format=yuv420p[v];"
               f"[1:a]volume={gain:.8f},adelay=1100,apad,atrim=duration={duration:.4f}[a]")
    cmd = [str(config.ffmpeg_bin / "ffmpeg.exe"), "-hide_banner", "-nostdin", "-n", "-f", "concat", "-safe", "1", "-i", "frames.txt",
           "-i", "voice.wav", "-filter_complex", filters, "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
           "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-ar", "48000", "-movflags", "+faststart", "-t", f"{duration:.4f}", "final.mp4"]
    with (out / "render.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(cmd, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=600)
    if result.returncode:
        raise WorkflowError("FFMPEG_RENDER_FAILED")
    write_json(out / "render-manifest.json", {"duration_seconds": duration, "captions": captions, "scenes": frames,
        "voice_sha256": meta["audio_sha256"], "scene_source_policy": "exactly_one_image_or_video",
        "profile_sha256": PROFILE_SHA, "subtitle_timing": "ESTIMATED_WITH_MEASURED_SCENE_AUDIO",
        "word_alignment": "none", "approval": snapshot["approval"], "voice_speed": 1})
    return qc(config, out, duration)


def qc(config, out, expected_duration):
    import numpy as np
    ffprobe = subprocess.check_output([str(config.ffmpeg_bin / "ffprobe.exe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(out / "final.mp4")], timeout=30)
    probe = json.loads(ffprobe)
    write_json(out / "ffprobe.json", probe)
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    with (out / "decode.log").open("w") as log:
        decoded = subprocess.run([str(config.ffmpeg_bin / "ffmpeg.exe"), "-v", "error", "-xerror", "-i", str(out / "final.mp4"), "-f", "null", "-"], stdout=log, stderr=log, timeout=180)
    pcm = subprocess.check_output([str(config.ffmpeg_bin / "ffmpeg.exe"), "-v", "error", "-i", str(out / "final.mp4"), "-vn", "-f", "f32le", "-ac", "1", "-ar", "48000", "-"], timeout=60)
    samples = np.frombuffer(pcm, dtype="<f4")
    with (out / "blackdetect.log").open("w") as log:
        black = subprocess.run([str(config.ffmpeg_bin / "ffmpeg.exe"), "-hide_banner", "-i", str(out / "final.mp4"), "-vf", "blackdetect=d=0.2:pix_th=0.1", "-an", "-f", "null", "-"], stdout=log, stderr=log, timeout=180)
    checks = {"portrait_1080x1920": (video["width"], video["height"]) == (1080, 1920),
              "h264_aac": video["codec_name"] == "h264" and audio["codec_name"] == "aac",
              "fps_30": video["avg_frame_rate"] == "30/1", "yuv420p": video["pix_fmt"] == "yuv420p",
              "audio_48khz": audio["sample_rate"] == "48000", "full_decode": decoded.returncode == 0,
              "duration_complete": abs(float(probe["format"]["duration"]) - expected_duration) < .12,
              "av_duration_match": abs(float(video["duration"]) - float(audio["duration"])) < .12,
              "finite_audible_audio": bool(samples.size and np.isfinite(samples).all() and np.sqrt(np.mean(samples ** 2)) > .005),
              "no_hard_clipping": bool(samples.size and np.max(np.abs(samples)) < .999),
              "no_black_intervals": black.returncode == 0 and "black_start:" not in (out / "blackdetect.log").read_text()}
    report = {"checks": checks, "passed": all(checks.values()), "final_sha256": file_sha(out / "final.mp4"),
              "duration_seconds": float(probe["format"]["duration"]), "final_bytes": (out / "final.mp4").stat().st_size,
              "human_final_video_accepted": False, "published": False}
    write_json(out / "qc-report.json", report)
    if not report["passed"]:
        raise WorkflowError("MEDIA_QC_FAILED")
    return report


class Pipeline:
    def __init__(self, config):
        self.config = config

    def run(self, job, stage):
        out = self.config.data_root / "jobs" / job["id"]
        if self.config.data_root.resolve() not in out.resolve().parents:
            raise WorkflowError("ARTIFACT_PATH_INVALID")
        retry_io(lambda: out.mkdir(parents=True, exist_ok=True), stage, "storage_prepare")
        artifacts = Artifacts(out, job)
        if (out / "input.json").exists():
            if json.loads((out / "input.json").read_bytes()) != job["snapshot"]:
                raise WorkflowError("CHECKPOINT_INPUT_CHANGED")
        else:
            retry_io(lambda: durable_json(out / "input.json", job["snapshot"]), stage, "storage_input")
        if job["kind"] == "asr":
            from .asr import analyze
            checkpoint = artifacts.load("asr")
            if checkpoint:
                stage("resuming_verified_asr")
                return checkpoint["result"]
            return analyze(self.config, job, out, stage)
        if job["kind"] == "content":
            checkpoint = artifacts.load("content")
            if checkpoint:
                stage("resuming_verified_content")
                return checkpoint["result"]
            doc = job["snapshot"]["document"]
            if doc.get("input_kind") == "script" or transcript_script(doc) is not None:
                stage("prepare_existing_script")
                source = "existing_user_script" if doc.get("input_kind") == "script" else "immutable_provider_transcript_for_human_review"
                result = {"proposal": existing_script(doc if source == "existing_user_script" else {"prompt": transcript_script(doc)}), "source": source,
                          "provider_calls": 0, "retries": 0, "facts_verified": False, "human_review_required": True}
                if source == "immutable_provider_transcript_for_human_review":
                    result["proposal"]["facts_needing_source"] = ["Lời nói do AssemblyAI nhận diện có thể sai. Kiểm tra video nguồn, sửa bản nháp nếu cần và xác minh dữ kiện trước khi duyệt; transcript gốc được giữ nguyên."]
                durable_json(out / "content-result.json", result)
                durable_json(out / "content-request.json", {"workflow": "existing_script", "provider_dispatch": False})
            else:
                stage("content_request")
                result = generate(self.config, job, out, stage)
            retry_io(lambda: artifacts.commit("content", [out / "content-result.json", out / "content-request.json"], result), stage, "storage_content_checkpoint")
            return result
        approval = job["snapshot"]["approval"]
        if not approval or approval["revision"] != job["revision"] or approval["snapshot_sha256"] != digest(job["snapshot"]["document"]):
            raise WorkflowError("HUMAN_APPROVAL_REQUIRED_BEFORE_TTS")
        stage("checking_scene_media")
        verify_selected_files(self.config, job["snapshot"]["document"])
        checkpoint = artifacts.load("render")
        if checkpoint:
            stage("resuming_verified_render")
            return checkpoint["result"]
        if artifacts.load("tts"):
            stage("resuming_verified_tts")
        else:
            stage("locked_thuy_dung_tts")
            def tts_attempt():
                attempt = self.attempt(out, "tts")
                retry_io(lambda: durable_json(attempt / "input.json", job["snapshot"]), stage, "storage_tts_input")
                retry_io(lambda: durable_json(attempt / "runtime-config.json", self.config.dump()), stage, "storage_tts_config")
                cmd = [sys.executable, "-m", "services.windows_native.tts_child", str(attempt)]
                try:
                    with (attempt / "tts.log").open("w", encoding="utf-8") as log:
                        child = retry_io(lambda: subprocess.run(cmd, cwd=REPO, stdout=log, stderr=log, timeout=600), stage, "locked_thuy_dung_tts")
                except subprocess.TimeoutExpired:
                    raise WorkflowError("TTS_TIMEOUT_NO_AUTOMATIC_INFERENCE_RETRY") from None
                if child.returncode:
                    status = attempt / "tts-status.json"
                    code = json.loads(status.read_bytes()).get("code", "TTS_CHILD_FAILED") if status.exists() else "TTS_CHILD_FAILED"
                    raise WorkflowError(code)
                self.publish_voice(artifacts, attempt, job, stage)
            # Recover a complete child output if the parent stopped before publishing its checkpoint.
            completed = [p for p in sorted((out / "attempts").glob("tts-*"), reverse=True)
                         if (p / "voice.json").is_file() and (p / "voice.wav").is_file() and (p / "tts-plan.json").is_file()]
            if completed:
                self.publish_voice(artifacts, completed[0], job, stage)
            else:
                if (out / "voice.wav").exists():
                    raise WorkflowError("TTS_UNCHECKPOINTED_OUTPUT_REVIEW_REQUIRED")
                tts_attempt()
        report = None
        for attempt_number in range(2):
            stage("ffmpeg_render_and_qc")
            def render_attempt():
                attempt = self.attempt(out, "render")
                for name in ("voice.wav", "voice.json"):
                    Artifacts(attempt, job).publish(out / name, name)
                return render(self.config, job["snapshot"], attempt), attempt
            try:
                report, attempt = retry_io(render_attempt, stage, "ffmpeg_render_and_qc")
                break
            except subprocess.TimeoutExpired:
                if attempt_number:
                    raise WorkflowError("FFMPEG_RENDER_TIMEOUT_RETRY_EXHAUSTED") from None
                stage("retrying:ffmpeg_render_and_qc")
        result = {"video_url": f"/api/jobs/{job['id']}/video", "qc": report,
                  "output_directory": str(out), "review_required": True,
                  "render_version": digest({"snapshot": job["snapshot"], "job_id": job["id"], "final_sha256": report["final_sha256"]})}
        paths = retry_io(lambda: [artifacts.publish(attempt / name, name) for name in
                        ("final.mp4", "qc-report.json", "ffprobe.json", "render-manifest.json", "subtitles.ass")], stage, "storage_render_publish")
        retry_io(lambda: artifacts.commit("render", paths, result), stage, "storage_render_checkpoint")
        return result

    @staticmethod
    def publish_voice(artifacts, attempt, job, stage):
        if json.loads((attempt / "input.json").read_bytes()) != job["snapshot"]:
            raise WorkflowError("TTS_RECOVERY_SNAPSHOT_MISMATCH")
        meta = json.loads((attempt / "voice.json").read_bytes())
        proposal = Proposal.model_validate(job["snapshot"]["document"]["proposal"])
        if meta["profile_sha256"] != PROFILE_SHA or meta["audio_sha256"] != file_sha(attempt / "voice.wav"):
            raise WorkflowError("VOICE_ARTIFACT_BINDING_MISMATCH")
        if normalize(" ".join(u["text"] for u in meta["units"])) != normalize(proposal.narration):
            raise WorkflowError("VOICE_NARRATION_BINDING_MISMATCH")
        measured_scene_units(proposal, meta)
        paths = retry_io(lambda: [artifacts.publish(attempt / name, name) for name in ("voice.wav", "voice.json", "tts-plan.json")], stage, "storage_tts_publish")
        retry_io(lambda: artifacts.commit("tts", paths), stage, "storage_tts_checkpoint")

    @staticmethod
    def attempt(out, kind):
        for number in range(100):
            path = out / "attempts" / f"{kind}-{number:03}"
            try:
                path.mkdir(parents=True, exist_ok=False)
                return path
            except FileExistsError:
                continue
        raise WorkflowError("LOCAL_ATTEMPT_LIMIT_REACHED")
