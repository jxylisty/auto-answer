from typing import Dict, List, Optional
import json


class ClickPlanBuilder:
    def __init__(self):
        self.click_plan: List[Dict] = []
    
    def build_plan(
        self,
        number_template: Dict,
        option_template: Dict,
        answers: Dict[str, str],
        offset_x: int = 0,
        offset_y: int = 0
    ) -> List[Dict]:
        self.click_plan = []
        
        questions = []
        for section in number_template.get("sections", []):
            questions.extend(section.get("questions", []))
        
        for question in questions:
            global_id = question.get("global_id")
            display_no = question.get("display_no")
            question_type = question.get("question_type", "single_choice")
            
            question_click = [
                question.get("click_x", 0) + offset_x,
                question.get("click_y", 0) + offset_y
            ]
            
            answer = answers.get(global_id)
            
            if not answer:
                plan_item = {
                    "global_id": global_id,
                    "display_no": display_no,
                    "question_click": question_click,
                    "answer": None,
                    "answer_clicks": [],
                    "question_type": question_type,
                    "status": "no_answer",
                    "source": question.get("source", "unknown")
                }
                self.click_plan.append(plan_item)
                continue
            
            answer_clicks = self._get_answer_clicks(
                answer,
                option_template,
                question_type,
                offset_x,
                offset_y
            )
            
            status = self._determine_status(answer, answer_clicks, question_type)
            
            plan_item = {
                "global_id": global_id,
                "display_no": display_no,
                "question_click": question_click,
                "answer": answer,
                "answer_clicks": answer_clicks,
                "question_type": question_type,
                "status": status,
                "source": question.get("source", "unknown")
            }
            
            self.click_plan.append(plan_item)
        
        print(f"点击计划生成完成，共 {len(self.click_plan)} 题")
        self._print_plan_summary()
        
        return self.click_plan
    
    def _get_answer_clicks(
        self,
        answer: str,
        option_template: Dict,
        question_type: str,
        offset_x: int,
        offset_y: int
    ) -> List[List[int]]:
        clicks = []
        
        if question_type == "true_false":
            judge_template = option_template.get("judge", option_template)
            true_option = judge_template.get("true_option", {})
            false_option = judge_template.get("false_option", {})
            
            if answer == "TRUE":
                if true_option:
                    clicks.append([
                        true_option.get("click_x", 0) + offset_x,
                        true_option.get("click_y", 0) + offset_y
                    ])
            elif answer == "FALSE":
                if false_option:
                    clicks.append([
                        false_option.get("click_x", 0) + offset_x,
                        false_option.get("click_y", 0) + offset_y
                    ])
        
        else:
            choice_template = option_template.get("single_choice", option_template)
            options = choice_template.get("options", {})

            if answer in options:
                selected_labels = [answer]
            else:
                selected_labels = list(answer)

            for letter in selected_labels:
                option_data = options.get(letter)
                if option_data:
                    clicks.append([
                        option_data.get("click_x", 0) + offset_x,
                        option_data.get("click_y", 0) + offset_y
                    ])
        
        return clicks
    
    def _determine_status(
        self,
        answer: str,
        answer_clicks: List[List[int]],
        question_type: str
    ) -> str:
        if not answer_clicks:
            return "no_coordinates"
        
        if question_type == "single_choice":
            if len(answer) != 1:
                return "invalid_answer"
            if len(answer_clicks) != 1:
                return "need_check"
        
        elif question_type == "multiple_choice":
            if len(answer) < 2:
                return "invalid_answer"
            if len(answer_clicks) != len(answer):
                return "need_check"
        
        elif question_type == "true_false":
            if answer not in ["TRUE", "FALSE"]:
                return "invalid_answer"
            if len(answer_clicks) != 1:
                return "need_check"
        
        return "ready"
    
    def _print_plan_summary(self):
        status_count = {}
        for item in self.click_plan:
            status = item.get("status", "unknown")
            status_count[status] = status_count.get(status, 0) + 1
        
        print("点击计划统计:")
        for status, count in sorted(status_count.items()):
            print(f"  {status}: {count} 题")
    
    def get_ready_items(self) -> List[Dict]:
        return [item for item in self.click_plan if item.get("status") == "ready"]
    
    def get_items_by_status(self, status: str) -> List[Dict]:
        return [item for item in self.click_plan if item.get("status") == status]
    
    def get_item_by_global_id(self, global_id: str) -> Optional[Dict]:
        for item in self.click_plan:
            if item.get("global_id") == global_id:
                return item
        return None
    
    def update_item_status(self, global_id: str, new_status: str):
        for item in self.click_plan:
            if item.get("global_id") == global_id:
                item["status"] = new_status
                break
    
    def save_plan(self, filepath: str = "click_plan.json"):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.click_plan, f, ensure_ascii=False, indent=2)
        print(f"点击计划已保存到: {filepath}")
    
    def load_plan(self, filepath: str = "click_plan.json") -> List[Dict]:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.click_plan = json.load(f)
            print(f"点击计划已加载: {filepath}")
            return self.click_plan
        except FileNotFoundError:
            print(f"点击计划文件不存在: {filepath}")
            return []
    
    def export_for_execution(self) -> List[Dict]:
        ready_items = self.get_ready_items()
        
        execution_plan = []
        for item in ready_items:
            execution_plan.append({
                "global_id": item["global_id"],
                "display_no": item["display_no"],
                "question_click": item["question_click"],
                "answer": item["answer"],
                "answer_clicks": item["answer_clicks"],
                "question_type": item["question_type"]
            })
        
        return execution_plan
    
    def validate_plan(self) -> List[str]:
        issues = []
        
        for item in self.click_plan:
            global_id = item.get("global_id", "unknown")
            status = item.get("status", "unknown")
            
            if status == "no_answer":
                issues.append(f"{global_id}: 没有答案")
            elif status == "no_coordinates":
                issues.append(f"{global_id}: 没有坐标")
            elif status == "invalid_answer":
                issues.append(f"{global_id}: 答案格式无效")
            elif status == "need_check":
                issues.append(f"{global_id}: 需要检查")
        
        return issues
