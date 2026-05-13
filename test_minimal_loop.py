# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')

from ui.template_helper import (
    _generate_questions_from_counts,
    _parse_answers,
    _generate_click_plan,
)

print("=" * 60)
print("一、模板生成测试")
print("=" * 60)

questions = _generate_questions_from_counts([], 20, 15, 10)

print(f"总题数: {len(questions)}")
print()

print("前5题:")
for q in questions[:5]:
    print(f"  {q['global_id']} = {q['display_no']}, {q['question_type']}, ({q['click_x']}, {q['click_y']})")

print()
print("关键题目验证:")
q1 = questions[0]
assert q1['global_id'] == 'Q000001', f"Q000001错误: {q1['global_id']}"
assert q1['display_no'] == '一-1', f"一-1错误: {q1['display_no']}"
assert q1['question_type'] == 'single_choice', f"single_choice错误: {q1['question_type']}"
print("[OK] Q000001 = 一-1, single_choice")

q20 = questions[19]
assert q20['global_id'] == 'Q000020', f"Q000020错误: {q20['global_id']}"
assert q20['display_no'] == '一-20', f"一-20错误: {q20['display_no']}"
print("[OK] Q000020 = 一-20, single_choice")

q21 = questions[20]
assert q21['global_id'] == 'Q000021', f"Q000021错误: {q21['global_id']}"
assert q21['display_no'] == '二-1', f"二-1错误: {q21['display_no']}"
assert q21['question_type'] == 'multi_choice', f"multi_choice错误: {q21['question_type']}"
print("[OK] Q000021 = 二-1, multi_choice")

q35 = questions[34]
assert q35['global_id'] == 'Q000035', f"Q000035错误: {q35['global_id']}"
assert q35['display_no'] == '二-15', f"二-15错误: {q35['display_no']}"
print("[OK] Q000035 = 二-15, multi_choice")

q36 = questions[35]
assert q36['global_id'] == 'Q000036', f"Q000036错误: {q36['global_id']}"
assert q36['display_no'] == '三-1', f"三-1错误: {q36['display_no']}"
assert q36['question_type'] == 'judge', f"judge错误: {q36['question_type']}"
print("[OK] Q000036 = 三-1, judge")

q45 = questions[44]
assert q45['global_id'] == 'Q000045', f"Q000045错误: {q45['global_id']}"
assert q45['display_no'] == '三-10', f"三-10错误: {q45['display_no']}"
print("[OK] Q000045 = 三-10, judge")

print()
print("=" * 60)
print("二、答案映射测试")
print("=" * 60)

answer_text = """
1 B
2 A
20 C
二-1 ABC
二-2 AD
二-15 BCD
三-1 正确
三-2 错误
三-10 对
Q000003 D
"""

answers = _parse_answers(answer_text, questions)

print(f"解析到 {len(answers)} 个答案:")
for gid, ans in sorted(answers.items()):
    print(f"  {gid} -> {ans}")

print()
print("答案映射验证:")
assert answers.get('Q000001') == 'B', f"Q000001错误: {answers.get('Q000001')}"
print("[OK] Q000001 -> B")

assert answers.get('Q000002') == 'A', f"Q000002错误: {answers.get('Q000002')}"
print("[OK] Q000002 -> A")

assert answers.get('Q000003') == 'D', f"Q000003错误: {answers.get('Q000003')}"
print("[OK] Q000003 -> D")

assert answers.get('Q000020') == 'C', f"Q000020错误: {answers.get('Q000020')}"
print("[OK] Q000020 -> C")

assert answers.get('Q000021') == 'ABC', f"Q000021错误: {answers.get('Q000021')}"
print("[OK] Q000021 -> ABC")

assert answers.get('Q000022') == 'AD', f"Q000022错误: {answers.get('Q000022')}"
print("[OK] Q000022 -> AD")

assert answers.get('Q000035') == 'BCD', f"Q000035错误: {answers.get('Q000035')}"
print("[OK] Q000035 -> BCD")

assert answers.get('Q000036') == 'TRUE', f"Q000036错误: {answers.get('Q000036')}"
print("[OK] Q000036 -> TRUE")

assert answers.get('Q000037') == 'FALSE', f"Q000037错误: {answers.get('Q000037')}"
print("[OK] Q000037 -> FALSE")

assert answers.get('Q000045') == 'TRUE', f"Q000045错误: {answers.get('Q000045')}"
print("[OK] Q000045 -> TRUE")

print()
print("=" * 60)
print("三、click_plan生成测试")
print("=" * 60)

option_template = {"options": {}}

click_plan = _generate_click_plan(questions, option_template, answers)

print(f"生成 {len(click_plan)} 个点击计划项")

no_answer_count = sum(1 for item in click_plan if item['status'] == 'no_answer')
no_option_count = sum(1 for item in click_plan if item['status'] == 'no_option')
ready_count = sum(1 for item in click_plan if item['status'] == 'ready')

print(f"  ready: {ready_count}")
print(f"  no_option: {no_option_count}")
print(f"  no_answer: {no_answer_count}")

print()
print("前10项:")
for item in click_plan[:10]:
    print(f"  {item['global_id']} | {item['display_no']} | {item['answer']} | {item['status']}")

print()
print("关键项验证:")
item21 = next(item for item in click_plan if item['global_id'] == 'Q000021')
print(f"Q000021: answer={item21['answer']}, answer_clicks={item21['answer_clicks']}, status={item21['status']}")

item36 = next(item for item in click_plan if item['global_id'] == 'Q000036')
print(f"Q000036: answer={item36['answer']}, answer_clicks={item36['answer_clicks']}, status={item36['status']}")

item45 = next(item for item in click_plan if item['global_id'] == 'Q000045')
print(f"Q000045: answer={item45['answer']}, answer_clicks={item45['answer_clicks']}, status={item45['status']}")

print()
print("=" * 60)
print("全部测试通过!")
print("=" * 60)
