import re
import time
import unicodedata
from typing import Optional

from PIL import Image

from core.box_ocr_backend import locate_text_boxes_for_options


QUESTION_NUMBER_PATTERN = re.compile(r"(第\s*\d+\s*题|\b\d+\s*[.)、])", re.IGNORECASE)
ROW_LABEL_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?:\(|（)?\s*(正确|错误|对|错|TRUE|FALSE|T|F|√|×|✓|✗|✔|✘|[A-Z])\s*(?:\)|）|[.、:：])?",
    re.IGNORECASE,
)

LETTER_INDEX = {"A": 0, "B": 1, "C": 2, "D": 3}
BOOLEAN_TRUE_LABELS = {"TRUE", "T", "正确", "对"}
BOOLEAN_FALSE_LABELS = {"FALSE", "F", "错误", "错"}

# 噪声文本模式，在匹配前清洗
NOISE_PATTERNS = [
    "拼命加载中...", "拼命加载中..", "拼命加载中.",
    "加载中...", "加载中..",
    "loading...",
]


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").strip()
    for pattern in NOISE_PATTERNS:
        text = text.replace(pattern, "")
    return text.strip()


def _normalize_option_label(label: str) -> str:
    normalized = _normalize_text(label).upper()
    if normalized in {"TRUE", "T", "正确", "对", "√", "✓", "✔"}:
        return "T" if normalized in {"TRUE", "T"} else "正确"
    if normalized in {"FALSE", "F", "错误", "错", "×", "✗", "✘"}:
        return "F" if normalized in {"FALSE", "F"} else "错误"
    return normalized


def _build_option_info(
    label: str,
    text: str,
    local_x: float,
    local_y: float,
    width: float,
    height: float,
    region_left: int,
    region_top: int,
    image_width: int,
    score: float,
    backend: str,
) -> dict:
    return {
        "label": label,
        "text": _normalize_text(text),
        "local_x": int(round(local_x)),
        "local_y": int(round(local_y)),
        "width": int(round(width)),
        "height": int(round(height)),
        "screen_x": int(round(region_left + local_x)),
        "screen_y": int(round(region_top + local_y)),
        "click_x": int(round(region_left + local_x)),
        "click_y": int(round(region_top + local_y)),
        "score": float(score),
        "backend": backend,
    }


def _group_boxes_by_row(boxes: list[dict], y_threshold: Optional[int] = None) -> list[list[dict]]:
    if not boxes:
        return []

    if y_threshold is None:
        heights = [box["height"] for box in boxes if box.get("height", 0) > 0]
        if heights:
            import statistics

            median_height = statistics.median(heights)
            y_threshold = max(22, int(median_height * 1.2))
        else:
            y_threshold = 32

    boxes_sorted = sorted(boxes, key=lambda b: b["local_y"])
    rows: list[list[dict]] = []
    current_row: list[dict] = [boxes_sorted[0]]

    for current_box in boxes_sorted[1:]:
        last_box = current_row[-1]
        if abs(current_box["local_y"] - last_box["local_y"]) < y_threshold:
            current_row.append(current_box)
        else:
            rows.append(current_row)
            current_row = [current_box]

    rows.append(current_row)
    return rows


def _extract_labeled_segments(
    row_text: str,
) -> list[tuple[str, str]]:
    matches = list(ROW_LABEL_PATTERN.finditer(row_text))
    labels: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        label = _normalize_option_label(match.group(1))
        if not label:
            continue
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(row_text)
        option_text = row_text[start:end].strip()
        labels.append((label, option_text))
    return labels


def _extract_label_box_candidates(row_boxes: list[dict]) -> list[tuple[str, dict]]:
    candidates: list[tuple[str, dict]] = []
    strict_pattern = re.compile(
        r"^\s*(?:\(|（)?\s*(正确|错误|对|错|TRUE|FALSE|T|F|√|×|✓|✗|✔|✘|[A-Z])\s*(?:\)|）|[.、:：])?\s*$",
        re.IGNORECASE,
    )
    for box in sorted(row_boxes, key=lambda b: b["local_x"]):
        text = _normalize_text(box.get("text", ""))
        match = strict_pattern.fullmatch(text)
        if not match:
            continue
        label = _normalize_option_label(match.group(1))
        if label:
            candidates.append((label, box))
    return candidates


