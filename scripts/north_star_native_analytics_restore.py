"""Fresh checksum-anchored Native backup/restore rehearsal over explicit owned fixtures."""
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.pipeline import Config
from services.windows_native.contracts import file_sha
from north_star_native_analytics_contract import read


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path,required=True);parser.add_argument('--restore-root',type=Path,required=True)
    parser.add_argument('--project',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    source=args.data_root.resolve();destination=args.restore_root.resolve();out=args.output.resolve()
    if source.parent!=Path('C:/') or not source.name.startswith('vf-native-fixture-publication-') or not source.is_dir():raise ValueError('Owned source fixture required')
    if destination.parent!=Path('C:/') or not destination.name.startswith('vf-native-fixture-analytics-restore-') or destination.exists():raise ValueError('Fresh owned restore destination required')
    out.mkdir(parents=True,exist_ok=False);expected=read(source,args.project)
    if len(expected['history']['items'])!=6 or len(expected['overview']['items'])!=4:raise ValueError('Completed explicit analytics fixture required')
    absent=source.parent/(source.name+'-absent-secrets');config=Config(data_root=source,secret_file=absent/'absent-openai.env',assemblyai_secret_file=absent/'absent-asr.dpapi')
    backup=create_backup(config,out/'native-state-backup.zip');restored=restore_backup(out/'native-state-backup.zip',destination,expected_sha256=backup['sha256'])
    observed=json.loads(subprocess.check_output([sys.executable,str(ROOT/'scripts/north_star_native_analytics_contract.py'),
        '--read-root',str(destination),'--project',args.project],timeout=60))
    assert observed==expected and read(source,args.project)==expected
    finals={path.relative_to(source).as_posix():file_sha(path) for path in (source/'jobs').rglob('final.mp4')}
    assert finals and all(file_sha(destination/name)==sha for name,sha in finals.items())
    for name,value in [('backup-receipt.json',backup),('restore-receipt.json',restored),('restored-state.json',observed),('contract.json',{
        'status':'PASS','source':str(source),'fresh_restore_destination':str(destination),'database_history_exact':True,
        'publication_history_exact':True,'analytics_syncs':6,'metric_snapshots':5,'distinct_publications':4,
        'source_state_unchanged':True,'final_media_hashes':finals,'source_is_explicit_synthetic_fixture':True,
        'secrets_included':False,'real_provider_calls':0,'services_started':False,'production_deployed':False,
        'all_absolute_render_paths_rebound':False,'render_after_restore_tested':False,'production_recovery_accepted':False})]:
        with (out/name).open('x',encoding='utf-8') as file:json.dump(value,file,ensure_ascii=False,indent=2)
    print(json.dumps({'status':'PASS','output':str(out),'database_history_exact':True,'fresh_process_restore':True}))


if __name__=='__main__':main()
