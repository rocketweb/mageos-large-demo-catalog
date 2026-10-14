"""Build a deterministic standalone Python installer artifact; never publish it."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
FILES = ('catalog.py', 'catalog_runtime.php', 'github_download.py', 'download.py', 'release.py')


def build(output):
    output = Path(output)
    with output.open('xb') as stream:
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            contents = {name: (HERE / name).read_bytes() for name in FILES}
            contents['LICENSE.txt'] = (HERE.parents[3] / 'LICENSE').read_bytes()
            contents['NOTICE.md'] = (HERE.parents[3] / 'NOTICE.md').read_bytes()
            contents['__main__.py'] = b'from catalog import main\nraise SystemExit(main())\n'
            for name, data in sorted(contents.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
    with output.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    result = {'path': output.name, 'bytes': output.stat().st_size, 'sha256': sha}
    output.with_suffix('.sha256').write_text(result['sha256'] + '  ' + output.name + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(json.dumps(build(args.output), sort_keys=True))


if __name__ == '__main__':
    main()
