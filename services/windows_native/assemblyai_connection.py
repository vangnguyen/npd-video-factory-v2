"""Owner-entered AssemblyAI connection; no audio upload or paid ASR dispatch."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import uuid

from .contracts import WorkflowError, file_sha
from .hardening import durable_json
from .ingestion import API_ROOT  # Establish the existing pure API contract namespace.
from app.assemblyai_asr_profile import assemblyai_asr_profile, assemblyai_profile_sha256

PREFIX = b"VF-AADPAPI1\0"
ENTROPY = b"VideoFactory-AssemblyAI-Windows-v1"
VERIFY_URL = "https://api.assemblyai.com/v2/transcript?limit=1"


def validate_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._-]{16,512}", value.strip()):
        raise WorkflowError("ASSEMBLYAI_KEY_FORMAT_INVALID", 400)
    return value.strip()


def credential_path(config):
    supplied = Path(config.assemblyai_secret_file)
    repo = Path(__file__).resolve().parents[2]
    if supplied.is_symlink() or any(p.is_symlink() for p in supplied.parents):
        raise WorkflowError("ASSEMBLYAI_SECRET_PATH_INVALID", 400)
    path = supplied.resolve()
    for protected in (repo.resolve(), config.data_root.resolve(), config.runtime_root.resolve(),
                      Path(r"C:\NPD-Video-Factory\outputs\MVP1").resolve()):
        if path == protected or protected in path.parents:
            raise WorkflowError("ASSEMBLYAI_SECRET_MUST_BE_OUTSIDE_REPO_DATA_RUNTIME_MVP", 400)
    return path


def _dpapi(value, *, decrypt=False):
    if os.name != "nt":
        raise WorkflowError("ASSEMBLYAI_WINDOWS_SECRET_STORAGE_REQUIRED", 503)
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    raw_buffer, entropy_buffer = ctypes.create_string_buffer(value), ctypes.create_string_buffer(ENTROPY)
    raw = Blob(len(value), ctypes.cast(raw_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    entropy = Blob(len(ENTROPY), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]; kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        function = crypt.CryptUnprotectData
        function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                             ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        description = None
    else:
        function = crypt.CryptProtectData
        function.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.POINTER(Blob),
                             ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        description = "Video Factory AssemblyAI"
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(raw), description, ctypes.byref(entropy), None, None, 1, ctypes.byref(output)):
        raise WorkflowError("ASSEMBLYAI_WINDOWS_SECRET_PROTECTION_FAILED", 503)
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.memset(output.data, 0, output.size)
        kernel.LocalFree(output.data)
        ctypes.memset(raw_buffer, 0, len(value))


def _restrict_file(path):
    """Protected DACL grants only the current Windows user and LocalSystem."""
    if os.name != "nt":
        raise WorkflowError("ASSEMBLYAI_WINDOWS_SECRET_STORAGE_REQUIRED", 503)
    kernel, advapi = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]; kernel.LocalFree.restype = ctypes.c_void_p
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    advapi.GetSecurityDescriptorDacl.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL)]
    advapi.GetSecurityDescriptorDacl.restype = wintypes.BOOL
    advapi.SetNamedSecurityInfoW.argtypes = [wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    advapi.SetNamedSecurityInfoW.restype = wintypes.DWORD
    token, sid_text, descriptor = wintypes.HANDLE(), wintypes.LPWSTR(), ctypes.c_void_p()
    try:
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
            raise OSError()
        required = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(required))
        data = ctypes.create_string_buffer(required.value)
        if not advapi.GetTokenInformation(token, 1, data, required, ctypes.byref(required)):
            raise OSError()
        sid = ctypes.cast(data, ctypes.POINTER(ctypes.c_void_p))[0]
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(sid_text)):
            raise OSError()
        sddl = f"D:P(A;;FA;;;SY)(A;;FA;;;{sid_text.value})"
        if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None):
            raise OSError()
        present, defaulted, dacl = wintypes.BOOL(), wintypes.BOOL(), ctypes.c_void_p()
        if not advapi.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)) or not present.value:
            raise OSError()
        if advapi.SetNamedSecurityInfoW(str(path), 1, 4 | 0x80000000, None, None, dacl, None) != 0:
            raise OSError()
    except Exception:
        raise WorkflowError("ASSEMBLYAI_SECRET_FILE_PERMISSIONS_FAILED", 503) from None
    finally:
        if descriptor: kernel.LocalFree(descriptor)
        if sid_text: kernel.LocalFree(ctypes.cast(sid_text, ctypes.c_void_p))
        if token: kernel.CloseHandle(token)


def load_credential(config):
    path = credential_path(config)
    try:
        if not path.is_file() or path.stat().st_size > 16384:
            raise ValueError()
        raw = path.read_bytes()
        if not raw.startswith(PREFIX):
            raise ValueError()
        return validate_key(_dpapi(raw[len(PREFIX):], decrypt=True).decode("ascii"))
    except Exception:
        raise WorkflowError("ASSEMBLYAI_CREDENTIAL_UNAVAILABLE", 503) from None


def _save_credential(config, key):
    path = credential_path(config)
    encrypted = PREFIX + _dpapi(key.encode("ascii"))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / (".assemblyai-" + uuid.uuid4().hex + ".part")
    try:
        with temp.open("xb") as handle:
            _restrict_file(temp)
            handle.write(encrypted); handle.flush(); os.fsync(handle.fileno())
        # Windows rename is atomic and refuses an existing destination.
        os.rename(temp, path)
    except FileExistsError:
        raise WorkflowError("ASSEMBLYAI_CREDENTIAL_ALREADY_SAVED", 409) from None
    finally:
        temp.unlink(missing_ok=True)


def verify_credential(key):
    import httpx2
    logging.getLogger("httpx2").disabled = True
    timeout = httpx2.Timeout(15.0, connect=5.0)
    try:
        with httpx2.Client(timeout=timeout, trust_env=False, follow_redirects=False) as client:
            with client.stream("GET", VERIFY_URL, headers={"authorization": key}) as response:
                status = response.status_code
    except Exception:
        raise WorkflowError("ASSEMBLYAI_CONNECTION_UNAVAILABLE", 503) from None
    if status in {401, 403}:
        raise WorkflowError("ASSEMBLYAI_AUTHENTICATION_FAILED", 400)
    if status == 429:
        raise WorkflowError("ASSEMBLYAI_CONNECTION_RATE_LIMITED", 503)
    if status != 200:
        raise WorkflowError("ASSEMBLYAI_CONNECTION_CHECK_FAILED", 503)
    return {"verification_http_calls": 1, "transcription_calls": 0, "audio_uploaded": False}


def status(config):
    path = credential_path(config)
    result = {"provider": "assemblyai-transcription", "profile_id": assemblyai_asr_profile().profile_id,
              "model": assemblyai_asr_profile().model, "language": "vi", "credential_saved": path.is_file(),
              "connected": False, "speech_video_acceptance": "NOT_RUN"}
    receipt = config.data_root / "assemblyai-connection.json"
    if path.is_file() and receipt.is_file():
        try:
            record = json.loads(receipt.read_bytes())
            if record.get("credential_cipher_sha256") == file_sha(path) and record.get("profile_sha256") == assemblyai_profile_sha256():
                result.update(connected=record["status"] == "verified", checked_at=record["checked_at"])
        except (ValueError, KeyError, OSError):
            pass
    return result


def connect(config, key=None):
    path = credential_path(config)
    key = load_credential(config) if key is None else validate_key(key)
    if path.exists() and load_credential(config) != key:
        raise WorkflowError("ASSEMBLYAI_CREDENTIAL_ALREADY_SAVED", 409)
    try:
        checks = verify_credential(key)
    except WorkflowError as error:
        if path.is_file():
            durable_json(config.data_root / "assemblyai-connection.json", {
                "status": "verification_failed", "checked_at": datetime.now(timezone.utc).isoformat(),
                "profile_sha256": assemblyai_profile_sha256(), "credential_cipher_sha256": file_sha(path),
                "error_code": error.code, "transcription_calls": 0, "audio_uploaded": False})
        raise
    if not path.exists():
        _save_credential(config, key)
    durable_json(config.data_root / "assemblyai-connection.json", {
        "status": "verified", "checked_at": datetime.now(timezone.utc).isoformat(),
        "provider": "assemblyai-transcription", "profile_sha256": assemblyai_profile_sha256(),
        "credential_cipher_sha256": file_sha(path), **checks})
    return {**status(config), **checks}
