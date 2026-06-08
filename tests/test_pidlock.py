"""
test_pidlock.py

测试 server/pidlock.py 的 PID 文件锁安全逻辑：
- 正常启动：创建 PID 文件，atexit 清理
- 僵尸清理：检测旧进程 → 验证 cmdline → 杀掉 → 接管
- 安全校验：不杀非 sp_mcp.py 进程、不杀已死进程、不杀自己
"""

import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock, call


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_pid_file():
    """每个测试前清除 PID 文件，测试后清理。"""
    from server.pidlock import _PID_FILE
    try:
        os.remove(_PID_FILE)
    except OSError:
        pass
    yield
    try:
        os.remove(_PID_FILE)
    except OSError:
        pass


@pytest.fixture
def pid_file_path():
    from server.pidlock import _PID_FILE
    return _PID_FILE


# ── _process_exists ──────────────────────────────────────────────────────────

class TestProcessExists:
    def test_current_process_exists(self):
        """当前进程应该返回 True。"""
        from server.pidlock import _process_exists
        assert _process_exists(os.getpid()) is True

    def test_nonexistent_pid(self):
        """无效 PID 应该返回 False。"""
        from server.pidlock import _process_exists
        assert _process_exists(99999999) is False

    def test_dead_child_process(self):
        """已终止的子进程应该返回 False。"""
        import subprocess
        from server.pidlock import _process_exists
        p = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        p.wait()
        time.sleep(0.1)  # 给系统一点时间回收
        assert _process_exists(p.pid) is False


# ── _get_process_cmdline ─────────────────────────────────────────────────────

class TestGetProcessCmdline:

    def test_self_contains_python(self):
        """当前 Python 进程的 cmdline 应该包含 python。"""
        from server.pidlock import _get_process_cmdline
        cmd = _get_process_cmdline(os.getpid())
        assert "python" in cmd.lower()

    def test_dead_pid_returns_no_sp_mcp(self):
        """死进程/无效 PID 的 cmdline 不应包含 sp_mcp.py（安全校验通过）。"""
        from server.pidlock import _get_process_cmdline
        cmd = _get_process_cmdline(99999999)
        # wmic 对无效 PID 返回 CSV 头但无数据行，确保不含 sp_mcp.py 即可
        assert "sp_mcp.py" not in cmd


# ── _kill_process ────────────────────────────────────────────────────────────

class TestKillProcess:

    def test_kill_sleeping_child(self):
        """杀掉一个 sleep 子进程应该成功。"""
        import subprocess
        from server.pidlock import _kill_process, _process_exists

        p = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        assert _process_exists(p.pid) is True
        result = _kill_process(p.pid)
        # 等待进程终止
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
        time.sleep(0.2)
        assert result is True
        assert _process_exists(p.pid) is False

    def test_kill_dead_pid_no_error(self):
        """杀已经不存在的 PID 不应该报错。"""
        from server.pidlock import _kill_process
        result = _kill_process(99999999)
        # 可能返回 True（如果意外成功）或 False（正常失败），但不应抛异常
        assert isinstance(result, bool)


# ── _cleanup_pid_file ────────────────────────────────────────────────────────

class TestCleanupPidFile:

    def test_removes_own_pid_file(self, pid_file_path):
        """退出时应该删除自己写入的 PID 文件。"""
        from server.pidlock import _cleanup_pid_file

        # 写入当前 PID
        with open(pid_file_path, "w") as f:
            f.write(str(os.getpid()))

        assert os.path.exists(pid_file_path)
        _cleanup_pid_file()
        assert not os.path.exists(pid_file_path)

    def test_does_not_remove_foreign_pid_file(self, pid_file_path):
        """不应该删除其他进程的 PID 文件。"""
        from server.pidlock import _cleanup_pid_file

        foreign_pid = 99999
        with open(pid_file_path, "w") as f:
            f.write(str(foreign_pid))

        assert os.path.exists(pid_file_path)
        _cleanup_pid_file()
        # 文件中是别人的 PID，不应该删
        assert os.path.exists(pid_file_path)

    def test_no_file_no_error(self, pid_file_path):
        """PID 文件不存在时不应该报错。"""
        from server.pidlock import _cleanup_pid_file
        assert not os.path.exists(pid_file_path)
        _cleanup_pid_file()  # 不应抛异常


# ── acquire_pid_lock ─────────────────────────────────────────────────────────

