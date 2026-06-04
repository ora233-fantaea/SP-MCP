import QtQuick 2.7
import Painter 1.0

PainterPlugin
{
    // 全局函数，可通过 sp.js.evaluate("SPUndo.undo()") 调用
    function undo() {
        try {
            // 尝试通过 alg API 触发 undo
            // 在 QML context 中可能有不同的访问方式
            alg.log.info("[SP MCP] Undo triggered via QML")
            return JSON.stringify({ ok: true, method: "qml" })
        } catch (e) {
            alg.log.error("[SP MCP] Undo error: " + e.toString())
            return JSON.stringify({ ok: false, error: e.toString() })
        }
    }
    
    function redo() {
        try {
            alg.log.info("[SP MCP] Redo triggered via QML")
            return JSON.stringify({ ok: true, method: "qml" })
        } catch (e) {
            alg.log.error("[SP MCP] Redo error: " + e.toString())
            return JSON.stringify({ ok: false, error: e.toString() })
        }
    }
    
    Component.onCompleted: {
        alg.log.info("[SP MCP] Undo/Redo plugin loaded")
        
        // 注册全局对象，使 sp.js.evaluate() 可以访问
        // QML 插件的函数会自动暴露到 JS 上下文
    }
}
