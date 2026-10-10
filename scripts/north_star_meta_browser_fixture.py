"""Explicit disposable mock fixture for readonly Studio browser inspection."""
import argparse,json,tempfile,time
from pathlib import Path
from services.windows_native.tests.test_meta_runtime_http import MetaRuntimeHTTPTests

LOG=Path(r'C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007')
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();out=args.output.absolute()
    if out.parent!=LOG or not out.name.startswith('meta-studio-browser-n') or out.exists():raise ValueError('Fresh owned browser evidence output required')
    out.mkdir();case=MetaRuntimeHTTPTests('test_runtime_signed_review_separate_media_selection_and_async_receipt_use_one_worker');case.setUp()
    assert case.folder.resolve().parent==Path(tempfile.gettempdir()).resolve() and case.root.resolve()==case.folder.resolve()/'state'
    try:
        original=case.server.store.get(case.c.project['id']);case.review();media=case.deliver();case.bind(media)
        safe={'scope':'readonly_browser_on_disposable_signed_mock_owner_meta_s3_nonplayable_media_fixture','origin':'http://127.0.0.1:'+str(case.server.server_port),
            'project_id':original['id'],'workspace_id':case.workspace,'publication_id':case.value['publication_id'],'worker_started':False,'real_provider_calls':0,'paid_operations':0,'owner_uat':False,'accepted_media_generated':False}
        (out/'metadata.json').write_text(json.dumps(safe,indent=2)+'\n',encoding='utf-8',newline='\n')
        print(json.dumps({**safe,'explicit_mock_human_login_token':case.raw}),flush=True)
        deadline=time.monotonic()+900
        while not (out/'stop.signal').is_file() and time.monotonic()<deadline:time.sleep(0.25)
        assert (out/'stop.signal').read_text(encoding='utf-8').strip()=='stop'
        assert case.server.store.get(original['id'])==original and case.pipeline.calls==0
        (out/'shutdown.json').write_text(json.dumps({**safe,'fixture_stopped':True,'canonical_project_unchanged':True,'publication_mutations_by_browser':len(case.c.mutations),'manual_old_data_deleted':False},indent=2)+'\n',encoding='utf-8',newline='\n')
    finally:case.tearDown()
if __name__=='__main__':main()
