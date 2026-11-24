#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Inspect an IPA or build the version-pinned Instagram Focus modification locally."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unicodedata
import zipfile


SKILL = Path(__file__).resolve().parent.parent
SOURCES = SKILL / "assets" / "instagram-focus" / "src"
ORIGINAL_BUNDLE_ID = "com.burbn.instagram"
SUPPORTED_VERSION = "418.2.0"
LOAD_PATH = "@executable_path/Frameworks/InstagramFocus.dylib"
MACHO_MAGICS = {
    b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf",
    b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xce",
    b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
    b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca",
}
MAX_ARCHIVE_BYTES = 8 * 1024**3
MAX_MEMBER_BYTES = 2 * 1024**3
MAX_ARCHIVE_MEMBERS = 200_000


def inspect_macho(data: bytes) -> dict:
    """Parse bounded load commands for a thin, little-endian arm64 Mach-O image."""
    if len(data) < 32:
        raise ValueError("Truncated Mach-O header")
    magic, cpu, subtype, kind, count, command_bytes, _flags, _reserved = struct.unpack_from("<8I", data)
    if magic != 0xFEEDFACF or cpu != 0x100000C or (subtype & 0xFFFFFF) == 2:
        raise ValueError("Unsupported Mach-O layout; this recipe requires thin arm64, not arm64e or universal images")
    end = 32 + command_bytes
    if end > len(data) or count > command_bytes // 8:
        raise ValueError("Invalid Mach-O load-command bounds")
    offset = 32
    sections = []
    dylibs = []
    encrypted = False
    commands = []
    for _ in range(count):
        if offset + 8 > end:
            raise ValueError("Truncated Mach-O load command")
        command, size = struct.unpack_from("<II", data, offset)
        if size < 8 or size % 8 or offset + size > end:
            raise ValueError("Invalid Mach-O load-command bounds or alignment")
        commands.append((command, offset, size))
        if command in (0x21, 0x2C):
            minimum = 24 if command == 0x2C else 20
            if size < minimum:
                raise ValueError("Truncated Mach-O encryption command")
            crypt_offset, crypt_size, crypt_id = struct.unpack_from("<III", data, offset + 8)
            if crypt_offset + crypt_size > len(data):
                raise ValueError("Invalid Mach-O encrypted range")
            encrypted = encrypted or crypt_id != 0
        if command == 0x19:
            if size < 72:
                raise ValueError("Truncated Mach-O segment")
            file_offset, file_size = struct.unpack_from("<QQ", data, offset + 40)
            if file_offset + file_size > len(data):
                raise ValueError("Mach-O segment exceeds the file")
            nsections = struct.unpack_from("<I", data, offset + 64)[0]
            if 72 + nsections * 80 > size:
                raise ValueError("Invalid Mach-O segment sections")
            for index in range(nsections):
                section = offset + 72 + index * 80
                length, position = struct.unpack_from("<QI", data, section + 40)
                flags = struct.unpack_from("<I", data, section + 64)[0]
                if (flags & 0xFF) in (1, 12, 18):
                    continue
                if length and position:
                    if position < end or position + length > len(data):
                        raise ValueError("Invalid Mach-O file-backed section bounds")
                    sections.append(position)
        if command in (0xC, 0x80000018, 0x8000001F, 0x20, 0x80000023):
            if size < 24:
                raise ValueError("Truncated Mach-O dylib command")
            name_offset = struct.unpack_from("<I", data, offset + 8)[0]
            if not 24 <= name_offset < size:
                raise ValueError("Invalid Mach-O dylib name offset")
            name_data = data[offset + name_offset:offset + size]
            if b"\0" not in name_data:
                raise ValueError("Unterminated Mach-O dylib name")
            try:
                dylibs.append(name_data.split(b"\0", 1)[0].decode("utf-8"))
            except UnicodeDecodeError as error:
                raise ValueError("Invalid Mach-O dylib name encoding") from error
        offset += size
    if offset != end:
        raise ValueError("Mach-O load-command count does not match its byte size")
    return {
        "architecture": "arm64", "filetype": kind, "encrypted": encrypted,
        "dylibs": dylibs, "header_end": end,
        "first_section": min(sections) if sections else len(data),
        "section_count": len(sections), "commands": commands,
    }


