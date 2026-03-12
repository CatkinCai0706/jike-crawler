"""
获取 Token 的独立脚本（手动登录版）
"""
from playwright.sync_api import sync_playwright
import time

PROJECT_DIR = "/Users/xiaokang/my_project/jike-crawler"
BROWSER_DATA = f"{PROJECT_DIR}/browser_data"
TOKEN_FILE = f"{PROJECT_DIR}/token.txt"

print("打开浏览器，请在浏览器中登录即刻...")
print("登录成功后，脚本会自动检测并保存 Token")
print("检测到 Token 后浏览器会自动关闭\n")

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=BROWSER_DATA,
        headless=False,
        viewport={"width": 1280, "height": 900},
    )
    page = context.new_page()

    captured = {}

    def on_request(request):
        if "api.ruguoapp.com" in request.url:
            t = request.headers.get("x-jike-access-token", "")
            if t:
                captured["token"] = t
                print(f"✓ 检测到 Token: {t[:50]}...")

    page.on("request", on_request)
    page.goto("https://web.okjike.com/", wait_until="domcontentloaded", timeout=60000)

    # 循环检测，直到拿到 Token
    max_wait = 300  # 最多等待5分钟
    waited = 0

    while not captured.get("token") and waited < max_wait:
        time.sleep(2)
        waited += 2

        # 尝试从 localStorage 读取
        try:
            token_from_storage = page.evaluate("() => localStorage.getItem('JK_ACCESS_TOKEN')")
            if token_from_storage:
                captured["token"] = token_from_storage
                print(f"✓ 从 localStorage 获取到 Token")
                break
        except:
            pass

        # 每10秒提示一次
        if waited % 10 == 0:
            print(f"等待登录中... ({waited}s)")

    context.close()

    token = captured.get("token", "")
    if token:
        with open(TOKEN_FILE, "w") as f:
            f.write(token)
        print(f"\n✓ Token 已保存到 {TOKEN_FILE}")
        print("现在可以运行爬虫了")
    else:
        print("\n✗ 未获取到 Token，请确认已登录")
