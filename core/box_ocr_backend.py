import time

import numpy as np
from PIL import Image, ImageOps

from core.ocr_engine import detect_text_boxes_windows_ocr, get_rapid_backend


class BaseBoxOcrBackend:
    name = "base"

    def locate_text_boxes(
        self,
        image: Image.Image,
        region_left: int = 0,
        region_top: int = 0,
    ) -> list[dict]:
        raise NotImplementedError


class RapidOpenVinoBoxBackend(BaseBoxOcrBackend):
    name = "rapidocr-openvino"

    def __init__(self):
        try:
            from rapidocr_openvino import RapidOCR  # type: ignore
        except Exception as exc:
            raise RuntimeError("rapidocr-openvino unavailable") from exc
        self._engine = RapidOCR()

    def locate_text_boxes(
        self,
        image: Image.Image,
        region_left: int = 0,
        region_top: int = 0,
    ) -> list[dict]:
        return _locate_boxes_with_rapid_family(
            self._engine,
            image,
            region_left,
            region_top,
            self.name,
        )


class PaddleBoxBackend(BaseBoxOcrBackend):
    name = "paddleocr"

    def __init__(self):
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except Exception as exc:
            raise RuntimeError("paddleocr unavailable") from exc

        try:
            print("正在初始化 PaddleOCR 引擎...")
            try:
                self._engine = PaddleOCR(use_angle_cls=False, lang="ch", show_log=False)
            except TypeError:
                self._engine = PaddleOCR(use_angle_cls=False, lang="ch")
            except ValueError as exc:
                if "show_log" not in str(exc):
                    raise
                self._engine = PaddleOCR(use_angle_cls=False, lang="ch")
            print("PaddleOCR 引擎初始化成功")
        except Exception as exc:
            print(f"PaddleOCR 引擎初始化失败: {repr(exc)}")
            raise RuntimeError(f"paddleocr init failed: {repr(exc)}") from exc

    def locate_text_boxes(
        self,
        image: Image.Image,
        region_left: int = 0,
        region_top: int = 0,
    ) -> list[dict]:
        work_image = np.array(ImageOps.autocontrast(ImageOps.grayscale(image)))
        try:
            raw_result = self._engine.ocr(work_image, cls=False)
        except TypeError:
            raw_result = self._engine.ocr(work_image)
        except Exception as exc:
            raise RuntimeError(f"paddleocr locate failed: {repr(exc)}") from exc

        lines = raw_result[0] if raw_result and isinstance(raw_result, list) else raw_result
        if not lines:
            return []

        boxes: list[dict] = []
        for item in lines:
            if not item or len(item) < 2:
                continue
            quad = item[0]
            rec = item[1]
            if not quad or not rec:
                continue
            text = str(rec[0]).strip()
            score = float(rec[1]) if len(rec) > 1 else 1.0
            if not text:
                continue
            boxes.append(
                _make_box_result(
                    quad,
                    text,
                    score,
                    region_left,
                    region_top,
                    self.name,
                )
            )
        return boxes


class RapidOnnxBoxBackend(BaseBoxOcrBackend):
    name = "rapidocr-onnxruntime"

    def __init__(self):
        self._engine = get_rapid_backend()._get_engine()

    def locate_text_boxes(
        self,
        image: Image.Image,
        region_left: int = 0,
        region_top: int = 0,
    ) -> list[dict]:
        return _locate_boxes_with_rapid_family(
            self._engine,
            image,
            region_left,
            region_top,
            self.name,
        )