def inject_dylib(data: bytes, load_path: str) -> bytes:
    """Add one load command in confirmed empty header padding without relocating data."""
    image = inspect_macho(data)
    if image["filetype"] != 2:
        raise ValueError("The injection target must be an MH_EXECUTE executable")
    if image["encrypted"]:
        raise ValueError("The executable is still encrypted")
    if not isinstance(load_path, str) or not load_path or "\0" in load_path:
        raise ValueError("Invalid dylib load path")
    if load_path in image["dylibs"]:
        raise ValueError("The executable is already patched with this dylib")
    encoded = load_path.encode("utf-8")
    size = (24 + len(encoded) + 1 + 7) & ~7
    start = image["header_end"]
    if not image["section_count"] or start + size > image["first_section"]:
        raise ValueError("Insufficient verified header padding; relocation is not supported")
    if data[start:start + size] != bytes(size):
        raise ValueError("Header padding is not empty; refusing to overwrite it")
    result = bytearray(data)
    load = struct.pack("<6I", 0xC, size, 24, 0, 0x10000, 0x10000) + encoded + b"\0"
    result[start:start + size] = load.ljust(size, b"\0")
    count, command_bytes = struct.unpack_from("<II", data, 16)
    struct.pack_into("<II", result, 16, count + 1, command_bytes + size)
    return bytes(result)


def _archive_members(archive: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, str]]:
    infos = archive.infolist()
    if not infos or len(infos) > MAX_ARCHIVE_MEMBERS:
        raise ValueError("Empty archive or archive member limit exceeded")
    if sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive extraction size limit exceeded")
    records = []
    names = {}
    for info in infos:
        original = info.orig_filename
        name = original[:-1] if original.endswith("/") else original
        parts = name.split("/")
        if not name or "\0" in original or "\\" in name or ":" in name or any(part in ("", ".", "..") for part in parts):
            raise ValueError("Unsafe archive path")
        if PurePosixPath(name).is_absolute():
            raise ValueError("Absolute archive path")
        key = unicodedata.normalize("NFC", name).casefold()
        if key in names:
            raise ValueError("Duplicate or case-colliding archive path")
        kind = stat.S_IFMT(info.external_attr >> 16)
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or (kind == stat.S_IFDIR and not info.is_dir()):
            raise ValueError("Archive contains a symlink or unsupported entry type")
        if info.is_dir() and kind == stat.S_IFREG:
            raise ValueError("Archive directory has conflicting file metadata")
        if info.flag_bits & 1:
            raise ValueError("ZIP-level encrypted archives are not supported")
        if info.file_size > MAX_MEMBER_BYTES:
            raise ValueError("Archive member size limit exceeded")
        names[key] = info.is_dir()
        records.append((info, name))
    for _info, name in records:
        parts = name.split("/")
        for length in range(1, len(parts)):
            parent = unicodedata.normalize("NFC", "/".join(parts[:length])).casefold()
            if parent in names and not names[parent]:
                raise ValueError("Archive file conflicts with a parent directory")
    return records


def _app_info(app: Path) -> dict:
    try:
        info = plistlib.loads((app / "Info.plist").read_bytes())
    except (OSError, plistlib.InvalidFileException, ValueError) as error:
        raise ValueError("The app must contain a readable Info.plist") from error
    if not isinstance(info, dict):
        raise ValueError("The app Info.plist must be a dictionary")
    executable = info.get("CFBundleExecutable")
    if not isinstance(executable, str) or not executable or executable in (".", "..") or any(character in executable for character in "/\\:\0"):
        raise ValueError("Unsafe or missing CFBundleExecutable")
    if not (app / executable).is_file():
        raise ValueError("The app's main executable is missing")
    return info


