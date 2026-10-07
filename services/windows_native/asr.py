"""Native media analysis with the existing strict AssemblyAI adapter.

Durable dispatch intents permit GET observation of a known job, never replay of
an ambiguous upload or transcript creation. No source media or narration edits.
"""
import asyncio
from dataclasses import asdict
import io
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import wave

from . import assemblyai_connection as connection
from .contracts import WorkflowError, canonical, digest, file_sha
from .hardening import Artifacts, durable_json
from .ingestion import API_ROOT
from .media import media_path, project_assets
from app.assemblyai_asr_profile import ASSEMBLYAI_CREDENTIAL_ALIAS, assemblyai_asr_profile, assemblyai_profile_sha256


def analysis_for_asset(document, asset):
    record = next((r for r in document.get("media_analysis", []) if r.get("asset_id") == asset["id"]), None)
    if not record or record.get("source_sha256") != asset["sha256"]:
        return None
    body = {k: v for k, v in record.items() if k != "analysis_sha256"}
    return record if digest(body) == record.get("analysis_sha256") else None


def pending_assets(document):
    return [a for a in project_assets(document) if not analysis_for_asset(document, a)]


def pending_speech(document):
    return [a for a in pending_assets(document) if a["kind"] == "video" and a.get("has_audio")]


class DurableTransport:
    """One upload/create per asset; durable known acknowledgements are reusable."""
    def __init__(self, out, binding, stage, *, client_factory=None):
        self.out, self.binding, self.stage = Path(out), binding, stage
        self.out.mkdir(parents=True, exist_ok=True)
        if client_factory is None:
            import httpx2
            client_factory = httpx2.AsyncClient
        self.client_factory = client_factory
        logging.getLogger("httpx2").disabled = True

    def load(self, name):
        path = self.out / (name + ".json")
        if not path.exists():
            return None
        value = json.loads(path.read_bytes())
        body = {k: v for k, v in value.items() if k != "receipt_sha256"}
        if value.get("binding") != self.binding or digest(body) != value.get("receipt_sha256"):
            raise WorkflowError("ASR_RECEIPT_BINDING_CHANGED")
        return value["payload"]

    def save(self, name, payload):
        body = {"binding": self.binding, "payload": payload}
        durable_json(self.out / (name + ".json"), {**body, "receipt_sha256": digest(body)})

    def intent(self, name):
        path = self.out / (name + ".intent.json")
        if path.exists():
            raise WorkflowError("ASR_OUTCOME_UNKNOWN_NO_REPLAY")
        with path.open("xb") as handle:
            handle.write(canonical({"binding": self.binding, "operation": name, "automatic_retry": False}))
            handle.flush(); os.fsync(handle.fileno())

    async def request(self, method, path, credential, timeout, **kwargs):
        # The authorization header is confined to this fixed verified TLS origin.
        ledger, context = getattr(self, 'cost_ledger', None), getattr(self, 'cost_context', None)
        cost_id = None
        if ledger and context:
            operation = ('upload' if path == '/v2/upload' else 'create-transcript'
                         if method == 'POST' else f'observe-{len(list(self.out.glob("observe-*.intent.json"))):04}')
            operation = f'asr-{self.binding[:24]}-{operation}'
            cost_id = ledger.begin(**context, provider='assemblyai', model=assemblyai_asr_profile().model,
                operation=operation, request_sha256=self.binding,
                estimated_cost=None, paid=(method == 'POST' and path == '/v2/transcript'))
        try:
            async with self.client_factory(timeout=timeout, trust_env=False, follow_redirects=False) as client:
                async with client.stream(method, "https://api.assemblyai.com" + path,
                                         headers={"authorization": credential}, **kwargs) as response:
                    if response.status_code != 200:
                        raise WorkflowError("ASR_HTTP_REQUEST_FAILED", http_status=response.status_code)
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 8 * 1024 * 1024:
                            raise WorkflowError("ASR_RESPONSE_SIZE_LIMIT")
                        chunks.append(chunk)
            raw = b"".join(chunks)
            if credential.encode("ascii") in raw:
                raise WorkflowError("ASR_RESPONSE_CONTAINS_CREDENTIAL_REJECTED")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise WorkflowError("ASR_RESPONSE_INVALID")
            if credential.encode("ascii") in canonical(value):
                raise WorkflowError("ASR_RESPONSE_CONTAINS_CREDENTIAL_REJECTED")
            if cost_id:
                ledger.settle(cost_id, status='response_received', response_sha256=digest(value))
            return value
        except Exception as error:
            if cost_id and ledger.pending(cost_id):
                ledger.settle(cost_id, status='outcome_unknown', error_code=type(error).__name__)
            raise

    async def upload(self, audio, credential, timeout):
        receipt = self.load("upload-ack")
        if receipt:
            return receipt["upload_url"]
        self.intent("upload")
        self.stage("asr_upload")
        value = await self.request("POST", "/v2/upload", credential, timeout, content=audio)
        url = value.get("upload_url")
        if not isinstance(url, str) or not re.fullmatch(r"https://[A-Za-z0-9.-]+\.assemblyai\.com/[^\s]+", url):
            raise WorkflowError("ASR_UPLOAD_ACK_INVALID")
        self.save("upload-ack", {"upload_url": url})
        return url

    async def create_transcript(self, request, credential, timeout):
        request_sha = digest(request)
        receipt = self.load("transcript-ack")
        if receipt:
            if receipt["request_sha256"] != request_sha:
                raise WorkflowError("ASR_REQUEST_CHANGED")
            return {"id": receipt["id"]}
        self.intent("create-transcript")
        self.stage("asr_create_transcript")
        value = await self.request("POST", "/v2/transcript", credential, timeout, json=request)
        identifier = value.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,128}", identifier):
            raise WorkflowError("ASR_TRANSCRIPT_ACK_INVALID")
        self.save("transcript-ack", {"id": identifier, "request_sha256": request_sha})
        return {"id": identifier}

    async def get_transcript(self, identifier, credential, timeout):
        if not re.fullmatch(r"[A-Za-z0-9-]{1,128}", identifier):
            raise WorkflowError("ASR_TRANSCRIPT_ID_INVALID")
        complete = self.load("provider-completed")
        if complete:
            if complete.get("id") != identifier:
                raise WorkflowError("ASR_TRANSCRIPT_ID_CHANGED")
            return complete
        self.stage("asr_observe_known_transcript")
        # Count dispatch intents even if the read fails before receipt persistence.
        number = len(list(self.out.glob("observe-*.intent.json")))
        self.intent(f"observe-{number:04}")
        value = await self.request("GET", "/v2/transcript/" + identifier, credential, timeout)
        if value.get("id") != identifier:
            raise WorkflowError("ASR_TRANSCRIPT_ID_CHANGED")
        if value.get("status") == "completed":
            if value.get("language_code") != "vi":
                raise WorkflowError("ASR_LANGUAGE_MISMATCH")
            used = value.get("speech_model_used")
            if used != assemblyai_asr_profile().model:
                raise WorkflowError("ASR_MODEL_MISMATCH_NO_FALLBACK")
            self.save("provider-completed", value)
        return value


