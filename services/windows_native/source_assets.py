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


def used_timeline_asset_ids(timeline):
    # Caption clips render as text. Uploaded cue/ASR origins still require rights.
    return {clip.get('metadata',{}).get('native_asset_id') for track in timeline['tracks'] if not track['disabled']
        for clip in track['clips'] if not clip['disabled'] and (clip.get('asset_id') or
            clip['kind']=='subtitle' and clip.get('metadata',{}).get('native_media_import_id'))}
