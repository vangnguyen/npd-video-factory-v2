"""Bounded lifecycle for rebuildable, read-only stock response JSON only.

The existing v2 response envelope remains the authority. A namespace lock never
covers a provider request or quota admission. No media, database, paid generated
output, model, transcript or evidence path is traversed or deleted.
"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass,asdict
import hashlib,json,math,os,re,stat,time,uuid
from pathlib import Path

MAX_FILE_BYTES=2*1024*1024+2048
LOCK='.vf-stock-read-cache.lock'
MARKER='.vf-stock-read-cache.namespace'
HEX=re.compile(r'^[a-f0-9]{64}$')

class StockCacheError(RuntimeError):pass

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

@dataclass(frozen=True)
class StockCachePolicy:
    max_entries:int=256
    max_bytes:int=64*1024*1024
    max_age_seconds:int=86400
    max_file_bytes:int=MAX_FILE_BYTES
    max_scan_entries:int=4096
    max_scan_bytes:int=128*1024*1024
    lock_timeout_seconds:float=2.
    def __post_init__(self):
        bounds={'max_entries':(3,10000),'max_bytes':(4096,1024*1024*1024),'max_age_seconds':(1,86400),
            'max_file_bytes':(1024,MAX_FILE_BYTES),'max_scan_entries':(3,100000),'max_scan_bytes':(1024,1024*1024*1024)}
        for key,(minimum,maximum) in bounds.items():
            value=getattr(self,key)
            if type(value) is not int or not minimum<=value<=maximum:raise ValueError('STOCK_CACHE_POLICY_INVALID')
        if self.max_scan_entries<self.max_entries or self.max_scan_bytes<self.max_file_bytes:raise ValueError('STOCK_CACHE_POLICY_INVALID')
        if isinstance(self.lock_timeout_seconds,bool) or not isinstance(self.lock_timeout_seconds,(int,float)) or not math.isfinite(self.lock_timeout_seconds) or not 0<=self.lock_timeout_seconds<=5:
            raise ValueError('STOCK_CACHE_POLICY_INVALID')

def io_path(path):
    value=str(Path(path).absolute())
    return Path('\\\\?\\UNC\\'+value[2:] if value.startswith('\\\\') else '\\\\?\\'+value) if os.name=='nt' and len(value)>=240 and not value.startswith('\\\\?\\') else Path(value)

def linked(path):
    for parent in [Path(path),*Path(path).parents]:
        try:info=os.lstat(io_path(parent))
        except FileNotFoundError:continue
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024):return True
    return False

def ordinary(path):
    value=str(path)
    if value.startswith('\\\\?\\UNC\\'):value='\\\\'+value[8:]
    elif value.startswith('\\\\?\\'):value=value[4:]
    return Path(value).absolute()

def _windows_info(kernel,handle):
    import ctypes
    from ctypes import wintypes
    class Info(ctypes.Structure):
        _fields_=[('attributes',wintypes.DWORD),('created',wintypes.FILETIME),('accessed',wintypes.FILETIME),
            ('written',wintypes.FILETIME),('volume',wintypes.DWORD),('size_high',wintypes.DWORD),('size_low',wintypes.DWORD),
            ('links',wintypes.DWORD),('index_high',wintypes.DWORD),('index_low',wintypes.DWORD)]
    info=Info();kernel.GetFileInformationByHandle.argtypes=[wintypes.HANDLE,ctypes.POINTER(Info)]
    if not kernel.GetFileInformationByHandle(handle,ctypes.byref(info)):raise StockCacheError('STOCK_CACHE_PATH_INVALID')
    return info

class _Access:
    """Held directory custody; POSIX uses relative descriptors, Windows pins.

    Windows directory handles omit FILE_SHARE_DELETE, preventing ancestors from
    being renamed/swapped while an operation holds its namespace lock.
    """
    def __init__(self,directory,*,create):
        self.directory=directory;self.fds=[];self.handles=[];self.fd=None;self.available=False
        chain=list(reversed([directory,*directory.parents]))
        try:
            for path in chain:
                if not io_path(path).exists():
                    if not create:return
                    try:
                        if self.fd is not None and os.name!='nt':os.mkdir(path.name,dir_fd=self.fd)
                        else:io_path(path).mkdir()
                    except FileExistsError:pass # A peer may create this exact guarded directory.
                if linked(path):raise StockCacheError('STOCK_CACHE_PATH_INVALID')
                if os.name=='nt':self.handles.append(self._pin(path))
                else:
                    flags=os.O_RDONLY|os.O_DIRECTORY|getattr(os,'O_NOFOLLOW',0)
                    fd=os.open(path if self.fd is None else path.name,flags,**({} if self.fd is None else {'dir_fd':self.fd}))
                    self.fds.append(fd);self.fd=fd
            self.available=True
        except Exception:self.close();raise
    @staticmethod
    def _pin(path):
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        kernel.CreateFileW.restype=wintypes.HANDLE
        handle=kernel.CreateFileW(str(io_path(path)),0x80,3,None,3,0x02000000|0x00200000,None)
        if handle==ctypes.c_void_p(-1).value:raise StockCacheError('STOCK_CACHE_DIRECTORY_CUSTODY_FAILED')
        try:attrs=_windows_info(kernel,handle).attributes
        except Exception:
            kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle(handle);raise
        if not attrs&16 or attrs&1024:
            kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle(handle)
            raise StockCacheError('STOCK_CACHE_PATH_INVALID')
        return handle
    def close(self):
        for fd in reversed(self.fds):os.close(fd)
        self.fds=[]
        if self.handles:
            import ctypes
            from ctypes import wintypes
            kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.CloseHandle.argtypes=[wintypes.HANDLE]
            for handle in reversed(self.handles):kernel.CloseHandle(handle)
            self.handles=[]
    def stats(self,name):
        return os.stat(io_path(self.directory/name),follow_symlinks=False) if os.name=='nt' else os.stat(name,dir_fd=self.fd,follow_symlinks=False)
    def open(self,name,flags,mode=0o600):
        if '/' in name or '\\' in name:raise StockCacheError('STOCK_CACHE_PATH_INVALID')
        try:
            previous=self.stats(name)
            if not stat.S_ISREG(previous.st_mode) or previous.st_nlink!=1 or getattr(previous,'st_file_attributes',0)&1024:raise StockCacheError('STOCK_CACHE_PATH_INVALID')
        except FileNotFoundError:previous=None
        if os.name=='nt':
            # OPEN_REPARSE_POINT checks the opened entry rather than a path that
            # could have changed between lstat and open. No external target is
            # followed even during a last-component link race.
            import ctypes,msvcrt
            from ctypes import wintypes
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
            kernel.CreateFileW.restype=wintypes.HANDLE;kernel.CloseHandle.argtypes=[wintypes.HANDLE]
            desired=0x80000000|(0x40000000 if flags&(os.O_WRONLY|os.O_RDWR) else 0)
            disposition=1 if flags&os.O_EXCL and flags&os.O_CREAT else 4 if flags&os.O_CREAT else 3
            handle=kernel.CreateFileW(str(io_path(self.directory/name)),desired,3,None,disposition,0x00200000|0x80,None)
            if handle==ctypes.c_void_p(-1).value:
                code=ctypes.get_last_error()
                if code in {2,3}:raise FileNotFoundError()
                if code in {80,183}:raise FileExistsError()
                raise StockCacheError('STOCK_CACHE_IO_FAILED')
            try:
                actual=_windows_info(kernel,handle)
                if actual.attributes&(16|1024) or actual.links!=1:raise StockCacheError('STOCK_CACHE_PATH_INVALID')
                fd=msvcrt.open_osfhandle(handle,flags|getattr(os,'O_BINARY',0))
            except Exception:kernel.CloseHandle(handle);raise
        else:fd=os.open(name,flags|getattr(os,'O_NOFOLLOW',0),mode,dir_fd=self.fd)
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or getattr(info,'st_file_attributes',0)&1024 or previous and (previous.st_dev,previous.st_ino)!=(info.st_dev,info.st_ino):
            os.close(fd);raise StockCacheError('STOCK_CACHE_PATH_INVALID')
        return fd
    def names(self):
        with os.scandir(io_path(self.directory) if os.name=='nt' else self.fd) as iterator:
            for entry in iterator:yield entry.name
    def replace(self,source,target):
        if os.name=='nt':os.replace(io_path(self.directory/source),io_path(self.directory/target))
        else:os.replace(source,target,src_dir_fd=self.fd,dst_dir_fd=self.fd)
    def unlink(self,name):
        if os.name=='nt':os.unlink(io_path(self.directory/name))
        else:os.unlink(name,dir_fd=self.fd)

class StockResponseCache:
    def __init__(self,root,*,scope_sha256,provider,binding_sha256,execution_mode,configuration_sha256,policy=None,clock=time.time):
        self.root=ordinary(root);self.policy=policy or StockCachePolicy();self.clock=clock
        if type(self.policy) is not StockCachePolicy or not HEX.fullmatch(scope_sha256) or not HEX.fullmatch(binding_sha256) or not re.fullmatch(r'[a-z][a-z0-9-]{0,48}',provider) or execution_mode not in {'fixture','official'} or configuration_sha256 is not None and not HEX.fullmatch(configuration_sha256):
            raise ValueError('STOCK_CACHE_NAMESPACE_INVALID')
        if self.root==self.root.parent or linked(self.root):raise StockCacheError('STOCK_CACHE_PATH_INVALID')
        self.scope,self.provider,self.binding,self.mode,self.configuration=scope_sha256,provider,binding_sha256,execution_mode,configuration_sha256
        self.directory=self.root/scope_sha256/provider
        if self.root.resolve() not in self.directory.resolve().parents:raise StockCacheError('STOCK_CACHE_PATH_INVALID')
        self.marker={'schema':'stock-read-only-response-namespace.v1','root_sha256':digest(str(self.root.resolve())),
            'scope_sha256':self.scope,'provider':self.provider,'contents':'rebuildable-provider-response-json-only'}

    @staticmethod
    def _bytes(access,name,limit):
        fd=access.open(name,os.O_RDONLY)
        try:
            if os.fstat(fd).st_size>limit:raise StockCacheError('STOCK_CACHE_INVALID')
            with os.fdopen(fd,'rb',closefd=False) as handle:raw=handle.read(limit+1)
            if len(raw)>limit:raise StockCacheError('STOCK_CACHE_INVALID')
            return raw
        finally:os.close(fd)

    @contextmanager
    def locked(self,*,create=False):
        access=_Access(self.directory,create=create);fd=None;held=False
        try:
            if not access.available:yield None;return
            fd=access.open(LOCK,os.O_RDWR|os.O_CREAT)
            if os.fstat(fd).st_size>1:raise StockCacheError('STOCK_CACHE_CONTROL_INVALID')
            if not os.fstat(fd).st_size:os.write(fd,b'0');os.fsync(fd)
            deadline=time.monotonic()+self.policy.lock_timeout_seconds
            while True:
                try:
                    if os.name=='nt':
                        import msvcrt
                        os.lseek(fd,0,os.SEEK_SET);msvcrt.locking(fd,msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    held=True;break
                except OSError:
                    if time.monotonic()>=deadline:raise StockCacheError('STOCK_CACHE_BUSY') from None
                    time.sleep(.01)
            try:raw=self._bytes(access,MARKER,2048)
            except FileNotFoundError:
                encoded=json.dumps(self.marker,sort_keys=True,separators=(',',':')).encode()
                self._atomic(access,MARKER,encoded);raw=encoded
            try:marker=json.loads(raw)
            except (ValueError,TypeError):raise StockCacheError('STOCK_CACHE_CONTROL_INVALID') from None
            if marker!=self.marker:raise StockCacheError('STOCK_CACHE_CONTROL_INVALID')
            yield access
        finally:
            if held:
                if os.name=='nt':
                    import msvcrt
                    os.lseek(fd,0,os.SEEK_SET);msvcrt.locking(fd,msvcrt.LK_UNLCK,1)
                else:
                    import fcntl
                    fcntl.flock(fd,fcntl.LOCK_UN)
            if fd is not None:os.close(fd)
            access.close()

    def _envelope(self,raw,key):
        try:value=json.loads(raw)
        except (ValueError,TypeError):raise StockCacheError('STOCK_CACHE_INVALID') from None
        try:
            valid=(type(value['schema']) is int and value['schema']==2 and value['scope']==self.scope and value['key']==key
                and value['provider']==self.provider and value['binding_sha256']==self.binding and value['execution_mode']==self.mode
                and value['configuration_sha256']==self.configuration and isinstance(value['response'],dict)
                and value['sha256']==digest(value['response']) and type(value['created_at']) in (int,float) and math.isfinite(value['created_at']))
        except (KeyError,ValueError,TypeError):valid=False
        if not valid:raise StockCacheError('STOCK_CACHE_INVALID')
        return value

    def _inspect(self,access):
        names=[]
        for name in access.names():
            names.append(name)
            if len(names)>self.policy.max_scan_entries:raise StockCacheError('STOCK_CACHE_SCAN_LIMIT')
        names.sort();entries=[];protected=0;size=0;unknown=False;controls=0;parsed_bytes=0
        for name in names:
            info=access.stats(name);size+=info.st_size
            if name in {LOCK,MARKER}:controls+=1;continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or getattr(info,'st_file_attributes',0)&1024:
                protected+=1;unknown|=not stat.S_ISREG(info.st_mode);continue
            key=name[:-5] if name.endswith('.json') else ''
            if not HEX.fullmatch(key) or info.st_size>self.policy.max_file_bytes:protected+=1;continue
            parsed_bytes+=info.st_size
            if parsed_bytes>self.policy.max_scan_bytes:raise StockCacheError('STOCK_CACHE_SCAN_LIMIT')
            try:raw=self._bytes(access,name,self.policy.max_file_bytes);value=self._envelope(raw,key)
            except StockCacheError:protected+=1;continue
            entries.append({'name':name,'key':key,'size':info.st_size,'created_at':value['created_at'],
                'signature':(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns),'sha256':hashlib.sha256(raw).hexdigest()})
        return {'entries':entries,'count':len(names),'bytes':size,'protected_entries':protected,'unknown_nested_bytes':unknown,'control_entries':controls}

    def _delete(self,access,entry):
        info=access.stats(entry['name'])
        if (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)!=entry['signature']:raise StockCacheError('STOCK_CACHE_CHANGED')
        raw=self._bytes(access,entry['name'],self.policy.max_file_bytes)
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise StockCacheError('STOCK_CACHE_CHANGED')
        self._envelope(raw,entry['key']);access.unlink(entry['name'])

    def _trim(self,access,inspection,*,reserve_entries=0,reserve_bytes=0,keep=None):
        removed=0;removed_bytes=0;clock=float(self.clock())
        if not math.isfinite(clock):raise StockCacheError('STOCK_CACHE_CLOCK_INVALID')
        remaining=[]
        for entry in sorted(inspection['entries'],key=lambda entry:(entry['created_at'],entry['key'])):
            if entry['key']!=keep and clock-entry['created_at']>=self.policy.max_age_seconds:
                self._delete(access,entry);removed+=1;removed_bytes+=entry['size']
            else:remaining.append(entry)
        for entry in remaining:
            if inspection['count']-removed+reserve_entries<=self.policy.max_entries and inspection['bytes']-removed_bytes+reserve_bytes<=self.policy.max_bytes:break
            if entry['key']==keep:continue
            self._delete(access,entry);removed+=1;removed_bytes+=entry['size']
        count=inspection['count']-removed;size=inspection['bytes']-removed_bytes
        return {'schema_version':'stock-response-cache-maintenance.v1','namespace_entries':count,'namespace_bytes':size,
            'verified_entries':len(inspection['entries'])-removed,'protected_entries':inspection['protected_entries'],
            'control_entries':inspection['control_entries'],'unknown_nested_bytes':inspection['unknown_nested_bytes'],
            'removed_entries':removed,'removed_bytes':removed_bytes,
            'within_limits':not inspection['unknown_nested_bytes'] and count+reserve_entries<=self.policy.max_entries and size+reserve_bytes<=self.policy.max_bytes,
            'provider_calls':0,'media_files_touched':0,'quota_state_touched':False}

    @staticmethod
    def _atomic(access,name,raw):
        temporary='.'+uuid.uuid4().hex+'.stock-cache.tmp';fd=access.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        try:
            with os.fdopen(fd,'wb',closefd=False) as handle:handle.write(raw);handle.flush();os.fsync(fd)
            os.close(fd);fd=None;access.replace(temporary,name)
        finally:
            if fd is not None:os.close(fd)
            try:access.unlink(temporary)
            except FileNotFoundError:pass

    def read(self,key):
        if not isinstance(key,str) or not HEX.fullmatch(key):raise ValueError('STOCK_CACHE_KEY_INVALID')
        with self.locked() as access:
            if access is None:return None
            try:value=self._envelope(self._bytes(access,key+'.json',self.policy.max_file_bytes),key)
            except FileNotFoundError:return None
            age=float(self.clock())-value['created_at']
            return value['response'] if 0<=age<self.policy.max_age_seconds else None

    def maintain(self):
        with self.locked() as access:
            if access is None:return {'schema_version':'stock-response-cache-maintenance.v1','namespace_entries':0,'namespace_bytes':0,
                'verified_entries':0,'protected_entries':0,'control_entries':0,'unknown_nested_bytes':False,'removed_entries':0,'removed_bytes':0,
                'within_limits':True,'provider_calls':0,'media_files_touched':0,'quota_state_touched':False}
            return self._trim(access,self._inspect(access))

    def write(self,key,envelope):
        if not isinstance(key,str) or not HEX.fullmatch(key):raise ValueError('STOCK_CACHE_KEY_INVALID')
        raw=json.dumps(envelope,ensure_ascii=False,separators=(',',':')).encode();self._envelope(raw,key)
        with self.locked(create=True) as access:
            inspection=self._inspect(access);old=next((entry for entry in inspection['entries'] if entry['key']==key),None)
            # Existing foreign/invalid files are never overwritten or deleted.
            if old is None:
                try:access.stats(key+'.json')
                except FileNotFoundError:pass
                else:raise StockCacheError('STOCK_CACHE_INVALID')
            if len(raw)>self.policy.max_file_bytes or len(raw)>self.policy.max_bytes:
                return {**self._trim(access,inspection),'stored':False,'code':'STOCK_CACHE_ENTRY_NOT_STORED'}
            reserve_entries=0 if old else 1;reserve_bytes=len(raw)-(old['size'] if old else 0)
            report=self._trim(access,inspection,reserve_entries=reserve_entries,reserve_bytes=reserve_bytes,keep=key)
            if not report['within_limits']:return {**report,'stored':False,'code':'STOCK_CACHE_GROWTH_BLOCKED'}
            self._atomic(access,key+'.json',raw)
            return {**report,'namespace_entries':report['namespace_entries']+reserve_entries,
                'namespace_bytes':report['namespace_bytes']+reserve_bytes,'verified_entries':report['verified_entries']+(0 if old else 1),'stored':True,'code':None}
