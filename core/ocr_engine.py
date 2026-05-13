from abc import ABC, abstractmethod
import asyncio
from typing import Optional

import numpy as np
from PIL import Image, ImageOps
from rapidocr_onnxruntime import RapidOCR


class BaseOcrBackend(ABC):
    name: str = "base"

    @abstractmethod
    def recognize(self, image: Image.Image) -> str:
        raise NotImplementedError


class RapidOcrBackend(BaseOcrBackend):
    name = "rapidocr-onnxruntime"

    def __init__(self):
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            self._engine = RapidOCR()
        return self._engine

    def recognize(self, image: Image.Image) -> str:
        engine = self._get_engine()
        image_np = np.array(image)
        try:
            result, _ = engine(image_np, use_cls=False)
        except TypeError:
            result, _ = engine(image_np)
        if not result:
            return ""
        return "\n".join(line[1] for line in result if len(line) >= 2)


class RapidOpenVinoOcrBackend(BaseOcrBackend):
    name = "rapidocr-openvino"

    def __init__(self):
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from rapidocr_openvino import RapidOCR as RapidOpenVino  # type: ignore

            self._engine = RapidOpenVino()
        return self._engine

    def recognize(self, image: Image.Image) -> str:
        engine = self._get_engine()
        image_np = np.array(image)
        try:
            result, _ = engine(image_np, use_cls=False)
        except TypeError:
            result, _ = engine(image_np)
        if not result:
            return ""
        return "\n".join(line[1] for line in result if len(line) >= 2)


class PaddleOcrBackend(BaseOcrBackend):
    name = "paddleocr"

    def __init__(self):
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from paddleocr import PaddleOCR  # type: ignore

            self._engine = PaddleOCR(use_angle_cls=False, lang="ch", show_log=False)
        return self._engine

    def recognize(self, image: Image.Image) -> str:
        engine = self._get_engine()
        image_np = np.array(image)
        try:
            result = engine.ocr(image_np, cls=False)
        except TypeError:
            result = engine.ocr(image_np)
        if not result:
            return ""
        lines = result[0] if isinstance(result, list) else result
        if not lines:
            return ""
        texts: list[str] = []
        for line in lines:
            if not line or len(line) < 2:
                continue
            rec = line[1]
            if isinstance(rec, (list, tuple)) and rec:
                texts.append(str(rec[0]))
            else:
                texts.append(str(rec))
        return "\n".join(text for text in texts if text)


class WindowsOcrBackend(BaseOcrBackend):
    name = "windows-ocr"

    def __init__(self):
        try:
            from winsdk.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
            from winsdk.windows.media.ocr import OcrEngine
            from winsdk.windows.storage.streams import DataWriter
        except Exception as exc:
            raise RuntimeError(
                "Windows OCR runtime is unavailable. Install with: pip install winsdk"
            ) from exc

        self._bitmap_pixel_format = BitmapPixelFormat
        self._software_bitmap = SoftwareBitmap
        self._data_writer = DataWriter
        self._engine = OcrEngine.try_create_from_user_profile_languages()

        if self._engine is None:
            raise RuntimeError("Windows OCR engine is unavailable for current user languages.")

        self._rgba8 = self._get_enum_value(BitmapPixelFormat, "RGBA8", "Rgba8", "rgba8")

    @staticmethod
    def _get_enum_value(enum_cls, *names):
        for name in names:
            if hasattr(enum_cls, name):
                return getattr(enum_cls, name)
        available = [name for name in dir(enum_cls) if not name.startswith("_")]
        raise AttributeError(
            f"{enum_cls.__name__} missing expected enum names {names}; available={available}"
        )

    def _run_async(self, awaitable):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(awaitable)
        finally:
            loop.close()

    def _image_to_software_bitmap(self, image: Image.Image):
        rgba_image = image.convert("RGBA")
        width, height = rgba_image.size

        writer = self._data_writer()
        raw = rgba_image.tobytes()

        try:
            writer.write_bytes(raw)
        except TypeError:
            writer.write_bytes(list(raw))

        bitmap = self._software_bitmap(self._rgba8, width, height)
        bitmap.copy_from_buffer(writer.detach_buffer())
        writer.close()
        return bitmap

    def _recognize_result(self, image: Image.Image):
        software_bitmap = self._image_to_software_bitmap(image)
        return self._run_async(self._engine.recognize_async(software_bitmap))

    def recognize(self, image: Image.Image) -> str:
        result = self._recognize_result(image)
        return result.text or ""


_RAPID_BACKEND: Optional[RapidOcrBackend] = None
_RAPID_OPENVINO_BACKEND: Optional[RapidOpenVinoOcrBackend] = None
_PADDLE_BACKEND: Optional[PaddleOcrBackend] = None
_WINDOWS_BACKEND: Optional[WindowsOcrBackend] = None
_TEXT_BACKEND_ERRORS: dict[str, str] = {}


def get_rapid_backend() -> RapidOcrBackend:
    global _RAPID_BACKEND
    if _RAPID_BACKEND is None:
        _RAPID_BACKEND = RapidOcrBackend()
    return _RAPID_BACKEND


def get_rapid_openvino_backend() -> RapidOpenVinoOcrBackend:
    global _RAPID_OPENVINO_BACKEND
    if _RAPID_OPENVINO_BACKEND is None:
        _RAPID_OPENVINO_BACKEND = RapidOpenVinoOcrBackend()
    return _RAPID_OPENVINO_BACKEND


