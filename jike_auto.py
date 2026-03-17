"""
jike_auto.py — Appium 自动化：批量关注即刻用户 + 发私信/评论
用法: python3 jike_auto.py [--test N]  (--test N 只处理前 N 个用户)

数据来源：jike_pipeline.py 爬取分析后自动生成的 auto_targets.json
"""

import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from auto_config import (
    ACTION_DELAY_MIN,
    ACTION_DELAY_MAX,
    APPIUM_SERVER,
    AUTO_TARGETS_FILE,
    AUTO_PROGRESS_FILE,
    BATCH_REST_MAX,
    BATCH_REST_MIN,
    BATCH_SIZE,
    DAILY_LIMIT,
    DESIRED_CAPS,
    MESSAGE_TEMPLATES,
)


# ========== 进度管理 ==========

def load_progress() -> dict:
    """加载进度文件，支持断点续传"""
    if os.path.exists(AUTO_PROGRESS_FILE):
        with open(AUTO_PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"processed": {}, "daily_counts": {}}


def save_progress(progress: dict):
    with open(AUTO_PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def get_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def today_count(progress: dict) -> int:
    return progress.get("daily_counts", {}).get(get_today(), 0)


def increment_today(progress: dict):
    today = get_today()
    if "daily_counts" not in progress:
        progress["daily_counts"] = {}
    progress["daily_counts"][today] = progress["daily_counts"].get(today, 0) + 1


# ========== ADB 工具 ==========

def adb_open_deeplink(user_id: str) -> bool:
    """通过 adb 打开即刻用户 deeplink"""
    deeplink = f"jike://page.jk/user/{user_id}"
    try:
        subprocess.run(
            ["adb", "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", deeplink],
            capture_output=True, text=True, timeout=10,
        )
        return True
    except Exception as e:
        print(f"  adb deeplink 失败: {e}")
        return False


def adb_go_back():
    """adb 模拟返回键"""
    subprocess.run(["adb", "shell", "input", "keyevent", "4"], capture_output=True, timeout=5)


# ========== Appium 操作 ==========

def init_driver() -> webdriver.Remote:
    """初始化 Appium driver"""
    options = UiAutomator2Options()
    for key, value in DESIRED_CAPS.items():
        if value:  # 跳过空值
            options.set_capability(key, value)

    driver = webdriver.Remote(APPIUM_SERVER, options=options)
    driver.implicitly_wait(5)
    return driver


def random_delay(min_s: float = ACTION_DELAY_MIN, max_s: float = ACTION_DELAY_MAX):
    """随机等待"""
    delay = random.uniform(min_s, max_s)
    print(f"  等待 {delay:.1f}s...")
    time.sleep(delay)


def wait_for_page_load(driver: webdriver.Remote, timeout: int = 10):
    """等待用户主页加载完成"""
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((AppiumBy.ID,
                "com.ruguoapp.jike:id/btnFollow"))
        )
        return True
    except TimeoutException:
        try:
            driver.find_element(AppiumBy.ID, "com.ruguoapp.jike:id/tvUsername")
            return True
        except Exception:
            return False


def find_and_click_follow(driver: webdriver.Remote) -> str:
    """
    找到并点击关注按钮
    返回: "followed" / "already_followed" / "not_found"
    """
    try:
        follow_btn = driver.find_elements(AppiumBy.ID, "com.ruguoapp.jike:id/btnFollow")
        if not follow_btn:
            print("  未找到关注按钮")
            return "not_found"

        btn_text = ""
        try:
            text_el = follow_btn[0].find_element(AppiumBy.CLASS_NAME, "android.widget.TextView")
            btn_text = text_el.text
        except Exception:
            pass

        if btn_text in ("已关注", "互相关注"):
            print(f"  已关注（{btn_text}），跳过")
            return "already_followed"

        if btn_text == "关注":
            follow_btn[0].click()
            time.sleep(1.5)
            print("  关注成功")
            return "followed"

        print(f"  关注按钮文本: '{btn_text}'，尝试点击")
        follow_btn[0].click()
        time.sleep(1.5)
        return "followed"

    except Exception as e:
        print(f"  关注操作异常: {e}")
        return "not_found"


