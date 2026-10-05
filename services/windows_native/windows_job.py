"""Native process containment and one server per durable data root."""
import ctypes
from ctypes import wintypes
import os

from .contracts import WorkflowError

_job_handle = None


def contain_process_tree():
    global _job_handle
    if os.name != "nt":
        raise WorkflowError("WINDOWS_NATIVE_REQUIRED")
    if _job_handle:
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    class Basic(ctypes.Structure):
        _fields_ = [("per_process", ctypes.c_int64), ("per_job", ctypes.c_int64),
                    ("flags", wintypes.DWORD), ("min_ws", ctypes.c_size_t), ("max_ws", ctypes.c_size_t),
                    ("active", wintypes.DWORD), ("affinity", ctypes.c_size_t),
                    ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(k, ctypes.c_uint64) for k in ("read_op", "write_op", "other_op", "read_bytes", "write_bytes", "other_bytes")]

    class Extended(ctypes.Structure):
        _fields_ = [("basic", Basic), ("io", IO), ("process_memory", ctypes.c_size_t),
                    ("job_memory", ctypes.c_size_t), ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]

    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    handle = kernel.CreateJobObjectW(None, None)
    info = Extended()
    info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not handle or not kernel.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)) or not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        raise WorkflowError("WINDOWS_CHILD_CONTAINMENT_UNAVAILABLE")
    # Non-inheritable handle stays open only in the parent; OS closes it on exit.
    _job_handle = handle


def lock_data_root(root):
    import msvcrt
    root.mkdir(parents=True, exist_ok=True)
    handle = (root / ".server.lock").open("a+b")
    try:
        handle.seek(0)
        if not handle.read(1):
            handle.write(b"1")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        raise WorkflowError("DATA_ROOT_ALREADY_IN_USE") from None
    return handle
