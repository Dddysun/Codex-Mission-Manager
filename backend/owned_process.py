"""Bounded cleanup of a family created by this application, never a desktop client."""
import ctypes
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import time

IS_WINDOWS = os.name == 'nt'


class WindowsJob:
    """A non-inherited handle makes every assigned descendant die with its host."""
    def __init__(self):
        from ctypes import wintypes as w
        class Limits(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                        ('flags', w.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
                        ('active_limit', w.DWORD), ('affinity', ctypes.c_size_t),
                        ('priority', w.DWORD), ('scheduling', w.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]
        class Extended(ctypes.Structure):
            _fields_ = [('limits', Limits), ('io', IO), ('process_memory', ctypes.c_size_t),
                        ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t),
                        ('peak_job', ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        k = self.kernel
        k.CreateJobObjectW.argtypes = (ctypes.c_void_p, w.LPCWSTR)
        k.CreateJobObjectW.restype = w.HANDLE
        k.SetInformationJobObject.argtypes = (w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD)
        k.SetInformationJobObject.restype = w.BOOL
        k.AssignProcessToJobObject.argtypes = (w.HANDLE, w.HANDLE)
        k.AssignProcessToJobObject.restype = w.BOOL
        k.TerminateJobObject.argtypes = (w.HANDLE, w.UINT)
        k.TerminateJobObject.restype = w.BOOL
        k.QueryInformationJobObject.argtypes = (w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p)
        k.QueryInformationJobObject.restype = w.BOOL
        k.CloseHandle.argtypes = (w.HANDLE,)
        k.CloseHandle.restype = w.BOOL
        self.handle = k.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = Extended()
        info.limits.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
        if not k.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            code = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(code)

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def active(self):
        # JOBOBJECT_BASIC_ACCOUNTING_INFORMATION: four LARGE_INTEGERs, four DWORDs.
        info = ctypes.create_string_buffer(48)
        if not self.kernel.QueryInformationJobObject(self.handle, 1, info, len(info), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return ctypes.c_uint32.from_buffer(info, 40).value

    def terminate(self):
        if not self.kernel.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            handle, self.handle = self.handle, None
            self.kernel.CloseHandle(handle)


class OwnedProcess:
    def __init__(self, script, args=(), *, stdout=None, stderr=None):
        self.process = None
        self._result = None
        self.job = WindowsJob() if IS_WINDOWS else None
        assigned = False
        command = [sys.executable, '-X', 'utf8', '-I', str(Path(__file__).resolve()),
                   '--bootstrap', str(Path(script).resolve())] + list(map(str, args))
        options = ({'creationflags': subprocess.CREATE_NO_WINDOW} if IS_WINDOWS
                   else {'start_new_session': True})
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE,
                stdout=stdout, stderr=stderr, **options)
            # Bootstrap cannot run the script or spawn RPC until assignment succeeds.
            if self.job:
                self.job.assign(self.process)
                assigned = True
            self.process.stdin.write(b'1')
            self.process.stdin.flush()
            self.process.stdin.close()
        except BaseException:
            if self.process:
                if self.process.stdin and not self.process.stdin.closed:
                    self.process.stdin.close()
                if self.job and assigned:
                    self.job.close()
                elif not IS_WINDOWS:
                    self._signal(force=True)
                elif self.process.poll() is None:
                    self.process.kill()  # Assignment failed; bootstrap is still gated.
                try:
                    self.process.wait(timeout=.5)
                except subprocess.TimeoutExpired:
                    pass
            if self.job:
                self.job.close()
            raise

    def _alive(self):
        if self.job:
            return self.job.active() != 0
        try:
            os.killpg(self.process.pid, 0)  # Only our newly created private group.
            return True
        except ProcessLookupError:
            return False

    def _signal(self, force=False):
        if self.job:
            self.job.terminate()
        else:
            try:
                os.killpg(self.process.pid, signal.SIGKILL if force else signal.SIGTERM)
            except ProcessLookupError:
                pass

    def stop(self, *, deadline=None, grace_seconds=3):
        if self._result is not None:
            return self._result
        deadline = time.monotonic() + 5 if deadline is None else deadline
        errors = []
        forced = False
        grace = min(deadline - .8, time.monotonic() + grace_seconds)
        try:
            while self.process.poll() is None and time.monotonic() < grace:
                time.sleep(min(.03, max(0, grace - time.monotonic())))
            # A leader's exit is not proof its RPC descendants exited as well.
            if self._alive():
                forced = True
                self._signal()
            soft_end = min(deadline - .3, time.monotonic() + .5)
            while self._alive() and time.monotonic() < soft_end:
                self.process.poll()
                time.sleep(.02)
            if self._alive():
                self._signal(force=True)
        except OSError as exc:
            errors.append(type(exc).__name__)
        finally:
            if self.job:
                # Also protects against a racing child or failed termination call.
                self.job.close()
            try:
                self.process.wait(timeout=max(.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                errors.append('owned_process_wait_timeout')
        self._result = {'forced': forced, 'daemon_exit_code': self.process.poll(), 'errors': errors}
        return self._result


def bootstrap():
    if len(sys.argv) < 3 or sys.argv[1] != '--bootstrap' or sys.stdin.buffer.read(1) != b'1':
        return 2
    script, args = sys.argv[2], sys.argv[3:]
    sys.stdin.close()
    sys.stdin = open(os.devnull, encoding='utf-8')
    sys.argv = [script] + args
    runpy.run_path(script, run_name='__main__')
    return 0


if __name__ == '__main__':
    raise SystemExit(bootstrap())