def send_message(driver: webdriver.Remote, message: str) -> bool:
    """点击私信按钮并发送消息"""
    try:
        msg_btn = driver.find_elements(AppiumBy.ID, "com.ruguoapp.jike:id/layLetter")
        if not msg_btn:
            print("  未找到私信按钮")
            return False

        msg_btn[0].click()
        time.sleep(3)

        input_box = None
        for selector in [
            (AppiumBy.CLASS_NAME, "android.widget.EditText"),
            (AppiumBy.XPATH, "//*[contains(@resource-id, 'input') or contains(@resource-id, 'edit') or contains(@resource-id, 'et_')]"),
        ]:
            elements = driver.find_elements(*selector)
            if elements:
                input_box = elements[0]
                break

        if not input_box:
            print("  未找到输入框")
            adb_go_back()
            return False

        input_box.click()
        time.sleep(0.5)
        input_box.send_keys(message)
        time.sleep(1)

        send_btn = None
        for selector in [
            (AppiumBy.ID, "com.ruguoapp.jike:id/laySend"),
            (AppiumBy.XPATH, "//*[@text='发送']"),
            (AppiumBy.XPATH, "//*[contains(@resource-id, 'send')]"),
        ]:
            elements = driver.find_elements(*selector)
            if elements:
                send_btn = elements[0]
                break

        if not send_btn:
            print("  未找到发送按钮")
            adb_go_back()
            return False

        send_btn.click()
        time.sleep(1.5)
        print("  私信发送成功")

        adb_go_back()
        time.sleep(1)
        return True

    except Exception as e:
        print(f"  私信操作异常: {e}")
        adb_go_back()
        return False


def comment_on_latest_post(driver: webdriver.Remote, message: str) -> bool:
    """在用户最新一条动态下评论"""
    try:
        screen_size = driver.get_window_size()
        sx = screen_size["width"] // 2
        sy_start = int(screen_size["height"] * 0.75)
        sy_end = int(screen_size["height"] * 0.35)
        driver.swipe(sx, sy_start, sx, sy_end, duration=500)
        time.sleep(1.5)

        comment_icons = driver.find_elements(AppiumBy.ID, "com.ruguoapp.jike:id/ivComment")
        if not comment_icons:
            print("  未找到动态评论图标")
            return False

        comment_icons[0].click()
        time.sleep(3)

        input_box = driver.find_elements(AppiumBy.ID, "com.ruguoapp.jike:id/etInput")
        if not input_box:
            input_box = driver.find_elements(AppiumBy.CLASS_NAME, "android.widget.EditText")
        if not input_box:
            print("  未找到评论输入框")
            adb_go_back()
            return False

        input_box[0].click()
        time.sleep(0.5)
        input_box[0].send_keys(message)
        time.sleep(1)

        send_btn = driver.find_elements(AppiumBy.ID, "com.ruguoapp.jike:id/laySend")
        if not send_btn:
            send_btn = driver.find_elements(AppiumBy.XPATH, "//*[@text='发送']")
        if not send_btn:
            print("  未找到评论发送按钮")
            adb_go_back()
            return False

        send_btn[0].click()
        time.sleep(1.5)
        print("  评论发送成功")

        adb_go_back()
        time.sleep(1)
        return True

    except Exception as e:
        print(f"  评论操作异常: {e}")
        adb_go_back()
        return False


def search_user_fallback(driver: webdriver.Remote, username: str) -> bool:
    """备选方案：通过搜索找到用户（deeplink 不生效时使用）"""
    try:
        adb_go_back()
        time.sleep(1)
        adb_go_back()
        time.sleep(1)

        search_btn = driver.find_elements(AppiumBy.XPATH,
            "//*[contains(@resource-id, 'search') or @content-desc='搜索']")
        if not search_btn:
            return False

        search_btn[0].click()
        time.sleep(1)

        search_input = driver.find_elements(AppiumBy.XPATH, "//android.widget.EditText")
        if not search_input:
            return False

        search_input[0].click()
        search_input[0].send_keys(username)
        time.sleep(1)

        driver.press_keycode(66)  # KEYCODE_ENTER
        time.sleep(2)

        user_tab = driver.find_elements(AppiumBy.XPATH, "//*[@text='用户']")
        if user_tab:
            user_tab[0].click()
            time.sleep(1)

        results = driver.find_elements(AppiumBy.XPATH,
            f"//*[contains(@text, '{username}')]")
        if results:
            results[0].click()
            time.sleep(2)
            return True

        return False

    except Exception as e:
        print(f"  搜索备选方案异常: {e}")
        return False


def check_for_anomaly(driver: webdriver.Remote) -> bool:
    """检测验证码或异常弹窗"""
    try:
        for xpath in [
            "//*[contains(@resource-id, 'captcha')]",
            "//*[contains(@resource-id, 'verify')]",
            "//*[contains(@resource-id, 'dialog') and contains(@text, '验证')]",
            "//*[contains(@resource-id, 'dialog') and contains(@text, '频繁')]",
            "//*[contains(@resource-id, 'dialog') and contains(@text, '限制')]",
        ]:
            elements = driver.find_elements(AppiumBy.XPATH, xpath)
            if elements:
                return True

        alerts = driver.find_elements(AppiumBy.ID, "android:id/message")
        for alert in alerts:
            text = alert.text or ""
            if any(kw in text for kw in ["验证码", "操作频繁", "操作限制", "安全验证", "账号异常"]):
                return True

    except Exception:
        pass
    return False


# ========== 主流程 ==========

