import QtQuick 2.7
import Painter 1.0

PainterPlugin
{
    Component.onCompleted: {
        alg.log.info("[SP MCP] TextureSet Channels plugin loaded")

        // 添加菜单项
        var addChannelAction = alg.ui.addAction(
            alg.ui.AppMenu.Tools,
            "Add User Channel (RGB16F)",
            "Add a user channel to the active texture set"
        )
        addChannelAction.triggered.connect(function() {
            try {
                var ts = alg.texturesets.getActiveTextureSet()
                if (ts && ts.length > 0) {
                    alg.texturesets.addChannel(ts, "user0", "RGB16F", "User Channel 0")
                    alg.log.info("[SP MCP] Added user channel to: " + ts[0])
                }
            } catch (e) {
                alg.log.error("[SP MCP] Add channel error: " + e.toString())
            }
        })

        var removeChannelAction = alg.ui.addAction(
            alg.ui.AppMenu.Tools,
            "Remove User Channel",
            "Remove user0 channel from the active texture set"
        )
        removeChannelAction.triggered.connect(function() {
            try {
                var ts = alg.texturesets.getActiveTextureSet()
                if (ts && ts.length > 0) {
                    alg.texturesets.removeChannel(ts, "user0")
                    alg.log.info("[SP MCP] Removed user channel from: " + ts[0])
                }
            } catch (e) {
                alg.log.error("[SP MCP] Remove channel error: " + e.toString())
            }
        })
    }

    // 通过 Python 调用的接口函数
    function addChannel(textureSetName, channelId, channelFormat, channelLabel) {
        try {
            alg.texturesets.addChannel(
                [textureSetName],
                channelId,
                channelFormat || "RGB16F",
                channelLabel || channelId
            )
            return JSON.stringify({ ok: true, channel: channelId })
        } catch (e) {
            return JSON.stringify({ ok: false, error: e.toString() })
        }
    }

    function removeChannel(textureSetName, channelId) {
        try {
            alg.texturesets.removeChannel([textureSetName], channelId)
            return JSON.stringify({ ok: true, channel: channelId })
        } catch (e) {
            return JSON.stringify({ ok: false, error: e.toString() })
        }
    }
}
