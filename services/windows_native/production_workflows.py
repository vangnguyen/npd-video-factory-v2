"""Production choices and reviewed drama authoring over the existing canonical timeline."""
import copy,json,re,uuid,unicodedata
from pydantic import Field,StrictBool,StrictInt,StrictStr,ValidationError
from app.models import StrictModel
from .contracts import WorkflowError,digest,normalize
from .store import now

SCHEMA='native-production-workflow.v1'
FORMATS={'9:16':(1080,1920,'vertical'),'16:9':(1920,1080,'landscape'),'1:1':(1080,1080,'square'),'4:5':(1080,1350,'feed')}
STEPS=('script','voices','scenes','preview','export')

def is_drama(document):return document.get('production_workflow',{}).get('kind')=='drama'

def drama_selection(output_format='9:16',*,template_id=None,duration_mode=None):
    from .branding import catalog,BrandProfile,VideoTemplate,Selection,FIT_NARRATION_POLICY
    if template_id is not None:
        output_format=next((ratio for ratio,(_,_,suffix) in FORMATS.items() if template_id=='drama-'+suffix),None)
    if output_format not in FORMATS or duration_mode not in (None,FIT_NARRATION_POLICY):raise WorkflowError('DRAMA_OUTPUT_FORMAT_INVALID',400)
    width,height,suffix=FORMATS[output_format]
    base=copy.deepcopy(next(b for b in catalog()['brands'] if b['id']=='vf-reference'))
    base.update(id='drama-neutral',name='Phim Drama',asset_status='generic_reference',logo=None,primary_cta='',intro='',intro_seconds=0.,outro_seconds=.25,project_disclaimers=[])
    brand=BrandProfile.model_validate(base).model_dump()
    template=VideoTemplate(id='drama-'+suffix,name='Phim thoại nhiều nhân vật',purpose='drama',scene_label='PHIM DRAMA',duration_seconds=30,
        width=width,height=height,aspect_ratio=output_format,duration_policy=FIT_NARRATION_POLICY).model_dump()
    return Selection(brand=brand,template=template,brand_sha256=digest(brand),template_sha256=digest(template)).model_dump()

def initial_selection(kind,output_format):
    if output_format not in FORMATS:raise WorkflowError('DRAMA_OUTPUT_FORMAT_INVALID',400)
    result={'production_workflow':{'schema_version':SCHEMA,'kind':kind,'series':None,'episode':None}}
    if kind=='drama':result.update(brand_template=drama_selection(output_format),music_enabled=False,niche='fiction_drama')
    return result

def catalog():
    return {'schema_version':SCHEMA,'choices':[
        {'kind':'standard','name':'Video giới thiệu / nội dung','description':'Kể chuyện, giới thiệu hoặc chia sẻ kiến thức.','input':'Ý tưởng, kịch bản và tư liệu','output':'Video có lời đọc, phụ đề và gói đăng thủ công'},
        {'kind':'drama','name':'Phim Drama','description':'Phim ngắn với lời thoại và giọng riêng cho từng nhân vật.','input':'Ý tưởng hoặc kịch bản có người nói; ảnh/video cho các cảnh','output':'Video thoại nhiều nhân vật, phụ đề theo người nói và gói đăng thủ công'},
        {'kind':'source','name':'Dựng từ video có sẵn','description':'Cắt và biên tập footage bạn đã có.','input':'Video nguồn có quyền sử dụng','output':'Video đã dựng, phụ đề và gói đăng thủ công'}],
        'drama':{'default_format':'9:16','width':1080,'height':1920,'narrator_enabled':False,'timing':'measured_per_line_audio_and_intentional_pauses',
            'steps':list(STEPS),'formats':list(FORMATS),'max_scenes':20,'max_seconds':180,'acting_generation_verified':False,'lip_sync_verified':False,'character_consistency_verified':False},'provider_calls':0}

def key(value):return unicodedata.normalize('NFC',normalize(value)).casefold()
def identifier(project,prefix,value):return prefix+uuid.uuid5(uuid.NAMESPACE_URL,'vf/drama/'+project+'/'+prefix+'/'+value).hex

