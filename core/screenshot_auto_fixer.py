from typing import Dict, List, Optional, Tuple
from PIL import Image
import json


class ScreenshotAutoFixer:
    def __init__(self):
        self.fix_log: List[Dict] = []
    
    def check_and_fix_number_card(
        self,
        image: Image.Image,
        region: Dict,
        ocr_result: List[Dict],
        screen_width: int = 1920,
        screen_height: int = 1080
    ) -> Tuple[Image.Image, Dict, List[str]]:
        issues = []
        needs_fix = False
        fix_reasons = []
        
        original_region = region.copy()
        fixed_region = region.copy()
        
        number_count = len([r for r in ocr_result if r.get("text", "").isdigit()])
        
        if number_count < 3:
            issues.append(f"题号数量不足: {number_count} < 3")
            needs_fix = True
            fix_reasons.append("题号数量不足")
        
        has_last_number = False
        for result in ocr_result:
            text = result.get("text", "")
            if text.isdigit() and int(text) > 10:
                has_last_number = True
                break
        
        if not has_last_number:
            issues.append("未识别到最后一个题号")
            fix_reasons.append("未识别到最后一个题号")
        
        edge_threshold = 30
        for result in ocr_result:
            x = result.get("x", 0)
            y = result.get("y", 0)
            width = result.get("width", 0)
            height = result.get("height", 0)
            
            if x < edge_threshold:
                issues.append(f"题号贴近左边缘: x={x}")
                needs_fix = True
                fix_reasons.append("题号贴近左边缘")
                break
            
            if y < edge_threshold:
                issues.append(f"题号贴近上边缘: y={y}")
                needs_fix = True
                fix_reasons.append("题号贴近上边缘")
                break
        
        if needs_fix or fix_reasons:
            fixed_region["left"] = max(0, region.get("left", 0) - 30)
            fixed_region["right"] = min(screen_width, region.get("right", 0) + 30)
            fixed_region["top"] = max(0, region.get("top", 0) - 40)
            fixed_region["bottom"] = min(screen_height, region.get("bottom", 0) + 80)
        
        self.fix_log.append({
            "type": "number_card",
            "original_region": original_region,
            "fixed_region": fixed_region,
            "fix_reasons": fix_reasons,
            "issues": issues
        })
        
        return image, fixed_region, issues
    
    def check_and_fix_question_page(
        self,
        image: Image.Image,
        region: Dict,
        ocr_result: List[Dict],
        option_count: int = 0,
        screen_width: int = 1920,
        screen_height: int = 1080
    ) -> Tuple[Image.Image, Dict, List[str]]:
        issues = []
        needs_fix = False
        fix_reasons = []
        
        original_region = region.copy()
        fixed_region = region.copy()
        
        has_question_text = False
        for result in ocr_result:
            text = result.get("text", "")
            if len(text) > 8:
                has_question_text = True
                break
        
        if not has_question_text:
            issues.append("未识别到题干文本")
            needs_fix = True
            fix_reasons.append("未识别到题干文本")
        
        if option_count < 2:
            issues.append(f"选项数量不足: {option_count} < 2")
            needs_fix = True
            fix_reasons.append("选项数量不足")
        
        image_height = image.height if image else 0
        image_width = image.width if image else 0
        
        if image_height > 0:
            for result in ocr_result:
                y = result.get("y", 0)
                height = result.get("height", 0)
                
                if y + height > image_height - 50:
                    issues.append("选项贴近截图底部")
                    needs_fix = True
                    fix_reasons.append("选项贴近截图底部")
                    break
        
        if image_height > 0:
            for result in ocr_result:
                y = result.get("y", 0)
                
                if y < 50:
                    issues.append("题干贴近截图顶部")
                    needs_fix = True
                    fix_reasons.append("题干贴近截图顶部")
                    break
        
        if needs_fix:
            fixed_region["left"] = max(0, region.get("left", 0) - 40)
            fixed_region["right"] = min(screen_width, region.get("right", 0) + 80)
            fixed_region["top"] = max(0, region.get("top", 0) - 80)
            fixed_region["bottom"] = min(screen_height, region.get("bottom", 0) + 180)
        
        self.fix_log.append({
            "type": "question_page",
            "original_region": original_region,
            "fixed_region": fixed_region,
            "fix_reasons": fix_reasons,
            "issues": issues
        })
        
        return image, fixed_region, issues
    
    def suggest_number_card_fix(
        self,
        ocr_result: List[Dict],
        region: Dict
    ) -> Dict:
        suggestions = {
            "needs_rescreenshot": False,
            "reasons": [],
            "suggested_action": None
        }
        
        number_count = len([r for r in ocr_result if r.get("text", "").isdigit()])
        
        if number_count < 3:
            suggestions["needs_rescreenshot"] = True
            suggestions["reasons"].append("题号数量不足，请确保截图包含更多题号")
        
        has_large_number = False
        for result in ocr_result:
            text = result.get("text", "")
            if text.isdigit() and int(text) > 10:
                has_large_number = True
                break
        
        if not has_large_number:
            suggestions["needs_rescreenshot"] = True
            suggestions["reasons"].append("未看到最后一个题号，请滚动到底部再截一次")
            suggestions["suggested_action"] = "scroll_to_bottom"
        
        return suggestions
    
    def get_fix_log(self) -> List[Dict]:
        return self.fix_log.copy()
    
    def save_fix_log(self, filepath: str = "screenshot_fix_log.json"):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.fix_log, f, ensure_ascii=False, indent=2)
        print(f"截图修正日志已保存到: {filepath}")
    
    def clear_log(self):
        self.fix_log = []
    
    def print_summary(self):
        print("=" * 60)
        print("截图修正摘要")
        print("=" * 60)
        
        for idx, log_entry in enumerate(self.fix_log, start=1):
            print(f"\n修正 {idx}:")
            print(f"  类型: {log_entry.get('type', 'unknown')}")
            print(f"  原始区域: {log_entry.get('original_region', {})}")
            print(f"  修正区域: {log_entry.get('fixed_region', {})}")
            print(f"  修正原因: {', '.join(log_entry.get('fix_reasons', []))}")
            print(f"  问题列表: {', '.join(log_entry.get('issues', []))}")
