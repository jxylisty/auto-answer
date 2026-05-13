from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from core.screenshot import get_virtual_geometry


class SelectionOverlay(QWidget):
    selection_made = Signal(QRect)
    selection_canceled = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Screen OCR Overlay")
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.Tool, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

        left, top, width, height = get_virtual_geometry()
        self.screen_left = left
        self.screen_top = top
        self.setGeometry(left, top, width, height)

        self.drag_start_local: Optional[QPoint] = None
        self.drag_current_local: Optional[QPoint] = None
        self.selection_rect_local = QRect()

    def show_full_desktop(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.selection_canceled.emit()
            self.close()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_local = event.position().toPoint()
            self.drag_current_local = self.drag_start_local
            self.selection_rect_local = QRect(
                self.drag_start_local, self.drag_current_local
            ).normalized()
            self.update()

    def mouseMoveEvent(self, event):
        if self.drag_start_local is not None:
            self.drag_current_local = event.position().toPoint()
            self.selection_rect_local = QRect(
                self.drag_start_local, self.drag_current_local
            ).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self.drag_start_local is None:
            return

        self.drag_current_local = event.position().toPoint()
        rect_local = QRect(self.drag_start_local, self.drag_current_local).normalized()

        self.drag_start_local = None
        self.drag_current_local = None
        self.selection_rect_local = QRect()
        self.update()

        if rect_local.width() < 2 or rect_local.height() < 2:
            self.selection_canceled.emit()
            self.close()
            return

        global_top_left = self.mapToGlobal(rect_local.topLeft())
        rect_global = QRect(
            global_top_left.x(),
            global_top_left.y(),
            rect_local.width(),
            rect_local.height(),
        )
        print(f"mouseReleaseEvent rect_local={rect_local}")
        print(f"mouseReleaseEvent rect_global={rect_global}")
        self.close()
        QTimer.singleShot(120, lambda: self.selection_made.emit(rect_global))

    def paintEvent(self, event):
        _ = event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(5, 8, 14, 110))

        if not self.selection_rect_local.isNull():
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(self.selection_rect_local, Qt.transparent)

            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(86, 170, 255), 2))
            painter.drawRect(self.selection_rect_local)

            hint_rect = QRect(
                self.selection_rect_local.left(),
                max(0, self.selection_rect_local.top() - 30),
                220,
                26,
            )
            painter.fillRect(hint_rect, QColor(16, 20, 28, 210))
            painter.setPen(Qt.white)
            painter.drawText(
                hint_rect.adjusted(10, 0, 0, 0),
                Qt.AlignVCenter,
                f"{self.selection_rect_local.width()} x {self.selection_rect_local.height()}",
            )
