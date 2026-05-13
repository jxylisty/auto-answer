import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image

from core.box_ocr_backend import locate_text_boxes_for_options


LETTER_INDEX = {"A": 0, "B": 1, "C": 2, "D": 3}
TRUE_KEYWORDS = ["正确", "对", "T", "TRUE", "√", "✓"]
FALSE_KEYWORDS = ["错误", "错", "F", "FALSE", "×", "✗"]


def calibrate_options_from_image(
    image: Image.Image,
    region_left: int,
    region_top: int,
    backend_name: str = "auto",
) -> Dict:
    t0 = time.perf_counter()
    boxes = locate_text_boxes_for_options(
        image,
        region_left,
        region_top,
        backend_name=backend_name,
    )
    t1 = time.perf_counter()
    print(f"选项坐标识别耗时: {t1 - t0:.3f}s")
    
    if not boxes:
        print("未识别到任何文本框")
        return {"options": {}, "source": "empty"}
    
    print(f"识别到 {len(boxes)} 个文本框:")
    for box in boxes:
        print(f"  text={box['text']!r}, x={box['local_x']}, y={box['local_y']}")
    
    choice_options = _extract_choice_options(boxes, region_left, region_top)
    judge_options = _extract_judge_options(boxes, region_left, region_top)
    
    result = {
        "options": {},
        "source": "ocr"
    }
    
    if choice_options:
        inferred = _infer_full_choice_options(choice_options)
        result["options"].update(inferred)
        result["choice_source"] = "ocr_inferred" if len(inferred) > len(choice_options) else "ocr"
    
    if judge_options:
        result["options"].update(judge_options)
        result["judge_source"] = "ocr"
    
    return result


def _extract_choice_options(boxes: List[Dict], region_left: int, region_top: int) -> Dict[str, Dict]:
    import re
    from unicodedata import normalize
    
    options = {}
    pattern = re.compile(r"[\(\（]?\s*([A-ZＡ-Ｚ])\s*[\)\）\.\．、:：]")
    
    for box in boxes:
        text = normalize("NFKC", box.get("text", "")).strip()
        match = pattern.search(text)
        
        if match:
            letter = match.group(1)
            letter_map = {chr(ord("Ａ") + idx): chr(ord("A") + idx) for idx in range(26)}
            letter = letter_map.get(letter, letter).upper()
            
            if letter not in options:
                options[letter] = {
                    "click_x": region_left + box["local_x"] + box["width"] // 2,
                    "click_y": region_top + box["local_y"] + box["height"] // 2,
                    "source": "ocr",
                    "text": text,
                }
                print(f"  识别到选项 {letter}: ({options[letter]['click_x']}, {options[letter]['click_y']})")
    
    return options


def _extract_judge_options(boxes: List[Dict], region_left: int, region_top: int) -> Dict[str, Dict]:
    from unicodedata import normalize
    
    options = {}
    
    for box in boxes:
        text = normalize("NFKC", box.get("text", "")).strip().upper()
        
        for keyword in TRUE_KEYWORDS:
            if keyword.upper() in text:
                if "正确" not in options:
                    options["正确"] = {
                        "click_x": region_left + box["local_x"] + box["width"] // 2,
                        "click_y": region_top + box["local_y"] + box["height"] // 2,
                        "source": "ocr",
                        "text": text,
                    }
                    print(f"  识别到 正确: ({options['正确']['click_x']}, {options['正确']['click_y']})")
                break
        
        for keyword in FALSE_KEYWORDS:
            if keyword.upper() in text:
                if "错误" not in options:
                    options["错误"] = {
                        "click_x": region_left + box["local_x"] + box["width"] // 2,
                        "click_y": region_top + box["local_y"] + box["height"] // 2,
                        "source": "ocr",
                        "text": text,
                    }
                    print(f"  识别到 错误: ({options['错误']['click_x']}, {options['错误']['click_y']})")
                break
    
    return options


