"""
Web 后端 - 采集模块
包含：题号检测、题目采集、选项解析
"""

import os
import threading
import time
import re
import unicodedata
from typing import Dict, List

from .core import (
    _collected_records,
    _collection_lock,
    _collection_running,
    _collection_stop_flag,
    _hide_webview_window,
    _restore_webview_window,
    _set_operation_state,
    _update_operation_state,
    _clear_operation_state,
    add_collected_record,
    get_question_region,
    get_number_region,
    get_number_region_image,
    get_detected_question_points,
    update_detected_question_points,
)

# 导入智能合并函数
from .ocr import _smart_merge_paragraphs, _process_ocr_text


def detect_question_points(backend_name: str = "auto") -> Dict:
    """检测题号坐标点"""
    number_region = get_number_region()

    if number_region is None:
        return {
            "success": False,
            "error": "未选择题号区域"
        }

    from core.ocr_engine import recognize_image_with_boxes

    # 使用之前保存的题号区域截图，不再重新截图
    image = get_number_region_image()
    if image is None:
        return {
            "success": False,
            "error": "没有题号区域截图，请先保存题号区域"
        }

    try:
        # 题号坐标识别不能用 prepare_image_for_ocr（它会缩放图片），
        # 因为 OCR 返回的是缩放后图片内的坐标，需要对应原始截图尺寸。
        # 直接用原图送 OCR，引擎内部会处理缩放。
        #
        # 双通道识别：原图 + 反色图合并结果
        # 原因：OCR 引擎训练数据是黑字白底，遇到蓝底白字（选中状态）会漏检
        raw_text, actual_backend, boxes = recognize_image_with_boxes(image, backend_name)

        # 第二遍：反色后再跑一次，抓取浅色文字（如蓝底白字的选中题号）
        from PIL import ImageOps
        inverted = ImageOps.invert(image.convert("RGB"))
        _, _, inv_boxes = recognize_image_with_boxes(inverted, backend_name)
        if inv_boxes:
            boxes = boxes + inv_boxes  # 合并，后续去重靠 no 字段

        if not boxes:
            update_detected_question_points([])
            return {
                "success": True,
                "message": "未识别到题号",
                "points": [],
                "count": 0
            }

        number_pattern = re.compile(r'^\d+$')
        points = []
        seen_nos = set()  # 去重：原图优先，反色图补漏
        total_boxes = len(boxes)

        # 区域偏移：OCR 坐标是相对于截图区域的，需要加上区域偏移才是屏幕绝对坐标
        offset_x = number_region.get("left", 0)
        offset_y = number_region.get("top", 0)

        for idx, box in enumerate(boxes, start=1):
            text = box.get("text", "").strip()
            if number_pattern.match(text):
                try:
                    no = int(text)
                    if no >= 1 and no not in seen_nos:
                        seen_nos.add(no)
                        # 兼容不同 OCR 后端返回的坐标字段
                        cx = box.get("center_x", box.get("x", 0) + box.get("width", 0) / 2)
                        cy = box.get("center_y", box.get("y", 0) + box.get("height", 0) / 2)
                        points.append({
                            "no": no,
                            "x": cx + offset_x,
                            "y": cy + offset_y,
                            "source": "ocr"
                        })
                except Exception:
                    pass
            _update_operation_state(current=idx, total=max(total_boxes, 1), message=f"题号识别进度 {idx}/{total_boxes}", phase="filter")

        # 按行排序
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

        # 推断缺失题号
        expected_count = _detect_expected_question_count_from_boxes(boxes)
        if expected_count and len(points) < expected_count:
            inferred_points = _infer_question_points(points, expected_count)
            if inferred_points:
                points = inferred_points

        update_detected_question_points(points)
        _update_operation_state(current=len(boxes), total=max(len(boxes), 1), message=f"题号识别完成，共 {len(points)} 个", phase="done")

        # 格式化显示
        display_points = []
        for p in points:
            display_points.append({
                "display_no": str(p["no"]),
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


def _detect_expected_question_count_from_boxes(boxes: list) -> int | None:
    """从 OCR 结果中检测期望的题目数量"""
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


def _infer_question_points(points: list, expected_count: int) -> list | None:
    """推断缺失的题号坐标"""
    if not points or expected_count <= len(points):
        return points

    sorted_points = sorted(points, key=lambda item: (item.get("y", 0), item.get("x", 0)))
    if len(sorted_points) < 2:
        return None

    # 按行分组
    row_groups: list = []
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
                    "no": point_idx + 1,
                    "x": int(round(start_x + col * avg_x_diff)),
                    "y": int(round(start_y + row * avg_y_diff)),
                    "source": "inferred",
                })
            point_idx += 1
            if point_idx >= expected_count:
                return inferred_points[:expected_count]

    return inferred_points[:expected_count] if inferred_points else None


