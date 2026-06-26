"""
server/pidlock.py

安全 PID 文件锁 — 防止 MCP 僵尸进程堆积。

设计原则：
- 只杀命令行包含 "sp_mcp.py" 的进程（双重校验，绝不误杀）
- atexit 正常退出时自动清理 PID 文件
- 旧进程不存在时静默覆盖
- 用 psutil？不用 —— 保持零依赖，纯 stdlib
"""

import atexit
import os
import sys
import time
import signal
import ctypes
import subprocess
import logging

log = logging.getLogger(__name__)

_PID_FILE = os.path.join(
    os.environ.get("TEMP", os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp")),
    "sp_mcp_server.pid"
)

_OLD_PID_KILL_TIMEOUT_S = 5  # 等旧进程死的最大秒数


def _process_exists(pid: int) -> bool:
    """检查 PID 对应的进程是否存活（Windows 兼容）。

    使用 WaitForSingleObject 而非仅检查 OpenProcess，
    因为已退出但句柄未释放的进程仍可能被 OpenProcess 打开。
    """
    kernel32 = ctypes.windll.kernel32
    SYNCHRONIZE = 0x00100000
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if handle == 0:
        return False
    # WaitForSingleObject(handle, 0):
    #   WAIT_OBJECT_0 (0x00000000) — 进程已退出
    #   WAIT_TIMEOUT  (0x00000102) — 进程仍在运行
    WAIT_TIMEOUT = 0x00000102
    ret = kernel32.WaitForSingleObject(handle, 0)
    kernel32.CloseHandle(handle)
    return ret == WAIT_TIMEOUT


def _get_process_cmdline(pid: int) -> str:
    """获取进程命令行（仅用于校验是本项目进程）。

    不依赖已废弃的 wmic（在新版 Windows 11 上可能已移除，且在受限环境
    返回空字符串）。优先用 ctypes 直接读目标进程 PEB 中的命令行；失败再
    回退到 PowerShell 的 CIM 查询。两条路径都失败时返回空字符串，调用方
    据此跳过 kill（安全第一）。
    """
    cmd = _cmdline_via_peb(pid)
    if cmd:
        return cmd
    return _cmdline_via_powershell(pid)


def _cmdline_via_peb(pid: int) -> str:
    """通过 ntdll 读取目标进程 PEB 中的命令行（纯 ctypes，无外部进程）。

    仅支持 64 位 Windows（本项目运行环境）。任何异常或读取失败都返回
    空字符串，由上层回退。
    """
    try:
        kernel32 = ctypes.windll.kernel32
        ntdll = ctypes.windll.ntdll

        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid
        )
        if not handle:
            return ""
        try:
            class PROCESS_BASIC_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("Reserved1", ctypes.c_void_p),
                    ("PebBaseAddress", ctypes.c_void_p),
                    ("Reserved2", ctypes.c_void_p * 2),
                    ("UniqueProcessId", ctypes.c_void_p),
                    ("Reserved3", ctypes.c_void_p),
                ]

            pbi = PROCESS_BASIC_INFORMATION()
            ret_len = ctypes.c_ulong(0)
            status = ntdll.NtQueryInformationProcess(
                handle, 0, ctypes.byref(pbi),
                ctypes.sizeof(pbi), ctypes.byref(ret_len),
            )
            if status != 0 or not pbi.PebBaseAddress:
                return ""

            def _read(addr, size):
                buf = ctypes.create_string_buffer(size)
                nread = ctypes.c_size_t(0)
                ok = kernel32.ReadProcessMemory(
                    handle, ctypes.c_void_p(addr), buf,
                    size, ctypes.byref(nread),
                )
                if not ok or nread.value != size:
                    return None
                return buf.raw

            ptr_size = ctypes.sizeof(ctypes.c_void_p)
            peb = ctypes.cast(pbi.PebBaseAddress, ctypes.c_void_p).value
            # PEB 偏移 0x20（x64）指向 RTL_USER_PROCESS_PARAMETERS 指针
            params_ptr_raw = _read(peb + 0x20, ptr_size)
            if not params_ptr_raw:
                return ""
            params_ptr = int.from_bytes(params_ptr_raw, "little")
            if not params_ptr:
                return ""
            # RTL_USER_PROCESS_PARAMETERS 偏移 0x70（x64）是 CommandLine
            # UNICODE_STRING：USHORT Length, USHORT MaximumLength, padding, PWSTR Buffer
            us_raw = _read(params_ptr + 0x70, 8 + ptr_size)
            if not us_raw:
                return ""
            length = int.from_bytes(us_raw[0:2], "little")
            buf_ptr = int.from_bytes(us_raw[8:8 + ptr_size], "little")
            if not buf_ptr or length == 0:
                return ""
            data = _read(buf_ptr, length)
            if not data:
                return ""
            return data.decode("utf-16-le", errors="replace")
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ""


