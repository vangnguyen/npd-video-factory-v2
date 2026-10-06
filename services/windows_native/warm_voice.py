"""Opt-in warmed scenes, with isolated local synthesis and real ASR trim evidence.

The accepted voice/profile and legacy synthesis path remain unchanged. A cache
entry is content addressed; incomplete inference is never automatically replayed.
ASR runs only in the coordinator, outside the offline inference subprocess.
"""
import argparse
import asyncio
from dataclasses import asdict
import difflib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import wave

from .contracts import PROFILE_SHA, Proposal, WorkflowError, canonical, digest, file_sha, normalize
from .hardening import durable_json

RATE = 48000
POLICY_ID = "warm-scene-context-v1"


def read_json(path):
    return json.loads(Path(path).read_bytes())


def build_plan(proposal, policy):
    """Cache identity binds exact approved target/context and effective inference."""
    from .pipeline import profile, sentence_units
    from vieneu_utils.phonemize_text import normalize_to_chunks_v3_with_gaps, phonemize_text_with_emotions
    if policy.get("id") != POLICY_ID or policy.get("sampling_overrides") != {}:
        raise WorkflowError("WARM_VOICE_POLICY_INVALID")
    locked = profile()
    parameters = {k: locked["parameters"][k] for k in
                  ("temperature", "top_k", "top_p", "repetition_penalty", "max_new_frames")}
    sentences = sentence_units(proposal)
    plans = []
    for scene in proposal.visual_brief:
        if not normalize(scene.narration_excerpt):
            continue
        prior = [u for u in sentences if u["scene"] < scene.scene]
        context = prior[-1]["text"] if prior else ""
        target = normalize(scene.narration_excerpt)
        combined = normalize(context + " " + target)
        if len(combined) >= policy["combined_text_character_limit"]:
            raise WorkflowError("WARM_VOICE_CONTEXT_TOO_LONG")
        chunks, gaps = normalize_to_chunks_v3_with_gaps(combined, max_chars=policy["normalization_max_chars"])
        if len(chunks) != 1 or gaps:
            raise WorkflowError("WARM_VOICE_SINGLE_CONTEXT_REQUIRED")
        plans.append({"schema_version": 1, "scene": scene.scene, "target_text": target,
                      "context_text": context, "combined_text": combined, "normalized_text": chunks[0],
                      "phonemes": phonemize_text_with_emotions(chunks[0]),
                      "profile_sha256": PROFILE_SHA, "preset_sha256": locked["rights"]["preset_asset_sha256"],
                      "policy_sha256": digest(policy), "seed": policy["random_seed"],
                      "normalization_max_chars": policy["normalization_max_chars"],
                      "effective_sampling_parameters": parameters, "sample_rate": RATE,
                      "channels": 1, "sample_width": 2})
    return plans


def cache_key(plan):
    return digest(plan)


def cache_directory(config, plan):
    root = (config.data_root / "voice-context-cache").resolve()
    path = root / cache_key(plan)
    if path.resolve().parent != root or path.is_symlink():
        raise WorkflowError("WARM_VOICE_CACHE_PATH_INVALID")
    return path


def preserve_json(path, value):
    path = Path(path)
    if path.exists():
        if read_json(path) != value:
            raise WorkflowError("WARM_VOICE_CACHE_BINDING_CHANGED")
    else:
        durable_json(path, value)


def read_wave(path):
    import numpy as np
    with wave.open(str(path), "rb") as wav:
        if (wav.getnchannels(), wav.getframerate(), wav.getsampwidth()) != (1, RATE, 2):
            raise WorkflowError("WARM_VOICE_SOURCE_FORMAT_INVALID")
        values = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").copy()
    if not len(values):
        raise WorkflowError("WARM_VOICE_SOURCE_EMPTY")
    return values


def generated_record(folder, plan):
    path = folder / "generated.json"
    if not path.exists():
        return None
    if read_json(folder / "plan.json") != plan:
        raise WorkflowError("WARM_VOICE_CACHE_BINDING_CHANGED")
    record = read_json(path)
    source = folder / "source.wav"
    if (record.get("schema_version") != 1 or record.get("plan_sha256") != cache_key(plan)
            or record.get("source_wave_sha256") != file_sha(source)
            or record.get("observed_eos") is not True or record.get("network_blocked") is not True
            or record.get("retries") != 0):
        raise WorkflowError("WARM_VOICE_GENERATED_BINDING_CHANGED")
    audio = read_wave(source)
    if not math.isfinite(record.get("duration_seconds", -1)) or abs(len(audio) / RATE - record["duration_seconds"]) > 1 / RATE:
        raise WorkflowError("WARM_VOICE_SOURCE_DURATION_CHANGED")
    return record