def extract_ipa(ipa: Path, destination: Path) -> Path:
    """Validate archive paths before extracting into a new private directory."""
    ipa, destination = Path(ipa), Path(destination)
    if os.path.lexists(destination):
        raise ValueError("Extraction destination already exists")
    with zipfile.ZipFile(ipa) as archive:
        records = _archive_members(archive)
        roots = {
            "/".join(name.split("/")[:2]) for _info, name in records
            if len(name.split("/")) >= 2 and name.split("/")[0] == "Payload" and name.split("/")[1].endswith(".app")
        }
        if len(roots) != 1:
            raise ValueError("Expected exactly one Payload/*.app bundle")
        destination.mkdir(parents=True, mode=0o700)
        destination.chmod(0o700)
        try:
            for info, name in records:
                path = destination.joinpath(*name.split("/"))
                if info.is_dir():
                    path.mkdir(parents=True, exist_ok=True, mode=0o700)
                    continue
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with archive.open(info) as source, path.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                mode = (info.external_attr >> 16) & 0o111
                path.chmod(0o644 | mode)
            for path in destination.rglob("*"):
                if path.is_dir():
                    path.chmod(0o755)
            app = destination / next(iter(roots))
            _app_info(app)
            return app
        except Exception:
            shutil.rmtree(destination)
            raise


def _images(app: Path) -> list[tuple[Path, dict]]:
    result = []
    for path in sorted(app.rglob("*")):
        if path.is_symlink():
            raise ValueError("App bundles containing symlinks are not supported")
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            magic = stream.read(4)
        if magic in MACHO_MAGICS:
            try:
                result.append((path, inspect_macho(path.read_bytes())))
            except ValueError as error:
                raise ValueError(f"Unsupported or malformed image at {path.relative_to(app).as_posix()}: {error}") from error
    return result


def inspect_ipa(ipa: Path) -> dict:
    """Report app metadata and image encryption without exposing Store account metadata."""
    with tempfile.TemporaryDirectory(prefix="ios-app-inspect-") as temporary:
        app = extract_ipa(Path(ipa), Path(temporary) / "input")
        info = _app_info(app)
        main = app / info["CFBundleExecutable"]
        main_image = inspect_macho(main.read_bytes())
        clues = [
            "IGUnifiedVideoCollectionView", "IGSundialAutoScroll", "IGMainFeedListAdapterDataSource",
            "IGExploreGridViewController", "IGTabBarController", "objectsForListAdapter:",
            "_tabBarSurfaces", "followedByCurrentUser",
        ]
        data = main.read_bytes()
        return {
            "bundle_id": info.get("CFBundleIdentifier"),
            "version": info.get("CFBundleShortVersionString"),
            "minimum_os": info.get("MinimumOSVersion"),
            "main_executable": info["CFBundleExecutable"],
            "architecture": main_image["architecture"],
            "images": [
                {"path": path.relative_to(app).as_posix(), "architecture": image["architecture"], "encrypted": image["encrypted"]}
                for path, image in _images(app)
            ],
            "name_clues": {name: name.encode() in data for name in clues},
            "name_clues_are_behavioral_verification": False,
        }


def _check_bundle_id(bundle_id: str) -> None:
    if not isinstance(bundle_id, str) or not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+){2,}", bundle_id):
        raise ValueError("Use a reverse-DNS bundle identifier with at least three components")
    if bundle_id.casefold() == ORIGINAL_BUNDLE_ID.casefold():
        raise ValueError("Choose a separate bundle identifier for the modified app")