class WindowsBoxBackend(BaseBoxOcrBackend):
    name = "windows-ocr"

    def locate_text_boxes(
        self,
        image: Image.Image,
        region_left: int = 0,
        region_top: int = 0,
    ) -> list[dict]:
        raw_boxes = detect_text_boxes_windows_ocr(image)
        boxes: list[dict] = []
        for box in raw_boxes:
            center_x = int(box.get("center_x", 0))
            center_y = int(box.get("center_y", 0))
            boxes.append(
                {
                    "text": box.get("text", ""),
                    "x": int(box.get("x", 0)),
                    "y": int(box.get("y", 0)),
                    "width": int(box.get("width", 0)),
                    "height": int(box.get("height", 0)),
                    "center_x": center_x,
                    "center_y": center_y,
                    "local_x": center_x,
                    "local_y": center_y,
                    "screen_x": int(region_left + center_x),
                    "screen_y": int(region_top + center_y),
                    "score": 1.0,
                    "source": self.name,
                    "backend": self.name,
                }
            )
        return boxes


def _make_box_result(
    quad,
    text: str,
    score: float,
    region_left: int,
    region_top: int,
    backend_name: str,
) -> dict:
    xs = [float(point[0]) for point in quad]
    ys = [float(point[1]) for point in quad]
    left = min(xs)
    top = min(ys)
    width = max(xs) - left
    height = max(ys) - top
    center_x = left + width / 2
    center_y = top + height / 2
    return {
        "text": text,
        "x": int(round(left)),
        "y": int(round(top)),
        "width": int(round(width)),
        "height": int(round(height)),
        "center_x": int(round(center_x)),
        "center_y": int(round(center_y)),
        "local_x": int(round(center_x)),
        "local_y": int(round(center_y)),
        "screen_x": int(round(region_left + center_x)),
        "screen_y": int(round(region_top + center_y)),
        "score": float(score),
        "source": backend_name,
        "backend": backend_name,
    }


def _locate_boxes_with_rapid_family(
    engine,
    image: Image.Image,
    region_left: int,
    region_top: int,
    backend_name: str,
) -> list[dict]:
    scale = 2
    work_image = ImageOps.autocontrast(ImageOps.grayscale(image)).resize(
        (max(1, image.width * scale), max(1, image.height * scale)),
        Image.Resampling.LANCZOS,
    )
    image_np = np.array(work_image)

    try:
        result, _ = engine(image_np, use_cls=False)
    except TypeError:
        result, _ = engine(image_np)
    except Exception as exc:
        raise RuntimeError(f"{backend_name} locate failed: {repr(exc)}") from exc

    if not result:
        return []

    boxes: list[dict] = []
    for item in result:
        if len(item) < 2:
            continue
        quad = item[0]
        text = str(item[1]).strip()
        score = float(item[2]) if len(item) > 2 else 1.0
        if not quad or len(quad) < 4 or not text:
            continue

        scaled_quad = [[point[0] / scale, point[1] / scale] for point in quad]
        boxes.append(
            _make_box_result(
                scaled_quad,
                text,
                score,
                region_left,
                region_top,
                backend_name,
            )
        )
    return boxes


_BOX_BACKENDS: dict[str, BaseBoxOcrBackend] = {}
_OPTION_BOX_BACKENDS: dict[str, BaseBoxOcrBackend] = {}
_FAILED_BACKENDS: set[str] = set()


def _get_box_backend_candidates(
    backend_name: str,
    for_options: bool = False,
) -> list[type[BaseBoxOcrBackend]]:
    ordered = (
        [RapidOpenVinoBoxBackend, RapidOnnxBoxBackend, WindowsBoxBackend, PaddleBoxBackend]
        if for_options
        else [RapidOpenVinoBoxBackend, RapidOnnxBoxBackend, WindowsBoxBackend, PaddleBoxBackend]
    )
    if backend_name and backend_name != "auto":
        for backend_cls in ordered:
            if backend_cls.name == backend_name:
                return [backend_cls]
        raise RuntimeError(f"Unknown box OCR backend: {backend_name}")
    return ordered


