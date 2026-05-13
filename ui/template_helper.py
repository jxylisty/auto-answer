import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Dict, List
from PIL import Image
import pyperclip

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QSpinBox, QTableWidget, QTableWidgetItem, QPlainTextEdit, 
    QFileDialog, QMessageBox, QSplitter, QScrollArea, 
    QHeaderView, QFrame, QGroupBox, QComboBox
)
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPixmap

if TYPE_CHECKING:
    from ui.main_window import MainWindow


def build_template_tab_ui(self: 'MainWindow'):
    self.template_tab = QWidget()
    
    root_layout = QVBoxLayout(self.template_tab)
    root_layout.setContentsMargins(18, 18, 18, 18)
    root_layout.setSpacing(14)
    
    flow_label = QLabel(
        "最小可用流程：① 截题号栏 → ② 输入题型数量 → ③ 建立模板 → ④ 导入答案 → ⑤ 生成点击计划"
    )
    flow_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #1976D2;")
    root_layout.addWidget(flow_label)
    
    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.setChildrenCollapsible(False)
    root_layout.addWidget(splitter, 1)
    
    left_scroll = QScrollArea()
    left_scroll.setWidgetResizable(True)
    left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    left_scroll.setFrameShape(QFrame.Shape.NoFrame)
    left_scroll.setFixedWidth(580)
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
    
    self.template_top_btn = QPushButton("① 截左侧题号栏顶部")
    self.template_bottom_btn = QPushButton("截左侧题号栏底部")
    self.template_question_btn = QPushButton("② 截右侧当前题页面")
    self.template_build_btn = QPushButton("③ 建立模板")
    self.template_import_btn = QPushButton("④ 导入答案文件")
    self.template_paste_btn = QPushButton("粘贴答案")
    self.template_generate_btn = QPushButton("⑤ 生成点击计划")
    self.template_save_btn = QPushButton("保存模板")
    
    self.template_build_btn.setStyleSheet("font-size: 16px; font-weight: bold; background-color: #1976D2; color: white;")
    self.template_generate_btn.setStyleSheet("font-size: 16px; font-weight: bold; background-color: #388E3C; color: white;")
    
    self.template_top_label = QLabel("未设置")
    self.template_top_label.setStyleSheet("font-weight: bold; color: #D32F2F;")
    self.template_bottom_label = QLabel("未设置")
    self.template_bottom_label.setStyleSheet("font-weight: bold; color: #D32F2F;")
    self.template_question_label = QLabel("未设置")
    self.template_question_label.setStyleSheet("font-weight: bold; color: #D32F2F;")
    self.template_number_ocr_combo = QComboBox()
    self.template_option_ocr_combo = QComboBox()
    self._populate_box_ocr_combo(self.template_number_ocr_combo)
    self._populate_box_ocr_combo(self.template_option_ocr_combo)
    self.template_number_ocr_combo.setCurrentIndex(
        max(0, self.template_number_ocr_combo.findData("rapidocr-openvino"))
    )
    self.template_option_ocr_combo.setCurrentIndex(
        max(0, self.template_option_ocr_combo.findData("rapidocr-openvino"))
    )
    
    self.template_single_spin = QSpinBox()
    self.template_multi_spin = QSpinBox()
    self.template_judge_spin = QSpinBox()
    self.template_single_spin.setRange(0, 100)
    self.template_multi_spin.setRange(0, 100)
    self.template_judge_spin.setRange(0, 100)
    self.template_single_spin.setValue(0)
    self.template_multi_spin.setValue(0)
    self.template_judge_spin.setValue(0)
    self.template_single_spin.setFixedWidth(80)
    self.template_multi_spin.setFixedWidth(80)
    self.template_judge_spin.setFixedWidth(80)
    self.template_single_spin.installEventFilter(self)
    self.template_multi_spin.installEventFilter(self)
    self.template_judge_spin.installEventFilter(self)
    
    self.template_answer_edit = QPlainTextEdit()
    self.template_answer_edit.setPlaceholderText(
        "在此输入或粘贴答案，支持格式：\n"
        "1 B\n"
        "2 A\n"
        "二-1 ABC\n"
        "三-1 正确\n"
        "Q000021 AD"
    )
    self.template_answer_edit.setMaximumHeight(120)
    
    self.template_info_table = QTableWidget(0, 5)
    self.template_info_table.setHorizontalHeaderLabels(["global_id", "display_no", "题型", "X", "Y"])
    self.template_info_table.verticalHeader().setVisible(False)
    self.template_info_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    self.template_info_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    self.template_info_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    
    self.template_plan_table = QTableWidget(0, 6)
    self.template_plan_table.setHorizontalHeaderLabels([
        "global_id", "display_no", "答案", "题号坐标", "选项坐标", "状态"
    ])
    self.template_plan_table.verticalHeader().setVisible(False)
    self.template_plan_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    self.template_plan_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    self.template_plan_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    
    self.template_log_edit = QPlainTextEdit()
    self.template_log_edit.setReadOnly(True)
    self.template_log_edit.setPlaceholderText("操作日志会显示在这里...")
    
    self.template_top_btn.clicked.connect(lambda: template_select_top_region(self))
    self.template_bottom_btn.clicked.connect(lambda: template_select_bottom_region(self))
    self.template_question_btn.clicked.connect(lambda: template_select_question_region(self))
    self.template_build_btn.clicked.connect(lambda: template_build(self))
    self.template_import_btn.clicked.connect(lambda: template_import_answers(self))
    self.template_paste_btn.clicked.connect(lambda: template_paste_answers(self))
    self.template_generate_btn.clicked.connect(lambda: template_generate_plan(self))
    self.template_save_btn.clicked.connect(lambda: template_save(self))
    
    group = QGroupBox("第一步：截取题号栏")
    group_layout = QVBoxLayout(group)
    group_layout.addWidget(QLabel("顶部截图："))
    group_layout.addWidget(self.template_top_label)
    group_layout.addWidget(self.template_top_btn)
    group_layout.addSpacing(8)
    group_layout.addWidget(QLabel("底部截图（可选，用于识别最后题号）："))
    group_layout.addWidget(self.template_bottom_label)
    group_layout.addWidget(self.template_bottom_btn)
    left_layout.addWidget(group)
    
    group = QGroupBox("第二步：截取题目页面")
    group_layout = QVBoxLayout(group)
    group_layout.addWidget(QLabel("题目截图（用于识别选项）："))
    group_layout.addWidget(self.template_question_label)
    group_layout.addWidget(self.template_question_btn)
    group_layout.addWidget(QLabel("题号 OCR："))
    group_layout.addWidget(self.template_number_ocr_combo)
    group_layout.addWidget(QLabel("选项 OCR："))
    group_layout.addWidget(self.template_option_ocr_combo)
    left_layout.addWidget(group)
    
    group = QGroupBox("第三步：输入题型数量")
    group_layout = QVBoxLayout(group)
    row = QHBoxLayout()
    row.addWidget(QLabel("单选题："))
    row.addWidget(self.template_single_spin)
    row.addSpacing(20)
    row.addWidget(QLabel("多选题："))
    row.addWidget(self.template_multi_spin)
    row.addSpacing(20)
    row.addWidget(QLabel("判断题："))
    row.addWidget(self.template_judge_spin)
    group_layout.addLayout(row)
    group_layout.addSpacing(8)
    group_layout.addWidget(self.template_build_btn)
    left_layout.addWidget(group)
    
    group = QGroupBox("第四步：导入答案")
    group_layout = QVBoxLayout(group)
    btn_row = QHBoxLayout()
    btn_row.addWidget(self.template_import_btn)
    btn_row.addWidget(self.template_paste_btn)
    group_layout.addLayout(btn_row)
    group_layout.addWidget(self.template_answer_edit)
    left_layout.addWidget(group)
    
    group = QGroupBox("第五步：生成点击计划")
    group_layout = QVBoxLayout(group)
    group_layout.addWidget(self.template_generate_btn)
    group_layout.addSpacing(8)
    group_layout.addWidget(self.template_save_btn)
    left_layout.addWidget(group)
    
    group = QGroupBox("手动校准选项（可选）")
    group_layout = QVBoxLayout(group)
    
    row = QHBoxLayout()
    row.addWidget(QLabel("第一点："))
    self.template_manual_label1 = QComboBox()
    self.template_manual_label1.addItems(["A", "B", "C", "D", "正确", "错误"])
    self.template_manual_label1.setFixedWidth(80)
    self.template_manual_label1.installEventFilter(self)
    row.addWidget(self.template_manual_label1)
    self.template_manual_point1_btn = QPushButton("选取坐标")
    self.template_manual_point1_btn.setFixedWidth(100)
    row.addWidget(self.template_manual_point1_btn)
    self.template_manual_point1_label = QLabel("未设置")
    self.template_manual_point1_label.setStyleSheet("color: #D32F2F;")
    row.addWidget(self.template_manual_point1_label)
    row.addStretch()
    group_layout.addLayout(row)
    
    row = QHBoxLayout()
    row.addWidget(QLabel("第二点："))
    self.template_manual_label2 = QComboBox()
    self.template_manual_label2.addItems(["A", "B", "C", "D", "正确", "错误"])
    self.template_manual_label2.setCurrentIndex(1)
    self.template_manual_label2.setFixedWidth(80)
    self.template_manual_label2.installEventFilter(self)
    row.addWidget(self.template_manual_label2)
    self.template_manual_point2_btn = QPushButton("选取坐标")
    self.template_manual_point2_btn.setFixedWidth(100)
    row.addWidget(self.template_manual_point2_btn)
    self.template_manual_point2_label = QLabel("未设置")
    self.template_manual_point2_label.setStyleSheet("color: #D32F2F;")
    row.addWidget(self.template_manual_point2_label)
    row.addStretch()
    group_layout.addLayout(row)
    
    row = QHBoxLayout()
    self.template_manual_apply_btn = QPushButton("应用手动校准")
    self.template_manual_apply_btn.setStyleSheet("background-color: #FF9800; color: white;")
    row.addWidget(self.template_manual_apply_btn)
    row.addStretch()
    group_layout.addLayout(row)
    
    self.template_manual_point1_btn.clicked.connect(lambda: template_select_manual_point1(self))
    self.template_manual_point2_btn.clicked.connect(lambda: template_select_manual_point2(self))
    self.template_manual_apply_btn.clicked.connect(lambda: template_apply_manual_calibration(self))
    
    left_layout.addWidget(group)
    
    right_layout.addWidget(QLabel("模板信息："))
    right_layout.addWidget(self.template_info_table, 1)
    right_layout.addSpacing(8)
    right_layout.addWidget(QLabel("点击计划："))
    right_layout.addWidget(self.template_plan_table, 1)
    right_layout.addSpacing(8)
    right_layout.addWidget(QLabel("日志："))
    right_layout.addWidget(self.template_log_edit, 1)


