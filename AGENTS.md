# AGENTS.md

本项目是 Windows 截图 OCR 工具，技术栈为 webview + mss + OCR，前端 webui/，后端 web_backend/。

## 工作规则
- 默认直接修改文件，不要粘贴完整代码。
- 每次只解决一个问题。
- 修 bug 前必须根据控制台日志判断原因。
- 修改必须是最小 diff。
- 不要无意义重构。
- 环境用虚拟环境.venv1
## 禁止改动
- 不允许整屏截图后裁剪，必须使用 mss.grab(region)。
- 不允许硬编码题目数量（如 45 题），必须根据实际采集结果动态生成。

## Windows OCR 规则
- 不要猜 winsdk API。
- 遇到 Windows OCR 失败，必须打印 repr(exc) 和 traceback。
- 只允许修改 core/ocr_engine.py。
- RapidOCR 必须保留 fallback。
- 日志必须打印实际 OCR backend。
- OCR 后端返回的坐标字段不统一：RapidOCR 有 center_x/center_y，Windows OCR 只有 x/y/width/height，代码必须兼容两种格式。

## 修改规则
- 保证前端和后端一起更新
- 保证后端实现的功能需要在前端体现
- 不允许只测试后端不测试前端
- 一定要做 前端适配后端
- 截图后必须先恢复窗口，再执行 OCR 识别（窗口显示后再做耗时的 OCR）

## 采集与执行规则
- 判断题选项键名可能是 正确/错误、T/F、TRUE/FALSE、A/B，代码必须按优先级依次查找，不能只查 A/B。
- _collected_records 在采集线程中写入，主线程中读取，必须使用 _collection_lock 保护。
- prepare_image_for_ocr 可能缩小图片，传给 _smart_merge_paragraphs 的 region_width 必须用 ocr_image.width 而非原始截图宽度。
- PaddleOcrBackend 必须实现 recognize_with_boxes 方法，否则 fallback 时 boxes 为空导致合并算法失效。
