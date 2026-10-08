"""Bounded input-only FFmpeg EBU R128 measurements, never a target/voice claim."""
import json,math,re,subprocess
from .backup import guard
from .contracts import WorkflowError,file_sha
VERSION='native-measured-audio-loudness-v1'
def parse(raw):
    try:
        objects=[json.loads(v) for v in re.findall(r'\{[^{}]*\}',raw)]
        data=next(v for v in reversed(objects) if all(k in v for k in ('input_i','input_tp','input_lra','input_thresh')))
        measured={}
        for src,dst,lower,upper in [('input_i','integrated_lufs',-99,20),('input_tp','true_peak_dbfs',-120,20),('input_lra','loudness_range_lu',0,99),('input_thresh','relative_threshold_lufs',-99,20)]:
            value=data[src]
            if not isinstance(value,str) or len(value)>32:raise ValueError()
            numeric=float(value)
            if value.lower()=='-inf' and src!='input_lra':measured[dst]=None
            elif not math.isfinite(numeric) or not lower<=numeric<=upper:raise ValueError()
            else:measured[dst]=numeric
        if measured['integrated_lufs'] is None and measured['true_peak_dbfs'] is not None:state='below_integrated_measurement_floor'
        elif measured['integrated_lufs'] is None:state='silent_input'
        else:state='measured'
        return {'measurement_state':state,**measured}
    except (ValueError,TypeError,StopIteration,OverflowError):raise WorkflowError('NATIVE_AUDIO_LOUDNESS_RESULT_INVALID') from None
def measure(config,path):
    path=guard(path,exists=True);before=file_sha(path)
    try:
        result=subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-hide_banner','-nostdin','-v','info',
            '-protocol_whitelist','file,pipe','-i',str(path),'-map','0:a:0','-vn',
            '-af','loudnorm=I=-16:LRA=11:TP=-1:print_format=json','-f','null','-'],capture_output=True,timeout=60)
    except (subprocess.SubprocessError,OSError):raise WorkflowError('NATIVE_AUDIO_LOUDNESS_SCAN_FAILED') from None
    if result.returncode or len(result.stderr)>1024*1024:raise WorkflowError('NATIVE_AUDIO_LOUDNESS_SCAN_FAILED')
    values=parse(result.stderr.decode('utf-8',errors='replace'))
    if file_sha(path)!=before:raise WorkflowError('NATIVE_AUDIO_LOUDNESS_INPUT_CHANGED')
    return {'schema_version':VERSION,'provider':'local-ffmpeg-loudnorm-input-measurement','input_sha256':before,
        **values,'audio_modified':False,'normalization_target_achieved_claimed':False,'speech_detection_performed':False,
        'voice_music_balance_accepted':False,'external_provider_calls':0}
