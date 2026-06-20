"""
Web 后端 - 核心模块
包含：全局状态、窗口管理、操作状态
"""

import threading
import time
from typing import Dict

# ============= 全局状态 =============
_last_ocr_text = ""
_fixed_region = None
_last_capture_path = "last_capture_debug.png"
_question_region = None
_number_region = None
_last_region = None
_last_full_screen_image = None  # 全屏截图（PIL Image），选区域时保存，crop 区域图用
_last_number_region_image = None  # 题号区域截图（从全屏图 crop 出来）
_detected_question_points = []
_collected_records = []
_collection_lock = threading.Lock()  # 保护 _collected_records 的线程锁
_collection_running = False
_collection_stop_flag = False
_webview_window = None
_selection_controller = None
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

_execution_stop_flag = False
_answer_click_tasks = []


# ============= 状态管理函数 =============

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


def get_operation_status() -> Dict:
    """获取当前操作状态"""
    return _operation_state.copy()


def _serialize_collected_record(record: dict) -> dict:
    if not isinstance(record, dict):
        return {}
    data = dict(record)
    data.pop("capture_image", None)
    return data


# ============= 窗口管理 =============

def set_window(window):
    global _webview_window
    _webview_window = window


def set_selection_controller(controller):
    global _selection_controller
    _selection_controller = controller


def _hide_webview_window():
    """隐藏 webview 窗口"""
    global _webview_window
    if _webview_window:
        try:
            _webview_window.hide()
        except Exception:
            pass


def _restore_webview_window():
    """恢复显示 webview 窗口"""
    global _webview_window
    if _webview_window:
        try:
            _webview_window.show()
        except Exception:
            pass


# ============= 导出全局变量供外部访问 =============

def get_state() -> Dict:
    return {
        "last_ocr_text": _last_ocr_text,
        "question_region": _question_region,
        "number_region": _number_region,
        "last_region": _last_region,
        "detected_question_points": _detected_question_points,
        "collected_records": _collected_records,
        "collection_running": _collection_running,
        "operation_state": _operation_state,
    }


# ============= 统一的状态修改器 =============

def update_last_ocr_text(text: str):
    """更新 OCR 识别的文本（统一状态修改器）"""
    global _last_ocr_text
    _last_ocr_text = text


def update_question_region(region: Dict):
    """更新题目区域"""
    global _question_region
    _question_region = region


def update_number_region(region: Dict):
    """更新题号区域"""
    global _number_region
    _number_region = region


def update_last_region(region: Dict):
    """更新最后截图区域"""
    global _last_region
    _last_region = region


def add_collected_record(record: Dict):
    """添加采集记录（线程安全）"""
    global _collected_records
    with _collection_lock:
        _collected_records.append(record)


def get_question_region():
    """获取题目区域"""
    return _question_region


def get_number_region():
    """获取题号区域"""
    return _number_region


def get_last_region():
    """获取最后截图区域"""
    return _last_region


def update_number_region_image(image):
    """保存题号区域截图（PIL Image）"""
    global _last_number_region_image
    _last_number_region_image = image


def get_number_region_image():
    """获取题号区域截图"""
    return _last_number_region_image


def update_full_screen_image(image):
    """保存全屏截图"""
    global _last_full_screen_image
    _last_full_screen_image = image


def get_full_screen_image():
    """获取全屏截图"""
    return _last_full_screen_image


def get_detected_question_points():
    """获取检测到的题号坐标"""
    return _detected_question_points


def update_detected_question_points(points):
    """更新检测到的题号坐标"""
    global _detected_question_points
    _detected_question_points = points


def clear_collected_records():
    """清空采集记录"""
    _collected_records.clear()