def generate_offline(out):
    """Fresh process: exactly one locally isolated call for each missing scene."""
    import numpy as np
    import socket
    from .pipeline import Config, profile, verify_runtime
    from .voice_quality import resolve_policy
    out = Path(out)
    config = Config.load(out / "runtime-config.json")
    snapshot = read_json(out / "input.json")
    approval, document = snapshot.get("approval"), snapshot.get("document")
    if not approval or not document or approval.get("snapshot_sha256") != digest(document):
        raise WorkflowError("HUMAN_APPROVAL_REQUIRED_BEFORE_TTS")
    policy = resolve_policy(document)
    if not policy or policy.get("id") != POLICY_ID:
        raise WorkflowError("WARM_VOICE_POLICY_INVALID")
    proposal = Proposal.model_validate(document["proposal"])
    expected = [{"plan": plan, "folder": str(cache_directory(config, plan))}
                for plan in build_plan(proposal, policy)]
    entries = read_json(out / "warm-generation.json")["entries"]
    if entries != expected:
        raise WorkflowError("WARM_VOICE_GENERATION_PLAN_BINDING_CHANGED")
    verify_runtime(config)
    import vieneu
    from vieneu._v3_turbo_engine.onnx_runtime_lite import OnnxV3LiteEngine
    generated = []
    pending = []
    for entry in entries:
        plan, folder = entry["plan"], Path(entry["folder"])
        if folder != cache_directory(config, plan):
            raise WorkflowError("WARM_VOICE_CACHE_PATH_INVALID")
        folder.mkdir(parents=True, exist_ok=True)
        preserve_json(folder / "plan.json", plan)
        if generated_record(folder, plan):
            continue
        if (folder / "generation.intent.json").exists() or (folder / "source.wav").exists():
            raise WorkflowError("WARM_TTS_OUTCOME_UNKNOWN_NO_REPLAY")
        pending.append((plan, folder))
    if not pending:
        durable_json(out / "warm-generation-result.json", {"new_inference_calls": 0, "plan_keys": generated})
        return

    def blocked_connect(*args, **kwargs):
        raise WorkflowError("LOCAL_TTS_OUTBOUND_NETWORK_BLOCKED")
    socket.socket.connect = blocked_connect
    class OfflineEngine(OnnxV3LiteEngine):
        def _load_denoiser(self):
            return None
        def _acoustic_frame(self, *args, **kwargs):
            codes, eos = super()._acoustic_frame(*args, **kwargs)
            self.observed_frames += 1
            self.observed_eos = bool(eos)
            return codes, eos
    engine = OfflineEngine(checkpoint_path=str(config.runtime_root / "models/vieneu-v3-turbo"),
                           onnx_dir=str(config.runtime_root / "models/vieneu-v3-turbo/onnx_update"),
                           codec_dir=str(config.runtime_root / "models/moss-codec"), threads=4)
    engine.babble_retries = 0
    preset = read_json(Path(vieneu.__file__).parent / "assets/voices_v3_turbo.json")["presets"][profile()["voice_id"]]
    for plan, folder in pending:
        with (folder / "generation.intent.json").open("xb") as intent:
            intent.write(canonical({"plan_sha256": cache_key(plan), "automatic_inference_retry": False}))
            intent.flush()
            import os
            os.fsync(intent.fileno())
        np.random.seed(plan["seed"])
        engine.observed_frames, engine.observed_eos = 0, False
        audio = engine.infer(phonemes=plan["phonemes"],
                             speaker_emb=np.asarray(preset["speaker_emb"], dtype=np.float32),
                             ref_codes=np.asarray(preset["codes"], dtype=np.int64),
                             **plan["effective_sampling_parameters"])
        if not engine.observed_eos:
            raise WorkflowError("SYNTHESIS_FRAME_CAP_WITHOUT_EOS_STOP")
        if not audio.size or not np.isfinite(audio).all():
            raise WorkflowError("INVALID_TTS_AUDIO")
        if float(np.abs(audio).max()) > 1:
            raise WorkflowError("WARM_TTS_CLIPPING_REQUIRES_REVIEW")
        with (folder / "source.wav").open("xb") as dest, wave.open(dest, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(RATE)
            wav.writeframes((audio * 32767).astype("<i2").tobytes())
        durable_json(folder / "generated.json", {"schema_version": 1, "plan_sha256": cache_key(plan),
                     "source_wave_sha256": file_sha(folder / "source.wav"), "duration_seconds": len(audio) / RATE,
                     "observed_eos": True, "frames": engine.observed_frames, "network_blocked": True,
                     "retries": 0, "origin": {"method": "fresh_offline_warm_scene_inference",
                     "producer_source_sha256": file_sha(Path(__file__))}})
        generated.append(cache_key(plan))
    durable_json(out / "warm-generation-result.json", {"new_inference_calls": len(generated), "plan_keys": generated})


def timing_record(folder, plan, generated):
    path = folder / "timing.json"
    if not path.exists():
        return None
    value = read_json(path)
    transcript = value.get("transcript", {})
    raw = value.get("raw_response", {})
    provenance = transcript.get("provenance", {})
    if (value.get("schema_version") != 1 or value.get("plan_sha256") != cache_key(plan)
            or value.get("source_wave_sha256") != generated["source_wave_sha256"]
            or provenance.get("provider") != "assemblyai-transcription" or provenance.get("raw_response_sha256") != digest(raw)
            or raw.get("status") != "completed" or raw.get("id") != provenance.get("transcript_id")
            or provenance.get("word_timing_source") != "provider_native_word_timestamps"):
        raise WorkflowError("WARM_VOICE_TIMING_BINDING_CHANGED")
    raw_words = raw.get("words")
    words = [w for segment in transcript.get("segments", []) for w in segment.get("words", [])]
    if not isinstance(raw_words, list) or len(raw_words) != len(words) or not words:
        raise WorkflowError("WARM_VOICE_TIMING_WORDS_CHANGED")
    previous_end = 0
    for source, actual in zip(raw_words, words):
        start, end = actual.get("start_seconds"), actual.get("end_seconds")
        if (not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                or not math.isfinite(start) or not math.isfinite(end) or not previous_end <= start < end <= generated["duration_seconds"] + .001
                or actual.get("text") != source.get("text")
                or abs(start * 1000 - source.get("start", -999)) > .001
                or abs(end * 1000 - source.get("end", -999)) > .001):
            raise WorkflowError("WARM_VOICE_TIMING_WORDS_CHANGED")
        previous_end = end
    return value


def observe_timing(config, folder, plan, generated):
    """Use the existing connected provider; ambiguous paid intents never replay."""
    cached = timing_record(folder, plan, generated)
    if cached:
        return cached
    from . import assemblyai_connection as connection
    from .asr import DurableTransport
    from .pipeline import REPO
    sys.path.insert(0, str(REPO / "apps/api"))
    from app.assemblyai_asr_profile import ASSEMBLYAI_CREDENTIAL_ALIAS, assemblyai_asr_profile, assemblyai_profile_sha256
    from app.assemblyai_transcription_provider import AssemblyAITranscriptionProvider
    from app.auto_edit_models import MediaMetadata
    if not connection.status(config)["connected"]:
        raise WorkflowError("WARM_VOICE_EXISTING_ASR_CONNECTION_REQUIRED")
    profile = assemblyai_asr_profile()
    binding = digest({"plan_sha256": cache_key(plan), "source_wave_sha256": generated["source_wave_sha256"],
                      "profile_sha256": assemblyai_profile_sha256()})
    transport = DurableTransport(folder / "provider", binding, lambda stage: None)
    provider = AssemblyAITranscriptionProvider(model=profile.model, credential_alias=ASSEMBLYAI_CREDENTIAL_ALIAS,
               credential_resolver=lambda _: connection.load_credential(config), profile=profile,
               transport=transport, poll_interval_seconds=3)
    async def execute():
        return await asyncio.wait_for(provider.transcribe(folder / "source.wav",
            metadata=MediaMetadata(media_kind="audio", detected_content_type="audio/wav",
                duration_seconds=generated["duration_seconds"], audio_channels=1, audio_sample_rate=RATE),
            checksum_sha256=generated["source_wave_sha256"]), timeout=180)
    try:
        transcript = asdict(asyncio.run(execute()))
    except (ValueError, TimeoutError) as error:
        code = str(error)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,119}", code):
            code = "WARM_VOICE_ASR_TIMING_FAILED"
        raise WorkflowError(code) from None
    transcript.pop("actual_cost_vnd", None)
    raw = transport.load("provider-completed")
    value = {"schema_version": 1, "plan_sha256": cache_key(plan),
             "source_wave_sha256": generated["source_wave_sha256"], "transcript": transcript,
             "raw_response": raw, "origin": {"method": "existing_assemblyai_provider",
             "automatic_paid_replay": False, "provider_is_fixture": False,
             "provider_receipt_binding": binding}}
    durable_json(folder / "timing.json", value)
    return timing_record(folder, plan, generated)


