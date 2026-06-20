"""
Web 后端 - OCR 模块
包含：截图识别、固定区域识别、图像预处理、智能段落合并
"""

import time
import os
import re
import base64
from io import BytesIO
from datetime import datetime
from typing import Dict, List

from .core import (
    _last_capture_path,
    _restore_webview_window,
    _set_operation_state,
    _update_operation_state,
    _clear_operation_state,
    update_last_ocr_text,
    update_last_region,
    get_last_region,
)


def _smart_merge_paragraphs(boxes: List[dict], region_width: int) -> str:
    """
    智能合并段落算法

    核心逻辑：利用行尾留白距离 ΔX = region_width - 当前文本块右边界(x_max)
    - 如果 ΔX 小于 2.5 倍字高，说明是"被迫视觉折行"，抹去换行符
    - 如果 ΔX 很大，说明是作者主动按回车折行，保留换行符

    语种拼接：
    - 均为中文：直接无缝粘连
    - 英文/数字/中英混排：补一个空格防止粘连
    """
    if not boxes:
        return ""

    # 仅按 Y 坐标排序（行），行内排序在分组后单独处理
    sorted_boxes = sorted(boxes, key=lambda b: b.get("y", 0))

    lines = []
    current_line = []
    current_y = None
    line_height = 0

    # 先将 boxes 按行分组
    for box in sorted_boxes:
        y = box.get("y", 0)
        height = box.get("height", 20)
        text = box.get("text", "")

        if current_y is None:
            current_y = y
            line_height = height

        # 如果 Y 坐标相差超过字高的一半，认为是新行
        if abs(y - current_y) > line_height * 0.4:
            # 保存上一行（行内按 X 坐标升序排序，防止横向错乱）
            if current_line:
                current_line.sort(key=lambda b: b.get("x", 0))
                lines.append({
                    "text": "".join([b["text"] for b in current_line]),
                    "boxes": current_line,
                    "y": current_y,
                    "height": line_height
                })
            current_line = [box]
            current_y = y
            line_height = height
        else:
            current_line.append(box)
            line_height = max(line_height, height)

    # 保存最后一行（同样按 X 坐标排序）
    if current_line:
        current_line.sort(key=lambda b: b.get("x", 0))
        lines.append({
            "text": "".join([b["text"] for b in current_line]),
            "boxes": current_line,
            "y": current_y,
            "height": line_height
        })

    # 合并段落
    result_parts = []
    for i, line in enumerate(lines):
        line_text = line["text"]
        boxes_in_line = line["boxes"]
        height = line["height"]

        if not boxes_in_line:
            continue

        # 获取这一行最后一个块的信息
        last_box = boxes_in_line[-1]
        x_max = last_box.get("x", 0) + last_box.get("width", 0)

        # 计算行尾留白距离
        delta_x = region_width - x_max

        # 判断是否应该保留换行
        # 如果 ΔX < 2.5倍字高，说明是被迫折行，应该合并
        should_merge = delta_x < height * 2.5

        if i == 0:
            result_parts.append(line_text)
        else:
            prev_line = lines[i - 1]
            prev_last_box = prev_line["boxes"][-1] if prev_line["boxes"] else {}
            prev_text = prev_last_box.get("text", "")

            if should_merge:
                # 判断是否需要加空格
                # 只有当交界处出现英文/数字时才需要加空格，中文（含标点）直接粘连
                need_space = False
                if prev_text and line_text:
                    # 检查前一行末尾或当前行开头是否为英文字母或数字
                    prev_is_alnum = bool(re.match(r'[a-zA-Z0-9]$', prev_text))
                    curr_is_alnum = bool(re.match(r'^[a-zA-Z0-9]', line_text))
                    if prev_is_alnum or curr_is_alnum:
                        need_space = True

                if need_space:
                    result_parts.append(" ")
                result_parts.append(line_text)
            else:
                # 主动换行，保留 \n
                result_parts.append("\n")
                result_parts.append(line_text)

    return "".join(result_parts)


