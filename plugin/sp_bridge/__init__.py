"""
plugin/sp_bridge/__init__.py
"""

import traceback
import pathlib
from typing import Optional

import substance_painter.logging

from . import bridge as _bridge

_LOG = pathlib.Path.home() / "sp_bridge.log"
_BRIDGE = None  # type: Optional[_bridge.BridgeServer]
BRIDGE_PORT = 27182


def start_plugin():
    global _BRIDGE
    try:
        _BRIDGE = _bridge.BridgeServer(port=BRIDGE_PORT)
        _BRIDGE.start()
        msg = "SP Bridge started on port {}".format(BRIDGE_PORT)
        _LOG.write_text(msg + "\n")
        substance_painter.logging.log(
            substance_painter.logging.INFO,
            "sp_bridge",
            msg,
        )
    except Exception:
        err = traceback.format_exc()
        _LOG.write_text(err)
        substance_painter.logging.log(
            substance_painter.logging.ERROR,
            "sp_bridge",
            err,
        )
        raise


def close_plugin():
    global _BRIDGE
    try:
        if _BRIDGE is not None:
            _BRIDGE.stop()
            _BRIDGE = None
        substance_painter.logging.log(
            substance_painter.logging.INFO,
            "sp_bridge",
            "SP Bridge stopped",
        )
    except Exception:
        _LOG.write_text(traceback.format_exc())
