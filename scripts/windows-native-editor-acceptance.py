"""Real FFmpeg editor evidence. Reuses exact accepted speech; test-only approvals.

No SDK/provider/TTS dispatch; generated images/video/music are explicit local fixtures.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import wave
import numpy as np
from PIL import Image, ImageDraw

REPO=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(REPO))
from services.windows_native.contracts import file_sha, digest
from services.windows_native.editor import validate_plan
from services.windows_native.hardening import Artifacts, durable_json
from services.windows_native.media import ingest_media
from services.windows_native.music import ingest_music
from services.windows_native.pipeline import Config, Pipeline, music_filters
from services.windows_native.server import Runner
from services.windows_native.store import Store


def wav(path,samples):
    with wave.open(str(path),"wb") as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(48000)
        output.writeframes((np.asarray(samples)*32767).astype("<i2").tobytes())


def sample(config,video,seconds):
    raw=subprocess.check_output([str(config.ffmpeg_bin/"ffmpeg.exe"),"-v","error","-ss",str(seconds),"-i",str(video),
        "-vf","crop=800:600:140:460,scale=160:120","-frames:v","1","-f","rawvideo","-pix_fmt","rgb24","-"],timeout=30)
    return np.frombuffer(raw,dtype=np.uint8).astype(float)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--data-root",type=Path,required=True); parser.add_argument("--report",type=Path,required=True)
    args=parser.parse_args(); config=Config(data_root=args.data_root.resolve()); config.validate_data_root()
    if config.data_root.exists() or args.report.exists(): raise ValueError("FRESH_EDITOR_ACCEPTANCE_ROOT_REQUIRED")
    store=Store(config.data_root); durable_json(config.data_root/"runtime-config.json",config.dump())
    source=Path(r"C:\NPD-Video-Factory\outputs\MVP1")
    approved=json.loads((source/"owner-final-video-approval.json").read_bytes())
    assert file_sha(source/"voice.wav")==approved["voice_sha256"]
    proposal=json.loads((source/"content-proposal.json").read_bytes())
    timing=Path(r"C:\NPD-Video-Factory\phase2-validation\single-media-regression\voice.json")
    assert json.loads(timing.read_bytes())["audio_sha256"]==approved["voice_sha256"]
    fixtures=config.data_root/"fixtures"; fixtures.mkdir()
    project=store.create("Auto Editor · thử nghiệm kỹ thuật", "Exact accepted narration/WAV; generated local reference media", "script")
    project=store.save(project["id"],project["revision"],proposal=proposal)
    assets=[]
    for index in range(5):
        if index<3:
            path=fixtures/f"reference-image-{index}.png"; image=Image.new("RGB",(1280,800),(60+index*30,90,120))
            draw=ImageDraw.Draw(image)
            for x in range(0,1280,80): draw.rectangle((x,0,x+35,799),fill=(180-index*20,120+x//20,60))
            for y in range(0,800,80): draw.line((0,y,1279,y),fill="white",width=4)
            draw.text((160,280),f"LOCAL EDITOR REFERENCE {index+1}",fill="white",font_size=48)
            image.save(path); mime="image/png"
        else:
            path=fixtures/f"reference-video-{index}.mp4"; mime="video/mp4"
            subprocess.run([str(config.ffmpeg_bin/"ffmpeg.exe"),"-v","error","-nostdin","-n","-f","lavfi","-i",
                f"testsrc2=size=640x360:rate=30:duration={2 if index==3 else 3}","-c:v","libx264","-pix_fmt","yuv420p",str(path)],check=True,timeout=30)
        asset=ingest_media(config,path,mime,path.name,rights_confirmed=True,illustration=True); assets.append(asset)
        project=store.append_media(project["id"],project["revision"],asset)
    seconds=np.arange(48000*6)/48000
    music_path=fixtures/"locally-generated-reference-music.wav"; wav(music_path,.3*np.sin(2*np.pi*440*seconds)+.12*np.sin(2*np.pi*660*seconds))
    project=store.set_music(project["id"],project["revision"],ingest_music(config,music_path,"audio/wav",music_path.name,rights_confirmed=True))
    project=store.auto_plan(project["id"],project["revision"])
    auto=project["document"]["edit_plan"]; assert all(len(s["asset_candidates"])==5 for s in auto["scenes"])
    outputs=[]
    for index in range(2):
        bindings=[{"scene":1,"asset_id":assets[0]["id"]},{"scene":2,"asset_id":assets[3]["id"]},{"scene":3,"asset_id":assets[2]["id"]}]
        options=[{"scene":1,"motion":"zoom_in","crop_strategy":"cover","transition":"fade"},
                 {"scene":2,"source_start":.75,"crop_strategy":"contain","transition":"fade"},
                 {"scene":3,"motion":"pan_left" if index==0 else "pan_right","crop_strategy":"cover","transition":"cut"}]
        project=store.save(project["id"],project["revision"],scene_media=bindings,scene_options=options,music_enabled=index==0)
        validate_plan(project["document"]); assert project["approval"] is None
        project=store.approve(project["id"],project["revision"],"INTEGRATION FIXTURE — NOT OWNER/HUMAN ACCEPTANCE",True)
        identity=digest({k:project[k] for k in ("document","approval","revision")})
        job=store.enqueue(project["id"],project["revision"],"render","editor-acceptance-"+uuid.uuid4().hex)
        out=config.data_root/"jobs"/job["id"]; out.mkdir(parents=True)
        artifacts=Artifacts(out,job); speech=artifacts.publish(source/"voice.wav","voice.wav"); meta=artifacts.publish(timing,"voice.json")
        artifacts.commit("tts",[speech,meta],{"fixture_seed":"reused_existing_real_accepted_WAV","new_inference":False})
        Runner(store,Pipeline(config)).run_one(); result=store.get_job(job["id"])
        assert result["status"]=="succeeded",result
        assert result["result"]["qc"]["passed"]; assert Artifacts(out,job).load("render")
        current=Store(config.data_root).get(project["id"]); assert digest({k:current[k] for k in ("document","approval","revision")})==identity
        manifest=json.loads((out/"render-manifest.json").read_bytes()); canonical=json.loads((out/"timeline.json").read_bytes())
        assert len(canonical["tracks"])==(4 if index==0 else 3)
        deltas=[]
        for frame in manifest["scenes"]:
            left=sample(config,out/"final.mp4",frame["start"]+.7); right=sample(config,out/"final.mp4",frame["end"]-.7)
            difference=float(np.mean(np.abs(left-right))); assert difference>1.5,(frame,difference)
            deltas.append({"scene":frame["scene"],"mean_pixel_delta":difference,"motion":frame["motion"]})
        outputs.append({"job_id":job["id"],"revision":project["revision"],"final_mp4":str(out/"final.mp4"),"qc":result["result"]["qc"],"timeline_sha256":file_sha(out/"timeline.json"),
            "music_enabled":index==0,"measured_motion":deltas,"human_final_accepted":False,"approval_kind":"explicit integration fixture"})
        print(json.dumps({"completed":index+1,"job_id":job["id"],"qc":"PASS"}),flush=True)
    # Measure the exact production ducking filter with independent controllable signals.
    seconds=np.arange(48000*10)/48000
    controlled=np.where((seconds>=2)&(seconds<4),.12*np.sin(2*np.pi*3500*seconds),0)
    wav(fixtures/"controlled-voice.wav",controlled); wav(fixtures/"controlled-music.wav",.4*np.sin(2*np.pi*440*seconds))
    filters=music_filters("[1:a]adelay=1100,apad,atrim=duration=10[a]",10)
    raw=subprocess.check_output([str(config.ffmpeg_bin/"ffmpeg.exe"),"-v","error","-f","lavfi","-i","anullsrc=r=48000:cl=mono",
        "-i",str(fixtures/"controlled-voice.wav"),"-i",str(fixtures/"controlled-music.wav"),"-filter_complex",filters,"-map","[a]","-t","10","-f","f32le","-ac","1","-"],timeout=30)
    samples=np.frombuffer(raw,dtype="<f4")
    def amplitude(at):
        data=samples[int(at*48000):int((at+.5)*48000)]; t=np.arange(len(data))/48000
        return float(abs(np.mean(data*np.exp(-2j*np.pi*440*t)))*2)
    quiet,active=amplitude(1.5),amplitude(4.)
    assert active<quiet*.5,(quiet,active)
    with store.transaction() as con: integrity=con.execute("PRAGMA integrity_check").fetchone()[0]
    assert integrity=="ok"
    report={"status":"PASS","scope":"technical native auto-editor; test-only approvals; not final editorial acceptance","data_root":str(config.data_root),"project_id":project["id"],
        "assets":len(assets),"auto_plan":auto,"outputs":outputs,"ducking_measurement":{"music_440hz_quiet_amplitude":quiet,"music_440hz_voiced_amplitude":active,"ratio":active/quiet,"exact_production_filter":True},
        "source_voice_sha256":approved["voice_sha256"],"new_provider_calls":0,"new_tts_inferences":0,"human_final_accepted":False,"sqlite_integrity":integrity}
    args.report.parent.mkdir(parents=True,exist_ok=True); durable_json(args.report,report)
    print(json.dumps({"status":"PASS","report":str(args.report)}),flush=True)


if __name__=="__main__": main()