def _process_ocr_text(text: str) -> str:
    """处理 OCR 识别结果：空格被误识别成换行时替换为空格，保留正常段落换行"""
    if not text:
        return text
    # 只替换连续的小写字母/数字之间的换行（这些是空格被误识别为换行）
    # 保留有标点或中文分隔的换行
    text = re.sub(r'([a-z0-9])\n([a-z0-9])', r'\1 \2', text, flags=re.IGNORECASE)
    text = re.sub(r'([a-z0-9])\n([a-z0-9])', r'\1 \2', text, flags=re.IGNORECASE)  # 多次处理
    return text.strip()


def capture_ocr(region: Dict = None, backend_name: str = "auto") -> Dict:
    """通用 OCR 截图识别"""
    from PySide6.QtCore import QRect
    from core.screenshot import grab_region
    from core.image_utils import prepare_image_for_ocr
    from core.ocr_engine import recognize_image_with_boxes

    if region is None:
        from .region import select_region
        select_result = select_region("single_ocr")
        if not select_result.get("success"):
            return select_result
        region = select_result.get("region")

    rect = QRect(
        region.get("left", region.get("x", 0)),
        region.get("top", region.get("y", 0)),
        region.get("width", 0),
        region.get("height", 0)
    )

    if rect.width() <= 0 or rect.height() <= 0:
        _restore_webview_window()
        return {
            "success": False,
            "error": "无效的截图区域"
        }

    update_last_region({
        "left": rect.x(),
        "top": rect.y(),
        "width": rect.width(),
        "height": rect.height()
    })

    # 设置初始状态通知前端
    _set_operation_state("single_ocr", True, 0, 1, "屏幕截图已捕获，正在进行图像预处理...", "preprocess")

    start_time = time.time()

    # 确保窗口已隐藏再截图
    _hide_webview_window()
    time.sleep(0.15)

    try:
        image = grab_region(rect)
        ocr_image = prepare_image_for_ocr(image)
    except Exception as e:
        import traceback
        _restore_webview_window()
        _clear_operation_state("single_ocr")
        return {
            "success": False,
            "error": f"截图失败: {e}\n{traceback.format_exc()}"
        }

    # 截图完成后再恢复窗口，然后执行 OCR
    _restore_webview_window()

    try:
        # 使用带坐标的 OCR 识别
        raw_text, actual_backend, boxes = recognize_image_with_boxes(ocr_image, backend_name)

        _update_operation_state(message="OCR 识别完成，正在进行文本智能合并与重组...", phase="paragraph_merge")

        # 使用智能合并算法处理文本（使用 ocr_image 的宽度，与 boxes 坐标一致）
        if boxes:
            text = _smart_merge_paragraphs(boxes, ocr_image.width)
        else:
            # 如果没有 boxes，回退到旧的处理方式
            text = _process_ocr_text(raw_text)

        # 同步到全局状态
        update_last_ocr_text(text)

        try:
            ocr_image.save(_last_capture_path)
        except Exception as e:
            print(f"Failed to save debug image: {e}")

        elapsed = time.time() - start_time

        # 清理状态
        _clear_operation_state("single_ocr")

        return {
            "success": True,
            "text": text,
            "image_path": _last_capture_path,
            "backend": actual_backend,
            "elapsed": round(elapsed, 2),
            "region": {
                "left": rect.x(),
                "top": rect.y(),
                "width": rect.width(),
                "height": rect.height()
            }
        }
    except Exception as e:
        _clear_operation_state("single_ocr")
        return {
            "success": False,
            "error": str(e)
        }


