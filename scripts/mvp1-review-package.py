"""Package shareable first-party dev proofs, never sessions/DB/object store/RC evidence.

Requires a clean exact commit and actual decode/QC. No network or provider client.
The ZIP is local; this script does not upload, publish or grant acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

parser=argparse.ArgumentParser()
parser.add_argument("--root",type=Path,required=True)
parser.add_argument("--output",type=Path,required=True)
parser.add_argument("--ffmpeg",required=True)
parser.add_argument("--ffprobe",required=True)
parser.add_argument("--test-report",type=Path,required=True)
args=parser.parse_args()
repo=Path(__file__).resolve().parents[1]
commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip()
if subprocess.check_output(["git","status","--porcelain"],cwd=repo,text=True).strip():
    raise SystemExit("clean committed source required")
root=args.root.resolve();output=args.output.resolve()
if output.exists() or output.with_suffix(".zip").exists():
    raise SystemExit("fresh output required; existing evidence is never overwritten")
output.mkdir(mode=0o700)

def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source,"sha256").hexdigest()

def run(command):
    result=subprocess.run(command,capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError(f"verification exit {result.returncode}: {command[0]} {result.stderr[-500:]}")
    return result

def copy(source,destination):
    if source.is_symlink() or not source.is_file():raise ValueError("regular files only")
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,destination)
    if digest(source)!=digest(destination):raise ValueError("copy identity mismatch")

cases=[];media=[]
for folder in sorted(root.glob("ui-*")):
    report_path=folder/"proof-report.json"
    if not report_path.is_file():continue
    report=json.loads(report_path.read_text())
    if report.get("source_commit")!=commit:raise ValueError("proof commit mismatch")
    if report["verdict"]=="DEV_PROOF_BLOCKED":continue  # preserved separately, not mislabeled as successful review
    destination=output/"cases"/folder.name
    for file in sorted(folder.iterdir()):
        if file.suffix in {".json",".png",".mp4"}:copy(file,destination/file.name)
    for movie in sorted(folder.glob("*.mp4")):
        render=json.loads((folder/(movie.stem+"-render.json")).read_text())
        if render["qc_status"]!="passed" or render["status"] not in {"ready","awaiting_review"}:
            raise ValueError("MP4 lacks successful actual production QC")
        decode=run([args.ffmpeg,"-hide_banner","-v","error","-i",str(movie),"-f","null","-"])
        probe=json.loads(run([args.ffprobe,"-v","error","-show_streams","-show_format","-of","json",str(movie)]).stdout)
        video=next(s for s in probe["streams"] if s["codec_type"]=="video")
        audio=next(s for s in probe["streams"] if s["codec_type"]=="audio")
        if video["codec_name"]!="h264" or audio["codec_name"]!="aac":raise ValueError("delivery codec mismatch")
        is_final=movie.stem.startswith("final")
        if is_final and (video["width"],video["height"])!=(1080,1920):raise ValueError("final profile mismatch")
        narration=render["manifest"]["narration"]
        for cue in narration["timing"]:
            if not (0<=cue["start_seconds"]<cue["end_seconds"]<=cue["slot_end_seconds"]+0.001):raise ValueError("bad measured cue interval")
        # Extract representative frames for visual inspection; not a human full-watch assertion.
        frame_dir=destination/"representative-frames"
        frame_dir.mkdir(exist_ok=True)
        duration=float(probe["format"]["duration"])
        for fraction in (0.2,0.5,0.8):
            frame=frame_dir/f"{movie.stem}-{int(fraction*100)}.png"
            run([args.ffmpeg,"-v","error","-ss",str(duration*fraction),"-i",str(movie),"-frames:v","1","-vf","scale=270:480",str(frame)])
        media.append({"path":str((destination/movie.name).relative_to(output)).replace("\\","/"),
            "source_commit":commit,"render_id":render["render_id"],"timeline_version":render["timeline_version"],
            "audio_version":render["audio_version"],"subtitle_version":render["subtitle_version"],
            "width":video["width"],"height":video["height"],"video_codec":video["codec_name"],
            "audio_codec":audio["codec_name"],"audio_sample_rate":audio["sample_rate"],"duration_seconds":duration,
            "full_decode_exit_code":decode.returncode,"qc":render["qc_report"],"narration_provenance":narration,
            "human_full_watch_listen":"NOT_PERFORMED","professional_voice_acceptance":False})
    cases.append({"scenario":report["scenario"],"folder":str(destination.relative_to(output)).replace("\\","/"),"verdict":report["verdict"]})

required={"image-script","mixed","script","idea","prompt","image-only","mixed-audio-blocked","script-long"}
if not required.issubset({case["scenario"] for case in cases}):raise ValueError("review case missing")
for fixture in ("fixtures","fixtures-spoken"):
    manifest=json.loads((root/fixture/"source-rights-manifest.json").read_text())
    if manifest["classification"]!="SELF_AUTHORED_SYNTHETIC_DEV_MEDIA" or manifest["benchmark_asset_reused"]:
        raise ValueError("unapproved source rights")
    for file in (root/fixture).iterdir():
        if file.suffix in {".json",".png",".mp4",".wav"}:copy(file,output/"inputs"/fixture/file.name)
copy(args.test_report,output/"TEST_REPORT.md")
for junit in args.test_report.parent.glob("*final*.xml"):copy(junit,output/"tests"/junit.name)
metadata={"task":"VF-MVP1-MULTI-INPUT-IMPLEMENT-02","source_commit":commit,"classification":"DEV_FIXTURE_REVIEW_NOT_ACCEPTANCE",
    "cases":cases,"media":media,"external_ai_provider_calls_task":0,"provider_credential_reads_task":0,
    "provider_spend_vnd_task":0,"host_lifetime_counters":"NOT_VERIFIED",
    "generation_provider":"offline fixture, not creative AI",
    "rights":"self-authored synthetic media and source narration; no benchmark assets; local dev review only",
    "human_quality_accepted":False,"production_path_accepted":False}
(output/"METADATA_QC_AUDIO_TIMING.json").write_text(json.dumps(metadata,ensure_ascii=False,sort_keys=True,indent=2),encoding="utf8")
(output/"README.md").write_text("""# MVP-1 multi-input review — dev fixture only

