import json
import importlib.util
import re
import time
import unicodedata
from pathlib import Path
from typing import Optional

import pyperclip
from PIL import Image
from PySide6.QtCore import QEvent, QRect, Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.frontend_collect_worker import FrontendCollectWorker
from core.image_utils import pil_image_to_pixmap
from core.box_ocr_backend import get_box_ocr_backend
from core.ocr_engine import (
    detect_text_boxes_rapidocr,
    detect_text_boxes_windows_ocr,
    get_ocr_backend,
)
from core.screenshot import grab_region
from core.text_locator import locate_text_targets
from core.worker import OcrWorker
from ui.selection_overlay import SelectionOverlay
from ui.template_helper import (
    build_template_tab_ui,
    init_template_attributes,
    template_handle_region_selected,
)

try:
    import keyboard
except Exception:
    keyboard = None


DEFAULT_FRONTEND_COLLECT_CONFIG = {
    "click_delay": 0.3,
    "interval": 0.0,
    "start_countdown": 1.0,
    "dry_run": True,
    "save_images": True,
}

FRONTEND_COLLECT_SETTINGS_PATH = Path("frontend_collect_settings.json")


class MainWindow(QMainWindow):
    request_collect_stop = Signal()

    def __init__(self):
        super().__init__()
        self.last_region: Optional[QRect] = None
        self.collect_region: Optional[QRect] = None
        self.number_region: Optional[QRect] = None
        self.last_capture_image: Optional[Image.Image] = None
        self.last_preview_pixmap: Optional[QPixmap] = None
        self.overlay: Optional[SelectionOverlay] = None
        self.overlay_mode: Optional[str] = None
        self.ocr_thread: Optional[QThread] = None
        self.ocr_worker: Optional[OcrWorker] = None
        self.collect_thread: Optional[QThread] = None
        self.collect_worker: Optional[FrontendCollectWorker] = None
        self._keyboard_hotkey_registered = False

        self.frontend_collect_config = self.load_frontend_collect_config()
        self.detected_question_points: list[dict] = []
        self.option_points = {"A": None, "B": None, "C": None, "D": None}
        self.last_collection_points: list[dict] = []
        self.collected_question_records: list[dict] = []
        self.all_collect_text_chunks: list[str] = []
        self.latest_collect_click = "-"
        self.latest_collect_image_path = "-"
        self.latest_option_parse = {}
        
        init_template_attributes(self)

        self.setWindowTitle("截图 OCR")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setMinimumSize(1280, 860)
        self.resize(1480, 1020)

        self.tabs = QTabWidget()
        self.ocr_tab = QWidget()
        self.template_tab = QWidget()
        self.collect_tab = QWidget()
        self.tabs.addTab(self.ocr_tab, "截图 OCR")
        self.tabs.addTab(self.template_tab, "模板辅助")
        self.tabs.addTab(self.collect_tab, "旧版前台采集（备用）")
        self.setCentralWidget(self.tabs)

        self._build_ocr_tab()
        build_template_tab_ui(self)
        self._build_collect_tab()
        self.apply_collect_config_to_ui(self.frontend_collect_config)
        self.apply_styles()

        self.request_collect_stop.connect(self.stop_collection)
        self._register_hotkeys()
        self.refresh_collect_status_labels()

    def _make_card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("card")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        layout.addWidget(title_label)
        return card, layout

    def _configure_spinbox(self, widget, minimum, maximum, value, step=None):
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        if step is not None:
            widget.setSingleStep(step)
        widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        widget.setFixedWidth(160)
        widget.setFixedHeight(48)
        widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        widget.installEventFilter(self)

    def _probe_text_backend_status(self) -> dict[str, bool]:
        statuses = {
            "auto": True,
            "windows-ocr": True,
            "rapidocr-onnxruntime": True,
            "paddleocr": importlib.util.find_spec("paddleocr") is not None,
            "rapidocr-openvino": importlib.util.find_spec("rapidocr_openvino") is not None,
        }
        return statuses

    def _probe_box_backend_status(self) -> dict[str, bool]:
        statuses = {
            "auto": True,
            "windows-ocr": True,
            "rapidocr-onnxruntime": True,
            "paddleocr": importlib.util.find_spec("paddleocr") is not None,
            "rapidocr-openvino": importlib.util.find_spec("rapidocr_openvino") is not None,
        }
        return statuses

    def _populate_text_ocr_combo(self, combo: QComboBox):
        statuses = self._probe_text_backend_status()
        labels = {
            "auto": "自动选择（推荐）",
            "windows-ocr": "windows-ocr",
            "paddleocr": "paddleocr",
            "rapidocr-openvino": "rapidocr-openvino",
            "rapidocr-onnxruntime": "rapidocr-onnxruntime",
        }
        combo.clear()
        for backend_name in (
            "auto",
            "windows-ocr",
            "paddleocr",
            "rapidocr-openvino",
            "rapidocr-onnxruntime",
        ):
            label = labels[backend_name]
            if not statuses.get(backend_name, False):
                label += "（当前不可用）"
            combo.addItem(label, backend_name)
        combo.installEventFilter(self)

    def _populate_box_ocr_combo(self, combo: QComboBox):
        statuses = self._probe_box_backend_status()
        labels = {
            "auto": "自动选择（推荐）",
            "windows-ocr": "windows-ocr",
            "paddleocr": "paddleocr",
            "rapidocr-openvino": "rapidocr-openvino",
            "rapidocr-onnxruntime": "rapidocr-onnxruntime",
        }
        combo.clear()
        for backend_name in (
            "auto",
            "windows-ocr",
            "paddleocr",
            "rapidocr-openvino",
            "rapidocr-onnxruntime",
        ):
            label = labels[backend_name]
            if not statuses.get(backend_name, False):
                label += "（当前不可用）"
            combo.addItem(label, backend_name)
        combo.installEventFilter(self)

    def _build_ocr_tab(self):
        self.capture_btn = QPushButton("截图识别")
        self.fixed_btn = QPushButton("固定区域识别")
        self.copy_capture_btn = QPushButton("复制截图")
        self.clear_btn = QPushButton("清空结果")
        self.copy_btn = QPushButton("复制结果")
        self.single_ocr_backend_combo = QComboBox()
        self._populate_text_ocr_combo(self.single_ocr_backend_combo)
        self.single_ocr_backend_combo.setCurrentIndex(
            max(0, self.single_ocr_backend_combo.findData("windows-ocr"))
        )
        self.result_edit = QTextEdit()
        self.preview_label = QLabel("截图预览")
        self.status_label = QLabel("准备就绪")
        self.status_label.setObjectName("statusLabel")

        self.result_edit.setPlaceholderText("识别结果会显示在这里，并自动复制到剪贴板。")
        self.result_edit.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(300)
        self.preview_label.setStyleSheet(
            "background: #232833; border: 1px solid #313949; border-radius: 14px;"
        )

        self.capture_btn.clicked.connect(self.start_capture)
        self.fixed_btn.clicked.connect(self.recognize_fixed_region)
        self.copy_capture_btn.clicked.connect(self.copy_capture)
        self.clear_btn.clicked.connect(self.clear_result)
        self.copy_btn.clicked.connect(self.copy_result)

        button_row = QHBoxLayout()
        button_row.setSpacing(12)
        button_row.addWidget(self.capture_btn)
        button_row.addWidget(self.fixed_btn)
        button_row.addWidget(self.copy_capture_btn)
        button_row.addWidget(self.clear_btn)
        button_row.addWidget(self.copy_btn)

        backend_row = QHBoxLayout()
        backend_row.setSpacing(12)
        backend_row.addWidget(QLabel("文字 OCR"))
        backend_row.addWidget(self.single_ocr_backend_combo, 1)

        layout = QVBoxLayout(self.ocr_tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        layout.addLayout(button_row)
        layout.addLayout(backend_row)
        layout.addWidget(self.preview_label, 2)
        layout.addWidget(self.result_edit, 3)
        layout.addWidget(self.status_label)

    def _build_collect_tab(self):
        root_layout = QVBoxLayout(self.collect_tab)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(14)

        flow_label = QLabel(
            "向导模式：① 选择题目区域 → ② 智能识别题号 → ③ 开始采集"
        )
        flow_label.setObjectName("hintText")
        flow_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #1976D2;")
        root_layout.addWidget(flow_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        root_layout.addWidget(splitter, 1)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setFixedWidth(620)
        splitter.addWidget(left_scroll)

        left_content = QWidget()
        left_layout = QVBoxLayout(left_content)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(16)
        left_scroll.setWidget(left_content)

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(16)
        splitter.addWidget(right_container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self.select_collect_region_btn = QPushButton("① 选择题目截图区域")
        self.select_number_region_btn = QPushButton("选择题号区域")
        self.save_number_region_btn = QPushButton("保存题号截图")
        self.detect_question_points_btn = QPushButton("② 智能识别题号坐标")
        self.use_detected_points_btn = QPushButton("使用识别坐标采集")
        self.clear_detected_points_btn = QPushButton("清空识别坐标")
        self.collect_start_btn = QPushButton("③ 开始采集")
        self.collect_stop_btn = QPushButton("停止采集")
        self.fill_answers_btn = QPushButton("④ 自动点击答案")
        self.restore_collect_defaults_btn = QPushButton("恢复默认参数")
        self.save_collect_defaults_btn = QPushButton("保存当前参数为默认")
        self.copy_all_collect_text_btn = QPushButton("复制全部采集文本")
        self.clear_collect_text_btn = QPushButton("清空采集文本")

        self.collect_start_btn.setObjectName("primaryLarge")
        self.collect_stop_btn.setObjectName("dangerLarge")
        self.fill_answers_btn.setObjectName("primaryLarge")
        self.collect_start_btn.setMinimumHeight(56)
        self.collect_stop_btn.setMinimumHeight(56)
        self.fill_answers_btn.setMinimumHeight(56)
        self.collect_start_btn.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.collect_stop_btn.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.fill_answers_btn.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.collect_region_label = QLabel("未设置")
        self.collect_region_label.setStyleSheet("font-weight: bold; color: #D32F2F; font-size: 18px;")
        self.collect_region_hint_label = QLabel("框选题目正文区域（包含题号和选项）")
        self.collect_region_hint_label.setWordWrap(True)
        self.collect_region_hint_label.setObjectName("hintText")
        self.number_region_label = QLabel("未设置")
        self.number_region_label.setStyleSheet("font-weight: bold; color: #D32F2F; font-size: 18px;")
        self.number_region_hint_label = QLabel("框选仅包含题号数字的区域，用于自动识别点击坐标")
        self.number_region_hint_label.setWordWrap(True)
        self.number_region_hint_label.setObjectName("hintText")
        self.collect_hint_label = QLabel(
            "点击等待0.3秒，开始倒计时1秒"
        )
        self.collect_hint_label.setWordWrap(True)
        self.collect_hint_label.setObjectName("hintText")

        self.click_delay_spin = QDoubleSpinBox()
        self.interval_spin = QDoubleSpinBox()
        self.start_countdown_spin = QDoubleSpinBox()
        self._configure_spinbox(self.click_delay_spin, 0.0, 60.0, 0.3, 0.1)
        self._configure_spinbox(self.interval_spin, 0.0, 60.0, 0.0, 0.1)
        self._configure_spinbox(self.start_countdown_spin, 0.0, 60.0, 1.0, 0.1)
        self.start_countdown_spin.setDecimals(2)
        self.interval_spin.setDecimals(2)
        self.start_countdown_spin.setDecimals(2)

        self.ocr_backend_combo = QComboBox()
        self._populate_box_ocr_combo(self.ocr_backend_combo)
        self.ocr_backend_combo.setCurrentIndex(
            max(0, self.ocr_backend_combo.findData("rapidocr-openvino"))
        )
        self.collect_text_ocr_backend_combo = QComboBox()
        self._populate_text_ocr_combo(self.collect_text_ocr_backend_combo)
        self.collect_text_ocr_backend_combo.setCurrentIndex(
            max(0, self.collect_text_ocr_backend_combo.findData("windows-ocr"))
        )
        self.collect_option_ocr_backend_combo = QComboBox()
        self._populate_box_ocr_combo(self.collect_option_ocr_backend_combo)
        self.collect_option_ocr_backend_combo.setCurrentIndex(
            max(0, self.collect_option_ocr_backend_combo.findData("rapidocr-openvino"))
        )

        self.test_mode_checkbox = QCheckBox("测试模式（不实际点击）")
        self.test_mode_checkbox.setChecked(True)
        self.save_screenshots_checkbox = QCheckBox("保存截图")

        self.collect_progress_label = QLabel("未开始")
        self.collect_status_progress_value = QLabel("未开始")
        self.collect_status_click_value = QLabel("-")
        self.collect_status_mode_value = QLabel("测试模式")
        self.collect_status_region_value = QLabel("未设置")
        self.collect_status_path_value = QLabel("-")
        self.collect_status_path_value.setWordWrap(True)
        
        self.collect_progress_bar = QProgressBar()
        self.collect_progress_bar.setMinimum(0)
        self.collect_progress_bar.setMaximum(100)
        self.collect_progress_bar.setValue(0)
        self.collect_progress_bar.setTextVisible(True)
        self.collect_progress_bar.setFormat("%p% - %v/%m")

        self.collect_log_edit = QPlainTextEdit()
        self.collect_log_edit.setReadOnly(True)
        self.collect_log_edit.setPlaceholderText("采集日志会显示在这里...")

        self.collect_text_edit = QPlainTextEdit()
        self.collect_text_edit.setReadOnly(True)
        self.collect_text_edit.setPlaceholderText("采集到的题目文本会显示在这里...")

        self.option_a_label = QLabel("未设置")
        self.option_b_label = QLabel("未设置")
        self.option_c_label = QLabel("未设置")
        self.option_d_label = QLabel("未设置")
        self.capture_option_a_btn = QPushButton("记录 A")
        self.capture_option_b_btn = QPushButton("记录 B")
        self.capture_option_c_btn = QPushButton("记录 C")
        self.capture_option_d_btn = QPushButton("记录 D")
        self.answer_sequence_edit = QPlainTextEdit()
        self.answer_sequence_edit.setPlaceholderText(
            "例如：\n1 A\n2 BC\n3 E\n4 T\n或简单单选：ACCDB"
        )
        self.answer_sequence_edit.setMaximumHeight(110)
        self.preview_answers_btn = QPushButton("解析答案")
        self.answer_preview_table = QTableWidget(0, 5)
        self.answer_preview_table.setHorizontalHeaderLabels(["题号", "输入", "匹配标签", "状态", "说明"])
        self.answer_preview_table.verticalHeader().setVisible(False)
        self.answer_preview_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.answer_preview_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.answer_preview_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        self.detected_points_table = QTableWidget(0, 4)
        self.detected_points_table.setHorizontalHeaderLabels(["题号", "X", "Y", "来源"])
        self.detected_points_table.verticalHeader().setVisible(False)
        self.detected_points_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.detected_points_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.detected_points_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        self.select_collect_region_btn.clicked.connect(self.select_collect_region)
        self.select_number_region_btn.clicked.connect(self.select_number_region)
        self.detect_question_points_btn.clicked.connect(self.detect_question_points)
        self.save_number_region_btn.clicked.connect(self.save_number_region_capture)
        self.use_detected_points_btn.clicked.connect(self.start_detected_points_collection)
        self.clear_detected_points_btn.clicked.connect(self.clear_detected_points)
        self.restore_collect_defaults_btn.clicked.connect(self.restore_collect_defaults)
        self.save_collect_defaults_btn.clicked.connect(self.save_current_collect_defaults)
        self.collect_start_btn.clicked.connect(self.start_collection)
        self.collect_stop_btn.clicked.connect(self.stop_collection)
        self.preview_answers_btn.clicked.connect(self.preview_answer_sequence)
        self.fill_answers_btn.clicked.connect(self.fill_answers_by_sequence)
        self.copy_all_collect_text_btn.clicked.connect(self.copy_all_collect_text)
        self.clear_collect_text_btn.clicked.connect(self.clear_collect_text)
        self.test_mode_checkbox.stateChanged.connect(self.refresh_collect_status_labels)
        self.save_screenshots_checkbox.stateChanged.connect(self.refresh_collect_status_labels)

        card, layout = self._make_card("第一步：选择截图区域")
        layout.addWidget(QLabel("题目区域："))
        layout.addWidget(self.collect_region_label)
        layout.addWidget(self.select_collect_region_btn)
        layout.addWidget(self.collect_region_hint_label)
        layout.addSpacing(8)
        layout.addWidget(QLabel("题号区域（可选）："))
        layout.addWidget(self.number_region_label)
        number_row = QHBoxLayout()
        number_row.setSpacing(10)
        number_row.addWidget(self.select_number_region_btn)
        number_row.addWidget(self.save_number_region_btn)
        layout.addLayout(number_row)
        layout.addWidget(self.number_region_hint_label)
        left_layout.addWidget(card)

        card, layout = self._make_card("第二步：智能识别题号")
        layout.addWidget(QLabel("题号 OCR："))
        layout.addWidget(self.ocr_backend_combo)
        layout.addWidget(QLabel("正文 OCR："))
        layout.addWidget(self.collect_text_ocr_backend_combo)
        layout.addWidget(QLabel("选项 OCR："))
        layout.addWidget(self.collect_option_ocr_backend_combo)
        layout.addSpacing(8)
        layout.addWidget(self.detect_question_points_btn)
        detect_row = QHBoxLayout()
        detect_row.setSpacing(10)
        detect_row.addWidget(self.use_detected_points_btn)
        detect_row.addWidget(self.clear_detected_points_btn)
        layout.addLayout(detect_row)
        layout.addSpacing(8)
        layout.addWidget(QLabel("识别结果："))
        layout.addWidget(self.detected_points_table)
        left_layout.addWidget(card)

        card, layout = self._make_card("第三步：开始采集")
        layout.addWidget(self.collect_hint_label)
        layout.addWidget(self.test_mode_checkbox)
        layout.addWidget(self.save_screenshots_checkbox)
        layout.addSpacing(12)
        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        action_row.addWidget(self.collect_start_btn)
        action_row.addWidget(self.collect_stop_btn)
        layout.addLayout(action_row)
        layout.addSpacing(12)
        layout.addWidget(QLabel("进度："))
        layout.addWidget(self.collect_progress_bar)
        layout.addSpacing(12)
        layout.addWidget(QLabel("答案输入（推荐每题一行）："))
        layout.addWidget(self.answer_sequence_edit)
        layout.addSpacing(8)
        layout.addWidget(self.preview_answers_btn)
        layout.addSpacing(8)
        layout.addWidget(self.answer_preview_table)
        layout.addSpacing(8)
        layout.addWidget(self.fill_answers_btn)
        layout.addSpacing(12)
        defaults_row = QHBoxLayout()
        defaults_row.setSpacing(10)
        defaults_row.addWidget(self.restore_collect_defaults_btn)
        defaults_row.addWidget(self.save_collect_defaults_btn)
        layout.addLayout(defaults_row)
        left_layout.addWidget(card)

        card, layout = self._make_card("采集参数（可选）")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.addWidget(QLabel("开始倒计时"), 0, 0)
        grid.addWidget(self.start_countdown_spin, 0, 1)
        grid.addWidget(QLabel("点击后等待"), 0, 2)
        grid.addWidget(self.click_delay_spin, 0, 3)
        layout.addLayout(grid)
        left_layout.addWidget(card)
        left_layout.addStretch(1)

        card, layout = self._make_card("运行状态")
        status_grid = QGridLayout()
        status_grid.setHorizontalSpacing(18)
        status_grid.setVerticalSpacing(10)
        status_grid.addWidget(QLabel("进度"), 0, 0)
        status_grid.addWidget(self.collect_status_progress_value, 0, 1)
        status_grid.addWidget(QLabel("当前点击坐标"), 1, 0)
        status_grid.addWidget(self.collect_status_click_value, 1, 1)
        status_grid.addWidget(QLabel("当前模式"), 2, 0)
        status_grid.addWidget(self.collect_status_mode_value, 2, 1)
        status_grid.addWidget(QLabel("当前截图区域"), 3, 0)
        status_grid.addWidget(self.collect_status_region_value, 3, 1)
        status_grid.addWidget(QLabel("最近一次保存路径"), 4, 0)
        status_grid.addWidget(self.collect_status_path_value, 4, 1)
        layout.addLayout(status_grid)
        right_layout.addWidget(card)

        card, layout = self._make_card("采集日志")
        layout.addWidget(self.collect_log_edit)
        right_layout.addWidget(card, 2)

        card, layout = self._make_card("采集到的题目文本")
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addWidget(self.copy_all_collect_text_btn)
        buttons.addWidget(self.clear_collect_text_btn)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addWidget(self.collect_text_edit)
        right_layout.addWidget(card, 3)

        card, layout = self._make_card("最近一题选项解析")
        self.latest_options_edit = QPlainTextEdit()
        self.latest_options_edit.setReadOnly(True)
        self.latest_options_edit.setPlaceholderText("识别到的真实选项标签会显示在这里...")
        layout.addWidget(self.latest_options_edit)
        right_layout.addWidget(card, 2)

        self.collect_stop_btn.setEnabled(False)

    def load_frontend_collect_config(self):
        config = dict(DEFAULT_FRONTEND_COLLECT_CONFIG)
        if not FRONTEND_COLLECT_SETTINGS_PATH.exists():
            return config
        try:
            data = json.loads(FRONTEND_COLLECT_SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key in config:
                    if key in data:
                        config[key] = data[key]
        except Exception:
            return dict(DEFAULT_FRONTEND_COLLECT_CONFIG)
        return config

    def get_collect_config_from_ui(self):
        return {
            "click_delay": self.click_delay_spin.value(),
            "interval": self.interval_spin.value(),
            "start_countdown": self.start_countdown_spin.value(),
            "dry_run": self.test_mode_checkbox.isChecked(),
            "save_images": self.save_screenshots_checkbox.isChecked(),
        }

    def apply_collect_config_to_ui(self, config):
        self.click_delay_spin.setValue(float(config["click_delay"]))
        self.interval_spin.setValue(float(config["interval"]))
        self.start_countdown_spin.setValue(float(config["start_countdown"]))
        self.test_mode_checkbox.setChecked(bool(config["dry_run"]))
        self.save_screenshots_checkbox.setChecked(bool(config["save_images"]))

    def restore_collect_defaults(self):
        self.apply_collect_config_to_ui(dict(DEFAULT_FRONTEND_COLLECT_CONFIG))
        self.append_collect_log("已恢复默认参数")
        self.refresh_collect_status_labels()

    def save_current_collect_defaults(self):
        config = self.get_collect_config_from_ui()
        try:
            FRONTEND_COLLECT_SETTINGS_PATH.write_text(
                json.dumps(config, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.append_collect_log(
                f"已保存当前参数到 {FRONTEND_COLLECT_SETTINGS_PATH.name}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"保存参数失败：\n{exc}")

    def clear_collect_text(self):
        self.all_collect_text_chunks.clear()
        self.collect_text_edit.clear()
        self.answer_sequence_edit.clear()
        self.answer_preview_table.setRowCount(0)

    def _build_llm_answer_prompt(self) -> str:
        return (
            "\n\n===== 请附加给大模型的答题输出要求 =====\n"
            "请直接输出答案，不要解释，不要复述题目。\n"
            "每题一行，按题目顺序输出。\n"
            "每行只保留最终答案本身，或使用“题号 空格 答案”的格式。\n"
            "如果是单选题，输出 1 个选项标签，例如：A 或 E 或 T。\n"
            "如果是多选题，把多个选项标签直接连写，不要加逗号，不要加空格，例如：BC 或 ACD 或 BE。\n"
            "如果页面显示的是 T/F，就输出 T 或 F。\n"
            "如果页面显示的是 正确/错误，就输出 正确 或 错误。\n"
            "如果页面显示的是 √/× 或 ✓/✗ 或 ✔/✘，就按页面符号原样输出。\n"
            "必须尽量使用题目页面真实显示的选项标签，不要擅自把 E 改成 A-D，也不要把 T/F 改写成 正确/错误。\n"
            "不要输出编号列表说明、不要输出括号、不要输出多余文本。\n"
            "可接受示例：\n"
            "1 A\n"
            "2 BC\n"
            "3 E\n"
            "4 T\n"
            "5 错误\n"
        )

    def copy_all_collect_text(self):
        text = self.collect_text_edit.toPlainText()
        if not text.strip():
            QMessageBox.information(self, "提示", "还没有可复制的采集文本。")
            return
        payload = text + self._build_llm_answer_prompt()
        pyperclip.copy(payload)
        self.append_collect_log("已复制全部采集文本，并追加大模型答案格式要求")

    def clear_detected_points(self):
        self.detected_question_points.clear()
        self.detected_points_table.setRowCount(0)
        self.append_collect_log("已清空识别坐标")

    def _option_label_for_letter(self, letter: str) -> QLabel:
        return {
            "A": self.option_a_label,
            "B": self.option_b_label,
            "C": self.option_c_label,
            "D": self.option_d_label,
        }[letter]

    def _format_point_text(self, point: Optional[dict]) -> str:
        if not point:
            return "未设置"
        return f"x={point['x']}, y={point['y']}"

    def _format_options_text(self, options: dict) -> str:
        if not options:
            return "[未识别到选项]"

        lines = []
        ordered_labels = sorted(
            options.keys(),
            key=lambda item: (len(item) > 1, item),
        )
        for letter in ordered_labels:
            option = options.get(letter, {})
            text = option.get("text", "") or "[未识别]"
            x = option.get("screen_x", "-")
            y = option.get("screen_y", "-")
            lines.append(f"{letter}: {text}\n坐标: ({x}, {y})")
        return "\n\n".join(lines)

    def _clean_option_display_text(self, label: str, text: str) -> str:
        cleaned = unicodedata.normalize("NFKC", text or "").strip()
        if not cleaned:
            return ""
        pattern = rf"^\s*(?:\(|（)?\s*{re.escape(label)}\s*(?:\)|）|[.、:：])?\s*"
        return re.sub(pattern, "", cleaned, count=1, flags=re.IGNORECASE).strip()

    def _iter_llm_option_items(self, options: dict) -> list[tuple[str, str]]:
        if not options:
            return []

        preferred_labels: list[str] = []
        if "正确" in options or "错误" in options:
            preferred_labels.extend([label for label in ("正确", "错误") if label in options])
        elif "T" in options or "F" in options:
            preferred_labels.extend([label for label in ("T", "F") if label in options])
        else:
            preferred_labels.extend(
                label for label in sorted(options.keys()) if len(label) == 1 and label.isalpha()
            )

        seen_labels = set(preferred_labels)
        for label in sorted(options.keys(), key=lambda item: (len(item) > 1, item)):
            if label in {"TRUE", "FALSE"} or label in seen_labels:
                continue
            preferred_labels.append(label)
            seen_labels.add(label)

        items: list[tuple[str, str]] = []
        for label in preferred_labels:
            option = options.get(label, {})
            option_text = self._clean_option_display_text(label, option.get("text", ""))
            if not option_text:
                continue
            items.append((label, option_text))
        return items

    def _build_collect_question_block(self, record: dict) -> str:
        row_display = record["row"] if record["row"] != "" else "-"
        col_display = record["col"] if record["col"] != "" else "-"
        options = record.get("options", {}) or {}

        raw_lines = [
            unicodedata.normalize("NFKC", line).strip()
            for line in (record.get("ocr_text", "") or "").splitlines()
        ]
        filtered_lines: list[str] = []
        for line in raw_lines:
            if not line:
                continue
            if "当前第" in line and "题" in line:
                continue
            if re.fullmatch(r"[一二三四五六七八九十]?[单不判多].*题\d+(?:\.\d+)?分", line):
                continue
            if re.fullmatch(r"\(?\d+(?:\.\d+)?分\)?", line):
                continue
            if re.fullmatch(r"(?:\(|（)?\s*(?:[A-Z]|T|F|正确|错误|√|×|✓|✗|✔|✘)\s*(?:\)|）)?", line, re.IGNORECASE):
                continue
            filtered_lines.append(line)

        option_lines = [f"{label}. {text}" for label, text in self._iter_llm_option_items(options)]
        body_lines = filtered_lines + option_lines
        body = "\n".join(body_lines) if body_lines else "[空结果]"
        return (
            f"===== 第 {record['index']} 题 row={row_display}, col={col_display} =====\n"
            f"{body}\n"
        )

    def capture_option_point_after_delay(self, letter: str):
        self.set_status(f"请把鼠标移动到选项 {letter} 的中心，3 秒后自动记录")
        self.append_collect_log(f"3 秒后记录选项 {letter} 坐标")
        from PySide6.QtCore import QTimer

        QTimer.singleShot(3000, lambda: self.capture_option_point(letter))

    def capture_option_point(self, letter: str):
        pos = self._get_mouse_position()
        if pos is None:
            return
        point = {"x": int(pos.x), "y": int(pos.y)}
        self.option_points[letter] = point
        self._option_label_for_letter(letter).setText(self._format_point_text(point))
        self.set_status(f"已记录选项 {letter} 坐标")
        self.append_collect_log(f"已记录选项 {letter}：x={point['x']}, y={point['y']}")

    def _build_current_question_points(self) -> list[dict]:
        if self.detected_question_points:
            return [
                {
                    "index": idx + 1,
                    "row": point.get("row", ""),
                    "col": point.get("col", ""),
                    "x": int(point["x"]),
                    "y": int(point["y"]),
                }
                for idx, point in enumerate(self.detected_question_points)
            ]
        return []

    def _normalize_option_token(self, token: str) -> str:
        normalized = unicodedata.normalize("NFKC", token or "").strip().upper()
        for char in ["，", ",", "；", ";", "、", "/", "|", "：", ":", "。", ".", "．", ")", "）", "(", "（"]:
            normalized = normalized.replace(char, "")
        return normalized

    def _normalize_answer_sequence(self) -> list[str]:
        raw = unicodedata.normalize("NFKC", self.answer_sequence_edit.toPlainText() or "").strip()
        if not raw:
            return []

        answers: list[str] = []
        seen_spans: list[tuple[int, int]] = []

        numbered_pattern = re.compile(
            r"(?:Q\d+|第?\s*\d+\s*题?|题目\s*\d+)\s*[：:.．、)\-]*\s*(正确|错误|对|错|TRUE|FALSE|√|×|✓|✗|✔|✘|[A-Z]+)",
            re.IGNORECASE,
        )
        for match in numbered_pattern.finditer(raw):
            token = self._normalize_option_token(match.group(1))
            if token:
                answers.append(token)
                seen_spans.append(match.span())

        if not answers:
            lines = [line.strip() for line in raw.splitlines() if line.strip()]
            if len(lines) > 1:
                for line in lines:
                    part = re.sub(
                        r"^(?:Q\d+|第?\s*\d+\s*题?|题目\s*\d+)\s*[：:.．、)\-]*\s*",
                        "",
                        line,
                        flags=re.IGNORECASE,
                    ).strip()
                    if not part:
                        continue
                    sub_parts = [item for item in part.split() if item]
                    if sub_parts:
                        token = self._normalize_option_token(sub_parts[-1])
                        if token:
                            answers.append(token)

        if not answers:
            tokens = [self._normalize_option_token(item) for item in raw.split()]
            tokens = [item for item in tokens if item]
            if len(tokens) > 1:
                answers = tokens

        if not answers:
            compact = self._normalize_option_token(raw)
            if re.fullmatch(r"[A-D]+", compact):
                answers = list(compact)
            elif compact:
                answers = [compact]

        if answers:
            formatted = " ".join(answers)
            self.answer_sequence_edit.setPlainText(formatted)
            self.append_collect_log(f"已格式化答案输入: {formatted}")

        return answers

    def _describe_answer_preview(self, question_index: int, answer_token: str, question_points: list[dict]) -> dict:
        has_question_point = question_index < len(question_points)
        options = {}
        if question_index < len(self.collected_question_records):
            record = self.collected_question_records[question_index]
            options = record.get("options", {}) or {}

        resolved_labels = self._resolve_answer_labels(answer_token, options)
        option_points = self._get_option_points_for_answer(question_index, answer_token)
        matched_labels = " / ".join(
            point.get("label", "") for point in option_points if point.get("label")
        )
        sources = {point.get("source", "") for point in option_points}

        if option_points and has_question_point:
            note = "将使用页面识别到的真实选项"
            if sources == {"manual-fixed"}:
                note = "将使用手动记录坐标"
            return {
                "question_no": question_index + 1,
                "token": answer_token,
                "matched": matched_labels or answer_token,
                "status": "可执行",
                "note": note,
                "points": option_points,
            }

        if not has_question_point:
            return {
                "question_no": question_index + 1,
                "token": answer_token,
                "matched": matched_labels,
                "status": "超出范围",
                "note": "答案数量超过当前题号坐标数量",
                "points": [],
            }

        if options:
            available_labels = " / ".join(str(label) for label in options.keys())
            if resolved_labels:
                note = f"已识别标签但坐标不完整，可用标签：{available_labels}"
            else:
                note = f"当前题可用标签：{available_labels}"
            return {
                "question_no": question_index + 1,
                "token": answer_token,
                "matched": " / ".join(resolved_labels),
                "status": "无法匹配",
                "note": note,
                "points": [],
            }

        return {
            "question_no": question_index + 1,
            "token": answer_token,
            "matched": "",
            "status": "缺少坐标",
            "note": "当前题还没有识别到可用选项坐标",
            "points": [],
        }

    def _refresh_answer_preview_table(self, preview_rows: list[dict]):
        self.answer_preview_table.setRowCount(0)
        for row_data in preview_rows:
            row = self.answer_preview_table.rowCount()
            self.answer_preview_table.insertRow(row)
            self.answer_preview_table.setItem(row, 0, QTableWidgetItem(str(row_data["question_no"])))
            self.answer_preview_table.setItem(row, 1, QTableWidgetItem(row_data["token"]))
            self.answer_preview_table.setItem(row, 2, QTableWidgetItem(row_data["matched"]))
            self.answer_preview_table.setItem(row, 3, QTableWidgetItem(row_data["status"]))
            self.answer_preview_table.setItem(row, 4, QTableWidgetItem(row_data["note"]))

    def preview_answer_sequence(self, show_message: bool = True) -> list[dict]:
        answers = self._normalize_answer_sequence()
        if not answers:
            self.answer_preview_table.setRowCount(0)
            if show_message:
                QMessageBox.information(
                    self,
                    "提示",
                    "请输入答案。推荐格式：每题一行，如 1 A、2 BC、3 正确。",
                )
            return []

        question_points = self.last_collection_points or self._build_current_question_points()
        preview_rows = [
            self._describe_answer_preview(idx, answer_token, question_points)
            for idx, answer_token in enumerate(answers)
        ]
        self._refresh_answer_preview_table(preview_rows)

        executable_count = sum(1 for row in preview_rows if row["status"] == "可执行")
        skipped_count = len(preview_rows) - executable_count
        self.append_collect_log(
            f"答案解析预览：共 {len(preview_rows)} 题，可执行 {executable_count} 题，待跳过 {skipped_count} 题"
        )
        if show_message:
            self.set_status(
                f"答案预览已更新：可执行 {executable_count} 题，待跳过 {skipped_count} 题"
            )
        return preview_rows

    def _resolve_answer_labels(self, answer_token: str, options: dict) -> list[str]:
        normalized_token = self._normalize_option_token(answer_token)
        if not normalized_token:
            return []

        normalized_options = {
            self._normalize_option_token(label): label
            for label in options.keys()
        }

        if normalized_token in normalized_options:
            return [normalized_options[normalized_token]]

        if normalized_token in {"TRUE", "T", "正确", "对", "√", "✓", "✔"}:
            for candidate in ("TRUE", "T", "正确", "对", "√", "✓", "✔"):
                if candidate in normalized_options:
                    return [normalized_options[candidate]]

        if normalized_token in {"FALSE", "F", "错误", "错", "×", "✗", "✘"}:
            for candidate in ("FALSE", "F", "错误", "错", "×", "✗", "✘"):
                if candidate in normalized_options:
                    return [normalized_options[candidate]]

        if re.fullmatch(r"[A-Z]+", normalized_token):
            labels = []
            for char in normalized_token:
                if char not in normalized_options:
                    return []
                labels.append(normalized_options[char])
            return labels

        return []

    def _get_option_points_for_answer(self, question_index: int, answer_token: str) -> list[dict]:
        options = {}
        if question_index < len(self.collected_question_records):
            record = self.collected_question_records[question_index]
            options = record.get("options", {}) or {}

        resolved_labels = self._resolve_answer_labels(answer_token, options)
        if resolved_labels:
            points = []
            for label in resolved_labels:
                option_data = options.get(label)
                if not option_data:
                    continue
                points.append(
                    {
                        "label": label,
                        "x": int(option_data.get("click_x", option_data.get("screen_x"))),
                        "y": int(option_data.get("click_y", option_data.get("screen_y"))),
                        "source": "recorded-options",
                    }
                )
            if points:
                return points

        if len(answer_token) == 1:
            manual_point = self.option_points.get(answer_token)
            if manual_point is not None:
                return [
                    {
                        "label": answer_token,
                        "x": int(manual_point["x"]),
                        "y": int(manual_point["y"]),
                        "source": "manual-fixed",
                    }
                ]
        return []

    def fill_answers_by_sequence(self):
        preview_rows = self.preview_answer_sequence(show_message=False)
        if not preview_rows:
            QMessageBox.information(self, "提示", "请输入答案。推荐格式：每题一行，如 1 A、2 BC、3 正确。")
            return
        answers = [row["token"] for row in preview_rows]

        question_points = self.last_collection_points or self._build_current_question_points()
        if not question_points:
            QMessageBox.information(self, "提示", "还没有题号点击顺序，请先采集或配置题号坐标。")
            return

        executable_items = []
        missing_indices = []
        for row in preview_rows:
            if row["status"] != "可执行":
                missing_indices.append(f"{row['question_no']}:{row['token']}")
                continue
            executable_items.append(
                (row["question_no"] - 1, row["token"], row["points"])
            )

        if not executable_items:
            QMessageBox.information(
                self,
                "提示",
                "当前没有任何题目的选项坐标可用，无法执行自动点击。",
            )
            return

        answer_count = len(executable_items)
        answer_preview = " ".join(answers)
        skip_hint = ""
        if missing_indices:
            skip_hint = f"\n\n以下题目会跳过：{', '.join(missing_indices)}"
        answer = QMessageBox.question(
            self,
            "确认填写",
            f"即将按顺序填写 {answer_count} 题答案：{answer_preview}{skip_hint}",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            import pyautogui
        except Exception:
            QMessageBox.warning(self, "提示", "未安装 pyautogui，请运行 pip install pyautogui")
            return

        pyautogui.FAILSAFE = True
        click_delay = self.click_delay_spin.value()
        interval = self.interval_spin.value()

        self.hide()
        
        try:
            skipped_count = 0
            for original_index, answer_token in enumerate(answers, start=1):
                question_point = question_points[original_index - 1]
                option_points = self._get_option_points_for_answer(original_index - 1, answer_token)
                if not option_points:
                    skipped_count += 1
                    self.append_collect_log(
                        f"跳过题 {original_index}：答案 {answer_token} 没有可用选项坐标"
                    )
                    continue
                pyautogui.click(question_point["x"], question_point["y"])
                self.append_collect_log(
                    f"填写答案：先点击题号 {original_index}，x={question_point['x']}, y={question_point['y']}"
                )
                QApplication.processEvents()
                time.sleep(click_delay)

                for option_point in option_points:
                    pyautogui.click(option_point["x"], option_point["y"])
                    self.append_collect_log(
                        f"填写答案：题 {original_index} 选择 {option_point['label']}，x={option_point['x']}, y={option_point['y']} ({option_point['source']})"
                    )
                    QApplication.processEvents()
                    if interval > 0:
                        time.sleep(interval)

            self.set_status(f"已填写 {answer_count} 题，跳过 {skipped_count} 题")
        finally:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _register_hotkeys(self):
        if keyboard is None:
            return

        try:
            keyboard.add_hotkey("f8", lambda: self.request_collect_stop.emit())
            self._keyboard_hotkey_registered = True
        except Exception as exc:
            print(f"未能注册 F8 全局热键：{exc}")

    def apply_styles(self):
        self.setStyleSheet(
            """
            QMainWindow { background: #171a21; }
            QWidget {
                color: #edf2f7;
                font-family: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif;
                font-size: 18px;
            }
            QTabWidget::pane { border: none; }
            QTabBar::tab {
                background: #232833;
                color: #edf2f7;
                padding: 16px 28px;
                min-height: 40px;
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
                margin-right: 10px;
                font-size: 18px;
                font-weight: 600;
            }
            QTabBar::tab:selected { background: #2f6df6; }
            QFrame#card {
                background: #232833;
                border: 1px solid #313949;
                border-radius: 18px;
            }
            QLabel#cardTitle { font-size: 20px; font-weight: 700; }
            QLabel#statusLabel { color: #9aa5b5; padding-left: 2px; font-size: 18px; }
            QLabel#hintText { color: #aeb8c7; font-size: 17px; }
            QLabel#warningBar {
                background: rgba(245, 179, 59, 0.15);
                color: #ffd978;
                border: 1px solid rgba(245, 179, 59, 0.4);
                border-radius: 14px;
                padding: 14px 16px;
                font-size: 17px;
            }
            QLabel#infoBar {
                background: rgba(84, 155, 255, 0.12);
                color: #bcd6ff;
                border: 1px solid rgba(84, 155, 255, 0.35);
                border-radius: 14px;
                padding: 14px 16px;
                font-size: 17px;
            }
            QTextEdit, QPlainTextEdit, QTableWidget {
                background: #232833;
                border: 1px solid #313949;
                border-radius: 18px;
                padding: 16px;
                selection-background-color: #3f7cff;
                font-size: 18px;
            }
            QPushButton {
                background: #2f6df6;
                color: white;
                border: none;
                border-radius: 16px;
                padding: 14px 24px;
                min-height: 28px;
                font-size: 18px;
                font-weight: 600;
            }
            QPushButton:hover { background: #4781ff; }
            QPushButton:pressed { background: #275dd2; }
            QPushButton#primaryLarge { background: #2f6df6; }
            QPushButton#primaryLarge:hover { background: #4781ff; }
            QPushButton#dangerLarge { background: #d97757; }
            QPushButton#dangerLarge:hover { background: #e48a6d; }
            QSpinBox, QDoubleSpinBox {
                background: #2b303b;
                border: 1px solid #465063;
                border-radius: 14px;
                padding: 10px 14px;
                min-height: 44px;
                font-size: 18px;
            }
            QCheckBox { spacing: 14px; font-size: 18px; }
            QScrollArea { border: none; background: transparent; }
            QLabel { font-size: 18px; }
            QLineEdit {
                background: #2b303b;
                border: 1px solid #465063;
                border-radius: 14px;
                padding: 10px 14px;
                font-size: 18px;
            }
            QComboBox {
                background: #2b303b;
                border: 1px solid #465063;
                border-radius: 14px;
                padding: 10px 14px;
                font-size: 18px;
            }
            """
        )

    def closeEvent(self, event: QCloseEvent):
        if keyboard is not None and self._keyboard_hotkey_registered:
            try:
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
        super().closeEvent(event)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel and isinstance(
            watched, (QComboBox, QAbstractSpinBox)
        ):
            event.ignore()
            return True
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.last_preview_pixmap is not None and not self.last_preview_pixmap.isNull():
            self.preview_label.setPixmap(
                self.last_preview_pixmap.scaled(
                    self.preview_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def set_status(self, text: str):
        self.status_label.setText(text)

    def append_collect_log(self, text: str):
        self.collect_log_edit.appendPlainText(text)
        scrollbar = self.collect_log_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def append_collect_result_record(self, record: dict):
        block = self._build_collect_question_block(record)
        self.all_collect_text_chunks.append(block)
        current = self.collect_text_edit.toPlainText()
        if current:
            current += "\n"
        current += block
        self.collect_text_edit.setPlainText(current)
        scrollbar = self.collect_text_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self.latest_collect_click = f"({record['click_x']}, {record['click_y']})"
        self.collect_status_click_value.setText(self.latest_collect_click)
        self.latest_collect_image_path = record.get("image_path", "") or self.latest_collect_image_path
        self.collect_status_path_value.setText(self.latest_collect_image_path or "-")
        self.latest_option_parse = record.get("options", {}) or {}
        self.latest_options_edit.setPlainText(self._format_options_text(self.latest_option_parse))

    def refresh_collect_status_labels(self):
        mode = "测试模式" if self.test_mode_checkbox.isChecked() else "正式采集"
        self.collect_status_mode_value.setText(mode)
        if self.collect_region is None:
            self.collect_status_region_value.setText("未设置")
        else:
            self.collect_status_region_value.setText(
                f"left={self.collect_region.left()}, top={self.collect_region.top()}, "
                f"width={self.collect_region.width()}, height={self.collect_region.height()}"
            )
        self.collect_status_click_value.setText(self.latest_collect_click)
        self.collect_status_path_value.setText(self.latest_collect_image_path)

    def clear_result(self):
        self.result_edit.clear()
        self.last_capture_image = None
        self.last_preview_pixmap = None
        self.preview_label.clear()
        self.preview_label.setText("截图预览")
        self.set_status("结果已清空")

    def copy_capture(self):
        if self.last_capture_image is None:
            QMessageBox.information(self, "提示", "还没有可复制的截图，请先截图识别。")
            return
        pixmap = pil_image_to_pixmap(self.last_capture_image)
        QApplication.clipboard().setPixmap(pixmap)
        self.set_status("已复制截图到剪贴板")

    def copy_result(self):
        pyperclip.copy(self.result_edit.toPlainText())
        self.set_status("已复制结果到剪贴板")

    def set_buttons_enabled(self, enabled: bool):
        self.capture_btn.setEnabled(enabled)
        self.fixed_btn.setEnabled(enabled)
        self.copy_capture_btn.setEnabled(enabled)
        self.clear_btn.setEnabled(enabled)
        self.copy_btn.setEnabled(enabled)
        self.single_ocr_backend_combo.setEnabled(enabled)

    def set_collect_buttons_enabled(self, running: bool):
        self.collect_start_btn.setEnabled(not running)
        self.collect_stop_btn.setEnabled(running)
        self.preview_answers_btn.setEnabled(not running)
        self.fill_answers_btn.setEnabled(not running)
        self.select_collect_region_btn.setEnabled(not running)
        self.select_number_region_btn.setEnabled(not running)
        self.detect_question_points_btn.setEnabled(not running)
        self.use_detected_points_btn.setEnabled(not running)
        self.clear_detected_points_btn.setEnabled(not running)
        self.restore_collect_defaults_btn.setEnabled(not running)
        self.save_collect_defaults_btn.setEnabled(not running)
        self.click_delay_spin.setEnabled(not running)
        self.interval_spin.setEnabled(not running)
        self.start_countdown_spin.setEnabled(not running)
        self.test_mode_checkbox.setEnabled(not running)
        self.save_screenshots_checkbox.setEnabled(not running)
        self.ocr_backend_combo.setEnabled(not running)
        self.collect_text_ocr_backend_combo.setEnabled(not running)
        self.collect_option_ocr_backend_combo.setEnabled(not running)
        self.capture_option_a_btn.setEnabled(not running)
        self.capture_option_b_btn.setEnabled(not running)
        self.capture_option_c_btn.setEnabled(not running)
        self.capture_option_d_btn.setEnabled(not running)
        self.answer_sequence_edit.setEnabled(not running)
        self.answer_preview_table.setEnabled(not running)

    def open_selection_overlay(self, mode: str):
        self.hide()
        QApplication.processEvents()
        self.overlay_mode = mode
        self.overlay = SelectionOverlay()
        self.overlay.selection_made.connect(self.on_overlay_region_selected)
        self.overlay.selection_canceled.connect(self.on_capture_canceled)
        self.overlay.show_full_desktop()

    def start_capture(self):
        self.open_selection_overlay("single_ocr")

    def select_collect_region(self):
        self.open_selection_overlay("collect_region")

    def select_number_region(self):
        self.open_selection_overlay("number_region")

    def on_capture_canceled(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.set_status("已取消截图")

    def on_overlay_region_selected(self, rect: QRect):
        mode = self.overlay_mode
        self.overlay_mode = None

        if mode == "collect_region":
            self.collect_region = QRect(rect)
            self.collect_region_label.setText(
                f"left={rect.left()}, top={rect.top()}, width={rect.width()}, height={rect.height()}"
            )
            self.showNormal()
            self.raise_()
            self.activateWindow()
            self.append_collect_log("已选择题目截图区域")
            self.refresh_collect_status_labels()
            return

        if mode == "number_region":
            self.number_region = QRect(rect)
            self.number_region_label.setText(
                f"left={rect.left()}, top={rect.top()}, width={rect.width()}, height={rect.height()}"
            )
            self.showNormal()
            self.raise_()
            self.activateWindow()
            self.append_collect_log("已选择题号区域")
            return
        
        if mode in ["template_top", "template_bottom", "template_question", "manual_point1", "manual_point2"]:
            template_handle_region_selected(self, rect)
            self.showNormal()
            self.raise_()
            self.activateWindow()
            return

        self.last_region = QRect(rect)
        self.start_ocr_task(self.last_region)

    def _infer_question_points(self, points: list[dict], expected_count: int) -> Optional[list[dict]]:
        if len(points) < 3:
            return None
        
        import re
        
        def extract_number(no_str):
            match = re.search(r'\d+', str(no_str))
            return int(match.group()) if match else 0
        
        sorted_points = sorted(points, key=lambda p: (extract_number(p["no"]), p["y"], p["x"]))
        
        x_coords = [p["x"] for p in sorted_points]
        y_coords = [p["y"] for p in sorted_points]
        
        unique_x = sorted(set(x_coords))
        unique_y = sorted(set(y_coords))
        
        x_tolerance = 30
        y_tolerance = 30
        
        x_groups = []
        for x in unique_x:
            if not x_groups or abs(x - x_groups[-1][-1]) > x_tolerance:
                x_groups.append([x])
            else:
                x_groups[-1].append(x)
        
        y_groups = []
        for y in unique_y:
            if not y_groups or abs(y - y_groups[-1][-1]) > y_tolerance:
                y_groups.append([y])
            else:
                y_groups[-1].append(y)
        
        avg_x_positions = [sum(group) / len(group) for group in x_groups]
        avg_y_positions = [sum(group) / len(group) for group in y_groups]
        
        num_cols = len(avg_x_positions)
        num_rows = len(avg_y_positions)
        
        print(f"检测到 {num_rows} 行 × {num_cols} 列的网格")
        
        if num_rows >= 2 and num_cols >= 2:
            x_diffs = []
            for i in range(len(avg_x_positions) - 1):
                x_diffs.append(avg_x_positions[i + 1] - avg_x_positions[i])
            avg_x_diff = sum(x_diffs) / len(x_diffs) if x_diffs else 0
            
            y_diffs = []
            for i in range(len(avg_y_positions) - 1):
                y_diffs.append(avg_y_positions[i + 1] - avg_y_positions[i])
            avg_y_diff = sum(y_diffs) / len(y_diffs) if y_diffs else 0
            
            start_x = avg_x_positions[0]
            start_y = avg_y_positions[0]
            
            total_needed = expected_count
            inferred_rows = (total_needed + num_cols - 1) // num_cols
            
            inferred_points = []
            point_idx = 0
            
            for row in range(inferred_rows):
                for col in range(num_cols):
                    x = int(start_x + col * avg_x_diff)
                    y = int(start_y + row * avg_y_diff)
                    
                    if point_idx < len(sorted_points):
                        inferred_points.append(sorted_points[point_idx])
                        point_idx += 1
                    else:
                        inferred_points.append({
                            "no": str(point_idx + 1),
                            "x": x,
                            "y": y,
                            "source": "inferred",
                            "type": "",
                        })
                        print(f"  推断题号 {point_idx + 1}: ({x}, {y})")
            
            return inferred_points
        
        elif num_rows >= 2:
            y_diffs = []
            for i in range(len(avg_y_positions) - 1):
                y_diffs.append(avg_y_positions[i + 1] - avg_y_positions[i])
            avg_y_diff = sum(y_diffs) / len(y_diffs) if y_diffs else 0
            
            start_x = avg_x_positions[0]
            start_y = avg_y_positions[0]
            
            inferred_points = []
            point_idx = 0
            
            for row in range(expected_count):
                x = int(start_x)
                y = int(start_y + row * avg_y_diff)
                
                if point_idx < len(sorted_points):
                    inferred_points.append(sorted_points[point_idx])
                    point_idx += 1
                else:
                    inferred_points.append({
                        "no": str(point_idx + 1),
                        "x": x,
                        "y": y,
                        "source": "inferred",
                        "type": "",
                    })
                    print(f"  推断题号 {point_idx + 1}: ({x}, {y})")
            
            return inferred_points
        
        elif num_cols >= 2:
            x_diffs = []
            for i in range(len(avg_x_positions) - 1):
                x_diffs.append(avg_x_positions[i + 1] - avg_x_positions[i])
            avg_x_diff = sum(x_diffs) / len(x_diffs) if x_diffs else 0
            
            start_x = avg_x_positions[0]
            start_y = avg_y_positions[0]
            
            inferred_points = []
            point_idx = 0
            
            for col in range(expected_count):
                x = int(start_x + col * avg_x_diff)
                y = int(start_y)
                
                if point_idx < len(sorted_points):
                    inferred_points.append(sorted_points[point_idx])
                    point_idx += 1
                else:
                    inferred_points.append({
                        "no": str(point_idx + 1),
                        "x": x,
                        "y": y,
                        "source": "inferred",
                        "type": "",
                    })
                    print(f"  推断题号 {point_idx + 1}: ({x}, {y})")
            
            return inferred_points
        
        else:
            print("无法推断：题号位置过于集中")
            return None

    def detect_question_points(self):
        if self.number_region is None:
            QMessageBox.information(self, "提示", "请先选择题号区域。")
            return

        image = grab_region(self.number_region)
        image.save("number_region_debug.png")
        self.append_collect_log("已保存题号截图: number_region_debug.png")
        
        selected_backend = self.ocr_backend_combo.currentData()

        try:
            backend = get_box_ocr_backend(selected_backend)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "错误",
                f"初始化OCR后端失败: {selected_backend}\n\n错误信息: {exc}",
            )
            return
        
        print(f"定位OCR后端: {backend.name}")
        
        boxes = backend.locate_text_boxes(
            image,
            region_left=self.number_region.left(),
            region_top=self.number_region.top(),
        )
        print(f"number boxes count: {len(boxes)}")
        
        for idx, box in enumerate(boxes, start=1):
            print(
                "number box "
                f"{idx}: text={box['text']!r}, "
                f"x={box['x']}, y={box['y']}, "
                f"width={box['width']}, height={box['height']}, "
                f"center_x={box['center_x']}, center_y={box['center_y']}, "
                f"source={box['source']}"
            )

        digit_boxes = []
        filtered_boxes = []
        for box in boxes:
            text = box["text"].strip()
            match = re.fullmatch(r"[\s\(\[（【]*?(\d{1,3})[\s\)\]）】、,，.．:：;；]*", text)
            if match:
                normalized_box = dict(box)
                normalized_box["text"] = match.group(1)
                digit_boxes.append(normalized_box)
            else:
                filtered_boxes.append(box)

        print(f"number boxes digit count: {len(digit_boxes)}")
        if filtered_boxes:
            print("number boxes filtered out:")
            for box in filtered_boxes:
                print(f"  filtered text={box['text']!r}")

        if not digit_boxes:
            QMessageBox.information(
                self,
                "提示",
                "未识别到题号，请确保题号区域包含数字。",
            )
            self.set_status("未识别到题号")
            return

        sorted_digit_boxes = sorted(
            digit_boxes,
            key=lambda box: (box["center_y"], box["center_x"]),
        )
        
        groups = []
        if sorted_digit_boxes:
            current_group = [sorted_digit_boxes[0]]
            last_y = sorted_digit_boxes[0]["center_y"]
            
            for box in sorted_digit_boxes[1:]:
                y = box["center_y"]
                if abs(y - last_y) > 50:
                    groups.append(current_group)
                    current_group = [box]
                else:
                    current_group.append(box)
                last_y = y
            
            groups.append(current_group)
        
        print(f"检测到 {len(groups)} 个题号组")
        
        valid_groups = [group for group in groups if len(group) >= 2]
        if valid_groups:
            digit_boxes = [box for group in valid_groups for box in group]
            print(f"过滤孤立数字后保留 {len(digit_boxes)} 个题号框")

        points = []
        
        for box in digit_boxes:
            text = box["text"].strip()
            no = int(text)
            screen_x = int(round(self.number_region.left() + box["center_x"]))
            screen_y = int(round(self.number_region.top() + box["center_y"]))
            
            points.append({
                "no": no,
                "x": screen_x,
                "y": screen_y,
                "source": box["source"],
            })
            print(f"  识别题号: {no} at ({screen_x}, {screen_y})")
        
        points.sort(key=lambda p: (p["y"], p["x"]))
        print(f"共识别 {len(points)} 个题号（不去重）")
        
        self.detected_question_points = points
        self.detected_points_table.setRowCount(0)

        for point in points:
            row = self.detected_points_table.rowCount()
            self.detected_points_table.insertRow(row)
            self.detected_points_table.setItem(row, 0, QTableWidgetItem(str(point["no"])))
            self.detected_points_table.setItem(row, 1, QTableWidgetItem(str(point["x"])))
            self.detected_points_table.setItem(row, 2, QTableWidgetItem(str(point["y"])))
            self.detected_points_table.setItem(row, 3, QTableWidgetItem(point["source"]))

        if not points:
            QMessageBox.information(
                self,
                "提示",
                "未识别到题号，请尝试放大题号区域，或使用两点校准",
            )
            self.set_status("未识别到题号")
            return

        self.set_status(f"已识别到 {len(points)} 个题号坐标")
        self.append_collect_log(f"已识别到 {len(points)} 个题号坐标")

    def start_detected_points_collection(self):
        if not self.detected_question_points:
            QMessageBox.information(self, "提示", "还没有识别到题号坐标。")
            return
        self.start_collection(question_points=self.detected_question_points)

    def save_number_region_capture(self):
        if self.number_region is None:
            QMessageBox.information(self, "提示", "请先选择题号区域。")
            return

        image = grab_region(self.number_region)
        image.save("number_region_debug.png")
        self.append_collect_log("已保存题号截图: number_region_debug.png")
        self.set_status("已保存题号截图")

    def start_detected_points_collection(self):
        if not self.detected_question_points:
            QMessageBox.information(self, "提示", "还没有识别到题号坐标。")
            return
        self.start_collection(question_points=self.detected_question_points)

    def _get_mouse_position(self):
        try:
            import pyautogui
        except Exception:
            QMessageBox.warning(
                self,
                "提示",
                "未安装 pyautogui，无法获取鼠标坐标，请运行 pip install pyautogui",
            )
            self.append_collect_log(
                "未安装 pyautogui，无法获取鼠标坐标，请运行 pip install pyautogui"
            )
            return None
        return pyautogui.position()

    def recognize_fixed_region(self):
        if self.last_region is None:
            QMessageBox.information(self, "提示", "还没有固定区域，请先截图识别。")
            return
        self.start_ocr_task(self.last_region)

    def start_ocr_task(self, rect: QRect):
        if self.ocr_thread is not None:
            return
        self.set_status("正在识别...")
        self.set_buttons_enabled(False)
        self.ocr_thread = QThread(self)
        self.ocr_worker = OcrWorker(
            rect,
            text_ocr_backend=self.single_ocr_backend_combo.currentData(),
        )
        self.ocr_worker.moveToThread(self.ocr_thread)
        self.ocr_thread.started.connect(self.ocr_worker.run)
        self.ocr_worker.captured.connect(self.handle_captured_image)
        self.ocr_worker.finished.connect(self.handle_ocr_finished)
        self.ocr_worker.failed.connect(self.handle_ocr_failed)
        self.ocr_worker.finished.connect(self.ocr_thread.quit)
        self.ocr_worker.failed.connect(self.ocr_thread.quit)
        self.ocr_thread.finished.connect(self.cleanup_ocr_thread)
        self.ocr_thread.start()

    def handle_captured_image(self, image: Image.Image):
        self.last_capture_image = image.copy()
        self.last_preview_pixmap = pil_image_to_pixmap(image)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.preview_label.setPixmap(
            self.last_preview_pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def handle_ocr_finished(self, text: str):
        self.result_edit.setPlainText(text)
        pyperclip.copy(text)
        if text:
            self.set_status("识别完成，结果已复制到剪贴板")
        else:
            self.set_status("未识别到文字，已复制空结果到剪贴板")
        self.set_buttons_enabled(True)

    def handle_ocr_failed(self, error: str):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.set_status("识别失败")
        self.set_buttons_enabled(True)
        QMessageBox.critical(self, "错误", f"识别失败：\n{error}")

    def cleanup_ocr_thread(self):
        if self.ocr_worker is not None:
            self.ocr_worker.deleteLater()
            self.ocr_worker = None
        if self.ocr_thread is not None:
            self.ocr_thread.deleteLater()
            self.ocr_thread = None

    def _start_collect_worker(self, question_points: Optional[list[dict]] = None):
        self.collect_thread = QThread(self)
        self.collect_worker = FrontendCollectWorker(
            capture_region=self.collect_region,
            click_delay=self.click_delay_spin.value(),
            interval=self.interval_spin.value(),
            start_countdown=self.start_countdown_spin.value(),
            test_mode=self.test_mode_checkbox.isChecked(),
            save_screenshots=self.save_screenshots_checkbox.isChecked(),
            text_ocr_backend=self.collect_text_ocr_backend_combo.currentData(),
            option_ocr_backend=self.collect_option_ocr_backend_combo.currentData(),
            parse_options=True,
            question_points=question_points,
        )
        self.collect_worker.moveToThread(self.collect_thread)
        self.collect_thread.started.connect(self.collect_worker.run)
        self.collect_worker.log.connect(self.append_collect_log)
        self.collect_worker.progress.connect(self.on_collect_progress)
        self.collect_worker.progress_value.connect(self.on_collect_progress_value)
        self.collect_worker.show_window.connect(self.on_show_window)
        self.collect_worker.result.connect(self.on_collect_result)
        self.collect_worker.exported.connect(self.on_collect_exported)
        self.collect_worker.finished.connect(self.on_collection_finished)
        self.collect_worker.failed.connect(self.on_collection_failed)
        self.collect_worker.finished.connect(self.collect_thread.quit)
        self.collect_worker.failed.connect(self.collect_thread.quit)
        self.collect_thread.finished.connect(self.cleanup_collect_thread)
        self.set_collect_buttons_enabled(True)
        self.collect_thread.start()

    def start_collection(self, question_points: Optional[list[dict]] = None):
        if self.collect_region is None:
            QMessageBox.information(self, "提示", "请先选择题目截图区域。")
            return
        if self.collect_thread is not None:
            return

        current_points = (
            [
                {
                    "index": idx + 1,
                    "row": point.get("row", ""),
                    "col": point.get("col", ""),
                    "x": int(point["x"]),
                    "y": int(point["y"]),
                }
                for idx, point in enumerate(question_points)
            ]
            if question_points
            else self._build_current_question_points()
        )
        self.last_collection_points = current_points
        total = len(current_points)
        answer = QMessageBox.question(
            self,
            "确认采集",
            f"即将采集 {total} 个题号，请确保网页在前台，不会自动选择答案或提交。",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.collect_log_edit.clear()
        self.collect_text_edit.clear()
        self.latest_options_edit.clear()
        self.all_collect_text_chunks.clear()
        self.collected_question_records.clear()
        self.latest_collect_click = "-"
        self.latest_collect_image_path = "-"
        self.latest_option_parse = {}
        self.collect_progress_label.setText(f"准备采集 {total} 题")
        self.collect_status_progress_value.setText(f"准备采集 {total} 题")
        self.collect_progress_bar.setValue(0)
        self.collect_progress_bar.setMaximum(total)
        self.collect_status_mode_value.setText(
            "测试模式" if self.test_mode_checkbox.isChecked() else "正式采集"
        )
        self.refresh_collect_status_labels()
        self.append_collect_log("即将开始前台采集，请切换到网页前台。")
        self.hide()
        self._start_collect_worker(question_points=question_points)

    def on_collect_progress(self, text: str):
        self.collect_progress_label.setText(text)
        self.collect_status_progress_value.setText(text)

    def on_collect_progress_value(self, current: int, total: int, text: str):
        if total > 0:
            self.collect_progress_bar.setMaximum(total)
            self.collect_progress_bar.setValue(current)
            self.collect_progress_bar.setFormat(f"{text} (%p%)")

    def on_show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def on_collect_result(self, record: dict):
        self.collected_question_records.append(record)
        self.append_collect_result_record(record)

    def on_collect_exported(self, csv_path: str, md_path: str):
        self.collect_status_path_value.setText(f"{csv_path}, {md_path}")
        self.set_status(f"已保存：{csv_path}, {md_path}")

    def stop_collection(self):
        if self.collect_worker is not None:
            self.collect_worker.request_stop()
            self.append_collect_log("已请求停止采集")

    def on_collection_finished(self):
        self.collect_progress_label.setText("已完成")
        self.collect_status_progress_value.setText("已完成")
        self.collect_progress_bar.setValue(self.collect_progress_bar.maximum())
        self.append_collect_log("前台采集结束")
        self.set_collect_buttons_enabled(False)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def on_collection_failed(self, error: str):
        self.collect_progress_label.setText("采集失败")
        self.collect_status_progress_value.setText("采集失败")
        self.collect_progress_bar.setValue(0)
        self.append_collect_log(f"采集失败: {error}")
        self.set_collect_buttons_enabled(False)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        QMessageBox.critical(self, "错误", f"前台采集失败：\n{error}")

    def cleanup_collect_thread(self):
        if self.collect_worker is not None:
            self.collect_worker.deleteLater()
            self.collect_worker = None
        if self.collect_thread is not None:
            self.collect_thread.deleteLater()
            self.collect_thread = None
