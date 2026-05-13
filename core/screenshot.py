import ctypes
import sys
from typing import Tuple

import mss
from PIL import Image
from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication


def get_virtual_geometry() -> Tuple[int, int, int, int]:
    """Return the full virtual desktop bounds for multi-monitor setups."""
    if sys.platform == "win32":
        user32 = ctypes.windll.user32
        sm_xvirtualscreen = 76
        sm_yvirtualscreen = 77
        sm_cxvirtualscreen = 78
        sm_cyvirtualscreen = 79
        left = user32.GetSystemMetrics(sm_xvirtualscreen)
        top = user32.GetSystemMetrics(sm_yvirtualscreen)
        width = user32.GetSystemMetrics(sm_cxvirtualscreen)
        height = user32.GetSystemMetrics(sm_cyvirtualscreen)
        return left, top, width, height

    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return 0, 0, 0, 0
    geometry = screen.geometry()
    return geometry.x(), geometry.y(), geometry.width(), geometry.height()


def grab_region(rect: QRect) -> Image.Image:
    """Capture the selected region directly with mss."""
    monitor = {
        "left": int(rect.left()),
        "top": int(rect.top()),
        "width": int(rect.width()),
        "height": int(rect.height()),
    }
    print(f"grab_region rect={rect}")
    print(f"grab_region monitor={monitor}")
    with mss.mss() as sct:
        shot = sct.grab(monitor)
    return Image.frombytes("RGB", shot.size, shot.rgb)
