"""Local cover sources and bounded image transforms, separate from video approval."""
import hashlib
import io
import json
import math
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Literal
from pydantic import Field,StrictBool,model_validator
from app.models import StrictModel
from .backup import guard
from .contracts import WorkflowError,digest,file_sha
from .hardening import durable_json
from .store import now

MAX_BYTES=8*1024*1024
MAX_PIXELS=20_000_000


class CoverOptions(StrictModel):
    source:Literal['frame','uploaded_cover','project_image','render_thumbnail']='frame'
    source_id:str|None=Field(default=None,pattern=r'^[A-Za-z0-9_.-]{1,100}$')
    format:Literal['jpg','png']='jpg'
    center_x:float=Field(default=.5,strict=True,ge=0,le=1,allow_inf_nan=False)
    center_y:float=Field(default=.5,strict=True,ge=0,le=1,allow_inf_nan=False)
    zoom:float=Field(default=1,strict=True,ge=1,le=4,allow_inf_nan=False)
    title:str=Field(default='',max_length=160)
    logo:StrictBool=False

    @model_validator(mode='after')
    def source_reference(self):
        if (self.source=='frame') != (self.source_id is None):raise ValueError('Cover source reference required')
        if '\x00' in self.title:raise ValueError('Invalid title')
        return self


def checked_image(raw,declared=None):
    from PIL import Image,UnidentifiedImageError
    if not 0<len(raw)<=MAX_BYTES:raise WorkflowError('EXPORT_COVER_MAX_8MB',400)
    try:
        with Image.open(io.BytesIO(raw)) as image:
            width,height=image.size;kind=image.format
            if width*height>MAX_PIXELS or min(width,height)<16:raise ValueError()
            image.verify()
        actual={'JPEG':'image/jpeg','PNG':'image/png','WEBP':'image/webp'}.get(kind)
        if actual is None or declared not in (None,'application/octet-stream',actual):raise ValueError()
        with Image.open(io.BytesIO(raw)) as image:
            from PIL import ImageOps
            pixels=ImageOps.exif_transpose(image).convert('RGB')
        return pixels,actual
    except (ValueError,OSError,UnidentifiedImageError,Image.DecompressionBombError):
        raise WorkflowError('EXPORT_COVER_IMAGE_OR_MIME_INVALID',400) from None


