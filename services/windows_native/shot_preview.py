"""Version-bound local proxies. Cached proxies are never acceptance artifacts."""
import copy
import asyncio
import json
from pathlib import Path
import subprocess
import threading
import time
from .contracts import WorkflowError, digest, file_sha, write_json
from .media import media_path, project_assets
from .hardening import durable_json,retry_io
from .source_preview import profile_for, resolve_assets, render as render_source
from app.timeline_proxy import PreviewCancelledError


def proxy_key(shot, document):
    keys=('asset_id','source_sha256','duration','visual','on_screen_text','subtitle','crop_strategy','motion','source_start','transition')
    return digest({'schema':'native-shot-proxy-v2','shot':{k:shot.get(k) for k in keys},
                   'brand_template':document.get('brand_template'),'audio_mode':'silent_visual_proxy'})


def shot_fields(project):
    view=project['shot_timeline']
    return view, view['shots']


class PreviewManager:
    def __init__(self, config, store):
        self.config,self.store=config,store
        self.root=config.data_root/'shot-previews'; self.root.mkdir(parents=True,exist_ok=True)
        self.cache=self.root/'cache'; self.cache.mkdir(exist_ok=True)
        self.lock=threading.RLock(); self.cancelled={}; self.workers={}
        self.render_lock=threading.Lock()

    def close(self):
        with self.lock:
            for event in self.cancelled.values(): event.set()
            workers=list(self.workers.values())
        for worker in workers:
            if worker.is_alive(): worker.join(timeout=5)

    def _write(self,path,value):
        with self.lock:
            retry_io(lambda:durable_json(path,value),lambda _:None,'storage_preview')

    def _folder(self, project_id, timeline_sha, revision, profile=None):
        identity={'project':project_id,'timeline':timeline_sha,'revision':revision}
        if profile:identity['preview_profile']=profile
        return self.root/digest(identity)

    def status(self, project_id):
        with self.lock:
            return self._status(project_id)

    def _status(self, project_id):
        project=self.store.shot_view(project_id); view,_=shot_fields(project)
        source_mode=view.get('editing_mode')=='source_footage'
        profile=profile_for(project) if source_mode else None
        folder=self._folder(project_id,view['sha256'],project['revision'],profile); record=folder/'preview.json'
        if not record.is_file():
            history=sorted(self.root.glob('*/preview.json'),key=lambda p:p.stat().st_mtime,reverse=True)
            previous=next((json.loads(p.read_bytes()) for p in history if json.loads(p.read_bytes()).get('project_id')==project_id),None)
            return {**(previous or {}),'status':'STALE' if previous else 'EMPTY','revision':project['revision'],
                    'timeline_version':view['version'],'timeline_sha256':view['sha256'],
                    'video_url':None,'audio_mode':'canonical_timeline_proxy' if source_mode else 'silent_visual_proxy','final_approval_eligible':False}
        value=json.loads(record.read_bytes())
        if value['revision']!=project['revision']:
            return {**value,'status':'STALE','video_url':None}
        if value['status'] in {'RUNNING','QUEUED'} and value['id'] not in self.workers:
            value.update(status='FAILED',error={'code':'PREVIEW_INTERRUPTED_REQUEST_AGAIN','automatic_replay':False})
            self._write(record,value)
        if value['status']=='READY':
            output=folder/'preview.mp4'
            if not output.is_file() or file_sha(output)!=value['sha256']:
                raise WorkflowError('PREVIEW_ARTIFACT_CHANGED')
            if source_mode:
                manifest=folder/'render-manifest.json'
                if (value.get('preview_profile') != profile or not manifest.is_file()
                        or file_sha(manifest) != value.get('manifest_sha256')
                        or json.loads(manifest.read_bytes()) != value.get('manifest')
                        or value.get('manifest',{}).get('timeline_sha256') != view['sha256']
                        or value.get('manifest',{}).get('timeline_version') != view['version']):
                    raise WorkflowError('PREVIEW_MANIFEST_CHANGED')
                resolve_assets(self.config,project)
            value['video_url']=f"/api/projects/{project_id}/preview/video?version={view['version']}"
        return value

    def generate(self, project_id, revision):
        with self.lock:
            project=self.store.shot_view(project_id)
            if project['revision']!=revision: raise WorkflowError('STALE_VERSION_RELOAD')
            if project.get('archived'): raise WorkflowError('PROJECT_ARCHIVED_RESTORE_FIRST')
            if any(j['status'] in {'queued','running','retrying'} for j in project['jobs']): raise WorkflowError('PROJECT_BUSY')
            view,shots=shot_fields(project)
            source_mode=view.get('editing_mode')=='source_footage'
            if source_mode:
                resolve_assets(self.config,project)
            else:
                if not shots or len(shots)>20 or sum(s['duration'] for s in shots)>180:
                    raise WorkflowError('PREVIEW_SHOTS_DURATION_INVALID',400)
                assets={a['id']:a for a in project_assets(project['document'])}
                for s in shots:
                    a=assets.get(s['asset_id']); source=media_path(self.config,s['asset_id']) if a else None
                    if not a or a.get('rights_confirmed') is not True or not source.is_file() or file_sha(source)!=a['sha256']:
                        raise WorkflowError('SOURCE_MEDIA_CHANGED_OR_MISSING')
                    s['source_sha256']=a['sha256']
            profile=profile_for(project) if source_mode else None
            folder=self._folder(project_id,view['sha256'],revision,profile); folder.mkdir(parents=True,exist_ok=True)
            old=self.status(project_id)
            if old.get('status') in {'READY','RUNNING','QUEUED'}: return old
            identifier=folder.name
            value={'id':identifier,'project_id':project_id,'revision':revision,'timeline_version':view['version'],
                   'timeline_sha256':view['sha256'],'status':'QUEUED','completed_shots':0,'total_shots':len(shots),
                   'cached_shots':0,'new_proxy_shots':0,'audio_mode':'canonical_timeline_proxy' if source_mode else 'silent_visual_proxy','final_approval_eligible':False,
                   **({'preview_profile':profile} if source_mode else {}),
                   'provider_calls':0,'tts_calls':0,'video_url':None}
            self._write(folder/'preview.json',value)
            event=threading.Event(); self.cancelled[identifier]=event
            worker=threading.Thread(target=self._run_source if source_mode else self._run,args=(copy.deepcopy(project),folder,event),daemon=True,name='native-source-proxy' if source_mode else 'native-shot-proxy')
            self.workers[identifier]=worker; worker.start()
            return value

    def cancel(self, project_id, revision):
        with self.lock:
            project=self.store.shot_view(project_id)
            if revision!=project['revision']: raise WorkflowError('STALE_VERSION_RELOAD')
            value=self.status(project_id)
            if value.get('id') in self.cancelled: self.cancelled[value['id']].set()
            return {**value,'cancel_requested':True}

    def video_path(self, project_id, version):
        value=self.status(project_id)
        if value['status']!='READY' or str(value['timeline_version'])!=str(version):
            raise WorkflowError('PREVIEW_STALE_OR_NOT_READY')
        return self._folder(project_id,value['timeline_sha256'],value['revision'],value.get('preview_profile'))/'preview.mp4'

    @staticmethod
    def _command(command, directory, event):
        with (directory/'proxy.log').open('ab') as log:
            process=subprocess.Popen(command,cwd=directory,stdout=log,stderr=subprocess.STDOUT)
            start=time.monotonic()
            while process.poll() is None:
                if event.wait(.15) or time.monotonic()-start>180:
                    process.terminate(); process.wait(timeout=10)
                    raise WorkflowError('PREVIEW_CANCELLED' if event.is_set() else 'PREVIEW_TIMEOUT')
            if process.returncode: raise WorkflowError('PREVIEW_FFMPEG_FAILED')

    def _proxy(self, shot, project, event):
        with self.render_lock:
            return self._proxy_one(shot,project,event)

    def _proxy_one(self, shot, project, event):
        key=proxy_key(shot,project['document']); directory=self.cache/key
        directory.mkdir(exist_ok=True); output=directory/'proxy.mp4'; receipt=directory/'proxy.json'
        if output.is_file() and receipt.is_file():
            value=json.loads(receipt.read_bytes())
            if value['key']!=key or value['sha256']!=file_sha(output): raise WorkflowError('PREVIEW_CACHE_CHANGED')
            return output,True
        # An interrupted proxy is local/reversible and may be explicitly retried. No provider dispatch.
        temp=directory/'working.mp4'
        if temp.exists(): temp.unlink()
        asset=next(a for a in project_assets(project['document']) if a['id']==shot['asset_id'])
        source=media_path(self.config,asset['id'])
        landscape=(project['document'].get('brand_template') or {}).get('template',{}).get('aspect_ratio')=='16:9'
        width,height=(960,540) if landscape else (540,960)
        duration=shot['duration']; fit=shot.get('crop_strategy','contain')
        from PIL import ImageFont
        from .pipeline import wrap_text,ass_time,ass_escape
        font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',24 if landscape else 28)
        lines=wrap_text(shot.get('subtitle',''),font,width-80)
        phrases=['\n'.join(lines[i:i+2]) for i in range(0,len(lines),2)]
        weights=[len(p) for p in phrases];cursor=0.;events=[]
        for phrase,weight in zip(phrases,weights):
            end=cursor+duration*weight/sum(weights)
            text='\\N'.join(ass_escape(line) for line in phrase.splitlines())
            events.append(f'Dialogue: 0,{ass_time(cursor)},{ass_time(end)},Subtitle,,0,0,0,,{text}')
            cursor=end
        title=ass_escape(shot.get('on_screen_text',''))
        events.append(f'Dialogue: 0,0:00:00.00,{ass_time(duration)},Title,,0,0,0,,{title}')
        header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Subtitle,Arial,{24 if landscape else 28},&H00FFFFFF,&H00FFFFFF,&H00101820,&H80101820,0,0,0,0,100,100,0,0,1,2,1,2,40,40,60,1
