# AGENTS.md

本项目是 Windows 截图 OCR 工具，技术栈为 PySide6 + mss + OCR。

## 工作规则
- 默认直接修改文件，不要粘贴完整代码。
- 每次只解决一个问题。
- 修 bug 前必须根据控制台日志判断原因。
- 修改必须是最小 diff。
- 不要无意义重构。

## 禁止改动
- 不允许修改 SelectionOverlay 坐标逻辑，除非用户明确要求。
- 不允许修改 QThread 结构，除非用户明确要求。
- 不允许整屏截图后裁剪，必须使用 mss.grab(region)。

## Windows OCR 规则
- 不要猜 winsdk API。
- 遇到 Windows OCR 失败，必须打印 repr(exc) 和 traceback。
- 只允许修改 core/ocr_engine.py。
- RapidOCR 必须保留 fallback。
- 日志必须打印实际 OCR backend。
## 修改规则
- 保证前端和后端一起更新
- 保证后端实现的功能需要在前端体现
- 不允许只测试后端不测试前端
- 一定要做 前端适配后端