def init_template_attributes(self: 'MainWindow'):
    self.template_top_image: Optional[Image.Image] = None
    self.template_bottom_image: Optional[Image.Image] = None
    self.template_question_image: Optional[Image.Image] = None
    self.template_top_region: Optional[QRect] = None
    self.template_bottom_region: Optional[QRect] = None
    self.template_question_region: Optional[QRect] = None
    self.template_number_template: Dict = {}
    self.template_option_template: Dict = {}
    self.template_questions: List[Dict] = []
    self.template_answers: Dict[str, str] = {}
    self.template_click_plan: List[Dict] = []
    self.template_overlay_mode: Optional[str] = None
    self.template_manual_point1: Optional[tuple] = None
    self.template_manual_point2: Optional[tuple] = None


def template_select_top_region(self: 'MainWindow'):
    self.template_overlay_mode = "template_top"
    self._start_selection("请框选左侧题号栏顶部区域")


def template_select_bottom_region(self: 'MainWindow'):
    self.template_overlay_mode = "template_bottom"
    self._start_selection("请框选左侧题号栏底部区域")


def template_select_question_region(self: 'MainWindow'):
    self.template_overlay_mode = "template_question"
    self._start_selection("请框选右侧当前题页面区域")


def template_handle_region_selected(self: 'MainWindow', region: QRect):
    from core.screenshot import grab_region
    
    if self.template_overlay_mode == "manual_point1":
        x = region.left() + region.width() // 2
        y = region.top() + region.height() // 2
        template_handle_manual_point(self, x, y)
        return
        
    elif self.template_overlay_mode == "manual_point2":
        x = region.left() + region.width() // 2
        y = region.top() + region.height() // 2
        template_handle_manual_point(self, x, y)
        return
    
    if self.template_overlay_mode == "template_top":
        self.template_top_region = QRect(region)
        self.template_top_image = grab_region(region)
        self.template_top_label.setText(
            f"({region.left()}, {region.top()}) - {region.width()}x{region.height()}"
        )
        self.template_top_label.setStyleSheet("font-weight: bold; color: #388E3C;")
        self.template_log_edit.appendPlainText(f"已截取题号栏顶部: {region}")
        
    elif self.template_overlay_mode == "template_bottom":
        self.template_bottom_region = QRect(region)
        self.template_bottom_image = grab_region(region)
        self.template_bottom_label.setText(
            f"({region.left()}, {region.top()}) - {region.width()}x{region.height()}"
        )
        self.template_bottom_label.setStyleSheet("font-weight: bold; color: #388E3C;")
        self.template_log_edit.appendPlainText(f"已截取题号栏底部: {region}")
        
    elif self.template_overlay_mode == "template_question":
        self.template_question_region = QRect(region)
        self.template_question_image = grab_region(region)
        self.template_question_label.setText(
            f"({region.left()}, {region.top()}) - {region.width()}x{region.height()}"
        )
        self.template_question_label.setStyleSheet("font-weight: bold; color: #388E3C;")
        self.template_log_edit.appendPlainText(f"已截取题目页面: {region}")