def _extract_options_from_row(
    row_boxes: list[dict],
    region_left: int,
    region_top: int,
    image_width: int,
) -> dict[str, dict]:
    row_boxes_sorted = sorted(row_boxes, key=lambda b: b["local_x"])
    row_text = " ".join(box["text"] for box in row_boxes_sorted)
    print(f"    尝试匹配行文本: {row_text!r}")

    segments = _extract_labeled_segments(row_text)
    if not segments:
        print("    未匹配到任何选项标记")
        return {}

    avg_y = sum(box["local_y"] for box in row_boxes_sorted) / len(row_boxes_sorted)
    max_height = max(box["height"] for box in row_boxes_sorted)
    avg_score = sum(box.get("score", 1.0) for box in row_boxes_sorted) / len(row_boxes_sorted)
    backend = row_boxes_sorted[0]["backend"]
    options: dict[str, dict] = {}
    label_box_candidates = _extract_label_box_candidates(row_boxes_sorted)
    used_candidate_indexes: set[int] = set()

    for index, (label, option_text) in enumerate(segments):
        matched_box = None
        for candidate_index, (candidate_label, candidate_box) in enumerate(label_box_candidates):
            if candidate_index in used_candidate_indexes:
                continue
            if candidate_label == label:
                matched_box = candidate_box
                used_candidate_indexes.add(candidate_index)
                break

        if matched_box is not None:
            local_x = matched_box["local_x"]
            local_y = matched_box["local_y"]
            width = matched_box["width"]
            height = matched_box["height"]
            score = matched_box.get("score", avg_score)
        else:
            local_x = (index + 0.5) / len(segments) * image_width
            local_y = avg_y
            width = 100
            height = max_height
            score = avg_score

        options[label] = _build_option_info(
            label=label,
            text=option_text,
            local_x=local_x,
            local_y=local_y,
            width=width,
            height=height,
            region_left=region_left,
            region_top=region_top,
            image_width=image_width,
            score=score,
            backend=backend,
        )
    return options


def _infer_options_by_rows(
    rows: list[list[dict]],
    image_width: int,
    image_height: int,
    region_left: int,
    region_top: int,
) -> dict[str, dict]:
    if not rows:
        return {}

    print("  启用行位置 fallback 策略")
    candidate_rows = []
    min_y_threshold = image_height * 0.35

    for row_boxes in rows:
        row_boxes_sorted = sorted(row_boxes, key=lambda b: b["local_x"])
        row_text = " ".join(box["text"] for box in row_boxes_sorted)
        if not row_text.strip():
            continue

        avg_y = sum(box["local_y"] for box in row_boxes_sorted) / len(row_boxes_sorted)
        if avg_y < min_y_threshold:
            continue
        if QUESTION_NUMBER_PATTERN.search(row_text):
            continue
        if len(row_text) > 80:
            continue

        min_x = min(box["local_x"] - box["width"] / 2 for box in row_boxes_sorted)
        max_x = max(box["local_x"] + box["width"] / 2 for box in row_boxes_sorted)
        candidate_rows.append(
            {
                "text": row_text,
                "avg_y": avg_y,
                "center_x": (min_x + max_x) / 2,
                "width": max_x - min_x,
                "height": max(box["height"] for box in row_boxes_sorted),
                "score": sum(box.get("score", 1.0) for box in row_boxes_sorted) / len(row_boxes_sorted),
                "backend": row_boxes_sorted[0]["backend"],
            }
        )

    candidate_rows.sort(key=lambda item: item["avg_y"])
    selected_rows = candidate_rows[-4:] if len(candidate_rows) >= 4 else candidate_rows

    options: dict[str, dict] = {}
    for index, row_data in enumerate(selected_rows):
        if index >= 4:
            break
        label = ["A", "B", "C", "D"][index]
        options[label] = _build_option_info(
            label=label,
            text=row_data["text"],
            local_x=row_data["center_x"],
            local_y=row_data["avg_y"],
            width=row_data["width"],
            height=row_data["height"],
            region_left=region_left,
            region_top=region_top,
            image_width=image_width,
            score=row_data["score"],
            backend=row_data["backend"] + "-row-fallback",
        )
    return options


def infer_options_from_any_two(
    options: dict[str, dict],
    region_left: int,
    region_top: int,
    image_width: int,
) -> dict[str, dict]:
    if not {"A", "B", "C", "D"}.intersection(options):
        return options

    existing_letters = [label for label in ("A", "B", "C", "D") if label in options]
    if len(existing_letters) < 2 or len(existing_letters) >= 4:
        return options

    l1, l2 = existing_letters[0], existing_letters[1]
    opt1, opt2 = options[l1], options[l2]
    x1, y1 = opt1["screen_x"], opt1["screen_y"]
    x2, y2 = opt2["screen_x"], opt2["screen_y"]

    idx1 = LETTER_INDEX[l1]
    idx2 = LETTER_INDEX[l2]
    index_gap = idx2 - idx1
    if index_gap == 0:
        return options

    gap_x = (x2 - x1) / index_gap
    gap_y = (y2 - y1) / index_gap
    is_vertical = abs(gap_y) > abs(gap_x) * 1.5
    is_horizontal = abs(gap_x) > abs(gap_y) * 1.5

    inferred = dict(options)
    for letter in ("A", "B", "C", "D"):
        if letter in inferred:
            continue
        target_idx = LETTER_INDEX[letter]
        if is_vertical:
            inferred_x = int(round(sum(opt["screen_x"] for opt in options.values()) / len(options)))
            inferred_y = int(round(y1 + (target_idx - idx1) * gap_y))
        elif is_horizontal:
            inferred_x = int(round(x1 + (target_idx - idx1) * gap_x))
            inferred_y = int(round(sum(opt["screen_y"] for opt in options.values()) / len(options)))
        else:
            inferred_x = int(round(x1 + (target_idx - idx1) * gap_x))
            inferred_y = int(round(y1 + (target_idx - idx1) * gap_y))

        inferred[letter] = {
            "label": letter,
            "text": "(推断)",
            "local_x": inferred_x - region_left,
            "local_y": inferred_y - region_top,
            "width": 100,
            "height": opt1.get("height", 30),
            "screen_x": inferred_x,
            "screen_y": inferred_y,
            "click_x": inferred_x,
            "click_y": inferred_y,
            "score": 0.5,
            "backend": "inferred-linear",
        }
    return inferred