def tokens(text):
    return re.findall(r"\w+", text.casefold())


def provider_counts(folder):
    provider = folder / "provider"
    return {"upload_requests": int((provider / "upload.intent.json").exists()),
            "transcript_create_requests": int((provider / "create-transcript.intent.json").exists()),
            "observe_requests": len(list(provider.glob("observe-*.intent.json")))}


def archive_source(folder, out, scene):
    """Keep source bytes and exact actual provider receipts inside the attempt."""
    target = out / "context-sources" / f"scene-{scene:02}"
    paths = [folder / name for name in ("plan.json", "source.wav", "generated.json", "timing.json", "generation.intent.json")]
    paths += sorted((folder / "provider").glob("*.json"))
    metadata = []
    for source in paths:
        if not source.exists():
            continue
        if source.is_symlink():
            raise WorkflowError("WARM_VOICE_CACHE_PATH_INVALID")
        relative = source.relative_to(folder)
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if file_sha(dest) != file_sha(source):
                raise WorkflowError("WARM_VOICE_ARCHIVE_BINDING_CHANGED")
        else:
            shutil.copyfile(source, dest)
        metadata.append({"path": dest.relative_to(out).as_posix(), "sha256": file_sha(dest), "bytes": dest.stat().st_size})
    return target, metadata


