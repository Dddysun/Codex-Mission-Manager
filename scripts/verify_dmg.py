#!/usr/bin/env python3
"""Read-only mount verification. No app installation or live chat access."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def test_evidence(path):
    """Import only explicit test results, never package or runtime claims."""
    if path is None:
        return {}
    receipt = json.loads(path.read_text())
    if not isinstance(receipt, dict):
        raise ValueError("Test report must be a JSON object")
    evidence = {}
    for key in ("backend_tests_passed", "packaging_host_tests_passed"):
        if key in receipt:
            value = receipt[key]
            if type(value) is not int or value <= 0:
                raise ValueError("Invalid passed-test count: " + key)
            evidence[key] = value
    for key in ("native_control_contract_checks", "javascript_render_checks"):
        if key in receipt:
            if receipt[key] != "passed":
                raise ValueError("Test report does not confirm success: " + key)
            evidence[key] = "passed"
    if evidence:
        evidence["test_receipt"] = {"file": path.name}
        for key in ("test_environment", "checked_at_dubai"):
            if isinstance(receipt.get(key), str):
                evidence["test_receipt"][key] = receipt[key]
    return evidence


def resource_hashes(app):
    """Hash ordinary resources without following bundle symlinks."""
    return {str(path.relative_to(app)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in app.rglob('*') if path.is_file() and not path.is_symlink()}


def verify_writable_runtime(app):
    """Exercise cold imports on a disposable writable copy, never the installed app.

    A read-only DMG hides attempted .pyc writes. This check also catches changes
    to existing resources, and verifies the seal again after both interpreter
    generations have imported cold modules.
    """
    with tempfile.TemporaryDirectory(prefix='tokenmax-writable-runtime-') as directory:
        copy = Path(directory)/'TokenMax.app'
        shutil.copytree(app, copy, symlinks=True)
        before = resource_hashes(copy)
        resources = copy/'Contents/Resources'
        python = resources/'python/bin/python3'
        command = [str(python), '-B', '-I', str(resources/'backend/app_host.py'), '--self-test']
        report = json.loads(subprocess.check_output(command, text=True, timeout=20))
        if report.get('bytecode_disabled') is not True or report.get('private_data_loaded') is not False:
            raise RuntimeError('Runtime did not confirm isolated no-bytecode imports')
        # Exercise the daemon bootstrap through its real owned-process launcher.
        probe = '''import sys, subprocess, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from owned_process import OwnedProcess
owner = OwnedProcess(Path(sys.argv[1])/'app_host.py', ['--self-test'],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
try:
    owner.process.wait(timeout=20)
    output, error = owner.process.stdout.read(), owner.process.stderr.read()
    if owner.process.returncode != 0:
        raise RuntimeError(error.decode())
    print(output.decode())
finally:
    owner.stop(deadline=time.monotonic()+1, grace_seconds=0)
    owner.process.stdout.close()
    owner.process.stderr.close()
'''
        child = json.loads(subprocess.check_output([str(python), '-B', '-I', '-c', probe,
                                                   str(resources/'backend')], text=True, timeout=25))
        if child.get('bytecode_disabled') is not True:
            raise RuntimeError('Owned interpreter enables bytecode writes')
        if resource_hashes(copy) != before:
            raise RuntimeError('Runtime imports modified application resources')
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(copy)],
                       check=True, capture_output=True, timeout=20)
        return {'writable_copy': True, 'cold_imports': True, 'owned_child_imports': True,
                'resources_unchanged': True, 'signature_integrity_after_imports': True,
                'bytecode_disabled': True, 'private_data_loaded': False,
                'live_chat_messages_sent': 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--test-report", type=Path,
                        help="Optional JSON receipt from separately executed tests")
    args = parser.parse_args()
    evidence = test_evidence(args.test_report)
    image = args.image.resolve()
    report = {"dmg_sha256": hashlib.sha256(image.read_bytes()).hexdigest(), "live_chat_messages_sent": 0,
              "administrator_service_installed": False, "system_power_settings_changed": False}
    with tempfile.TemporaryDirectory(prefix="mission-dmg-") as directory:
        mount = Path(directory) / "mount"
        mount.mkdir()
        subprocess.run(["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(image)], check=True, capture_output=True)
        try:
            app = mount / "TokenMax.app"
            subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True, capture_output=True)
            binary = app / "Contents/MacOS/CodexMissionManager"
            helper = app / "Contents/Library/HelperTools/PowerHelper"
            resources = app / "Contents/Resources"
            libraries = subprocess.check_output(["otool", "-L", str(binary)], text=True)
            assert "WebKit" not in libraries, "Native app unexpectedly links WebKit"
            report["webkit_linked"] = False
            native = subprocess.check_output([str(binary), "--self-test"], text=True)
            python = subprocess.check_output([str(resources / "python/bin/python3"), "-B", "-I",
                str(resources / "backend/app_host.py"), "--self-test"], text=True)
            report.update(readonly_mount=True, signature_integrity=True, native_self_test=json.loads(native),
                          embedded_runtime_self_test=json.loads(python))
            denied = subprocess.run([str(helper)], capture_output=True)
            report["unsigned_preview_helper_rejected"] = denied.returncode == 78
            assert report["unsigned_preview_helper_rejected"], "Preview helper did not fail closed"
            report['writable_runtime_check'] = verify_writable_runtime(app)
        finally:
            subprocess.run(["hdiutil", "detach", str(mount)], check=True, capture_output=True)
    report.update(graphical_ui_verified=False, login_autostart_verified=False, locked_delivery_verified=False,
                  display_off_delivery_verified=False, closed_lid_delivery_verified=False, notarized=False)
    report.update(evidence)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__": main()
