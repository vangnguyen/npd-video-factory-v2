"""Self-authored synthetic media. No ASR benchmark assets, provider or official render."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zlib

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--ffmpeg", required=True)
parser.add_argument("--espeak", help="optional local offline voice for speech-blocking dev fixture")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
def png(architecture):
    w,h=270,480
    rows=[]
    for y in range(h):
        pixels=bytearray()
        for x in range(w):
            color=(38+y//10, 85+y//12, 120+y//9)
            if architecture and 55<x<215 and 130<y<400:
                color=(205,215,220) if x%30<5 or y%35<5 else (55,100,130)
            pixels.extend(color)
        rows.append(b"\0"+pixels)
    def chunk(k,v): return struct.pack(">I",len(v))+k+v+struct.pack(">I",zlib.crc32(k+v)&0xffffffff)
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",w,h,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(b"".join(rows)))+chunk(b"IEND",b"")
for name, architecture in [("owned-photo.png",False),("synthetic-architecture.png",True)]:
    (args.output/name).write_bytes(png(architecture))
subprocess.run([args.ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i",
    "testsrc2=size=270x480:rate=30:duration=6","-an","-c:v","libx264","-pix_fmt","yuv420p",
    str(args.output/"owned-silent-video.mp4")],check=True)
if args.espeak:
    subprocess.run([args.espeak,"-v","vi","-s","175","-w",str(args.output/"dev-speech.wav"),
        "Đây là video có lời nói, chỉ dùng để kiểm thử nội bộ."],check=True)
    subprocess.run([args.ffmpeg,"-hide_banner","-loglevel","error","-i",str(args.output/"owned-silent-video.mp4"),
        "-i",str(args.output/"dev-speech.wav"),"-map","0:v","-map","1:a","-c:v","copy","-c:a","aac","-shortest",
        str(args.output/"owned-spoken-video.mp4")],check=True)
manifest={"classification":"SELF_AUTHORED_SYNTHETIC_DEV_MEDIA", "rights":"owned-for-isolated-dev",
    "official_architectural_render":False,"benchmark_asset_reused":False,
    "assets":[{"filename":p.name,"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"bytes":p.stat().st_size}
        for p in sorted(args.output.iterdir())]}
(args.output/"source-rights-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2))
