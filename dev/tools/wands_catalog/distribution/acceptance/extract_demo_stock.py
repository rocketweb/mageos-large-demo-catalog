"""Extract only numeric/date stock rows from the exact private demo SQL backup."""
import csv
import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path('/opt/comtom/stores/relevance/catalog-enriched-20260913-v2')
TARGET = Path('/opt/comtom/stores/relevance/src/var/catalog-enriched-20260913-v2/stock-before.json')
PIN = '4cd9630880f9102f626b7a545733b6fd4cc3e27851e92dee1484bc646d85ae7a'


def extract(lines):
    columns, rows = [], []
    inside = False
    lines = iter(lines)
    for line in lines:
        if line.startswith('CREATE TABLE `cataloginventory_stock_item` ('):
            inside = True
        elif inside and line.startswith(')'):
            inside = False
        elif inside:
            match = re.match(r'  `([a-z_]+)` ', line)
            if match:
                columns.append(match[1])
        marker = 'INSERT INTO `cataloginventory_stock_item` VALUES'
        if line.startswith(marker):
            if not columns:
                raise ValueError('Stock schema missing')
            parts = [line[len(marker):].strip()]
            size = len(parts[0])
            while not parts[-1].endswith(';'):
                try:
                    part = next(lines).strip()
                except StopIteration as error:
                    raise ValueError('Truncated stock statement') from error
                size += len(part)
                if size > 64 * 1024 * 1024:
                    raise ValueError('Stock statement exceeds limit')
                parts.append(part)
            payload = ''.join(parts).removesuffix(';')
            if not payload.startswith('(') or not payload.endswith(')'):
                raise ValueError('Unexpected stock SQL')
            for group in payload[1:-1].split('),('):
                # No arbitrary SQL, free text, escapes or expressions are accepted.
                if not re.fullmatch(r"(?:NULL|-?\d+(?:\.\d+)?|'[0-9 :.-]+')(?:,(?:NULL|-?\d+(?:\.\d+)?|'[0-9 :.-]+'))*", group):
                    raise ValueError('Unsupported stock literal')
                values = next(csv.reader([group], quotechar="'"))
                if len(values) != len(columns):
                    raise ValueError('Stock column count mismatch')
                rows.append(dict(zip(columns, [None if v == 'NULL' else v for v in values])))
    if not rows or len({r['item_id'] for r in rows}) != len(rows):
        raise ValueError('Missing or duplicate stock rows')
    return rows


def main():
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError('Wrong source root')
    with (ROOT/'before.sql').open('rb') as source:
        assert hashlib.file_digest(source, 'sha256').hexdigest() == PIN
    # Other tables may contain raw binary literals. Stock literals are strictly
    # ASCII-validated above; latin-1 lets unrelated dump bytes pass untouched.
    with (ROOT/'before.sql').open(encoding='latin-1') as source:
        rows = extract(source)
    assert len(rows) == 55044
    with os.fdopen(os.open(TARGET, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'w') as output:
        json.dump(rows, output)
    os.chown(TARGET, 33, 33)
    print(json.dumps({'rows': len(rows), 'source_backup_sha256': PIN}))


if __name__ == '__main__':
    main()
