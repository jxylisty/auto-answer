"""
Web 后端 - 区域模块
包含：区域选择、截图、tkinter选择器
"""

import time
import os
import threading
import queue
from datetime import datetime
from typing import Dict

from .core import (
    _hide_webview_window,
    _restore_webview_window,
    _clear_operation_state,
    _selection_controller,
    _webview_window,
    update_question_region,
    update_number_region,
    update_last_region,
    update_number_region_image,
    update_full_screen_image,
    get_full_screen_image,
    get_number_region,
)


def _run_tkinter_selector(image, screen_geo, result_queue):
    """运行 tkinter 截图选择器"""
    import tkinter as tk
    from PIL import ImageTk

    screen_left, screen_top, screen_width, screen_height = screen_geo

    root = tk.Tk()
    root.title("截图选择")
    root.attributes('-fullscreen', True)
    root.attributes('-topmost', True)
    root.attributes('-alpha', 1.0)
    root.configure(bg='black', cursor='cross')
    root.bind('<Escape>', lambda e: (result_queue.put(None), root.destroy()))

    tk_image = ImageTk.PhotoImage(image)

    canvas = tk.Canvas(root, width=screen_width, height=screen_height, bg='black', highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)

    canvas.create_image(0, 0, anchor=tk.NW, image=tk_image)

    start_x = [0]
    start_y = [0]
    current_rect = [None]

    def on_mouse_down(event):
        start_x[0] = event.x
        start_y[0] = event.y

    def on_mouse_move(event):
        if current_rect[0]:
            canvas.delete(current_rect[0])

        x1, y1 = start_x[0], start_y[0]
        x2, y2 = event.x, event.y

        current_rect[0] = canvas.create_rectangle(
            x1, y1, x2, y2,
            outline='#00ff00', width=2, fill=''
        )

    def on_mouse_up(event):
        x1, y1 = start_x[0], start_y[0]
        x2, y2 = event.x, event.y

        left = min(x1, x2)
        top = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)

        if width > 5 and height > 5:
            real_left = screen_left + left
            real_top = screen_top + top

            result = {
                "left": real_left,
                "top": real_top,
                "width": width,
                "height": height
            }
            result_queue.put(result)
            root.destroy()

    canvas.bind('<Button-1>', on_mouse_down)
    canvas.bind('<B1-Motion>', on_mouse_move)
    canvas.bind('<ButtonRelease-1>', on_mouse_up)

    root.mainloop()


def select_region_tkinter(mode: str = "single_ocr") -> Dict:
    """使用 tkinter 交互式选择区域"""
    from PySide6.QtCore import QRect
    from core.screenshot import get_virtual_geometry, grab_region

    try:
        # 隐藏窗口并截取全屏作为选择器背景
        _hide_webview_window()
        time.sleep(0.3)

        screen_geo = get_virtual_geometry()
        screen_left, screen_top, screen_width, screen_height = screen_geo

        rect = QRect(screen_left, screen_top, screen_width, screen_height)
        image = grab_region(rect)

        result_queue = queue.Queue()

        selector_thread = threading.Thread(
            target=_run_tkinter_selector,
            args=(image, screen_geo, result_queue),
            daemon=True
        )
        selector_thread.start()
        selector_thread.join()

        try:
            result = result_queue.get_nowait()
        except queue.Empty:
            result = None

        if result is None:
            _restore_webview_window()
            return {
                "success": False,
                "error": "已取消截图"
            }

        if mode == "single_ocr":
            update_last_region(result)
            # 不在这里恢复窗口，capture_ocr_from_selected_region 会处理
        elif mode == "question_region":
            update_question_region(result)
            _restore_webview_window()
        elif mode == "number_region":
            update_number_region(result)
            # 选完区域后立即截图保存（隐藏窗口避免截到自己）
            from core.screenshot import grab_region
            left = int(result.get("left", 0))
            top = int(result.get("top", 0))
            w = int(result.get("width", 0))
            h = int(result.get("height", 0))
            if w > 0 and h > 0:
                _hide_webview_window()
                time.sleep(0.15)
                rect = QRect(left, top, w, h)
                region_image = grab_region(rect)
                update_number_region_image(region_image)
                # 保存到文件
                base_dir = os.path.dirname(os.path.abspath(__file__))
                captures_dir = os.path.join(base_dir, "..", "captures")
                if not os.path.exists(captures_dir):
                    os.makedirs(captures_dir)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                region_image.save(os.path.join(captures_dir, f"number_region_{timestamp}.png"))
                _restore_webview_window()
            else:
                _restore_webview_window()
        else:
            _restore_webview_window()

        _clear_operation_state("parse_collected_options")
        return {
            "success": True,
            "mode": mode,
            "region": result
        }

    except Exception as e:
        import traceback
        _restore_webview_window()
        return {
            "success": False,
            "error": f"截图失败: {str(e)}\n{traceback.format_exc()}"
        }


