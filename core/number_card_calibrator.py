from typing import List, Dict, Optional, Tuple
from PIL import Image
import json
import re


class NumberCardCalibrator:
    def __init__(self):
        self.template = {
            "sections": [],
            "total_questions": 0,
            "grid_info": {
                "rows": 0,
                "cols": 0,
                "dx": 0,
                "dy": 0
            }
        }
        self._global_index = 0
    
    def calibrate_from_screenshots(
        self,
        top_image: Image.Image,
        bottom_image: Optional[Image.Image],
        ocr_backend,
        region_left: int = 0,
        region_top: int = 0
    ) -> Dict:
        print("=" * 60)
        print("开始题号栏校准 - 直接使用OCR坐标")
        print("=" * 60)
        
        top_boxes = self._extract_number_boxes(top_image, ocr_backend, region_left, region_top, "top")
        print(f"顶部截图识别到 {len(top_boxes)} 个题号")
        
        bottom_boxes = []
        if bottom_image:
            bottom_boxes = self._extract_number_boxes(bottom_image, ocr_backend, region_left, region_top, "bottom")
            print(f"底部截图识别到 {len(bottom_boxes)} 个题号")
        
        all_boxes = top_boxes + bottom_boxes
        print(f"共 {len(all_boxes)} 个题号（不去重）")
        
        if len(all_boxes) < 1:
            print("错误: 未识别到任何题号")
            return self.template
        
        questions = []
        boxes_sorted = sorted(all_boxes, key=lambda b: (b["y"], b["x"]))
        
        for idx, box in enumerate(boxes_sorted, start=1):
            self._global_index += 1
            
            question = {
                "global_id": f"Q{self._global_index:06d}",
                "global_index": self._global_index,
                "section_id": 1,
                "section_name": "题目",
                "question_type": "choice",
                "local_no": idx,
                "display_no": str(idx),
                "click_x": box["x"],
                "click_y": box["y"],
                "source": box["source"],
                "original_number": box["number"]
            }
            questions.append(question)
            print(f"  Q{self._global_index:06d} | ({box['x']}, {box['y']}) | OCR题号:{box['number']}")
        
        section = {
            "section_id": 1,
            "section_name": "题目",
            "question_type": "choice",
            "questions": questions
        }
        
        self.template["sections"] = [section]
        self.template["total_questions"] = len(questions)
        
        self.save_template("number_card_template.json")
        
        print(f"\n题号栏校准完成，共 {len(questions)} 题")
        return self.template
    
    def _detect_sections_simple(self, boxes: List[Dict]) -> List[Dict]:
        sections = []
        
        y_groups = self._group_by_y(boxes, tolerance=50)
        print(f"\n按Y坐标分组: {len(y_groups)} 组")
        
        for i, group in enumerate(y_groups):
            print(f"  组{i+1}: {len(group)} 个位置")
        
        type_names = ["单选题", "多选题", "判断题", "填空题", "简答题"]
        
        for idx, group in enumerate(y_groups):
            type_name = type_names[idx] if idx < len(type_names) else f"题型{idx + 1}"
            section = self._build_section_simple(group, type_name, idx + 1)
            sections.append(section)
        
        return sections
    
    def _build_section_simple(self, boxes: List[Dict], type_name: str, section_id: int) -> Dict:
        questions = []
        boxes_sorted = sorted(boxes, key=lambda b: (b["y"], b["x"]))
        
        section_prefixes = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}
        section_prefix = section_prefixes.get(section_id, str(section_id))
        
        for local_idx, box in enumerate(boxes_sorted, start=1):
            self._global_index += 1
            
            display_no = f"{section_prefix}-{local_idx}"
            
            question = {
                "global_id": f"Q{self._global_index:06d}",
                "global_index": self._global_index,
                "section_id": section_id,
                "section_name": type_name,
                "question_type": self._get_question_type(type_name),
                "local_no": local_idx,
                "display_no": display_no,
                "click_x": box["x"],
                "click_y": box["y"],
                "source": box["source"],
                "original_number": box["number"]
            }
            questions.append(question)
            print(f"  创建题目: {question['global_id']} | {display_no} | ({box['x']}, {box['y']})")
        
        return {
            "section_id": section_id,
            "section_name": type_name,
            "question_type": self._get_question_type(type_name),
            "questions": questions
        }
    
    def _extract_number_boxes(
        self,
        image: Image.Image,
        ocr_backend,
        region_left: int,
        region_top: int,
        position: str
    ) -> List[Dict]:
        print(f"\n处理{position}截图...")
        
        boxes = ocr_backend.locate_text_boxes(
            image,
            region_left=region_left,
            region_top=region_top
        )
        
        number_boxes = []
        for box in boxes:
            text = box.get("text", "").strip()
            if text.isdigit():
                number_boxes.append({
                    "number": int(text),
                    "x": box.get("center_x", box.get("x")),
                    "y": box.get("center_y", box.get("y")),
                    "source": box.get("source", "ocr"),
                    "position": position
                })
        
        number_boxes.sort(key=lambda b: (b["y"], b["x"]))
        return number_boxes
    
    def _deduplicate_boxes(self, boxes: List[Dict]) -> List[Dict]:
        unique = {}
        for box in boxes:
            key = (box["number"], box["x"], box["y"])
            if key not in unique:
                unique[key] = box
            else:
                if unique[key]["source"] == "inferred" and box["source"] == "ocr":
                    unique[key] = box
        
        return list(unique.values())
    
    def _detect_sections(self, boxes: List[Dict]) -> List[Dict]:
        sections = []
        
        first_number_boxes = [b for b in boxes if b["number"] == 1]
        print(f"找到 {len(first_number_boxes)} 个'第1题'位置")
        
        for i, first_box in enumerate(first_number_boxes):
            print(f"  大题{i+1} 第1题: ({first_box['x']}, {first_box['y']})")
        
        if len(first_number_boxes) == 0:
            print("未找到任何'第1题'，按Y坐标分组")
            y_groups = self._group_by_y(boxes, tolerance=50)
            print(f"按Y坐标分组: {len(y_groups)} 组")
            
            type_names = ["单选题", "多选题", "判断题", "填空题", "简答题"]
            
            for idx, group in enumerate(y_groups):
                type_name = type_names[idx] if idx < len(type_names) else f"题型{idx + 1}"
                section = self._build_section(group, type_name, idx + 1)
                sections.append(section)
        
        elif len(first_number_boxes) == 1:
            print("只找到一个'第1题'，作为单一题型")
            section = self._build_section(boxes, "选择题", 1)
            sections.append(section)
        
        else:
            type_names = ["单选题", "多选题", "判断题", "填空题", "简答题"]
            
            for idx, first_box in enumerate(first_number_boxes):
                type_name = type_names[idx] if idx < len(type_names) else f"题型{idx + 1}"
                
                section_boxes = self._get_boxes_for_section(boxes, first_number_boxes, idx)
                
                print(f"大题{idx+1} ({type_name}): OCR识别到 {len(section_boxes)} 个题号")
                
                section = self._build_section(section_boxes, type_name, idx + 1)
                sections.append(section)
        
        return sections
    
    def _get_boxes_for_section(
        self, 
        all_boxes: List[Dict], 
        first_boxes: List[Dict], 
        section_idx: int
    ) -> List[Dict]:
        current_first = first_boxes[section_idx]
        
        if section_idx + 1 < len(first_boxes):
            next_first = first_boxes[section_idx + 1]
            section_boxes = [
                b for b in all_boxes 
                if b["y"] >= current_first["y"] - 30 and b["y"] < next_first["y"] - 30
            ]
        else:
            section_boxes = [
                b for b in all_boxes 
                if b["y"] >= current_first["y"] - 30
            ]
        
        return section_boxes
    
    def _infer_missing_in_section(
        self,
        ocr_boxes: List[Dict],
        section_id: int,
        total_expected: int
    ) -> List[Dict]:
        if not ocr_boxes:
            print(f"  区域{section_id}: 无OCR数据，无法推断")
            return []
        
        ocr_boxes_sorted = sorted(ocr_boxes, key=lambda b: (b["y"], b["x"]))
        
        existing_numbers = set(b["number"] for b in ocr_boxes_sorted)
        missing_numbers = [n for n in range(1, total_expected + 1) if n not in existing_numbers]
        
        if not missing_numbers:
            print(f"  区域{section_id}: OCR已识别全部 {len(ocr_boxes)} 个题号")
            return ocr_boxes_sorted
        
        print(f"  区域{section_id}: OCR识别 {len(ocr_boxes)} 个，缺失 {len(missing_numbers)} 个: {missing_numbers}")
        
        if len(ocr_boxes_sorted) < 2:
            print(f"  区域{section_id}: OCR数据不足2个，无法推断")
            return ocr_boxes_sorted
        
        x_coords = [b["x"] for b in ocr_boxes_sorted]
        y_coords = [b["y"] for b in ocr_boxes_sorted]
        
        cols = len(set(x_coords))
        if cols < 2:
            cols = 1
        
        if cols > 1:
            x_sorted = sorted(set(x_coords))
            dx = x_sorted[1] - x_sorted[0] if len(x_sorted) > 1 else 0
        else:
            dx = 0
        
        y_sorted = sorted(set(y_coords))
        dy = y_sorted[1] - y_sorted[0] if len(y_sorted) > 1 else 0
        
        if dy == 0:
            dy = 40
        
        print(f"  区域{section_id}: 推断参数 cols={cols}, dx={dx}, dy={dy}")
        
        first_box = ocr_boxes_sorted[0]
        first_x = first_box["x"]
        first_y = first_box["y"]
        first_number = first_box["number"]
        
        all_boxes = list(ocr_boxes_sorted)
        
        for missing_no in missing_numbers:
            number_offset = missing_no - first_number
            
            if cols > 1:
                col = number_offset % cols
                row = number_offset // cols
            else:
                col = 0
                row = number_offset
            
            inferred_x = first_x + col * dx
            inferred_y = first_y + row * dy
            
            all_boxes.append({
                "number": missing_no,
                "x": inferred_x,
                "y": inferred_y,
                "source": "inferred"
            })
            print(f"    推断题号 {missing_no}: ({inferred_x}, {inferred_y})")
        
        all_boxes.sort(key=lambda b: b["number"])
        return all_boxes
    
    def _group_by_y(self, boxes: List[Dict], tolerance: int = 50) -> List[List[Dict]]:
        if not boxes:
            return []
        
        sorted_boxes = sorted(boxes, key=lambda b: b["y"])
        
        y_coords = [b["y"] for b in sorted_boxes]
        
        y_regions = []
        current_region_start = y_coords[0]
        current_region_end = y_coords[0]
        
        for y in y_coords[1:]:
            if y - current_region_end > tolerance:
                y_regions.append((current_region_start, current_region_end))
                current_region_start = y
                current_region_end = y
            else:
                current_region_end = y
        
        y_regions.append((current_region_start, current_region_end))
        
        print(f"  Y区域分组: {len(y_regions)} 个区域")
        for i, (start, end) in enumerate(y_regions):
            print(f"    区域{i+1}: y={start} ~ {end}")
        
        groups = []
        for start, end in y_regions:
            group = [b for b in sorted_boxes if start - tolerance <= b["y"] <= end + tolerance]
            groups.append(group)
        
        return groups
    
    def _build_section(self, boxes: List[Dict], type_name: str, section_id: int) -> Dict:
        questions = []
        boxes.sort(key=lambda b: (b["y"], b["x"]))
        
        section_prefixes = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}
        section_prefix = section_prefixes.get(section_id, str(section_id))
        
        for local_idx, box in enumerate(boxes, start=1):
            self._global_index += 1
            
            display_no = f"{section_prefix}-{box['number']}"
            
            question = {
                "global_id": f"Q{self._global_index:06d}",
                "global_index": self._global_index,
                "section_id": section_id,
                "section_name": type_name,
                "question_type": self._get_question_type(type_name),
                "local_no": box["number"],
                "display_no": display_no,
                "click_x": box["x"],
                "click_y": box["y"],
                "source": box["source"]
            }
            questions.append(question)
        
        return {
            "section_id": section_id,
            "section_name": type_name,
            "question_type": self._get_question_type(type_name),
            "questions": questions
        }
    
    def _get_question_type(self, type_name: str) -> str:
        type_map = {
            "单选题": "single_choice",
            "多选题": "multiple_choice",
            "判断题": "true_false",
            "填空题": "fill_blank",
            "简答题": "short_answer"
        }
        return type_map.get(type_name, "unknown")
    
    def _calculate_grid_info(self, boxes: List[Dict]) -> Dict:
        if len(boxes) < 2:
            return {"rows": 0, "cols": 0, "dx": 0, "dy": 0}
        
        sorted_boxes = sorted(boxes, key=lambda b: (b["y"], b["x"]))
        
        x_coords = sorted(set(b["x"] for b in sorted_boxes))
        y_coords = sorted(set(b["y"] for b in sorted_boxes))
        
        x_tolerance = 30
        y_tolerance = 30
        
        x_groups = []
        for x in x_coords:
            if not x_groups or abs(x - x_groups[-1][-1]) > x_tolerance:
                x_groups.append([x])
            else:
                x_groups[-1].append(x)
        
        y_groups = []
        for y in y_coords:
            if not y_groups or abs(y - y_groups[-1][-1]) > y_tolerance:
                y_groups.append([y])
            else:
                y_groups[-1].append(y)
        
        cols = len(x_groups)
        rows = len(y_groups)
        
        avg_x_positions = [sum(group) / len(group) for group in x_groups]
        avg_y_positions = [sum(group) / len(group) for group in y_groups]
        
        dx = 0
        if len(avg_x_positions) >= 2:
            dx = int(avg_x_positions[1] - avg_x_positions[0])
        
        dy = 0
        if len(avg_y_positions) >= 2:
            dy = int(avg_y_positions[1] - avg_y_positions[0])
        
        return {
            "rows": rows,
            "cols": cols,
            "dx": dx,
            "dy": dy
        }
    
    def infer_missing_questions(
        self,
        total_expected: int,
        start_x: int,
        start_y: int,
        dx: int,
        dy: int,
        cols: int
    ) -> List[Dict]:
        inferred = []
        
        rows_needed = (total_expected + cols - 1) // cols
        
        for row in range(rows_needed):
            for col in range(cols):
                idx = row * cols + col
                if idx >= total_expected:
                    break
                
                x = start_x + col * dx
                y = start_y + row * dy
                
                self._global_index += 1
                
                inferred.append({
                    "global_id": f"Q{self._global_index:06d}",
                    "section_id": 1,
                    "section_name": "选择题",
                    "question_type": "single_choice",
                    "local_no": idx + 1,
                    "global_index": self._global_index,
                    "display_no": f"1-{idx + 1}",
                    "click_x": x,
                    "click_y": y,
                    "source": "inferred"
                })
        
        return inferred
    
    def infer_section_questions(
        self,
        section_id: int,
        section_name: str,
        first_number: int,
        total_count: int,
        first_x: int,
        first_y: int,
        dx: int,
        dy: int,
        cols: int
    ) -> List[Dict]:
        inferred = []
        
        section_prefixes = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五"}
        section_prefix = section_prefixes.get(section_id, str(section_id))
        
        rows_needed = (total_count + cols - 1) // cols
        
        for row in range(rows_needed):
            for col in range(cols):
                local_idx = row * cols + col
                if local_idx >= total_count:
                    break
                
                local_no = first_number + local_idx
                x = first_x + col * dx
                y = first_y + row * dy
                
                self._global_index += 1
                
                inferred.append({
                    "global_id": f"Q{self._global_index:06d}",
                    "global_index": self._global_index,
                    "section_id": section_id,
                    "section_name": section_name,
                    "question_type": self._get_question_type(section_name),
                    "local_no": local_no,
                    "display_no": f"{section_prefix}-{local_no}",
                    "click_x": x,
                    "click_y": y,
                    "source": "inferred"
                })
        
        return inferred
    
    def calibrate_with_counts(
        self,
        top_image: Image.Image,
        bottom_image: Optional[Image.Image],
        ocr_backend,
        section_counts: List[int],
        region_left: int = 0,
        region_top: int = 0
    ) -> Dict:
        print("=" * 60)
        print("开始题号栏校准 - 直接使用OCR坐标")
        print("=" * 60)
        
        top_boxes = self._extract_number_boxes(top_image, ocr_backend, region_left, region_top, "top")
        print(f"顶部截图识别到 {len(top_boxes)} 个题号")
        
        bottom_boxes = []
        if bottom_image:
            bottom_boxes = self._extract_number_boxes(bottom_image, ocr_backend, region_left, region_top, "bottom")
            print(f"底部截图识别到 {len(bottom_boxes)} 个题号")
        
        all_boxes = top_boxes + bottom_boxes
        print(f"共 {len(all_boxes)} 个题号（不去重）")
        
        if len(all_boxes) < 1:
            print("错误: 未识别到任何题号")
            return self.template
        
        questions = []
        boxes_sorted = sorted(all_boxes, key=lambda b: (b["y"], b["x"]))
        
        for idx, box in enumerate(boxes_sorted, start=1):
            self._global_index += 1
            
            question = {
                "global_id": f"Q{self._global_index:06d}",
                "global_index": self._global_index,
                "section_id": 1,
                "section_name": "题目",
                "question_type": "choice",
                "local_no": idx,
                "display_no": str(idx),
                "click_x": box["x"],
                "click_y": box["y"],
                "source": box["source"],
                "original_number": box["number"]
            }
            questions.append(question)
            print(f"  Q{self._global_index:06d} | ({box['x']}, {box['y']}) | OCR题号:{box['number']}")
        
        section = {
            "section_id": 1,
            "section_name": "题目",
            "question_type": "choice",
            "questions": questions
        }
        
        self.template["sections"] = [section]
        self.template["total_questions"] = len(questions)
        
        self.save_template("number_card_template.json")
        
        print(f"\n题号栏校准完成，共 {len(questions)} 题")
        return self.template
    
    def save_template(self, filepath: str = "number_card_template.json"):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.template, f, ensure_ascii=False, indent=2)
        print(f"题号模板已保存到: {filepath}")
    
    def load_template(self, filepath: str = "number_card_template.json") -> Dict:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.template = json.load(f)
            print(f"题号模板已加载: {filepath}")
            return self.template
        except FileNotFoundError:
            print(f"题号模板文件不存在: {filepath}")
            return {}
    
    def get_question_by_global_id(self, global_id: str) -> Optional[Dict]:
        for section in self.template.get("sections", []):
            for question in section.get("questions", []):
                if question.get("global_id") == global_id:
                    return question
        return None
    
    def get_question_by_display_no(self, display_no: str) -> Optional[Dict]:
        for section in self.template.get("sections", []):
            for question in section.get("questions", []):
                if question.get("display_no") == display_no:
                    return question
        return None
    
    def get_all_questions(self) -> List[Dict]:
        questions = []
        for section in self.template.get("sections", []):
            questions.extend(section.get("questions", []))
        return questions
