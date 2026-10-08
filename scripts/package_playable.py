"""Build the source + exported-browser download without personal saves or caches."""
from pathlib import Path
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / 'releases/WORLDFORGE-playable.zip'


def main():
    required = ['index.html', 'index.js', 'index.wasm', 'index.pck']
    if any(not (ROOT / 'build/web' / name).is_file() for name in required):
        raise SystemExit('Export the browser client with scripts/export_web.sh first.')
    paths = []
    for directory in ('server', 'shared', 'client', 'assets', 'scripts', 'docs', 'tests', 'deploy', 'build/web'):
        paths.extend((ROOT / directory).rglob('*'))
    paths.extend(ROOT / name for name in ('README.md', 'requirements.txt', 'project.godot',
                                        'export_presets.cfg', '.gitignore', '.dockerignore', 'Play-WORLDFORGE.bat',
                                        'Host-WORLDFORGE-LAN.bat', 'Join-WORLDFORGE-LAN.bat',
                                        'Host-WORLDFORGE-Online.bat'))
    DESTINATION.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(DESTINATION, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(set(paths)):
            if not path.is_file() or path.suffix in ('.pyc', '.uid', '.import') or '__pycache__' in path.parts:
                continue
            archive.write(path, 'WORLDFORGE/' + path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(DESTINATION) as archive:
        if archive.testzip() is not None:
            raise SystemExit('Archive integrity check failed.')
        names = archive.namelist()
        assert not any('/data/' in name or '/.venv/' in name for name in names)
        definitions = json.loads(archive.read('WORLDFORGE/shared/definitions.json'))
        print(f'Packaged {len(names)} files, {len(definitions["items"])} items, '
              f'{len(definitions["recipes"])} recipes; {DESTINATION.stat().st_size:,} bytes.')


if __name__ == '__main__':
    main()
