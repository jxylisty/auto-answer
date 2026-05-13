import time

from PIL import Image
from PySide6.QtCore import QObject, QRect, Signal, Slot

from core.image_utils import prepare_image_for_ocr
from core.ocr_engine import recognize_image
from core.screenshot import grab_region


class OcrWorker(QObject):
    captured = Signal(object)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, rect: QRect, text_ocr_backend: str = "auto"):
        super().__init__()
        self.rect = QRect(rect)
        self.text_ocr_backend = text_ocr_backend

    @Slot()
    def run(self):
        try:
            t0 = time.perf_counter()
            image = grab_region(self.rect)
            t1 = time.perf_counter()
            image.save("last_capture_debug.png")
            self.captured.emit(image.copy())

            ocr_image = prepare_image_for_ocr(image)
            t2 = time.perf_counter()
            text = recognize_image(ocr_image, backend_name=self.text_ocr_backend).strip()
            t3 = time.perf_counter()

            print(f"截图耗时: {t1 - t0:.3f}s")
            print(f"预处理耗时: {t2 - t1:.3f}s")
            print(f"OCR耗时: {t3 - t2:.3f}s")
            print(f"工作线程总耗时: {t3 - t0:.3f}s")
            self.finished.emit(text)
        except Exception as exc:
            self.failed.emit(str(exc))
