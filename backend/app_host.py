"""App-owned backend host. Resources are immutable; user data stays outside .app."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))  # Trusted bundled modules, also in isolated Python mode.
from platform_support import (check_writable_directory, lock_held, private_directory,
                              private_file_permissions, sqlite_ro_uri,
                              support_directory, python_command)

IS_WINDOWS = os.name == 'nt'


def locked(path):
    return lock_held(path, create=False)


def legacy_service(home):
    root = home / ".codex/usage-guardian"
    if not locked(root / "state/daemon.lock"):
        return None
    for name in ("ui-8769.json", "ui-8768.json", "ui.json"):
        info = root / "state" / name
        lock = info.with_suffix(".lock")
        if info.exists() and locked(lock):
            value = json.loads(info.read_text(encoding="utf-8"))
            if value.get("url", "").startswith("http://127.0.0.1:"):
                return {"url": value["url"], "external": True, "owned": False,
                        "state_dir": str(root / "state"), "config": str(root / "config.json")}
    raise RuntimeError("Existing Guardian is running without its UI. Open its current interface before migration; no duplicate executor started.")


def make_config(directory, home=None, port=8769, parent_pid=None):
    directory = Path(directory)
    private_directory(directory)
    state = directory / "state"
    cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    previous = directory / 'config.json'
    if previous.exists():
        saved = json.loads(previous.read_text(encoding='utf-8'))
        if not isinstance(saved, dict):
            raise ValueError('Existing application configuration is invalid; it was not overwritten')
        cfg.update(saved)
    cfg.update(state_dir=str(state), runtime_root=str(ROOT), ui_port=port,
               host_pid=parent_pid, system_notifications=False, native_notifications=True, power_guard_enabled=False)
    cfg["desktop_database"] = str(Path(home or Path.home()) / ".codex/state_5.sqlite")
    if os.name == 'nt':
        cfg.update(desktop_platform='windows', desktop_connect_timeout_seconds=8)
    path = directory / "config.json"
    from guardian import atomic_json
    atomic_json(path, cfg)
    from guardian import Store
    fresh = not (state / "guardian.sqlite3").exists()
    store = Store(state)
    if fresh:
        store.put("supervisor_paused", True)
    store.close()
    return path


def migrate_legacy(directory, home=None):
    """Explicit local migration; never includes data in a build or source upload."""
    home = Path(home or Path.home())
    source = home / ".codex/usage-guardian/state"
    if locked(source / "daemon.lock"):
        raise RuntimeError("Stop the existing Guardian before migration")
    destination = Path(directory) / "state"
    private_directory(destination)
    target = destination / "guardian.sqlite3"
    if target.exists():
        raise RuntimeError("Destination already contains a ledger; it was not overwritten")
    with closing(sqlite3.connect(sqlite_ro_uri(source / "guardian.sqlite3"), uri=True)) as old:
        with closing(sqlite3.connect(str(target))) as new:
            old.backup(new)
            new.commit()
    private_file_permissions(target)


def preflight_application_data(directory):
    """Fail before opening a server or daemon; never repair an existing ACL."""
    directory = Path(directory)
    checks = (
        (directory, ('config.json', 'config.json.tmp', 'backend.log',
                     'native-host.log', 'native-preferences.json',
                     'native-preferences.json.tmp', 'host.lock')),
        (directory / 'state', ('guardian.sqlite3', 'guardian.sqlite3-wal',
                               'guardian.sqlite3-shm', 'daemon.lock',
                               'status.json', 'status.json.tmp',
                               'native-notices.json', 'native-notices.json.tmp')),
    )
    for target, files in checks:
        try:
            private_directory(target)
        except OSError as exc:
            raise RuntimeError(
                'app_data_not_writable: Application data folder cannot be created: %s. '
                'Ask the folder owner or administrator to restore write access '
                'for your account, then reopen the app normally. '
                'Existing permissions were not changed.' % target) from exc
        check_writable_directory(target, files)


def run(directory, attach=True, home=None):
    if not IS_WINDOWS:
        return run_owned(directory, attach, home)
    directory = Path(directory)
    preflight_application_data(directory)
    lease = None
    from platform_support import open_lock, lock_file
    try:
        lease = open_lock(directory/'host.lock')
        lock_file(lease)
        return run_owned(directory, attach, home)
    except BlockingIOError as exc:
        raise RuntimeError('The application backend is already running for this user') from exc
    finally:
        if lease:
            lease.close()


def read_host_input(stream, stop, detail):
    """Only an explicit stop command or the owning parent's EOF ends a host."""
    for line in stream:
        if line.strip() == 'stop':
            detail['reason'] = 'requested'
            stop.set()
            return
    detail['reason'] = 'parent_input_closed'
    stop.set()