Open the MP4 files under `cases/` with a normal video player. Start with
`ui-image-script-*/review.mp4`, then `final-after-edit.mp4` (T08),
`ui-mixed-*/final.mp4` (video has NO audio stream), and `ui-script-*/final.mp4`.
Idea/prompt are explicit OFFLINE FIXTURE proposals without a narration label,
not real creative AI generation or acceptance. The audio-bearing mixed case is
correctly BLOCKED even when mute is selected; no ASR transcript was fabricated.

Source narration, storyboard, timeline, media plan, version-bound production
package and actual QC are beside each MP4. Metadata records exact commit,
decoded codecs/duration, measured PCM cue durations and eSpeak voice/rate.
Scene placements are editorial, NOT measured word timestamps. There is no word
alignment and no professional Vietnamese pronunciation acceptance. Human
full-watch/full-listen and real-input production/consecutive E2E remain required.

Inputs are self-authored dev media, not official architectural renderings.
See `inputs/*/source-rights-manifest.json`. This archive contains no session,
database, .env, credentials or restricted ASR benchmark audio. No public upload
or publishing is performed. SHA-256 inventory is `REVIEW_CHECKSUMS.sha256`.
See TEST_REPORT.md for exact commands, results, skip reasons and reproduction.
""",encoding="utf8")
findings=[]
patterns=[r"vhuman\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{32,}",r"sk-(?:proj-)?[A-Za-z0-9_-]{24,}",r"gh[pousr]_[A-Za-z0-9]{20,}",r"Bearer\s+[A-Za-z0-9._-]{20,}"]
for file in output.rglob("*"):
    if file.suffix in {".json",".md",".xml"}:
        value=file.read_text(encoding="utf8")
        if any(re.search(pattern,value) for pattern in patterns):findings.append(str(file.relative_to(output)))
if findings:raise ValueError(f"secret scan failed in {findings}")
inventory=[{"path":str(file.relative_to(output)).replace("\\","/"),"sha256":digest(file),"bytes":file.stat().st_size}
    for file in sorted(output.rglob("*")) if file.is_file()]
(output/"REVIEW_MANIFEST.json").write_text(json.dumps({"source_commit":commit,"secret_scan":"PASS / 0 findings",
    "files":inventory},ensure_ascii=False,sort_keys=True,indent=2),encoding="utf8")
checksum_files=[file for file in sorted(output.rglob("*")) if file.is_file()]
(output/"REVIEW_CHECKSUMS.sha256").write_text("".join(f"{digest(file)}  {file.relative_to(output).as_posix()}\n" for file in checksum_files),encoding="utf8")
archive=output.with_suffix(".zip")
with zipfile.ZipFile(archive,"x",compression=zipfile.ZIP_DEFLATED) as package:
    for file in sorted(output.rglob("*")):
        if file.is_file():package.write(file,file.relative_to(output).as_posix())
with zipfile.ZipFile(archive) as package:
    if package.testzip():raise ValueError("archive CRC failure")
print(json.dumps({"archive":str(archive),"sha256":digest(archive),"bytes":archive.stat().st_size,
    "media_count":len(media),"case_count":len(cases),"secret_scan":"PASS / 0 findings"}))