def visual_metadata(config, asset):
    """Measured visual descriptors only; no semantic inference from filenames."""
    from PIL import Image
    source = media_path(config, asset["id"])
    if asset["kind"] == "video":
        frame = subprocess.run([str(config.ffmpeg_bin / "ffmpeg.exe"), "-v", "error", "-nostdin",
            "-protocol_whitelist", "file,pipe", "-ss", str(min(.5, asset["duration_seconds"]/2)), "-i", str(source),
            "-map", f"0:{asset['video_stream_index']}", "-frames:v", "1", "-vf", "scale=160:-2",
            "-f", "image2pipe", "-c:v", "png", "-"], capture_output=True, timeout=30)
        if frame.returncode or not frame.stdout:
            raise WorkflowError("ASR_LOCAL_FRAME_EXTRACTION_FAILED")
        source = io.BytesIO(frame.stdout)
    with Image.open(source) as image:
        rgb = list(image.convert("RGB").resize((1, 1)).getpixel((0, 0)))
    metadata = {"width": asset["width"], "height": asset["height"],
                "orientation": "portrait" if asset["height"] > asset["width"] else "landscape" if asset["width"] > asset["height"] else "square",
                "average_rgb": rgb, "mean_luminance": round(.2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2], 2),
                "visual_descriptor_source": "measured_source_frame_pixels", "semantic_content": "not_analyzed",
                "audio_present": bool(asset.get("has_audio")), "duration_seconds": asset.get("duration_seconds"),
                "fps": asset.get("fps"), "shots": []}
    if asset["kind"] == "video":
        duration = asset["duration_seconds"]
        result = subprocess.run([str(config.ffmpeg_bin / "ffmpeg.exe"), "-v", "info", "-nostdin",
            "-protocol_whitelist", "file,pipe", "-i", str(media_path(config, asset["id"])),
            "-map", f"0:{asset['video_stream_index']}", "-an", "-vf",
            "scale=160:-2,select='gt(scene,0.35)',showinfo", "-f", "null", "-"], capture_output=True, timeout=120)
        if result.returncode:
            raise WorkflowError("ASR_LOCAL_SCENE_ANALYSIS_FAILED")
        boundaries = [0.0] + sorted({float(t) for t in re.findall(rb"pts_time:([0-9.]+)", result.stderr)
                                     if 0 < float(t) < duration}) + [duration]
        metadata["shots"] = [{"start_seconds": a, "end_seconds": b} for a, b in zip(boundaries, boundaries[1:])]
        metadata["shot_source"] = "ffmpeg_scene_score_threshold_0.35"
    return metadata


