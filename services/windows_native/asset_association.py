"""Project association changes preserve original files and source hashes."""
import copy
import json
from .contracts import WorkflowError
from .media import project_assets, scene_bindings
from .store import now


def mutate(store, project_id, revision, asset_id, action, tags=None):
    if action not in {'tag','remove'}: raise WorkflowError('ASSET_ASSOCIATION_ACTION_INVALID',400)
    if action=='tag' and (not isinstance(tags,list) or len(tags)>12 or any(not isinstance(t,str) or not 1<=len(t.strip())<=60 for t in tags)):
        raise WorkflowError('ASSET_TAGS_INVALID',400)
    with store.transaction() as con:
        project=store.editable(con,project_id,revision); doc=project['document']; prior=copy.deepcopy(doc)
        assets=project_assets(doc); asset=next((a for a in assets if a['id']==asset_id),None)
        if not asset: raise WorkflowError('ASSET_NOT_IN_PROJECT',404)
        if action=='remove':
            if any(b['asset_id']==asset_id for b in scene_bindings(doc)):
                raise WorkflowError('ASSET_USED_REPLACE_BEFORE_REMOVING')
            doc['assets']=[a for a in assets if a['id']!=asset_id]
            if (doc.get('asset') or {}).get('id')==asset_id: doc['asset']=None
        else:
            doc['asset_tags']={**doc.get('asset_tags',{}),asset_id:list(dict.fromkeys(t.strip() for t in tags))}
        from .shot_adapter import sync_legacy
        doc=sync_legacy(doc,prior,project_id)
        con.execute('UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?',
                    (revision+1,json.dumps(doc,ensure_ascii=False),now(),project_id))
        store.version(con,project_id)
        store.event(con,project_id,'asset_association_'+action,{'asset_id':asset_id,'revision':revision+1,'original_deleted':False,'approval_invalidated':True})
    return store.get(project_id)