def validate_profile(profile: dict, bundle_id: str, identity_sha1: str) -> dict:
    """Select a minimal entitlement set authorized by this profile and certificate."""
    _check_bundle_id(bundle_id)
    if not isinstance(profile, dict):
        raise ValueError("The provisioning profile must decode to a dictionary")
    expiration = profile.get("ExpirationDate")
    if not isinstance(expiration, datetime):
        raise ValueError("The profile has no valid expiration date")
    expiration = expiration.replace(tzinfo=timezone.utc) if expiration.tzinfo is None else expiration.astimezone(timezone.utc)
    if expiration <= datetime.now(timezone.utc):
        raise ValueError("The provisioning profile has expired; refresh it in Xcode")
    if not isinstance(identity_sha1, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", identity_sha1):
        raise ValueError("The signing identity must be its 40-character SHA-1 fingerprint")
    certificates = profile.get("DeveloperCertificates", [])
    if not isinstance(certificates, list) or not any(isinstance(certificate, bytes) and hashlib.sha1(certificate).hexdigest().casefold() == identity_sha1.casefold() for certificate in certificates):
        raise ValueError("The signing certificate is not authorized by the provisioning profile")
    allowed = profile.get("Entitlements")
    if not isinstance(allowed, dict):
        raise ValueError("The provisioning profile has no entitlement dictionary")
    pattern = allowed.get("application-identifier")
    if not isinstance(pattern, str) or "." not in pattern:
        raise ValueError("The profile has no valid application identifier")
    prefix = pattern.split(".", 1)[0]
    if not re.fullmatch(r"[A-Z0-9]{10}", prefix):
        raise ValueError("Unsupported profile App ID prefix")
    application_id = f"{prefix}.{bundle_id}"
    if not fnmatch.fnmatchcase(application_id, pattern):
        raise ValueError("The profile does not authorize the requested bundle identifier")
    prefixes = profile.get("ApplicationIdentifierPrefix")
    if prefixes is not None and (not isinstance(prefixes, list) or prefix not in prefixes):
        raise ValueError("The profile App ID prefix is inconsistent")
    team = allowed.get("com.apple.developer.team-identifier")
    teams = profile.get("TeamIdentifier")
    if not isinstance(team, str) or not re.fullmatch(r"[A-Z0-9]{10}", team) or not isinstance(teams, list) or team not in teams:
        raise ValueError("The profile team identifier is missing or inconsistent")
    groups = allowed.get("keychain-access-groups", [])
    if not isinstance(groups, list) or not any(isinstance(group, str) and fnmatch.fnmatchcase(application_id, group) for group in groups):
        raise ValueError("The profile does not authorize the app's isolated keychain group")
    result = {
        "application-identifier": application_id,
        "com.apple.developer.team-identifier": team,
        "keychain-access-groups": [application_id],
    }
    if allowed.get("get-task-allow") is True:
        result["get-task-allow"] = True
    return result


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif os.path.lexists(path):
        path.unlink()


def _normalize_bundle_permissions(app: Path) -> None:
    app.chmod(0o755)
    for path in app.rglob("*"):
        if path.is_dir():
            path.chmod(0o755)
        elif path.is_file():
            path.chmod(0o644 | (stat.S_IMODE(path.stat().st_mode) & 0o111))


def prepare_app(source: Path, dylib: Path, destination: Path, bundle_id: str, keychain_group: str) -> Path:
    """Stage the pinned recipe without changing the original app or signing it."""
    source, dylib, destination = Path(source), Path(dylib), Path(destination)
    _check_bundle_id(bundle_id)
    if not isinstance(keychain_group, str) or not re.fullmatch(r"[A-Z0-9]{10}\." + re.escape(bundle_id), keychain_group):
        raise ValueError("The keychain group must be the profile-authorized full application identifier")
    if source.is_symlink() or any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("App bundles containing symlinks are not supported")
    if os.path.lexists(destination):
        raise ValueError("Staging destination already exists")
    if source.resolve() in destination.resolve().parents:
        raise ValueError("The staging destination must be outside the source app")
    info = _app_info(source)
    if info.get("CFBundleIdentifier") != ORIGINAL_BUNDLE_ID or info.get("CFBundleShortVersionString") != SUPPORTED_VERSION:
        raise ValueError(f"This recipe requires {ORIGINAL_BUNDLE_ID} version {SUPPORTED_VERSION}")
    library = inspect_macho(dylib.read_bytes())
    if library["filetype"] != 6 or library["encrypted"]:
        raise ValueError("The supplied tweak must be an unencrypted arm64 MH_DYLIB library")
    shutil.copytree(source, destination)
    try:
        for path in sorted(destination.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.name in ("SC_Info", "_CodeSignature", "embedded.mobileprovision") or path.suffix == ".appex":
                _remove(path)
        for name in ("PlugIns", "Watch", "WatchKitSupport", "WatchKitSupport2"):
            _remove(destination / name)
        executable = destination / info["CFBundleExecutable"]
        images = _images(destination)
        if not any(path == executable for path, _image in images):
            raise ValueError("The main executable is not a supported Mach-O image")
        if any(image["encrypted"] for _path, image in images):
            raise ValueError("At least one retained executable or framework is still encrypted")
        info = dict(info)
        info["CFBundleIdentifier"] = bundle_id
        info["CFBundleDisplayName"] = "Instagram Focus"
        info["InstagramFocusPatchVersion"] = 2
        info["InstagramFocusKeychainGroup"] = keychain_group
        info["CFBundleURLTypes"] = [{"CFBundleURLName": bundle_id, "CFBundleURLSchemes": ["focus-" + bundle_id.lower().replace(".", "-")]}]
        (destination / "Info.plist").write_bytes(plistlib.dumps(info, fmt=plistlib.FMT_BINARY))
        executable.write_bytes(inject_dylib(executable.read_bytes(), LOAD_PATH))
        executable.chmod(0o755)
        framework_directory = destination / "Frameworks"
        framework_directory.mkdir(exist_ok=True)
        target = framework_directory / "InstagramFocus.dylib"
        if target.exists():
            raise ValueError("The input app already contains InstagramFocus.dylib")
        shutil.copy2(dylib, target)
        target.chmod(0o755)
        _normalize_bundle_permissions(destination)
        return destination
    except Exception:
        shutil.rmtree(destination)
        raise


def _new_output(output: Path) -> Path:
    output = Path(output).expanduser().absolute()
    if os.path.lexists(output):
        raise ValueError("Output already exists; choose a new path")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    return output


def _publish(source: Path, output: Path, mode: int) -> None:
    source.chmod(mode)
    try:
        os.link(source, output)
    except FileExistsError as error:
        raise ValueError("Output already exists; it was not overwritten") from error


def _run(*arguments: object, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run([str(argument) for argument in arguments], check=True, stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None)


def compile_tweak(output: Path) -> None:
    if sys.platform != "darwin":
        raise ValueError("Compiling the tweak requires macOS and Xcode's iPhone SDK")
    output = _new_output(output)
    with tempfile.TemporaryDirectory(prefix=".ios-tweak-compile-", dir=output.parent) as temporary:
        library = Path(temporary) / "InstagramFocus.dylib"
        _run(
            "xcrun", "--sdk", "iphoneos", "clang", "-target", "arm64-apple-ios16.3", "-dynamiclib", "-fobjc-arc",
            "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
            "-framework", "Foundation", "-framework", "UIKit", "-framework", "Security",
            "-install_name", "@rpath/InstagramFocus.dylib",
            SOURCES / "InstagramFocus.m", SOURCES / "third_party/fishhook/fishhook.c", "-o", library,
        )
        image = inspect_macho(library.read_bytes())
        if image["filetype"] != 6 or image["encrypted"]:
            raise ValueError("The compiler did not produce the expected unencrypted arm64 dylib")
        _publish(library, output, 0o700)


def build_instagram(ipa: Path, profile: Path, identity: str, bundle_id: str, output: Path) -> None:
    if sys.platform != "darwin":
        raise ValueError("Building and signing an IPA requires macOS and Xcode")
    ipa, profile = Path(ipa).expanduser().resolve(), Path(profile).expanduser().resolve()
    output = _new_output(output)
    if output.resolve() in (ipa, profile):
        raise ValueError("The output must not replace an input")
    decoded = plistlib.loads(_run("security", "cms", "-D", "-i", profile, capture=True).stdout)
    entitlements = validate_profile(decoded, bundle_id, identity)
    identities = _run("security", "find-identity", "-v", "-p", "codesigning", capture=True).stdout.decode("utf-8", errors="replace")
    if not re.search(r"\b" + re.escape(identity) + r"\b", identities, flags=re.IGNORECASE):
        raise ValueError("The signing identity's private key is not available in the local keychain")
    with tempfile.TemporaryDirectory(prefix=".ios-tweak-build-", dir=output.parent) as temporary:
        work = Path(temporary)
        source = extract_ipa(ipa, work / "input")
        library = work / "InstagramFocus.dylib"
        compile_tweak(library)
        payload = work / "Payload"
        payload.mkdir(mode=0o700)
        app = prepare_app(source, library, payload / "InstagramFocus.app", bundle_id, entitlements["keychain-access-groups"][0])
        shutil.copy2(profile, app / "embedded.mobileprovision")
        entitlement_path = work / "entitlements.plist"
        entitlement_path.write_bytes(plistlib.dumps(entitlements))
        entitlement_path.chmod(0o600)
        main_executable = app / _app_info(app)["CFBundleExecutable"]
        images = _images(app)
        for path, _image in sorted(images, key=lambda pair: len(pair[0].parts), reverse=True):
            if path != main_executable:
                _run("codesign", "--force", "--sign", identity, "--timestamp=none", "--generate-entitlement-der", path)
        for framework in sorted(app.rglob("*.framework"), key=lambda path: len(path.parts), reverse=True):
            _run("codesign", "--force", "--sign", identity, "--timestamp=none", "--generate-entitlement-der", framework)
        _run("codesign", "--force", "--sign", identity, "--timestamp=none", "--generate-entitlement-der", "--entitlements", entitlement_path, app)
        _normalize_bundle_permissions(app)
        _run("codesign", "--verify", "--deep", "--strict", app)
        result = work / "InstagramFocus.ipa"
        with zipfile.ZipFile(result, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(payload.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(work).as_posix())
        _publish(result, output, 0o600)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect", help="Inspect a local IPA without reporting account metadata")
    inspect_parser.add_argument("--ipa", type=Path, required=True)
    compile_parser = subparsers.add_parser("compile", help="Compile only the included tweak from source on macOS")
    compile_parser.add_argument("--output", type=Path, required=True)
    build_parser = subparsers.add_parser("build", help="Build and sign a separate Instagram Focus IPA locally on macOS")
    build_parser.add_argument("--ipa", type=Path, required=True)
    build_parser.add_argument("--profile", type=Path, required=True)
    build_parser.add_argument("--identity", required=True, help="40-character certificate SHA-1 from security find-identity")
    build_parser.add_argument("--bundle-id", required=True)
    build_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            print(json.dumps(inspect_ipa(args.ipa.expanduser()), indent=2))
        elif args.command == "compile":
            compile_tweak(args.output)
            print("Compiled the arm64 Instagram Focus library. No app was signed or installed.")
        elif args.command == "build":
            build_instagram(args.ipa, args.profile, args.identity, args.bundle_id, args.output)
            print("Built and signature-verified the local IPA. Device behavior still requires phone acceptance.")
        return 0
    except (ValueError, OSError, zipfile.BadZipFile, plistlib.InvalidFileException) as error:
        print(f"Error: {error}", file=sys.stderr)
    except subprocess.CalledProcessError as error:
        print(f"Error: {Path(str(error.cmd[0])).name} failed with exit code {error.returncode}. Check the local tool output.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
