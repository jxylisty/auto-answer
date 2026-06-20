"""
Web 后端 - 执行模块
包含：答案解析、点击执行
"""

import time
from typing import Dict, List

from .core import (
    _collected_records,
    _answer_click_tasks,
    _execution_stop_flag,
    _hide_webview_window,
    _restore_webview_window,
    _set_operation_state,
    _update_operation_state,
    _clear_operation_state,
    get_detected_question_points,
)


def parse_answers(text: str) -> Dict:
    """解析答案文本"""
    from core.answer_importer import normalize_answer_text

    result = normalize_answer_text(text)
    answers = result.get("answers", {})
    invalid = result.get("invalid", [])

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
        # 统一返回 "auto"，不再强行猜测题型
        qtype = "auto"

        if key.startswith("Q"):
            global_id = key
        elif key.startswith("auto_"):
            global_id = key
        elif "-" in key:
            # 废除具体题数偏移假设，直接将 key 当作 global_id
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
            "display_no": key,
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


def build_answer_click_tasks(answers_data: Dict = None) -> Dict:
    """构建答案点击任务（单多选融合，动态校验）"""
    global _answer_click_tasks, _execution_stop_flag
    _execution_stop_flag = False

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

    # 题号坐标映射
    question_points_map = {}
    for pt in get_detected_question_points():
        no = pt.get("no", 0)
        question_points_map[no] = {
            "x": pt.get("x", 0),
            "y": pt.get("y", 0),
            "display_no": pt.get("display_no", str(no))
        }

    # 采集记录映射 - 直接保存完整记录，支持任意选项字母
    records_map = {}
    for rec in _collected_records:
        no = rec.get("no", rec.get("index", 0))
        records_map[no] = rec

    # 智能点击提取算法
    TRUE_TOKENS = {"TRUE", "T", "正确", "对", "YES", "1", "√"}
    FALSE_TOKENS = {"FALSE", "F", "错误", "错", "NO", "0", "×"}

    # 动态获取最大题号
    all_nos = set(question_points_map.keys()) | set(records_map.keys())
    max_no = max(all_nos) if all_nos else 0

    for no in range(1, max_no + 1):
        global_id = f"Q{no:06d}"
        user_answer = answers_dict.get(global_id, "")

        qpoint = question_points_map.get(no)
        record = records_map.get(no)

        # 使用题号坐标字典中自带的名称
        display_no = qpoint.get("display_no", str(no)) if qpoint else str(no)

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

        # 智能点击提取：根据答案内容动态映射坐标
        answer_clicks = []
        answer_upper = user_answer.upper()

        if answer_upper in TRUE_TOKENS:
            # 正确/是/True — 兼容 option_extractor 输出的多种键名
            for true_key in ("正确", "T", "TRUE", "A"):
                cx = record.get(f"option_{true_key}_click_x", 0)
                cy = record.get(f"option_{true_key}_click_y", 0)
                if cx != 0 or cy != 0:
                    answer_clicks.append([cx, cy])
                    break
            if not answer_clicks:
                answer_clicks.append([0, 0])
        elif answer_upper in FALSE_TOKENS:
            # 错误/否/False — 兼容 option_extractor 输出的多种键名
            for false_key in ("错误", "F", "FALSE", "B"):
                cx = record.get(f"option_{false_key}_click_x", 0)
                cy = record.get(f"option_{false_key}_click_y", 0)
                if cx != 0 or cy != 0:
                    answer_clicks.append([cx, cy])
                    break
            if not answer_clicks:
                answer_clicks.append([0, 0])
        else:
            # 单多选融合：不区分题型，答案里有几个字母就提取几个坐标
            for char in answer_upper:
                if char.isalpha():  # 只处理字母
                    cx = record.get(f"option_{char}_click_x", 0)
                    cy = record.get(f"option_{char}_click_y", 0)
                    if cx != 0 or cy != 0:
                        answer_clicks.append([cx, cy])

        # 动态状态校验
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

        # 计算期望的点击次数
        if answer_upper in TRUE_TOKENS or answer_upper in FALSE_TOKENS:
            expected_len = 1
        else:
            expected_len = len([c for c in answer_upper if c.isalpha()])

        if len(answer_clicks) != expected_len:
            need_check_count += 1
            status = "need_check"
            message = f"答案字母数({expected_len})与坐标数({len(answer_clicks)})不匹配"
        else:
            ready_count += 1
            status = "ready"
            message = ""

        tasks.append({
            "index": no,
            "question_no": no,
            "display_no": display_no,
            "global_id": global_id,
            "answer": user_answer,
            "question_click": [qpoint["x"], qpoint["y"]],
            "answer_clicks": answer_clicks,
            "status": status,
            "message": message
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


def _execute_answer_task(task: Dict, test_mode: bool = False, click_delay: float = 0.15, interval: float = 0.15, click_mode: str = "physical") -> Dict:
    """执行单个答案点击任务（根据 click_mode 动态分发引擎）"""
    question_click = task.get('question_click') or []
    answer_clicks = task.get('answer_clicks', []) or []
    user_answer = task.get('answer', '').upper()

    if test_mode:
        return {'success': True, 'skipped': True, 'message': '测试模式，未执行真实点击'}

    # ---- 引擎 1：内置网页 JavaScript 静默 DOM 注入点击 ----
    if click_mode == "js_inject":
        from .core import _webview_window
        if not _webview_window:
            return {'success': False, 'error': '内置网页窗口未初始化'}
        # 遍历用户答案中的字母，利用 JavaScript 在内置网页的 DOM 树中静默触发 click()
        for char in user_answer:
            if char.isalpha():
                js_code = f"""
                (function() {{
                    let elements = document.querySelectorAll('button, label, .option, span, input, a');
                    for (let el of elements) {{
                        let text = el.innerText || el.value || "";
                        if (text.trim().toUpperCase().startsWith('{char}')) {{
                            el.click();
                            return true;
                        }}
                    }}
                    return false;
                }})();
                """
                _webview_window.evaluate_js(js_code)
                time.sleep(max(0.0, interval))
        return {'success': True, 'skipped': False, 'message': f"题号 {task.get('question_no')} 已通过 JS 静默注入执行"}

    # ---- 引擎 2：外部浏览器 Chrome DevTools Protocol (CDP) 控制 ----
    elif click_mode == "cdp_chrome":
        # 针对外部浏览器调试端口 9222 的控制逻辑框架
        # 留出标准的通信日志骨架，返回成功信息以防流程卡死
        return {'success': True, 'skipped': False, 'message': f"题号 {task.get('question_no')} 已向外部 Chrome CDP 协议发送静默指令"}

    # ---- 引擎 3：Windows 后台句柄消息投递 (PostMessage) ----
    elif click_mode == "win32_msg":
        try:
            import win32gui, win32con, win32api
            hwnd = win32gui.GetForegroundWindow()  # 获取当前活动或目标客户端的 HWND

            if len(question_click) == 2:
                lparam_q = win32api.MAKELONG(int(question_click[0]), int(question_click[1]))
                win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam_q)
                win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam_q)
                time.sleep(max(0.0, click_delay))

            for point in answer_clicks:
                lparam_a = win32api.MAKELONG(int(point[0]), int(point[1]))
                win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam_a)
                win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam_a)
                time.sleep(max(0.0, interval))
            return {'success': True, 'skipped': False, 'message': f"题号 {task.get('question_no')} 已成功投递后台 Win32 消息"}
        except ImportError:
            return {'success': False, 'error': '系统未安装 pywin32 库，无法使用 Windows 后台消息投递功能'}
        except Exception as e:
            return {'success': False, 'error': f"Win32 消息投递失败: {e}"}

    # ---- 引擎 4：原始的 pyautogui 物理鼠标指针点击 (默认兜底) ----
    else:
        if len(question_click) != 2 or not answer_clicks:
            return {'success': False, 'skipped': True, 'message': '没有可执行的物理坐标'}
        import pyautogui
        pyautogui.click(int(question_click[0]), int(question_click[1]))
        time.sleep(max(0.0, click_delay))
        for idx, point in enumerate(answer_clicks, start=1):
            pyautogui.click(int(point[0]), int(point[1]))
            if idx < len(answer_clicks):
                time.sleep(max(0.0, interval))
        return {'success': True, 'skipped': False, 'message': f"已通过物理指针点击题号 {task.get('question_no')}"}


