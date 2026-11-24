# SPDX-License-Identifier: GPL-3.0-only
"""Exercise the public recipe using synthetic app, Mach-O, and profile data."""

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import os
from pathlib import Path
import plistlib
import stat
import struct
import sys
import tempfile
import unittest
import warnings
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "skills/tweakin/scripts/instagram.py"
SPEC = importlib.util.spec_from_file_location("instagram_recipe", SCRIPT)
recipe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = recipe
SPEC.loader.exec_module(recipe)

LOAD_PATH = "@executable_path/Frameworks/InstagramFocus.dylib"
BUNDLE_ID = "org.example.InstagramFocus"
PREFIX = "TESTPREFIX"
TEAM = "TESTTEAM01"
CERTIFICATE = b"synthetic certificate fixture, not a real certificate"
IDENTITY = hashlib.sha1(CERTIFICATE).hexdigest().upper()
PAYLOAD = bytes(range(64))


def macho(*, encrypted=False, kind=2, section_offset=4096):
    segment_size = 72 + 80
    segment = struct.pack(
        "<II16sQQQQIIII", 0x19, segment_size, b"__TEXT", 0x100000000,
        section_offset + len(PAYLOAD), 0, section_offset + len(PAYLOAD), 7, 5, 1, 0,
    )
    section = struct.pack(
        "<16s16sQQIIIIIIII", b"__text", b"__TEXT", 0x100000000 + section_offset,
        len(PAYLOAD), section_offset, 2, 0, 0, 0x80000400, 0, 0, 0,
    )
    encryption = struct.pack("<6I", 0x2C, 24, section_offset, len(PAYLOAD), int(encrypted), 0)
    commands = segment + section + encryption
    header = struct.pack("<8I", 0xFEEDFACF, 0x100000C, 0, kind, 2, len(commands), 0, 0)
    return (header + commands).ljust(section_offset, b"\0") + PAYLOAD


def profile():
    return {
        "ExpirationDate": datetime.now(timezone.utc) + timedelta(days=2),
        "ApplicationIdentifierPrefix": [PREFIX],
        "TeamIdentifier": [TEAM],
        "DeveloperCertificates": [CERTIFICATE],
        "ProvisionedDevices": ["synthetic-test-device"],
        "Entitlements": {
            "application-identifier": f"{PREFIX}.org.example.*",
            "com.apple.developer.team-identifier": TEAM,
            "keychain-access-groups": [f"{PREFIX}.*"],
            "get-task-allow": True,
            "aps-environment": "development",
            "com.apple.security.application-groups": ["group.org.example.fixture"],
        },
    }


def app_entries(*, version="418.2.0", executable="Instagram", encrypted=False):
    return [
        ("Payload/Instagram.app/Info.plist", plistlib.dumps({
            "CFBundleIdentifier": "com.burbn.instagram",
            "CFBundleShortVersionString": version,
            "CFBundleExecutable": executable,
            "MinimumOSVersion": "16.3",
        })),
        ("Payload/Instagram.app/Instagram", macho(encrypted=encrypted)),
    ]


def write_ipa(path, entries):
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries:
            entry = zipfile.ZipInfo(name)
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(entry, content)
    return path


class SyntheticRecipeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_injection_preserves_payload_and_input(self):
        original = macho()
        snapshot = bytes(original)
        patched = recipe.inject_dylib(original, LOAD_PATH)
        inspection = recipe.inspect_macho(patched)
        self.assertEqual(original, snapshot)
        self.assertEqual(len(patched), len(original))
        self.assertEqual(patched[4096:], PAYLOAD)
        self.assertIn(LOAD_PATH, inspection["dylibs"])
        self.assertEqual(inspection["architecture"], "arm64")
        self.assertFalse(inspection["encrypted"])

    def test_injection_rejects_existing_load_command(self):
        patched = recipe.inject_dylib(macho(), LOAD_PATH)
        with self.assertRaises(ValueError):
            recipe.inject_dylib(patched, LOAD_PATH)

    def test_injection_rejects_encrypted_and_unsupported_images(self):
        unsupported = bytearray(macho())
        struct.pack_into("<I", unsupported, 4, 0x1000007)
        for data in [macho(encrypted=True), bytes(unsupported), b"not a Mach-O"]:
            with self.subTest(data_length=len(data)):
                with self.assertRaises(ValueError):
                    recipe.inject_dylib(data, LOAD_PATH)

    def test_injection_rejects_bad_commands_and_padding(self):
        malformed = bytearray(macho())
        struct.pack_into("<I", malformed, 36, len(malformed))
        occupied = bytearray(macho())
        occupied[208] = 1
        insufficient = macho(section_offset=208)
        for name, data in [("malformed", malformed), ("occupied", occupied), ("insufficient", insufficient)]:
            with self.subTest(case=name):
                snapshot = bytes(data)
                with self.assertRaises(ValueError):
                    recipe.inject_dylib(bytes(data), LOAD_PATH)
                self.assertEqual(bytes(data), snapshot)

    def test_archive_extracts_one_valid_app(self):
        ipa = write_ipa(self.root / "input.ipa", app_entries())
        app = recipe.extract_ipa(ipa, self.root / "extracted")
        self.assertEqual((app / "Instagram").read_bytes(), macho())
        self.assertEqual(plistlib.loads((app / "Info.plist").read_bytes())["CFBundleIdentifier"], "com.burbn.instagram")

    def test_bundle_permissions_remain_readable_inside_private_staging(self):
        ipa = self.root / "permissions.ipa"
        with zipfile.ZipFile(ipa, "w") as archive:
            for name, content in app_entries() + [("Payload/Instagram.app/Resources/note.txt", b"fixture")]:
                entry = zipfile.ZipInfo(name)
                entry.create_system = 3
                mode = 0o755 if name.endswith("/Instagram") else 0o600
                entry.external_attr = (stat.S_IFREG | mode) << 16
                archive.writestr(entry, content)
        previous_umask = os.umask(0o077)
        try:
            outer = self.root / "private-extraction"
            app = recipe.extract_ipa(ipa, outer)
            self.assertEqual(stat.S_IMODE(outer.stat().st_mode), 0o700)
            for directory in [app, app / "Resources"]:
                self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE((app / "Info.plist").stat().st_mode), 0o644)
            self.assertEqual(stat.S_IMODE((app / "Instagram").stat().st_mode), 0o755)
            dylib = self.root / "patch.dylib"
            dylib.write_bytes(macho(kind=6))
            staged = recipe.prepare_app(app, dylib, self.root / "prepared.app", BUNDLE_ID, f"{PREFIX}.{BUNDLE_ID}")
            for directory in [staged, staged / "Resources", staged / "Frameworks"]:
                self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE((staged / "Info.plist").stat().st_mode), 0o644)
            self.assertEqual(stat.S_IMODE((staged / "Instagram").stat().st_mode), 0o755)
        finally:
            os.umask(previous_umask)

    def test_archive_rejects_unsafe_paths_before_extracting_files(self):
        for index, name in enumerate(["../outside", "/absolute", "Payload/Instagram.app/../../outside", "Payload\\outside"]):
            with self.subTest(name=name):
                ipa = write_ipa(self.root / f"unsafe-{index}.ipa", app_entries() + [(name, b"unsafe")])
                destination = self.root / f"out-{index}"
                with self.assertRaises(ValueError):
                    recipe.extract_ipa(ipa, destination)
                self.assertFalse(destination.exists() and any(destination.rglob("*")))
        self.assertFalse((self.root / "outside").exists())

    def test_archive_rejects_duplicate_and_case_colliding_names(self):
        for index, names in enumerate([
            ["Payload/Instagram.app/note", "Payload/Instagram.app/note"],
            ["Payload/Instagram.app/Note", "Payload/Instagram.app/note"],
        ]):
            with self.subTest(names=names), warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                ipa = write_ipa(self.root / f"duplicate-{index}.ipa", app_entries() + [(name, b"fixture") for name in names])
                with self.assertRaises(ValueError):
                    recipe.extract_ipa(ipa, self.root / f"duplicate-out-{index}")

    def test_archive_rejects_symlinks_and_ambiguous_app_roots(self):
        ipa = write_ipa(self.root / "symlink.ipa", app_entries())
        with zipfile.ZipFile(ipa, "a") as archive:
            link = zipfile.ZipInfo("Payload/Instagram.app/link")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, "../../outside")
        with self.assertRaises(ValueError):
            recipe.extract_ipa(ipa, self.root / "symlink-out")
        ambiguous = write_ipa(self.root / "ambiguous.ipa", app_entries() + [
            ("Payload/Other.app/Info.plist", plistlib.dumps({"CFBundleExecutable": "Other"})),
            ("Payload/Other.app/Other", macho()),
        ])
        with self.assertRaises(ValueError):
            recipe.extract_ipa(ambiguous, self.root / "ambiguous-out")

    def test_archive_rejects_unsafe_executable_name(self):
        ipa = write_ipa(self.root / "bad-executable.ipa", app_entries(executable="../Instagram"))
        with self.assertRaises(ValueError):
            recipe.extract_ipa(ipa, self.root / "bad-executable-out")

    def test_archive_does_not_overwrite_existing_destination(self):
        destination = self.root / "existing"
        destination.mkdir()
        sentinel = destination / "keep.txt"
        sentinel.write_text("keep")
        ipa = write_ipa(self.root / "input.ipa", app_entries())
        with self.assertRaises((ValueError, FileExistsError)):
            recipe.extract_ipa(ipa, destination)
        self.assertEqual(sentinel.read_text(), "keep")

    def test_inspection_finds_encrypted_framework(self):
        ipa = write_ipa(self.root / "framework.ipa", app_entries() + [
            ("Payload/Instagram.app/Frameworks/Fixture.framework/Fixture", macho(encrypted=True, kind=6)),
        ])
        result = recipe.inspect_ipa(ipa)
        images = result["images"]
        self.assertTrue(any(image["encrypted"] and "Fixture.framework" in image["path"] for image in images))

    def test_profile_uses_authorized_prefix_and_minimal_entitlements(self):
        for debugging in [True, False]:
            with self.subTest(debugging=debugging):
                data = profile()
                data["Entitlements"]["get-task-allow"] = debugging
                result = recipe.validate_profile(data, BUNDLE_ID, IDENTITY)
                self.assertEqual(result["application-identifier"], f"{PREFIX}.{BUNDLE_ID}")
                self.assertEqual(result["keychain-access-groups"], [f"{PREFIX}.{BUNDLE_ID}"])
                self.assertEqual(result["com.apple.developer.team-identifier"], TEAM)
                self.assertEqual(bool(result.get("get-task-allow")), debugging)
                self.assertNotIn("aps-environment", result)
                self.assertNotIn("com.apple.security.application-groups", result)

    def test_profile_rejects_expiry_bundle_and_certificate_mismatch(self):
        expired = profile()
        expired["ExpirationDate"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        wrong_bundle = profile()
        wrong_bundle["Entitlements"]["application-identifier"] = f"{PREFIX}.org.other.*"
        for name, data, identity in [
            ("expired", expired, IDENTITY),
            ("bundle", wrong_bundle, IDENTITY),
            ("certificate", profile(), "0" * 40),
        ]:
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    recipe.validate_profile(data, BUNDLE_ID, identity)

    def test_profile_rejects_unauthorized_keychain_and_original_bundle(self):
        denied = profile()
        denied["Entitlements"]["keychain-access-groups"] = ["OTHERGROUP.*"]
        with self.assertRaises(ValueError):
            recipe.validate_profile(denied, BUNDLE_ID, IDENTITY)
        original_authorized = profile()
        original_authorized["Entitlements"]["application-identifier"] = f"{PREFIX}.*"
        with self.assertRaises(ValueError):
            recipe.validate_profile(original_authorized, "com.burbn.instagram", IDENTITY)

    def test_prepare_preserves_original_and_removes_unprovisioned_components(self):
        source = self.root / "original.app"
        source.mkdir()
        for name, data in app_entries():
            relative = Path(name).relative_to("Payload/Instagram.app")
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for name in ["PlugIns/Share.appex/Share", "Extensions/Camera.appex/Camera", "Watch/Fixture.app/Fixture", "SC_Info/license", "_CodeSignature/CodeResources", "embedded.mobileprovision"]:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(macho(encrypted=True) if name.endswith(("Share", "Camera", "Fixture")) else b"fixture")
        before = {str(path.relative_to(source)): path.read_bytes() for path in source.rglob("*") if path.is_file()}
        dylib = self.root / "patch.dylib"
        dylib.write_bytes(macho(kind=6))
        app = recipe.prepare_app(source, dylib, self.root / "prepared.app", BUNDLE_ID, f"{PREFIX}.{BUNDLE_ID}")
        info = plistlib.loads((app / "Info.plist").read_bytes())
        self.assertEqual(info["CFBundleIdentifier"], BUNDLE_ID)
        self.assertEqual(info["CFBundleDisplayName"], "Instagram Focus")
        self.assertEqual(info["InstagramFocusKeychainGroup"], f"{PREFIX}.{BUNDLE_ID}")
        self.assertEqual(info["InstagramFocusPatchVersion"], 2)
        self.assertIn(LOAD_PATH, recipe.inspect_macho((app / "Instagram").read_bytes())["dylibs"])
        self.assertEqual((app / "Frameworks/InstagramFocus.dylib").read_bytes(), dylib.read_bytes())
        self.assertFalse(any(app.rglob("*.appex")))
        for name in ["Watch", "SC_Info", "_CodeSignature", "embedded.mobileprovision"]:
            self.assertFalse((app / name).exists(), name)
        self.assertEqual(before, {str(path.relative_to(source)): path.read_bytes() for path in source.rglob("*") if path.is_file()})

    def test_prepare_rejects_encrypted_retained_framework(self):
        ipa = write_ipa(self.root / "encrypted-framework.ipa", app_entries() + [
            ("Payload/Instagram.app/Frameworks/Fixture.framework/Fixture", macho(encrypted=True, kind=6)),
        ])
        source = recipe.extract_ipa(ipa, self.root / "source")
        dylib = self.root / "patch.dylib"
        dylib.write_bytes(macho(kind=6))
        with self.assertRaises(ValueError):
            recipe.prepare_app(source, dylib, self.root / "rejected.app", BUNDLE_ID, f"{PREFIX}.{BUNDLE_ID}")

    def test_prepare_rejects_unaccepted_app_version(self):
        ipa = write_ipa(self.root / "other-version.ipa", app_entries(version="999.0"))
        source = recipe.extract_ipa(ipa, self.root / "source")
        dylib = self.root / "patch.dylib"
        dylib.write_bytes(macho(kind=6))
        with self.assertRaises(ValueError):
            recipe.prepare_app(source, dylib, self.root / "rejected.app", BUNDLE_ID, f"{PREFIX}.{BUNDLE_ID}")

    def test_prepare_rejects_encrypted_or_executable_patch(self):
        ipa = write_ipa(self.root / "input.ipa", app_entries())
        source = recipe.extract_ipa(ipa, self.root / "source")
        for index, data in enumerate([macho(encrypted=True, kind=6), macho(kind=2)]):
            with self.subTest(index=index):
                dylib = self.root / f"bad-{index}.dylib"
                dylib.write_bytes(data)
                with self.assertRaises(ValueError):
                    recipe.prepare_app(source, dylib, self.root / f"rejected-{index}.app", BUNDLE_ID, f"{PREFIX}.{BUNDLE_ID}")


if __name__ == "__main__":
    unittest.main()