def parse_script(text,project_id):
    """Conservative labels only: actions are visual, unknown speakers need review."""
    scenes=[];current=None;characters={};lines=[]
    def scene(title):
        nonlocal current
        current={'scene_key':identifier(project_id,'scene_',str(len(scenes))+':'+title),'title':title[:150],'actions':[],'lines':[]}
        scenes.append(current)
    for number,raw in enumerate(text.splitlines()):
        raw=raw.strip()
        if not raw:continue
        if re.match(r'^(?:CẢNH|SCENE)\s+\d+(?:\s|[:.\-–]|$)',raw,re.I):scene(raw);continue
        if current is None:scene('Cảnh 1')
        if raw.startswith(('(', '[','*')) or re.match(r'^(?:Hành động|Action|Bối cảnh)\s*:',raw,re.I):current['actions'].append(raw);continue
        match=re.match(r'^([^:\n]{1,80})\s*[:：]\s*(.+)$',raw)
        speaker=normalize(match[1]) if match else None;text_part=normalize(match[2] if match else raw)
        if speaker and (speaker.isdigit() or re.search(r'[.!?]',speaker)):speaker=None;text_part=normalize(raw)
        role='narrator' if speaker and key(speaker) in {'người kể','người kể chuyện','narrator','lời kể'} else 'character'
        char_id=identifier(project_id,'chr_',key(speaker)) if speaker else None
        if speaker:characters.setdefault(char_id,{'character_id':char_id,'name':speaker,'role':role})
        line={'line_id':identifier(project_id,'line_',str(number)), 'character_id':char_id,'speaker_name':speaker,'text':text_part,'scene_key':current['scene_key'],'needs_speaker':speaker is None,'role':role}
        current['lines'].append(line['line_id']);lines.append(line)
    if len(scenes)>20:raise WorkflowError('DRAMA_MAX_20_SCENES',400)
    return {'scenes':scenes,'characters':list(characters.values()),'lines':lines,'needs_speaker':[v['line_id'] for v in lines if v['needs_speaker']],
        'actions_are_spoken':False,'narrator_enabled':False,'provider_calls':0}

class ScriptSave(StrictModel):
    revision:StrictInt=Field(ge=1)
    request_key:StrictStr=Field(pattern=r'^[A-Za-z0-9_.:-]{12,128}$')
    text:StrictStr=Field(max_length=20000)
    confirm_characters:StrictBool=False
    narrator_enabled:StrictBool=False
    speaker_assignments:dict[StrictStr,StrictStr]=Field(default_factory=dict)
    character_notes:dict[StrictStr,StrictStr]=Field(default_factory=dict)
    series:StrictStr|None=Field(default=None,max_length=100)
    episode:StrictStr|None=Field(default=None,max_length=100)

def save_script(store,project_id,payload,*,actor_ref,authorization_check=lambda:None):
    try:body=ScriptSave.model_validate(payload).model_dump()
    except (ValueError,TypeError,ValidationError):raise WorkflowError('DRAMA_SCRIPT_REQUEST_INVALID',400) from None
    fingerprint=digest(body);authorization_check()
    with store.transaction() as con:
        con.execute('CREATE TABLE IF NOT EXISTS native_drama_script_writes (project_id TEXT NOT NULL,request_key TEXT NOT NULL,fingerprint TEXT NOT NULL,response TEXT NOT NULL,PRIMARY KEY(project_id,request_key))')
        old=con.execute('SELECT * FROM native_drama_script_writes WHERE project_id=? AND request_key=?',(project_id,body['request_key'])).fetchone()
        if old:
            if old['fingerprint']!=fingerprint:raise WorkflowError('DRAMA_REQUEST_KEY_CONFLICT')
            return {**json.loads(old['response']),'idempotent_replay':True}
        project=store.editable(con,project_id,body['revision']);doc=copy.deepcopy(project['document'])
        if not is_drama(doc):raise WorkflowError('DRAMA_WORKFLOW_REQUIRED',400)
        parsed=parse_script(body['text'],project_id)
        for line in parsed['lines']:
            selected=body['speaker_assignments'].get(line['line_id'])
            if selected:
                character=next((v for v in parsed['characters'] if v['character_id']==selected),None)
                if not character:raise WorkflowError('DRAMA_SPEAKER_SELECTION_REQUIRED',400)
                line.update(character_id=character['character_id'],speaker_name=character['name'],role=character['role'],needs_speaker=False)
        parsed['needs_speaker']=[v['line_id'] for v in parsed['lines'] if v['needs_speaker']]
        record={'schema_version':'native-drama-script.v1','raw_text':body['text'],'parsed':parsed,'characters_confirmed':body['confirm_characters'],
            'character_notes':body['character_notes'],'narrator_enabled':body['narrator_enabled']}
        if any(len(k)>100 or len(v)>500 for k,v in body['character_notes'].items()):raise WorkflowError('DRAMA_CHARACTER_NOTES_INVALID',400)
        if body['confirm_characters']:
            if parsed['needs_speaker']:raise WorkflowError('DRAMA_SPEAKER_SELECTION_REQUIRED',400)
            materialize(doc,parsed,project_id,body['narrator_enabled'])
        doc['drama_script']=record;doc['prompt']=body['text'];doc['input_kind']='script'
        doc['production_workflow'].update(series=body['series'],episode=body['episode'])
        authorization_check();revision=project['revision']+1
        con.execute('UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?',(revision,json.dumps(doc,ensure_ascii=False),now(),project_id))
        store.version(con,project_id);store.event(con,project_id,'drama_script_saved',{'revision':revision,'characters_confirmed':body['confirm_characters'],'provider_calls':0,'actor_ref':actor_ref,'approval_invalidated':True})
        response={'project_id':project_id,'revision':revision,'characters_confirmed':body['confirm_characters'],'needs_speaker':parsed['needs_speaker'],'provider_calls':0,'human_approval_granted':False,'idempotent_replay':False}
        con.execute('INSERT INTO native_drama_script_writes VALUES(?,?,?,?)',(project_id,body['request_key'],fingerprint,json.dumps(response)))
    return response

