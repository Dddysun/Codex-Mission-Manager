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
    app = build / "Codex Mission Manager.app"
    if not app.is_dir(): raise SystemExit("Build the application first")
    stage = build / "dmg-stage"
    if stage.exists(): shutil.rmtree(stage)
    stage.mkdir()
    shutil.copytree(app, stage / app.name, symlinks=True)
    (stage / "Applications").symlink_to("/Applications")
    (stage / "安装说明.txt").write_text(
        "任务管家 V0.1 原生窗口预览 / Apple Silicon / macOS 14+\n\n"
        "将 Codex Mission Manager.app 拖入 Applications 后打开。关闭窗口后继续后台运行。\n"
        "此版主窗口使用 SwiftUI / AppKit 原生控件，不内嵌网页。\n"
        "若已有网页版本后台，应用会优先连接它，避免重复执行器。\n\n"
        "本包为临时签名预览，尚未 Apple 公证。管理员无外屏合盖服务被禁用，未通过实机验收。\n"
        "若系统阻止打开，请使用后续正式签名版本；本包不提供绕过系统保护的方法。\n\n"
        "首次新安装默认暂停自动控制；确认账号与聊天后再开启。\n"
        "当前需要已安装且兼容的 ChatGPT/Codex 桌面客户端，本包不分发原客户端。\n"
        "源码、产品蓝图与验证结果：https://github.com/Dddysun/Codex-Mission-Manager\n", encoding="utf-8")
    image = build / "Codex-Mission-Manager-0.1.0-arm64-native-preview.dmg"
    subprocess.run(["hdiutil", "create", "-volname", "Codex Mission Manager", "-srcfolder", str(stage),
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