def select_region(mode: str) -> Dict:
    """原生 PySide6 区域选择"""
    if _selection_controller is None:
        return {
            "success": False,
            "error": "原生截图控制器未初始化"
        }

    result = _selection_controller.select_region(mode)

    # 保存选区到全局状态
    if result.get("success") and result.get("region"):
        region_data = result["region"]
        if mode == "single_ocr":
            update_last_region(region_data)
        elif mode == "question_region":
            update_question_region(region_data)
        elif mode == "number_region":
            update_number_region(region_data)

    return result


def begin_screen_capture(mode: str = "single_ocr") -> Dict:
    """开始屏幕截图（用于前端网页选区）"""
    if _webview_window is None:
        return {
            "success": False,
            "error": "窗口未初始化"
        }

    try:
        import base64
        from io import BytesIO
        from datetime import datetime
        from PySide6.QtCore import QRect
        from core.screenshot import get_virtual_geometry, grab_region

        _hide_webview_window()
        time.sleep(0.15)

        screen_geo = get_virtual_geometry()
        screen_left, screen_top, screen_width, screen_height = screen_geo

        rect = QRect(screen_left, screen_top, screen_width, screen_height)
        image = grab_region(rect)

        # 保存截图
        base_dir = os.path.dirname(os.path.abspath(__file__))
        captures_dir = os.path.join(base_dir, "..", "captures")
        if not os.path.exists(captures_dir):
            os.makedirs(captures_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"full_screen_capture_{timestamp}.png"
        full_path = os.path.join(captures_dir, filename)
        image.save(full_path)
        update_full_screen_image(image)

        # 生成 base64
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        img_data_url = f"data:image/png;base64,{img_base64}"

        # 先恢复窗口，再返回
        _restore_webview_window()

        return {
            "success": True,
            "mode": mode,
            "image_path": img_data_url,
            "screen": {
                "left": screen_left,
                "top": screen_top,
                "width": screen_width,
                "height": screen_height
            },
            "natural_width": image.width,
            "natural_height": image.height
        }
    except Exception as e:
        import traceback
        if _webview_window:
            try:
                _restore_webview_window()
            except:
                pass
        return {
            "success": False,
            "error": f"截图失败: {str(e)}\n{traceback.format_exc()}"
        }


def finish_region_select(mode: str, rect: Dict) -> Dict:
    """完成区域选择（前端选区后调用）"""

    screen_left = rect.get("screen_left", 0)
    screen_top = rect.get("screen_top", 0)
    display_width = rect.get("display_width", 1)
    display_height = rect.get("display_height", 1)
    natural_width = rect.get("natural_width", 1)
    natural_height = rect.get("natural_height", 1)

    x = int(rect.get("x", 0))
    y = int(rect.get("y", 0))
    width = int(rect.get("width", 0))
    height = int(rect.get("height", 0))

    if display_width > 0 and display_height > 0:
        scale_x = natural_width / display_width
        scale_y = natural_height / display_height
    else:
        scale_x = 1.0
        scale_y = 1.0

    real_left = int(screen_left + x * scale_x)
    real_top = int(screen_top + y * scale_y)
    real_width = int(width * scale_x)
    real_height = int(height * scale_y)

    region_data = {
        "left": real_left,
        "top": real_top,
        "width": real_width,
        "height": real_height
    }

    if mode == "single_ocr":
        update_last_region(region_data)
    elif mode == "question_region":
        update_question_region(region_data)
    elif mode == "number_region":
        update_number_region(region_data)

    return {
        "success": True,
        "mode": mode,
        "region": region_data
    }


def select_question_region() -> Dict:
    """选择题目的区域"""
    result = select_region_tkinter("question_region")
    return result


def select_number_region() -> Dict:
    """选择题号区域"""
    result = select_region_tkinter("number_region")
    return result


def save_number_region_capture() -> Dict:
    """保存题号区域截图"""
    number_region = get_number_region()

    if number_region is None:
        return {
            "success": False,
            "error": "未选择题号区域"
        }

    from PySide6.QtCore import QRect
    from core.screenshot import grab_region

    try:
        rect = QRect(
            number_region.get("left", 0),
            number_region.get("top", 0),
            number_region.get("width", 0),
            number_region.get("height", 0)
        )

        _hide_webview_window()
        time.sleep(0.15)
        image = grab_region(rect)
        _restore_webview_window()

        base_dir = os.path.dirname(os.path.abspath(__file__))
        captures_dir = os.path.join(base_dir, "..", "captures")
        if not os.path.exists(captures_dir):
            os.makedirs(captures_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"number_region_{timestamp}.png"
        full_path = os.path.join(captures_dir, filename)
        image.save(full_path)
        update_number_region_image(image)

        return {
            "success": True,
            "message": f"题号区域截图已保存: {filename}",
            "image_path": full_path
        }
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": f"截图失败: {str(e)}\n{traceback.format_exc()}"
        }
