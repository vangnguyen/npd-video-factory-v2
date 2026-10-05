"""Offline render regression with the accepted MVP1 audio; no new approval or TTS."""
import argparse
import json
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from services.windows_native.contracts import PROFILE_SHA, file_sha, write_json
from services.windows_native.pipeline import Config, render


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True, help="fresh directory outside the accepted MVP1 evidence")
    args = parser.parse_args()
    out = args.output.resolve()
    accepted = Path(r"C:\NPD-Video-Factory\outputs\MVP1")
    if out == accepted or accepted in out.parents or out.exists():
        parser.error("fresh output outside MVP1 required")
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
    out.mkdir(parents=True)
    config = Config(data_root=out)
    assets = out / "assets"
    assets.mkdir()
    shutil.copyfile(image, assets / "accepted-image.jpg")
    shutil.copyfile(accepted / "voice.wav", out / "voice.wav")
    # MVP1 synthesized four exact sentences for three storyboard scenes.
    units = [{**unit, "scene": min(i + 1, 3)} for i, unit in enumerate(meta["units"])]
    write_json(out / "voice.json", {"profile_sha256": PROFILE_SHA, "audio_sha256": meta["audio_sha256"],
                                   "units": units, "duration_seconds": meta["decoded_duration_seconds"]})
    snapshot = {"document": {"proposal": json.loads((accepted / "content-proposal.json").read_bytes()),
                              "asset": {"id": "accepted-image.jpg", "sha256": manifest["source_asset_sha256"], "illustration": True}},
                "approval": None}
    report = render(config, snapshot, out)
    write_json(out / "smoke-report.json", {"scope": "OFFLINE_RENDER_REGRESSION_ONLY", "qc": report,
        "source": str(accepted), "historical_receipt": receipt, "new_human_approval": False,
        "content_provider_calls": 0, "tts_inferences": 0, "mvp1_modified": False})
    print(json.dumps({"passed": report["passed"], "output": str(out / "final.mp4"), "provider_calls": 0, "tts_inferences": 0}))


if __name__ == "__main__":
    main()