def process_user(driver: webdriver.Remote, user: dict) -> dict:
    """处理单个用户：关注 + 私信/评论"""
    user_id = user["user_id"]
    username = user["username"]
    result = {"follow": "skipped", "message": "skipped", "error": None}

    print(f"\n处理: {username} ({user_id})")

    # 1. 打开用户主页
    if not adb_open_deeplink(user_id):
        if not search_user_fallback(driver, username):
            result["error"] = "无法打开用户主页"
            return result

    time.sleep(3)

    # 2. 检测异常
    if check_for_anomaly(driver):
        result["error"] = "检测到异常/验证码，暂停"
        return result

    # 3. 等待页面加载
    if not wait_for_page_load(driver):
        print("  页面加载超时，尝试搜索")
        if not search_user_fallback(driver, username):
            result["error"] = "页面加载失败"
            return result
        time.sleep(2)

    # 4. 关注
    result["follow"] = find_and_click_follow(driver)
    time.sleep(1)

    # 5. 私信或评论
    template = random.choice(MESSAGE_TEMPLATES)
    message = template.replace("{username}", username)

    has_letter = driver.find_elements(AppiumBy.ID, "com.ruguoapp.jike:id/layLetter")
    if has_letter:
        msg_ok = send_message(driver, message)
        result["message"] = "sent" if msg_ok else "failed"
    else:
        print("  无私信按钮，重新进入主页准备评论")
        adb_go_back()
        time.sleep(1)
        adb_open_deeplink(user_id)
        time.sleep(3)
        if not wait_for_page_load(driver):
            result["message"] = "no_comment"
            return result

        comment_ok = comment_on_latest_post(driver, message)
        result["message"] = "commented" if comment_ok else "no_comment"

    # 6. 返回
    adb_go_back()
    time.sleep(1)

    return result


def main():
    # 解析参数
    test_count = None
    if "--test" in sys.argv:
        idx = sys.argv.index("--test")
        if idx + 1 < len(sys.argv):
            test_count = int(sys.argv[idx + 1])
            print(f"测试模式：只处理前 {test_count} 个用户")

    # 加载数据
    if not os.path.exists(AUTO_TARGETS_FILE):
        print(f"目标用户文件 {AUTO_TARGETS_FILE} 不存在")
        print("请先运行 jike_pipeline.py 爬取技术人员，会自动生成该文件")
        sys.exit(1)

    with open(AUTO_TARGETS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
    print(f"共 {len(users)} 个目标用户")

    # 加载进度
    progress = load_progress()
    processed = progress.get("processed", {})

    # 过滤已处理的
    pending = [u for u in users if u["user_id"] not in processed]
    print(f"待处理: {len(pending)} 个")

    if test_count:
        pending = pending[:test_count]

    # 检查每日上限
    if today_count(progress) >= DAILY_LIMIT:
        print(f"今日已达上限 {DAILY_LIMIT}，明天继续")
        sys.exit(0)

    # 初始化 Appium
    print("连接 Appium...")
    driver = init_driver()
    print("Appium 连接成功")

    batch_counter = 0

    try:
        for i, user in enumerate(pending):
            if today_count(progress) >= DAILY_LIMIT:
                print(f"\n今日已达上限 {DAILY_LIMIT}，停止")
                break

            result = process_user(driver, user)

            if result.get("error") and "异常" in result["error"]:
                print(f"\n  {result['error']}")
                print("请手动处理后按 Enter 继续，或输入 q 退出...")
                user_input = input()
                if user_input.strip().lower() == "q":
                    break
                continue

            processed[user["user_id"]] = {
                "username": user["username"],
                "result": result,
                "time": datetime.now().isoformat(),
            }
            progress["processed"] = processed
            increment_today(progress)
            save_progress(progress)

            batch_counter += 1
            done_today = today_count(progress)
            print(f"  进度: 今日 {done_today}/{DAILY_LIMIT}, 本批次 {batch_counter}/{BATCH_SIZE}")

            if batch_counter >= BATCH_SIZE:
                rest = random.uniform(BATCH_REST_MIN, BATCH_REST_MAX)
                print(f"\n已处理 {BATCH_SIZE} 人，休息 {rest/60:.1f} 分钟...")
                time.sleep(rest)
                batch_counter = 0
            else:
                random_delay()

    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"\n运行异常: {e}")
    finally:
        save_progress(progress)
        try:
            driver.quit()
        except Exception:
            pass

    # 统计
    total_processed = len(processed)
    followed = sum(1 for v in processed.values() if v["result"]["follow"] == "followed")
    already_followed = sum(1 for v in processed.values() if v["result"]["follow"] == "already_followed")
    messaged = sum(1 for v in processed.values() if v["result"]["message"] == "sent")
    commented = sum(1 for v in processed.values() if v["result"]["message"] == "commented")
    failed = sum(1 for v in processed.values() if v["result"]["message"] in ("failed", "no_comment"))
    print(f"\n完成! 总处理: {total_processed}, 新关注: {followed}, 已关注: {already_followed}, 私信: {messaged}, 评论: {commented}, 失败: {failed}")


if __name__ == "__main__":
    main()
