# SPDX-License-Identifier: GPL-3.0-only
"""Exercise the source distribution boundary without account or app fixtures."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/check_public.py'
SPEC = importlib.util.spec_from_file_location('check_public', SCRIPT)
public = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(public)


class PublicDistributionTests(unittest.TestCase):
    def test_rejects_app_signing_and_enrollment_artifacts(self):
        for name in ('App.ipa', 'profile.mobileprovision', 'identity.p12', 'models/license.bin', 'Payload/App.app/Info.plist'):
            with self.subTest(name=name):
                self.assertTrue(public.check_blob(name, b'example'))

    def test_binary_cannot_hide_under_source_extension(self):
        self.assertTrue(public.check_blob('patch.py', bytes.fromhex('cffaedfe') + bytes(32)))

    def test_personal_values_are_flagged_without_printing_them(self):
        home_path = '/' + 'Users' + '/person/Documents/file'
        device = '1234ABCD' + '-' + '1234567890ABCDEF'
        token = 'gh' + 'p_' + 'A' * 36
        for content in (home_path, device, token):
            with self.subTest():
                errors = public.check_blob('reference.md', content.encode())
                self.assertTrue(errors)
                self.assertNotIn(content, '\n'.join(errors))

    def test_normal_source_and_upstream_revision_are_allowed(self):
        data = b'# Source attribution\nhttps://github.com/example/project\n' + b'a' * 40
        self.assertEqual([], public.check_blob('NOTICE.md', data))

    def make_repository(self, root):
        subprocess.run(['git', 'init', str(root)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (root / 'public-files.json').write_text(json.dumps(['public-files.json', 'README.md']))
        (root / 'README.md').write_text('Source documentation.\n')
        subprocess.run(['git', '-C', str(root), 'add', 'public-files.json', 'README.md'], check=True)

    def test_index_audit_rejects_files_outside_allowlist(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repository(root)
            with patch.object(public, 'ROOT', root):
                self.assertEqual([], public.audit())
                (root / 'extra.txt').write_text('Unexpected distribution file.\n')
                subprocess.run(['git', '-C', str(root), 'add', 'extra.txt'], check=True)
                self.assertIn('extra.txt: not in the distribution allowlist', public.audit())

    def test_index_audit_reads_staged_content_after_working_copy_is_cleaned(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repository(root)
            (root / 'README.md').write_text('/' + 'Users' + '/person/private-input\n')
            subprocess.run(['git', '-C', str(root), 'add', 'README.md'], check=True)
            (root / 'README.md').write_text('Clean working copy.\n')
            with patch.object(public, 'ROOT', root):
                self.assertIn('README.md: personal home path', public.audit())


if __name__ == '__main__':
    unittest.main()