def _infer_full_choice_options(known_options: Dict[str, Dict]) -> Dict[str, Dict]:
    if len(known_options) >= 4:
        return known_options
    
    if len(known_options) < 2:
        print(f"选项不足2个，无法推断")
        return known_options
    
    letters = list(known_options.keys())
    letter1, letter2 = letters[0], letters[1]
    
    idx1 = LETTER_INDEX[letter1]
    idx2 = LETTER_INDEX[letter2]
    
    x1 = known_options[letter1]["click_x"]
    y1 = known_options[letter1]["click_y"]
    x2 = known_options[letter2]["click_x"]
    y2 = known_options[letter2]["click_y"]
    
    idx_diff = idx2 - idx1
    dx = (x2 - x1) / idx_diff
    dy = (y2 - y1) / idx_diff
    
    layout = _detect_layout(dx, dy)
    print(f"检测到布局: {layout}, dx={dx:.1f}, dy={dy:.1f}")
    
    if layout == "uncertain":
        print("布局不确定，不进行推断")
        return known_options
    
    result = dict(known_options)
    
    for letter, idx in LETTER_INDEX.items():
        if letter not in result:
            inferred_x = int(round(x1 + (idx - idx1) * dx))
            inferred_y = int(round(y1 + (idx - idx1) * dy))
            
            result[letter] = {
                "click_x": inferred_x,
                "click_y": inferred_y,
                "source": "inferred",
            }
            print(f"  推断选项 {letter}: ({inferred_x}, {inferred_y})")
    
    return result


def _detect_layout(dx: float, dy: float) -> str:
    abs_dx = abs(dx)
    abs_dy = abs(dy)
    
    if abs_dy > abs_dx * 1.5:
        return "vertical"
    elif abs_dx > abs_dy * 1.5:
        return "horizontal"
    else:
        return "uncertain"


def calibrate_from_manual_points(
    point1: Tuple[int, int, str],
    point2: Tuple[int, int, str],
) -> Dict:
    x1, y1, label1 = point1
    x2, y2, label2 = point2
    
    result = {"options": {}, "source": "manual"}
    
    if label1 in TRUE_KEYWORDS or label2 in TRUE_KEYWORDS:
        if label1 in TRUE_KEYWORDS:
            result["options"]["正确"] = {"click_x": x1, "click_y": y1, "source": "manual"}
        if label2 in TRUE_KEYWORDS:
            result["options"]["正确"] = {"click_x": x2, "click_y": y2, "source": "manual"}
        if label1 in FALSE_KEYWORDS:
            result["options"]["错误"] = {"click_x": x1, "click_y": y1, "source": "manual"}
        if label2 in FALSE_KEYWORDS:
            result["options"]["错误"] = {"click_x": x2, "click_y": y2, "source": "manual"}
        return result
    
    if label1 in LETTER_INDEX and label2 in LETTER_INDEX:
        known = {
            label1: {"click_x": x1, "click_y": y1, "source": "manual"},
            label2: {"click_x": x2, "click_y": y2, "source": "manual"},
        }
        result["options"] = _infer_full_choice_options(known)
        return result
    
    return result


def build_option_layout_template(
    choice_options: Optional[Dict] = None,
    judge_options: Optional[Dict] = None,
) -> Dict:
    template = {}
    
    if choice_options:
        template["single_choice"] = {
            "options": {
                letter: {
                    "click_x": opt.get("click_x", 0),
                    "click_y": opt.get("click_y", 0),
                    "source": opt.get("source", "unknown"),
                }
                for letter, opt in choice_options.items()
            }
        }
        template["multi_choice"] = {"reuse_from": "single_choice"}
    
    if judge_options:
        template["judge"] = {
            "true_option": {
                "click_x": judge_options.get("正确", {}).get("click_x", 0),
                "click_y": judge_options.get("正确", {}).get("click_y", 0),
                "source": judge_options.get("正确", {}).get("source", "unknown"),
            },
            "false_option": {
                "click_x": judge_options.get("错误", {}).get("click_x", 0),
                "click_y": judge_options.get("错误", {}).get("click_y", 0),
                "source": judge_options.get("错误", {}).get("source", "unknown"),
            },
        }
    
    return template


def save_option_layout_template(template: Dict, filepath: str = "option_layout_template.json"):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)
    print(f"已保存选项模板到 {filepath}")


def load_option_layout_template(filepath: str = "option_layout_template.json") -> Optional[Dict]:
    path = Path(filepath)
    if not path.exists():
        return None
    
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)
