from pathlib import Path
from datetime import datetime
import csv
import time

from playwright.sync_api import sync_playwright


# ======================
# 配置区
# ======================

# 如果你用我之前给你的 test_questions.html，就放在当前目录
LOCAL_TEST_HTML = Path("test_questions.html")

# 如果采集真实网页，把 USE_LOCAL_TEST_PAGE 改成 False，并填写 URL
USE_LOCAL_TEST_PAGE = True
URL = "https://example.com"

# 题号按钮选择器
QUESTION_BUTTON_SELECTOR = ".qbtn"

# 题目区域选择器
QUESTION_CONTENT_SELECTOR = "#questionPanel"

# 每次点击题号后等待页面刷新时间，单位秒
CLICK_DELAY = 0.3

# 最多采集多少题；None 表示全部
MAX_QUESTIONS = None

# 保存目录
SAVE_DIR = Path("web_collected_questions")

# 是否显示浏览器
HEADLESS = False

# 是否使用持久化登录目录
USER_DATA_DIR = "browser_profile"


def get_target_url() -> str:
    if USE_LOCAL_TEST_PAGE:
        html_path = LOCAL_TEST_HTML.resolve()
        if not html_path.exists():
            raise FileNotFoundError(f"找不到测试 HTML：{html_path}")
        return html_path.as_uri()
    return URL


def save_outputs(records):
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    csv_path = SAVE_DIR / "questions.csv"
    md_path = SAVE_DIR / "questions.md"

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["index", "timestamp", "text", "image_path"],
        )
        writer.writeheader()
        writer.writerows(records)

    with md_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(f"## 第 {record['index']} 题\n\n")
            f.write(f"时间：{record['timestamp']}\n\n")
            f.write(f"图片：{record['image_path']}\n\n")
            f.write("OCR/DOM 文本：\n\n")
            f.write(record["text"])
            f.write("\n\n---\n\n")

    print(f"\n已导出：{csv_path}")
    print(f"已导出：{md_path}")


def main():
    target_url = get_target_url()
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    image_dir = SAVE_DIR / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    records = []

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=HEADLESS,
            viewport={"width": 1280, "height": 800},
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.goto(target_url)

        print("浏览器已打开。")
        print("如果是真实网页，需要登录的话，请先手动登录。")
        input("登录/准备完成后，按回车开始采集...")

        buttons = page.locator(QUESTION_BUTTON_SELECTOR)
        count = buttons.count()

        if count == 0:
            print(f"没有找到题号按钮：{QUESTION_BUTTON_SELECTOR}")
            context.close()
            return

        total = count if MAX_QUESTIONS is None else min(count, MAX_QUESTIONS)
        print(f"检测到题号按钮数量：{count}，准备采集：{total} 题")

        for i in range(total):
            print(f"\n正在采集第 {i + 1} 题...")

            btn = buttons.nth(i)
            btn.click()

            time.sleep(CLICK_DELAY)

            question_area = page.locator(QUESTION_CONTENT_SELECTOR)

            try:
                text = question_area.inner_text(timeout=3000).strip()
            except Exception as exc:
                print(f"读取题目文本失败：{exc}")
                text = ""

            image_path = image_dir / f"question_{i + 1:03d}.png"

            try:
                question_area.screenshot(path=str(image_path))
            except Exception as exc:
                print(f"题目区域截图失败，改用整页截图：{exc}")
                page.screenshot(path=str(image_path), full_page=True)

            record = {
                "index": i + 1,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "text": text,
                "image_path": str(image_path),
            }
            records.append(record)

            print(f"文本：{text[:80]}...")
            print(f"截图：{image_path}")

        save_outputs(records)
        context.close()

    print("\n采集完成。")


if __name__ == "__main__":
    main()