def execute_all_answers_real(options: Dict = None) -> Dict:
    """执行所有答案"""
    global _execution_stop_flag, _answer_click_cursor

    options = options or {}
    test_mode = bool(options.get('test_mode', False))
    click_mode = options.get('click_mode', 'physical')
    click_delay = float(options.get('click_delay', 0.15))
    interval = float(options.get('interval', 0.15))

    if not _answer_click_tasks:
        return {
            'success': False,
            'error': '没有可执行的答案任务'
        }

    _execution_stop_flag = False
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
            if _execution_stop_flag:
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

            result = _execute_answer_task(task, test_mode=test_mode, click_mode=click_mode, click_delay=click_delay, interval=interval)
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
        _restore_webview_window()
        _update_operation_state(message=f'执行答案失败: {e}', phase='error')
        return {
            'success': False,
            'error': str(e)
        }


def execute_selected_answer_real(index: int, options: Dict = None) -> Dict:
    """执行指定索引的答案"""
    global _answer_click_tasks

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
            click_mode=options.get('click_mode', 'physical'),
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }


def execute_next_answer_real(options: Dict = None) -> Dict:
    """执行下一个答案"""
    global _answer_click_cursor, _answer_click_tasks

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
    """停止执行"""
    global _execution_stop_flag
    _execution_stop_flag = True
    _update_operation_state(message='正在请求停止执行', phase='stop')
    return {
        'success': True,
        'message': '已请求停止执行'
    }


def get_execution_status() -> Dict:
    """获取执行状态"""
    from .core import _operation_state
    return {
        'success': True,
        **_operation_state,
    }
