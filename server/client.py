"""
server/client.py

对 plugin HTTP bridge 的封装。
sp_mcp.py 里的所有 tool 通过这里和 Painter 通信。

Bridge 地址默认 http://127.0.0.1:27182，可通过环境变量 SP_BRIDGE_PORT 覆盖。
"""

import os
import requests

_PORT = int(os.environ.get("SP_BRIDGE_PORT", 27182))
_BASE_URL = f"http://127.0.0.1:{_PORT}"
_TIMEOUT = 12.0  # 略大于 bridge 侧的 10s 超时


def call(method: str, params: dict | None = None, timeout: float | None = None) -> object:
    """
    向 SP bridge 发送一次 RPC 调用，返回 result 字段。

    成功：返回 result（可以是 dict / list / str / None）
    失败：抛出对应异常

    参数：
      method   RPC 方法名
      params   方法参数字典
      timeout  自定义超时秒数（None 用默认 _TIMEOUT）

    异常类型：
      ConnectionError  bridge 不可达（Painter 未启动或插件未加载）
      ConnectionError  请求超时
      RuntimeError     bridge 返回 ok=false（SP API 执行失败）
    """
    payload = {"method": method, "params": params or {}}
    effective_timeout = timeout if timeout is not None else _TIMEOUT

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

    data = resp.json()

    if not data.get("ok"):
        error_msg = data.get("error", "unknown error")
        raise RuntimeError(f"SP bridge error: {error_msg}")

    return data.get("result")