def template_build(self: 'MainWindow'):
    self.template_log_edit.appendPlainText("=" * 60)
    self.template_log_edit.appendPlainText("开始建立模板...")
    self.template_log_edit.appendPlainText("=" * 60)
    
    try:
        if self.template_top_image is not None:
            from core.box_ocr_backend import get_box_ocr_backend
            from core.number_card_calibrator import NumberCardCalibrator
            
            ocr_backend = get_box_ocr_backend(self.template_number_ocr_combo.currentData())
            
            region_left = self.template_top_region.left() if self.template_top_region else 0
            region_top = self.template_top_region.top() if self.template_top_region else 0
            section_counts = [
                self.template_single_spin.value(),
                self.template_multi_spin.value(),
                self.template_judge_spin.value(),
            ]
            
            calibrator = NumberCardCalibrator()
            template = calibrator.calibrate_with_counts(
                self.template_top_image,
                self.template_bottom_image,
                ocr_backend,
                section_counts,
                region_left,
                region_top,
            )
            
            self.template_questions = []
            for section in template.get("sections", []):
                self.template_questions.extend(section.get("questions", []))
            
            self.template_log_edit.appendPlainText(f"生成 {len(self.template_questions)} 个题目坐标")
            for section in template.get("sections", []):
                self.template_log_edit.appendPlainText(f"  {section['section_name']}: {len(section['questions'])}题")
        else:
            self.template_log_edit.appendPlainText("未提供截图，将使用占位坐标生成模板")
            self.template_questions = []
        
        if self.template_question_image:
            self.template_log_edit.appendPlainText("正在识别选项坐标...")
            self.template_option_template = _extract_option_template(
                self.template_question_image,
                self.template_question_region,
                backend_name=self.template_option_ocr_combo.currentData(),
            )
            
            options = self.template_option_template.get("options", {})
            choice_options = {
                k: v for k, v in options.items()
                if len(k) == 1 and k.isalpha()
            }
            judge_options = {k: v for k, v in options.items() if k in ["正确", "错误"]}
            
            from core.minimal_option_calibrator import build_option_layout_template, save_option_layout_template
            
            option_layout = build_option_layout_template(
                choice_options if choice_options else None,
                judge_options if judge_options else None
            )
            
            if option_layout:
                save_option_layout_template(option_layout)
                self.template_log_edit.appendPlainText("选项模板已保存到 option_layout_template.json")
            
            self.template_log_edit.appendPlainText(f"选项模板建立完成: {list(options.keys())}")
        
        self._template_update_info_table()
        
        self.template_log_edit.appendPlainText("模板建立完成！")
        QMessageBox.information(self, "成功", f"模板建立完成！共 {len(self.template_questions)} 题")
        
    except Exception as e:
        self.template_log_edit.appendPlainText(f"错误: {e}")
        import traceback
        self.template_log_edit.appendPlainText(traceback.format_exc())
        QMessageBox.critical(self, "错误", f"建立模板失败: {e}")


