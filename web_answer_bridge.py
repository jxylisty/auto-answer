from __future__ import annotations

from typing import Dict, List

import api_bridge


TRUE_TOKENS = {"TRUE", "T", "正确", "对", "是", "1", "YES", "Y", "√", "✓"}
FALSE_TOKENS = {"FALSE", "F", "错误", "错", "否", "0", "NO", "N", "×", "✗"}


def _normalize_token(token: str) -> str:
    import unicodedata

    value = unicodedata.normalize("NFKC", str(token or "")).strip().upper()
    for ch in (" ", "\t", "\n", "\r", ",", "，", ";", "；", ":", "：", "/", "|", "(", ")", "[", "]", "【", "】", ".", "。"):
        value = value.replace(ch, "")
    return value


def _question_display_no(question_no: int) -> str:
    if question_no <= 20:
        return str(question_no)
    if question_no <= 35:
        return f"二-{question_no - 20}"
    return f"三-{question_no - 35}"


def _question_type_from_no(question_no: int) -> str:
    if question_no <= 20:
        return "single"
    if question_no <= 35:
        return "multi"
    return "true_false"


def _collect_ordered_answers(answers_data: Dict) -> list[dict]:
    rows = []
    if isinstance(answers_data, dict):
        rows = answers_data.get("rows") or []

    ordered: list[dict] = []
    if isinstance(rows, list) and rows:
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("status") != "valid":
                continue
            answer = str(row.get("answer", "") or "").strip()
            if not answer:
                continue
            ordered.append(
                {
                    "answer": answer,
                    "raw_input": str(row.get("raw_input", "") or "").strip(),
                    "global_id": str(row.get("global_id", "") or "").strip(),
                }
            )
        return ordered

    answers_dict = {}
    if isinstance(answers_data, dict):
        answers_dict = answers_data.get("answers", {}) or {}

    for key, value in answers_dict.items():
        answer = str(value or "").strip()
        if not answer:
            continue
        ordered.append(
            {
                "answer": answer,
                "raw_input": str(key),
                "global_id": str(key),
            }
        )
    return ordered


def _option_labels(options: dict) -> dict[str, str]:
    labels: dict[str, str] = {}
    for label in options.keys():
        labels[_normalize_token(label)] = label
    return labels


def _option_tokens(option: dict) -> set[str]:
    tokens = set()
    label = _normalize_token(option.get("label", ""))
    text = _normalize_token(option.get("text", ""))
    if label:
        tokens.add(label)
    if text:
        tokens.add(text)
    if text in TRUE_TOKENS:
        tokens.update({"TRUE", "T", "正确", "对", "是", "1", "YES", "Y", "√", "✓"})
    if text in FALSE_TOKENS:
        tokens.update({"FALSE", "F", "错误", "错", "否", "0", "NO", "N", "×", "✗"})
    return tokens


def _resolve_labels(answer_token: str, options: dict) -> list[str]:
    normalized_token = _normalize_token(answer_token)
    if not normalized_token:
        return []

    normalized_options = _option_labels(options)
    if normalized_token in normalized_options:
        return [normalized_options[normalized_token]]

    for label, option in options.items():
        if normalized_token in _option_tokens(option):
            return [label]

    if normalized_token in TRUE_TOKENS:
        for candidate in ("TRUE", "T", "正确", "对", "是", "1", "YES", "Y", "√", "✓"):
            if candidate in normalized_options:
                return [normalized_options[candidate]]
        for label, option in options.items():
            if _normalize_token(option.get("text", "")) in TRUE_TOKENS:
                return [label]

    if normalized_token in FALSE_TOKENS:
        for candidate in ("FALSE", "F", "错误", "错", "否", "0", "NO", "N", "×", "✗"):
            if candidate in normalized_options:
                return [normalized_options[candidate]]
        for label, option in options.items():
            if _normalize_token(option.get("text", "")) in FALSE_TOKENS:
                return [label]

    if len(normalized_token) > 1 and normalized_token.isalpha():
        labels: list[str] = []
        for ch in normalized_token:
            if ch not in normalized_options:
                return []
            labels.append(normalized_options[ch])
        return labels

    return []


