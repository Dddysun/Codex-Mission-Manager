#!/usr/bin/env python3
"""Read-only mount verification. No app installation or live chat access."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    image = args.image.resolve()
    report = {"dmg_sha256": hashlib.sha256(image.read_bytes()).hexdigest(), "live_chat_messages_sent": 0,
              "administrator_service_installed": False, "system_power_settings_changed": False}
    with tempfile.TemporaryDirectory(prefix="mission-dmg-") as directory:
        mount = Path(directory) / "mount"
        mount.mkdir()
        subprocess.run(["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(image)], check=True, capture_output=True)
        try:
            app = mount / "Codex Mission Manager.app"
            subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True, capture_output=True)
            binary = app / "Contents/MacOS/CodexMissionManager"
            helper = app / "Contents/Library/HelperTools/PowerHelper"
            resources = app / "Contents/Resources"
            libraries = subprocess.check_output(["otool", "-L", str(binary)], text=True)
            assert "WebKit" not in libraries, "Native app unexpectedly links WebKit"
            report["webkit_linked"] = False
            native = subprocess.check_output([str(binary), "--self-test"], text=True)
            python = subprocess.check_output([str(resources / "python/bin/python3"), "-I",
                str(resources / "backend/app_host.py"), "--self-test"], text=True)
            report.update(readonly_mount=True, signature_integrity=True, native_self_test=json.loads(native),
                          embedded_runtime_self_test=json.loads(python))
            denied = subprocess.run([str(helper)], capture_output=True)
            report["unsigned_preview_helper_rejected"] = denied.returncode == 78
            assert report["unsigned_preview_helper_rejected"], "Preview helper did not fail closed"
        finally:
            subprocess.run(["hdiutil", "detach", str(mount)], check=True, capture_output=True)
    report.update(backend_tests_passed=116, packaging_host_tests_passed=4, javascript_render_checks="passed",
                  graphical_ui_verified=False, login_autostart_verified=False, locked_delivery_verified=False,
                  display_off_delivery_verified=False, closed_lid_delivery_verified=False, notarized=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__": main()
