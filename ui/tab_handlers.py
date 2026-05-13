import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Dict, List
from PIL import Image
import pyperclip

from PySide6.QtWidgets import QFileDialog, QMessageBox
from PySide6.QtCore import Qt, QRect

if TYPE_CHECKING:
    from ui.main_window import MainWindow


def init_template_attributes(self: 'MainWindow'):
    from core.number_card_calibrator import NumberCardCalibrator
    from core.screenshot_auto_fixer import ScreenshotAutoFixer
    
    self.number_card_calibrator = NumberCardCalibrator()
    self.screenshot_auto_fixer = ScreenshotAutoFixer()
    self.template_top_image: Optional[Image.Image] = None
    self.template_bottom_image: Optional[Image.Image] = None
    self.template_question_image: Optional[Image.Image] = None
    self.template_top_region: Optional[QRect] = None
    self.template_bottom_region: Optional[QRect] = None
    self.template_question_region: Optional[QRect] = None
    self.number_template: Dict = {}
    self.option_template: Dict = {}
    self.template_offset_x = 0
    self.template_offset_y = 0


def init_collect_attributes(self: 'MainWindow'):
    self.collect_mode = "fast"
    self.collected_questions: List[Dict] = []


def init_answer_attributes(self: 'MainWindow'):
    from core.answer_importer import AnswerImporter
    from core.click_plan_builder import ClickPlanBuilder
    
    self.answer_importer = AnswerImporter()
    self.click_plan_builder = ClickPlanBuilder()
    self.user_answers: Dict[str, str] = {}
    self.click_plan: List[Dict] = []
    self.is_executing = False


def select_template_top_region(self: 'MainWindow'):
    self.overlay_mode = "template_top"
    self._start_selection("请框选左侧题号栏顶部区域")


def select_template_bottom_region(self: 'MainWindow'):
    self.overlay_mode = "template_bottom"
    self._start_selection("请框选左侧题号栏底部区域")


def select_template_question_region(self: 'MainWindow'):
    self.overlay_mode = "template_question"
    self._start_selection("请框选右侧当前题页面区域")


def handle_template_region_selected(self: 'MainWindow', region: QRect):
    from core.screenshot import grab_region
    from core.image_utils import pil_image_to_pixmap
    
    if self.overlay_mode == "template_top":
        self.template_top_region = region
        self.template_top_image = grab_region(region)
        self.template_top_label.setText(
            f"({region.left()}, {region.top()}) - {region.width()}x{region.height()}"
        )
        self.template_top_label.setStyleSheet("font-weight: bold; color: #388E3C; font-size: 16px;")
        self.template_log_edit.appendPlainText(f"已截取题号栏顶部: {region}")
        
    elif self.overlay_mode == "template_bottom":
        self.template_bottom_region = region
        self.template_bottom_image = grab_region(region)
        self.template_bottom_label.setText(
            f"({region.left()}, {region.top()}) - {region.width()}x{region.height()}"
        )
        self.template_bottom_label.setStyleSheet("font-weight: bold; color: #388E3C; font-size: 16px;")
        self.template_log_edit.appendPlainText(f"已截取题号栏底部: {region}")
        
    elif self.overlay_mode == "template_question":
        self.template_question_region = region
        self.template_question_image = grab_region(region)
        self.template_question_label.setText(
            f"({region.left()}, {region.top()}) - {region.width()}x{region.height()}"
        )
        self.template_question_label.setStyleSheet("font-weight: bold; color: #388E3C; font-size: 16px;")
        self.template_log_edit.appendPlainText(f"已截取题目页面: {region}")


