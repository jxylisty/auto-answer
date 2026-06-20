"""
Web 后端 - 剪贴板模块
包含：复制 OCR 结果、导出题目等
"""

from typing import Dict
import subprocess

from .core import _last_ocr_text, _collected_records, update_last_ocr_text, _last_capture_path


def copy_ocr_result(text: str = None) -> Dict:
    """复制 OCR 结果到剪贴板"""
    if text is None:
        text = _last_ocr_text

    if not text:
        return {
            "success": False,
            "message": "没有可复制的文本"
        }

    try:
        import pyperclip
        pyperclip.copy(text)
        return {
            "success": True,
            "message": "OCR结果已复制到剪贴板"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"复制失败: {str(e)}"
        }


def clear_ocr_result() -> Dict:
    """清空 OCR 结果"""
    update_last_ocr_text("")
    return {
        "success": True,
        "message": "OCR结果已清空"
    }


def export_collected_questions() -> Dict:
    """导出采集的题目"""
    if not _collected_records:
        return {
            "success": False,
            "error": "没有采集的题目"
        }

    lines = []
    for rec in _collected_records:
        no = rec.get("no", rec.get("index", 0))
        text = rec.get("ocr_text", "").strip()
        if text:
            lines.append(f"第{no}题：\n{text}\n")

    content = "\n".join(lines)

    try:
        import pyperclip
        pyperclip.copy(content)
        return {
            "success": True,
            "message": f"已复制 {len(lines)} 道题目到剪贴板",
            "count": len(lines),
            "content": content
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"复制失败: {str(e)}"
        }


def get_ai_prompt_with_questions() -> Dict:
    """获取带题目的 AI 提示词"""
    if not _collected_records:
        return {
            "success": False,
            "error": "没有采集的题目"
        }

    lines = []
    for rec in _collected_records:
        no = rec.get("no", rec.get("index", 0))
        text = rec.get("ocr_text", "").strip()
        if text:
            lines.append(f"{no}. {text}")

    questions_text = "\n".join(lines)

    prompt = f"""请根据以下题目内容，给出每道题的正确答案。

题目：
{questions_text}

请按以下格式回答：
1. A
2. B
3. C
...

只输出答案，不要解释。"""

    try:
        import pyperclip
        pyperclip.copy(prompt)
        return {
            "success": True,
            "message": f"AI提示词已复制到剪贴板（{len(lines)}道题）",
            "count": len(lines),
            "prompt": prompt
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"复制失败: {str(e)}"
        }


def set_fixed_region(region: Dict) -> Dict:
    """设置固定区域"""
    from .core import _fixed_region
    global _fixed_region
    _fixed_region = region
    return {
        "success": True,
        "message": "固定区域已设置"
    }


def copy_screenshot() -> Dict:
    """复制截图到剪贴板"""
    import os
    if not os.path.exists(_last_capture_path):
        return {
            "success": False,
            "message": "没有可复制的截图，请先执行 OCR 识别"
        }
    try:
        abs_path = os.path.abspath(_last_capture_path).replace("\\", "\\\\")
        # 使用 PowerShell 将图片复制到剪贴板
        ps_script = (
            'Add-Type -AssemblyName System.Windows.Forms; '
            'Add-Type -AssemblyName System.Drawing; '
            f'$img = [System.Drawing.Image]::FromFile("{abs_path}"); '
            '[System.Windows.Forms.Clipboard]::SetImage($img); '
            '$img.Dispose()'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return {
                "success": True,
                "message": "截图已复制到剪贴板"
            }
        else:
            return {
                "success": False,
                "message": f"复制失败: {result.stderr.strip()}"
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"复制失败: {str(e)}"
        }
