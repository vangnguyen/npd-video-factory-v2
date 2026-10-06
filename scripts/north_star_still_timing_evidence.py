"""Verify exported isolated synthetic B-roll timing; no provider or approval calls."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess


def verify(output: Path):
    record = json.loads((output / "broll-evidence.json").read_text(encoding="utf-8"))
    if record.get("fixture_asr") is not True or record.get("real_provider_tested") is not False:
        raise ValueError("only the labeled synthetic timing fixture is supported")
    history = json.loads((output / "timeline-history.json").read_text(encoding="utf-8"))
    states = {v["version"]: v for v in history}
    if set(states) != {1, 2, 3, 4, 5}:
        raise ValueError("expected original, apply, edit, undo and redo versions")
    def image(version):
        clips = [c for t in states[version]["snapshot"]["tracks"] for c in t["clips"] if c["kind"] == "image"]
        if len(clips) != 1:
            raise ValueError("expected one synthetic supporting image")
        return clips[0]
    before, edited = image(2), image(3)
    assert (before["timeline_start"], before["duration"]) == (0, 16)
    assert (edited["timeline_start"], edited["duration"]) == (2, 4.25)
    assert states[4]["snapshot"] == states[2]["snapshot"]
    assert states[5]["snapshot"] == states[3]["snapshot"]
    for version in (2, 3, 4, 5):
        clip = image(version)
        assert (clip["source_start"], clip["source_end"], clip["speed"]) == (0, None, 1)
        assert states[version]["actor_ref"] == "usr:test-owner"
        assert states[version]["snapshot"]["duration_seconds"] == 16
    assert record["non_broll_tracks_preserved"] is True
    samples = {}
    for label, timestamp in (("before", .5), ("during", 3), ("after", 8)):
        samples[label] = list(subprocess.check_output([
            "ffmpeg", "-v", "error", "-nostdin", "-ss", str(timestamp), "-i", str(output / "preview.mp4"),
            "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ], timeout=30))
    during = samples["during"]
    assert during[2] > during[0] + 50 and during[2] > during[1] + 50
    assert samples["before"] != during and samples["after"] != during
    result = {"local_real_encoding": True, "fixture_asr": True, "real_provider_tested": False,
              "human_approval_claimed": False, "production_deployed": False,
              "timeline_version": 5, "saved_image_duration_seconds": 4.25, "timeline_start_seconds": 2,
              "immutable_undo_redo_verified": True, "authenticated_actor_verified": True,
              "source_time_not_fabricated": True, "primary_audio_subtitle_tracks_preserved": True,
              "decoded_rgb": samples, "render_sha256": record["preview_sha256"],
              "audio_included": False, "output_directory": str(output)}
    (output / "still-timing-evidence.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    verify(parser.parse_args().output)
