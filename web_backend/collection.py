"""
Web 后端 - 采集模块
包含：题号检测、题目采集、选项解析
"""

import os
import threading
import time
import re
import math
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
        # 【优化1】：主动放大图像 2 倍。这对细小笔画（如 1、4、7）的识别率有质的提升
        scale_factor = 2.0
        from PIL import Image, ImageOps
        work_image = image.resize(
            (int(image.width * scale_factor), int(image.height * scale_factor)),
            Image.Resampling.LANCZOS
        )

        # 双通道识别：放大后的原图 + 放大后的反色图
        raw_text, actual_backend, boxes = recognize_image_with_boxes(work_image, backend_name)

        inverted = ImageOps.invert(work_image.convert("RGB"))
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

        points = []
        total_boxes = len(boxes)

        # 区域偏移：OCR 坐标是相对于截图区域的，需要加上区域偏移才是屏幕绝对坐标
        offset_x = number_region.get("left", 0)
        offset_y = number_region.get("top", 0)

        for idx, box in enumerate(boxes, start=1):
            text = box.get("text", "").strip()

            # 【优化2】：容错与清洗逻辑
            # 去除可能误识别的标点符号后缀，比如 "1." "7、" "4)"
            text = re.sub(r'[.、)）\]】]+$', '', text)
            # 常见形近字强制纠偏
            text = text.replace('l', '1').replace('I', '1').replace('|', '1')
            text = text.replace('O', '0').replace('o', '0')
            text = text.replace('Z', '2').replace('z', '2')
            text = text.replace('q', '9')

            # 放宽正则要求，只要清洗后是纯数字即可
            if re.match(r'^\d+$', text):
                try:
                    no = int(text)
                    if no >= 1:
                        # 【优化3】：将放大图的坐标按比例还原回原图坐标
                        box_x = box.get("x", 0) / scale_factor
                        box_y = box.get("y", 0) / scale_factor
                        box_w = box.get("width", 0) / scale_factor
                        box_h = box.get("height", 0) / scale_factor

                        # 获取中心点坐标，并加上窗口区域的 offset
                        cx = box.get("center_x")
                        if cx is not None:
                            cx = cx / scale_factor
                        else:
                            cx = box_x + box_w / 2

                        cy = box.get("center_y")
                        if cy is not None:
                            cy = cy / scale_factor
                        else:
                            cy = box_y + box_h / 2

                        screen_cx = cx + offset_x
                        screen_cy = cy + offset_y

                        # 【核心改进1：基于空间坐标去重，而非基于数字去重】
                        # 遍历已有点，如果距离 < 15px 则视为双通道重复点（原图+反色图识别同一位置）
                        is_duplicate = False
                        for existing_point in points:
                            dist = math.hypot(screen_cx - existing_point["x"], screen_cy - existing_point["y"])
                            if dist < 15:  # 15像素阈值
                                is_duplicate = True
                                break

                        if not is_duplicate:
                            points.append({
                                "no": no,
                                "x": screen_cx,
                                "y": screen_cy,
                                "source": "ocr"
                            })
                except Exception:
                    pass
            _update_operation_state(current=idx, total=max(total_boxes, 1), message=f"题号识别进度 {idx}/{total_boxes}", phase="filter")

        # 按行排序（保持原有空间排序逻辑）
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

        # 推断缺失题号（已移至独立API trigger_infer_missing_points，用户手动触发）
        # expected_count = _detect_expected_question_count_from_boxes(boxes)
        # inferred_points = _infer_question_points(points, expected_count)
        # if inferred_points:
        #     points = inferred_points

        # 【核心改进2：题号前缀智能推断（处理不同题型题号重置问题）】
        section_idx = 1
        last_no = 0
        global_id = 0

        for point in points:
            global_id += 1
            no = point["no"]

            # 如果当前题号 <= 上一个题号，说明进入了新题型区域（如判断题从1重新开始）
            if no <= last_no and last_no > 0:
                section_idx += 1

            # 动态生成 display_no
            if section_idx == 1:
                point["display_no"] = str(no)
            else:
                point["display_no"] = f"第{section_idx}部分-{no}"

            # 添加全局唯一ID
            point["global_id"] = global_id

            last_no = no

        update_detected_question_points(points)
        _update_operation_state(current=len(boxes), total=max(len(boxes), 1), message=f"题号识别完成，共 {len(points)} 个（{section_idx}个部分）", phase="done")

        # 格式化显示（保留所有新字段供前端使用）
        display_points = []
        for p in points:
            display_points.append({
                "display_no": p.get("display_no", str(p["no"])),
                "global_id": p.get("global_id", 0),
                "no": p["no"],
                "x": p["x"],
                "y": p["y"],
                "source": p["source"]
            })

        return {
            "success": True,
            "message": f"题号坐标识别完成 ({len(points)}个, {section_idx}个部分)",
            "points": display_points,
            "count": len(points),
            "sections": section_idx
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


def _infer_question_points(points: list, expected_count: int = None) -> list | None:
    """基于网格数学模型的智能分段坐标推断（包含防暴走与空间越界保护）"""
    if not points:
        return points

    # 1. 确保点按空间位置（从上到下，从左到右）排序
    sorted_points = sorted(points, key=lambda item: (item.get("y", 0), item.get("x", 0)))
    if len(sorted_points) < 2:
        return sorted_points

    # --- 【新增核心】：计算截图的物理空间边界 ---
    min_y = min(p.get("y", 0) for p in sorted_points)
    max_y = max(p.get("y", 0) for p in sorted_points)
    min_x = min(p.get("x", 0) for p in sorted_points)
    max_x = max(p.get("x", 0) for p in sorted_points)

    # 2. 计算全局网格几何参数
    row_groups = []
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

    columns = max(len(row) for row in row_groups)
    if columns < 1:
        columns = 1

    x_diffs = []
    for row in row_groups:
        if len(row) >= 2:
            row_x = sorted(p.get("x", 0) for p in row)
            x_diffs.extend([row_x[i+1] - row_x[i] for i in range(len(row_x)-1)])
    avg_x_diff = sum(x_diffs) / len(x_diffs) if x_diffs else 100  # 兜底间距

    y_diffs = []
    if len(row_groups) >= 2:
        row_ys = [sum(p.get("y", 0) for p in row) / len(row) for row in row_groups]
        y_diffs = [row_ys[i+1] - row_ys[i] for i in range(len(row_ys)-1)]
    avg_y_diff = sum(y_diffs) / len(y_diffs) if y_diffs else 50   # 兜底间距

    if avg_x_diff == 0 and avg_y_diff == 0:
        return sorted_points

    # --- 【新增核心】：设置严格的空间安全视口（允许外扩半个到一个题的间距） ---
    safe_top = min_y - avg_y_diff * 0.8
    safe_bottom = max_y + avg_y_diff * 1.5
    safe_left = min_x - avg_x_diff * 1.5
    safe_right = max_x + avg_x_diff * 1.5

    # 3. 智能分段与严格的序列清洗（彻底解决满屏噪点）
    sections = []
    current_section = [sorted_points[0]]
    last_valid_no = sorted_points[0].get("no", 0)

    # 动态允许的最大跨度（列数越多，允许跳过的题号越多）
    max_allowed_jump = max(5, columns * 2 + 3)

    for p in sorted_points[1:]:
        curr_no = p.get("no", 0)

        if curr_no > last_valid_no:
            # 正常递增，但要拦截离谱的跳跃（如 2 后面跟着 288）
            if curr_no - last_valid_no <= max_allowed_jump:
                current_section.append(p)
                last_valid_no = curr_no
            else:
                continue # 暴增直接抛弃
        else:
            # 题号变小：极其严格的新段落判定
            # 只有当新题号 <= 5 时，才认定这是卷子真正的“第二部分”
            if curr_no <= 5:
                sections.append(current_section)
                current_section = [p]
                last_valid_no = curr_no
            else:
                continue # 随意掉落的乱码数字，直接抛弃

    if current_section:
        sections.append(current_section)

    # 过滤掉孤立且离谱的噪点段落
    valid_sections = []
    for sec in sections:
        if len(sec) == 1 and sec[0].get("no", 0) > 10:
            continue
        valid_sections.append(sec)
    sections = valid_sections

    # 4. 独立推断填补，并施加【空间越界防护】
    final_points = []
    for sec_idx, sec_points in enumerate(sections):
        base_point = sec_points[0]
        base_no = base_point.get("no", 1)
        base_x = base_point.get("x", 0)
        base_y = base_point.get("y", 0)

        base_row = (base_no - 1) // columns
        base_col = (base_no - 1) % columns

        max_no_in_sec = sec_points[-1].get("no", 1)
        if sec_idx == len(sections) - 1 and expected_count and expected_count > max_no_in_sec:
            if expected_count - max_no_in_sec <= max_allowed_jump:
                max_no_in_sec = expected_count

        existing_nos = {p.get("no"): p for p in sec_points}

        # 尝试推算，但用物理坐标进行无情拦截
        for target_no in range(1, max_no_in_sec + 1):
            if target_no in existing_nos:
                final_points.append(existing_nos[target_no])
            else:
                target_row = (target_no - 1) // columns
                target_col = (target_no - 1) % columns

                calc_x = int(round(base_x + (target_col - base_col) * avg_x_diff))
                calc_y = int(round(base_y + (target_row - base_row) * avg_y_diff))

                # 【终极防守】：算出来的点如果不在这张图的物理范围内，立刻扔掉！
                if calc_y < safe_top or calc_y > safe_bottom or calc_x < safe_left or calc_x > safe_right:
                    continue

                final_points.append({
                    "no": target_no,
                    "x": calc_x,
                    "y": calc_y,
                    "source": "inferred_math"
                })

    return final_points


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

        # 【核心改进3：严格按照空间顺序（global_id）采集，不进行任何基于题号的覆盖】
        for idx, point in enumerate(points, start=1):
            if _collection_stop_flag:
                _update_operation_state(message=f"采集已停止于 {idx - 1}/{total}", phase="stopped")
                break

            no = point.get("no", idx)
            x = point.get("x", 0)
            y = point.get("y", 0)
            display_no = point.get("display_no", str(no))
            global_id = point.get("global_id", idx)

            _update_operation_state(current=idx - 1, total=total, message=f"采集中 {idx}/{total}，点击题号 {display_no}", phase="click")

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
                "global_id": global_id,
                "no": no,
                "display_no": display_no,
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
            _update_operation_state(current=idx, total=total, message=f"采集进度 {idx}/{total}，题号 {display_no}", phase="done")

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


def get_mouse_position() -> Dict:
    """获取当前鼠标的绝对屏幕坐标"""
    try:
        import pyautogui
        x, y = pyautogui.position()
        return {
            "success": True,
            "x": int(x),
            "y": int(y),
            "message": f"鼠标位置: ({int(x)}, {int(y)})"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"获取鼠标位置失败: {e}"
        }


# ==================== 非阻塞全局快捷键监听 ====================

_captured_hotkey_coords = None  # 全局变量：存储快捷键触发的坐标


def start_hotkey_listener() -> Dict:
    """
    启动非阻塞的全局快捷键监听（Home键）
    使用 keyboard.add_hotkey（非阻塞），不会卡死界面
    """
    global _captured_hotkey_coords

    try:
        import keyboard
        import pyautogui

        # 清除历史钩子
        keyboard.unhook_all()

        # 重置坐标变量
        _captured_hotkey_coords = None

        def on_hotkey():
            """快捷键触发时的回调函数（在后台线程执行）"""
            global _captured_hotkey_coords
            try:
                x, y = pyautogui.position()
                _captured_hotkey_coords = (int(x), int(y))
                print(f"[快捷键] 已捕获坐标: ({int(x)}, {int(y)})")
                # 立刻注销监听，防止重复触发
                keyboard.unhook_all()
            except Exception as e:
                print(f"[快捷键] 获取坐标失败: {e}")

        # 使用非阻塞方法绑定快捷键（立即返回）
        keyboard.add_hotkey('home', on_hotkey)

        return {
            "success": True,
            "message": "快捷键监听已启动，请按 Home 键"
        }
    except ImportError:
        return {
            "success": False,
            "error": "缺少 keyboard 库，请运行: pip install keyboard"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"启动监听失败: {e}"
        }


def check_hotkey_result() -> Dict:
    """
    检查快捷键是否已被触发（供前端轮询）
    """
    global _captured_hotkey_coords

    if _captured_hotkey_coords is not None:
        # 有坐标数据，取出并重置
        x, y = _captured_hotkey_coords
        _captured_hotkey_coords = None
        return {
            "success": True,
            "x": x,
            "y": y,
            "message": f"已捕获坐标: ({x}, {y})"
        }

    # 还没有触发
    return {
        "success": False,
        "waiting": True,
        "message": "仍在等待按键..."
    }


def cancel_hotkey_listener() -> Dict:
    """取消快捷键监听（前端取消或关闭对话框时调用）"""
    global _captured_hotkey_coords

    try:
        import keyboard

        # 注销所有钩子
        keyboard.unhook_all()

        # 重置坐标
        _captured_hotkey_coords = None

        return {
            "success": True,
            "message": "快捷键监听已取消"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"取消监听失败: {e}"
        }


def add_or_update_question_point(point_data: Dict) -> Dict:
    """手动添加或更新题号坐标点"""
    try:
        no = int(point_data.get("no", 0))
        x = float(point_data.get("x", 0))
        y = float(point_data.get("y", 0))

        if no < 1:
            return {
                "success": False,
                "error": "题号必须大于等于 1"
            }

        # 获取当前列表
        current_points = get_detected_question_points()

        # 查找是否已存在该题号（基于坐标匹配，而非数字）
        found = False
        for i, point in enumerate(current_points):
            dist = math.hypot(x - point["x"], y - point["y"])
            if dist < 15:  # 同一位置的点视为更新
                # 更新现有记录
                point["no"] = no
                point["x"] = x
                point["y"] = y
                point["source"] = "manual"
                found = True
                break

        if not found:
            # 添加新记录（初始不设置 display_no 和 global_id，后续统一计算）
            current_points.append({
                "no": no,
                "x": x,
                "y": y,
                "source": "manual"
            })

        # 重新空间排序并计算 display_no / global_id
        current_points = _recalculate_point_metadata(current_points)

        # 更新全局变量
        update_detected_question_points(current_points)

        # 格式化返回（包含所有新字段）
        display_points = []
        for p in current_points:
            display_points.append({
                "display_no": p.get("display_no", str(p["no"])),
                "global_id": p.get("global_id", 0),
                "no": p["no"],
                "x": p["x"],
                "y": p["y"],
                "source": p["source"]
            })

        action = "更新" if found else "添加"
        return {
            "success": True,
            "message": f"已{action}题号 {no} 的坐标 ({int(x)}, {int(y)})",
            "points": display_points,
            "count": len(display_points)
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": f"操作失败: {e}"
        }


def delete_question_point(no: int) -> Dict:
    """删除指定题号的坐标点"""
    try:
        no = int(no)

        # 获取当前列表
        current_points = get_detected_question_points()

        # 查找并删除（基于 global_id 或 no 匹配）
        original_count = len(current_points)
        current_points = [p for p in current_points if p.get("no") != no]

        if len(current_points) == original_count:
            return {
                "success": False,
                "error": f"未找到题号 {no}",
                "points": [],
                "count": len(current_points)
            }

        # 重新计算 display_no 和 global_id
        current_points = _recalculate_point_metadata(current_points)

        # 更新全局变量
        update_detected_question_points(current_points)

        # 格式化返回（包含所有新字段）
        display_points = []
        for p in current_points:
            display_points.append({
                "display_no": p.get("display_no", str(p["no"])),
                "global_id": p.get("global_id", 0),
                "no": p["no"],
                "x": p["x"],
                "y": p["y"],
                "source": p["source"]
            })

        return {
            "success": True,
            "message": f"已删除题号 {no}",
            "points": display_points,
            "count": len(display_points)
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": f"删除失败: {e}"
        }


def _recalculate_point_metadata(points: List[Dict]) -> List[Dict]:
    """
    重新计算题号点的元数据（空间排序 + display_no + global_id）
    用于手动编辑后重新整理数据结构
    """
    if not points:
        return points

    # 1. 空间排序：先按 Y 分行，行内按 X 排序
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

    sorted_points = []
    for row in rows:
        sorted_points.extend(row)

    # 2. 计算 section_idx、display_no 和 global_id
    section_idx = 1
    last_no = 0
    global_id = 0

    for point in sorted_points:
        global_id += 1
        no = point["no"]

        # 如果当前题号 <= 上一个题号，说明进入了新题型区域
        if no <= last_no and last_no > 0:
            section_idx += 1

        # 动态生成 display_no
        if section_idx == 1:
            point["display_no"] = str(no)
        else:
            point["display_no"] = f"第{section_idx}部分-{no}"

        # 添加全局唯一ID
        point["global_id"] = global_id

        last_no = no

    return sorted_points


def trigger_infer_missing_points() -> Dict:
    """
    触发智能网格推断（独立API，用户手动触发）
    
    功能：
    - 读取当前已识别的题号点
    - 进行严格二维容差排序
    - 智能分段检测（题号重置时自动切分）
    - 对每段执行网格推断补齐缺失题号
    - 保存结果并返回
    
    Returns:
        Dict: {
            "success": bool,
            "message": str,
            "inferred_count": int,  # 新增推断的点数
            "total_count": int,     # 总点数
            "points": list          # 更新后的点列表
        }
    """
    try:
        # 1. 获取当前已识别的点
        current_points = get_detected_question_points()
        if not current_points:
            return {
                "success": False,
                "error": "没有已识别的题号点，请先进行OCR识别",
                "inferred_count": 0,
                "total_count": 0,
                "points": []
            }

        print(f"[网格推断] 开始处理 {len(current_points)} 个已识别点...")

        # 2. 严格二维容差排序（Y轴30px分行，行内X排序）
        sorted_points = sorted(current_points, key=lambda item: (item.get("y", 0), item.get("x", 0)))

        row_groups = []
        current_row = [sorted_points[0]]
        last_y = sorted_points[0].get("y", 0)

        for point in sorted_points[1:]:
            if abs(point.get("y", 0) - last_y) <= 30:  # Y轴容差30px
                current_row.append(point)
            else:
                # 行内按X坐标排序
                current_row.sort(key=lambda p: p.get("x", 0))
                row_groups.append(current_row)
                current_row = [point]
            last_y = point.get("y", 0)

        if current_row:
            current_row.sort(key=lambda p: p.get("x", 0))
            row_groups.append(current_row)

        print(f"[网格推断] 排序完成：{len(row_groups)} 行")

        # 3. 计算全局网格参数
        columns = max(len(row) for row in row_groups) if row_groups else 1
        if columns < 1:
            columns = 1

        x_diffs = []
        for row in row_groups:
            if len(row) >= 2:
                row_x = [p.get("x", 0) for p in row]
                x_diffs.extend([row_x[i+1] - row_x[i] for i in range(len(row_x)-1)])
        avg_x_diff = sum(x_diffs) / len(x_diffs) if x_diffs else 0

        y_diffs = []
        if len(row_groups) >= 2:
            row_ys = [sum(p.get("y", 0) for p in row) / len(row) for row in row_groups]
            y_diffs = [row_ys[i+1] - row_ys[i] for i in range(len(row_ys)-1)]
        avg_y_diff = sum(y_diffs) / len(y_diffs) if y_diffs else 0

        print(f"[网格推断] 网格参数: columns={columns}, avg_x={avg_x_diff:.1f}, avg_y={avg_y_diff:.1f}")

        if avg_x_diff == 0 and avg_y_diff == 0:
            return {
                "success": False,
                "error": "无法计算网格间距，点数不足或分布异常",
                "inferred_count": 0,
                "total_count": len(current_points),
                "points": current_points
            }

        # 4. 智能分段检测（题号重置时切分）
        sections = []
        current_section = [sorted_points[0]]
        last_no = sorted_points[0].get("no", 0)

        for p in sorted_points[1:]:
            current_no = p.get("no", 0)
            if current_no <= last_no:
                # 题号不升反降 → 重置了，开辟新段落
                sections.append(current_section)
                current_section = [p]
                print(f"[网格推断] 检测到分段: 题号从 {last_no} 重置为 {current_no}")
            else:
                current_section.append(p)
            last_no = current_no

        if current_section:
            sections.append(current_section)

        print(f"[网格推断] 共分为 {len(sections)} 个段落")

        # 5. 对每个段独立推断
        final_points = []
        total_inferred = 0

        for sec_idx, sec_points in enumerate(sections):
            print(f"[网格推断] 处理第 {sec_idx + 1} 段: {len(sec_points)} 个点")

            # 以该段第一个点作为相对基准
            base_point = sec_points[0]
            base_no = base_point.get("no", 1)
            base_x = base_point.get("x", 0)
            base_y = base_point.get("y", 0)

            base_row = (base_no - 1) // columns
            base_col = (base_no - 1) % columns

            # 确定该段的推断范围
            max_no_in_sec = sec_points[-1].get("no", 1)

            # 提取已有的题号
            existing_nos = {p.get("no"): p for p in sec_points}

            # 逐号遍历填补缺失
            for target_no in range(1, max_no_in_sec + 1):
                if target_no in existing_nos:
                    final_points.append(existing_nos[target_no])
                else:
                    target_row = (target_no - 1) // columns
                    target_col = (target_no - 1) % columns

                    calc_x = int(round(base_x + (target_col - base_col) * avg_x_diff))
                    calc_y = int(round(base_y + (target_row - base_row) * avg_y_diff))

                    inferred_point = {
                        "no": target_no,
                        "x": calc_x,
                        "y": calc_y,
                        "source": "inferred_math"
                    }
                    final_points.append(inferred_point)
                    total_inferred += 1

            print(f"[网格推断] 第 {sec_idx + 1} 段完成: 补齐 {max_no_in_sec - len(sec_points)} 个缺失点")

        # 6. 重新计算元数据（display_no, global_id等）
        final_points_with_meta = _recalculate_point_metadata(final_points)

        # 7. 保存结果
        update_detected_question_points(final_points_with_meta)

        original_count = len(current_points)
        new_count = len(final_points_with_meta)

        print(f"[网格推断] ✅ 完成！原始: {original_count} 个 → 最终: {new_count} 个 (新增推断: {total_inferred} 个)")

        return {
            "success": True,
            "message": f"网格推断完成！原始 {original_count} 个点 → 最终 {new_count} 个点（新增推断 {total_inferred} 个）",
            "inferred_count": total_inferred,
            "original_count": original_count,
            "total_count": new_count,
            "sections": len(sections),
            "points": [
                {
                    "display_no": p.get("display_no", str(p.get("no", ""))),
                    "global_id": p.get("global_id", 0),
                    "no": p.get("no", 0),
                    "x": p.get("x", 0),
                    "y": p.get("y", 0),
                    "source": p.get("source", "unknown")
                }
                for p in final_points_with_meta
            ]
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": f"网格推断失败: {e}",
            "inferred_count": 0,
            "total_count": 0,
            "points": []
        }