def _cmdline_via_powershell(pid: int) -> str:
    """回退方案：用 PowerShell 的 CIM 查询命令行（不依赖 wmic）。"""
    try:
        ps_cmd = (
            "(Get-CimInstance Win32_Process -Filter "
            f"\"ProcessId={int(pid)}\").CommandLine"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.stdout or ""
    except Exception:
        return ""


def _ensure_parent_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)


def _kill_process(pid: int) -> bool:
    """温和杀进程：先 SIGTERM（ctrl+c），超时后 SIGKILL。"""
    try:
        handle = ctypes.windll.kernel32.OpenProcess(1, False, pid)  # PROCESS_TERMINATE
        if handle:
            ctypes.windll.kernel32.TerminateProcess(handle, 0)
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
    except Exception:
        pass
    return False


def _cleanup_pid_file() -> None:
    """退出时删除 PID 文件。"""
    try:
        if os.path.isfile(_PID_FILE):
            with open(_PID_FILE, "r") as f:
                stored = f.read().strip()
            if stored == str(os.getpid()):
                os.remove(_PID_FILE)
                log.debug("Removed PID file %s", _PID_FILE)
    except Exception:
        pass


def acquire_pid_lock() -> None:
    """
    安全获取 PID 锁：
    1. 读旧 PID 文件
    2. 验证旧进程存在且命令行含 'sp_mcp.py'（双重校验）
    3. 满足条件才杀旧进程
    4. 等旧进程退出（最多 5s）
    5. 写新 PID 文件
    6. 注册 atexit 清理
    """
    _ensure_parent_dir(_PID_FILE)
    current_pid = os.getpid()

    # Step 1: 读旧 PID
    old_pid = None
    if os.path.isfile(_PID_FILE):
        try:
            with open(_PID_FILE, "r") as f:
                old_pid_str = f.read().strip()
            old_pid = int(old_pid_str)
        except (ValueError, OSError):
            old_pid = None

    # Step 2: 验证旧进程 === 我们的 sp_mcp.py
    if old_pid and old_pid != current_pid and _process_exists(old_pid):
        cmdline = _get_process_cmdline(old_pid)

        if "sp_mcp.py" in cmdline:
            log.info(
                "Found existing sp_mcp.py process (PID %d), terminating...", old_pid
            )
            _kill_process(old_pid)

            # Step 3: 等它死
            for _ in range(_OLD_PID_KILL_TIMEOUT_S * 2):
                time.sleep(0.5)
                if not _process_exists(old_pid):
                    log.info("Old process (PID %d) terminated.", old_pid)
                    break
            else:
                log.warning(
                    "Old process (PID %d) did not terminate in %ds, continuing anyway.",
                    old_pid, _OLD_PID_KILL_TIMEOUT_S,
                )
        else:
            # PID 文件在，但进程不是 sp_mcp —— 不杀（安全第一）
            log.debug(
                "PID file points to PID %d but cmdline does NOT contain 'sp_mcp.py'"
                " (got: %r). Skipping kill.",
                old_pid, cmdline[:200],
            )

    elif old_pid and old_pid == current_pid:
        # 自己遗留的文件，更新即可（理论上不会走到这里）
        log.debug("PID file already points to current process.")

    # Step 4: 写新 PID
    with open(_PID_FILE, "w") as f:
        f.write(str(current_pid))

    # Step 5: 注册退出清理
    atexit.register(_cleanup_pid_file)

    log.info("PID lock acquired (PID=%d, file=%s)", current_pid, _PID_FILE)