def build_template(self: 'MainWindow'):
    if self.template_top_image is None:
        QMessageBox.warning(self, "警告", "请先截取左侧题号栏顶部区域")
        return
    
    self.template_log_edit.appendPlainText("=" * 60)
    self.template_log_edit.appendPlainText("开始建立模板...")
    self.template_log_edit.appendPlainText("=" * 60)
    
    try:
        from core.box_ocr_backend import get_box_ocr_backend
        from core.multi_ocr_manager import get_ocr_manager
        
        ocr_backend = get_box_ocr_backend()
        
        region_left = self.template_top_region.left() if self.template_top_region else 0
        region_top = self.template_top_region.top() if self.template_top_region else 0
        
        self.number_template = self.number_card_calibrator.calibrate_from_screenshots(
            self.template_top_image,
            self.template_bottom_image,
            ocr_backend,
            region_left,
            region_top
        )
        
        self.template_log_edit.appendPlainText(f"题号模板建立完成，共 {self.number_template.get('total_questions', 0)} 题")
        
        if self.template_question_image:
            self.template_log_edit.appendPlainText("正在识别选项坐标...")
            self.option_template = self._extract_option_template(self.template_question_image)
            self.template_log_edit.appendPlainText(f"选项模板建立完成")
        
        self._update_template_info_table()
        
        QMessageBox.information(self, "成功", "模板建立完成！")
        
    except Exception as e:
        self.template_log_edit.appendPlainText(f"错误: {e}")
        QMessageBox.critical(self, "错误", f"建立模板失败: {e}")


def save_template(self: 'MainWindow'):
    if not self.number_template:
        QMessageBox.warning(self, "警告", "请先建立模板")
        return
    
    try:
        with open("number_card_template.json", "w", encoding="utf-8") as f:
            json.dump(self.number_template, f, ensure_ascii=False, indent=2)
        
        if self.option_template:
            with open("option_layout_template.json", "w", encoding="utf-8") as f:
                json.dump(self.option_template, f, ensure_ascii=False, indent=2)
        
        self.template_log_edit.appendPlainText("模板已保存到 number_card_template.json 和 option_layout_template.json")
        QMessageBox.information(self, "成功", "模板保存成功！")
        
    except Exception as e:
        QMessageBox.critical(self, "错误", f"保存模板失败: {e}")


def load_template(self: 'MainWindow'):
    try:
        template_path = Path("number_card_template.json")
        if not template_path.exists():
            QMessageBox.warning(self, "警告", "模板文件不存在")
            return
        
        with open(template_path, "r", encoding="utf-8") as f:
            self.number_template = json.load(f)
        
        option_path = Path("option_layout_template.json")
        if option_path.exists():
            with open(option_path, "r", encoding="utf-8") as f:
                self.option_template = json.load(f)
        
        self._update_template_info_table()
        
        self.template_log_edit.appendPlainText(f"已加载模板，共 {self.number_template.get('total_questions', 0)} 题")
        QMessageBox.information(self, "成功", "模板加载成功！")
        
    except Exception as e:
        QMessageBox.critical(self, "错误", f"加载模板失败: {e}")


def preview_template(self: 'MainWindow'):
    if not self.number_template:
        QMessageBox.warning(self, "警告", "请先建立模板")
        return
    
    if self.template_top_image is None:
        QMessageBox.warning(self, "警告", "没有预览图片")
        return
    
    from core.image_utils import pil_image_to_pixmap
    from PySide6.QtGui import QPainter, QPen, QColor, QFont
    
    pixmap = pil_image_to_pixmap(self.template_top_image)
    painter = QPainter(pixmap)
    
    pen = QPen(QColor(255, 0, 0), 3)
    painter.setPen(pen)
    font = QFont()
    font.setPointSize(12)
    font.setBold(True)
    painter.setFont(font)
    
    offset_x = self.template_offset_x_spin.value()
    offset_y = self.template_offset_y_spin.value()
    
    sections = self.number_template.get("sections", [])
    for section in sections:
        for question in section.get("questions", []):
            x = question.get("click_x", 0) + offset_x
            y = question.get("click_y", 0) + offset_y
            source = question.get("source", "ocr")
            
            if source == "inferred":
                pen.setColor(QColor(255, 165, 0))
            else:
                pen.setColor(QColor(255, 0, 0))
            painter.setPen(pen)
            
            painter.drawEllipse(x - 10, y - 10, 20, 20)
            painter.drawText(x + 15, y, question.get("display_no", ""))
    
    painter.end()
    
    self.template_preview_label.setPixmap(pixmap)
    self.template_log_edit.appendPlainText("模板预览已更新")