def _run_collection_thread(options: Dict, result_queue):
    """后台采集线程"""
    global _collected_records, _collection_running, _collection_stop_flag

    question_region = get_question_region()
    detected_points = get_detected_question_points()

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
            question_region.get("left", 0),
            question_region.get("top", 0),
            question_region.get("width", 0),
            question_region.get("height", 0)
        )

        screenshot_dir = "question_captures"
        if save_images:
            os.makedirs(screenshot_dir, exist_ok=True)

        points = detected_points

        import pyautogui
        pyautogui.FAILSAFE = True

        total = len(points)
        _set_operation_state("start_collection", True, 0, total, "正在开始采集", "start")

        _hide_webview_window()
        time.sleep(0.2)

        # 去重：使用题号作为唯一键，遇到重复题号时覆盖旧记录
        seen_nos: Dict[int, int] = {}  # no -> index in _collected_records

        for idx, point in enumerate(points, start=1):
            if _collection_stop_flag:
                _update_operation_state(message=f"采集已停止于 {idx - 1}/{total}", phase="stopped")
                break

            no = point.get("no", idx)
            x = point.get("x", 0)
            y = point.get("y", 0)
            _update_operation_state(current=idx - 1, total=total, message=f"采集中 {idx}/{total}，点击题号 {no}", phase="click")

            # 检查是否重复题号
            if no in seen_nos:
                print(f"检测到重复题号 {no}，将覆盖之前的记录")
                # 移除旧记录
                old_index = seen_nos[no]
                if 0 <= old_index < len(_collected_records):
                    _collected_records.pop(old_index)
                    # 更新后续记录的索引
                    for existing_no, existing_idx in list(seen_nos.items()):
                        if existing_idx > old_index:
                            seen_nos[existing_no] = existing_idx - 1

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
                    from core.ocr_engine import recognize_image_with_boxes
                    region_width = image.width
                    raw_text, _, boxes = recognize_image_with_boxes(image, text_ocr_backend)
                    if boxes:
                        ocr_text = _smart_merge_paragraphs(boxes, region_width)
                    else:
                        ocr_text = _process_ocr_text(raw_text)
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
                        question_region.get("left", 0),
                        question_region.get("top", 0),
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
            seen_nos[no] = len(_collected_records) - 1  # 记录该题号在列表中的位置
            _update_operation_state(current=idx, total=total, message=f"采集进度 {idx}/{total}，题号 {no}", phase="done")

            time.sleep(interval)

        _collection_running = False
        _restore_webview_window()
        _clear_operation_state("start_collection")

        from .core import _serialize_collected_record
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
    """启动采集任务"""
    global _collected_records, _collection_running, _collection_stop_flag

    question_region = get_question_region()
    detected_points = get_detected_question_points()

    if question_region is None:
        return {
            "success": False,
            "error": "未设置题目区域"
        }

    if not detected_points:
        return {
            "success": False,
            "error": "未识别题号坐标"
        }

    _collection_running = True
    _collection_stop_flag = False
    with _collection_lock:
        _collected_records.clear()

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
        "total": len(detected_points)
    }


def get_collection_status() -> Dict:
    """获取采集状态"""
    global _collected_records, _collection_running

    from .core import _serialize_collected_record, _operation_state

    with _collection_lock:
        records_snapshot = list(_collected_records)
        current_count = len(records_snapshot)

    return {
        "success": True,
        "running": _collection_running,
        "current": current_count,
        "total": len(get_detected_question_points()),
        "phase": _operation_state.get("phase", ""),
        "message": _operation_state.get("message", ""),
        "records": [_serialize_collected_record(record) for record in records_snapshot],
        "latest_text": records_snapshot[-1].get("ocr_text", "") if records_snapshot else "",
        "latest_image_path": records_snapshot[-1].get("image_path", "") if records_snapshot else ""
    }


def stop_collection() -> Dict:
    """停止采集"""
    global _collection_stop_flag
    _collection_stop_flag = True
    return {
        "success": True,
        "message": "采集已停止"
    }


def parse_collected_options(options: Dict = None) -> Dict:
    """解析已采集的选项"""
    global _collected_records

    question_region = get_question_region()

    with _collection_lock:
        records_snapshot = list(_collected_records)

    if not records_snapshot:
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
        total = len(records_snapshot)
        _set_operation_state("parse_collected_options", True, 0, total, "正在解析已采集内容", "start")

        for record in records_snapshot:
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

            # 状态更新：正在进行正文文字识别
            _update_operation_state(
                current=record.get("index", 0),
                total=total,
                message=f"正在对第 {record.get('index', '?')} 题进行正文文字识别...",
                phase="text_ocr",
            )

            try:
                option_img = record.get("capture_image")
                if option_img is None:
                    from PIL import Image as PILImage
                    with PILImage.open(image_path) as file_image:
                        option_img = file_image.copy()
                else:
                    option_img = option_img.copy()

                try:
                    from core.ocr_engine import recognize_image_with_boxes
                    region_width = option_img.width
                    raw_text, _, boxes = recognize_image_with_boxes(option_img, text_ocr_backend)
                    if boxes:
                        ocr_text = _smart_merge_paragraphs(boxes, region_width)
                    else:
                        ocr_text = _process_ocr_text(raw_text)
                    record["ocr_text"] = ocr_text
                except Exception as e:
                    print(f"Text OCR failed: {e}")
                    record["ocr_text"] = ""

                # 状态更新：正在进行选项坐标解析
                _update_operation_state(
                    current=record.get("index", 0),
                    total=total,
                    message=f"正在解析第 {record.get('index', '?')} 题的选项坐标...",
                    phase="option",
                )

                options_result = extract_options_from_question_image(
                    option_img,
                    question_region.get("left", 0),
                    question_region.get("top", 0),
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

        from .core import _serialize_collected_record
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
