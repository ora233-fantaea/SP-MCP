"""
server/client.py

对 plugin HTTP bridge 的封装。
sp_mcp.py 里的所有 tool 通过这里和 Painter 通信。

Bridge 地址默认 http://127.0.0.1:27182，可通过环境变量 SP_BRIDGE_PORT 覆盖。
"""

import os
import requests

_PORT = int(os.environ.get("SP_BRIDGE_PORT", 27182))
_HOST = os.environ.get("SP_BRIDGE_HOST", "127.0.0.1")
_BASE_URL = f"http://{_HOST}:{_PORT}"
# client timeout 必须比 bridge 的 TIMEOUT（60s）大一个余量，
# 保证 bridge 先超时返回 504，client 收到明确的 ok=false
# 而非网络层超时。否则 bridge 任务仍在队列里稍后执行，导致重复操作。
_TIMEOUT = float(os.environ.get("SP_BRIDGE_TIMEOUT", 65.0))

# 与 bridge._RpcHandler 的 TIMEOUT / MAX_TIMEOUT 保持一致。bridge 会把请求里的
# timeout 夹取到 [_BRIDGE_MIN_WAIT, _BRIDGE_MAX_WAIT]，client 必须按相同规则
# 推算 bridge 的真实等待时长，再加余量，否则当 timeout < _BRIDGE_MIN_WAIT 时
# client 会先于 bridge 网络层超时，导致「报错但任务仍在执行」的重复风险。
_BRIDGE_MIN_WAIT = 60.0
_BRIDGE_MAX_WAIT = 600.0
_TIMEOUT_MARGIN = 5.0


def call(method: str, params: dict | None = None, timeout: float | None = None) -> object:
    """
    向 SP bridge 发送一次 RPC 调用，返回 result 字段。

    成功：返回 result（可以是 dict / list / str / None）
    失败：抛出对应异常

    参数：
      method   RPC 方法名
      params   方法参数字典
      timeout  自定义超时秒数（None 用默认 _TIMEOUT）。用于 export/bake 等
               长操作：client 的 HTTP 读超时会比 bridge 端等待多留一个余量，
               并把期望的 bridge 等待时长随请求传过去，保证 bridge 先超时返回
               504，而非网络层超时（后者会让 bridge 任务仍在队列里稍后执行）。

    异常类型：
      ConnectionError  bridge 不可达（Painter 未启动或插件未加载）
      ConnectionError  请求超时
      RuntimeError     bridge 返回 ok=false（SP API 执行失败）
    """
    payload = {"method": method, "params": params or {}}
    if timeout is not None:
        # 告知 bridge 期望的等待时长，使其放宽 UI 线程等待（夹取到 bridge 上限）。
        payload["timeout"] = timeout

    # 推算 bridge 真实等待时长：未指定 timeout 时 bridge 用其默认 60s；指定时
    # bridge 会夹取到 [_BRIDGE_MIN_WAIT, _BRIDGE_MAX_WAIT]。HTTP 读超时取「bridge
    # 真实等待 + 余量」，确保 bridge 先返回 504，而非客户端网络层先超时（后者会
    # 让任务仍在 bridge 队列里稍后执行，造成重复操作）。
    if timeout is None:
        # 默认路径：bridge 用其默认 60s 等待，client 读超时用可配置的 _TIMEOUT
        # （默认 65s，可经 SP_BRIDGE_TIMEOUT 覆盖），保证 ≥ bridge 等待 + 余量。
        effective_timeout = max(_TIMEOUT, _BRIDGE_MIN_WAIT + _TIMEOUT_MARGIN)
    else:
        bridge_wait = min(max(float(timeout), _BRIDGE_MIN_WAIT), _BRIDGE_MAX_WAIT)
        effective_timeout = bridge_wait + _TIMEOUT_MARGIN

    try:
        resp = requests.post(_BASE_URL, json=payload, timeout=effective_timeout)
    except requests.exceptions.Timeout:
        raise ConnectionError(
            f"SP bridge timeout after {effective_timeout}s — "
            "is Painter running and the project open?"
        )
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            f"SP bridge not reachable at {_BASE_URL} — "
            "check that Painter is running and the plugin loaded "
            "(look for 'SP Bridge running on :27182' in the status bar)"
        )

    # bridge 可能返回非 JSON body（连接被 RST、空 body、HTML 错误页等），
    # 需要 try/except 包住 .json()，否则抛原始 JSONDecodeError 对 LLM 不可读。
    try:
        data = resp.json()
    except Exception:
        raise ConnectionError(
            f"SP bridge returned non-JSON response (status {resp.status_code}) — "
            "bridge may have crashed or port is occupied by another process"
        )

    if not data.get("ok"):
        error_msg = data.get("error", "unknown error")
        raise RuntimeError(f"SP bridge error: {error_msg}")

    return data.get("result")