def quiet_gaps(audio, start, end):
    import numpy as np
    begin, stop, size = round(start * RATE), round(end * RATE), 480
    clip = audio[begin:stop]
    frames = len(clip) // size
    if not frames:
        return []
    levels = np.sqrt(np.mean(clip[:frames * size].reshape(frames, size) ** 2, axis=1))
    edges = np.diff(np.r_[False, levels < .0015, False].astype(np.int8))
    return [{"start_seconds": (begin + a * size) / RATE, "end_seconds": (begin + b * size) / RATE}
            for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))
            if b - a >= 6 and a > 0 and b < frames]


def match_opening(plan, expanded):
    """Match approved spellings exactly; never invent or fuzz missing onset words."""
    from vieneu_utils.phonemize_text import normalize_to_chunks_v3_with_gaps
    normalized, _ = normalize_to_chunks_v3_with_gaps(plan["target_text"], max_chars=4096)
    expected = tokens(" ".join(normalized))
    variants = [("sdk_normalized_approved_target", expected)]
    original = tokens(plan["target_text"])
    if original != expected:
        variants.append(("original_approved_target_spelling", original))
    resolved, ambiguous = [], False
    for representation, candidate in variants:
        if len(candidate) < 2:
            continue
        for size in range(2, min(8, len(candidate)) + 1):
            prefix = candidate[:size]
            matches = [i for i in range(len(expanded) - size + 1)
                       if [t for t, _ in expanded[i:i + size]] == prefix]
            if not matches:
                break
            if len(matches) == 1:
                resolved.append({"representation": representation, "flat_token_index": matches[0],
                                 "matched_opening_tokens": prefix, "exact_prefix_token_count": size})
                break
        else:
            if len(matches) > 1:
                ambiguous = True
    if not resolved or ambiguous:
        raise WorkflowError("WARM_VOICE_UNIQUE_TARGET_ONSET_REQUIRED")
    if len({match["flat_token_index"] for match in resolved}) != 1:
        raise WorkflowError("WARM_VOICE_TARGET_VARIANTS_DISAGREE")
    return resolved[0]["flat_token_index"], expected, resolved


