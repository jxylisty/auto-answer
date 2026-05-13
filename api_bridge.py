from typing import Dict, List
import time
import os
import threading

_last_ocr_text = ""
_fixed_region = None
_last_capture_path = "last_capture_debug.png"
_question_region = None
_number_region = None
_last_region = None
_detected_question_points = []
_collected_records = []
_collection_running = False
_collection_stop_flag = False
_webview_window = None
_selection_controller = None
_execution_running = False
_answer_click_cursor = 0
_operation_state = {
    "name": "",
    "running": False,
    "current": 0,
    "total": 0,
    "message": "",
    "phase": "",
    "updated_at": 0.0,
}
_execution_running = False
_execution_stop_flag = False
_answer_click_tasks = []


def _set_operation_state(
    name: str,
    running: bool,
    current: int = 0,
    total: int = 0,
    message: str = "",
    phase: str = "",
):
    _operation_state.update(
        {
            "name": name,
            "running": running,
            "current": int(current),
            "total": int(total),
            "message": message,
            "phase": phase,
            "updated_at": time.time(),
        }
    )


def _update_operation_state(**kwargs):
    _operation_state.update(kwargs)
    _operation_state["updated_at"] = time.time()


def _clear_operation_state(name: str = ""):
    _operation_state.update(
        {
            "name": name or _operation_state.get("name", ""),
            "running": False,
            "current": 0,
            "total": 0,
            "message": "",
            "phase": "",
            "updated_at": time.time(),
        }
    )


def _serialize_collected_record(record: dict) -> dict:
    if not isinstance(record, dict):
        return {}
    data = dict(record)
    data.pop("capture_image", None)
    return data


def set_window(window):
    global _webview_window
    _webview_window = window


def set_selection_controller(controller):
    global _selection_controller
    _selection_controller = controller


def _run_tkinter_selector(image, screen_geo, result_queue):
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
    selection = [None]
    
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
            
            selection[0] = {
                "left": real_left,
                "top": real_top,
                "width": width,
                "height": height
            }
            result_queue.put(selection[0])
            root.destroy()
    
    canvas.bind('<Button-1>', on_mouse_down)
    canvas.bind('<B1-Motion>', on_mouse_move)
    canvas.bind('<ButtonRelease-1>', on_mouse_up)
    
    root.mainloop()


def _hide_webview_window():
    """Hide webview before real screen capture.

    Do not call minimize() here: minimize + hide + restore easily causes visible flicker.
    """
    global _webview_window
    if _webview_window:
        try:
            _webview_window.hide()
        except Exception:
            pass


def _restore_webview_window():
    """Restore webview after screen capture.

    Do not call restore() by default: show() is enough after hide() and avoids animation flicker.
    """
    global _webview_window
    if _webview_window:
        try:
            _webview_window.show()
        except Exception:
            pass


def _grab_region_without_webview(rect, delay: float = 0.25):
    """Hide the webview before grabbing a screen region, then restore it immediately."""
    from core.screenshot import grab_region
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        QApplication = None

    _hide_webview_window()
    if QApplication is not None:
        try:
            QApplication.processEvents()
        except Exception:
            pass
    time.sleep(max(0.0, delay))
    try:
        return grab_region(rect)
    finally:
        _restore_webview_window()


def select_region_tkinter(mode: str = "single_ocr") -> Dict:
    import queue
    from PySide6.QtCore import QRect
    from core.screenshot import get_virtual_geometry, grab_region
    
    try:
        # Step 1: hide self and capture the full desktop as the selector background.
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
        
        global _last_region, _question_region, _number_region
        
        if mode == "single_ocr":
            _last_region = result
            # Do NOT restore here. capture_ocr_from_selected_region() will immediately
            # take the real cropped screenshot, then restore the window.
        elif mode == "question_region":
            _question_region = result
            _restore_webview_window()
        elif mode == "number_region":
            _number_region = result
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

def get_state() -> Dict:
    return {
        "question_region": {"selected": False, "x": 0, "y": 0, "width": 0, "height": 0},
        "number_region": {"selected": False, "x": 0, "y": 0, "width": 0, "height": 0},
        "question_count": 0,
        "answers_count": 0,
        "mode": "test"
    }


def get_operation_status() -> Dict:
    return {
        "success": True,
        **_operation_state,
    }


def capture_ocr_with_tkinter(backend_name: str = "auto") -> Dict:
    global _last_ocr_text, _last_region
    
    select_result = select_region_tkinter("single_ocr")
    
    if not select_result.get("success"):
        return select_result
    
    region = select_result.get("region")
    
    return capture_ocr_from_selected_region(region, backend_name)