def run_owned(directory, attach=True, home=None):
    if attach and os.name != 'nt':
        existing = legacy_service(Path(home or Path.home()))
        if existing:
            print(json.dumps(existing), flush=True)
            # Explicit app quit stops its attached supervisor, not client turns.
            for line in sys.stdin:
                if line.strip() == "stop":
                    subprocess.run([sys.executable, str(Path(existing["config"]).parent / "guardian.py"),
                                    "--config", existing["config"], "stop"], timeout=8, capture_output=True)
                    subprocess.run([sys.executable, str(Path(existing["config"]).parent / "ui.py"),
                                    "stop", "--config", existing["config"]], timeout=8, capture_output=True)
                    deadline = time.monotonic() + 35
                    while locked(Path(existing["state_dir"]) / "daemon.lock") and time.monotonic() < deadline:
                        time.sleep(.5)
                    break
            return
    with socket.socket() as check:
        check.bind(("127.0.0.1", 0))
        port = check.getsockname()[1]
    config_path = make_config(directory, home, port, os.getpid())
    from ui import make_server
    from guardian import Store
    server = make_server(config_path, port)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    stop = threading.Event()
    stop_detail = {}
    threading.Thread(target=read_host_input, args=(sys.stdin, stop, stop_detail), daemon=True).start()
    with (Path(directory) / "backend.log").open("ab") as log:
        daemon = subprocess.Popen(python_command(ROOT / "guardian.py", "--config", config_path, "run", isolated=True),
            stdout=log, stderr=log, stdin=subprocess.DEVNULL,
            **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
        print(json.dumps({"url": "http://127.0.0.1:%s" % port, "external": False, "owned": True,
            "state_dir": str(Path(directory) / "state"), "config": str(config_path)}), flush=True)
        try:
            while not stop.wait(.5):
                if daemon.poll() is not None:
                    # Do not silently reissue stop requests; a user can reopen.
                    break
        finally:
            exit_reason = stop_detail.get('reason', 'daemon_exited')
            ledger = Store(Path(directory) / "state")
            ledger.put("stop_requested", True)
            ledger.close()
            server.shutdown()
            server.server_close()
            try:
                daemon.wait(timeout=35)
            except subprocess.TimeoutExpired:
                daemon.terminate()
                try:
                    daemon.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    daemon.kill()
                    daemon.wait(timeout=5)
            print(json.dumps({'host_exit': {'reason':exit_reason,
                                           'daemon_exit_code':daemon.poll()}}), file=sys.stderr, flush=True)


def self_test():
    import asyncio
    import hashlib
    import ssl
    import tempfile
    import ui, desktop, immediate, plans, catalog, stages
    runtime = ROOT.parent / "python"
    if os.name == "nt":
        runtime = ROOT.parent / "runtime/python"
    if runtime.is_dir():
        assert Path(sys.prefix).resolve() == runtime.resolve(), "Runtime escaped application bundle"
    with tempfile.TemporaryDirectory() as temp:
        path = make_config(Path(temp), Path(temp) / "fake-home", 0)
        from guardian import load_config, Store
        cfg = load_config(path)
        store = Store(cfg["state_dir"])
        assert store.get("supervisor_paused") is True
        assert cfg["runtime_root"] == str(ROOT)
        store.close()
    print(json.dumps({"runtime": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
                      "ssl": ssl.OPENSSL_VERSION, "portable_config": True, "private_data_loaded": False,
                      "all_backend_imports": True, "runtime_inside_bundle": runtime.is_dir()}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=support_directory())
    parser.add_argument("--no-attach", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--migrate", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.migrate:
        migrate_legacy(args.directory)
    else:
        run(args.directory, not args.no_attach)
