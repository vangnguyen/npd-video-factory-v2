"""Checksum-bound local PCM reuse; timeline/review/render evidence remains private."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import threading
import time
import uuid
import wave

from .contracts import WorkflowError,canonical,digest,file_sha

ALGORITHM='native-source-pcm-cache-v1'
MAX_ENTRIES=512
MAX_BYTES=2*1024**3
_mutex=threading.Lock()
_locks={}

def paths():
    # Lazy import avoids importing the pipeline again during renderer imports.
    from .backup import guard,io_path
    return guard,io_path

def cancelled(event):
    if event is not None and event.is_set():raise WorkflowError('PREVIEW_CANCELLED')

@contextmanager
def lease(path,event=None,timeout=330):
    """One entry at a time across both threads and Windows/POSIX processes."""
    guard,io=paths();guard(path)
    key=str(path.absolute())
    with _mutex:
        lock,users=_locks.get(key,(threading.Lock(),0));_locks[key]=(lock,users+1)
    started=time.monotonic();acquired=False;handle=None;os_locked=False
    try:
        while not acquired:
            cancelled(event)
            if time.monotonic()-started>timeout:raise WorkflowError('SOURCE_AUDIO_CACHE_LOCK_TIMEOUT',503)
            acquired=lock.acquire(timeout=.1)
        handle=io(guard(path)).open('a+b')
        if handle.seek(0,2)==0:handle.write(b'0');handle.flush()
        while not os_locked:
            cancelled(event);handle.seek(0)
            try:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                os_locked=True
            except OSError:
                if time.monotonic()-started>timeout:raise WorkflowError('SOURCE_AUDIO_CACHE_LOCK_TIMEOUT',503) from None
                if event is None:time.sleep(.1)
                elif event.wait(.1):cancelled(event)
        yield
    finally:
        if handle is not None:
            if os_locked:
                handle.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle,fcntl.LOCK_UN)
            handle.close()
        if acquired:lock.release()
        with _mutex:
            users=_locks[key][1]-1
            if users:_locks[key]=(lock,users)
            else:_locks.pop(key)

def scope(root,project):
    """Client metadata never grants family sharing; validate frozen DB history."""
    guard,io=paths();root=guard(root,exists=True).resolve();workspace='wsp_native_local'
    marker=guard(root/'.vf-auth-workspace.json')
    if io(marker).exists():
        try:
            if io(marker).stat().st_size>512:raise ValueError()
            value=json.loads(io(marker).read_bytes())
            if value.get('schema')!='vf-native-workspace-binding-v1' or not re.fullmatch(r'wsp_[A-Za-z0-9_-]{1,100}',value.get('workspace_id','')):raise ValueError()
            workspace=value['workspace_id']
        except (ValueError,TypeError,OSError):raise WorkflowError('SOURCE_AUDIO_CACHE_WORKSPACE_INVALID') from None
    identifier=project['id']
    if not re.fullmatch(r'[a-f0-9]{32}',identifier):raise WorkflowError('SOURCE_AUDIO_CACHE_PROJECT_INVALID')
    lineage=project['document']['canonical_timeline']['snapshot']['metadata'].get('source_variant')
    if lineage is not None:
        from .source_variants import SourceVariants
        from types import SimpleNamespace
        database=io(guard(root/'workflow.sqlite3',exists=True))
        con=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=15);con.row_factory=sqlite3.Row
        try:
            con.execute('PRAGMA trusted_schema=OFF');con.execute('BEGIN')
            rows=con.execute('SELECT * FROM native_source_variant_batches WHERE workspace_id=? AND master_project_id=? AND request_fingerprint=? LIMIT 51',
                (workspace,lineage.get('master_project_id'),lineage.get('request_fingerprint'))).fetchall()
            found=False
            for row in rows:
                batch=SourceVariants.read(SimpleNamespace(workspace=workspace),row,con)
                member=next((item for item in batch['result']['variants'] if item['project_id']==identifier),None)
                if member is not None:
                    if lineage.get('schema_version')!='native-source-variants-v1' or lineage.get('master_document_sha256')!=batch['snapshot']['master_document_sha256'] or lineage.get('profile')!=member['profile']:
                        raise WorkflowError('SOURCE_AUDIO_CACHE_FAMILY_INVALID')
                    identifier=row['master_project_id'];found=True;break
            if not found:raise WorkflowError('SOURCE_AUDIO_CACHE_FAMILY_INVALID')
        except (sqlite3.Error,KeyError,TypeError,ValueError):raise WorkflowError('SOURCE_AUDIO_CACHE_FAMILY_INVALID') from None
        finally:con.close()
    return {'data_root_sha256':digest(os.path.normcase(str(root))), 'workspace_id':workspace,'master_or_project_id':identifier}

def fingerprint(binding,audio,assets,duration,ffmpeg):
    by_path={str(path):asset.checksum_sha256 for asset,path in assets.values()}
    sources=[]
    if len(audio.inputs)%2:raise WorkflowError('SOURCE_AUDIO_CACHE_GRAPH_INVALID')
    for index in range(0,len(audio.inputs),2):
        if audio.inputs[index]!='-i' or audio.inputs[index+1] not in by_path:raise WorkflowError('SOURCE_AUDIO_CACHE_GRAPH_INVALID')
        sources.append(by_path[audio.inputs[index+1]])
    guard,io=paths()
    return {'algorithm':ALGORITHM,'scope':binding,'source_sha256_in_input_order':sources,
        'filters':audio.filters,'duration_seconds':duration,'silent_source':not bool(audio.clips),
        'output':{'codec':'pcm_s16le','sample_rate':48000,'channels':2},
        'ffmpeg_executable_sha256':file_sha(io(guard(ffmpeg,exists=True)))}

def measure(path,duration):
    guard,io=paths();path=io(guard(path,exists=True))
    try:
        if not path.is_file() or not 44<=path.stat().st_size<=MAX_BYTES:raise ValueError()
        with wave.open(str(path),'rb') as audio:
            frames=audio.getnframes()
            if (audio.getnchannels(),audio.getsampwidth(),audio.getframerate(),audio.getcomptype())!=(2,2,48000,'NONE') or abs(frames-round(duration*48000))>2:raise ValueError()
            remaining=frames
            while remaining:
                chunk=audio.readframes(min(remaining,48000))
                if not chunk or len(chunk)%4:raise ValueError()
                remaining-=len(chunk)//4
        return {'sha256':file_sha(path),'bytes':path.stat().st_size,'sample_rate':48000,'channels':2,'sample_width':2,'frames':frames}
    except (OSError,EOFError,wave.Error,ValueError):raise WorkflowError('SOURCE_AUDIO_CACHE_PCM_INVALID') from None

def read(entry,request):
    guard,io=paths();receipt=io(guard(entry/'receipt.json',exists=True))
    try:
        if receipt.stat().st_size>256*1024:raise ValueError()
        value=json.loads(receipt.read_bytes())
        if set(value)!={'schema_version','request','request_sha256','pcm','receipt_sha256'} or value['schema_version']!=ALGORITHM or value['request']!=request or value['request_sha256']!=digest(request):raise ValueError()
        if value['receipt_sha256']!=digest({key:item for key,item in value.items() if key!='receipt_sha256'}):raise ValueError()
        if measure(entry/'mix.wav',request['duration_seconds'])!=value['pcm']:raise ValueError()
        return value
    except (KeyError,TypeError,ValueError,OSError):raise WorkflowError('SOURCE_AUDIO_CACHE_EVIDENCE_CHANGED') from None

def materialize(root,request,target,build,*,cancel_event=None):
    """Build at most once, atomically commit, copy verified bytes to this job."""
    guard,io=paths();cancelled(cancel_event)
    cache=guard(Path(root)/'cache'/ALGORITHM);io(cache).mkdir(parents=True,exist_ok=True)
    key=digest(request);entry=guard(cache/key)
    with lease(cache/'.capacity.lock',cancel_event):
        if not io(entry).exists():
            entries=[path for path in io(cache).iterdir() if path.is_dir()]
            if len(entries)>=MAX_ENTRIES:
                build(target);cancelled(cancel_event)
                return {'schema_version':ALGORITHM,'status':'bypass_capacity','key':key,'pcm':measure(target,request['duration_seconds']),'external_provider_calls':0}
            io(entry).mkdir()
    with lease(entry/'.lock',cancel_event):
        ready=guard(entry/'ready');hit=io(ready).exists()
        if hit:value=read(ready,request)
        else:
            attempt=guard(entry/('attempt-'+uuid.uuid4().hex));io(attempt).mkdir()
            mixed=attempt/'mix.wav';build(io(mixed));cancelled(cancel_event)
            pcm=measure(mixed,request['duration_seconds'])
            value={'schema_version':ALGORITHM,'request':request,'request_sha256':key,'pcm':pcm}
            value['receipt_sha256']=digest(value)
            with io(guard(attempt/'receipt.json')).open('xb') as handle:
                handle.write(canonical(value));handle.flush();os.fsync(handle.fileno())
            with io(guard(mixed,exists=True)).open('r+b') as handle:os.fsync(handle.fileno())
            with lease(cache/'.capacity.lock',cancel_event):
                # Bounded retention, no automatic eviction of recorded evidence.
                total=sum(io(guard(path,exists=True)).stat().st_size for path in io(cache).glob('*/ready/mix.wav'))
                if total+pcm['bytes']>MAX_BYTES:
                    shutil.copyfile(io(mixed),target);cancelled(cancel_event)
                    if measure(target,request['duration_seconds'])!=pcm:raise WorkflowError('SOURCE_AUDIO_CACHE_COPY_CHANGED')
                    return {'schema_version':ALGORITHM,'status':'bypass_capacity','key':key,'pcm':pcm,'external_provider_calls':0}
                os.rename(io(attempt),io(ready))
            value=read(ready,request)
        cancelled(cancel_event);shutil.copyfile(io(guard(ready/'mix.wav',exists=True)),target);cancelled(cancel_event)
        if measure(target,request['duration_seconds'])!=value['pcm']:raise WorkflowError('SOURCE_AUDIO_CACHE_COPY_CHANGED')
        return {'schema_version':ALGORITHM,'status':'hit' if hit else 'built','key':key,'scope':request['scope'],
            'receipt_sha256':value['receipt_sha256'],'pcm':value['pcm'],'external_provider_calls':0}