def get_paddle_backend() -> PaddleOcrBackend:
    global _PADDLE_BACKEND
    if _PADDLE_BACKEND is None:
        _PADDLE_BACKEND = PaddleOcrBackend()
    return _PADDLE_BACKEND


def get_windows_ocr_backend() -> Optional[WindowsOcrBackend]:
    global _WINDOWS_BACKEND
    if _WINDOWS_BACKEND is None:
        try:
            _WINDOWS_BACKEND = WindowsOcrBackend()
        except Exception as exc:
            print(f"Windows OCR unavailable: {exc}")
            return None
    return _WINDOWS_BACKEND


def _get_text_backend_candidates(backend_name: str) -> list[str]:
    if backend_name and backend_name != "auto":
        return [backend_name]
    return [
        "windows-ocr",
        "rapidocr-onnxruntime",
        "paddleocr",
        "rapidocr-openvino",
    ]


def get_ocr_backend(backend_name: str = "auto") -> BaseOcrBackend:
    errors: list[str] = []
    for candidate in _get_text_backend_candidates(backend_name):
        try:
            if candidate == "windows-ocr":
                backend = get_windows_ocr_backend()
                if backend is not None:
                    return backend
                errors.append("windows-ocr unavailable")
            elif candidate == "rapidocr-onnxruntime":
                return get_rapid_backend()
            elif candidate == "rapidocr-openvino":
                return get_rapid_openvino_backend()
            elif candidate == "paddleocr":
                return get_paddle_backend()
            else:
                errors.append(f"unknown backend: {candidate}")
        except Exception as exc:
            error_text = f"{candidate}: {repr(exc)}"
            _TEXT_BACKEND_ERRORS[candidate] = error_text
            errors.append(error_text)

    raise RuntimeError("No text OCR backend available: " + " | ".join(errors))


def recognize_image(image: Image.Image, backend_name: str = "auto") -> str:
    errors: list[str] = []
    for candidate in _get_text_backend_candidates(backend_name):
        try:
            backend = get_ocr_backend(candidate)
            print(f"OCR backend: {backend.name}")
            return backend.recognize(image)
        except Exception as exc:
            error_text = f"{candidate}: {repr(exc)}"
            errors.append(error_text)
            if candidate == "windows-ocr":
                print(f"Windows OCR failed, fallback continues: {repr(exc)}")
            else:
                print(f"OCR backend failed: {error_text}")
            if backend_name != "auto":
                raise RuntimeError(error_text) from exc

    raise RuntimeError("All OCR backends failed: " + " | ".join(errors))


def detect_text_boxes_windows_ocr(image: Image.Image) -> list[dict]:
    backend = get_windows_ocr_backend()
    if backend is None:
        return []

    scale = 3
    work_image = image
    if image.width > 0 and image.height > 0:
        gray_image = ImageOps.grayscale(image)
        enhanced_image = ImageOps.autocontrast(gray_image)
        work_image = enhanced_image.resize(
            (image.width * scale, image.height * scale),
            Image.Resampling.LANCZOS,
        )

    try:
        result = backend._recognize_result(work_image)
    except Exception as exc:
        print(f"Windows OCR detect boxes failed: {repr(exc)}")
        return []

    boxes: list[dict] = []
    for line in getattr(result, "lines", []) or []:
        for word in getattr(line, "words", []) or []:
            text = (getattr(word, "text", "") or "").strip()
            rect = getattr(word, "bounding_rect", None)
            if not rect:
                continue

            x = int(round(getattr(rect, "x", 0) / scale))
            y = int(round(getattr(rect, "y", 0) / scale))
            width = int(round(getattr(rect, "width", 0) / scale))
            height = int(round(getattr(rect, "height", 0) / scale))
            center_x = x + width / 2
            center_y = y + height / 2

            boxes.append(
                {
                    "text": text,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "center_x": center_x,
                    "center_y": center_y,
                    "source": "windows-ocr",
                }
            )
    return boxes


def detect_text_boxes_rapidocr(image: Image.Image) -> list[dict]:
    backend = get_rapid_backend()
    engine = backend._get_engine()

    scale = 2
    work_image = image
    if image.width > 0 and image.height > 0:
        gray_image = ImageOps.grayscale(image)
        enhanced_image = ImageOps.autocontrast(gray_image)
        work_image = enhanced_image.resize(
            (image.width * scale, image.height * scale),
            Image.Resampling.LANCZOS,
        )

    image_np = np.array(work_image)
    try:
        result, _ = engine(image_np, use_cls=False)
    except TypeError:
        result, _ = engine(image_np)
    except Exception as exc:
        print(f"RapidOCR detect boxes failed: {repr(exc)}")
        return []

    if not result:
        return []

    boxes: list[dict] = []
    for item in result:
        if len(item) < 2:
            continue

        quad = item[0]
        text = str(item[1]).strip()
        if not quad or len(quad) < 4:
            continue

        xs = [point[0] for point in quad]
        ys = [point[1] for point in quad]
        x = int(round(min(xs) / scale))
        y = int(round(min(ys) / scale))
        width = int(round((max(xs) - min(xs)) / scale))
        height = int(round((max(ys) - min(ys)) / scale))
        center_x = x + width / 2
        center_y = y + height / 2

        boxes.append(
            {
                "text": text,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "center_x": center_x,
                "center_y": center_y,
                "source": "rapidocr-onnxruntime",
            }
        )
    return boxes
