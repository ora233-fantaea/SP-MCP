"""
plugin/sp_bridge/bridge.py

跨线程调度方案：轮询队列
  - BridgeServer.start() 在主线程创建一个 50ms QTimer，持续消费 _task_queue
  - HTTP server 线程把任务放进 _task_queue，然后阻塞等待 threading.Event
  - QTimer 在主线程执行任务，设置 Event，HTTP 线程收到结果后返回响应
"""

import json
import queue
import threading
import time
import traceback
import pathlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from PySide2.QtCore import QTimer

from . import handlers

_LOG = pathlib.Path.home() / "sp_bridge.log"
_task_queue = queue.Queue()   # type: queue.Queue

# 关闭协调：_enqueue_lock 串行化「入队」与「stop() drain」两段临界区，
# _shutting_down 一旦置位，新请求不再入队（改为立即拒绝），从根本上杜绝
# 「drain 之后才 put 的孤儿任务永远无人消费、HTTP 线程死等到超时」竞态。
_enqueue_lock = threading.Lock()
_shutting_down = False

# 单次 QTimer tick 内最多执行的任务数，防止积压时阻塞 SP UI 过久。
_MAX_TASKS_PER_TICK = 8
# 请求 body 最大长度（字节），防止恶意大 body。
_MAX_BODY_BYTES = 16 * 1024 * 1024  # 16 MB


def _log(msg: str) -> None:
    """追加式日志，不覆盖历史记录。"""
    try:
        with open(str(_LOG), "a", encoding="utf-8") as f:
            f.write(msg if msg.endswith("\n") else msg + "\n")
    except Exception:
        pass


class BridgeServer(object):
    def __init__(self, port=27182):
        self.port = port
        self._server = None    # type: Optional[ThreadingHTTPServer]
        self._thread = None    # type: Optional[threading.Thread]
        self._timer = None     # type: Optional[QTimer]

    def start(self):
        # QTimer 必须在主线程创建，start() 由 __init__.py 在主线程调用
        global _shutting_down
        with _enqueue_lock:
            _shutting_down = False   # 支持 stop() 后再次 start()（reload 场景）
        self._timer = QTimer()
        self._timer.timeout.connect(self._process_queue)
        self._timer.start(50)  # 每 50ms 消费一次队列

        # ThreadingHTTPServer: 每个请求独立线程，避免长操作阻塞 accept。
        # allow_reuse_address 必须在 bind 之前设置，且只作用于本实例（不污染
        # ThreadingHTTPServer 类的全局状态，以免影响 SP 进程内其它 HTTP server）。
        # 因此用 bind_and_activate=False 构造，设好实例属性后再手动 bind/activate。
        self._server = ThreadingHTTPServer(
            ("127.0.0.1", self.port), _RpcHandler, bind_and_activate=False
        )
        self._server.allow_reuse_address = True  # reload 时避免 EADDRINUSE
        try:
            self._server.server_bind()
            self._server.server_activate()
        except Exception:
            self._server.server_close()
            self._server = None
            raise
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="sp-bridge",
        )
        self._thread.start()

    def stop(self):
        # 先停 timer，再 drain 队列通知 in-flight 请求，最后关 server。
        global _shutting_down
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

        # 置关闭标志（持锁），使「检查标志后入队」的请求线程要么在置标志前已
        # 入队（会被下面 drain 到并取消），要么在置标志后被拒绝（不再入队）。
        # 二者都不会留下无人消费的孤儿任务。
        with _enqueue_lock:
            _shutting_down = True
            cancelled = []
            while True:
                try:
                    pending = _task_queue.get_nowait()
                    cancelled.append(pending)
                except queue.Empty:
                    break
        for task in cancelled:
            # 标记取消，避免任务稍后执行；同时 set done 让阻塞的 HTTP 线程立即返回。
            cancel_fn = getattr(task, "_cancel", None)
            if cancel_fn:
                cancel_fn()
            # 在 holder 写入错误，避免 HTTP 端把「未执行的已取消任务」当成
            # ok=true / result=null 的成功响应回给 client。
            holder = getattr(task, "_holder", None)
            if holder is not None and holder.get("error") is None:
                holder["error"] = "bridge shutting down — operation cancelled, not executed"
            done = getattr(task, "_done", None)
            if done is not None and not done.is_set():
                done.set()

        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None

    def _process_queue(self):
        """在 Qt 主线程里执行队列中的待处理任务（单次最多 _MAX_TASKS_PER_TICK 个）。"""
        for _ in range(_MAX_TASKS_PER_TICK):
            try:
                task = _task_queue.get_nowait()
            except queue.Empty:
                break
            try:
                task()
            except Exception:
                _log("task error:\n" + traceback.format_exc())
                # 兜底：确保 task 的 done event 被设置，避免 HTTP 端无限等待。
                done = getattr(task, "_done", None)
                if done is not None and not done.is_set():
                    err = getattr(task, "_holder", None)
                    if err is not None:
                        err["error"] = "internal task error"
                    done.set()


