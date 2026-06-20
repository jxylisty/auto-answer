from PIL import Image, ImageOps
from PySide6.QtGui import QImage, QPixmap


def pil_image_to_pixmap(image: Image.Image) -> QPixmap:
    """Convert a PIL image to QPixmap for preview display."""
    rgb_image = image.convert("RGB")
    width, height = rgb_image.size
    bytes_per_line = width * 3
    qimage = QImage(
        rgb_image.tobytes(), width, height, bytes_per_line, QImage.Format_RGB888
    ).copy()
    return QPixmap.fromImage(qimage)


def prepare_image_for_ocr(image: Image.Image) -> Image.Image:
    """
    OCR 图像预处理：只缩放大图，不做其他处理。
    RapidOCR/PaddleOCR 引擎内部已有完善的预处理流水线，
    额外的灰度化/CLAHE/反转等操作反而会降低识别率。
    """
    max_width = 480
    max_height = 360
    width, height = image.size

    if width <= max_width and height <= max_height:
        return image

    scale = min(max_width / width, max_height / height)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.Resampling.BILINEAR)