def extract_options_from_question_image(
    image: Image.Image,
    region_left: int,
    region_top: int,
    backend_name: str = "auto",
) -> dict:
    t0 = time.perf_counter()
    boxes = locate_text_boxes_for_options(
        image,
        region_left,
        region_top,
        backend_name=backend_name,
    )
    t1 = time.perf_counter()
    print(f"选项解析耗时: {t1 - t0:.3f}s")

    if not boxes:
        print("警告: 未识别到任何选项坐标")
        return {}

    rows = _group_boxes_by_row(boxes)
    print(f"按 y 坐标分行，共 {len(rows)} 行")

    options: dict[str, dict] = {}
    unmatched_rows: list[tuple[int, list[dict]]] = []  # (row_index, row_boxes) 未匹配到选项标记的行
    for row_index, row_boxes in enumerate(rows):
        row_text = " ".join(box["text"] for box in sorted(row_boxes, key=lambda b: b["local_x"]))
        print(f"  第 {row_index + 1} 行: {row_text!r}")
        row_options = _extract_options_from_row(
            row_boxes,
            region_left,
            region_top,
            image.width,
        )
        if row_options:
            for label, option_info in row_options.items():
                if (
                    label not in options
                    or option_info.get("screen_y", 0) >= options[label].get("screen_y", 0)
                ):
                    options[label] = option_info
        else:
            # 该行没有匹配到 A/B/C/D 标记，记录下来后续推断
            if row_text.strip() and not QUESTION_NUMBER_PATTERN.search(row_text):
                unmatched_rows.append((row_index, row_boxes))

    # 已有部分选项（如 A、B）但不足 4 个时，用未匹配行补全 C/D
    matched_labels = [l for l in ("A", "B", "C", "D") if l in options]
    if 1 <= len(matched_labels) < 4 and unmatched_rows:
        for row_idx, row_boxes in unmatched_rows:
            if len(matched_labels) >= 4:
                break
            # 找下一个缺失的标签
            next_label = None
            for candidate in ["A", "B", "C", "D"]:
                if candidate not in matched_labels:
                    next_label = candidate
                    break
            if not next_label:
                break

            row_sorted = sorted(row_boxes, key=lambda b: b["local_x"])
            avg_y = sum(b["local_y"] for b in row_sorted) / len(row_sorted)
            center_x = sum(b["local_x"] for b in row_sorted) / len(row_sorted)
            row_text = " ".join(b["text"] for b in row_sorted)

            options[next_label] = _build_option_info(
                label=next_label,
                text=row_text,
                local_x=center_x,
                local_y=avg_y,
                width=max(b.get("width", 60) for b in row_sorted),
                height=max(b.get("height", 20) for b in row_sorted),
                region_left=region_left,
                region_top=region_top,
                image_width=image.width,
                score=sum(b.get("score", 0.5) for b in row_sorted) / len(row_sorted),
                backend=row_sorted[0]["backend"] + "-inferred",
            )
            matched_labels.append(next_label)
            print(f"    推断选项 {next_label}: {row_text!r}")

    if len(options) < 2:
        fallback_options = _infer_options_by_rows(
            rows,
            image.width,
            image.height,
            region_left,
            region_top,
        )
        for label, option_info in fallback_options.items():
            options.setdefault(label, option_info)

    if 2 <= len([label for label in options if label in LETTER_INDEX]) < 4:
        options = infer_options_from_any_two(
            options,
            region_left,
            region_top,
            image.width,
        )

    if "正确" not in options and "T" in options:
        options["TRUE"] = dict(options["T"])
    if "错误" not in options and "F" in options:
        options["FALSE"] = dict(options["F"])
    if "T" not in options and "正确" in options:
        options["T"] = dict(options["正确"])
    if "F" not in options and "错误" in options:
        options["F"] = dict(options["错误"])

    return options
