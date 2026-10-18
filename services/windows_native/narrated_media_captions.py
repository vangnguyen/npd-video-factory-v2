"""Closed canonical subtitle styles -> ASS; provider/human text cannot add tags.

Tag syntax: https://aegisub.org/docs/latest/ass_tags/ . Actual libass pixels,
timestamps and bounds are still inspected by the existing storyboard Full QC.
"""
import json,re,shutil
from pathlib import Path
from PIL import ImageFont
from .contracts import WorkflowError,file_sha,write_json
from .narrated_media_timeline import enabled
from .source_media_tracks import _check_captions
from app.timeline_models import TimelineSnapshot
from app.production_models import SubtitleStyle
from app.production_logic import derive_subtitle_cues

FONT_ROOT=Path(__file__).with_name('fonts')
FONT_SHA={'NotoSans.ttf':'bfb7bb691513f12e734dc346c03a03f784912432d7e3fa8e56efcf906fe86b3d',
 'NotoSansDisplay.ttf':'deaa68141fa5ad21bd17d7c11fa79183ceda19b32e40ff5c33874d42f3636dde'}

def colour(value,alpha=0):
    value=value.lstrip('#');return f'&H{alpha:02X}{value[4:6]}{value[2:4]}{value[0:2]}'.upper()

def render(document,directory,width,height,safe_rectangle):
    if not enabled(document):return None
    from .pipeline import ass_time,ass_escape
    snapshot=TimelineSnapshot.model_validate(document['canonical_timeline']['snapshot']);_check_captions(snapshot)
    style=SubtitleStyle.model_validate(snapshot.metadata['subtitle_style']);cues=derive_subtitle_cues(snapshot)
    fonts=directory/'fonts';fonts.mkdir(exist_ok=False)
    chosen='NotoSansDisplay.ttf' if style.font_family=='Noto Sans Display' else 'NotoSans.ttf'
    for name,sha in FONT_SHA.items():
        if file_sha(FONT_ROOT/name)!=sha:raise WorkflowError('NARRATED_SUBTITLE_FONT_CHANGED')
        shutil.copyfile(FONT_ROOT/name,fonts/name)
    font=ImageFont.truetype(str(fonts/chosen),style.font_size)
    try:font.set_variation_by_name('ExtraBold' if style.font_weight>=800 else 'Bold' if style.font_weight>=600 else 'Regular')
    except (ValueError,OSError):raise WorkflowError('NARRATED_SUBTITLE_FONT_VARIATION_UNAVAILABLE') from None
    left,top,right,bottom=safe_rectangle;available=right-left-40;events=[];captions=[]
    primary=colour(style.text_color);highlight=colour(style.highlight_color)
    primary_tag='&H'+primary[-6:]+'&';highlight_tag='&H'+highlight[-6:]+'&'
    background=colour(style.background_color,round(255*(1-style.background_opacity)))
    header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Subtitle,{style.font_family},{style.font_size},{primary},{highlight},{background},{background},{style.font_weight},0,0,0,100,100,0,0,3,8,0,5,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    def lines_for(text):
        lines=[];line=[]
        for word in text.split():
            if font.getlength(word)>available:raise WorkflowError('SOURCE_MEDIA_TRACK_CAPTION_LAYOUT_INVALID',400)
            if line and font.getlength(' '.join([*line,word]))>available:lines.append(line);line=[]
            line.append(word)
        if line:lines.append(line)
        if len(lines)>style.max_lines:raise WorkflowError('SOURCE_MEDIA_TRACK_CAPTION_LAYOUT_INVALID',400)
        return lines
    speaker_mapping=[];delivery_cues=[]
    for cue in cues:
        speaker=None;display_text=cue.text
        if document.get('drama_casting') is not None:
            matches=[c for t in snapshot.tracks if t.kind=='subtitles' and not t.disabled for c in t.clips if not c.disabled
                and c.timeline_start-.002<=cue.start_seconds and c.timeline_start+c.duration+.002>=cue.end_seconds]
            if len(matches)!=1 or not all(matches[0].metadata.get(k) for k in ('speaker_id','speaker_name','dialogue_line_id')):
                raise WorkflowError('DRAMA_SUBTITLE_SPEAKER_MAPPING_REQUIRED',400)
            source=matches[0].metadata;speaker={k:source[k] for k in ('speaker_id','speaker_name','dialogue_line_id','voice_id','voice_version')}
            speaker_mapping.append({'cue_id':cue.cue_id,**speaker});display_text=source['speaker_name']+': '+cue.text
            if style.animation in {'word_by_word','word_highlight','karaoke'}:raise WorkflowError('DRAMA_SPEAKER_WORD_ALIGNMENT_UNAVAILABLE',400)
        pieces=lines_for(display_text);height_estimate=len(pieces)*style.font_size*1.45
        if style.position=='top':y=top+height_estimate/2+20
        elif style.position=='center':y=(top+bottom)/2
        else:y=bottom-height_estimate/2-20
        prefix=f'{{\\pos({round((left+right)/2)},{round(y)})}}'
        duration=round((cue.end_seconds-cue.start_seconds)*1000)
        if style.animation=='fade':prefix+=f'{{\\fad({min(120,duration//4)},{min(100,duration//4)})}}'
        elif style.animation=='pop':prefix+=f'{{\\fscx85\\fscy85\\t(0,{min(120,duration//4)},\\fscx100\\fscy100)}}'
        if style.animation in {'word_highlight','word_by_word','karaoke'}:
            if not cue.words:raise WorkflowError('WORD_ALIGNMENT_UNAVAILABLE',400)
            # Never align words by guessing their position in arbitrary text.
            if [w.text for w in cue.words]!=cue.text.split():raise WorkflowError('WORD_ALIGNMENT_UNAVAILABLE',400)
            breaks=set();count=0
            for line in pieces[:-1]:count+=len(line);breaks.add(count)
            rendered=[];clock=0
            for i,word in enumerate(cue.words):
                a=max(0,round((word.start_seconds-cue.start_seconds)*1000));b=min(duration,round((word.end_seconds-cue.start_seconds)*1000))
                text=ass_escape(word.text);join='\\N' if i in breaks else ' ' if i else ''
                if style.animation=='karaoke':
                    start=round(a/10);end=round(b/10)
                    gap=f'{{\\k{start-clock}}}\u200b' if start>clock else ''
                    tags=f'{{\\1c{highlight_tag}\\2c{primary_tag}\\kf{max(1,end-start)}}}';clock=end
                    rendered.append(join+gap+tags+text)
                elif style.animation=='word_by_word':
                    hold=round(((cue.words[i+1].start_seconds if i+1<len(cue.words) else cue.end_seconds)-cue.start_seconds)*1000)
                    tags=f'{{\\alpha&HFF&\\t({max(0,a-1)},{a},\\alpha&H00&)\\t({hold},{min(duration,hold+1)},\\alpha&HFF&)}}'
                    rendered.append(join+tags+text)
                else:
                    tags=f'{{\\1c{primary_tag}\\t({max(0,a-1)},{a},\\1c{highlight_tag})\\t({b},{min(duration,b+1)},\\1c{primary_tag})}}'
                    rendered.append(join+tags+text)
            text=''.join(rendered)
        else:
            def plain(text):
                if style.animation!='keyword_highlight' or not style.keywords:return ass_escape(text)
                pattern=re.compile('('+'|'.join(re.escape(k) for k in sorted(style.keywords,key=len,reverse=True))+')',re.IGNORECASE)
                parts=[];cursor=0
                for match in pattern.finditer(text):
                    parts.extend([ass_escape(text[cursor:match.start()]),f'{{\\1c{highlight_tag}}}'+ass_escape(match[0])+f'{{\\1c{primary_tag}}}']);cursor=match.end()
                parts.append(ass_escape(text[cursor:]));return ''.join(parts)
            text='\\N'.join(plain(' '.join(line)) for line in pieces)
        events.append(f"Dialogue: 0,{ass_time(cue.start_seconds)},{ass_time(cue.end_seconds)},Subtitle,,0,0,0,,{prefix}{text}")
        captions.append({'start':cue.start_seconds,'end':cue.end_seconds,'text':display_text,'cue_id':cue.cue_id,
            **(speaker or {}),
            'style_ref':style.template_ref,'animation':style.animation,'words':[w.model_dump(mode='json') for w in cue.words],
            'timing_source':'canonical_caption_bounds_words_only_when_source_evidence_exists'})
        if speaker:delivery_cues.append({'start':cue.start_seconds,'end':cue.end_seconds,'text':display_text,**speaker})
    (directory/'subtitles.ass').write_text(header+'\n'.join(events)+'\n',encoding='utf-8')
    write_json(directory/'subtitles.json',{'cues':[c.model_dump(mode='json') for c in cues],'style':style.model_dump(mode='json'),
        'actual_renderer':'local-ffmpeg-libass','font_sha256':FONT_SHA,'word_alignment_inferred':False,'source_media_mutated':False,
        **({'speaker_mapping':speaker_mapping,'delivery_cues':delivery_cues} if speaker_mapping else {})})
    return captions
