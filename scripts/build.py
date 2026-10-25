#!/usr/bin/env python3
"""Reproducible native build; no package installation or privileged actions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import struct

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    print("+", " ".join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def runtime(source, target):
    source = Path(source).resolve()
    info = subprocess.check_output([str(source / "bin/python3"), "-I", "-c",
        "import sys,json;print(json.dumps({'version':sys.version_info[:2]}))"], text=True)
    version = ".".join(map(str, json.loads(info)["version"]))
    (target / "bin").mkdir(parents=True)
    shutil.copy2((source / "bin/python3").resolve(), target / "bin" / ("python" + version))
    (target / "bin/python3").symlink_to("python" + version)
    excluded = {"site-packages", "__pycache__", "test", "tests", "idlelib", "tkinter", "turtledemo", "ensurepip", "config-" + version + "-darwin"}
    def ignore(path, names):
        return [n for n in names if n in excluded or n.endswith((".pyc", ".pem")) or n.startswith("_tkinter.")]
    shutil.copytree(source / "lib" / ("python" + version), target / "lib" / ("python" + version), ignore=ignore)
    for library in (source / "lib").glob("*.dylib"):
        if library.is_symlink():
            (target / "lib" / library.name).symlink_to(os.readlink(library))
        else: shutil.copy2(library, target / "lib" / library.name)
    for name in ("licenses", "LICENSE", "LICENSE.txt"):
        path = source / name
        if path.is_dir(): shutil.copytree(path, target / name)
        elif path.is_file(): shutil.copy2(path, target / name)
    # Retain no host-specific search paths/site customizations. The embedded
    # interpreter is relocatable; only standard library modules are required.
    for name in ("sitecustomize.py", "usercustomize.py"):
        (target / "lib" / ("python" + version) / name).unlink(missing_ok=True)
    return version


def build(args):
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = output / "Codex Mission Manager.app"
    if app.exists():
        if args.replace:
            shutil.rmtree(app)
        else:
            raise SystemExit("Output app already exists. Use --replace for this generated build, or choose a new output directory.")
    contents = app / "Contents"
    resources = contents / "Resources"
    for name in ("MacOS", "Resources", "Library/HelperTools", "Library/LaunchDaemons"):
        (contents / name).mkdir(parents=True, exist_ok=True)
    scratch = output / "build-work"
    scratch.mkdir(exist_ok=True)
    team = os.environ.get("MISSION_TEAM_ID", "")
    identity = os.environ.get("MISSION_SIGN_IDENTITY", "-")
    if bool(team) != (identity != "-"):
        raise SystemExit("Supply both MISSION_TEAM_ID and MISSION_SIGN_IDENTITY, or neither for local preview")
    shared = (ROOT / "native/Shared.swift").read_text().replace("__TEAM_ID__", team, 1)
    shared_path = scratch / "Shared.swift"
    shared_path.write_text(shared)
    module_cache = scratch / "module-cache"
    sdk = subprocess.check_output(["xcrun", "--show-sdk-path"], text=True).strip()
    common = ["swiftc", "-swift-version", "5", "-O", "-target", "arm64-apple-macos14.0", "-sdk", sdk,
              "-module-cache-path", module_cache, "-parse-as-library", shared_path]
    run(common + [ROOT / "native/Localization.swift", ROOT / "native/NativeState.swift", ROOT / "native/NativeViews.swift", ROOT / "native/NativeSettings.swift", ROOT / "native/MenuPanel.swift", ROOT / "native/App.swift", "-o", contents / "MacOS/CodexMissionManager"])
    run(common + [ROOT / "native/PowerHelper.swift", "-o", contents / "Library/HelperTools/PowerHelper"])
    icon = scratch / "draw-icon"
    run(["swiftc", "-module-cache-path", module_cache, ROOT / "scripts/Icon.swift", "-o", icon])
    iconset = scratch / "AppIcon.iconset"
    run([icon, iconset])
    icon_path = resources / "AppIcon.icns"
    converted = subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icon_path)], capture_output=True)
    if converted.returncode:
        # Standard ICNS PNG chunks, usable even when ImageIO's iconutil service
        # is unavailable in a headless build environment.
        chunks = []
        for kind, name in [(b"icp4", "icon_16x16.png"), (b"icp5", "icon_32x32.png"),
                           (b"icp6", "icon_32x32@2x.png"), (b"ic07", "icon_128x128.png"),
                           (b"ic08", "icon_256x256.png"), (b"ic09", "icon_512x512.png"),
                           (b"ic10", "icon_512x512@2x.png")]:
            data = (iconset / name).read_bytes()
            chunks.append(kind + struct.pack(">I", len(data) + 8) + data)
        data = b"".join(chunks)
        icon_path.write_bytes(b"icns" + struct.pack(">I", len(data) + 8) + data)
    shutil.copyfile(ROOT / "packaging/Info.plist", contents / "Info.plist")
    shutil.copyfile(ROOT / "packaging/com.dddysun.CodexMissionManager.PowerHelper.plist",
                    contents / "Library/LaunchDaemons/com.dddysun.CodexMissionManager.PowerHelper.plist")
    backend = resources / "backend"
    backend.mkdir()
    for path in (ROOT / "backend").iterdir():
        if path.suffix == ".py" or path.name == "config.example.json": shutil.copyfile(path, backend / path.name)
    shutil.copytree(ROOT / "backend/web", backend / "web")
    pyversion = runtime(args.python_runtime, resources / "python")
    shutil.copytree(ROOT / "third-party", resources / "third-party")
    shutil.copyfile(ROOT / "docs/PRODUCT_BLUEPRINT_V0.1.md", resources / "PRODUCT_BLUEPRINT_V0.1.md")
    run([resources / "python/bin/python3", "-I", backend / "app_host.py", "--self-test"])
    run([contents / "MacOS/CodexMissionManager", "--self-test"])
    run([contents / "Library/HelperTools/PowerHelper", "--self-test"])
    # Remove only build metadata that invalidates a code seal. Never remove
    # quarantine or alter Gatekeeper policy.
    for attribute in ("com.apple.FinderInfo", "com.apple.ResourceFork"):
        subprocess.run(["xattr", "-r", "-d", attribute, str(app)], capture_output=True)
    # Sign every nested Mach-O before signing the app, including CPython modules.
    binaries = []
    for path in resources.rglob("*"):
        if path.is_file() and not path.is_symlink() and (path.suffix in (".so", ".dylib") or path.name.startswith("python3.")):
            binaries.append(path)
    binaries += [contents / "Library/HelperTools/PowerHelper", contents / "MacOS/CodexMissionManager"]
    for path in binaries:
        command = ["codesign", "--force", "--sign", identity]
        if path.name == "PowerHelper": command += ["--identifier", "com.dddysun.CodexMissionManager.PowerHelper"]
        if identity != "-": command += ["--options", "runtime", "--timestamp"]
        run(command + [path])
    command = ["codesign", "--force", "--sign", identity]
    if identity != "-": command += ["--options", "runtime", "--timestamp"]
    run(command + [app])
    run(["codesign", "--verify", "--deep", "--strict", app])
    manifest = {"version": "0.2.1", "architecture": "arm64", "minimum_macos": "14.0",
        "python": pyversion, "signing": "developer-id" if team else "ad-hoc-local-preview",
        "notarized": False, "privileged_helper_enabled": bool(team), "live_closed_lid_verified": False,
        "ui": "SwiftUI-AppKit", "webview": False, "private_runtime_data_included": False, "external_dependency": "Compatible installed ChatGPT/Codex desktop client"}
    (output / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("APP_READY", app)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--python-runtime", required=True, help="Relocatable CPython root; no site-packages included")
    parser.add_argument("--output", required=True)
    build(parser.parse_args())