def extract_audio(config, asset, out, artifacts):
    checkpoint = artifacts.load("audio")
    path = out / "speech.wav"
    if checkpoint:
        return path, checkpoint["result"]
    partial = out / "speech.part.wav"
    result = subprocess.run([str(config.ffmpeg_bin / "ffmpeg.exe"), "-v", "error", "-xerror", "-nostdin", "-y",
        "-protocol_whitelist", "file,pipe", "-i", str(media_path(config, asset["id"])),
        "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(partial)],
        capture_output=True, timeout=120)
    if result.returncode or not partial.is_file():
        raise WorkflowError("ASR_AUDIO_EXTRACTION_FAILED")
    with wave.open(str(partial), "rb") as audio:
        duration = audio.getnframes()/audio.getframerate()
        if not 0 < duration <= 600 or audio.getnchannels() != 1 or audio.getframerate() != 16000:
            raise WorkflowError("ASR_EXTRACTED_AUDIO_INVALID")
    if partial.stat().st_size > 25_000_000:
        raise WorkflowError("ASR_AUDIO_MAX_25MB")
    os.replace(partial, path)
    metadata = {"duration_seconds": duration, "sha256": file_sha(path), "bytes": path.stat().st_size,
                "channels": 1, "sample_rate": 16000, "source_sha256": asset["sha256"]}
    artifacts.commit("audio", [path], metadata)
    return path, metadata


def analyze(config, job, out, stage, *, transport_factory=DurableTransport):
    document = job["snapshot"]["document"]
    assets = pending_assets(document)
    if pending_speech(document) and not connection.status(config)["connected"]:
        raise WorkflowError("ASR_PROVIDER_UNAVAILABLE_NO_TRANSCRIPT", 503)
    records = []
    for asset in assets:
        source = media_path(config, asset["id"])
        if asset.get("rights_confirmed") is not True or not source.is_file() or file_sha(source) != asset["sha256"]:
            raise WorkflowError("ASR_SOURCE_MEDIA_CHANGED_OR_RIGHTS_MISSING")
        directory = out / "analysis" / asset["id"]
        directory.mkdir(parents=True, exist_ok=True)
        artifacts = Artifacts(directory, job)
        checkpoint = artifacts.load("analysis")
        if checkpoint:
            records.append(checkpoint["result"])
            continue
        stage("asr_local_media_analysis")
        record = {"asset_id": asset["id"], "source_sha256": asset["sha256"], "media": visual_metadata(config, asset),
                  "transcript": None, "provider_calls": 0}
        paths = []
        if asset["kind"] == "video" and asset.get("has_audio"):
            from app.assemblyai_transcription_provider import AssemblyAITranscriptionProvider
            from app.auto_edit_models import MediaMetadata
            stage("asr_extract_audio")
            audio, metadata = extract_audio(config, asset, directory, artifacts)
            profile = assemblyai_asr_profile()
            transport = transport_factory(directory / "provider", digest({"snapshot": job["snapshot"],
                "asset_id": asset["id"], "audio": metadata, "profile_sha256": assemblyai_profile_sha256()}), stage)
            if isinstance(transport, DurableTransport):
                from .costs import CostLedger
                from .store import Store
                transport.cost_ledger = CostLedger(Store(config.data_root))
                transport.cost_context = {'project_id': job['project_id'], 'job_id': job['id']}
            provider = AssemblyAITranscriptionProvider(model=profile.model, credential_alias=ASSEMBLYAI_CREDENTIAL_ALIAS,
                credential_resolver=lambda _: connection.load_credential(config), profile=profile, transport=transport)
            async def execute():
                return await asyncio.wait_for(provider.transcribe(audio, metadata=MediaMetadata(media_kind="audio",
                    detected_content_type="audio/wav", duration_seconds=metadata["duration_seconds"],
                    audio_channels=1, audio_sample_rate=16000), checksum_sha256=metadata["sha256"]), timeout=180)
            try:
                transcript = asyncio.run(execute())
            except (TimeoutError, asyncio.TimeoutError):
                raise WorkflowError("ASR_OBSERVATION_TIMEOUT_RESUME_KNOWN_JOB") from None
            except (ValueError, WorkflowError) as error:
                # Never include a provider message, response body or credential.
                code = error.code if isinstance(error, WorkflowError) else str(error)
                if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,119}", code):
                    code = "ASR_RESULT_VALIDATION_FAILED"
                raise WorkflowError("ASR_" + code if not code.startswith("ASR_") else code) from None
            value = asdict(transcript)
            # The reused adapter's historical cost formula is an estimate, not a billed receipt.
            value.pop("actual_cost_vnd", None)
            raw = transport.load("provider-completed")
            if raw is None or digest(raw) != value["provenance"]["raw_response_sha256"]:
                raise WorkflowError("ASR_RAW_RESPONSE_BINDING_MISMATCH")
            record.update(transcript=value, audio=metadata, provider_calls=2 + len(list((directory/"provider").glob("observe-*.intent.json"))))
            paths = [audio, directory/"checkpoint-audio.json", directory/"provider"/"provider-completed.json",
                     directory/"provider"/"upload-ack.json", directory/"provider"/"transcript-ack.json"]
        record["analysis_sha256"] = digest(record)
        durable_json(directory / "analysis.json", record)
        artifacts.commit("analysis", paths + [directory/"analysis.json"], record)
        records.append(record)
    result = {"media_analysis": records, "source": "measured_media_and_real_provider_transcript",
              "provider_calls": sum(r["provider_calls"] for r in records), "human_review_required": True,
              "automatic_paid_replay": False}
    durable_json(out / "analysis-result.json", result)
    paths = [p for p in (out/"analysis").rglob("*") if p.is_file() and p.suffix in {".json", ".wav"} and ".part." not in p.name]
    Artifacts(out, job).commit("asr", paths + [out/"analysis-result.json"], result)
    return result


def validate_resume(root, job):
    out = Path(root)/"jobs"/job["id"]
    for directory in (out/"analysis").glob("*"):
        if not directory.is_dir():
            continue
        artifacts = Artifacts(directory, job)
        artifacts.load("audio")
        if artifacts.load("analysis"):
            continue
        provider = directory/"provider"
        if not provider.exists():
            continue
        # Loading validates binding/hash during execution. Here refuse ambiguous paid states.
        for name, ack in (("upload", "upload-ack"), ("create-transcript", "transcript-ack")):
            if (provider/(name+".intent.json")).exists() and not (provider/(ack+".json")).exists():
                raise WorkflowError("ASR_OUTCOME_UNKNOWN_NO_REPLAY")
