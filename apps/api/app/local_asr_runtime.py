"""Explicit isolated local runtime custody; full media/model checks at dispatch."""
import hashlib,json,stat
from pathlib import Path
from .local_asr_profile import model_manifest,digest

def file_sha(path):
    with path.open('rb') as h:return hashlib.file_digest(h,'sha256').hexdigest()

def plain(path):
    path=Path(path)
    if not path.is_absolute():raise ValueError('LOCAL_ASR_PATH_INVALID')
    for item in (path,*path.parents):
        info=item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
            raise ValueError('LOCAL_ASR_LINK_REJECTED')
    return path.resolve(strict=True)

def runtime(path,full=True):
    if path is None:raise ValueError('LOCAL_ASR_NOT_CONFIGURED')
    path=plain(path)
    if path.stat().st_size>16384:raise ValueError('LOCAL_ASR_RUNTIME_INVALID')
    value=json.loads(path.read_bytes())
    if set(value)!={'version','enabled','python','python_sha256','model_root','model_manifest_sha256','cpu_threads','timeout_seconds'}:
        raise ValueError('LOCAL_ASR_RUNTIME_INVALID')
    if value['version']!='local-asr-runtime.v1' or value['enabled'] is not True:
        raise ValueError('LOCAL_ASR_NOT_CONFIGURED')
    if type(value['cpu_threads']) is not int or not 1<=value['cpu_threads']<=4:
        raise ValueError('LOCAL_ASR_RUNTIME_INVALID')
    if type(value['timeout_seconds']) is not int or not 30<=value['timeout_seconds']<=600:
        raise ValueError('LOCAL_ASR_RUNTIME_INVALID')
    python=plain(value['python']);root=plain(value['model_root'])
    model=model_manifest()
    if not python.is_file() or file_sha(python)!=value['python_sha256'] or not root.is_dir():
        raise ValueError('LOCAL_ASR_RUNTIME_CHANGED')
    if value['model_manifest_sha256']!=digest(model):raise ValueError('LOCAL_ASR_MODEL_CHANGED')
    for name,proof in model['files'].items():
        item=plain(root/name)
        if not item.is_file() or item.stat().st_size!=proof['bytes'] or (full and file_sha(item)!=proof['sha256']):
            raise ValueError('LOCAL_ASR_MODEL_CHANGED')
    return value

def status(path):
    try:
        runtime(path,full=False)
        return {'configured':True,'provider':'faster-whisper','model':'base','execution':'local_cpu',
            'paid':False,'external_call':False,'model_verified_at_dispatch':True}
    except (OSError,ValueError,TypeError,KeyError):
        return {'configured':False,'provider':'faster-whisper','execution':'local_cpu','paid':False,'external_call':False}
