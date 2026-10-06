"""One existing-provider suggestion on an isolated unapproved technical clone."""
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.windows_native.pipeline import Config,REPO
from services.windows_native.store import Store
from services.windows_native.shot_ai_edit import ShotAIEdit
from services.windows_native.contracts import canonical,digest

def main():
    output=REPO/'evidence/post-mvp-roadmap/phase-10/provider-check.json'
    if output.exists():
        print(json.dumps({'status':'ALREADY_RECORDED_NO_REPLAY','receipt':str(output)}));return
    cfg=Config.load('C:/NPD-Video-Factory/phase10-uat/config.json');store=Store(cfg.data_root)
    identity=cfg.data_root/'phase10-technical-project.json'
    if identity.exists(): value=json.loads(identity.read_bytes())
    else:
        source=store.get('b458264408134ba28aa9434a0331681b');project=store.duplicate(source['id'],source['revision'])
        value={'project_id':project['id'],'source_project_id':source['id'],'kind':'CODEX_TECHNICAL_VERIFICATION_NOT_HUMAN_UAT'}
        identity.write_bytes(canonical(value))
    project=store.shot_view(value['project_id']);before=digest(store.get(project['id']));shot=project['shot_timeline']['shots'][0]
    receipt={**value,'at':datetime.now(timezone.utc).isoformat(),'existing_provider':True,'new_credentials':False,
             'project_revision':project['revision'],'human_acceptance':False,'auto_apply':False,'render_calls':0,'tts_calls':0}
    try:
        result=ShotAIEdit(cfg,store).suggest(project['id'],project['revision'],shot['shot_id'],
            'Viết lời đọc shot này ngắn hơn, giữ ý nghĩa và không thêm bất kỳ dữ kiện mới nào.', 'phase10-existing-provider-check-v1')
        receipt.update(status='PASS',result=result,project_unchanged=before==digest(store.get(project['id'])))
    except Exception as error:
        receipt.update(status='FAIL',error_code=getattr(error,'code',type(error).__name__),automatic_retry=False)
    output.write_bytes(canonical(receipt))
    print(json.dumps({'status':receipt['status'],'project_id':project['id'],'project_unchanged':receipt.get('project_unchanged'),
                      'error_code':receipt.get('error_code'),'human_acceptance':False}))

if __name__=='__main__':main()