def _extract_number_boxes(image: Image.Image, ocr_backend, region_left: int, region_top: int) -> List[Dict]:
    from core.box_ocr_backend import detect_text_boxes
    
    boxes = detect_text_boxes(image, ocr_backend)
    
    number_boxes = []
    for box in boxes:
        text = box.get("text", "")
        if text.isdigit():
            number_boxes.append({
                "text": text,
                "number": int(text),
                "x": box.get("x", 0) + region_left,
                "y": box.get("y", 0) + region_top,
                "width": box.get("width", 0),
                "height": box.get("height", 0),
            })
    
    return number_boxes


def _deduplicate_boxes(boxes: List[Dict]) -> List[Dict]:
    unique = {}
    for box in boxes:
        num = box["number"]
        if num not in unique:
            unique[num] = box
    return sorted(unique.values(), key=lambda b: b["number"])


def _generate_questions_from_counts(
    boxes: List[Dict], 
    single_count: int, 
    multi_count: int, 
    judge_count: int
) -> List[Dict]:
    questions = []
    global_index = 1
    
    sections = [
        ("single", "单选题", "single_choice", single_count),
        ("multi", "多选题", "multi_choice", multi_count),
        ("judge", "判断题", "judge", judge_count),
    ]
    
    section_names_display = ["一", "二", "三"]
    
    for section_idx, (section_id, section_name, question_type, count) in enumerate(sections):
        if count == 0:
            continue
        
        display_prefix = section_names_display[section_idx]
        
        for local_no in range(1, count + 1):
            global_id = f"Q{global_index:06d}"
            display_no = f"{display_prefix}-{local_no}"
            
            click_x, click_y, source = _get_question_coordinates(
                boxes, local_no, count, section_idx
            )
            
            questions.append({
                "global_id": global_id,
                "global_index": global_index,
                "section_id": section_id,
                "section_name": section_name,
                "question_type": question_type,
                "local_no": local_no,
                "display_no": display_no,
                "click_x": click_x,
                "click_y": click_y,
                "source": source,
            })
            
            global_index += 1
    
    return questions


