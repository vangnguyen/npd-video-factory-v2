"""Verify and package the existing Owner-accepted real MVP, without provider/TTS calls."""
import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from services.windows_native.contracts import file_sha
from services.windows_native.pipeline import Config


def main():
    source = Path(r"C:\NPD-Video-Factory\outputs\MVP1")
    destination = REPO / "evidence/windows-native-mvp"
    destination.mkdir(parents=True, exist_ok=True)
    load = lambda name: json.loads((source / name).read_bytes())
    content_approval = load("owner-content-approval.json")
    final_approval = load("owner-final-video-approval.json")
    proposal_sha = file_sha(source / "content-proposal.json")
    assert content_approval["proposal_sha256"] == proposal_sha
    assert content_approval["narration_file_sha256"] == file_sha(source / "narration.txt")
    assert final_approval["decision"] == "OWNER_FINAL_VIDEO_ACCEPTED"
    assert final_approval["final_video_sha256"] == file_sha(source / "final.mp4")
    assert final_approval["voice_sha256"] == file_sha(source / "voice.wav")
    qc = load("qc-report.json")
    assert qc["owner_final_video_accepted"] and all(qc["checks"].values())
    generation = load("content-generation.json")
    assert generation["http_status"] == 200 and generation["response_status"] == "completed"
    assert generation["content_generation_call_attempts"] == 1
    records = []

    def write(name, raw, lineage):
        path = destination / name
        if path.exists():
            if path.read_bytes() != raw:
                raise RuntimeError("EXISTING_EVIDENCE_DIFFERS_NO_OVERWRITE: " + name)
        else:
            with path.open("xb") as handle:
                handle.write(raw)
        records.append({"file": name, "sha256": file_sha(path), "bytes": path.stat().st_size,
                        "source": lineage})

    def write_json(name, value, lineage):
        write(name, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), lineage)

    for src, dst in (("content-proposal.json", "generated_script.json"), ("voice.wav", "tts.wav"),
                     ("final.mp4", "final.mp4"), ("owner-content-approval.json", "owner-content-approval.json"),
                     ("owner-final-video-approval.json", "owner-final-video-approval.json"),
                     ("qc-report.json", "qc-report.json"), ("voice.wav.vieneu.json", "tts-metadata.json"),
                     ("render-manifest.json", "render-manifest.json")):
        write(dst, (source / src).read_bytes(), str(source / src))
    write_json("input.json", {"source_task": "VF-MVP1-WINDOWS-NATIVE-FASTPATH-26",
                             "request": load("content-request.json"), "provider_evidence": generation,
                             "input_version": generation["prompt_sha256"]}, str(source / "content-request.json"))
    write_json("approved_script.json", {"proposal": load("content-proposal.json"),
                                        "script_version": "sha256:" + proposal_sha,
                                        "generated_script_sha256": proposal_sha,
                                        "narration": (source / "narration.txt").read_text(encoding="utf-8"),
                                        "human_approval": content_approval}, str(source / "owner-content-approval.json"))
    probe = subprocess.check_output([str(Config().ffmpeg_bin / "ffprobe.exe"), "-v", "error", "-show_streams",
                                     "-show_format", "-of", "json", str(destination / "final.mp4")], timeout=30)
    data = json.loads(probe)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    audio = next(s for s in data["streams"] if s["codec_type"] == "audio")
    assert (video["width"], video["height"], video["codec_name"]) == (1080, 1920, "h264")
    assert audio["codec_name"] == "aac" and int(audio["sample_rate"]) == 48000
    # ffprobe embeds the copied path, so this is a newly verified probe of identical bytes.
    write("ffprobe.json", probe, "read-only ffprobe of exact accepted MP4 copy")
    write_json("artifact-manifest.json", {"schema_version": 1, "evidence_type": "existing_real_accepted_mvp",
               "source_task": "VF-MVP1-WINDOWS-NATIVE-FASTPATH-26", "records": records,
               "provider_calls_this_capture": 0, "tts_calls_this_capture": 0,
               "does_not_approve_current_ui_project": True}, "original accepted artifacts plus current hash/probe verification")
    write_json("execution.log", {"verification": "existing accepted artifacts; not a fresh provider/TTS run",
               "source_generation": generation, "content_approval": content_approval,
               "original_tts_inferences": 4, "original_provider_attempts": 3,
               "technical_qc": qc["checks"], "final_approval": final_approval,
               "current_provider_calls": 0, "current_tts_calls": 0,
               "restart_fault_tests": "services/windows_native/tests/test_mvp_acceptance.py"}, str(source))
    print(json.dumps({"status": "REAL_ACCEPTED_ARTIFACTS_VERIFIED", "files": len(records),
                      "final_sha256": final_approval["final_video_sha256"], "provider_calls": 0, "tts_calls": 0}))


if __name__ == "__main__":
    main()
