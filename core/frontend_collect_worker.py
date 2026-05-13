import csv
import os
import time
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QObject, QRect, Signal, Slot

from core.ocr_engine import recognize_image
from core.option_extractor import extract_options_from_question_image
from core.screenshot import grab_region


class FrontendCollectWorker(QObject):
    log = Signal(str)
    progress = Signal(str)
    progress_value = Signal(int, int, str)
    show_window = Signal()
    result = Signal(dict)
    exported = Signal(str, str)
    finished = Signal()
    failed = Signal(str)

    def __init__(
        self,
        capture_region: QRect,
        click_delay: float,
        interval: float,
        start_countdown: float,
        test_mode: bool,
        save_screenshots: bool,
        text_ocr_backend: str = "auto",
        option_ocr_backend: str = "auto",
        parse_options: bool = False,
        question_points: Optional[list[dict]] = None,
    ):
        super().__init__()
        self.capture_region = QRect(capture_region)
        self.click_delay = click_delay
        self.interval = interval
        self.start_countdown = start_countdown
        self.test_mode = test_mode
        self.save_screenshots = save_screenshots
        self.text_ocr_backend = text_ocr_backend
        self.option_ocr_backend = option_ocr_backend
        self.parse_options = parse_options
        self.question_points = list(question_points or [])
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def _sleep_with_stop(self, seconds: float) -> bool:
        end_time = time.perf_counter() + max(0.0, seconds)
        while time.perf_counter() < end_time:
            if self._stop_requested:
                return False
            time.sleep(0.05)
        return True

    def _build_question_points(self) -> list[dict]:
        if self.question_points:
            return [
                {
                    "index": idx + 1,
                    "no": point.get("no", idx + 1),
                    "row": point.get("row", ""),
                    "col": point.get("col", ""),
                    "x": int(point["x"]),
                    "y": int(point["y"]),
                }
                for idx, point in enumerate(self.question_points)
            ]
        return []

    def _export_results(self, records: list[dict]):
        csv_path = "questions.csv"
        md_path = "questions.md"

        with open(csv_path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "index",
                    "time",
                    "row",
                    "col",
                    "click_x",
                    "click_y",
                    "ocr_text",
                    "image_path",
                    "option_A_text",
                    "option_A_x",
                    "option_A_y",
                    "option_A_click_x",
                    "option_A_click_y",
                    "option_B_text",
                    "option_B_x",
                    "option_B_y",
                    "option_B_click_x",
                    "option_B_click_y",
                    "option_C_text",
                    "option_C_x",
                    "option_C_y",
                    "option_C_click_x",
                    "option_C_click_y",
                    "option_D_text",
                    "option_D_x",
                    "option_D_y",
                    "option_D_click_x",
                    "option_D_click_y",
                ],
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(records)

        with open(md_path, "w", encoding="utf-8") as file:
            file.write("# Questions\n\n")
            for record in records:
                file.write(f"## {record['index']}. row={record['row']} col={record['col']}\n\n")
                file.write(f"- time: {record['time']}\n")
                file.write(f"- click: ({record['click_x']}, {record['click_y']})\n")
                if record["image_path"]:
                    file.write(f"- image: {record['image_path']}\n")
                file.write("\n")
                file.write(record["ocr_text"] or "[empty]")
                file.write("\n\n")
                file.write("选项解析:\n")
                for letter in ("A", "B", "C", "D"):
                    text = record.get(f"option_{letter}_text", "") or "[empty]"
                    x = record.get(f"option_{letter}_x", "")
                    y = record.get(f"option_{letter}_y", "")
                    click_x = record.get(f"option_{letter}_click_x", "")
                    click_y = record.get(f"option_{letter}_click_y", "")
                    coord_text = f"({x}, {y})" if x != "" and y != "" else "(-, -)"
                    click_text = f"({click_x}, {click_y})" if click_x != "" and click_y != "" else "(-, -)"
                    file.write(f"- {letter}: {text} 坐标: {coord_text} 建议点击: {click_text}\n")
                file.write("\n")

        self.log.emit(f"已导出 {csv_path}, {md_path}")
        self.exported.emit(csv_path, md_path)

    @Slot()
    def run(self):
        import pyautogui

        pyautogui.FAILSAFE = True
        records: list[dict] = []
        screenshot_dir = "question_captures"
        if self.save_screenshots:
            os.makedirs(screenshot_dir, exist_ok=True)

        points = self._build_question_points()

        try:
            if self.start_countdown > 0:
                self.progress.emit(f"倒计时 {self.start_countdown:.1f} 秒后开始")
                self.log.emit(f"开始倒计时 {self.start_countdown:.1f} 秒")
                if not self._sleep_with_stop(self.start_countdown):
                    self.log.emit("采集已停止")
                    self.progress.emit("已停止")
                    self.finished.emit()
                    return

            total = len(points)
            self.progress.emit(f"采集中 0/{total}")

            screenshots: list[tuple] = []

            for idx, point in enumerate(points, start=1):
                if self._stop_requested:
                    self.log.emit("采集已停止")
                    self.progress.emit("已停止")
                    self._export_results(records)
                    self.finished.emit()
                    return

                index = point["index"]
                row = point["row"]
                col = point["col"]
                x = point["x"]
                y = point["y"]
                self.progress.emit(f"当前第 {index}/{total} 题")
                self.progress_value.emit(idx, total, f"采集中 {idx}/{total}")

                if self.test_mode:
                    pyautogui.moveTo(x, y, duration=0.15)
                    self.log.emit(f"测试模式：移动到 row={row}, col={col}, x={x}, y={y}")
                    if not self._sleep_with_stop(self.interval):
                        self.log.emit("采集已停止")
                        self.progress.emit("已停止")
                        self.finished.emit()
                        return
                    continue

                pyautogui.click(x, y)
                self.log.emit(f"已点击 row={row}, col={col}, x={x}, y={y}")
                if not self._sleep_with_stop(self.click_delay):
                    self.log.emit("采集已停止")
                    self.progress.emit("已停止")
                    self._export_results(records)
                    self.finished.emit()
                    return

                image = grab_region(self.capture_region)

                image_path = ""
                if self.save_screenshots:
                    image_path = os.path.join(screenshot_dir, f"question_{index:03d}.png")
                    image.save(image_path)

                screenshots.append((index, row, col, x, y, image, image_path))
                self.log.emit(f"已截图 row={row}, col={col}")

                if not self._sleep_with_stop(self.interval):
                    self.log.emit("采集已停止")
                    self.progress.emit("已停止")
                    self._export_results(records)
                    self.finished.emit()
                    return

            self.progress.emit(f"截图完成，开始识别 {len(screenshots)} 张图片...")
            self.log.emit(f"截图完成，开始识别 {len(screenshots)} 张图片")
            self.progress_value.emit(0, len(screenshots), "准备识别...")
            self.show_window.emit()

            for idx, (index, row, col, x, y, image, image_path) in enumerate(screenshots, start=1):
                if self._stop_requested:
                    self.log.emit("识别已停止")
                    self.progress.emit("已停止")
                    self._export_results(records)
                    self.finished.emit()
                    return

                self.progress.emit(f"识别中 {idx}/{len(screenshots)}")
                self.progress_value.emit(idx, len(screenshots), f"识别中 {idx}/{len(screenshots)}")

                t_ocr_start = time.perf_counter()
                text = recognize_image(image, backend_name=self.text_ocr_backend).strip()
                t_ocr_end = time.perf_counter()

                t_options_start = time.perf_counter()
                if self.parse_options:
                    options = extract_options_from_question_image(
                        image,
                        self.capture_region.left(),
                        self.capture_region.top(),
                        backend_name=self.option_ocr_backend,
                    )
                else:
                    options = {}
                t_options_end = time.perf_counter()
                print(f"正文OCR耗时: {t_ocr_end - t_ocr_start:.3f}s")
                print(f"选项解析耗时: {t_options_end - t_options_start:.3f}s")

                if text:
                    self.log.emit(f"已识别 row={row}, col={col}")
                else:
                    self.log.emit(f"未识别到文字 row={row}, col={col}")

                record = {
                    "index": index,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "row": row,
                    "col": col,
                    "click_x": x,
                    "click_y": y,
                    "ocr_text": text,
                    "image_path": image_path,
                    "capture_image": image,
                    "options": options,
                }
                for letter in ("A", "B", "C", "D"):
                    option_data = options.get(letter, {})
                    record[f"option_{letter}_text"] = option_data.get("text", "")
                    record[f"option_{letter}_x"] = option_data.get("screen_x", "")
                    record[f"option_{letter}_y"] = option_data.get("screen_y", "")
                    record[f"option_{letter}_click_x"] = option_data.get("click_x", "")
                    record[f"option_{letter}_click_y"] = option_data.get("click_y", "")

                records.append(record)
                self.result.emit(record)

            self._export_results(records)
            self.progress.emit(f"采集完成，共 {len(records)} 条")
            self.log.emit("采集完成")
            self.finished.emit()
        except pyautogui.FailSafeException:
            self.log.emit("触发 PyAutoGUI FAILSAFE，采集已停止")
            self.progress.emit("已停止")
            self._export_results(records)
            self.finished.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