def _get_question_coordinates(
    boxes: List[Dict], 
    local_no: int, 
    section_count: int,
    section_idx: int
) -> tuple[int, int, str]:
    if len(boxes) >= 3:
        first_box = boxes[0]
        last_box = boxes[-1]
        
        if len(boxes) >= 2:
            second_box = boxes[1]
            dx = second_box["x"] - first_box["x"]
        else:
            dx = 0
        
        if len(boxes) >= 3:
            next_row_box = None
            for box in boxes[1:]:
                if box["y"] > first_box["y"] + 10:
                    next_row_box = box
                    break
            
            if next_row_box:
                dy = next_row_box["y"] - first_box["y"]
            else:
                dy = 50
        else:
            dy = 50
        
        total_questions = len(boxes)
        if local_no <= total_questions:
            box = boxes[local_no - 1]
            return box["x"], box["y"], "ocr"
        
        ratio = (local_no - 1) / max(section_count - 1, 1)
        x = first_box["x"] + ratio * (last_box["x"] - first_box["x"])
        y = first_box["y"] + ratio * (last_box["y"] - first_box["y"])
        return int(x), int(y), "inferred"
    
    return 0, 0, "unknown"


def _extract_option_template(
    image: Image.Image,
    region: Optional[QRect],
    backend_name: str = "auto",
) -> Dict:
    from core.minimal_option_calibrator import calibrate_options_from_image
    
    region_left = region.left() if region else 0
    region_top = region.top() if region else 0
    
    result = calibrate_options_from_image(
        image,
        region_left,
        region_top,
        backend_name=backend_name,
    )
    
    return {
        "options": result.get("options", {}),
        "region_left": region_left,
        "region_top": region_top,
        "source": result.get("source", "unknown"),
    }


def _template_update_info_table(self: 'MainWindow'):
    self.template_info_table.setRowCount(0)
    
    for question in self.template_questions:
        row = self.template_info_table.rowCount()
        self.template_info_table.insertRow(row)
        
        self.template_info_table.setItem(row, 0, QTableWidgetItem(question["global_id"]))
        self.template_info_table.setItem(row, 1, QTableWidgetItem(question["display_no"]))
        self.template_info_table.setItem(row, 2, QTableWidgetItem(question["section_name"]))
        self.template_info_table.setItem(row, 3, QTableWidgetItem(str(question["click_x"])))
        self.template_info_table.setItem(row, 4, QTableWidgetItem(str(question["click_y"])))


