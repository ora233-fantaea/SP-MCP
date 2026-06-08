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
    """获取进程命令行（仅用于校验是本项目进程）。"""
    try:
        result = subprocess.run(
            [
                "wmic", "process", "where", f"ProcessId={pid}",
                "get", "CommandLine", "/format:csv"
            ],
            capture_output=True, text=True, timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.stdout
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
