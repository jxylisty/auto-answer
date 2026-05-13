from typing import TYPE_CHECKING
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QComboBox, QSpinBox, QDoubleSpinBox, QTableWidget, 
    QTableWidgetItem, QPlainTextEdit, QLineEdit, QCheckBox,
    QFrame, QSplitter, QScrollArea, QHeaderView, QProgressBar,
    QFileDialog, QMessageBox, QAbstractSpinBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap

if TYPE_CHECKING:
    from ui.main_window import MainWindow


def build_template_tab(self: 'MainWindow'):
    self.template_tab = QWidget()
    self.tabs.insertTab(1, self.template_tab, "模板校准")
    
    root_layout = QVBoxLayout(self.template_tab)
    root_layout.setContentsMargins(18, 18, 18, 18)
    root_layout.setSpacing(14)
    
    flow_label = QLabel(
        "向导模式：① 截左侧题号栏 → ② 截右侧题目 → ③ 自动建立模板 → ④ 预览调整"
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
    
    self.select_template_top_btn = QPushButton("① 截左侧题号栏顶部")
    self.select_template_bottom_btn = QPushButton("截左侧题号栏底部")
    self.select_template_question_btn = QPushButton("② 截右侧当前题页面")
    self.build_template_btn = QPushButton("③ 自动建立模板")
    self.save_template_btn = QPushButton("④ 保存模板")
    self.preview_template_btn = QPushButton("预览模板")
    self.load_template_btn = QPushButton("加载模板")
    
    self.build_template_btn.setObjectName("primaryLarge")
    self.save_template_btn.setObjectName("primaryLarge")
    self.build_template_btn.setMinimumHeight(56)
    self.save_template_btn.setMinimumHeight(56)
    self.build_template_btn.setStyleSheet("font-size: 18px; font-weight: bold;")
    self.save_template_btn.setStyleSheet("font-size: 18px; font-weight: bold;")
    
    self.template_top_label = QLabel("未设置")
    self.template_top_label.setStyleSheet("font-weight: bold; color: #D32F2F; font-size: 16px;")
    self.template_bottom_label = QLabel("未设置")
    self.template_bottom_label.setStyleSheet("font-weight: bold; color: #D32F2F; font-size: 16px;")
    self.template_question_label = QLabel("未设置")
    self.template_question_label.setStyleSheet("font-weight: bold; color: #D32F2F; font-size: 16px;")
    
    self.template_offset_x_spin = QSpinBox()
    self.template_offset_y_spin = QSpinBox()
    self._configure_spinbox(self.template_offset_x_spin, -200, 200, 0, 1)
    self._configure_spinbox(self.template_offset_y_spin, -200, 200, 0, 1)
    
    self.template_info_table = QTableWidget(0, 4)
    self.template_info_table.setHorizontalHeaderLabels(["题号", "X", "Y", "来源"])
    self.template_info_table.verticalHeader().setVisible(False)
    self.template_info_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    self.template_info_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    self.template_info_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    
    self.template_preview_label = QLabel("模板预览")
    self.template_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.template_preview_label.setMinimumHeight(400)
    self.template_preview_label.setStyleSheet(
        "background: #232833; border: 1px solid #313949; border-radius: 14px;"
    )
    
    self.template_log_edit = QPlainTextEdit()
    self.template_log_edit.setReadOnly(True)
    self.template_log_edit.setPlaceholderText("模板校准日志会显示在这里...")
    
    self.select_template_top_btn.clicked.connect(self.select_template_top_region)
    self.select_template_bottom_btn.clicked.connect(self.select_template_bottom_region)
    self.select_template_question_btn.clicked.connect(self.select_template_question_region)
    self.build_template_btn.clicked.connect(self.build_template)
    self.save_template_btn.clicked.connect(self.save_template)
    self.preview_template_btn.clicked.connect(self.preview_template)
    self.load_template_btn.clicked.connect(self.load_template)
    self.template_offset_x_spin.valueChanged.connect(self.apply_template_offset)
    self.template_offset_y_spin.valueChanged.connect(self.apply_template_offset)
    
    card, layout = self._make_card("第一步：截取题号栏")
    layout.addWidget(QLabel("顶部截图："))
    layout.addWidget(self.template_top_label)
    layout.addWidget(self.select_template_top_btn)
    layout.addSpacing(8)
    layout.addWidget(QLabel("底部截图（可选）："))
    layout.addWidget(self.template_bottom_label)
    layout.addWidget(self.select_template_bottom_btn)
    left_layout.addWidget(card)
    
    card, layout = self._make_card("第二步：截取题目页面")
    layout.addWidget(QLabel("题目截图："))
    layout.addWidget(self.template_question_label)
    layout.addWidget(self.select_template_question_btn)
    left_layout.addWidget(card)
    
    card, layout = self._make_card("第三步：建立模板")
    layout.addWidget(self.build_template_btn)
    build_row = QHBoxLayout()
    build_row.setSpacing(10)
    build_row.addWidget(self.save_template_btn)
    build_row.addWidget(self.preview_template_btn)
    build_row.addWidget(self.load_template_btn)
    layout.addLayout(build_row)
    layout.addSpacing(12)
    layout.addWidget(QLabel("坐标微调："))
    offset_row = QHBoxLayout()
    offset_row.setSpacing(10)
    offset_row.addWidget(QLabel("X偏移："))
    offset_row.addWidget(self.template_offset_x_spin)
    offset_row.addWidget(QLabel("Y偏移："))
    offset_row.addWidget(self.template_offset_y_spin)
    layout.addLayout(offset_row)
    left_layout.addWidget(card)
    
    card, layout = self._make_card("模板信息")
    layout.addWidget(self.template_info_table)
    left_layout.addWidget(card)
    
    right_layout.addWidget(self.template_preview_label, 2)
    right_layout.addWidget(self.template_log_edit, 1)


def build_collect_questions_tab(self: 'MainWindow'):
    self.collect_questions_tab = QWidget()
    self.tabs.insertTab(2, self.collect_questions_tab, "题目采集")
    
    root_layout = QVBoxLayout(self.collect_questions_tab)
    root_layout.setContentsMargins(18, 18, 18, 18)
    root_layout.setSpacing(14)
    
    flow_label = QLabel(
        "向导模式：① 选择采集模式 → ② 快速采集 → ③ 导出题目"
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
    
    self.collect_mode_combo = QComboBox()
    self.collect_mode_combo.addItem("精确模式 - 每题OCR题干和选项", "precise")
    self.collect_mode_combo.addItem("快速模式 - 题干OCR+选项模板 (推荐)", "fast")
    self.collect_mode_combo.addItem("极速模式 - 全部使用模板", "turbo")
    self.collect_mode_combo.setCurrentIndex(1)
    
    self.quick_collect_btn = QPushButton("② 快速采集")
    self.stop_quick_collect_btn = QPushButton("停止采集")
    self.export_questions_btn = QPushButton("③ 导出题目")
    self.copy_all_questions_btn = QPushButton("复制全部题目")
    
    self.quick_collect_btn.setObjectName("primaryLarge")
    self.stop_quick_collect_btn.setObjectName("dangerLarge")
    self.quick_collect_btn.setMinimumHeight(56)
    self.stop_quick_collect_btn.setMinimumHeight(56)
    self.quick_collect_btn.setStyleSheet("font-size: 18px; font-weight: bold;")
    self.stop_quick_collect_btn.setStyleSheet("font-size: 18px; font-weight: bold;")
    
    self.collect_questions_progress = QProgressBar()
    self.collect_questions_progress.setMinimum(0)
    self.collect_questions_progress.setMaximum(100)
    self.collect_questions_progress.setValue(0)
    self.collect_questions_progress.setTextVisible(True)
    self.collect_questions_progress.setFormat("%p% - %v/%m")
    
    self.questions_table = QTableWidget(0, 7)
    self.questions_table.setHorizontalHeaderLabels([
        "global_id", "display_no", "题型", "题干", "图片", "OCR后端", "状态"
    ])
    self.questions_table.verticalHeader().setVisible(False)
    self.questions_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    self.questions_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    self.questions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    
    self.questions_log_edit = QPlainTextEdit()
    self.questions_log_edit.setReadOnly(True)
    self.questions_log_edit.setPlaceholderText("采集日志会显示在这里...")
    
    self.quick_collect_btn.clicked.connect(self.quick_collect)
    self.stop_quick_collect_btn.clicked.connect(self.stop_collection)
    self.export_questions_btn.clicked.connect(self.export_questions)
    self.copy_all_questions_btn.clicked.connect(self.copy_all_questions)
    self.collect_mode_combo.currentIndexChanged.connect(self.set_collect_mode)
    
    card, layout = self._make_card("第一步：选择采集模式")
    layout.addWidget(QLabel("采集模式："))
    layout.addWidget(self.collect_mode_combo)
    left_layout.addWidget(card)
    
    card, layout = self._make_card("第二步：快速采集")
    layout.addWidget(self.quick_collect_btn)
    layout.addWidget(self.stop_quick_collect_btn)
    layout.addSpacing(12)
    layout.addWidget(QLabel("进度："))
    layout.addWidget(self.collect_questions_progress)
    left_layout.addWidget(card)
    
    card, layout = self._make_card("第三步：导出题目")
    export_row = QHBoxLayout()
    export_row.setSpacing(10)
    export_row.addWidget(self.export_questions_btn)
    export_row.addWidget(self.copy_all_questions_btn)
    layout.addLayout(export_row)
    left_layout.addWidget(card)
    
    right_layout.addWidget(self.questions_table, 2)
    right_layout.addWidget(self.questions_log_edit, 1)


def build_answer_plan_tab(self: 'MainWindow'):
    self.answer_plan_tab = QWidget()
    self.tabs.insertTab(3, self.answer_plan_tab, "答案与点击计划")
    
    root_layout = QVBoxLayout(self.answer_plan_tab)
    root_layout.setContentsMargins(18, 18, 18, 18)
    root_layout.setSpacing(14)
    
    flow_label = QLabel(
        "向导模式：① 导入答案 → ② 生成点击计划 → ③ 预览测试 → ④ 执行点击"
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
    
    self.import_answers_btn = QPushButton("① 导入答案")
    self.paste_answers_btn = QPushButton("粘帖答案")
    self.parse_answers_btn = QPushButton("解析答案")
    self.generate_plan_btn = QPushButton("② 生成点击计划")
    self.preview_plan_btn = QPushButton("预览点击计划")
    self.dry_run_btn = QPushButton("③ Dry-Run 测试")
    self.execute_plan_btn = QPushButton("④ 执行点击")
    self.stop_execute_btn = QPushButton("停止执行")
    self.export_plan_btn = QPushButton("导出计划")
    
    self.execute_plan_btn.setObjectName("primaryLarge")
    self.stop_execute_btn.setObjectName("dangerLarge")
    self.execute_plan_btn.setMinimumHeight(56)
    self.stop_execute_btn.setMinimumHeight(56)
    self.execute_plan_btn.setStyleSheet("font-size: 18px; font-weight: bold;")
    self.stop_execute_btn.setStyleSheet("font-size: 18px; font-weight: bold;")
    
    self.answers_input_edit = QPlainTextEdit()
    self.answers_input_edit.setPlaceholderText(
        "在此输入答案，支持多种格式：\n"
        "1 B\n"
        "2 A\n"
        "二-1 ABC\n"
        "三-1 正确\n"
        "Q000021 AD"
    )
    self.answers_input_edit.setMaximumHeight(150)
    
    self.answers_table = QTableWidget(0, 4)
    self.answers_table.setHorizontalHeaderLabels(["题号", "答案", "类型", "状态"])
    self.answers_table.verticalHeader().setVisible(False)
    self.answers_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    self.answers_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    self.answers_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    
    self.plan_table = QTableWidget(0, 6)
    self.plan_table.setHorizontalHeaderLabels([
        "global_id", "display_no", "答案", "题号坐标", "选项坐标", "状态"
    ])
    self.plan_table.verticalHeader().setVisible(False)
    self.plan_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    self.plan_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    self.plan_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    
    self.invalid_answers_label = QLabel("无效答案：无")
    self.invalid_answers_label.setWordWrap(True)
    self.invalid_answers_label.setStyleSheet("color: #D32F2F;")
    
    self.plan_log_edit = QPlainTextEdit()
    self.plan_log_edit.setReadOnly(True)
    self.plan_log_edit.setPlaceholderText("点击计划日志会显示在这里...")
    
    self.import_answers_btn.clicked.connect(self.import_answers)
    self.paste_answers_btn.clicked.connect(self.paste_answers)
    self.parse_answers_btn.clicked.connect(self.parse_answers)
    self.generate_plan_btn.clicked.connect(self.generate_click_plan)
    self.preview_plan_btn.clicked.connect(self.preview_click_plan)
    self.dry_run_btn.clicked.connect(self.dry_run_click_plan)
    self.execute_plan_btn.clicked.connect(self.execute_click_plan)
    self.stop_execute_btn.clicked.connect(self.stop_execute_plan)
    self.export_plan_btn.clicked.connect(self.export_click_plan)
    
    card, layout = self._make_card("第一步：导入答案")
    import_row = QHBoxLayout()
    import_row.setSpacing(10)
    import_row.addWidget(self.import_answers_btn)
    import_row.addWidget(self.paste_answers_btn)
    import_row.addWidget(self.parse_answers_btn)
    layout.addLayout(import_row)
    layout.addSpacing(8)
    layout.addWidget(self.answers_input_edit)
    layout.addSpacing(8)
    layout.addWidget(self.answers_table)
    layout.addSpacing(8)
    layout.addWidget(self.invalid_answers_label)
    left_layout.addWidget(card)
    
    card, layout = self._make_card("第二步：生成点击计划")
    layout.addWidget(self.generate_plan_btn)
    layout.addWidget(self.preview_plan_btn)
    left_layout.addWidget(card)
    
    card, layout = self._make_card("第三步：执行点击")
    layout.addWidget(self.dry_run_btn)
    execute_row = QHBoxLayout()
    execute_row.setSpacing(10)
    execute_row.addWidget(self.execute_plan_btn)
    execute_row.addWidget(self.stop_execute_btn)
    layout.addLayout(execute_row)
    layout.addSpacing(8)
    layout.addWidget(self.export_plan_btn)
    left_layout.addWidget(card)
    
    right_layout.addWidget(self.plan_table, 2)
    right_layout.addWidget(self.plan_log_edit, 1)