def apply_template_offset(self: 'MainWindow'):
    self.template_offset_x = self.template_offset_x_spin.value()
    self.template_offset_y = self.template_offset_y_spin.value()
    
    if self.number_template:
        self.preview_template()


def set_collect_mode(self: 'MainWindow'):
    self.collect_mode = self.collect_mode_combo.currentData()
    self.questions_log_edit.appendPlainText(f"采集模式设置为: {self.collect_mode}")


def quick_collect(self: 'MainWindow'):
    if not self.number_template:
        QMessageBox.warning(self, "警告", "请先建立或加载模板")
        return
    
    self.questions_log_edit.appendPlainText("=" * 60)
    self.questions_log_edit.appendPlainText(f"开始快速采集，模式: {self.collect_mode}")
    self.questions_log_edit.appendPlainText("=" * 60)
    
    self.collected_questions = []
    self.questions_table.setRowCount(0)
    
    sections = self.number_template.get("sections", [])
    total_questions = sum(len(s.get("questions", [])) for s in sections)
    
    self.collect_questions_progress.setMaximum(total_questions)
    self.collect_questions_progress.setValue(0)
    
    current_idx = 0
    for section in sections:
        for question in section.get("questions", []):
            current_idx += 1
            self.collect_questions_progress.setValue(current_idx)
            
            global_id = question.get("global_id", "")
            display_no = question.get("display_no", "")
            question_type = question.get("question_type", "single_choice")
            click_x = question.get("click_x", 0) + self.template_offset_x
            click_y = question.get("click_y", 0) + self.template_offset_y
            
            self.questions_log_edit.appendPlainText(f"采集 {display_no} ({global_id})...")
            
            try:
                question_data = self._collect_single_question(
                    global_id, display_no, question_type, click_x, click_y
                )
                self.collected_questions.append(question_data)
                self._add_question_to_table(question_data)
                
            except Exception as e:
                self.questions_log_edit.appendPlainText(f"  错误: {e}")
    
    self.questions_log_edit.appendPlainText(f"采集完成，共 {len(self.collected_questions)} 题")
    QMessageBox.information(self, "完成", f"采集完成，共 {len(self.collected_questions)} 题")


def export_questions(self: 'MainWindow'):
    if not self.collected_questions:
        QMessageBox.warning(self, "警告", "没有可导出的题目")
        return
    
    format_choice = QMessageBox.question(
        self, "选择格式",
        "导出为 JSON 格式？\n\n是 = JSON\n否 = CSV",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
    )
    
    if format_choice == QMessageBox.StandardButton.Cancel:
        return
    
    try:
        if format_choice == QMessageBox.StandardButton.Yes:
            filepath = "questions.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.collected_questions, f, ensure_ascii=False, indent=2)
        else:
            filepath = "questions.csv"
            with open(filepath, "w", encoding="utf-8", newline="") as f:
                import csv
                writer = csv.DictWriter(f, fieldnames=[
                    "global_id", "display_no", "question_type", "stem_text", "image_path", "ocr_backend", "status"
                ])
                writer.writeheader()
                writer.writerows(self.collected_questions)
        
        self.questions_log_edit.appendPlainText(f"题目已导出到 {filepath}")
        QMessageBox.information(self, "成功", f"导出成功！\n{filepath}")
        
    except Exception as e:
        QMessageBox.critical(self, "错误", f"导出失败: {e}")


def copy_all_questions(self: 'MainWindow'):
    if not self.collected_questions:
        QMessageBox.warning(self, "警告", "没有可复制的题目")
        return
    
    text = "\n\n".join([
        f"{q.get('display_no', '')}\n{q.get('stem_text', '')}"
        for q in self.collected_questions
    ])
    
    pyperclip.copy(text)
    QMessageBox.information(self, "成功", "题目已复制到剪贴板")


def import_answers(self: 'MainWindow'):
    filepath, _ = QFileDialog.getOpenFileName(
        self, "选择答案文件", "", "文本文件 (*.txt);;所有文件 (*)"
    )
    
    if not filepath:
        return
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        self.answers_input_edit.setPlainText(content)
        self.plan_log_edit.appendPlainText(f"已导入答案文件: {filepath}")
        
    except Exception as e:
        QMessageBox.critical(self, "错误", f"导入失败: {e}")