def _backend_available(backend_cls: type[BaseBoxOcrBackend]) -> bool:
    if backend_cls.name == "rapidocr-openvino":
        try:
            import rapidocr_openvino  # type: ignore
        except ImportError:
            print("跳过 rapidocr-openvino（未安装）")
            _FAILED_BACKENDS.add(backend_cls.name)
            return False
    elif backend_cls.name == "paddleocr":
        try:
            import paddleocr  # type: ignore
        except ImportError:
            print("跳过 paddleocr（未安装）")
            _FAILED_BACKENDS.add(backend_cls.name)
            return False
    return True


def get_box_ocr_backend(backend_name: str = "auto") -> BaseBoxOcrBackend:
    if backend_name in _BOX_BACKENDS:
        return _BOX_BACKENDS[backend_name]

    backends_to_try = []
    for backend_cls in _get_box_backend_candidates(backend_name, for_options=False):
        if backend_name == "auto" and backend_cls.name in _FAILED_BACKENDS:
            continue
        if _backend_available(backend_cls):
            backends_to_try.append(backend_cls)

    errors = []
    for backend_cls in backends_to_try:
        try:
            print(f"尝试初始化定位 OCR 后端: {backend_cls.name}")
            backend = backend_cls()
            _BOX_BACKENDS[backend_name] = backend
            if backend_name == "auto":
                _BOX_BACKENDS[backend.name] = backend
            print(f"Box OCR backend: {backend.name}")
            return backend
        except Exception as exc:
            error_msg = f"{backend_cls.name}: {exc}"
            errors.append(error_msg)
            print(f"定位 OCR 后端 {backend_cls.name} 初始化失败: {error_msg}")
            _FAILED_BACKENDS.add(backend_cls.name)

    raise RuntimeError("No box OCR backend available: " + " | ".join(errors))


def get_option_box_ocr_backend(backend_name: str = "auto") -> BaseBoxOcrBackend:
    if backend_name in _OPTION_BOX_BACKENDS:
        return _OPTION_BOX_BACKENDS[backend_name]

    errors = []
    for backend_cls in _get_box_backend_candidates(backend_name, for_options=True):
        try:
            if not _backend_available(backend_cls):
                continue
            print(f"尝试初始化选项 OCR 后端: {backend_cls.name}")
            backend = backend_cls()
            _OPTION_BOX_BACKENDS[backend_name] = backend
            if backend_name == "auto":
                _OPTION_BOX_BACKENDS[backend.name] = backend
            print(f"Option Box OCR backend: {backend.name}")
            return backend
        except Exception as exc:
            error_msg = f"{backend_cls.name}: {exc}"
            errors.append(error_msg)
            print(f"选项 OCR 后端 {backend_cls.name} 初始化失败: {error_msg}")

    error_summary = "No option box OCR backend available: " + " | ".join(errors)
    print(error_summary)
    raise RuntimeError(error_summary)


def locate_text_boxes(
    image: Image.Image,
    region_left: int = 0,
    region_top: int = 0,
    backend_name: str = "auto",
) -> list[dict]:
    backend = get_box_ocr_backend(backend_name)
    t0 = time.perf_counter()
    boxes = backend.locate_text_boxes(image, region_left, region_top)
    t1 = time.perf_counter()
    print(f"Box OCR backend: {backend.name}")
    print(f"Box OCR耗时: {t1 - t0:.3f}s")
    if not boxes:
        print("警告: 未识别到任何文字坐标")
    return boxes


def locate_text_boxes_for_options(
    image: Image.Image,
    region_left: int = 0,
    region_top: int = 0,
    backend_name: str = "auto",
) -> list[dict]:
    backend = get_option_box_ocr_backend(backend_name)
    t0 = time.perf_counter()
    boxes = backend.locate_text_boxes(image, region_left, region_top)
    t1 = time.perf_counter()
    print(f"Option Box OCR backend: {backend.name}")
    print(f"Option Box OCR count: {len(boxes)}")
    print(f"Option Box OCR耗时: {t1 - t0:.3f}s")
    if not boxes:
        print("警告: 未识别到任何选项文字坐标")
    return boxes
