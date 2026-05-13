from typing import Dict, List, Optional, Tuple
import re
import json


def _normalize_tf_symbols(text: str) -> str:
    return (
        str(text or "")
        .replace("√", "TRUE")
        .replace("✓", "TRUE")
        .replace("×", "FALSE")
        .replace("✗", "FALSE")
    )


SECTION_MAP = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "单选": 1, "多选": 2, "判断": 3, "填空": 4, "简答": 5,
    "单选题": 1, "多选题": 2, "判断题": 3, "填空题": 4, "简答题": 5,
}

TRUE_VARIANTS = {'正确', '对', 't', 'true', '是', '√', '✓', 'yes', 'y', '1'}
FALSE_VARIANTS = {'错误', '错', 'f', 'false', '否', '×', '✗', 'no', 'n', '0'}


def normalize_answer_text(text: str, number_template: Optional[Dict] = None) -> Dict:
    result = {
        "answers": {},
        "invalid": [],
        "normalized_lines": []
    }
    
    lines = text.strip().split('\n')
    auto_index = 0
    
    for line_num, line in enumerate(lines, start=1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        parsed_list = _parse_line_multi(line)
        
        if not parsed_list:
            result["invalid"].append((line, f"行 {line_num}: 格式无法识别"))
            continue
        
        for parsed in parsed_list:
            question_id, answer = parsed
            
            normalized_answer = _normalize_answer_value(answer)
            if normalized_answer is None:
                result["invalid"].append((line, f"行 {line_num}: 答案格式无效 '{answer}'"))
                continue
            
            if question_id == "next_auto":
                auto_index += 1
                question_id = f"auto_{auto_index}"
            
            result["answers"][question_id] = normalized_answer
            result["normalized_lines"].append(f"{question_id} {normalized_answer}")
    
    return result


def _parse_line_multi(line: str) -> List[Tuple[str, str]]:
    results = []
    line = _normalize_tf_symbols(line)
    
    multi_pattern = r'(\d+)\s*[\.．、:：\)]\s*([A-Z]+)'
    matches = re.findall(multi_pattern, line)
    if len(matches) > 1:
        for num, ans in matches:
            results.append((num, ans.upper()))
        return results
    
    patterns = [
        (r'^Q(\d{6})\s+([A-Z]+)$', 'global_id'),
        (r'^Q(\d{6})\s+(正确|错误|对|错|T|F|true|false|是|否)$', 'global_id_tf'),
        (r'^([一二三四五六七八九十]+)-(\d+)\s+([A-Z]+)$', 'display_no'),
        (r'^([一二三四五六七八九十]+)-(\d+)\s+(正确|错误|对|错|T|F|true|false|是|否)$', 'display_no_tf'),
        (r'^(单选|多选|判断|填空|简答|单选题|多选题|判断题|填空题|简答题)\s*(\d+)\s+([A-Z]+)$', 'type_prefix'),
        (r'^(单选|多选|判断|填空|简答|单选题|多选题|判断题|填空题|简答题)\s*(\d+)\s+(正确|错误|对|错|T|F|true|false|是|否)$', 'type_prefix_tf'),
        (r'^(\d+)\s*[\.．、:：\)]\s*([A-Z]+)$', 'local_no_dot'),
        (r'^(\d+)\s+([A-Z]+)$', 'local_no'),
        (r'^(\d+)([A-Z])$', 'local_no_no_space'),
        (r'^题目\s*(\d+)\s+([A-Z]+)$', 'local_no_text'),
        (r'^第\s*(\d+)\s*题\s*[：:.．]?\s*([A-Z]+)$', 'local_no_question'),
        (r'^(\d+)\s+(正确|错误|对|错|T|F|true|false|是|否)$', 'local_no_tf'),
    ]
    
    for pattern, pattern_type in patterns:
        match = re.match(pattern, line, re.IGNORECASE)
        if match:
            parsed = _extract_from_match(match, pattern_type)
            if parsed:
                results.append(parsed)
            return results
    
    if re.match(r'^[A-Z]+$', line, re.IGNORECASE):
        if len(line) == 1:
            results.append(("next_auto", line.upper()))
        else:
            for ch in line.upper():
                results.append(("next_auto", ch))
        return results

    split_pattern = r'^([A-Z])\s*[,，;；\s]\s*([A-Z])\s*[,，;；\s]?\s*([A-Z]?)\s*[,，;；\s]?\s*([A-Z]?)$'
    match = re.match(split_pattern, line, re.IGNORECASE)
    if match:
        for i in range(1, 5):
            ch = match.group(i)
            if ch:
                results.append(("next_auto", ch.upper()))
        return results
    
    return results


def _extract_from_match(match, pattern_type: str) -> Optional[Tuple[str, str]]:
    if pattern_type == 'global_id':
        return f"Q{match.group(1)}", match.group(2).upper()
    
    elif pattern_type == 'global_id_tf':
        return f"Q{match.group(1)}", _normalize_tf(match.group(2))
    
    elif pattern_type == 'display_no':
        section = match.group(1)
        local_no = match.group(2)
        answer = match.group(3).upper()
        return f"{section}-{local_no}", answer
    
    elif pattern_type == 'display_no_tf':
        section = match.group(1)
        local_no = match.group(2)
        return f"{section}-{local_no}", _normalize_tf(match.group(3))
    
    elif pattern_type == 'type_prefix':
        type_name = match.group(1)
        local_no = match.group(2)
        answer = match.group(3).upper()
        section_id = SECTION_MAP.get(type_name, 1)
        section_name = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五"}.get(section_id, "一")
        return f"{section_name}-{local_no}", answer
    
    elif pattern_type == 'type_prefix_tf':
        type_name = match.group(1)
        local_no = match.group(2)
        section_id = SECTION_MAP.get(type_name, 1)
        section_name = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五"}.get(section_id, "一")
        return f"{section_name}-{local_no}", _normalize_tf(match.group(3))
    
    elif pattern_type in ('local_no_dot', 'local_no', 'local_no_no_space', 'local_no_text', 'local_no_question'):
        return match.group(1), match.group(2).upper()
    
    elif pattern_type == 'local_no_tf':
        return match.group(1), _normalize_tf(match.group(2))
    
    return None


def _normalize_answer_value(answer: str) -> Optional[str]:
    answer_lower = answer.lower().strip()
    
    if answer_lower in TRUE_VARIANTS:
        return 'TRUE'
    if answer_lower in FALSE_VARIANTS:
        return 'FALSE'
    
    if re.match(r'^[A-Z]+$', answer.upper()):
        return answer.upper()
    
    return None


def _normalize_tf(answer: str) -> str:
    answer_lower = answer.lower().strip()
    if answer_lower in TRUE_VARIANTS:
        return 'TRUE'
    if answer_lower in FALSE_VARIANTS:
        return 'FALSE'
    return answer.upper()


class AnswerImporter:
    def __init__(self):
        self.answers: Dict[str, str] = {}
        self.invalid_answers: List[Tuple[str, str]] = []
        
    def import_from_file(self, filepath: str) -> Dict[str, str]:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.import_from_text(content)
        except FileNotFoundError:
            print(f"答案文件不存在: {filepath}")
            return {}
    
    def import_from_text(self, text: str) -> Dict[str, str]:
        self.answers = {}
        self.invalid_answers = []
        
        lines = text.strip().split('\n')
        
        for line_num, line in enumerate(lines, start=1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parsed = self._parse_line(line)
            
            if parsed is None:
                self.invalid_answers.append((line, f"行 {line_num}: 格式无法识别"))
                continue
            
            question_id, answer = parsed
            
            if not self._is_answer_valid(answer):
                self.invalid_answers.append((line, f"行 {line_num}: 答案格式无效 '{answer}'"))
                continue
            
            if question_id in self.answers:
                print(f"警告: 题号 {question_id} 重复，将使用后面的答案")
            
            self.answers[question_id] = answer.upper()
        
        print(f"成功导入 {len(self.answers)} 个答案")
        if self.invalid_answers:
            print(f"无效答案 {len(self.invalid_answers)} 个:")
            for line, reason in self.invalid_answers:
                print(f"  {line} - {reason}")
        
        return self.answers
    
    def _parse_line(self, line: str) -> Optional[Tuple[str, str]]:
        line = _normalize_tf_symbols(line)
        patterns = [
            (r'^Q(\d{6})\s+([A-Z]+)$', 'global_id'),
            (r'^(\d+)\s+([A-Z]+)$', 'local_no'),
            (r'^([一二三四五六七八九十]+)-(\d+)\s+([A-Z]+)$', 'display_no'),
            (r'^(\d+)\.\s*([A-Z]+)$', 'local_no_dot'),
            (r'^题目\s*(\d+)\s+([A-Z]+)$', 'local_no_text'),
            (r'^第\s*(\d+)\s*题\s*[：:.．]?\s*([A-Z]+)$', 'local_no_question'),
            (r'^([一二三四五六七八九十]+)-(\d+)\s+(正确|错误|对|错|T|F|true|false)$', 'display_no_tf'),
            (r'^(\d+)\s+(正确|错误|对|错|T|F|true|false)$', 'local_no_tf'),
        ]
        
        for pattern, pattern_type in patterns:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                return self._extract_answer(match, pattern_type)
        
        simple_match = re.match(r'^([A-Z]+)$', line, re.IGNORECASE)
        if simple_match:
            return "next_auto", simple_match.group(1).upper()
        
        return None
    
    def _extract_answer(self, match, pattern_type: str) -> Tuple[str, str]:
        if pattern_type == 'global_id':
            global_id = f"Q{match.group(1)}"
            answer = match.group(2).upper()
            return global_id, answer
        
        elif pattern_type == 'local_no':
            local_no = match.group(1)
            answer = match.group(2).upper()
            return local_no, answer
        
        elif pattern_type == 'display_no':
            section = match.group(1)
            local_no = match.group(2)
            answer = match.group(3).upper()
            display_no = f"{section}-{local_no}"
            return display_no, answer
        
        elif pattern_type == 'local_no_dot':
            local_no = match.group(1)
            answer = match.group(2).upper()
            return local_no, answer
        
        elif pattern_type == 'local_no_text':
            local_no = match.group(1)
            answer = match.group(2).upper()
            return local_no, answer
        
        elif pattern_type == 'local_no_question':
            local_no = match.group(1)
            answer = match.group(2).upper()
            return local_no, answer
        
        elif pattern_type == 'display_no_tf':
            section = match.group(1)
            local_no = match.group(2)
            answer_text = match.group(3).lower()
            answer = self._normalize_true_false(answer_text)
            display_no = f"{section}-{local_no}"
            return display_no, answer
        
        elif pattern_type == 'local_no_tf':
            local_no = match.group(1)
            answer_text = match.group(2).lower()
            answer = self._normalize_true_false(answer_text)
            return local_no, answer
        
        return "unknown", ""
    
    def _normalize_true_false(self, answer_text: str) -> str:
        true_variants = ['正确', '对', 't', 'true']
        false_variants = ['错误', '错', 'f', 'false']
        
        if answer_text in true_variants:
            return 'TRUE'
        elif answer_text in false_variants:
            return 'FALSE'
        
        return answer_text.upper()
    
    def _is_answer_valid(self, answer: str) -> bool:
        if answer in ['TRUE', 'FALSE']:
            return True
        
        if not re.match(r'^[A-Z]+$', answer.upper()):
            return False
        
        return True
    
    def get_answer(self, question_id: str) -> Optional[str]:
        return self.answers.get(question_id)
    
    def get_all_answers(self) -> Dict[str, str]:
        return self.answers.copy()
    
    def get_invalid_answers(self) -> List[Tuple[str, str]]:
        return self.invalid_answers.copy()
    
    def map_to_global_ids(
        self,
        number_template: Dict,
        auto_increment: bool = True
    ) -> Dict[str, str]:
        mapped_answers = {}
        
        questions = []
        for section in number_template.get("sections", []):
            questions.extend(section.get("questions", []))
        
        auto_index = 0
        
        for question_id, answer in self.answers.items():
            if question_id.startswith('Q') and len(question_id) == 7:
                mapped_answers[question_id] = answer
                continue
            
            target_question = None
            
            for q in questions:
                if q.get("display_no") == question_id:
                    target_question = q
                    break
                if str(q.get("local_no")) == question_id:
                    target_question = q
                    break
            
            if target_question:
                global_id = target_question.get("global_id")
                if global_id:
                    mapped_answers[global_id] = answer
            elif auto_increment and question_id.isdigit():
                idx = int(question_id) - 1
                if 0 <= idx < len(questions):
                    global_id = questions[idx].get("global_id")
                    if global_id:
                        mapped_answers[global_id] = answer
            elif question_id == "next_auto":
                if auto_index < len(questions):
                    global_id = questions[auto_index].get("global_id")
                    if global_id:
                        mapped_answers[global_id] = answer
                    auto_index += 1
        
        print(f"映射后共 {len(mapped_answers)} 个答案")
        return mapped_answers
    
    def save_answers(self, filepath: str = "answers.json"):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.answers, f, ensure_ascii=False, indent=2)
        print(f"答案已保存到: {filepath}")
    
    def load_answers(self, filepath: str = "answers.json") -> Dict[str, str]:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.answers = json.load(f)
            print(f"答案已加载: {filepath}")
            return self.answers
        except FileNotFoundError:
            print(f"答案文件不存在: {filepath}")
            return {}
