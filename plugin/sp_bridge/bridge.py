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
import traceback
import pathlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

from PySide2.QtCore import QTimer

from . import handlers

_LOG = pathlib.Path.home() / "sp_bridge.log"
_task_queue = queue.Queue()   # type: queue.Queue


class BridgeServer(object):
    def __init__(self, port=27182):
        self.port = port
        self._server = None    # type: Optional[HTTPServer]
        self._thread = None    # type: Optional[threading.Thread]
        self._timer = None     # type: Optional[QTimer]

    def start(self):
        # QTimer 必须在主线程创建，start() 由 __init__.py 在主线程调用
        self._timer = QTimer()
        self._timer.timeout.connect(self._process_queue)
        self._timer.start(50)  # 每 50ms 消费一次队列

        self._server = HTTPServer(("127.0.0.1", self.port), _RpcHandler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="sp-bridge",
        )
        self._thread.start()

    def stop(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if self._server is not None:
            self._server.shutdown()
            self._server = None

    def _process_queue(self):
        """在 Qt 主线程里执行队列中的所有待处理任务。"""
        while True:
            try:
                task = _task_queue.get_nowait()
                try:
                    task()
                except Exception:
                    _LOG.write_text("task error:\n" + traceback.format_exc())
            except queue.Empty:
                break


class _RpcHandler(BaseHTTPRequestHandler):

    TIMEOUT = 60.0

    def do_POST(self):
        try:
            self._handle()
        except Exception:
            err = traceback.format_exc()
            _LOG.write_text("do_POST crash:\n" + err)
            try:
                self._respond(500, {"ok": False, "error": err})
            except Exception:
                pass

    def _handle(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)

        try:
            body = json.loads(raw)
        except Exception as exc:
            self._respond(400, {"ok": False, "error": "JSON parse error: {}".format(exc)})
            return

        holder = {"result": None, "error": None}
        done = threading.Event()

        def _ui_task():
            try:
                holder["result"] = handlers.dispatch(body)
            except Exception as exc:
                holder["error"] = str(exc)
                _LOG.write_text("ui_task error:\n" + traceback.format_exc())
            finally:
                done.set()

        _task_queue.put(_ui_task)

        timed_out = not done.wait(timeout=self.TIMEOUT)

        if timed_out:
            _LOG.write_text("timeout waiting for ui_task\n")
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