def capture_ocr(region: Dict = None, backend_name: str = "auto") -> Dict:
    global _last_ocr_text, _last_capture_path, _last_region
    
    if region is None:
        select_result = select_region("single_ocr")
        if not select_result.get("success"):
            return select_result
        region = select_result.get("region")
    
    from PySide6.QtCore import QRect
    from core.screenshot import grab_region
    from core.image_utils import prepare_image_for_ocr
    from core.ocr_engine import recognize_image
    
    rect = QRect(
        region.get("left", region.get("x", 0)),
        region.get("top", region.get("y", 0)),
        region.get("width", 0),
        region.get("height", 0)
    )
    
    if rect.width() <= 0 or rect.height() <= 0:
        return {
            "success": False,
            "error": "无效的截图区域"
        }
    
    _last_region = {
        "left": rect.x(),
        "top": rect.y(),
        "width": rect.width(),
        "height": rect.height()
    }
    
    start_time = time.time()
    
    try:
        image = grab_region(rect)
        ocr_image = prepare_image_for_ocr(image)
        text = recognize_image(ocr_image, backend_name)
        
        _last_ocr_text = text
        
        try:
            ocr_image.save(_last_capture_path)
        except Exception as e:
            print(f"Failed to save debug image: {e}")
        
        elapsed = time.time() - start_time
        
        return {
            "success": True,
            "text": text,
            "image_path": _last_capture_path,
            "backend": backend_name,
            "elapsed": round(elapsed, 2),
            "region": {
                "left": rect.x(),
                "top": rect.y(),
                "width": rect.width(),
                "height": rect.height()
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def recognize_fixed_region(backend_name: str = "auto") -> Dict:
    global _last_region
    
    if _last_region is None:
        return {
            "success": False,
            "error": "没有固定区域，请先执行一次截图识别"
        }
    
    return capture_ocr_from_selected_region(region=_last_region, backend_name=backend_name)


def begin_screen_capture(mode: str = "single_ocr") -> Dict:
    global _webview_window
    
    if _webview_window is None:
        return {
            "success": False,
            "error": "窗口未初始化"
        }
    
    try:
        import time
        import os
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
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        captures_dir = os.path.join(base_dir, "captures")
        if not os.path.exists(captures_dir):
            os.makedirs(captures_dir)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"full_screen_capture_{timestamp}.png"
        full_path = os.path.join(captures_dir, filename)
        image.save(full_path)
        
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        img_data_url = f"data:image/png;base64,{img_base64}"
        
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
    global _last_region, _question_region, _number_region
    
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
        _last_region = region_data
    elif mode == "question_region":
        _question_region = region_data
    elif mode == "number_region":
        _number_region = region_data
    
    return {
        "success": True,
        "mode": mode,
        "region": region_data
    }


def capture_ocr_from_selected_region(region: Dict, backend_name: str = "auto") -> Dict:
    global _last_ocr_text, _last_region
    
    try:
        from PySide6.QtCore import QRect
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": f"导入 QRect 失败: {e}\n{traceback.format_exc()}"
        }
    
    try:
        import os
        import base64
        from io import BytesIO
        from datetime import datetime
        from core.screenshot import grab_region
        from core.image_utils import prepare_image_for_ocr
        from core.ocr_engine import recognize_image
    except Exception as e:
        import traceback
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
        return {
            "success": False,
            "error": "无效的截图区域"
        }
    
    _last_region = region
    
    start_time = time.time()
    
    try:
        image = grab_region(rect)
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": f"grab_region 失败: {e}\n{traceback.format_exc()}"
        }
    
    try:
        ocr_image = prepare_image_for_ocr(image)
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": f"prepare_image_for_ocr 失败: {e}\n{traceback.format_exc()}"
        }
    
    try:
        text = recognize_image(ocr_image, backend_name)
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": f"recognize_image 失败: {e}\n{traceback.format_exc()}"
        }
    
    _last_ocr_text = text
    
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
    
    try:
        buffer = BytesIO()
        ocr_image.save(buffer, format="PNG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        image_data_url = f"data:image/png;base64,{image_base64}"
    except Exception as e:
        image_data_url = ""
        print(f"Failed to encode image to base64: {e}")
    
    elapsed = time.time() - start_time
    
    return {
        "success": True,
        "text": text,
        "image_path": image_path,
        "image_data_url": image_data_url,
        "backend": backend_name,
        "elapsed": round(elapsed, 2),
        "region": region
    }


def set_fixed_region(region: Dict) -> Dict:
    global _fixed_region
    _fixed_region = region
    return {
        "success": True,
        "message": "固定区域已设置"
    }


def copy_screenshot() -> Dict:
    return {
        "success": True,
        "message": "截图已复制到剪贴板"
    }


def copy_ocr_result(text: str = None) -> Dict:
    global _last_ocr_text
    
    if text is None:
        text = _last_ocr_text
    
    if not text:
        return {
            "success": False,
            "message": "没有可复制的文本"
        }
    
    try:
        import pyperclip
        pyperclip.copy(text)
        return {
            "success": True,
            "message": "OCR结果已复制到剪贴板"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"复制失败: {str(e)}"
        }


def clear_ocr_result() -> Dict:
    global _last_ocr_text
    _last_ocr_text = ""
    return {
        "success": True,
        "message": "OCR结果已清空"
    }


def export_collected_questions() -> Dict:
    global _collected_records
    
    if not _collected_records:
        return {
            "success": False,
            "error": "没有采集的题目"
        }
    
    lines = []
    for rec in _collected_records:
        no = rec.get("no", rec.get("index", 0))
        text = rec.get("ocr_text", "").strip()
        if text:
            lines.append(f"第{no}题：\n{text}\n")
    
    content = "\n".join(lines)
    
    try:
        import pyperclip
        pyperclip.copy(content)
        return {
            "success": True,
            "message": f"已复制 {len(lines)} 道题目到剪贴板",
            "count": len(lines),
            "content": content
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"复制失败: {str(e)}"
        }


def get_ai_prompt_with_questions() -> Dict:
    global _collected_records
    
    if not _collected_records:
        return {
            "success": False,
            "error": "没有采集的题目"
        }
    
    lines = []
    for rec in _collected_records:
        no = rec.get("no", rec.get("index", 0))
        text = rec.get("ocr_text", "").strip()
        if text:
            lines.append(f"{no}. {text}")
    
    questions_text = "\n".join(lines)
    
    prompt = f"""请根据以下题目内容，给出每道题的正确答案。

题目：
{questions_text}

请按以下格式回答：
1. A
2. B
3. C
...

只输出答案，不要解释。"""
    
    try:
        import pyperclip
        pyperclip.copy(prompt)
        return {
            "success": True,
            "message": f"AI提示词已复制到剪贴板（{len(lines)}道题）",
            "count": len(lines),
            "prompt": prompt
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"复制失败: {str(e)}"
        }


def select_question_region() -> Dict:
    result = select_region_tkinter("question_region")
    return result


def select_number_region() -> Dict:
    result = select_region_tkinter("number_region")
    return result


def select_region(mode: str) -> Dict:
    if _selection_controller is None:
        return {
            "success": False,
            "error": "原生截图控制器未初始化"
        }

    return _selection_controller.select_region(mode)


def save_number_region_capture() -> Dict:
    global _number_region
    
    if _number_region is None:
        return {
            "success": False,
            "error": "未选择题号区域"
        }
    
    from PySide6.QtCore import QRect
    from core.screenshot import grab_region
    
    try:
        
        rect = QRect(
            _number_region.get("left", 0),
            _number_region.get("top", 0),
            _number_region.get("width", 0),
            _number_region.get("height", 0)
        )
        
        image = grab_region(rect)
        save_path = "number_region_capture.png"
        image.save(save_path)
        
        return {
            "success": True,
            "message": "题号截图已保存",
            "path": save_path
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def detect_question_points(backend_name: str = "auto") -> Dict:
    global _number_region, _detected_question_points
    
    if _number_region is None:
        return {
            "success": False,
            "error": "未选择题号区域"
        }
    
    from PySide6.QtCore import QRect
    from core.screenshot import grab_region
    from core.box_ocr_backend import get_box_ocr_backend
    
    try:
        _set_operation_state("detect_question_points", True, 0, 0, "正在抓取题号区域", "capture")
        rect = QRect(
            _number_region.get("left", 0),
            _number_region.get("top", 0),
            _number_region.get("width", 0),
            _number_region.get("height", 0)
        )
        
        image = grab_region(rect)

        backend = get_box_ocr_backend(backend_name)
        
        _update_operation_state(message=f"题号 OCR 后端: {getattr(backend, 'name', backend_name)}", phase="ocr")
        boxes = backend.locate_text_boxes(
            image,
            _number_region.get("left", 0),
            _number_region.get("top", 0),
        )
        
        import re
        number_pattern = re.compile(r'^\d+$')
        
        points = []
        total_boxes = len(boxes)
        _update_operation_state(current=0, total=max(total_boxes, 1), message=f"已识别题号候选 {total_boxes} 个", phase="filter")
        for idx, box in enumerate(boxes, start=1):
            text = box.get("text", "").strip()
            if number_pattern.match(text):
                try:
                    no = int(text)
                    if 1 <= no <= 45:
                        points.append({
                            "no": no,
                            "x": box.get("screen_x", box.get("center_x", 0)),
                            "y": box.get("screen_y", box.get("center_y", 0)),
                            "source": "ocr"
                        })
                except Exception:
                    pass
            _update_operation_state(current=idx, total=max(total_boxes, 1), message=f"题号识别进度 {idx}/{total_boxes}", phase="filter")
        
        if points:
            y_coords = sorted(set(p["y"] for p in points))
            y_threshold = 20
            rows = []
            current_row = []
            last_y = None
            
            for p in sorted(points, key=lambda pt: pt["y"]):
                if last_y is None or abs(p["y"] - last_y) <= y_threshold:
                    current_row.append(p)
                    last_y = p["y"] if last_y is None else last_y
                else:
                    if current_row:
                        rows.append(current_row)
                    current_row = [p]
                    last_y = p["y"]
            
            if current_row:
                rows.append(current_row)
            
            for row in rows:
                row.sort(key=lambda p: p["x"])
            
            points = []
            for row in rows:
                points.extend(row)

        expected_count = _detect_expected_question_count_from_boxes(boxes)
        if expected_count and len(points) < expected_count:
            inferred_points = _infer_question_points(points, expected_count)
            if inferred_points:
                points = inferred_points
        
        _detected_question_points = points
        _update_operation_state(current=len(boxes), total=max(len(boxes), 1), message=f"题号识别完成，共 {len(points)} 个", phase="done")
        
        display_points = []
        for p in points:
            no = p["no"]
            if no <= 20:
                display_no = str(no)
            elif no <= 35:
                display_no = f"二-{no-20}"
            else:
                display_no = f"三-{no-35}"
            display_points.append({
                "display_no": display_no,
                "x": p["x"],
                "y": p["y"],
                "source": p["source"]
            })
        
        return {
            "success": True,
            "message": f"题号坐标识别完成 ({len(points)}个)",
            "points": display_points,
            "count": len(points)
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        _update_operation_state(message=f"题号识别失败: {e}", phase="error")
        return {
            "success": False,
            "error": str(e)
        }

def _detect_expected_question_count_from_boxes(boxes: list[dict]) -> int | None:
    import re
    import unicodedata

    totals = []
    for box in boxes:
        text = unicodedata.normalize("NFKC", box.get("text", "") or "").strip()
        if not text:
            continue
        for match in re.finditer(r"[\\/、]\s*(\d{1,3})\s*题", text):
            totals.append(int(match.group(1)))
        match = re.search(r"共\s*(\d{1,3})\s*题", text)
        if match:
            totals.append(int(match.group(1)))

    if not totals:
        return None
    return max(totals)


def _infer_question_points(points: list[dict], expected_count: int) -> list[dict] | None:
    if not points or expected_count <= len(points):
        return points

    sorted_points = sorted(points, key=lambda item: (item.get("y", 0), item.get("x", 0)))
    if len(sorted_points) < 2:
        return None

    row_groups: list[list[dict]] = []
    current_row = [sorted_points[0]]
    last_y = sorted_points[0].get("y", 0)
    for point in sorted_points[1:]:
        if abs(point.get("y", 0) - last_y) <= 50:
            current_row.append(point)
        else:
            row_groups.append(current_row)
            current_row = [point]
        last_y = point.get("y", 0)
    if current_row:
        row_groups.append(current_row)

    first_row = row_groups[0]
    x_values = sorted(p.get("x", 0) for p in first_row)
    if len(x_values) >= 2:
        x_diffs = [x_values[i + 1] - x_values[i] for i in range(len(x_values) - 1)]
        avg_x_diff = sum(x_diffs) / len(x_diffs)
    else:
        avg_x_diff = 0

    row_ys = [sum(p.get("y", 0) for p in row) / len(row) for row in row_groups]
    if len(row_ys) >= 2:
        y_diffs = [row_ys[i + 1] - row_ys[i] for i in range(len(row_ys) - 1)]
        avg_y_diff = sum(y_diffs) / len(y_diffs)
    else:
        avg_y_diff = 0

    columns = len(first_row)
    rows_needed = (expected_count + columns - 1) // max(1, columns)
    inferred_points = []
    point_idx = 0
    start_x = x_values[0]
    start_y = row_ys[0]

    for row in range(rows_needed):
        for col in range(columns):
            if point_idx < len(sorted_points):
                inferred_points.append(sorted_points[point_idx])
            else:
                inferred_points.append({
                    "no": str(point_idx + 1),
                    "x": int(round(start_x + col * avg_x_diff)),
                    "y": int(round(start_y + row * avg_y_diff)),
                    "source": "inferred",
                })
            point_idx += 1
            if point_idx >= expected_count:
                return inferred_points[:expected_count]

    return inferred_points[:expected_count] if inferred_points else None


def _run_collection_thread(options: Dict, result_queue):
    global _collected_records, _collection_running, _collection_stop_flag, _question_region, _detected_question_points
    
    from PySide6.QtCore import QRect
    from core.screenshot import grab_region
    
    test_mode = options.get("test_mode", False)
    save_images = options.get("save_images", True)
    click_delay = options.get("click_delay", 0.0)
    interval = options.get("interval", 0.5)
    parse_options = options.get("parse_options", False)
    text_ocr_backend = options.get("text_ocr_backend", "auto")
    option_ocr_backend = options.get("option_ocr_backend", "auto")
    from core.ocr_engine import recognize_image
    from core.option_extractor import extract_options_from_question_image
    
    try:
        rect = QRect(
            _question_region.get("left", 0),
            _question_region.get("top", 0),
            _question_region.get("width", 0),
            _question_region.get("height", 0)
        )
        
        screenshot_dir = "question_captures"
        if save_images:
            os.makedirs(screenshot_dir, exist_ok=True)
        
        points = _detected_question_points
        
        import pyautogui
        pyautogui.FAILSAFE = True
        
        total = len(points)
        _set_operation_state("start_collection", True, 0, total, "正在开始采集", "start")
        
        _hide_webview_window()
        time.sleep(0.2)
        
        for idx, point in enumerate(points, start=1):
            if _collection_stop_flag:
                _update_operation_state(message=f"采集已停止于 {idx - 1}/{total}", phase="stopped")
                break
            
            no = point.get("no", idx)
            x = point.get("x", 0)
            y = point.get("y", 0)
            _update_operation_state(current=idx - 1, total=total, message=f"采集中 {idx}/{total}，点击题号 {no}", phase="click")
            
            if not test_mode:
                pyautogui.click(x, y)
                time.sleep(click_delay)
            
            _update_operation_state(current=idx - 1, total=total, message=f"采集中 {idx}/{total}，正在截图", phase="capture")
            image = grab_region(rect)
            
            image_path = ""
            if save_images:
                image_path = os.path.join(screenshot_dir, f"question_{idx:03d}.png")
                image.save(image_path)
            
            record = {
                "index": idx,
                "no": no,
                "click_x": x,
                "click_y": y,
                "capture_image": image.copy(),
                "ocr_text": "",
                "image_path": image_path,
                "status": "captured"
            }

            if parse_options:
                _update_operation_state(current=idx - 1, total=total, message=f"采集中 {idx}/{total}，正文 OCR", phase="ocr")
                try:
                    ocr_text = recognize_image(image, text_ocr_backend).strip()
                except Exception as exc:
                    print(f"Text OCR failed: {repr(exc)}")
                    import traceback
                    traceback.print_exc()
                    ocr_text = ""
                record["ocr_text"] = ocr_text

                _update_operation_state(current=idx - 1, total=total, message=f"采集中 {idx}/{total}，解析选项", phase="option")
                try:
                    options_result = extract_options_from_question_image(
                        image,
                        _question_region.get("left", 0),
                        _question_region.get("top", 0),
                        option_ocr_backend,
                    )
                except Exception as exc:
                    print(f"Option extraction failed: {repr(exc)}")
                    import traceback
                    traceback.print_exc()
                    options_result = {}

                record["options"] = options_result
                for label, opt in options_result.items():
                    record[f"option_{label}_text"] = opt.get("text", "")
                    record[f"option_{label}_x"] = opt.get("screen_x", opt.get("x", 0))
                    record[f"option_{label}_y"] = opt.get("screen_y", opt.get("y", 0))
                    record[f"option_{label}_click_x"] = opt.get("click_x", opt.get("screen_x", 0))
                    record[f"option_{label}_click_y"] = opt.get("click_y", opt.get("screen_y", 0))
            
            _collected_records.append(record)
            _update_operation_state(current=idx, total=total, message=f"采集进度 {idx}/{total}，题号 {no}", phase="done")
            
            time.sleep(interval)
        
        _collection_running = False
        _restore_webview_window()
        _clear_operation_state("start_collection")
        
        result_queue.put({
            "success": True,
            "message": f"采集完成 ({len(_collected_records)}题)",
            "count": len(_collected_records),
            "records": [_serialize_collected_record(record) for record in _collected_records]
        })
    except Exception as e:
        _collection_running = False
        _restore_webview_window()
        import traceback
        traceback.print_exc()
        _update_operation_state(message=f"采集失败: {e}", phase="error")
        result_queue.put({
            "success": False,
            "error": str(e)
        })


def start_collection(options: Dict) -> Dict:
    global _collected_records, _collection_running, _collection_stop_flag, _question_region, _detected_question_points
    
    if _question_region is None:
        return {
            "success": False,
            "error": "未设置题目区域"
        }
    
    if not _detected_question_points:
        return {
            "success": False,
            "error": "未识别题号坐标"
        }
    
    _collection_running = True
    _collection_stop_flag = False
    _collected_records = []
    
    import queue
    result_queue = queue.Queue()
    
    thread = threading.Thread(
        target=_run_collection_thread,
        args=(options, result_queue),
        daemon=True
    )
    thread.start()
    
    return {
        "success": True,
        "message": "采集已启动",
        "total": len(_detected_question_points)
    }


def get_collection_status() -> Dict:
    global _collected_records, _collection_running
    
    return {
        "success": True,
        "running": _collection_running,
        "current": len(_collected_records),
        "total": len(_detected_question_points),
        "phase": _operation_state.get("phase", ""),
        "message": _operation_state.get("message", ""),
        "records": [_serialize_collected_record(record) for record in _collected_records],
        "latest_text": _collected_records[-1].get("ocr_text", "") if _collected_records else "",
        "latest_image_path": _collected_records[-1].get("image_path", "") if _collected_records else ""
    }


def stop_collection() -> Dict:
    global _collection_stop_flag
    _collection_stop_flag = True
    return {
        "success": True,
        "message": "采集已停止"
    }


def parse_collected_options(options: Dict = None) -> Dict:
    global _collected_records, _question_region
    
    if not _collected_records:
        return {
            "success": False,
            "error": "没有采集记录"
        }
    
    if options is None:
        options = {}
    
    text_ocr_backend = options.get("text_ocr_backend", "auto")
    option_ocr_backend = options.get("option_ocr_backend", "auto")
    
    from core.ocr_engine import recognize_image
    from core.option_extractor import extract_options_from_question_image
    
    try:
        total = len(_collected_records)
        _set_operation_state("parse_collected_options", True, 0, total, "正在解析已采集内容", "start")
        for record in _collected_records:
            record["status"] = "parsing"
            image_path = record.get("image_path", "")
            if not image_path:
                record["status"] = "missing_image"
                _update_operation_state(
                    current=record.get("index", 0),
                    total=total,
                    message=f"第 {record.get('index', '?')} 题没有截图，跳过",
                    phase="skip",
                )
                continue
            
            try:
                option_img = record.get("capture_image")
                if option_img is None:
                    from PIL import Image as PILImage
                    with PILImage.open(image_path) as file_image:
                        option_img = file_image.copy()
                else:
                    option_img = option_img.copy()
                
                try:
                    ocr_text = recognize_image(option_img, text_ocr_backend)
                    record["ocr_text"] = ocr_text
                except Exception as e:
                    print(f"Text OCR failed: {e}")
                    record["ocr_text"] = ""

                _update_operation_state(
                    current=record.get("index", 0),
                    total=total,
                    message=f"第 {record.get('index', '?')} 题正在解析选项坐标",
                    phase="option",
                )
                
                options_result = extract_options_from_question_image(
                    option_img,
                    _question_region.get("left", 0),
                    _question_region.get("top", 0),
                    option_ocr_backend
                )
                record["options"] = options_result
                for label, opt in options_result.items():
                    record[f"option_{label}_text"] = opt.get("text", "")
                    record[f"option_{label}_x"] = opt.get("screen_x", opt.get("x", 0))
                    record[f"option_{label}_y"] = opt.get("screen_y", opt.get("y", 0))
                    record[f"option_{label}_click_x"] = opt.get("click_x", opt.get("screen_x", 0))
                    record[f"option_{label}_click_y"] = opt.get("click_y", opt.get("screen_y", 0))
                
                record["status"] = "parsed"
                _update_operation_state(
                    current=record.get("index", 0),
                    total=total,
                    message=f"第 {record.get('index', '?')} 题解析完成，识别到 {len(options_result)} 个选项",
                    phase="done",
                )
            except Exception as e:
                print(f"Option extraction failed: {e}")
                import traceback
                traceback.print_exc()
                record["status"] = "parse_failed"
                _update_operation_state(
                    current=record.get("index", 0),
                    total=total,
                    message=f"第 {record.get('index', '?')} 题解析失败: {e}",
                    phase="error",
                )
        
        return {
            "success": True,
            "message": f"选项解析完成 ({len(_collected_records)}题)",
            "records": [_serialize_collected_record(record) for record in _collected_records]
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        _update_operation_state(message=f"选项解析失败: {e}", phase="error")
        return {
            "success": False,
            "error": str(e)
        }


def get_collection_results() -> Dict:
    results = []
    for i in range(1, 46):
        results.append({
            "index": i,
            "click_x": 100 + (i % 5) * 150,
            "click_y": 200 + (i // 5) * 80,
            "ocr_text": f"题目{i}的内容",
            "image_path": f"capture_{i}.png",
            "status": "success"
        })
    
    return {
        "success": True,
        "results": results,
        "count": len(results)
    }


def collect_questions() -> Dict:
    questions = []
    for i in range(1, 46):
        if i <= 20:
            qtype = "single"
            display_no = str(i)
        elif i <= 35:
            qtype = "multi"
            display_no = f"二-{i-20}"
        else:
            qtype = "true_false"
            display_no = f"三-{i-35}"
        
        questions.append({
            "id": i,
            "display_no": display_no,
            "type": qtype,
            "x": 100 + (i % 5) * 150,
            "y": 200 + (i // 5) * 80,
            "has_text": True
        })
    
    return {
        "success": True,
        "message": "题目采集完成 (Mock)",
        "questions": questions,
        "count": len(questions)
    }


def parse_answers(text: str) -> Dict:
    from core.answer_importer import normalize_answer_text
    
    result = normalize_answer_text(text)
    answers = result.get("answers", {})
    invalid = result.get("invalid", [])
    
    ANSWER_TYPE_MAP = {
        1: ("single", "1-20"),
        2: ("multi", "21-35"),
        3: ("true_false", "36-45")
    }
    
    def get_question_type(global_id: str) -> tuple:
        if global_id.startswith("Q"):
            try:
                num = int(global_id[1:])
                if num <= 20:
                    return ("single", f"1-{num}")
                elif num <= 35:
                    return ("multi", f"21-{num}")
                else:
                    return ("true_false", f"36-{num}")
            except:
                pass
        elif global_id.startswith("auto_"):
            return ("single", global_id)
        elif "-" in global_id:
            parts = global_id.split("-")
            if len(parts) == 2:
                prefix = parts[0]
                num = int(parts[1])
                if prefix in ["一", "1", "单"]:
                    return ("single", f"1-{num}")
                elif prefix in ["二", "2", "多"]:
                    return ("multi", f"21-{num}")
                elif prefix in ["三", "3", "判断"]:
                    return ("true_false", f"36-{num}")
        return ("single", global_id)
    
    rows = []
    for raw_input, error in invalid:
        rows.append({
            "raw_input": raw_input,
            "global_id": "",
            "display_no": "",
            "question_type": "",
            "answer": "",
            "status": "invalid",
            "message": error
        })
    
    for key, answer in answers.items():
        qtype, display_no = get_question_type(key)
        
        if key.startswith("Q"):
            global_id = key
        elif key.startswith("auto_"):
            global_id = key
        elif "-" in key:
            parts = key.split("-")
            if len(parts) == 2:
                prefix = parts[0]
                num = int(parts[1])
                if prefix in ["一", "1", "单"]:
                    global_id = f"Q{num:06d}"
                elif prefix in ["二", "2", "多"]:
                    global_id = f"Q{20 + num:06d}"
                elif prefix in ["三", "3", "判断"]:
                    global_id = f"Q{35 + num:06d}"
                else:
                    global_id = key
            else:
                global_id = key
        else:
            try:
                num = int(key)
                global_id = f"Q{num:06d}"
            except:
                global_id = key
        
        rows.append({
            "raw_input": f"{key} {answer}",
            "global_id": global_id,
            "display_no": display_no,
            "question_type": qtype,
            "answer": answer,
            "status": "valid",
            "message": ""
        })
    
    final_answers = {}
    for row in rows:
        if row["status"] == "valid" and row["global_id"]:
            final_answers[row["global_id"]] = row["answer"]
    
    return {
        "success": True,
        "answers": final_answers,
        "rows": rows,
        "invalid": invalid
    }


def execute_clicks(plan: List[Dict]) -> Dict:
    return {
        "success": True,
        "message": f"执行完成 (Mock)",
        "executed": len(plan)
    }


_execution_stopped = False
_answer_click_tasks = []


def build_answer_click_tasks(answers_data: Dict = None) -> Dict:
    global _detected_question_points, _collected_records, _answer_click_tasks, _execution_stopped
    _execution_stopped = False
    
    if answers_data is None:
        answers_data = {}
    
    if isinstance(answers_data, dict) and "answers" in answers_data:
        answers_dict = answers_data.get("answers", {})
    elif isinstance(answers_data, dict):
        answers_dict = answers_data
    elif isinstance(answers_data, list):
        answers_dict = {}
        for item in answers_data:
            if isinstance(item, dict):
                gid = item.get("global_id", "")
                ans = item.get("answer", "")
                if gid and ans:
                    answers_dict[gid] = ans
    else:
        answers_dict = {}
    
    tasks = []
    ready_count = 0
    no_answer_count = 0
    no_option_count = 0
    need_check_count = 0
    
    question_points_map = {}
    for pt in _detected_question_points:
        no = pt.get("no", 0)
        question_points_map[no] = {
            "x": pt.get("x", 0),
            "y": pt.get("y", 0),
            "display_no": pt.get("display_no", str(no))
        }
    
    records_map = {}
    for rec in _collected_records:
        no = rec.get("no", rec.get("index", 0))
        records_map[no] = {
            "click_x": rec.get("click_x", 0),
            "click_y": rec.get("click_y", 0),
            "option_A_click_x": rec.get("option_A_click_x", 0),
            "option_A_click_y": rec.get("option_A_click_y", 0),
            "option_B_click_x": rec.get("option_B_click_x", 0),
            "option_B_click_y": rec.get("option_B_click_y", 0),
            "option_C_click_x": rec.get("option_C_click_x", 0),
            "option_C_click_y": rec.get("option_C_click_y", 0),
            "option_D_click_x": rec.get("option_D_click_x", 0),
            "option_D_click_y": rec.get("option_D_click_y", 0),
        }
    
    for no in range(1, 46):
        global_id = f"Q{no:06d}"
        user_answer = answers_dict.get(global_id, "")
        
        qpoint = question_points_map.get(no)
        record = records_map.get(no)
        
        if no <= 20:
            display_no = str(no)
            qtype = "single"
        elif no <= 35:
            display_no = f"二-{no-20}"
            qtype = "multi"
        else:
            display_no = f"三-{no-35}"
            qtype = "true_false"
        
        if not user_answer:
            tasks.append({
                "index": no,
                "question_no": no,
                "display_no": display_no,
                "global_id": global_id,
                "answer": "",
                "question_click": [qpoint["x"], qpoint["y"]] if qpoint else None,
                "answer_clicks": [],
                "status": "no_answer",
                "message": "用户没有提供答案"
            })
            no_answer_count += 1
            continue
        
        if not qpoint:
            tasks.append({
                "index": no,
                "question_no": no,
                "display_no": display_no,
                "global_id": global_id,
                "answer": user_answer,
                "question_click": None,
                "answer_clicks": [],
                "status": "no_question_point",
                "message": "没有题号坐标"
            })
            no_option_count += 1
            continue
        
        if not record:
            tasks.append({
                "index": no,
                "question_no": no,
                "display_no": display_no,
                "global_id": global_id,
                "answer": user_answer,
                "question_click": [qpoint["x"], qpoint["y"]],
                "answer_clicks": [],
                "status": "no_option",
                "message": "没有采集到选项坐标"
            })
            no_option_count += 1
            continue
        
        answer_clicks = []
        
        if qtype == "true_false":
            is_true = user_answer.upper() in ["TRUE", "T", "正确", "对", "YES", "1"]
            if is_true:
                answer_clicks.append([record.get("option_A_click_x", 0), record.get("option_A_click_y", 0)])
            else:
                answer_clicks.append([record.get("option_B_click_x", 0), record.get("option_B_click_y", 0)])
        else:
            answer_upper = user_answer.upper()
            for char in answer_upper:
                if char == "A":
                    answer_clicks.append([record.get("option_A_click_x", 0), record.get("option_A_click_y", 0)])
                elif char == "B":
                    answer_clicks.append([record.get("option_B_click_x", 0), record.get("option_B_click_y", 0)])
                elif char == "C":
                    answer_clicks.append([record.get("option_C_click_x", 0), record.get("option_C_click_y", 0)])
                elif char == "D":
                    answer_clicks.append([record.get("option_D_click_x", 0), record.get("option_D_click_y", 0)])
        
        if not answer_clicks or all(ac == [0, 0] for ac in answer_clicks):
            tasks.append({
                "index": no,
                "question_no": no,
                "display_no": display_no,
                "global_id": global_id,
                "answer": user_answer,
                "question_click": [qpoint["x"], qpoint["y"]],
                "answer_clicks": [],
                "status": "no_option",
                "message": "选项坐标未找到"
            })
            no_option_count += 1
            continue
        
        if qtype == "multi":
            expected_len = len(user_answer)
            if len(answer_clicks) != expected_len:
                need_check_count += 1
                status = "need_check"
            else:
                ready_count += 1
                status = "ready"
        else:
            if len(answer_clicks) != 1:
                need_check_count += 1
                status = "need_check"
            else:
                ready_count += 1
                status = "ready"
        
        tasks.append({
            "index": no,
            "question_no": no,
            "display_no": display_no,
            "global_id": global_id,
            "answer": user_answer,
            "question_click": [qpoint["x"], qpoint["y"]],
            "answer_clicks": answer_clicks,
            "status": status,
            "message": ""
        })
    
    _answer_click_tasks = tasks
    
    return {
        "success": True,
        "tasks": tasks,
        "summary": {
            "ready": ready_count,
            "no_answer": no_answer_count,
            "no_option": no_option_count,
            "need_check": need_check_count
        }
    }


def execute_selected_answer(index: int) -> Dict:
    return {
        "success": False,
        "error": "执行点击尚未接入"
    }


def execute_next_answer() -> Dict:
    return {
        "success": False,
        "error": "执行点击尚未接入"
    }


def execute_all_answers() -> Dict:
    return {
        "success": False,
        "error": "执行点击尚未接入"
    }


def stop_execution() -> Dict:
    return {
        "success": False,
        "error": "执行点击尚未接入"
    }


def get_execution_status() -> Dict:
    return {
        'success': True,
        **_operation_state,
    }


def _execute_answer_task(task: Dict, test_mode: bool = False, click_delay: float = 0.15, interval: float = 0.15) -> Dict:
    import pyautogui

    question_click = task.get('question_click') or []
    answer_clicks = task.get('answer_clicks', []) or []
    if len(question_click) != 2 or not answer_clicks:
        return {
            'success': False,
            'skipped': True,
            'message': '没有可执行的坐标',
        }

    if test_mode:
        return {
            'success': True,
            'skipped': True,
            'message': '测试模式，未执行真实点击',
        }

    pyautogui.click(int(question_click[0]), int(question_click[1]))
    time.sleep(max(0.0, click_delay))
    for idx, point in enumerate(answer_clicks, start=1):
        pyautogui.click(int(point[0]), int(point[1]))
        if idx < len(answer_clicks):
            time.sleep(max(0.0, interval))

    return {
        'success': True,
        'skipped': False,
        'message': f"已点击题号 {task.get('question_no', '')} 的答案",
    }


def execute_all_answers_real(options: Dict = None) -> Dict:
    global _execution_stopped, _execution_running, _answer_click_cursor

    options = options or {}
    test_mode = bool(options.get('test_mode', False))
    click_delay = float(options.get('click_delay', 0.15))
    interval = float(options.get('interval', 0.15))

    if not _answer_click_tasks:
        return {
            'success': False,
            'error': '没有可执行的答案任务'
        }

    _execution_stopped = False
    _execution_running = True
    _answer_click_cursor = 0
    total = len(_answer_click_tasks)
    _set_operation_state('execute_all_answers', True, 0, total, '正在执行答案点击', 'start')

    try:
        import pyautogui

        pyautogui.FAILSAFE = True
        _hide_webview_window()
        time.sleep(0.15)

        executed = 0
        skipped = 0
        for idx, task in enumerate(_answer_click_tasks, start=1):
            if _execution_stopped:
                _update_operation_state(current=idx - 1, total=total, message=f'执行已停止于 {idx - 1}/{total}', phase='stopped')
                break

            _update_operation_state(
                current=idx - 1,
                total=total,
                message=f'执行答案进度 {idx}/{total}，题号 {task.get("question_no", idx)}',
                phase='click',
            )

            if task.get('status') != 'ready':
                skipped += 1
                continue

            result = _execute_answer_task(task, test_mode=test_mode, click_delay=click_delay, interval=interval)
            if result.get('success') and not result.get('skipped'):
                executed += 1
            else:
                skipped += 1

            _update_operation_state(
                current=idx,
                total=total,
                message=f'执行完成 {idx}/{total}',
                phase='done',
            )

        _execution_running = False
        _restore_webview_window()
        _clear_operation_state('execute_all_answers')
        return {
            'success': True,
            'message': f'答案执行完成，已执行 {executed} 题，跳过 {skipped} 题',
            'executed': executed,
            'skipped': skipped,
            'total': total,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        _execution_running = False
        _restore_webview_window()
        _update_operation_state(message=f'执行答案失败: {e}', phase='error')
        return {
            'success': False,
            'error': str(e)
        }


def execute_selected_answer_real(index: int, options: Dict = None) -> Dict:
    if index < 0 or index >= len(_answer_click_tasks):
        return {
            'success': False,
            'error': '索引超出范围'
        }
    options = options or {}
    try:
        return _execute_answer_task(
            _answer_click_tasks[index],
            test_mode=bool(options.get('test_mode', False)),
            click_delay=float(options.get('click_delay', 0.15)),
            interval=float(options.get('interval', 0.15)),
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }


def execute_next_answer_real(options: Dict = None) -> Dict:
    global _answer_click_cursor
    if _answer_click_cursor >= len(_answer_click_tasks):
        return {
            'success': False,
            'error': '没有下一题可执行'
        }
    result = execute_selected_answer_real(_answer_click_cursor, options)
    if result.get('success'):
        _answer_click_cursor += 1
    return result


def stop_execution_real() -> Dict:
    global _execution_stopped
    _execution_stopped = True
    _update_operation_state(message='正在请求停止执行', phase='stop')
    return {
        'success': True,
        'message': '已请求停止执行'
    }
