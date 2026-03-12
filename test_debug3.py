"""
调试：尝试不同的点击方式打开关注列表弹窗
"""
from playwright.sync_api import sync_playwright
import time

TARGET_URL = "https://web.okjike.com/u/E04918BA-823C-4284-B2FA-7E00D0849023"
PROJECT_DIR = "/Users/xiaokang/my_project/jike-crawler"
BROWSER_DATA = f"{PROJECT_DIR}/browser_data"


def check_login(page):
    time.sleep(3)
    if "login" in page.url.lower():
        return False
    content = page.content()
    return "关注" in content and "被关注" in content


def run():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DATA,
            headless=False,
            viewport={"width": 1280, "height": 900}
        )
        page = context.new_page()

        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        if not check_login(page):
            print("请登录后按回车...")
            input()
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

        time.sleep(3)

        # 方法1：点击 span._statCount（"118"数字）
        print("=== 方法1：点击 118 数字 span ===")
        count_el = page.evaluate("""() => {
            const stats = document.querySelectorAll('._stat_gw2sk_72');
            for (const stat of stats) {
                const label = stat.querySelector('._statLabel_gw2sk_88');
                if (label && label.innerText.trim() === '关注') {
                    const count = stat.querySelector('._statCount_gw2sk_82');
                    if (count) {
                        const rect = count.getBoundingClientRect();
                        return {text: count.innerText, x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                    }
                }
            }
            return null;
        }""")

        if count_el:
            print(f"  找到: text='{count_el['text']}', 坐标=({count_el['x']}, {count_el['y']})")
            # 用坐标点击
            page.mouse.click(count_el['x'], count_el['y'])
            time.sleep(3)
            page.screenshot(path=f"{PROJECT_DIR}/debug_method1.png")

            # 检查是否有弹窗
            has_dialog = page.evaluate("""() => {
                const els = document.querySelectorAll('[class*="dcsra"], [class*="TA关注"]');
                if (els.length > 0) return true;
                // 检查 modal 是否有内容了
                const modals = document.querySelectorAll('.mantine-Modal-root');
                for (const m of modals) {
                    if (m.children.length > 0 && m.innerHTML.length > 100) return true;
                }
                // 检查 role=dialog 是否有内容
                const dialogs = document.querySelectorAll('[role="dialog"]');
                for (const d of dialogs) {
                    if (d.innerHTML.length > 100) return true;
                }
                return false;
            }""")
            print(f"  弹窗出现: {has_dialog}")

            if not has_dialog:
                # 方法2：用 JavaScript 直接触发 click 事件
                print("\n=== 方法2：JS dispatch click ===")
                page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(4)

                page.evaluate("""() => {
                    const stats = document.querySelectorAll('._stat_gw2sk_72');
                    for (const stat of stats) {
                        const label = stat.querySelector('._statLabel_gw2sk_88');
                        if (label && label.innerText.trim() === '关注') {
                            stat.click();
                            return;
                        }
                    }
                }""")
                time.sleep(3)
                page.screenshot(path=f"{PROJECT_DIR}/debug_method2.png")

                has_dialog2 = page.evaluate("""() => {
                    const modals = document.querySelectorAll('.mantine-Modal-root');
                    for (const m of modals) {
                        if (m.children.length > 0 && m.innerHTML.length > 100) return 'modal: ' + m.innerHTML.substring(0, 200);
                    }
                    const dialogs = document.querySelectorAll('[role="dialog"]');
                    for (const d of dialogs) {
                        if (d.innerHTML.length > 100) return 'dialog: ' + d.innerHTML.substring(0, 200);
                    }
                    return null;
                }""")
                print(f"  弹窗: {has_dialog2}")

                if not has_dialog2:
                    # 方法3：直接导航到 following 页面
                    print("\n=== 方法3：直接访问 following URL ===")
                    page.goto(f"{TARGET_URL}/following", wait_until="domcontentloaded", timeout=60000)
                    time.sleep(4)
                    page.screenshot(path=f"{PROJECT_DIR}/debug_method3.png")
                    print(f"  URL: {page.url}")

                    # 检查页面内容
                    content_check = page.evaluate("""() => {
                        const text = document.body.innerText;
                        const hasFollowing = text.includes('TA关注的人') || text.includes('关注的人');
                        const userLinks = document.querySelectorAll('a[href*="/u/"]');
                        return {
                            hasFollowingTitle: hasFollowing,
                            userLinkCount: userLinks.length,
                            bodyTextPreview: text.substring(0, 500)
                        };
                    }""")
                    print(f"  有关注标题: {content_check['hasFollowingTitle']}")
                    print(f"  用户链接数: {content_check['userLinkCount']}")
                    print(f"  页面文本: {content_check['bodyTextPreview'][:200]}")

        time.sleep(5)
        context.close()


if __name__ == "__main__":
    run()
