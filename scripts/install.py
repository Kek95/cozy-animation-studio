#!/usr/bin/env python3
"""Install the skill locally, preserving an existing installation on replacement."""
import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

NAME = 'cozy-animation-studio'
PAYLOAD = ('SKILL.md', 'agents', 'assets', 'references', 'scripts', 'LICENSE', 'README.md', 'requirements-dev.txt')


def default_destination():
    return Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'skills' / NAME


def install(source, destination, replace=False, dry_run=False):
    source = Path(source).resolve()
    raw_destination = Path(destination).expanduser()
    if raw_destination.is_symlink():
        raise ValueError('Destination is a symlink; choose an ordinary directory.')
    destination = raw_destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Source and destination must be separate directory trees.')
    for name in PAYLOAD:
        if not (source / name).exists():
            raise ValueError(f'Incomplete source: missing {name}.')
    if destination.exists() and (not replace or not destination.is_dir()):
        raise ValueError('Destination exists; use --replace for an existing skill directory.')
    if destination.exists() and not (destination / 'SKILL.md').is_file():
        raise ValueError('Destination is not a skill directory; refusing to replace it.')
    result = {'destination': str(destination), 'dry_run': dry_run, 'backup': None}
    if dry_run:
        result['action'] = 'backup_then_install' if destination.exists() else 'install'
        return result
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f'.{NAME}-', dir=destination.parent))
    backup = None
    try:
        for name in PAYLOAD:
            item = source / name
            if item.is_dir():
                shutil.copytree(item, stage / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            else:
                shutil.copy2(item, stage / name)
        if destination.exists():
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            # Use a hidden backup folder to separate old versions from active skills.
            backup_root = destination.parent / '.cozy-animation-backups'
            backup_root.mkdir(exist_ok=True)
            backup = backup_root / f'{destination.name}-{timestamp}'
            destination.rename(backup)
        try:
            stage.rename(destination)
        except OSError:
            if backup is not None:
                backup.rename(destination)
            raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    result.update(action='installed', backup=str(backup) if backup else None)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dest', type=Path, default=default_destination())
    parser.add_argument('--replace', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        result = install(Path(__file__).resolve().parents[1], args.dest, args.replace, args.dry_run)
    except (ValueError, OSError) as exc:
        parser.exit(1, f'Install failed: {exc}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