Style: Title,Arial,{24 if landscape else 28},&H00FFFFFF,&H00FFFFFF,&H00101820,&H80101820,-1,0,0,0,100,100,0,0,1,2,1,8,40,40,40,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
'''
        (directory/'subtitles.ass').write_text(header+'\n'.join(events)+'\n',encoding='utf-8')
        scale=(f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}' if fit=='cover' else
               f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x101820')
        motion=''
        if asset['kind']=='image' and shot.get('motion') not in {None,'none'}:
            zoom='min(1+on*0.0004,1.08)' if shot['motion']=='zoom_in' else '1.06'
            x='iw/2-iw/zoom/2' if shot['motion']=='zoom_in' else ('(iw-iw/zoom)*(1-min(on/150,1))' if shot['motion']=='pan_left' else '(iw-iw/zoom)*min(on/150,1)')
            motion=f",zoompan=z='{zoom}':x='{x}':y='ih/2-ih/zoom/2':d=1:s={width}x{height}:fps=30"
        command=[str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-hide_banner','-nostdin','-n']
        command += ['-loop','1','-framerate','30'] if asset['kind']=='image' else ['-stream_loop','-1','-ss',str(shot.get('source_start',0)),'-protocol_whitelist','file,pipe']
        fade=f',fade=t=in:st=0:d=0.15,fade=t=out:st={max(0,duration-.15):.6f}:d=0.15' if shot.get('transition')=='fade' else ''
        command += ['-i',str(source),'-vf',scale+motion+',setsar=1,fps=30,ass=subtitles.ass'+fade+',format=yuv420p','-an','-c:v','libx264','-preset','ultrafast','-crf','26','-t',str(duration),'-movflags','+faststart',str(temp)]
        self._command(command,directory,event)
        if event.is_set(): raise WorkflowError('PREVIEW_CANCELLED')
        temp.replace(output); write_json(receipt,{'key':key,'sha256':file_sha(output),'source_sha256':asset['sha256'],'audio_mode':'silent_visual_proxy'})
        return output,False

    def _run(self, project, folder, event):
        with self.lock:
            value=json.loads((folder/'preview.json').read_bytes()); value['status']='RUNNING'; self._write(folder/'preview.json',value)
        try:
            paths=[]
            for shot in project['shot_timeline']['shots']:
                if event.is_set(): raise WorkflowError('PREVIEW_CANCELLED')
                path,cached=self._proxy(shot,project,event); paths.append(path)
                value['completed_shots']+=1; value['cached_shots']+=int(cached); value['new_proxy_shots']+=int(not cached)
                self._write(folder/'preview.json',value)
            manifest=folder/'concat.txt'
            manifest.write_text('ffconcat version 1.0\n'+''.join("file '"+str(p).replace('\\','/').replace("'", "'\\''")+"'\n" for p in paths),encoding='utf-8')
            output=folder/'preview.mp4'
            if output.exists(): output.unlink()
            self._command([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-hide_banner','-nostdin','-n','-f','concat','-safe','0','-i',str(manifest),'-c','copy','-movflags','+faststart',str(output)],folder,event)
            value.update(status='READY',sha256=file_sha(output),video_url=f"/api/projects/{project['id']}/preview/video?version={value['timeline_version']}")
        except Exception as error:
            code=error.code if isinstance(error,WorkflowError) else type(error).__name__
            value.update(status='CANCELLED' if code=='PREVIEW_CANCELLED' else 'FAILED',error={'code':code,'automatic_replay':False},video_url=None)
        finally:
            with self.lock:
                self._write(folder/'preview.json',value)
                self.workers.pop(value['id'],None)

    def _run_source(self, project, folder, event):
        with self.lock:
            value=json.loads((folder/'preview.json').read_bytes())
            value['status']='RUNNING';self._write(folder/'preview.json',value)
        output=folder/'preview.mp4'
        try:
            # Preserve the local renderer concurrency limit. Cancellation is checked
            # by the shared async renderer before and throughout media execution.
            with self.render_lock:
                manifest=asyncio.run(render_source(self.config,project,output,event))
            if event.is_set():raise PreviewCancelledError('preview was cancelled')
            manifest_path=folder/'render-manifest.json'
            self._write(manifest_path,manifest)
            value.update(status='READY',sha256=file_sha(output),manifest_sha256=file_sha(manifest_path),
                manifest=manifest,completed_shots=value['total_shots'],new_proxy_shots=value['total_shots'],
                video_url=f"/api/projects/{project['id']}/preview/video?version={value['timeline_version']}")
        except Exception as error:
            code='PREVIEW_CANCELLED' if isinstance(error,PreviewCancelledError) else error.code if isinstance(error,WorkflowError) else 'SOURCE_PREVIEW_RENDER_FAILED'
            output.unlink(missing_ok=True)
            value.update(status='CANCELLED' if code=='PREVIEW_CANCELLED' else 'FAILED',
                error={'code':code,'automatic_replay':False},video_url=None)
        finally:
            with self.lock:
                self._write(folder/'preview.json',value)
                self.workers.pop(value['id'],None)
