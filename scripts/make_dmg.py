#!/usr/bin/env python3
"""Create a drag-to-Applications DMG from an already verified .app."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", required=True, type=Path)
    args = parser.parse_args()
    build = args.build.resolve()
    manifest = json.loads((build / "build-manifest.json").read_text())
    version = manifest["version"]
    app = build / "TokenMax.app"
    if not app.is_dir(): raise SystemExit("Build the application first")
    stage = build / "dmg-stage"
    if stage.exists(): shutil.rmtree(stage)
    stage.mkdir()
    shutil.copytree(app, stage / app.name, symlinks=True)
    (stage / "Applications").symlink_to("/Applications")
    (stage / "安装说明.txt").write_text(
        "TOKEN榨汁机 / TokenMax V" + version + " 预览版\n\n"
        "将 TokenMax.app 拖入 Applications。关闭窗口后仍在后台运行。\n"
        "升级前请退出旧版；配置与记录保留。旧版名称为 Codex Mission Manager.app，可在退出后移到废纸篓，勿同时运行两个版本。\n"
        "首次安装请核对账号与聊天，再点“开始榨汁”。需要已登录的兼容 Codex 桌面客户端。\n"
        "Apple Silicon / macOS 14+。此预览未公证，合盖辅助服务不可用。\n\n"
        "Drag TokenMax.app to Applications. Quit the previous version before updating.\n"
        "Settings and history are retained. Remove the old Codex Mission Manager.app after quitting; do not run both copies.\n"
        "Requires a compatible Codex desktop client. Preview build; not notarized.\n"
        "Guide: https://github.com/Dddysun/Codex-Mission-Manager\n", encoding="utf-8")
    image = build / ("TokenMax-" + version + "-arm64-preview.dmg")
    subprocess.run(["hdiutil", "create", "-volname", "TokenMax", "-srcfolder", str(stage),
                    "-format", "UDZO", "-ov", str(image)], check=True)
    # DiskImages can retain a short-lived handle after create on hosted macOS.
    # Retry only its explicit transient resource errors, never a bad checksum.
    for attempt in range(5):
        verify = subprocess.run(["hdiutil", "verify", str(image)], capture_output=True, text=True)
        if verify.returncode == 0:
            print(verify.stdout)
            break
        detail = verify.stdout + verify.stderr
        transient = any(text in detail.lower() for text in ("resource temporarily unavailable", "resource busy"))
        if not transient or attempt == 4:
            raise RuntimeError("DMG verification failed: " + detail)
        time.sleep(2 ** attempt)
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    (build / "SHA256SUMS").write_text(digest + "  " + image.name + "\n")
    manifest = json.loads((build / "build-manifest.json").read_text())
    manifest.update(dmg=image.name, dmg_sha256=digest, dmg_bytes=image.stat().st_size, dmg_verified=True)
    (build / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("DMG_READY", image)


if __name__ == "__main__": main()
