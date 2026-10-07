"""Explicit offline backup or fresh-destination restore; never starts services."""
import argparse
import json
from pathlib import Path

from services.windows_native.backup import create_backup, restore_backup
from services.windows_native.contracts import WorkflowError
from services.windows_native.pipeline import Config


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    backup = commands.add_parser('backup')
    backup.add_argument('--config', type=Path, required=True)
    backup.add_argument('--output', type=Path, required=True)
    restore = commands.add_parser('restore')
    restore.add_argument('--backup', type=Path, required=True)
    restore.add_argument('--destination', type=Path, required=True)
    restore.add_argument('--expected-sha256', required=True)
    args = parser.parse_args()
    try:
        result = (create_backup(Config.load(args.config), args.output) if args.command == 'backup'
                  else restore_backup(args.backup, args.destination, expected_sha256=args.expected_sha256))
    except WorkflowError as error:
        print(json.dumps({'status': 'REFUSED', 'code': error.code, 'services_started': False}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