def template_import_answers(self: 'MainWindow'):
    filepath, _ = QFileDialog.getOpenFileName(
        self, "选择答案文件", "", "文本文件;;所有文件")
    if not filepath:
        return
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        self.template_answer_edit.setPlainText(content)
        self.template_log_edit.appendPlainText(f"已导入答案文件: {filepath}")
        
    except Exception as e:
        QMessageBox.critical(self, "错误", f"导入失败: {e}")


def template_paste_answers(self: 'MainWindow'):
    try:
        text = pyperclip.paste()
        self.template_answer_edit.setPlainText(text)
        self.template_log_edit.appendPlainText("已从剪贴板粘贴答案")
    except Exception as e:
        QMessageBox.critical(self, "错误", f"粘贴失败: {e}")


def template_generate_plan(self: 'MainWindow'):
    if not self.template_questions:
        QMessageBox.warning(self, "警告", "请先建立模板")
        return
    
    answer_text = self.template_answer_edit.toPlainText()
    if not answer_text.strip():
        QMessageBox.warning(self, "警告", "请先输入或导入答案")
        return
    
    self.template_log_edit.appendPlainText("=" * 60)
    self.template_log_edit.appendPlainText("开始解析答案...")
    
    self.template_answers = _parse_answers(answer_text, self.template_questions)
    
    self.template_log_edit.appendPlainText(f"解析完成，有效答案 {len(self.template_answers)} 个")
    
    self.template_log_edit.appendPlainText("开始生成点击计划...")
    
    self.template_click_plan = _generate_click_plan(
        self.template_questions,
        self.template_option_template,
        self.template_answers
    )
    
    self._template_update_plan_table()
    
    self.template_log_edit.appendPlainText(f"点击计划生成完成，共 {len(self.template_click_plan)} 项")
    
    with open("click_plan.json", "w", encoding="utf-8") as f:
        json.dump(self.template_click_plan, f, ensure_ascii=False, indent=2)
    
    self.template_log_edit.appendPlainText("已保存到 click_plan.json")
    QMessageBox.information(self, "成功", f"点击计划生成完成！\n共 {len(self.template_click_plan)} 项")


def _parse_answers(answer_text: str, questions: List[Dict]) -> Dict[str, str]:
    import re
    
    answers = {}
    lines = answer_text.strip().split('\n')
    
    question_map = {q["display_no"]: q["global_id"] for q in questions}
    
    question_by_local_single = {}
    question_by_local_multi = {}
    question_by_local_judge = {}
    
    for q in questions:
        local_no = q["local_no"]
        global_id = q["global_id"]
        if q["section_id"] == "single":
            question_by_local_single[str(local_no)] = global_id
        elif q["section_id"] == "multi":
            question_by_local_multi[str(local_no)] = global_id
        elif q["section_id"] == "judge":
            question_by_local_judge[str(local_no)] = global_id
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        patterns = [
            (r'^Q(\d{6})\s+([A-D]+)$', 'global_id'),
            (r'^([一二三])-?(\d+)\s+([A-D]+)$', 'display_no'),
            (r'^(\d+)\s+([A-D]+)$', 'local_no'),
            (r'^([一二三])-?(\d+)\s+(正确|错误|对|错|T|F)$', 'display_no_tf'),
            (r'^(\d+)\s+(正确|错误|对|错|T|F)$', 'local_no_tf'),
        ]
        
        matched = False
        for pattern, pattern_type in patterns:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                if pattern_type == 'global_id':
                    global_id = f"Q{match.group(1)}"
                    answer = match.group(2).upper()
                    answers[global_id] = answer
                    
                elif pattern_type == 'display_no':
                    section_map = {"一": "一", "二": "二", "三": "三"}
                    display_no = f"{section_map[match.group(1)]}-{match.group(2)}"
                    answer = match.group(3).upper()
                    if display_no in question_map:
                        answers[question_map[display_no]] = answer
                        
                elif pattern_type == 'local_no':
                    local_no = match.group(1)
                    answer = match.group(2).upper()
                    if local_no in question_by_local_single:
                        answers[question_by_local_single[local_no]] = answer
                        
                elif pattern_type == 'display_no_tf':
                    section_map = {"一": "一", "二": "二", "三": "三"}
                    display_no = f"{section_map[match.group(1)]}-{match.group(2)}"
                    answer_text = match.group(3).upper()
                    answer = "TRUE" if answer_text in ["正确", "对", "T", "TRUE"] else "FALSE"
                    if display_no in question_map:
                        answers[question_map[display_no]] = answer
                        
                elif pattern_type == 'local_no_tf':
                    local_no = match.group(1)
                    answer_text = match.group(2).upper()
                    answer = "TRUE" if answer_text in ["正确", "对", "T", "TRUE"] else "FALSE"
                    if local_no in question_by_local_judge:
                        answers[question_by_local_judge[local_no]] = answer
                
                matched = True
                break
        
        if not matched:
            pass
    
    return answers