class NativeDeliveryCovers:
    def __init__(self,delivery):
        self.delivery=delivery;self.store=delivery.store;self.config=delivery.config
        with self.store.transaction() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS native_delivery_covers (
                cover_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                checksum_sha256 TEXT NOT NULL,filename TEXT NOT NULL,content_type TEXT NOT NULL,
                width INTEGER NOT NULL,height INTEGER NOT NULL,created_at TEXT NOT NULL,
                UNIQUE(workspace_id,project_id,checksum_sha256))''')

    def path(self,project_id,cover_id):
        if not re.fullmatch(r'ncov_[a-f0-9]{32}',cover_id):raise WorkflowError('EXPORT_COVER_NOT_FOUND',404)
        return guard(self.store.root/'delivery-cover-assets'/project_id/(cover_id+'.image'))

    def upload(self,project_id,revision,raw,filename,content_type,*,authorization_check=lambda:None):
        self.delivery.scope();authorization_check()
        image,mime=checked_image(raw,content_type)
        if not isinstance(filename,str) or not 1<=len(filename)<=100 or any(ord(c)<32 for c in filename):raise WorkflowError('EXPORT_COVER_FILENAME_INVALID',400)
        checksum=hashlib.sha256(raw).hexdigest()
        with self.store.transaction() as con:
            self.store.editable(con,project_id,revision);authorization_check()
            old=con.execute('SELECT * FROM native_delivery_covers WHERE workspace_id=? AND project_id=? AND checksum_sha256=?',
                (self.delivery.workspace,project_id,checksum)).fetchone()
            if old:
                path=guard(self.path(project_id,old['cover_id']),exists=True)
                if path.stat().st_size>MAX_BYTES or file_sha(path)!=checksum:raise WorkflowError('EXPORT_COVER_SOURCE_CHANGED')
                return {**dict(old),'rights_status':'unknown','idempotent_replay':True}
            identifier='ncov_'+uuid.uuid4().hex;path=self.path(project_id,identifier);path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as output:output.write(raw);output.flush();os.fsync(output.fileno())
            authorization_check()
            row=(identifier,self.delivery.workspace,project_id,checksum,filename,mime,image.width,image.height,now())
            con.execute('INSERT INTO native_delivery_covers VALUES(?,?,?,?,?,?,?,?,?)',row)
        return {'cover_id':identifier,'filename':filename,'content_type':mime,'checksum_sha256':checksum,'width':image.width,'height':image.height,
            'rights_status':'unknown','idempotent_replay':False,'video_approval_changed':False,'externally_posted':False}

    def read(self,project_id,cover_id):
        self.delivery.scope()
        with self.store.transaction() as con:
            row=con.execute('SELECT * FROM native_delivery_covers WHERE workspace_id=? AND project_id=? AND cover_id=?',
                (self.delivery.workspace,project_id,cover_id)).fetchone()
        if row is None:raise WorkflowError('EXPORT_COVER_NOT_FOUND',404)
        path=guard(self.path(project_id,cover_id),exists=True)
        if path.stat().st_size>MAX_BYTES or file_sha(path)!=row['checksum_sha256']:raise WorkflowError('EXPORT_COVER_SOURCE_CHANGED')
        return path,dict(row)

    def page(self,project_id):
        self.delivery.scope();project=self.store.get(project_id)
        with self.store.transaction() as con:
            rows=[dict(r) for r in con.execute('SELECT * FROM native_delivery_covers WHERE workspace_id=? AND project_id=? ORDER BY created_at DESC LIMIT 100',(self.delivery.workspace,project_id))]
        from .source_assets import canonical_assets
        assets=[{'id':a['id'],'filename':a.get('filename',a['id']),'sha256':a.get('sha256'),'rights_status':a.get('rights_status','unknown')}
            for a in canonical_assets(project['document']) if a['kind']=='image']
        from .render_thumbnails import NativeRenderThumbnails
        candidates=NativeRenderThumbnails(self.store,self.config,workspace_id=self.delivery.workspace).page(project_id)['items']
        return {'uploads':rows,'project_images':assets,'candidates':[{'id':c['thumbnail_asset_id'],'render_job_id':c['snapshot']['request']['render_job_id'],
            'frame_id':c['snapshot']['frame']['frame_id']} for c in candidates],
            'logo_configured':bool((project['document'].get('brand_template') or {}).get('brand',{}).get('logo')),
            'video_approval_changed':False,'externally_posted':False}

    def export(self,project_id,job,options,video,stage,*,width,height,timestamp):
        options=options or CoverOptions();document=job['snapshot']['document']
        provenance={'source_type':options.source,'source_id':options.source_id,'rights_independently_verified':False}
        if options.source=='frame':
            result=subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-ss',str(timestamp),'-i',str(video),
                '-frames:v','1','-f','image2pipe','-c:v','png','pipe:1'],capture_output=True,check=True,timeout=60)
            raw=result.stdout;provenance.update(video_sha256=file_sha(video),timestamp_seconds=timestamp)
        elif options.source=='uploaded_cover':
            path,record=self.read(project_id,options.source_id);raw=path.read_bytes()
            provenance.update(source_sha256=record['checksum_sha256'],rights_status='unknown')
        elif options.source=='project_image':
            from .source_assets import canonical_assets
            from .media import media_path
            asset=next((a for a in canonical_assets(document) if a['id']==options.source_id and a['kind']=='image'),None)
            if asset is None:raise WorkflowError('EXPORT_COVER_SOURCE_NOT_IN_PROJECT')
            path=guard(media_path(self.config,asset['id']),exists=True)
            if file_sha(path)!=asset['sha256']:raise WorkflowError('EXPORT_COVER_SOURCE_CHANGED')
            raw=path.read_bytes();provenance.update(source_sha256=asset['sha256'],rights_status=asset.get('rights_status','unknown'))
        else:
            from .render_thumbnails import NativeRenderThumbnails
            raw,selected=NativeRenderThumbnails(self.store,self.config,workspace_id=self.delivery.workspace).image(project_id,options.source_id)
            if selected['request']['render_job_id']!=job['id']:raise WorkflowError('EXPORT_COVER_DIFFERENT_RENDER')
            provenance.update(source_sha256=selected['image']['sha256'],frame_id=selected['frame']['frame_id'],reviewed_vision=selected['reviewed_vision'])
        image,_=checked_image(raw);source_size=image.size
        # Crop in source pixels, then resize once. Geometry is never stretched.
        ratio=width/height;crop_width=min(image.width,image.height*ratio)/options.zoom;crop_height=crop_width/ratio
        left=max(0,min(image.width-crop_width,options.center_x*image.width-crop_width/2))
        top=max(0,min(image.height-crop_height,options.center_y*image.height-crop_height/2))
        box=(round(left),round(top),round(left+crop_width),round(top+crop_height))
        from PIL import Image,ImageDraw,ImageFont
        image=image.crop(box).resize((width,height),Image.Resampling.LANCZOS)
        if options.title or options.logo:
            from .branding import validate_assets
            brand=validate_assets(self.config,document)
            if options.title:
                draw=ImageDraw.Draw(image);font_path=Path(os.environ.get('WINDIR',r'C:\Windows'))/'Fonts'/brand.fonts.heading
                size=max(24,round(width*.055));lines=[]
                while size>=20:
                    font=ImageFont.truetype(str(font_path),size);lines=['']
                    for char in options.title.replace('\r','').replace('\n',' '):
                        candidate=lines[-1]+char
                        if draw.textlength(candidate,font=font)>width*.85 and lines[-1]:lines.append(char)
                        else:lines[-1]=candidate
                    if len(lines)*size*1.3<height*.3:break
                    size-=2
                text='\n'.join(lines);margin=round(width*.065);line_height=round(size*1.3);top_text=height-margin-len(lines)*line_height
                draw.rectangle((margin-12,top_text-12,width-margin+12,height-margin+12),fill=brand.palette.background)
                draw.multiline_text((margin,top_text),text,font=font,fill=brand.palette.text,spacing=max(2,round(size*.3)))
                provenance.update(title=options.title,font=brand.fonts.heading)
            if options.logo:
                if not brand.logo:raise WorkflowError('EXPORT_COVER_LOGO_NOT_CONFIGURED')
                from .media import media_path
                with Image.open(media_path(self.config,brand.logo)) as logo:
                    logo=logo.convert('RGB');logo.thumbnail((round(width*.22),round(height*.12)))
                    image.paste(logo,(round(width*.05),round(height*.05)))
                provenance['logo_asset_id']=brand.logo
        name='cover.'+options.format;image.save(stage/name,format='JPEG' if options.format=='jpg' else 'PNG',**({'quality':94} if options.format=='jpg' else {}))
        provenance.update(source_size=list(source_size),crop_pixels=list(box),output_width=width,output_height=height,
            settings=options.model_dump(mode='json'),output_sha256=file_sha(stage/name))
        durable_json(stage/'cover-provenance.json',provenance)
        return name
