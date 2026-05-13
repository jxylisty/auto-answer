import difflib
import time
import unicodedata
from typing import Optional

from PIL import Image

from core.box_ocr_backend import locate_text_boxes


def _normalize_text(text: str, ignore_case: bool = True) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = " ".join(normalized.split())
    if ignore_case:
        normalized = normalized.lower()
    return normalized


def _match_score(
    normalized_target: str,
    normalized_candidate: str,
    match_mode: str,
    fuzzy_threshold: float,
) -> Optional[float]:
    if not normalized_target or not normalized_candidate:
        return None

    if match_mode == "exact":
        return 1.0 if normalized_candidate == normalized_target else None

    if match_mode == "contains":
        if normalized_target in normalized_candidate:
            return 1.0
        return None

    if match_mode == "fuzzy":
        score = difflib.SequenceMatcher(
            None, normalized_target, normalized_candidate
        ).ratio()
        return score if score >= fuzzy_threshold else None

    return None


def locate_text_targets(
    image: Image.Image,
    targets: list[str],
    region_left: int,
    region_top: int,
    match_mode: str = "contains",
    fuzzy_threshold: float = 0.75,
) -> list[dict]:
    normalized_targets = []
    for target in targets:
        raw_target = (target or "").strip()
        normalized_target = _normalize_text(raw_target)
        if normalized_target:
            normalized_targets.append((raw_target, normalized_target))

    if not normalized_targets:
        return []

    t0 = time.perf_counter()
    boxes = locate_text_boxes(image, region_left, region_top)
    t1 = time.perf_counter()
    print(f"文字定位耗时: {t1 - t0:.3f}s")

    if not boxes:
        print("警告: 未识别到任何文字坐标")
        return []

    matches: list[dict] = []
    for box in boxes:
        text = box["text"]
        normalized_text = _normalize_text(text)
        for raw_target, normalized_target in normalized_targets:
            score = _match_score(
                normalized_target,
                normalized_text,
                match_mode,
                fuzzy_threshold,
            )
            if score is not None:
                matches.append(
                    {
                        "target": raw_target,
                        "matched_text": text,
                        "screen_x": box["screen_x"],
                        "screen_y": box["screen_y"],
                        "local_x": box["local_x"],
                        "local_y": box["local_y"],
                        "width": box["width"],
                        "height": box["height"],
                        "score": float(score),
                        "backend": box["backend"],
                    }
                )

    matches.sort(key=lambda item: (-item["score"], item["target"], item["screen_y"], item["screen_x"]))
    return matches
