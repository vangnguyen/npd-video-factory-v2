"""Project association changes preserve original files and source hashes."""
import copy
import json
from .contracts import WorkflowError
from .media import MAX_ASSETS, library_asset, project_assets, scene_bindings, validate_bindings
from .store import now


def mutate(store, project_id, revision, asset_id, action, tags=None, *, asset_ids=None):
    if action not in {'tag','remove','attach'}: raise WorkflowError('ASSET_ASSOCIATION_ACTION_INVALID',400)
    if action=='attach' and (not isinstance(asset_ids,list) or not 1<=len(asset_ids)<=MAX_ASSETS
            or any(not isinstance(a,str) for a in asset_ids) or len(set(asset_ids))!=len(asset_ids)):
        raise WorkflowError('LIBRARY_ASSET_IDS_INVALID',400)
    if action=='tag' and (not isinstance(tags,list) or len(tags)>12 or any(not isinstance(t,str) or not 1<=len(t.strip())<=60 for t in tags)):
        raise WorkflowError('ASSET_TAGS_INVALID',400)
    with store.transaction() as con:
        project=store.editable(con,project_id,revision); doc=project['document']; prior=copy.deepcopy(doc)
        no_change=False
        assets=project_assets(doc); asset=next((a for a in assets if a['id']==asset_id),None)
        if action=='attach':
            # Validate the entire selection under one optimistic transaction before
            # changing the project. No source/original bytes are copied or removed.
            selected=[library_asset(store,a,con=con) for a in asset_ids]
            if any(r['metadata']['rights_confirmed'] is not True for r in selected):
                raise WorkflowError('MEDIA_RIGHTS_CONFIRMATION_REQUIRED',400)
            existing={a['id'] for a in assets}
            incoming=[copy.deepcopy(r['metadata']) for r in selected if r['metadata']['id'] not in existing]
            if len(assets)+len(incoming)>MAX_ASSETS:
                raise WorkflowError('PROJECT_MEDIA_LIMIT_50',400)
            no_change=not incoming
            if incoming:
                doc['scene_media']=scene_bindings(doc)
                doc['assets']=assets+incoming
                associations=copy.deepcopy(doc.get('asset_library_associations',{}))
                for record in selected:
                    a=record['metadata']
                    associations[a['id']]={'origin':'existing_library_asset','asset_sha256':a['sha256'],
                        'source_project_ids':sorted(record['source_projects'])}
                doc['asset_library_associations']=associations
                validate_bindings(doc)
        elif not asset:
            raise WorkflowError('ASSET_NOT_IN_PROJECT',404)
        elif action=='remove':
            if any(b['asset_id']==asset_id for b in scene_bindings(doc)):
                raise WorkflowError('ASSET_USED_REPLACE_BEFORE_REMOVING')
            doc['assets']=[a for a in assets if a['id']!=asset_id]
            if (doc.get('asset') or {}).get('id')==asset_id: doc['asset']=None
            doc.get('asset_library_associations',{}).pop(asset_id,None)
            doc.get('asset_tags',{}).pop(asset_id,None)
        else:
            doc['asset_tags']={**doc.get('asset_tags',{}),asset_id:list(dict.fromkeys(t.strip() for t in tags))}
        if not no_change:
            from .shot_adapter import sync_legacy
            doc=sync_legacy(doc,prior,project_id)
            con.execute('UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?',
                        (revision+1,json.dumps(doc,ensure_ascii=False),now(),project_id))
            store.version(con,project_id)
            store.event(con,project_id,'asset_association_'+action,{'asset_id':asset_id,'asset_ids':asset_ids if action=='attach' else None,
                'revision':revision+1,'original_deleted':False,'approval_invalidated':True})
    return store.get(project_id)
