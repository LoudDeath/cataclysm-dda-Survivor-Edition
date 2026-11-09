"""Restore verified local dependency source cache and the exact patched vcpkg ports."""
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / 'assets/third-party-source/dependencies/MANIFEST.json').read_text(encoding='utf-8'))
    downloads = ROOT / '.tools/vcpkg-downloads'
    overlays = ROOT / '.tools/edition-ports'
    downloads.mkdir(parents=True, exist_ok=True)
    for package in manifest['packages']:
        port = ROOT / package['port_archive']
        assert hashlib.sha256(port.read_bytes()).hexdigest() == package['port_sha256'], package['name']
        target = overlays / package['name']
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(port) as archive:
            for member in archive.getmembers():
                destination = (target / member.name).resolve()
                if not destination.is_relative_to(target.resolve()) or not (member.isfile() or member.isdir()):
                    raise RuntimeError('Unsupported port member: ' + member.name)
                if member.isfile():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as source, destination.open('wb') as output:
                        shutil.copyfileobj(source, output)
        for resource in package['resources']:
            source = ROOT / resource['path']
            with source.open('rb') as stream:
                assert hashlib.file_digest(stream, 'sha512').hexdigest() == resource['sha512'], package['name']
            url = resource['source_url']
            parsed = urllib.parse.urlparse(url)
            if parsed.netloc == 'github.com':
                owner, repo, _, ref = parsed.path.strip('/').split('/', 3)
                filename = owner + '-' + repo + '-' + ref.removesuffix('.tar.gz').replace('/', '_-') + '.tar.gz'
            elif '/-/archive/' in url:
                repo_path, ref_path = parsed.path.strip('/').split('/-/archive/', 1)
                filename = repo_path.replace('/', '-') + '-' + ref_path.split('/')[0] + '.tar.gz'
            else:
                filename = parsed.path.rsplit('/', 1)[1]
            shutil.copyfile(source, downloads / filename)
    print(f'Restored verified source cache and {len(manifest["packages"])} exact overlay ports; no compilation performed')


if __name__ == '__main__':
    main()
