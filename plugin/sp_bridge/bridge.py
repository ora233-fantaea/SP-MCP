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
        self._timer = QTimer()
        self._timer.timeout.connect(self._process_queue)
        self._timer.start(50)  # 每 50ms 消费一次队列

        # ThreadingHTTPServer: 每个请求独立线程，避免长操作阻塞 accept。
        # allow_reuse_address=True: 插件 reload 时避免 EADDRINUSE。
        ThreadingHTTPServer.allow_reuse_address = True
        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), _RpcHandler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="sp-bridge",
        )
        self._thread.start()

    def stop(self):
        # 先停 timer，再 drain 队列通知 in-flight 请求，最后关 server。
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

        # 通知所有还在队列里的任务：已取消，让 HTTP 端立刻收到错误。
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

    # bridge 端超时。client 端应比此值大约 5-10s，确保 bridge 先返回 504。
    TIMEOUT = 60.0

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

        _task_queue.put(_ui_task)

        timed_out = not done.wait(timeout=self.TIMEOUT)

        if timed_out:
            # 标记取消，防止任务稍后执行产生副作用。
            cancelled[0] = True
            _log("timeout waiting for ui_task\n")
            self._respond(504, {"ok": False, "error": "UI thread timeout"})
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
