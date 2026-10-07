"""Bounded local audio intake; original music bytes and rights receipt are retained."""
import json
import shutil
import subprocess
import uuid
from .contracts import WorkflowError, file_sha
from .media import display_filename, media_path

MUSIC_TYPES = {"audio/wav", "audio/x-wav", "audio/mpeg"}
MUSIC_MAX_BYTES = 25 * 1024 * 1024


def ingest_music(config, source, content_type, filename, *, rights_confirmed):
    if rights_confirmed is not True or content_type not in MUSIC_TYPES or not 0 < source.stat().st_size <= MUSIC_MAX_BYTES:
        raise WorkflowError("MUSIC_RIGHTS_TYPE_SIZE_REQUIRED_MAX_25MB",400)
    try:
        probe=subprocess.run([str(config.ffmpeg_bin/"ffprobe.exe"),"-v","error","-protocol_whitelist","file,pipe",
            "-show_streams","-show_format","-of","json",str(source)],capture_output=True,timeout=30)
        value=json.loads(probe.stdout)
        expected="mp3" if content_type=="audio/mpeg" else "wav"
        duration=float(value["format"]["duration"])
        if probe.returncode or value["format"]["format_name"]!=expected or not 0<duration<=600:
            raise ValueError()
        if not any(s["codec_type"]=="audio" for s in value["streams"]) or any(s["codec_type"]=="video" and not s.get("disposition",{}).get("attached_pic") for s in value["streams"]):
            raise ValueError()
    except (ValueError,KeyError,TypeError,subprocess.TimeoutExpired):
        raise WorkflowError("MUSIC_AUDIO_INVALID_WAV_MP3_MAX_10_MINUTES",400) from None
    identifier=uuid.uuid4().hex
    directory=config.data_root/"assets"; directory.mkdir(parents=True,exist_ok=True)
    original=config.data_root/"originals"; original.mkdir(parents=True,exist_ok=True)
    original_id=identifier+(".mp3" if expected=="mp3" else ".wav")
    destination=media_path(config,identifier+".music.wav")
    try:
        result=subprocess.run([str(config.ffmpeg_bin/"ffmpeg.exe"),"-v","error","-xerror","-nostdin","-n",
            "-protocol_whitelist","file,pipe","-i",str(source),"-map","0:a:0","-vn","-ar","48000","-ac","2",
            "-c:a","pcm_s16le",str(destination)],capture_output=True,timeout=120)
        if result.returncode:
            raise WorkflowError("MUSIC_DECODE_FAILED",400)
        shutil.copyfile(source,original/original_id)
    except Exception as error:
        destination.unlink(missing_ok=True)
        (original/original_id).unlink(missing_ok=True)
        if isinstance(error,subprocess.TimeoutExpired):
            raise WorkflowError("MUSIC_DECODE_TIMEOUT",400) from None
        raise
    return {"id":destination.name,"original_id":original_id,"kind":"music","filename":display_filename(filename),
        "sha256":file_sha(destination),"bytes":destination.stat().st_size,"source_sha256":file_sha(source),
        "source_mime":content_type,"duration_seconds":duration,"rights_confirmed":True,"source":"immutable_user_upload",
        "ducking":"voice_sidechaincompress", "nominal_gain":.12,'source_type':'user_upload','rights_status':'unknown',
        'license':None,'provider':'native-local-upload','source_reference':'upload://'+original_id,'generation_provenance':{}}