def _generate_click_plan(
    questions: List[Dict],
    option_template: Dict,
    answers: Dict[str, str]
) -> List[Dict]:
    from core.minimal_option_calibrator import load_option_layout_template
    
    click_plan = []
    
    layout_template = load_option_layout_template()
    
    options = option_template.get("options", {})
    
    for question in questions:
        global_id = question["global_id"]
        answer = answers.get(global_id)
        question_type = question["question_type"]
        
        question_click = [question["click_x"], question["click_y"]]
        
        answer_clicks = []
        if answer:
            if question_type == "judge":
                if layout_template and "judge" in layout_template:
                    judge_config = layout_template["judge"]
                    if answer == "TRUE":
                        true_opt = judge_config.get("true_option", {})
                        if true_opt.get("click_x", 0) != 0 or true_opt.get("click_y", 0) != 0:
                            answer_clicks.append([true_opt.get("click_x", 0), true_opt.get("click_y", 0)])
                    elif answer == "FALSE":
                        false_opt = judge_config.get("false_option", {})
                        if false_opt.get("click_x", 0) != 0 or false_opt.get("click_y", 0) != 0:
                            answer_clicks.append([false_opt.get("click_x", 0), false_opt.get("click_y", 0)])
                else:
                    if answer == "TRUE" and "正确" in options:
                        opt = options["正确"]
                        answer_clicks.append([opt.get("click_x", 0), opt.get("click_y", 0)])
                    elif answer == "TRUE" and "T" in options:
                        opt = options["T"]
                        answer_clicks.append([opt.get("click_x", 0), opt.get("click_y", 0)])
                    elif answer == "FALSE" and "错误" in options:
                        opt = options["错误"]
                        answer_clicks.append([opt.get("click_x", 0), opt.get("click_y", 0)])
                    elif answer == "FALSE" and "F" in options:
                        opt = options["F"]
                        answer_clicks.append([opt.get("click_x", 0), opt.get("click_y", 0)])
            else:
                choice_options = None
                if layout_template:
                    if question_type == "single_choice" and "single_choice" in layout_template:
                        choice_options = layout_template["single_choice"].get("options", {})
                    elif question_type == "multi_choice" and "multi_choice" in layout_template:
                        multi_config = layout_template["multi_choice"]
                        if "reuse_from" in multi_config:
                            reuse_from = multi_config["reuse_from"]
                            if reuse_from in layout_template:
                                choice_options = layout_template[reuse_from].get("options", {})
                
                if not choice_options:
                    choice_options = {
                        k: v for k, v in options.items()
                        if len(k) == 1 and k.isalpha()
                    }
                
                for letter in answer:
                    if letter in choice_options:
                        opt = choice_options[letter]
                        answer_clicks.append([opt.get("click_x", 0), opt.get("click_y", 0)])
        
        status = "ready" if answer and answer_clicks else ("no_answer" if not answer else "no_option")
        
        click_plan.append({
            "global_id": global_id,
            "display_no": question["display_no"],
            "question_type": question_type,
            "answer": answer,
            "question_click": question_click,
            "answer_clicks": answer_clicks,
            "status": status,
        })
    
    return click_plan


def _template_update_plan_table(self: 'MainWindow'):
    self.template_plan_table.setRowCount(0)
    
    for item in self.template_click_plan:
        row = self.template_plan_table.rowCount()
        self.template_plan_table.insertRow(row)
        
        self.template_plan_table.setItem(row, 0, QTableWidgetItem(item["global_id"]))
        self.template_plan_table.setItem(row, 1, QTableWidgetItem(item["display_no"]))
        self.template_plan_table.setItem(row, 2, QTableWidgetItem(str(item.get("answer", ""))))
        self.template_plan_table.setItem(row, 3, QTableWidgetItem(str(item["question_click"])))
        self.template_plan_table.setItem(row, 4, QTableWidgetItem(str(item["answer_clicks"])))
        
        status = item["status"]
        status_item = QTableWidgetItem(status)
        
        if status != "ready":
            from PySide6.QtGui import QColor
            status_item.setBackground(QColor(255, 255, 0))
        
        self.template_plan_table.setItem(row, 5, status_item)