def paste_answers(self: 'MainWindow'):
    try:
        text = pyperclip.paste()
        self.answers_input_edit.setPlainText(text)
        self.plan_log_edit.appendPlainText("已从剪贴板粘贴答案")
    except Exception as e:
        QMessageBox.critical(self, "错误", f"粘贴失败: {e}")


def parse_answers(self: 'MainWindow'):
    text = self.answers_input_edit.toPlainText()
    
    if not text.strip():
        QMessageBox.warning(self, "警告", "请先输入答案")
        return
    
    self.plan_log_edit.appendPlainText("=" * 60)
    self.plan_log_edit.appendPlainText("开始解析答案...")
    self.plan_log_edit.appendPlainText("=" * 60)
    
    self.user_answers = self.answer_importer.import_from_text(text)
    
    self.answers_table.setRowCount(0)
    for question_id, answer in self.user_answers.items():
        row = self.answers_table.rowCount()
        self.answers_table.insertRow(row)
        
        self.answers_table.setItem(row, 0, QTableWidgetItem(question_id))
        self.answers_table.setItem(row, 1, QTableWidgetItem(answer))
        
        if len(answer) == 1:
            q_type = "单选题"
        elif len(answer) > 1:
            q_type = "多选题"
        else:
            q_type = "未知"
        
        self.answers_table.setItem(row, 2, QTableWidgetItem(q_type))
        self.answers_table.setItem(row, 3, QTableWidgetItem("有效"))
    
    invalid_count = len(self.answer_importer.invalid_answers)
    if invalid_count > 0:
        invalid_text = "无效答案：\n" + "\n".join([
            f"{line} - {reason}" for line, reason in self.answer_importer.invalid_answers
        ])
        self.invalid_answers_label.setText(invalid_text)
    else:
        self.invalid_answers_label.setText("无效答案：无")
    
    self.plan_log_edit.appendPlainText(f"解析完成，有效答案 {len(self.user_answers)} 个，无效答案 {invalid_count} 个")


def generate_click_plan(self: 'MainWindow'):
    if not self.number_template:
        QMessageBox.warning(self, "警告", "请先建立或加载模板")
        return
    
    if not self.user_answers:
        QMessageBox.warning(self, "警告", "请先解析答案")
        return
    
    self.plan_log_edit.appendPlainText("=" * 60)
    self.plan_log_edit.appendPlainText("开始生成点击计划...")
    self.plan_log_edit.appendPlainText("=" * 60)
    
    offset_x = self.template_offset_x_spin.value()
    offset_y = self.template_offset_y_spin.value()
    
    self.click_plan = self.click_plan_builder.build_plan(
        self.number_template,
        self.option_template,
        self.user_answers,
        offset_x,
        offset_y
    )
    
    self._update_plan_table()
    
    self.plan_log_edit.appendPlainText(f"点击计划生成完成，共 {len(self.click_plan)} 项")


def preview_click_plan(self: 'MainWindow'):
    if not self.click_plan:
        QMessageBox.warning(self, "警告", "请先生成点击计划")
        return
    
    if self.template_top_image is None:
        QMessageBox.warning(self, "警告", "没有预览图片")
        return
    
    from core.image_utils import pil_image_to_pixmap
    from PySide6.QtGui import QPainter, QPen, QColor, QFont
    
    pixmap = pil_image_to_pixmap(self.template_top_image)
    painter = QPainter(pixmap)
    
    pen = QPen(QColor(0, 255, 0), 3)
    painter.setPen(pen)
    font = QFont()
    font.setPointSize(12)
    font.setBold(True)
    painter.setFont(font)
    
    for item in self.click_plan:
        question_click = item.get("question_click", [])
        if len(question_click) >= 2:
            x, y = question_click[0], question_click[1]
            painter.drawEllipse(x - 8, y - 8, 16, 16)
            painter.drawText(x + 12, y, item.get("display_no", ""))
        
        answer_clicks = item.get("answer_clicks", [])
        for click in answer_clicks:
            if len(click) >= 2:
                ax, ay = click[0], click[1]
                pen.setColor(QColor(255, 0, 0))
                painter.setPen(pen)
                painter.drawEllipse(ax - 6, ay - 6, 12, 12)
    
    painter.end()
    
    self.template_preview_label.setPixmap(pixmap)
    self.plan_log_edit.appendPlainText("点击计划预览已更新")


