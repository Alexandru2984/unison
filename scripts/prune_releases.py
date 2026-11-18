#!/usr/bin/env python3
"""Plan (default) or apply retention for releases, runtimes and deploy backups.

Never removes: the release a `current` symlink points to, any --protect path,
the newest --keep-releases releases per root, the newest --keep-backups deploy
backups, or a runtime referenced by a kept API release. Only direct children of
the configured directories are considered and symlinks are never followed.
"""
import argparse
import json
import re
import shutil
from pathlib import Path

STAMP = re.compile(r'^\d{8}T\d{6}Z$')
RUNTIME = re.compile(r'^(venv|ucm)-[0-9a-f]{12}$')


def children(directory: Path):
    if not directory.is_dir():
        return []
    return [p for p in directory.iterdir() if p.is_dir() and not p.is_symlink()]


def plan_releases(root: Path, keep: int, protect: set[Path]):
    items = sorted(children(root / 'releases'), key=lambda p: (p.stat().st_mtime, p.name))
    current = root / 'current'
    pinned = {current.resolve()} if current.is_symlink() else set()
    kept = set(items[-keep:] if keep else []) | {p for p in items if p.resolve() in pinned | protect}
    return [p for p in items if p not in kept], [p for p in items if p in kept]


def runtime_references(release: Path) -> set[Path]:
    """Runtime directories an API release uses: its venv link and engine binary."""
    references = set()
    venv = release / 'venv'
    if venv.is_symlink():
        references.add(venv.resolve())
    env = release / 'runtime.env'
    if env.is_file():
        for line in env.read_text().splitlines():
            if line.startswith('UNISON_BIN='):
                references.add(Path(line.split('=', 1)[1].strip()).parent.resolve())
    return references


def plan(args):
    protect = {Path(p).resolve() for p in args.protect}
    remove_api, keep_api = plan_releases(args.api_root, args.keep_releases, protect)
    remove_site, _ = plan_releases(args.site_root, args.keep_releases, protect)
    used = set().union(*(runtime_references(release) for release in keep_api)) if keep_api else set()
    remove_runtime = [p for p in children(args.runtime_root) if RUNTIME.match(p.name) and p.resolve() not in used]
    backups = sorted(p for p in children(args.backups) if STAMP.match(p.name))
    kept_backups = set(backups[-args.keep_backups:] if args.keep_backups else []) | {p for p in backups if p.resolve() in protect}
    remove_backups = [p for p in backups if p not in kept_backups]
    return {'api_releases': remove_api, 'site_releases': remove_site, 'runtimes': remove_runtime, 'backups': remove_backups}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-root', type=Path, default=Path('/opt/unison-backend'))
    parser.add_argument('--site-root', type=Path, default=Path('/var/www/unison.micutu.com'))
    parser.add_argument('--runtime-root', type=Path, default=Path('/opt/unison-runtime'))
    parser.add_argument('--backups', type=Path, default=Path('/var/backups/unison-backend'))
    parser.add_argument('--keep-releases', type=int, default=8)
    parser.add_argument('--keep-backups', type=int, default=20)
    parser.add_argument('--protect', action='append', default=[], help='A release or backup that must be kept')
    parser.add_argument('--apply', action='store_true', help='Delete the planned paths (default: dry run)')
    args = parser.parse_args(argv)
    if args.keep_releases < 2 or args.keep_backups < 2:
        parser.error('Keep at least two releases and two backups')
    for root in (args.api_root, args.site_root, args.runtime_root, args.backups):
        if not root.is_absolute():
            parser.error(f'{root} must be an absolute path')
    removal = plan(args)
    if args.apply:
        allowed = {'api_releases': args.api_root / 'releases', 'site_releases': args.site_root / 'releases',
                   'runtimes': args.runtime_root, 'backups': args.backups}
        for group, paths in removal.items():
            for path in paths:
                if path.parent != allowed[group] or path.is_symlink():
                    raise SystemExit(f'Refusing to remove unexpected path {path}')
                shutil.rmtree(path)
    print(json.dumps({'applied': args.apply, **{k: [p.name for p in v] for k, v in removal.items()}}, indent=2))


if __name__ == '__main__':
    main()
