"""Measured line/speaker subtitle windows; no ASR, word alignment or human acceptance claims."""
import json,math
from .backup import guard
from .contracts import WorkflowError,digest,file_sha,write_json

SCHEMA='native-dialogue-qc.v1'
CODE='DRAMA_DIALOGUE_QC_FAILED'
TOLERANCE=.003

def failed(document,directory,reason):
    write_json(directory/'dialogue-qc.json',{'schema_version':SCHEMA,'document_sha256':digest(document),'status':'failed_qc',
        'reasons':[reason],'human_voice_uat_complete':False,'word_alignment_claimed':False})
    raise WorkflowError(CODE)

def evaluate(document,directory,captions):
    from .dialogue_runtime import expected_profile
    from .export_encoder import output_options
    report={'schema_version':SCHEMA,'document_sha256':digest(document),'timeline_sha256':document['canonical_timeline']['sha256'],
        'status':'passed','reasons':[],'cue_windows':[],'timing_basis':'measured_dialogue_activity_windows_no_word_alignment',
        'tolerance_seconds':TOLERANCE,'speech_semantics_verified':False,'human_voice_uat_complete':False,'word_alignment_claimed':False}
    try:
        def read(name):
            path=guard(directory/name,exists=True)
            if path.stat().st_size>4*1024*1024:raise ValueError()
            return json.loads(path.read_bytes())
        placed=read('render-voice.json');original=read('voice.json');state=document['canonical_timeline']['snapshot']
        if (placed.get('profile_sha256')!=expected_profile(document) or placed.get('canonical_timeline_sha256')!=document['canonical_timeline']['sha256']
            or placed.get('source_voice_sha256')!=original.get('audio_sha256') or placed.get('sample_preserving_placement') is not True):raise ValueError()
        units=placed['units'];by_line={v['line_id']:v for v in units}
        if not units or len(by_line)!=len(units):raise ValueError()
        options=output_options(document)
        if options['audio_included']:
            active=[c for t in state['tracks'] if t['type']=='audio' and t['kind']=='voice' and not t['disabled'] and not t['muted']
                for c in t['clips'] if not c['disabled'] and c['volume']>0]
            if len(active)!=1 or active[0]['metadata'].get('narrated_generated_voice') is not True:
                report['reasons'].append('approved_dialogue_voice_missing_or_unbound_voice_overlap')
        for cue in captions:
            unit=by_line.get(cue.get('dialogue_line_id'))
            if unit is None or any(cue.get(a)!=unit.get(b) for a,b in (('speaker_id','character_id'),('speaker_name','speaker_name'),('voice_id','voice_id'),('voice_version','voice_version'))):
                report['reasons'].append('subtitle_speaker_or_line_binding_changed');continue
            start,end=cue.get('start'),cue.get('end');a,b=unit['activity_start_seconds'],unit['activity_end_seconds']
            if (any(type(v) not in (int,float) or not math.isfinite(v) for v in (start,end,a,b)) or not 0<=a<b
                or not start<end or start<a-TOLERANCE or end>b+TOLERANCE):
                report['reasons'].append('subtitle_outside_measured_speaker_window');continue
            report['cue_windows'].append({'cue_id':cue.get('cue_id'),'line_id':unit['line_id'],'speaker_id':unit['character_id'],
                'start_seconds':round(start,6),'end_seconds':round(end,6),'audio_activity_start_seconds':round(a,6),'audio_activity_end_seconds':round(b,6)})
        if not captions:report['reasons'].append('dialogue_captions_missing')
        report.update(placed_voice_metadata_sha256=file_sha(directory/'render-voice.json'),source_voice_sha256=original['audio_sha256'],captions_sha256=digest(captions))
    except (OSError,KeyError,ValueError,TypeError,WorkflowError):report['reasons'].append('measured_dialogue_source_missing_or_changed')
    report['reasons']=sorted(set(report['reasons']));report['status']='failed_qc' if report['reasons'] else 'passed'
    return report

def inspect(document,directory,captions):
    result=evaluate(document,directory,captions);write_json(directory/'dialogue-qc.json',result)
    if result['status']!='passed':raise WorkflowError(CODE)
    return result

def verify(document,directory,manifest):
    if document.get('drama_casting') is None:return None
    try:
        source=guard(directory/'dialogue-qc.json',exists=True)
        if source.stat().st_size>4*1024*1024 or manifest.get('dialogue_qc_sha256')!=file_sha(source):raise ValueError()
        saved=json.loads(source.read_bytes());current=evaluate(document,directory,manifest['captions'])
        if saved!=current or current['status']!='passed':raise ValueError()
    except (OSError,KeyError,ValueError,TypeError,WorkflowError):raise WorkflowError(CODE) from None
    return current
