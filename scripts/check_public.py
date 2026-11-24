#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Audit distributable files from Git's index before a commit or release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_SUFFIXES = {
    '.ipa', '.dylib', '.mobileprovision', '.provisionprofile', '.p12', '.pfx',
    '.p8', '.pem', '.key', '.cer', '.bin', '.snapshot', '.sinf', '.supf',
    '.supp', '.sidb', '.zip', '.log',
}
FORBIDDEN_PARTS = {'private', 'models', 'SC_Info', 'DerivedData', 'vendor'}
BINARY_MAGICS = {
    bytes.fromhex(value) for value in (
        'cffaedfe', 'feedfacf', 'cefaedfe', 'feedface', 'cafebabe',
        'bebafeca', 'cafebabf', 'bfbafeca', '504b0304', '4d5a9000',
    )
}
PATTERNS = (
    ('private key', re.compile(r'^-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----', re.M)),
    ('GitHub token', re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b')),
    ('personal home path', re.compile(r'(?:/Users/|/home/)[A-Za-z0-9._-]+/')),
    ('device identifier', re.compile(r'\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16}\b')),
)


def check_blob(name: str, data: bytes) -> list[str]:
    path = PurePosixPath(name)
    problems = []
    if path.is_absolute() or '..' in path.parts or '\\' in name:
        problems.append('unsafe distribution path')
    if path.suffix.lower() in FORBIDDEN_SUFFIXES or any(part in FORBIDDEN_PARTS or part.endswith(('.app', '.appex')) for part in path.parts):
        problems.append('private or generated artifact type')
    if data[:4] in BINARY_MAGICS:
        problems.append('compiled binary or archive')
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        problems.append('distribution files must be UTF-8 source or documentation')
        return problems
    for label, pattern in PATTERNS:
        if pattern.search(text):
            problems.append(label)
    return problems


def git(*arguments: str) -> bytes:
    return subprocess.run(['git', '-C', str(ROOT), *arguments], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def audit(working_tree: bool = False) -> list[str]:
    if working_tree:
        manifest_data = (ROOT / 'public-files.json').read_bytes()
    else:
        manifest_data = git('show', ':public-files.json')
    manifest = json.loads(manifest_data)
    if not isinstance(manifest, list) or not all(isinstance(name, str) for name in manifest) or len(set(manifest)) != len(manifest):
        raise ValueError('public-files.json must be a list of unique relative paths')
    for name in manifest:
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or not name:
            raise ValueError('The distribution manifest contains an unsafe path')
    errors = []
    if working_tree:
        entries = {name: ('100644', None) for name in manifest}
    else:
        entries = {}
        for record in git('ls-files', '--stage', '-z').split(b'\0'):
            if not record:
                continue
            metadata, encoded_name = record.split(b'\t', 1)
            mode, _object_id, stage = metadata.decode().split()
            name = encoded_name.decode('utf-8')
            if stage != '0':
                errors.append(f'{name}: unresolved Git index entry')
            entries[name] = (mode, None)
        for name in sorted(set(entries) - set(manifest)):
            errors.append(f'{name}: not in the distribution allowlist')
        for name in sorted(set(manifest) - set(entries)):
            errors.append(f'{name}: required distribution file is not staged')
    for name in manifest:
        if name not in entries:
            continue
        mode, _ = entries[name]
        if mode not in ('100644', '100755'):
            errors.append(f'{name}: symlinks and submodules are not distributable')
            continue
        if working_tree:
            path = ROOT / name
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT.resolve()):
                errors.append(f'{name}: missing or symlinked distribution file')
                continue
            data = path.read_bytes()
        else:
            data = git('show', ':' + name)
        errors.extend(f'{name}: {problem}' for problem in check_blob(name, data))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--working-tree', action='store_true', help='Check allowlisted source files before staging; the default checks the actual Git index')
    args = parser.parse_args()
    try:
        errors = audit(args.working_tree)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'Audit could not run: {error}', file=sys.stderr)
        return 1
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print('Distribution audit passed: allowlisted text source, licenses, and documentation only.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
