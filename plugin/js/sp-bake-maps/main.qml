import QtQuick 2.7
import Painter 1.0

PainterPlugin
{
    Component.onCompleted: {
        alg.log.info("[SP MCP] Bake Maps plugin loaded")

        // 添加菜单项到 Tools 菜单
        var bakeAction = alg.ui.addAction(
            alg.ui.AppMenu.Tools,
            "Bake Mesh Maps (Active Texture Set)",
            "Bake all mesh maps for the active texture set"
        )
        bakeAction.triggered.connect(function() {
            try {
                var ts = alg.texturesets.getActiveTextureSet()
                if (ts && ts.length > 0) {
                    alg.baking.bake(ts[0])
                    alg.log.info("[SP MCP] Baking started for: " + ts[0])
                } else {
                    alg.log.warn("[SP MCP] No active texture set found")
                }
            } catch (e) {
                alg.log.error("[SP MCP] Bake error: " + e.toString())
            }
        })
    }

    // 通过 Python 调用的接口函数
    function bakeMeshMaps(textureSetName) {
        try {
            alg.baking.bake(textureSetName)
            return JSON.stringify({ ok: true, texture_set: textureSetName })
        } catch (e) {
            return JSON.stringify({ ok: false, error: e.toString() })
        }
    }
}
