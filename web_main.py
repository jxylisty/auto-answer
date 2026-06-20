import os
import sys
import threading
import webview


class Api:
    def get_state(self):
        from api_bridge import get_state
        return get_state()

    def capture_ocr(self, region: dict = None, backend_name: str = "auto"):
        from api_bridge import capture_ocr
        return capture_ocr(region, backend_name)

    def capture_ocr_with_tkinter(self, backend_name: str = "auto"):
        from api_bridge import capture_ocr_with_tkinter
        return capture_ocr_with_tkinter(backend_name)

    def recognize_fixed_region(self, backend_name: str = "auto"):
        from api_bridge import recognize_fixed_region
        return recognize_fixed_region(backend_name)

    def begin_screen_capture(self, mode: str = "single_ocr"):
        from api_bridge import begin_screen_capture
        return begin_screen_capture(mode)

    def finish_region_select(self, mode: str, rect: dict):
        from api_bridge import finish_region_select
        return finish_region_select(mode, rect)

    def capture_ocr_from_selected_region(self, region: dict, backend_name: str = "auto"):
        from api_bridge import capture_ocr_from_selected_region
        return capture_ocr_from_selected_region(region, backend_name)

    def copy_screenshot(self):
        from api_bridge import copy_screenshot
        return copy_screenshot()

    def copy_ocr_result(self, text: str):
        from api_bridge import copy_ocr_result
        return copy_ocr_result(text)

    def clear_ocr_result(self):
        from api_bridge import clear_ocr_result
        return clear_ocr_result()

    def export_collected_questions(self):
        from api_bridge import export_collected_questions
        return export_collected_questions()

    def get_ai_prompt_with_questions(self):
        from api_bridge import get_ai_prompt_with_questions
        return get_ai_prompt_with_questions()

    def select_question_region(self):
        from api_bridge import select_question_region
        return select_question_region()

    def select_number_region(self):
        from api_bridge import select_number_region
        return select_number_region()

    def save_number_region_capture(self):
        from api_bridge import save_number_region_capture
        return save_number_region_capture()

    def detect_question_points(self, backend_name: str = "auto"):
        from api_bridge import detect_question_points
        return detect_question_points(backend_name)

    def start_collection(self, options: dict):
        from api_bridge import start_collection
        return start_collection(options)

    def get_collection_status(self):
        from api_bridge import get_collection_status
        return get_collection_status()

    def get_operation_status(self):
        from api_bridge import get_operation_status
        return get_operation_status()

    def get_execution_status(self):
        from api_bridge import get_execution_status
        return get_execution_status()

    def stop_collection(self):
        from api_bridge import stop_collection
        return stop_collection()

    def parse_collected_options(self, options: dict = None):
        from api_bridge import parse_collected_options
        return parse_collected_options(options)

    def get_collection_results(self):
        from api_bridge import get_collection_results
        return get_collection_results()

    def collect_questions(self):
        from api_bridge import collect_questions
        return collect_questions()

    def parse_answers(self, text: str):
        from api_bridge import parse_answers
        return parse_answers(text)

    def build_answer_click_tasks(self, answers: list):
        from api_bridge import build_answer_click_tasks
        return build_answer_click_tasks(answers)

    def execute_selected_answer(self, index: int, options: dict = None):
        from api_bridge import execute_selected_answer_real
        return execute_selected_answer_real(index, options)

    def execute_next_answer(self, options: dict = None):
        from api_bridge import execute_next_answer_real
        return execute_next_answer_real(options)

    def execute_all_answers(self, options: dict = None):
        from api_bridge import execute_all_answers_real
        return execute_all_answers_real(options)

    def stop_execution(self):
        from api_bridge import stop_execution_real
        return stop_execution_real()

    def execute_clicks(self, plan: list):
        from api_bridge import execute_clicks
        return execute_clicks(plan)

    # ================= 补充手动录入与快捷键 API =================

    def start_hotkey_listener(self):
        from api_bridge import start_hotkey_listener
        return start_hotkey_listener()

    def check_hotkey_result(self):
        from api_bridge import check_hotkey_result
        return check_hotkey_result()

    def cancel_hotkey_listener(self):
        from api_bridge import cancel_hotkey_listener
        return cancel_hotkey_listener()

    def add_or_update_question_point(self, point_data: dict):
        from api_bridge import add_or_update_question_point
        return add_or_update_question_point(point_data)

    def delete_question_point(self, no: int):
        from api_bridge import delete_question_point
        return delete_question_point(no)

    def trigger_infer_missing_points(self):
        """触发智能网格推断（独立API，用户手动触发）"""
        from api_bridge import trigger_infer_missing_points
        return trigger_infer_missing_points()