class _RpcHandler(BaseHTTPRequestHandler):

    # bridge 端默认超时。client 端应比此值大约 5-10s，确保 bridge 先返回 504。
    TIMEOUT = 60.0
    # 单个请求可放宽到的硬上限（秒）。export/bake 等长操作通过请求里的
    # "timeout" 字段申请更长等待，但不得超过此上限，防止 UI 线程被无限占用。
    MAX_TIMEOUT = 600.0

    @classmethod
    def _resolve_wait_timeout(cls, req_timeout) -> float:
        """把请求里的 timeout 字段解析/夹取为合法的 UI 等待时长（秒）。

        - None → 默认 TIMEOUT
        - 非数值 / NaN / Infinity → 回退默认 TIMEOUT
        - 其余 → 夹取到 [TIMEOUT, MAX_TIMEOUT]
        """
        import math as _math
        if req_timeout is None:
            return cls.TIMEOUT
        try:
            rt = float(req_timeout)
        except (TypeError, ValueError):
            return cls.TIMEOUT
        if not _math.isfinite(rt):
            return cls.TIMEOUT
        return min(max(rt, cls.TIMEOUT), cls.MAX_TIMEOUT)

    def do_POST(self):
        try:
            self._handle()
        except Exception:
            err = traceback.format_exc()
            _log("do_POST crash:\n" + err)
            try:
                self._respond(500, {"ok": False, "error": err})
            except Exception:
                pass

    def _handle(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > _MAX_BODY_BYTES:
            self._respond(413, {"ok": False, "error": "Request body too large"})
            return
        raw = self.rfile.read(length)

        try:
            body = json.loads(raw)
        except Exception as exc:
            self._respond(400, {"ok": False, "error": "JSON parse error: {}".format(exc)})
            return

        # body 必须是 JSON object（dict）。裸标量/数组无法 dispatch，直接 400，
        # 避免后续 body.get(...) 抛 AttributeError 变成 500+traceback。
        if not isinstance(body, dict):
            self._respond(400, {"ok": False,
                                "error": "Request body must be a JSON object"})
            return

        # 按请求覆盖等待超时：长操作（export/bake）可申请更长等待，
        # 夹取到 [TIMEOUT, MAX_TIMEOUT]，避免提前 504 误报失败导致重复执行。
        wait_timeout = self._resolve_wait_timeout(body.get("timeout"))

        holder = {"result": None, "error": None}
        done = threading.Event()

        def _ui_task():
            # 超时取消检查：若已取消则不执行 dispatch，避免副作用泄漏。
            if cancelled[0]:
                return
            try:
                holder["result"] = handlers.dispatch(body)
            except Exception as exc:
                holder["error"] = str(exc)
                _log("ui_task error:\n" + traceback.format_exc())
            finally:
                done.set()

        cancelled = [False]
        _ui_task._done = done
        _ui_task._holder = holder
        _ui_task._cancel = lambda: cancelled.__setitem__(0, True)

        # 持锁检查关闭标志后入队，与 stop() 的 drain 互斥：若 bridge 正在/已经
        # 关闭，直接拒绝而非留下无人消费的任务（否则会死等到超时）。
        with _enqueue_lock:
            if _shutting_down:
                self._respond(503, {"ok": False,
                                    "error": "bridge is shutting down"})
                return
            _task_queue.put(_ui_task)

        timed_out = not done.wait(timeout=wait_timeout)

        if timed_out:
            # 标记取消，防止任务稍后执行产生副作用。
            # 注意：已在 UI 线程开始执行的同步 SP 调用无法真正中断，
            # 此标记只能阻止「尚未开始」的任务。client 端据 504 不应自动重试
            # 长操作（可能已在执行中），应改用查询类工具确认实际状态。
            cancelled[0] = True
            _log("timeout waiting for ui_task (waited %.0fs)\n" % wait_timeout)
            self._respond(504, {"ok": False, "error":
                                "UI thread timeout after %.0fs — operation may "
                                "still be running; do NOT blindly retry, verify "
                                "state first" % wait_timeout})
        elif holder["error"] is not None:
            self._respond(500, {"ok": False, "error": holder["error"]})
        else:
            self._respond(200, {"ok": True, "result": holder["result"]})

    def _respond(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