def capture_ocr_from_selected_region(region: Dict, backend_name: str = "auto") -> Dict:
    """从指定区域执行 OCR"""

    # 设置初始状态
    _set_operation_state("single_ocr", True, 0, 1, "屏幕截图已捕获，正在进行图像预处理...", "preprocess")

    try:
        from PySide6.QtCore import QRect
    except Exception as e:
        import traceback
        _restore_webview_window()
        _clear_operation_state("single_ocr")
        return {
            "success": False,
            "error": f"导入 QRect 失败: {e}\n{traceback.format_exc()}"
        }

    try:
        from core.screenshot import grab_region
        from core.image_utils import prepare_image_for_ocr
        from core.ocr_engine import recognize_image_with_boxes
    except Exception as e:
        import traceback
        _restore_webview_window()
        _clear_operation_state("single_ocr")
        return {
            "success": False,
            "error": f"导入 core 模块失败: {e}\n{traceback.format_exc()}"
        }

    rect = QRect(
        region.get("left", 0),
        region.get("top", 0),
        region.get("width", 0),
        region.get("height", 0)
    )

    if rect.width() <= 0 or rect.height() <= 0:
        _restore_webview_window()
        _clear_operation_state("single_ocr")
        return {
            "success": False,
            "error": "无效的截图区域"
        }

    update_last_region(region)

    start_time = time.time()

    # 先隐藏窗口，再截图
    _hide_webview_window()
    time.sleep(0.2)

    try:
        image = grab_region(rect)
    except Exception as e:
        import traceback
        _restore_webview_window()
        _clear_operation_state("single_ocr")
        return {
            "success": False,
            "error": f"grab_region 失败: {e}\n{traceback.format_exc()}"
        }

    # 截图完成后再恢复窗口
    _restore_webview_window()
    _update_operation_state(message="图像预处理完成，正在调用 OCR 引擎解析文本与坐标...", phase="ocr_processing")

    try:
        # 然后执行 OCR（耗时操作，窗口已恢复）
        ocr_image = prepare_image_for_ocr(image)
    except Exception as e:
        import traceback
        _clear_operation_state("single_ocr")
        return {
            "success": False,
            "error": f"prepare_image_for_ocr 失败: {e}\n{traceback.format_exc()}"
        }

    try:
        # 使用带坐标的 OCR 识别
        raw_text, actual_backend, boxes = recognize_image_with_boxes(ocr_image, backend_name)

        _update_operation_state(message="OCR 识别完成，正在进行文本智能合并与重组...", phase="paragraph_merge")

        # 使用智能合并算法处理文本（使用 ocr_image 的宽度，与 boxes 坐标一致）
        if boxes:
            text = _smart_merge_paragraphs(boxes, ocr_image.width)
        else:
            # 如果没有 boxes，回退到旧的处理方式
            text = _process_ocr_text(raw_text)

        # 同步到全局状态
        update_last_ocr_text(text)

    except Exception as e:
        import traceback
        _clear_operation_state("single_ocr")
        return {
            "success": False,
            "error": f"recognize_image 失败: {e}\n{traceback.format_exc()}"
        }

    # 保存截图
    try:
        captures_dir = "captures"
        if not os.path.exists(captures_dir):
            os.makedirs(captures_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_path = os.path.join(captures_dir, f"selected_ocr_{timestamp}.png")
        ocr_image.save(image_path)
    except Exception as e:
        image_path = ""
        print(f"Failed to save debug image: {e}")

    # 生成 base64
    try:
        buffer = BytesIO()
        ocr_image.save(buffer, format="PNG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        image_data_url = f"data:image/png;base64,{image_base64}"
    except Exception as e:
        image_data_url = ""
        print(f"Failed to encode image to base64: {e}")

    elapsed = time.time() - start_time

    # 清理状态
    _clear_operation_state("single_ocr")

    return {
        "success": True,
        "text": text,
        "image_path": image_path,
        "image_data_url": image_data_url,
        "backend": actual_backend,
        "elapsed": round(elapsed, 2),
        "region": region
    }


def recognize_fixed_region(backend_name: str = "auto") -> Dict:
    """使用固定区域识别"""
    last_region = get_last_region()

    if last_region is None:
        return {
            "success": False,
            "error": "没有固定区域，请先执行一次截图识别"
        }

    return capture_ocr_from_selected_region(region=last_region, backend_name=backend_name)


def capture_ocr_with_tkinter(backend_name: str = "auto") -> Dict:
    """使用 tkinter 交互式截图后识别"""
    global _last_ocr_text

    from .region import select_region_tkinter

    select_result = select_region_tkinter("single_ocr")

    if not select_result.get("success"):
        return select_result

    region = select_result.get("region")

    return capture_ocr_from_selected_region(region, backend_name)