def _get_option_click(record: dict, label: str) -> list[int] | None:
    options = record.get("options", {}) or {}
    if label in options:
        opt = options.get(label, {}) or {}
        click_x = opt.get("click_x", opt.get("screen_x", 0))
        click_y = opt.get("click_y", opt.get("screen_y", 0))
        return [int(click_x or 0), int(click_y or 0)]

    normalized_label = _normalize_token(label)
    for option_label, opt in options.items():
        if _normalize_token(option_label) == normalized_label:
            click_x = opt.get("click_x", opt.get("screen_x", 0))
            click_y = opt.get("click_y", opt.get("screen_y", 0))
            return [int(click_x or 0), int(click_y or 0)]
        if normalized_label in _option_tokens(opt):
            click_x = opt.get("click_x", opt.get("screen_x", 0))
            click_y = opt.get("click_y", opt.get("screen_y", 0))
            return [int(click_x or 0), int(click_y or 0)]

    click_x = record.get(f"option_{label}_click_x", 0)
    click_y = record.get(f"option_{label}_click_y", 0)
    if click_x or click_y:
        return [int(click_x or 0), int(click_y or 0)]
    return None


def build_answer_click_tasks(answers_data: Dict = None) -> Dict:
    api_bridge._execution_stopped = False
    answers_data = answers_data or {}

    ordered_answers = _collect_ordered_answers(answers_data)
    question_points = list(api_bridge._detected_question_points or [])
    collected_records = list(api_bridge._collected_records or [])

    tasks = []
    ready_count = 0
    no_answer_count = 0
    no_option_count = 0
    need_check_count = 0

    total = len(ordered_answers)
    for index in range(total):
        question_no = index + 1
        display_no = _question_display_no(question_no)
        qtype = _question_type_from_no(question_no)
        qpoint = question_points[index] if index < len(question_points) else None
        record = collected_records[index] if index < len(collected_records) else None
        answer_token = ordered_answers[index]["answer"] if index < len(ordered_answers) else ""

        if not answer_token:
            tasks.append(
                {
                    "index": question_no,
                    "question_no": question_no,
                    "display_no": display_no,
                    "global_id": f"Q{question_no:06d}",
                    "answer": "",
                    "question_click": [qpoint["x"], qpoint["y"]] if qpoint else None,
                    "answer_clicks": [],
                    "status": "no_answer",
                    "message": "没有答案",
                }
            )
            no_answer_count += 1
            continue

        if not qpoint:
            tasks.append(
                {
                    "index": question_no,
                    "question_no": question_no,
                    "display_no": display_no,
                    "global_id": f"Q{question_no:06d}",
                    "answer": answer_token,
                    "question_click": None,
                    "answer_clicks": [],
                    "status": "no_question_point",
                    "message": "没有题号坐标",
                }
            )
            no_option_count += 1
            continue

        if not record:
            tasks.append(
                {
                    "index": question_no,
                    "question_no": question_no,
                    "display_no": display_no,
                    "global_id": f"Q{question_no:06d}",
                    "answer": answer_token,
                    "question_click": [qpoint["x"], qpoint["y"]],
                    "answer_clicks": [],
                    "status": "no_option",
                    "message": "没有采集到选项坐标",
                }
            )
            no_option_count += 1
            continue

        options = record.get("options", {}) or {}
        resolved_labels = _resolve_labels(answer_token, options)
        answer_clicks: list[list[int]] = []

        for label in resolved_labels:
            click_point = _get_option_click(record, label)
            if click_point:
                answer_clicks.append(click_point)

        normalized_answer = _normalize_token(answer_token)
        if not answer_clicks or all(point == [0, 0] for point in answer_clicks):
            tasks.append(
                {
                    "index": question_no,
                    "question_no": question_no,
                    "display_no": display_no,
                    "global_id": f"Q{question_no:06d}",
                    "answer": answer_token,
                    "question_click": [qpoint["x"], qpoint["y"]],
                    "answer_clicks": [],
                    "status": "no_option",
                    "message": "选项坐标未找到",
                }
            )
            no_option_count += 1
            continue

        if qtype == "multi":
            status = "ready" if len(answer_clicks) == len(resolved_labels) and len(resolved_labels) > 0 else "need_check"
        elif qtype == "true_false":
            status = "ready" if len(answer_clicks) == 1 else "need_check"
        else:
            status = "ready" if len(answer_clicks) == 1 and len(normalized_answer) == 1 else "need_check"

        if status == "ready":
            ready_count += 1
        else:
            need_check_count += 1

        tasks.append(
            {
                "index": question_no,
                "question_no": question_no,
                "display_no": display_no,
                "global_id": f"Q{question_no:06d}",
                "answer": answer_token,
                "question_click": [qpoint["x"], qpoint["y"]],
                "answer_clicks": answer_clicks,
                "status": status,
                "message": "",
            }
        )

    api_bridge._answer_click_tasks = tasks
    return {
        "success": True,
        "tasks": tasks,
        "summary": {
            "ready": ready_count,
            "no_answer": no_answer_count,
            "no_option": no_option_count,
            "need_check": need_check_count,
        },
    }