def anchored_disputed_opening(plan, expanded, words, audio):
    """Locate existing disputed onset PCM from exact anchors on both sides.

    This never substitutes a word: one/two actual ASR head tokens remain in
    audio, and full word accuracy remains an explicit human review question.
    """
    from vieneu_utils.phonemize_text import normalize_to_chunks_v3_with_gaps
    normalized, _ = normalize_to_chunks_v3_with_gaps(plan["target_text"], max_chars=4096)
    expected = tokens(" ".join(normalized))
    targets = [expected]
    original = tokens(plan["target_text"])
    if original != expected:
        targets.append(original)
    normalized_context, _ = normalize_to_chunks_v3_with_gaps(plan["context_text"], max_chars=4096)
    contexts = [tokens(" ".join(normalized_context))]
    original_context = tokens(plan["context_text"])
    if original_context != contexts[0]:
        contexts.append(original_context)
    candidates = {}
    for context in contexts:
        for size in range(4, min(8, len(context)) + 1):
            suffix = context[-size:]
            for target in targets:
                for head_size in (1, 2):
                    following = target[head_size:head_size + 3]
                    if len(following) != 3:
                        continue
                    for flat in range(size, len(expanded) - head_size - 2):
                        if ([t for t, _ in expanded[flat - size:flat]] != suffix
                                or [t for t, _ in expanded[flat + head_size:flat + head_size + 3]] != following):
                            continue
                        actual_head = [t for t, _ in expanded[flat:flat + head_size]]
                        if actual_head == target[:head_size]:
                            continue
                        first_index = expanded[flat][1]
                        if first_index <= 0 or expanded[flat - 1][1] == first_index:
                            continue
                        previous, first = words[first_index - 1], words[first_index]
                        pauses = [p for p in quiet_gaps(audio, previous["start_seconds"], first["end_seconds"])
                                  if abs((p["start_seconds"] + p["end_seconds"]) / 2 - first["start_seconds"]) <= .25 + 1e-9]
                        if len(pauses) != 1:
                            continue
                        # One- and two-token interpretations can locate the same
                        # existing onset (the second token may already agree).
                        # Retain the shortest disputed head at that exact onset.
                        if flat in candidates and candidates[flat]["disputed_head_token_count"] < head_size:
                            continue
                        candidates[flat] = {
                            "representation": "exact_context_suffix_and_target_continuation_with_actual_disputed_head",
                            "flat_token_index": flat, "actual_disputed_head_tokens": actual_head,
                            "approved_head_tokens": target[:head_size], "disputed_head_token_count": head_size,
                            "actual_mismatched_head_token_count": sum(a != b for a, b in zip(actual_head, target[:head_size])),
                            "matched_context_suffix": suffix, "matched_target_continuation": following,
                            "matched_opening_tokens": [], "exact_prefix_token_count": 0,
                            "measured_quiet_gaps": pauses, "first_target_word": first,
                            "previous_word": previous, "full_target_word_accuracy_confirmed": False}
    if len(candidates) != 1:
        raise WorkflowError("WARM_VOICE_DISPUTED_HEAD_REVIEW_REQUIRED")
    candidate = next(iter(candidates.values()))
    return candidate["flat_token_index"], expected, [candidate]


