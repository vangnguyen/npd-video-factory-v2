"""Existing Native asset records projected for canonical source renderers."""
import copy
from .media import project_assets


def canonical_assets(document):
    output=copy.deepcopy(project_assets(document));seen={item['id'] for item in output}
    for music in [*document.get('source_music_assets',[]),*([document['music']] if document.get('music') else [])]:
        if music['id'] in seen:continue
        seen.add(music['id']);output.append({**copy.deepcopy(music),'kind':'audio','has_audio':True,
            'content_type':'audio/wav','canonical_role':'music'})
    return output
