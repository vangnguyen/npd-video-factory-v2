"""Read-only derivation into a separate cache, never certified job folders."""
import json
import subprocess
from .contracts import WorkflowError,digest,file_sha,write_json


def thumbnail(config, video):
    source=video['path']
    key=digest({'source_sha256':file_sha(source),'recipe':'frame1s-width200-v1'})
    root=config.data_root/'production-thumbnails'; root.mkdir(exist_ok=True)
    target=root/(key+'.jpg'); receipt=root/(key+'.json')
    if target.exists() and receipt.exists():
        if json.loads(receipt.read_bytes())['sha256']!=file_sha(target): raise WorkflowError('LIBRARY_THUMBNAIL_CHANGED')
        return target
    result=subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-ss','1','-i',str(source),'-frames:v','1','-vf','scale=200:-2',str(target)],capture_output=True,timeout=30)
    if result.returncode: raise WorkflowError('LIBRARY_THUMBNAIL_FAILED')
    write_json(receipt,{'key':key,'sha256':file_sha(target),'source_sha256':file_sha(source),'certified_source_modified':False})
    return target
