"""App-owned backend host. Resources are immutable; user data stays outside .app."""
import argparse
from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import socket
import signal
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
from owned_process import OwnedProcess

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
    try:
        for line in stream:
            if line.strip() == 'stop':
                detail['reason'] = 'requested'
                stop.set()
                return
        detail['reason'] = 'parent_input_closed'
    except OSError:
        detail['reason'] = 'parent_input_error'
    finally:
        stop.set()


@contextmanager
def host_signals(stop, detail):
    previous = {}
    if threading.current_thread() is threading.main_thread():
        def stopping(number, frame):
            detail['reason'] = 'signal'
            stop.set()
        for number in (signal.SIGTERM, signal.SIGINT):
            previous[number] = signal.signal(number, stopping)
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def request_owned_stop(directory, process, cancelled):
    """A short SQLite transaction cannot outlive cancellation and stop a new owner."""
    path = Path(directory) / 'state/guardian.sqlite3'
    if cancelled.is_set() or not path.is_file():
        return False
    with closing(sqlite3.connect(str(path), timeout=.15)) as db:
        with db:
            db.execute('BEGIN IMMEDIATE')
            # Check AFTER acquiring the writer lock. A timed-out worker must not
            # later overwrite a replacement daemon's stop flag.
            if cancelled.is_set() or process.poll() is not None:
                return False
            row = db.execute("SELECT value FROM kv WHERE key='last_report'").fetchone()
            if not row or json.loads(row[0]).get('pid') != process.pid:
                return False
            db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)', ('stop_requested', 'true'))
    return True


def close_http_server(server):
    def closing_server():
        try:
            server.shutdown()
        finally:
            server.server_close()
    thread = threading.Thread(target=closing_server, daemon=True)
    thread.start()
    return thread


def shutdown_owned(owned, server, directory, *, budget=5, grace_seconds=3):
    deadline = time.monotonic() + budget
    cancelled, errors = threading.Event(), []
    http = close_http_server(server) if server else None
    def stop_ledger():
        try:
            request_owned_stop(directory, owned.process, cancelled)
        except (OSError, sqlite3.Error, ValueError):
            errors.append('stop_flag_unavailable')
    ledger = threading.Thread(target=stop_ledger, daemon=True)
    ledger.start()
    try:
        result = owned.stop(deadline=deadline, grace_seconds=grace_seconds)
    finally:
        cancelled.set()
        # These helpers must never hold process-family cleanup hostage.
        ledger.join(timeout=max(0, min(.05, deadline - time.monotonic())))
        if http:
            http.join(timeout=max(0, min(.1, deadline - time.monotonic())))
            if http.is_alive():
                errors.append('http_shutdown_timeout')
                try:
                    server.socket.close()
                except OSError:
                    pass
    result['errors'].extend(errors)
    return result


def run_owned(directory, attach=True, home=None):
    stop, stop_detail = threading.Event(), {}
    with host_signals(stop, stop_detail):
        if attach and not IS_WINDOWS:
            existing = legacy_service(Path(home or Path.home()))
            if existing:
                print(json.dumps(existing), flush=True)
                threading.Thread(target=read_host_input, args=(sys.stdin, stop, stop_detail), daemon=True).start()
                stop.wait()
                # This host only attached to a shared service. Detach on quit.
                return
        with socket.socket() as check:
            check.bind(("127.0.0.1", 0))
            port = check.getsockname()[1]
        config_path = make_config(directory, home, port, os.getpid())
        if stop.is_set():
            return
        from ui import make_server
        server, owned, log = None, None, None
        try:
            server = make_server(config_path, port)
            server.daemon_threads = True
            server.block_on_close = False
            threading.Thread(target=lambda: server.serve_forever(poll_interval=.1), daemon=True).start()
            threading.Thread(target=read_host_input, args=(sys.stdin, stop, stop_detail), daemon=True).start()
            if stop.is_set():
                return
            log = (Path(directory) / 'backend.log').open('ab')
            owned = OwnedProcess(ROOT / 'guardian.py', ('--config', config_path, 'run'), stdout=log, stderr=log)
            print(json.dumps({"url": "http://127.0.0.1:%s" % port, "external": False, "owned": True,
                "state_dir": str(Path(directory) / "state"), "config": str(config_path)}), flush=True)
            while not stop.wait(.1):
                if owned.process.poll() is not None:
                    break
        finally:
            if owned:
                result = shutdown_owned(owned, server, directory)
            else:
                result = {'daemon_exit_code': None, 'errors': []}
                if server:
                    closing = close_http_server(server)
                    closing.join(timeout=.2)
                    if closing.is_alive():
                        server.socket.close()
            if log:
                log.close()
            result['reason'] = stop_detail.get('reason', 'daemon_exited')
            print(json.dumps({'host_exit': result}), file=sys.stderr, flush=True)


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