def trim_boundary(plan, audio, timing):
    """Same reviewed B onset rule; uncertainty is an explicit failure."""
    words = [w for segment in timing["transcript"]["segments"] for w in segment["words"]]
    expanded = [(token, index) for index, word in enumerate(words) for token in tokens(word["text"])]
    disputed = False
    try:
        flat, expected, opening_matches = match_opening(plan, expanded)
    except WorkflowError as error:
        if error.code != "WARM_VOICE_UNIQUE_TARGET_ONSET_REQUIRED":
            raise
        try:
            flat, expected, opening_matches = anchored_disputed_opening(plan, expanded, words, audio)
        except WorkflowError:
            raise error from None
        disputed = True
    first_index = expanded[flat][1]
    if first_index <= 0:
        raise WorkflowError("WARM_VOICE_CONTEXT_BOUNDARY_MISSING")
    previous, first = words[first_index - 1], words[first_index]
    gap = first["start_seconds"] - previous["end_seconds"]
    grouped = flat > 0 and expanded[flat - 1][1] == first_index
    if disputed:
        pauses = opening_matches[0]["measured_quiet_gaps"]
        cut = (pauses[0]["start_seconds"] + pauses[0]["end_seconds"]) / 2
        method = "unique_exact_context_and_continuation_anchors_actual_disputed_head_unique_60ms_quiet_gap"
    elif grouped:
        pauses = quiet_gaps(audio, first["start_seconds"], first["end_seconds"])
        if len(pauses) != 1:
            raise WorkflowError("WARM_VOICE_GROUPED_BOUNDARY_REVIEW_REQUIRED")
        cut = (pauses[0]["start_seconds"] + pauses[0]["end_seconds"]) / 2
        method = "unique_measured_60ms_quiet_gap_inside_context_target_asr_group"
    elif gap < .04:
        pauses = [p for p in quiet_gaps(audio, previous["start_seconds"], first["end_seconds"])
                  if abs((p["start_seconds"] + p["end_seconds"]) / 2 - first["start_seconds"]) <= .25]
        if len(pauses) != 1:
            raise WorkflowError("WARM_VOICE_TOUCHING_BOUNDARY_REVIEW_REQUIRED")
        cut = (pauses[0]["start_seconds"] + pauses[0]["end_seconds"]) / 2
        method = "unique_measured_60ms_quiet_gap_near_touching_asr_words"
    else:
        if gap > 2:
            raise WorkflowError("WARM_VOICE_BOUNDARY_REVIEW_REQUIRED")
        pauses = []
        cut = (previous["end_seconds"] + first["start_seconds"]) / 2
        method = "unique_exact_approved_opening_tokens_provider_word_gap_midpoint"
    samples = round(cut * RATE)
    if not 0 < samples < len(audio):
        raise WorkflowError("WARM_VOICE_CUT_OUTSIDE_SOURCE")
    actual = " ".join(t for t, _ in expanded[flat:])
    return {"method": method, "cut_seconds": cut, "removed_samples": samples,
            "removed_context": plan["context_text"], "matched_opening_tokens": opening_matches[0]["matched_opening_tokens"],
            "opening_matches": opening_matches,
            "onset_asr_disputed": disputed,
            "previous_word": previous, "first_target_word": first, "gap_seconds": gap,
            "asr_group_spans_context_and_target": grouped, "measured_quiet_gaps": pauses,
            "provider_native_timestamps_are_approximate": True,
            "actual_target_asr_text": actual,
            "raw_text_token_similarity_diagnostic": round(difflib.SequenceMatcher(a=expected, b=tokens(actual), autojunk=False).ratio(), 4),
            "asr_disagreement_is_not_proof_of_an_audio_word_error": True,
            "full_target_word_accuracy_confirmed": False, "human_audio_accepted": False}


