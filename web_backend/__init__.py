"""
Web 后端 - 总控入口
聚合所有模块，统一导出 API
"""

# 核心模块
from .core import (
    set_window,
    set_selection_controller,
    _hide_webview_window,
    _restore_webview_window,
    get_state,
    get_operation_status,
    _operation_state,
    # 状态修改器
    update_last_ocr_text,
    update_question_region,
    update_number_region,
    update_last_region,
    add_collected_record,
    clear_collected_records,
)

# OCR 模块
from .ocr import (
    capture_ocr,
    capture_ocr_from_selected_region,
    recognize_fixed_region,
    capture_ocr_with_tkinter,
)

# 区域模块
from .region import (
    select_region,
    select_region_tkinter,
    begin_screen_capture,
    finish_region_select,
    select_question_region,
    select_number_region,
    save_number_region_capture,
)

# 采集模块
from .collection import (
    detect_question_points,
    start_collection,
    get_collection_status,
    stop_collection,
    parse_collected_options,
    # 智能网格推断（独立API，用户手动触发）
    trigger_infer_missing_points,
    # 手动校准题号坐标
    get_mouse_position,
    # 非阻塞快捷键监听
    start_hotkey_listener,
    check_hotkey_result,
    cancel_hotkey_listener,
    add_or_update_question_point,
    delete_question_point,
)

# 执行模块
from .execution import (
    parse_answers,
    build_answer_click_tasks,
    execute_all_answers_real,
    execute_selected_answer_real,
    execute_next_answer_real,
    stop_execution_real,
    get_execution_status,
)

# 剪贴板模块
from .clipboard import (
    copy_ocr_result,
    clear_ocr_result,
    export_collected_questions,
    get_ai_prompt_with_questions,
    set_fixed_region,
    copy_screenshot,
)

# 兼容旧版 - 导出内部变量供 api_bridge 使用
from .core import (
    _collected_records,
    _execution_stop_flag,
    _answer_click_tasks,
    _operation_state,
    # getter 函数
    get_question_region,
    get_number_region,
    get_last_region,
    get_detected_question_points,
)

__all__ = [
    # 核心
    "set_window",
    "set_selection_controller",
    "get_state",
    "get_operation_status",
    # OCR
    "capture_ocr",
    "capture_ocr_from_selected_region",
    "recognize_fixed_region",
    "capture_ocr_with_tkinter",
    # 区域
    "select_region",
    "begin_screen_capture",
    "finish_region_select",
    "select_question_region",
    "select_number_region",
    "save_number_region_capture",
    # 采集
    "detect_question_points",
    "start_collection",
    "get_collection_status",
    "stop_collection",
    "parse_collected_options",
    # 智能网格推断（独立API，用户手动触发）
    "trigger_infer_missing_points",
    # 手动校准题号坐标
    "get_mouse_position",
    # 非阻塞快捷键监听
    "start_hotkey_listener",
    "check_hotkey_result",
    "cancel_hotkey_listener",
    "add_or_update_question_point",
    "delete_question_point",
    # 执行
    "parse_answers",
    "build_answer_click_tasks",
    "execute_all_answers_real",
    "execute_selected_answer_real",
    "execute_next_answer_real",
    "stop_execution_real",
    "get_execution_status",
    # 剪贴板
    "copy_ocr_result",
    "clear_ocr_result",
    "export_collected_questions",
    "get_ai_prompt_with_questions",
    "set_fixed_region",
    "copy_screenshot",
]