def template_save(self: 'MainWindow'):
    if not self.template_questions:
        QMessageBox.warning(self, "警告", "请先建立模板")
        return
    
    try:
        template_data = {
            "questions": self.template_questions,
            "option_template": self.template_option_template,
        }
        
        with open("number_card_template.json", "w", encoding="utf-8") as f:
            json.dump(template_data, f, ensure_ascii=False, indent=2)
        
        self.template_log_edit.appendPlainText("模板已保存到 number_card_template.json")
        QMessageBox.information(self, "成功", "模板保存成功！")
        
    except Exception as e:
        QMessageBox.critical(self, "错误", f"保存失败: {e}")


def template_select_manual_point1(self: 'MainWindow'):
    self.template_overlay_mode = "manual_point1"
    self._start_selection("请点击第一个选项位置")


def template_select_manual_point2(self: 'MainWindow'):
    self.template_overlay_mode = "manual_point2"
    self._start_selection("请点击第二个选项位置")


def template_handle_manual_point(self: 'MainWindow', x: int, y: int):
    if self.template_overlay_mode == "manual_point1":
        self.template_manual_point1 = (x, y)
        self.template_manual_point1_label.setText(f"({x}, {y})")
        self.template_manual_point1_label.setStyleSheet("color: #388E3C; font-weight: bold;")
        self.template_log_edit.appendPlainText(f"第一点坐标: ({x}, {y})")
        
    elif self.template_overlay_mode == "manual_point2":
        self.template_manual_point2 = (x, y)
        self.template_manual_point2_label.setText(f"({x}, {y})")
        self.template_manual_point2_label.setStyleSheet("color: #388E3C; font-weight: bold;")
        self.template_log_edit.appendPlainText(f"第二点坐标: ({x}, {y})")


def template_apply_manual_calibration(self: 'MainWindow'):
    if not self.template_manual_point1 or not self.template_manual_point2:
        QMessageBox.warning(self, "警告", "请先选取两个坐标点")
        return
    
    label1 = self.template_manual_label1.currentText()
    label2 = self.template_manual_label2.currentText()
    
    x1, y1 = self.template_manual_point1
    x2, y2 = self.template_manual_point2
    
    self.template_log_edit.appendPlainText("=" * 60)
    self.template_log_edit.appendPlainText("应用手动校准...")
    self.template_log_edit.appendPlainText(f"第一点: {label1} @ ({x1}, {y1})")
    self.template_log_edit.appendPlainText(f"第二点: {label2} @ ({x2}, {y2})")
    
    try:
        from core.minimal_option_calibrator import (
            calibrate_from_manual_points,
            build_option_layout_template,
            save_option_layout_template
        )
        
        point1 = (x1, y1, label1)
        point2 = (x2, y2, label2)
        
        result = calibrate_from_manual_points(point1, point2)
        options = result.get("options", {})
        
        self.template_log_edit.appendPlainText(f"推断选项: {list(options.keys())}")
        
        choice_options = {
            k: v for k, v in options.items()
            if len(k) == 1 and k.isalpha()
        }
        judge_options = {k: v for k, v in options.items() if k in ["正确", "错误"]}
        
        option_layout = build_option_layout_template(
            choice_options if choice_options else None,
            judge_options if judge_options else None
        )
        
        if option_layout:
            save_option_layout_template(option_layout)
            self.template_log_edit.appendPlainText("选项模板已保存到 option_layout_template.json")
            
            self.template_option_template = {"options": options}
            
            QMessageBox.information(self, "成功", "手动校准已应用！")
        else:
            QMessageBox.warning(self, "警告", "无法生成选项模板")
            
    except Exception as e:
        self.template_log_edit.appendPlainText(f"错误: {e}")
        import traceback
        self.template_log_edit.appendPlainText(traceback.format_exc())
        QMessageBox.critical(self, "错误", f"应用手动校准失败: {e}")
