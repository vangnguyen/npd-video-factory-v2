"""Versioned source canvas/caption choices over the same Native timeline."""
from typing import Literal
from pydantic import Field,model_validator
from .auto_edit_timeline import _cas,_save,view
from .contracts import WorkflowError
from app.models import StrictModel
from app.timeline_models import TimelineSnapshot
from app.production_models import SubtitleStyle
from app.production_logic import derive_subtitle_cues,validate_subtitles,ProductionContractError
from app.subtitle_templates import load_templates


class Settings(StrictModel):
    expected_version:int=Field(ge=1,strict=True)
    aspect_ratio:Literal['9:16','16:9','1:1','4:5']|None=None
    subtitle_template_ref:str|None=Field(default=None,max_length=100)
    keywords:list[str]=Field(default_factory=list,max_length=30)
    @model_validator(mode='after')
    def selected(self):
        if self.aspect_ratio is None and self.subtitle_template_ref is None:raise ValueError('choice required')
        if self.keywords and not self.subtitle_template_ref:raise ValueError('caption template required')
        return self


def configure(store,project_id,revision,body):
    try:payload=Settings.model_validate(body)
    except ValueError:raise WorkflowError('AUTO_EDIT_TIMELINE_REQUEST_INVALID',400) from None
    with store.transaction() as con:
        project=store.editable(con,project_id,revision);state=_cas(project,payload.expected_version)
        snapshot=TimelineSnapshot.model_validate(state['snapshot'])
        if payload.aspect_ratio:
            snapshot.width,snapshot.height={'9:16':(1080,1920),'16:9':(1920,1080),'1:1':(1080,1080),'4:5':(1080,1350)}[payload.aspect_ratio]
            snapshot.aspect_ratio=payload.aspect_ratio
        if payload.subtitle_template_ref:
            template=next((item for item in load_templates() if item['template_ref']==payload.subtitle_template_ref),None)
            if template is None:raise WorkflowError('SUBTITLE_TEMPLATE_UNKNOWN',400)
            if any(track.locked for track in snapshot.tracks if track.kind=='subtitles'):
                raise WorkflowError('AUTO_EDIT_SUBTITLE_TRACK_LOCKED',400)
            try:style=SubtitleStyle.model_validate({**template['style'],'keywords':payload.keywords})
            except ValueError:raise WorkflowError('SUBTITLE_TEMPLATE_KEYWORDS_INVALID',400) from None
            try:validate_subtitles(derive_subtitle_cues(snapshot),style,snapshot.duration_seconds)
            except ProductionContractError as error:
                code='WORD_ALIGNMENT_UNAVAILABLE' if 'WORD_ALIGNMENT' in str(error) else 'SUBTITLE_LAYOUT_OVERFLOW'
                raise WorkflowError(code,400) from None
            snapshot.metadata['subtitle_style']=style.model_dump(mode='json')
        _save(store,con,project,snapshot,'auto_edit_source_settings_saved')
    return view(store,project_id)
