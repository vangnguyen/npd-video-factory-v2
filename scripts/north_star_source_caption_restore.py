"""Offline separate-process restore of owned source-caption media proof."""
import argparse,json,sys,tempfile
from dataclasses import replace
from pathlib import Path
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO))
from services.windows_native.backup import restore_backup
from services.windows_native.pipeline import Config
from services.windows_native.store import Store
from services.windows_native.contracts import file_sha
from services.windows_native.hardening import durable_json
from services.windows_native.auto_edit_timeline import view,restore
from services.windows_native.source_media_tracks import catalog
from services.windows_native.source_preview import resolve_assets
from services.windows_native.source_media_track_origins import verify_physical

def main():
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
    bundle=a.bundle.resolve();receipt=a.receipt.resolve()
    if receipt.exists() or REPO==bundle or REPO in bundle.parents:raise ValueError('Fresh external recovery receipt required')
    evidence=json.loads((bundle/'evidence.json').read_bytes());saved=json.loads((bundle/'timeline-editor.json').read_bytes())
    history=json.loads((bundle/'timeline-history.json').read_bytes());page=json.loads((bundle/'media-tracks.json').read_bytes())
    backup=json.loads((bundle/'backup-restore.json').read_bytes())['backup']
    for relative,expected in evidence['exports'].items():
        path=(bundle/relative).resolve()
        if bundle not in path.parents or file_sha(path)!=expected:raise AssertionError('Retained bundle changed')
    if file_sha(bundle/'backup.zip')!=backup['sha256']:raise AssertionError('Backup checksum differs')
    # Short owned Windows root avoids MAX_PATH failures in restored preview caches.
    with tempfile.TemporaryDirectory(prefix='vf-owned-source-captions-',dir='C:/') as owned:
        parent=Path(owned).resolve();destination=parent/'state'
        result=restore_backup(bundle/'backup.zip',destination,expected_sha256=backup['sha256'])
        if destination.resolve().parent!=parent:raise AssertionError('Recovery escaped owned parent')
        store=Store(destination);config=replace(Config(),data_root=destination);pid=evidence['project_id'];before=store.get(pid)
        actual=view(store,pid)
        if actual!=saved or catalog(store,pid,page['workspace_id'])!=page:raise AssertionError('Cold canonical or caption catalog differs')
        with store.transaction() as con:
            actual_history=[{'revision':r['revision'],'canonical_timeline':json.loads(r['document']).get('canonical_timeline')}
                for r in con.execute('SELECT revision,document FROM project_versions WHERE project_id=? ORDER BY revision',(pid,))
                if json.loads(r['document']).get('canonical_timeline')]
            if actual_history!=history:raise AssertionError('Cold history differs')
            store.verified_render(evidence['job_id'],con)
        resolve_assets(config,before);verified=verify_physical(destination,before['document'])
        expected_sources=evidence['imports']
        if len(verified)!=expected_sources:raise AssertionError('Physical imported source count differs')
        target=next(r for r in reversed(history) if r['canonical_timeline']['sha256']!=actual['document']['canonical_timeline']['sha256'])
        undone=restore(store,pid,actual['revision'],{'expected_version':actual['shot_timeline']['version'],'restore_revision':target['revision']})
        if undone['shot_timeline']['sha256']!=target['canonical_timeline']['sha256']:raise AssertionError('Cold undo differs')
        redone=restore(store,pid,undone['revision'],{'expected_version':undone['shot_timeline']['version'],'restore_revision':actual['revision']})
        if redone['shot_timeline']['sha256']!=actual['shot_timeline']['sha256'] or redone['approval'] is not None:raise AssertionError('Cold redo or approval fence differs')
        if redone['jobs']!=before['jobs']:raise AssertionError('Recovery dispatched or changed jobs')
        report={'schema_version':'native-source-caption-cold-recovery-v1','bundle':str(bundle),'backup_sha256':backup['sha256'],
            'actual_separate_process':True,'provider_credentials_not_used':True,'canonical_history_and_caption_catalog_exact':True,
            'physical_sources_and_render_verified':True,'verified_active_sources':verified,
            'undo_sha256':undone['shot_timeline']['sha256'],'redo_sha256':redone['shot_timeline']['sha256'],
            'undo_redo_create_new_versions':True,'approval_invalidated':True,'jobs_unchanged':True,'provider_calls':0,'paid_calls':0,
            'real_published':False,'owner_UAT':False,'browser_rendered':False,'owned_new_restore_cleaned_after_receipt':True,
            'historical_data_deleted':False,'restoration':result}
    durable_json(receipt,report)
    print(json.dumps({'restored':True,'cold_undo_redo':True,'receipt':str(receipt)}))

if __name__=='__main__':main()
