from PIL import Image
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
    """Shrink large images before OCR to reduce inference time."""
    max_width = 480
    max_height = 360
    width, height = image.size
    print(f"prepare_image_for_ocr before={width}x{height}")

    if width <= max_width and height <= max_height:
        print(f"prepare_image_for_ocr after={width}x{height}")
        return image

    scale = min(max_width / width, max_height / height)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    resized = image.resize(new_size, Image.Resampling.BILINEAR)
    print(f"prepare_image_for_ocr after={resized.size[0]}x{resized.size[1]}")
    return resized