def materialize(doc,parsed,project_id,narrator_enabled):
    from .shot_adapter import shots as current_shots,snapshot_from_shots,project_projection,validate_document
    from .drama_casting import SCHEMA as CAST_SCHEMA
    from .north_star_quality import canonical_names
    active=[v for v in parsed['lines'] if v['role']!='narrator' or narrator_enabled]
    if not active:raise WorkflowError('DRAMA_ACTIVE_DIALOGUE_REQUIRED',400)
    if len(normalize(' '.join(v['text'] for v in active)))>4000:raise WorkflowError('DRAMA_DIALOGUE_TEXT_TOO_LONG',400)
    old=current_shots(doc);old_by_id={v['shot_id']:v for v in old};values=[];line_to_shot={}
    for index,scene in enumerate(parsed['scenes']):
        shot_id='shot_'+scene['scene_key'][6:];previous=old_by_id.get(shot_id,{})
        speech=canonical_names(normalize(' '.join(v['text'] for v in active if v['scene_key']==scene['scene_key'])))
        action=normalize(' '.join(scene['actions'])) or scene['title']
        values.append({'shot_id':shot_id,'visual':action[:1200],'narration':speech,'subtitle':speech,'on_screen_text':scene['title'],
            'asset_id':previous.get('asset_id'),'duration':previous.get('duration',max(.5,len(speech.split())/2.5)),'requested_duration':None,
            'narration_enabled':bool(speech),'crop_strategy':previous.get('crop_strategy','contain'),'motion':previous.get('motion','none'),
            'source_start':previous.get('source_start',0),'transition':previous.get('transition','cut')})
        for line_id in scene['lines']:line_to_shot[line_id]=shot_id
    projected=project_projection(doc,values)
    state=doc.get('canonical_timeline');snapshot=snapshot_from_shots(values,projected,canvas=state['snapshot'] if state else None)
    projected['canonical_timeline']={'version':state['version']+1 if state else 1,'snapshot':snapshot,'sha256':digest(snapshot)}
    old_cast=doc.get('drama_casting');character_ids={v['character_id'] for v in parsed['characters']}
    casts=[v for v in old_cast['configuration']['casting'] if v['character_id'] in character_ids] if old_cast else []
    configuration={'narrator_enabled':narrator_enabled,'characters':parsed['characters'],'casting':casts,'lines':[
        {'line_id':v['line_id'],'character_id':v['character_id'],'shot_id':line_to_shot[v['line_id']],'text':canonical_names(v['text']),
            'enabled':True,'speed':1.0,'style':'neutral','pause_after_seconds':.15} for v in parsed['lines']]}
    projected['drama_casting']={'schema_version':CAST_SCHEMA,'version':old_cast['version']+1 if old_cast else 1,'configuration':configuration,'sha256':digest(configuration)}
    validate_document(projected);doc.clear();doc.update(projected)
