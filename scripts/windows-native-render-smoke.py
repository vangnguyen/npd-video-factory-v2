"""Offline render regression with the accepted MVP1 audio; no new approval or TTS."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from services.windows_native.contracts import PROFILE_SHA, file_sha, write_json
from services.windows_native.pipeline import Config, render
from services.windows_native.media import ingest_media


def mixed_media(config, out, proposal):
    from PIL import Image
    assets = []
    for name, color in (("red", "red"), ("blue", "blue")):
        source = out / f"fixture-{name}.png"
        Image.new("RGB", (720, 480), color).save(source)
        assets.append(ingest_media(config, source, "image/png", source.name, rights_confirmed=True, illustration=False))
    source = out / "fixture-motion.mp4"
    subprocess.run([str(config.ffmpeg_bin / "ffmpeg.exe"), "-v", "error", "-nostdin", "-n", "-f", "lavfi", "-i",
        "testsrc2=size=720x480:rate=30:duration=0.8", "-f", "lavfi", "-i", "sine=frequency=1500:duration=0.8",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)], check=True, timeout=30)
    assets.insert(1, ingest_media(config, source, "video/mp4", "fixture-motion.mp4", rights_confirmed=True, illustration=False))
    return {"proposal": proposal, "assets": assets, "scene_media": [{"scene": i+1, "asset_id": a["id"]} for i, a in enumerate(assets)]}


def verify_mixed(config, out, audio_reference):
    import numpy as np
    manifest = json.loads((out / "render-manifest.json").read_bytes())
    ffmpeg = str(config.ffmpeg_bin / "ffmpeg.exe")
    def frame(t):
        raw = subprocess.check_output([ffmpeg, "-v", "error", "-ss", str(t), "-i", str(out / "final.mp4"),
            "-frames:v", "1", "-vf", "crop=600:420:240:680,scale=60:42", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], timeout=30)
        return np.frombuffer(raw, dtype=np.uint8).astype(np.float64).reshape(42, 60, 3)
    scenes = manifest["scenes"]
    red, blue = frame(.5).mean(axis=(0, 1)), frame(scenes[2]["start"]+.5).mean(axis=(0, 1))
    movement = np.mean(np.abs(frame(scenes[1]["start"]+.1)-frame(scenes[1]["start"]+.5)))
    late_movement = np.mean(np.abs(frame(scenes[1]["start"]+1.7)-frame(scenes[1]["start"]+2.1)))
    def audio(path):
        return subprocess.check_output([ffmpeg, "-v", "error", "-i", str(path), "-map", "0:a:0", "-c:a", "copy", "-f", "adts", "-"], timeout=30)
    checks = {"image_video_image_order": [s["kind"] for s in scenes] == ["image", "video", "image"],
        "first_scene_red_source": bool(red[0]>240 and max(red[1:])<10),
        "third_scene_blue_source": bool(blue[2]>240 and max(blue[:2])<10),
        "video_keeps_motion": bool(movement>2), "short_video_loops_with_motion": bool(late_movement>2),
        "source_audio_fully_muted": audio(out / "final.mp4") == audio(audio_reference)}
    for scene in scenes:
        probe = json.loads(subprocess.check_output([str(config.ffmpeg_bin / "ffprobe.exe"), "-v", "error", "-show_streams", "-of", "json", str(out/scene["file"])], timeout=30))
        checks[f"scene_{scene['scene']}_silent_source_segment"] = all(s["codec_type"] != "audio" for s in probe["streams"])
    write_json(out / "mixed-media-checks.json", {"checks": checks, "passed": all(checks.values()),
        "motion_mean_pixel_difference": movement, "loop_motion_mean_pixel_difference": late_movement,
        "audio_reference": str(audio_reference), "fixture_media_not_owner_assets": True})
    if not all(checks.values()):
        raise RuntimeError("MIXED_MEDIA_REGRESSION_FAILED")
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True, help="fresh directory outside the accepted MVP1 evidence")
    parser.add_argument("--mixed-media", action="store_true", help="synthetic red image / moving clip with tone / blue image")
    parser.add_argument("--audio-reference", type=Path, help="single-image regression MP4 to prove source tone is not mixed")
    args = parser.parse_args()
    out = args.output.resolve()
    accepted = Path(r"C:\NPD-Video-Factory\outputs\MVP1")
    if out == accepted or accepted in out.parents or out.exists():
        parser.error("fresh output outside MVP1 required")
    if args.mixed_media and (not args.audio_reference or not args.audio_reference.is_file()):
        parser.error("mixed-media requires an existing single-image audio reference")
    receipt = json.loads((accepted / "owner-final-video-approval.json").read_bytes())
    qc = json.loads((accepted / "qc-report.json").read_bytes())
    if not qc["owner_final_video_accepted"] or file_sha(accepted / "final.mp4") != qc["final_sha256"]:
        raise RuntimeError("MVP1_ACCEPTED_ARTIFACT_MISMATCH")
    meta = json.loads((accepted / "voice.wav.vieneu.json").read_bytes())
    if file_sha(accepted / "voice.wav") != meta["audio_sha256"] or meta["profile_sha256"] != PROFILE_SHA:
        raise RuntimeError("MVP1_VOICE_MISMATCH")
    manifest = json.loads((accepted / "render-manifest.json").read_bytes())
    image = Path(manifest["source_asset"])
    if file_sha(image) != manifest["source_asset_sha256"]:
        raise RuntimeError("MVP1_SOURCE_IMAGE_MISMATCH")
    config = Config(data_root=out)
    config.validate_data_root()
    out.mkdir(parents=True)
    assets = out / "assets"
    assets.mkdir()
    shutil.copyfile(image, assets / "accepted-image.jpg")
    shutil.copyfile(accepted / "voice.wav", out / "voice.wav")
    # MVP1 synthesized four exact sentences for three storyboard scenes.
    units = [{**unit, "scene": min(i + 1, 3)} for i, unit in enumerate(meta["units"])]
    write_json(out / "voice.json", {"profile_sha256": PROFILE_SHA, "audio_sha256": meta["audio_sha256"],
                                   "units": units, "duration_seconds": meta["decoded_duration_seconds"]})
    content = json.loads((accepted / "content-proposal.json").read_bytes())
    snapshot = {"document": {"proposal": content,
                              "asset": {"id": "accepted-image.jpg", "sha256": manifest["source_asset_sha256"], "illustration": True}},
                "approval": None}
    if args.mixed_media:
        snapshot["document"] = mixed_media(config, out, content)
    report = render(config, snapshot, out)
    checks = verify_mixed(config, out, args.audio_reference) if args.mixed_media else None
    write_json(out / "smoke-report.json", {"scope": "OFFLINE_RENDER_REGRESSION_ONLY", "qc": report,
        "source": str(accepted), "historical_receipt": receipt, "new_human_approval": False,
        "content_provider_calls": 0, "tts_inferences": 0, "mvp1_modified": False, "mixed_media_checks": checks})
    print(json.dumps({"passed": report["passed"], "output": str(out / "final.mp4"), "provider_calls": 0, "tts_inferences": 0}))


if __name__ == "__main__":
    main()
