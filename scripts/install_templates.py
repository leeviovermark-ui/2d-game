"""Optional browser build prerequisite: official release with SHA512 verification.

Retained cloud snapshots already contain the two verified Web templates. On a
fresh machine this fetches the upstream template bundle (about 1.2 GB) once.
It never disables TLS, substitutes checksums, or installs non-Web templates.
"""
import hashlib
from pathlib import Path
import tempfile
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '4.6.3'
BASE = f'https://github.com/godotengine/godot/releases/download/{VERSION}-stable/'
NAME = f'Godot_v{VERSION}-stable_export_templates.tpz'
DEST = ROOT / f'.tools/export_templates/{VERSION}.stable'


def main():
    if all((DEST/name).is_file() for name in ['web_debug.zip','web_release.zip']):
        print('Retained Web templates found.')
        return
    checks = urlopen(BASE+'SHA512-SUMS.txt', timeout=60).read().decode().splitlines()
    checksum = next(row.split()[0] for row in checks if row.endswith(NAME))
    with tempfile.TemporaryDirectory(prefix='worldforge-templates-') as temp:
        path = Path(temp)/NAME
        h = hashlib.sha512()
        print('Downloading official Godot Web export prerequisites (1.2 GB bundle)...',flush=True)
        with urlopen(BASE+NAME,timeout=60) as response, path.open('wb') as target:
            for chunk in iter(lambda:response.read(8*1024*1024),b''):
                h.update(chunk)
                target.write(chunk)
        if h.hexdigest() != checksum:
            raise RuntimeError('Official template SHA512 verification failed.')
        DEST.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(path) as archive:
            for name in ['web_debug.zip','web_release.zip','version.txt']:
                (DEST/name).write_bytes(archive.read('templates/'+name))
        print('Verified and installed Web templates.')


if __name__ == '__main__':
    main()