class SelectionController:
    def __init__(self, app, window):
        self._app = app
        self._window = window
        self._QEventLoop = None
        self._QThread = None
        self._bridge = None

        try:
            from PySide6.QtCore import QObject, Signal, Qt, QEventLoop, QThread

            class _Bridge(QObject):
                request_select = Signal(object)

                def __init__(self, controller):
                    super().__init__()
                    self._controller = controller
                    self.request_select.connect(self._handle_select, Qt.QueuedConnection)

                def _handle_select(self, payload):
                    payload["result"] = self._controller._select_region_on_main(payload["mode"])
                    payload["event"].set()

            self._QEventLoop = QEventLoop
            self._QThread = QThread
            self._bridge = _Bridge(self)
            if app is not None:
                self._bridge.moveToThread(app.thread())
        except ImportError:
            pass

    def _select_region_on_main(self, mode: str):
        from PySide6.QtWidgets import QApplication
        from core.selection_overlay import SelectionOverlay
        import api_bridge

        result = {"success": False, "error": "框选未返回结果"}
        overlay = None
        loop = self._QEventLoop()

        try:
            if self._window:
                self._window.hide()
            QApplication.processEvents()

            overlay = SelectionOverlay()

            def finish(value, restore: bool = True):
                nonlocal result
                result = value
                try:
                    if restore:
                        api_bridge._restore_webview_window()
                finally:
                    loop.quit()

            def on_selected(rect):
                region = {
                    "left": rect.left(),
                    "top": rect.top(),
                    "width": rect.width(),
                    "height": rect.height(),
                }
                # single_ocr 会马上调用 capture_ocr_from_selected_region 做真正截图，
                # 所以这里先别恢复窗口，避免“恢复 -> 再隐藏 -> 再恢复”的闪烁。
                finish({
                    "success": True,
                    "region": region,
                }, restore=(mode != "single_ocr"))

            def on_canceled():
                finish({
                    "success": False,
                    "error": "已取消框选"
                }, restore=True)

            overlay.selection_made.connect(on_selected)
            overlay.selection_canceled.connect(on_canceled)
            overlay.show_full_desktop()
            loop.exec()
            return result
        except Exception as exc:
            try:
                api_bridge._restore_webview_window()
            except Exception:
                pass
            return {
                "success": False,
                "error": f"框选失败: {exc}"
            }
        finally:
            if overlay is not None:
                try:
                    overlay.deleteLater()
                except Exception:
                    pass

    def select_region(self, mode: str):
        if self._app is None or self._QThread is None:
            # PySide6 不可用，回退到 tkinter
            from web_backend.region import select_region_tkinter
            return select_region_tkinter(mode)

        if self._QThread.currentThread() == self._app.thread():
            return self._select_region_on_main(mode)

        payload = {
            "mode": mode,
            "event": threading.Event(),
            "result": None,
        }
        self._bridge.request_select.emit(payload)
        payload["event"].wait()
        return payload["result"] or {
            "success": False,
            "error": "框选未返回结果"
        }


def main():
    import api_bridge
    
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        app = QApplication.instance()
        if app is None:
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
            QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
            app = QApplication(sys.argv)
    except Exception as e:
        print(f"Warning: QApplication init: {e}")
        app = None
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base_dir, 'webui', 'index.html')
    
    if not os.path.exists(html_path):
        print(f"错误: 找不到 {html_path}")
        sys.exit(1)
    
    api_instance = Api()
    window = webview.create_window(
        title='答题助手',
        url=html_path,
        width=1200,
        height=800,
        min_size=(900, 600),
        js_api=api_instance
    )
    
    api_bridge.set_window(window)
    api_bridge.set_selection_controller(SelectionController(app, window))
    
    webview.start(debug=False)


if __name__ == '__main__':
    main()