def dry_run_click_plan(self: 'MainWindow'):
    if not self.click_plan:
        QMessageBox.warning(self, "警告", "请先生成点击计划")
        return
    
    import pyautogui
    
    self.plan_log_edit.appendPlainText("=" * 60)
    self.plan_log_edit.appendPlainText("开始 Dry-Run 测试（只移动鼠标，不点击）...")
    self.plan_log_edit.appendPlainText("=" * 60)
    
    for idx, item in enumerate(self.click_plan, start=1):
        if item.get("status") != "ready":
            continue
        
        display_no = item.get("display_no", "")
        question_click = item.get("question_click", [])
        
        if len(question_click) >= 2:
            x, y = question_click[0], question_click[1]
            self.plan_log_edit.appendPlainText(f"{idx}. {display_no}: 移动到 ({x}, {y})")
            pyautogui.moveTo(x, y, duration=0.3)
            time.sleep(0.5)
        
        answer_clicks = item.get("answer_clicks", [])
        for click in answer_clicks:
            if len(click) >= 2:
                ax, ay = click[0], click[1]
                self.plan_log_edit.appendPlainText(f"   选项: 移动到 ({ax}, {ay})")
                pyautogui.moveTo(ax, ay, duration=0.2)
                time.sleep(0.3)
    
    self.plan_log_edit.appendPlainText("Dry-Run 测试完成")


def execute_click_plan(self: 'MainWindow'):
    if not self.click_plan:
        QMessageBox.warning(self, "警告", "请先生成点击计划")
        return
    
    reply = QMessageBox.question(
        self, "确认",
        "确定要执行点击计划吗？\n\n只会执行 status=ready 的项目。",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    
    if reply != QMessageBox.StandardButton.Yes:
        return
    
    import pyautogui
    
    self.is_executing = True
    self.plan_log_edit.appendPlainText("=" * 60)
    self.plan_log_edit.appendPlainText("开始执行点击计划...")
    self.plan_log_edit.appendPlainText("=" * 60)
    
    self.hide()
    time.sleep(0.5)
    
    try:
        for idx, item in enumerate(self.click_plan, start=1):
            if not self.is_executing:
                self.plan_log_edit.appendPlainText("用户中止执行")
                break
            
            if item.get("status") != "ready":
                continue
            
            display_no = item.get("display_no", "")
            answer = item.get("answer", "")
            
            question_click = item.get("question_click", [])
            if len(question_click) >= 2:
                x, y = question_click[0], question_click[1]
                self.plan_log_edit.appendPlainText(f"{idx}. {display_no}: 点击题号 ({x}, {y})")
                pyautogui.click(x, y)
                time.sleep(0.3)
            
            answer_clicks = item.get("answer_clicks", [])
            for click in answer_clicks:
                if len(click) >= 2:
                    ax, ay = click[0], click[1]
                    self.plan_log_edit.appendPlainText(f"   点击选项 ({ax}, {ay})")
                    pyautogui.click(ax, ay)
                    time.sleep(0.2)
        
        self.plan_log_edit.appendPlainText("点击计划执行完成")
        
    finally:
        self.is_executing = False
        self.show()


def stop_execute_plan(self: 'MainWindow'):
    self.is_executing = False
    self.plan_log_edit.appendPlainText("正在停止执行...")


def export_click_plan(self: 'MainWindow'):
    if not self.click_plan:
        QMessageBox.warning(self, "警告", "没有可导出的点击计划")
        return
    
    try:
        with open("click_plan.json", "w", encoding="utf-8") as f:
            json.dump(self.click_plan, f, ensure_ascii=False, indent=2)
        
        self.plan_log_edit.appendPlainText("点击计划已导出到 click_plan.json")
        QMessageBox.information(self, "成功", "导出成功！\nclick_plan.json")
        
    except Exception as e:
        QMessageBox.critical(self, "错误", f"导出失败: {e}")
