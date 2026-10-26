"""Small OS boundaries; Windows checks never signal an arbitrary process."""
import errno
import os
from pathlib import Path
import sys
import tempfile

IS_WINDOWS = os.name == 'nt'


def private_directory(path, *, enforce_mode=False):
    """Use inherited Windows ACLs; POSIX keeps its existing private modes."""
    directory = Path(path)
    if IS_WINDOWS:
        # Python 3.13 treats mode 0700 specially on Windows. An elevated
        # creator can then exclude the same user's normal desktop token.
        directory.mkdir(parents=True, exist_ok=True)
    else:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if enforce_mode:
            os.chmod(directory, 0o700)
    return directory


def private_file_permissions(path):
    if not IS_WINDOWS:
        os.chmod(path, 0o600)


def check_writable_directory(directory, existing_files=()):
    """Check real file access without changing existing contents or ACLs."""
    directory = Path(directory)
    target = directory
    try:
        with tempfile.TemporaryFile(prefix='.write-check-', dir=directory) as probe:
            probe.write(b'write-check')
            probe.flush()
            os.fsync(probe.fileno())
        for name in existing_files:
            target = directory / name
            if target.exists():
                # Request write access, but do not modify user data to test it.
                with target.open('r+b'):
                    pass
    except OSError as exc:
        raise RuntimeError(
            'app_data_not_writable: Application data cannot be written: %s. '
            'Check free disk space and ask the folder owner or administrator '
            'to restore write access for your account, then reopen the app '
            'normally. Existing permissions were not changed.' % target) from exc


def lock_file(stream):
    """Take a nonblocking exclusive lock until the stream is closed."""
    if os.name != 'nt':
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    import msvcrt
    stream.seek(0, os.SEEK_END)
    if stream.tell() == 0:
        stream.write(b'\0')
        stream.flush()
    stream.seek(0)
    try:
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            raise BlockingIOError(exc.errno, 'instance lock is already held') from exc
        raise


def open_lock(path):
    return Path(path).open('a+b')


def lock_held(path, create=True):
    path = Path(path)
    if not create and not path.exists():
        return False
    with open_lock(path) as stream:
        try:
            lock_file(stream)
            return False
        except BlockingIOError:
            return True


def process_alive(pid):
    try:
        pid = int(pid)
        if pid <= 0:
            return False
    except (ValueError, TypeError):
        return False
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only.
        if not handle:
            return ctypes.get_last_error() == 5  # Access denied is not proof of exit.
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258  # WAIT_TIMEOUT
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def sqlite_ro_uri(path):
    return Path(path).resolve().as_uri() + '?mode=ro'


def support_directory():
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA', Path.home()/'AppData/Local'))/'CodexMissionManager'
    return Path.home()/'Library/Application Support/CodexMissionManager'


def python_command(script, *args, isolated=False):
    command = [sys.executable, '-X', 'utf8']
    if isolated:
        command.append('-I')
    return command + [str(script)] + list(map(str, args))


def verify_windows_pipe_server(pipe_handle, expected_root):
    """Attest the connected local pipe server's installed path and user SID."""
    if os.name != 'nt':
        raise OSError('Windows pipe verification is only available on Windows')
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel.GetNamedPipeServerProcessId.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG))
    kernel.GetNamedPipeServerProcessId.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    advapi.OpenProcessToken.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE))
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.EqualSid.argtypes = (wintypes.LPVOID, wintypes.LPVOID)
    advapi.EqualSid.restype = wintypes.BOOL
    pid = wintypes.ULONG()
    if not kernel.GetNamedPipeServerProcessId(int(pipe_handle), ctypes.byref(pid)):
        raise ctypes.WinError(ctypes.get_last_error())
    process = kernel.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
    if not process:
        raise ctypes.WinError(ctypes.get_last_error())
    def user_token(process_handle):
        token = wintypes.HANDLE()
        if not advapi.OpenProcessToken(process_handle, 0x0008, ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            size = wintypes.DWORD()
            advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            buffer = ctypes.create_string_buffer(size.value)
            if not advapi.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            return buffer
        finally:
            kernel.CloseHandle(token)
    try:
        size = wintypes.DWORD(32768)
        path = ctypes.create_unicode_buffer(size.value)
        if not kernel.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        target = Path(path.value).resolve()
        root = Path(expected_root).resolve()
        if not target.is_relative_to(root) or target.suffix.lower() != '.exe':
            raise PermissionError('desktop pipe server is outside the installed OpenAI package')
        actual, current = user_token(process), user_token(kernel.GetCurrentProcess())
        actual_sid = ctypes.cast(actual, ctypes.POINTER(ctypes.c_void_p))[0]
        current_sid = ctypes.cast(current, ctypes.POINTER(ctypes.c_void_p))[0]
        if not advapi.EqualSid(actual_sid, current_sid):
            raise PermissionError('desktop pipe server belongs to a different Windows user')
        return {'pid':pid.value,'same_user':True,'installed_package_path':True}
    finally:
        kernel.CloseHandle(process)