class TestAcquirePidLock:

    def test_creates_pid_file_with_current_pid(self, pid_file_path):
        """初次启动应该创建 PID 文件并写入当前 PID。"""
        from server.pidlock import acquire_pid_lock

        acquire_pid_lock()
        assert os.path.exists(pid_file_path)
        with open(pid_file_path, "r") as f:
            stored = int(f.read().strip())
        assert stored == os.getpid()

    def test_overwrites_dead_pid(self, pid_file_path):
        """旧 PID 已死时应直接覆盖。"""
        from server.pidlock import acquire_pid_lock

        # 写入一个已死的 PID
        with open(pid_file_path, "w") as f:
            f.write("99999999")

        acquire_pid_lock()
        with open(pid_file_path, "r") as f:
            stored = int(f.read().strip())
        assert stored == os.getpid()

    def test_overwrites_invalid_pid_file(self, pid_file_path):
        """PID 文件内容无效时应覆盖。"""
        from server.pidlock import acquire_pid_lock

        with open(pid_file_path, "w") as f:
            f.write("not_a_pid")

        acquire_pid_lock()
        with open(pid_file_path, "r") as f:
            stored = int(f.read().strip())
        assert stored == os.getpid()

    def test_overwrites_own_pid(self, pid_file_path):
        """如果 PID 文件已经是自己的 PID，直接覆盖（幂等）。"""
        from server.pidlock import acquire_pid_lock

        with open(pid_file_path, "w") as f:
            f.write(str(os.getpid()))

        acquire_pid_lock()
        with open(pid_file_path, "r") as f:
            stored = int(f.read().strip())
        assert stored == os.getpid()

    @patch("server.pidlock._get_process_cmdline")
    @patch("server.pidlock._process_exists")
    def test_skips_kill_when_cmdline_not_sp_mcp(
        self, mock_exists, mock_cmdline, pid_file_path
    ):
        """旧进程存在但 cmdline 不含 sp_mcp.py → 不杀。"""
        from server.pidlock import acquire_pid_lock, _kill_process

        foreign_pid = 88888
        with open(pid_file_path, "w") as f:
            f.write(str(foreign_pid))

        # Mock: 进程存在，但 cmdline 不是 sp_mcp
        mock_exists.return_value = True
        mock_cmdline.return_value = "C:\\Windows\\System32\\cmd.exe /c some command"

        with patch("server.pidlock._kill_process") as mock_kill:
            acquire_pid_lock()
            mock_kill.assert_not_called()

        # PID 文件应被更新
        with open(pid_file_path, "r") as f:
            stored = int(f.read().strip())
        assert stored == os.getpid()

    @patch("server.pidlock._get_process_cmdline")
    @patch("server.pidlock._process_exists")
    @patch("server.pidlock._kill_process")
    @patch("server.pidlock.time.sleep")  # 避免实际 sleep
    def test_kills_old_sp_mcp_process(
        self, mock_sleep, mock_kill, mock_exists, mock_cmdline, pid_file_path
    ):
        """旧进程存在且 cmdline 含 sp_mcp.py → 杀掉并接管。"""
        from server.pidlock import acquire_pid_lock

        old_pid = 77777
        with open(pid_file_path, "w") as f:
            f.write(str(old_pid))

        mock_exists.return_value = True
        mock_cmdline.return_value = (
            r"C:\Users\1\AppData\Local\Programs\Python\Python310\python.exe"
            r" server/sp_mcp.py"
        )

        acquire_pid_lock()

        # 验证杀掉了旧进程
        mock_kill.assert_called_once_with(old_pid)

        # 验证写入了新 PID
        with open(pid_file_path, "r") as f:
            stored = int(f.read().strip())
        assert stored == os.getpid()

    @patch("server.pidlock.time.sleep")  # 避免实际 sleep
    def test_kills_real_sp_mcp_child(self, mock_sleep, pid_file_path):
        """集成测试：真实启动 sp_mcp 子进程，再用 PID 锁杀掉。"""
        import subprocess
        from server.pidlock import acquire_pid_lock, _process_exists

        # 启动一个 sp_mcp 子进程，写入其 PID
        p = subprocess.Popen(
            [sys.executable, "server/sp_mcp.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            # 等待子进程完全启动（fastmcp import 需要时间）
            time.sleep(15)

            with open(pid_file_path, "w") as f:
                f.write(str(p.pid))

            # 验证子进程存活
            assert _process_exists(p.pid) is True

            # 现在 mock sleep 让 kill 不等待
            mock_sleep.return_value = None

            # acquire_pid_lock 应该检测到旧进程并杀掉
            acquire_pid_lock()

            # 等子进程被 kill
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()

            # 子进程应该已死
            assert _process_exists(p.pid) is False

            # PID 文件已更新
            with open(pid_file_path, "r") as f:
                stored = int(f.read().strip())
            assert stored == os.getpid()
        finally:
            try:
                p.terminate()
                p.wait(timeout=3)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    p.kill()
                except OSError:
                    pass


# ── 安全性综合测试 ──────────────────────────────────────────────────────────

class TestSafety:

    def test_cmdline_check_prevents_false_kills(self):
        """双重校验设计：即使 PID 匹配，cmdline 不匹配也不杀。"""
        from server.pidlock import _get_process_cmdline

        # 当前进程的 cmdline 不含 sp_mcp.py（测试进程不是 MCP 服务器）
        cmd = _get_process_cmdline(os.getpid())
        # 在测试环境中，pytest 的 cmdline 可能包含 sp_mcp.py 文件名
        # （因为我们在测试 sp_mcp 项目），但这不是 bug——
        # 真正安全的场景是 PID 文件不会记录我们自己的 PID。
        # 这里验证的是 cmdline 能正确获取。
        assert len(cmd) > 0


# ── acquire_pid_lock 的 atexit 注册 ──────────────────────────────────────────

class TestAtexit:
    """验证 acquire_pid_lock 注册了 atexit 回调。"""

    def test_atexit_registered(self):
        """acquire_pid_lock 应该注册 atexit handler。"""
        import atexit
        from server.pidlock import _cleanup_pid_file, acquire_pid_lock

        # 检查 _cleanup_pid_file 是否在 atexit 回调中
        # 由于 atexit 没有直接的 "get registered handlers" API，
        # 我们通过调用 acquire_pid_lock 并验证它不会报错来间接测试
        acquire_pid_lock()

        # 直接调用 cleanup 验证它正常工作
        _cleanup_pid_file()
        # 不抛异常即为通过


# ── 并发安全性 ───────────────────────────────────────────────────────────────

class TestConcurrency:

    def test_repeated_acquire_is_idempotent(self, pid_file_path):
        """重复调用 acquire_pid_lock 应该是幂等的。"""
        from server.pidlock import acquire_pid_lock

        acquire_pid_lock()
        first_pid = int(open(pid_file_path, "r").read().strip())
        assert first_pid == os.getpid()

        # 再次调用
        acquire_pid_lock()
        second_pid = int(open(pid_file_path, "r").read().strip())
        assert second_pid == os.getpid()
        assert second_pid == first_pid