def synthesize_warm(config, snapshot, out, policy):
    """Coordinate isolated inference, actual timing, then existing scene rendering."""
    import numpy as np
    from vieneu_utils.core_utils import edge_silence, gaps_to_silence, join_audio_chunks, pause_pad_samples
    from .pipeline import measured_scene_units, profile
    out = Path(out)
    proposal = Proposal.model_validate(snapshot["document"]["proposal"])
    plans = build_plan(proposal, policy)
    entries = [{"plan": plan, "folder": str(cache_directory(config, plan))} for plan in plans]
    durable_json(out / "warm-generation.json", {"entries": entries})
    preserve_json(out / "input.json", snapshot)
    preserve_json(out / "runtime-config.json", config.dump())
    try:
        with (out / "warm-generation.log").open("w", encoding="utf-8") as log:
            completed = subprocess.run([sys.executable, "-m", "services.windows_native.warm_voice", "generate", str(out)],
                cwd=Path(__file__).resolve().parents[2], stdout=log, stderr=log, timeout=480)
    except subprocess.TimeoutExpired:
        raise WorkflowError("TTS_TIMEOUT_NO_AUTOMATIC_INFERENCE_RETRY") from None
    if completed.returncode:
        status = out / "warm-generation-status.json"
        code = read_json(status).get("code", "WARM_TTS_CHILD_FAILED") if status.exists() else "WARM_TTS_CHILD_FAILED"
        raise WorkflowError(code)
    records, waves, sources, offset = [], [], [], 0
    for index, entry in enumerate(entries):
        plan, folder = entry["plan"], Path(entry["folder"])
        generated = generated_record(folder, plan)
        if generated is None:
            raise WorkflowError("WARM_VOICE_GENERATION_INCOMPLETE")
        pcm = read_wave(folder / "source.wav")
        archive_source(folder, out, plan["scene"])
        before = provider_counts(folder)
        timing_reused = (folder / "timing.json").is_file() if plan["context_text"] else False
        try:
            timing = observe_timing(config, folder, plan, generated) if plan["context_text"] else None
        finally:
            archived, archived_files = archive_source(folder, out, plan["scene"])
        after = provider_counts(folder)
        boundary = trim_boundary(plan, pcm.astype(np.float64) / 32768, timing) if timing else {
            "method": "first_scene_without_extra_context", "cut_seconds": 0, "removed_samples": 0,
            "removed_context": "", "human_audio_accepted": False, "full_target_word_accuracy_confirmed": False}
        audio = pcm[boundary["removed_samples"]:].astype(np.float64) / 32768
        if index:
            offset += pause_pad_samples(waves[-1], audio, RATE, gaps_to_silence(["sentence"])[0])
        lead, tail = edge_silence(audio, RATE)
        records.append({"index": index, "scene": plan["scene"], "text": plan["target_text"],
                        "start_seconds": offset / RATE, "end_seconds": (offset + len(audio)) / RATE,
                        "activity_start_seconds": (offset + lead) / RATE,
                        "activity_end_seconds": (offset + len(audio) - tail) / RATE})
        offset += len(audio)
        waves.append(audio)
        sources.append({"plan_sha256": cache_key(plan), "plan": plan, "generated": generated,
                        "boundary": boundary, "timing": timing, "source_wave_path": str(archived / "source.wav"),
                        "source_wave_sha256": generated["source_wave_sha256"],
                        "cache_path": str(folder), "source_wave_preserved": True,
                        "archived_files": archived_files, "timing_reused": timing_reused,
                        "provider_requests_this_attempt": {key: after[key] - before[key] for key in after},
                        "provider_receipts_total_in_cache": after})
    audio = join_audio_chunks(waves, RATE, silence_ps=gaps_to_silence(["sentence"] * (len(waves) - 1)))
    if len(audio) != offset or offset > RATE * profile()["max_audio_seconds"]:
        raise WorkflowError("WARM_VOICE_TIMING_OR_DURATION_INVALID")
    # PCM remains sample exact through trimming; only silence is added at joins.
    with (out / "voice.wav").open("xb") as dest, wave.open(dest, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(RATE)
        wav.writeframes(np.rint(audio * 32768).astype("<i2").tobytes())
    generation = read_json(out / "warm-generation-result.json")
    shared = {"quality_policy": policy, "quality_policy_sha256": digest(policy),
              "pipeline_source_sha256": file_sha(Path(__file__).with_name("pipeline.py")),
              "warm_source_sha256": file_sha(Path(__file__)), "sources": sources,
              "source_approval": snapshot["approval"], "source_document_sha256": digest(snapshot["document"])}
    meta = {"audio_sha256": file_sha(out / "voice.wav"), "profile_sha256": PROFILE_SHA,
            "duration_seconds": len(audio) / RATE, "units": records,
            "inference_calls": len(plans), "new_inference_calls": generation["new_inference_calls"],
            "reused_inference_calls": len(plans) - generation["new_inference_calls"],
            "provider_requests_this_attempt": {key: sum(s["provider_requests_this_attempt"][key] for s in sources)
                                                for key in ("upload_requests", "transcript_create_requests", "observe_requests")},
            "retries": 0, "network_blocked": True, "local_inference_network_blocked": True,
            "network_scope": "local_inference_subprocess_only",
            "timing_provider_network_allowed": True, "word_alignment": "none",
            "scene_boundary_timing": "real_provider_words_and_measured_quiet_gap",
            "voice": "Thùy Dung", "speed": 1, "human_listening_required": True,
            "effective_sampling_parameters": plans[0]["effective_sampling_parameters"], **shared}
    measured_scene_units(proposal, meta)
    durable_json(out / "tts-plan.json", {"profile_sha256": PROFILE_SHA, "units": plans, **shared})
    durable_json(out / "voice.json", meta)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["generate"])
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    try:
        generate_offline(args.out)
        durable_json(args.out / "warm-generation-status.json", {"status": "pass"})
        return 0
    except Exception as error:
        code = error.code if isinstance(error, WorkflowError) else type(error).__name__
        durable_json(args.out / "warm-generation-status.json", {"status": "failed", "code": code})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
