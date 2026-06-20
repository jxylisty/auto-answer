"""
API Bridge - Web 端适配层
本文件作为适配层，将 web_backend 模块的函数暴露给前端调用
"""

# 从 web_backend 导入所有核心函数
from web_backend import (
    # 核心
    set_window,
    set_selection_controller,
    get_state,
    get_operation_status,
    # OCR
    capture_ocr,
    capture_ocr_from_selected_region,
    recognize_fixed_region,
    capture_ocr_with_tkinter,
    # 区域
    select_region,
    begin_screen_capture,
    finish_region_select,
    select_question_region,
    select_number_region,
    save_number_region_capture,
    # 采集
    detect_question_points,
    start_collection,
    get_collection_status,
    stop_collection,
    parse_collected_options,
    # 执行
    parse_answers,
    build_answer_click_tasks,
    execute_all_answers_real,
    execute_selected_answer_real,
    execute_next_answer_real,
    stop_execution_real,
    get_execution_status,
    # 剪贴板
    copy_ocr_result,
    clear_ocr_result,
    export_collected_questions,
    get_ai_prompt_with_questions,
    set_fixed_region,
    copy_screenshot,
)

# 导出内部变量/函数供 web_main 使用
from web_backend import (
    _collected_records,
    _execution_stop_flag,
    _answer_click_tasks,
    _operation_state,
    _restore_webview_window,
    # getter 函数
    get_question_region,
    get_number_region,
    get_last_region,
    get_detected_question_points,
)

# 兼容旧版 - 导出别名
_execution_stopped = _execution_stop_flag

# Mock 函数 - 用于兼容前端
def get_collection_results():
    """获取采集结果 - 返回真实数据"""
    results = []
    for rec in _collected_records:
        results.append({
            "index": rec.get("no", rec.get("index", 0)),
            "click_x": rec.get("question_click_x", 0),
            "click_y": rec.get("question_click_y", 0),
            "ocr_text": rec.get("ocr_text", ""),
            "image_path": rec.get("image_path", ""),
            "status": "success" if rec.get("ocr_text", "").strip() else "empty"
        })
    return {
        "success": True,
        "results": results,
        "count": len(results)
    }


def collect_questions():
    """采集题目 - 调用真正的采集流程"""
    import time

    # 先检测题号
    number_region = get_number_region()
    if not number_region:
        return {
            "success": False,
            "message": "未选择题号区域"
        }

    detect_result = detect_question_points({"backend": "auto"})
    if not detect_result.get("success"):
        return {
            "success": False,
            "message": detect_result.get("error", "题号检测失败")
        }

    # 启动采集
    start_result = start_collection({"text_ocr_backend": "auto", "option_ocr_backend": "auto"})
    if not start_result.get("success"):
        return {
            "success": False,
            "message": start_result.get("error", "采集启动失败")
        }

    # 等待采集完成（最多 120 秒）
    for _ in range(240):
        time.sleep(0.5)
        status = get_collection_status()
        if not status.get("running", False):
            break

    # 构建前端期望的格式
    records = _collected_records
    questions = []
    for rec in records:
        no = rec.get("no", rec.get("index", 0))
        questions.append({
            "id": no,
            "display_no": str(no),
            "type": rec.get("question_type", "single"),
            "x": rec.get("question_click_x", 0),
            "y": rec.get("question_click_y", 0),
            "has_text": bool(rec.get("ocr_text", "").strip())
        })

    return {
        "success": True,
        "message": f"题目采集完成，共 {len(questions)} 题",
        "questions": questions,
        "count": len(questions)
    }


def execute_clicks(plan):
    """执行点击（Mock）"""
    return {
        "success": True,
        "message": f"执行完成 (Mock)",
        "executed": len(plan) if plan else 0
    }


# 兼容旧版 - 导出 execute_selected_answer 等
def execute_selected_answer(index: int):
    return execute_selected_answer_real(index)


def execute_next_answer():
    return execute_next_answer_real()


def execute_all_answers():
    return execute_all_answers_real()


def stop_execution():
    return stop_execution_real()
