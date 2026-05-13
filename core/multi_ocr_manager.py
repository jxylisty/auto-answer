from typing import Optional, List, Dict, Any, Tuple
from PIL import Image
import json
import time


class MultiOcrManager:
    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode
        self._backends = {}
        self._failed_backends = set()
        self._init_stats()
        
    def _init_stats(self):
        self.stats = {
            "text_ocr_calls": 0,
            "option_ocr_calls": 0,
            "fallback_count": 0,
            "backend_stats": {}
        }
    
    def _get_backend(self, backend_name: str):
        if backend_name in self._failed_backends:
            return None
            
        if backend_name not in self._backends:
            try:
                if backend_name == "paddleocr":
                    from paddleocr import PaddleOCR
                    self._backends[backend_name] = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
                elif backend_name == "rapidocr-openvino":
                    from rapidocr_openvino import RapidOCR
                    self._backends[backend_name] = RapidOCR()
                elif backend_name == "rapidocr-onnxruntime":
                    from rapidocr_onnxruntime import RapidOCR
                    self._backends[backend_name] = RapidOCR()
                elif backend_name == "windows-ocr":
                    from core.ocr_engine import WindowsOcrBackend
                    self._backends[backend_name] = WindowsOcrBackend()
            except Exception as e:
                print(f"初始化OCR后端 {backend_name} 失败: {e}")
                self._failed_backends.add(backend_name)
                return None
        
        return self._backends.get(backend_name)
    
    def recognize_text(self, image: Image.Image) -> Tuple[str, str]:
        self.stats["text_ocr_calls"] += 1
        
        backends_priority = ["paddleocr", "rapidocr-onnxruntime", "windows-ocr"]
        
        for backend_name in backends_priority:
            backend = self._get_backend(backend_name)
            if backend is None:
                continue
            
            try:
                start_time = time.time()
                
                if backend_name == "windows-ocr":
                    text = backend.recognize(image)
                elif backend_name == "paddleocr":
                    import numpy as np
                    result = backend.ocr(np.array(image), cls=True)
                    if result and result[0]:
                        text = "\n".join([line[1][0] for line in result[0] if line])
                    else:
                        text = ""
                else:
                    import numpy as np
                    result, _ = backend(np.array(image))
                    if result:
                        text = "\n".join([line[1] for line in result if len(line) >= 2])
                    else:
                        text = ""
                
                elapsed = time.time() - start_time
                
                if self._is_text_valid(text):
                    if backend_name not in self.stats["backend_stats"]:
                        self.stats["backend_stats"][backend_name] = {"success": 0, "failed": 0}
                    self.stats["backend_stats"][backend_name]["success"] += 1
                    
                    if self.debug_mode:
                        print(f"[TEXT OCR] {backend_name}: {len(text)} chars, {elapsed:.2f}s")
                    
                    return text, backend_name
                else:
                    if backend_name not in self.stats["backend_stats"]:
                        self.stats["backend_stats"][backend_name] = {"success": 0, "failed": 0}
                    self.stats["backend_stats"][backend_name]["failed"] += 1
                    
                    if self.debug_mode:
                        print(f"[TEXT OCR] {backend_name}: 无效结果 (len={len(text)})")
                    
                    self.stats["fallback_count"] += 1
                    
            except Exception as e:
                print(f"[TEXT OCR] {backend_name} 失败: {e}")
                self.stats["fallback_count"] += 1
                continue
        
        return "", "failed"
    
    def recognize_options(self, image: Image.Image) -> Tuple[List[Dict], str]:
        self.stats["option_ocr_calls"] += 1
        
        backends_priority = ["paddleocr", "rapidocr-openvino", "rapidocr-onnxruntime"]
        
        for backend_name in backends_priority:
            backend = self._get_backend(backend_name)
            if backend is None:
                continue
            
            try:
                start_time = time.time()
                
                if backend_name == "paddleocr":
                    import numpy as np
                    result = backend.ocr(np.array(image), cls=True)
                    boxes = self._parse_paddle_result(result)
                else:
                    import numpy as np
                    result, _ = backend(np.array(image))
                    boxes = self._parse_rapid_result(result)
                
                elapsed = time.time() - start_time
                
                if self._are_options_valid(boxes):
                    if backend_name not in self.stats["backend_stats"]:
                        self.stats["backend_stats"][backend_name] = {"success": 0, "failed": 0}
                    self.stats["backend_stats"][backend_name]["success"] += 1
                    
                    if self.debug_mode:
                        print(f"[OPTION OCR] {backend_name}: {len(boxes)} boxes, {elapsed:.2f}s")
                    
                    return boxes, backend_name
                else:
                    if backend_name not in self.stats["backend_stats"]:
                        self.stats["backend_stats"][backend_name] = {"success": 0, "failed": 0}
                    self.stats["backend_stats"][backend_name]["failed"] += 1
                    
                    if self.debug_mode:
                        print(f"[OPTION OCR] {backend_name}: 无效结果 (boxes={len(boxes)})")
                    
                    self.stats["fallback_count"] += 1
                    
            except Exception as e:
                print(f"[OPTION OCR] {backend_name} 失败: {e}")
                self.stats["fallback_count"] += 1
                continue
        
        return [], "failed"
    
    def _parse_paddle_result(self, result) -> List[Dict]:
        boxes = []
        if not result or not result[0]:
            return boxes
        
        for line in result[0]:
            if not line or len(line) < 2:
                continue
            
            points = line[0]
            text_info = line[1]
            text = text_info[0] if isinstance(text_info, (list, tuple)) else str(text_info)
            confidence = text_info[1] if isinstance(text_info, (list, tuple)) and len(text_info) > 1 else 0.0
            
            x_coords = [p[0] for p in points]
            y_coords = [p[1] for p in points]
            
            boxes.append({
                "text": text,
                "confidence": confidence,
                "x": int(min(x_coords)),
                "y": int(min(y_coords)),
                "width": int(max(x_coords) - min(x_coords)),
                "height": int(max(y_coords) - min(y_coords)),
                "center_x": int((min(x_coords) + max(x_coords)) / 2),
                "center_y": int((min(y_coords) + max(y_coords)) / 2),
                "source": "paddleocr"
            })
        
        return boxes
    
    def _parse_rapid_result(self, result) -> List[Dict]:
        boxes = []
        if not result:
            return boxes
        
        for line in result:
            if len(line) < 2:
                continue
            
            points = line[0]
            text = line[1]
            confidence = line[2] if len(line) > 2 else 0.0
            
            x_coords = [p[0] for p in points]
            y_coords = [p[1] for p in points]
            
            boxes.append({
                "text": text,
                "confidence": confidence,
                "x": int(min(x_coords)),
                "y": int(min(y_coords)),
                "width": int(max(x_coords) - min(x_coords)),
                "height": int(max(y_coords) - min(y_coords)),
                "center_x": int((min(x_coords) + max(x_coords)) / 2),
                "center_y": int((min(y_coords) + max(y_coords)) / 2),
                "source": "rapidocr"
            })
        
        return boxes
    
    def _is_text_valid(self, text: str) -> bool:
        if not text or not text.strip():
            return False
        
        text_clean = text.strip()
        if len(text_clean) < 8:
            return False
        
        return True
    
    def _are_options_valid(self, boxes: List[Dict]) -> bool:
        if not boxes or len(boxes) < 2:
            return False
        
        option_count = 0
        for box in boxes:
            text = box.get("text", "").strip().upper()
            if any(opt in text for opt in ["A", "B", "C", "D", "正确", "错误", "对", "错", "T", "F"]):
                option_count += 1
        
        return option_count >= 2
    
    def get_stats(self) -> Dict:
        return self.stats.copy()
    
    def save_debug_info(self, filepath: str = "debug_ocr_raw.json"):
        if not self.debug_mode:
            return
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.stats, f, ensure_ascii=False, indent=2)
        
        print(f"OCR调试信息已保存到: {filepath}")
    
    def reset_stats(self):
        self._init_stats()


_ocr_manager_instance = None


def get_ocr_manager(debug_mode: bool = False) -> MultiOcrManager:
    global _ocr_manager_instance
    if _ocr_manager_instance is None:
        _ocr_manager_instance = MultiOcrManager(debug_mode=debug_mode)
    return _ocr_manager_instance
