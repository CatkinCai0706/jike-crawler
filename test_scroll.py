"""
测试：在关注列表弹窗中滚动加载全部用户
"""
from playwright.sync_api import sync_playwright
import time
import json

TARGET_URL = "https://web.okjike.com/u/E04918BA-823C-4284-B2FA-7E00D0849023"
PROJECT_DIR = "/Users/xiaokang/my_project/jike-crawler"
BROWSER_DATA = f"{PROJECT_DIR}/browser_data"
TARGET_ID = "E04918BA-823C-4284-B2FA-7E00D0849023"


def check_login(page):
    time.sleep(3)
    if "login" in page.url.lower():
        return False
    content = page.content()
    return "关注" in content and "被关注" in content


def extract_users(page):
    """提取当前页面上所有用户链接（去重，排除目标用户自己）"""
    all_links = page.query_selector_all('a[href*="/u/"]')
    users = {}
    for link in all_links:
        href = link.get_attribute("href") or ""
        if "/u/" in href and TARGET_ID not in href:
            name = link.inner_text().strip().split("\n")[0]
            if href not in users:
                users[href] = name
    return users


def run():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DATA,
            headless=False,
            viewport={"width": 1280, "height": 900}
        )
        page = context.new_page()

        print("1. 打开用户主页...")
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)

        if not check_login(page):
            print("\n  请在浏览器中完成登录，登录后按回车...")
            input("按回车继续...")
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

        time.sleep(3)

        # 点击"关注"数字
        print("2. 点击关注数...")
        following_idx = page.evaluate("""() => {
            const stats = document.querySelectorAll('._stat_gw2sk_72');
            for (let i = 0; i < stats.length; i++) {
                const label = stats[i].querySelector('._statLabel_gw2sk_88');
                if (label && label.innerText.trim() === '关注') return i;
            }
            return -1;
        }""")

        if following_idx < 0:
            print("  未找到关注数元素，退出")
            context.close()
            return

        stat_elements = page.query_selector_all('._stat_gw2sk_72')
        stat_elements[following_idx].click()
        time.sleep(3)
        print("  弹窗已打开")

        # 找到弹窗内的可滚动容器
        print("3. 查找弹窗滚动容器...")
        # 弹窗里的列表容器
        scroll_info = page.evaluate("""() => {
            // 找弹窗内的可滚动元素
            const dialogs = document.querySelectorAll('[role="dialog"], [class*="modal"], [class*="Modal"], [class*="drawer"], [class*="Drawer"]');
            const results = [];
            // 也检查所有 div
            const allDivs = document.querySelectorAll('div');
            for (const el of allDivs) {
                if (el.scrollHeight > el.clientHeight + 50 && el.clientHeight > 100 && el.clientHeight < 800) {
                    results.push({
                        className: el.className.substring(0, 120),
                        scrollHeight: el.scrollHeight,
                        clientHeight: el.clientHeight,
                        childCount: el.children.length
                    });
                }
            }
            return {dialogs: dialogs.length, scrollable: results.slice(0, 10)};
        }""")
        print(f"  弹窗数: {scroll_info['dialogs']}")
        for s in scroll_info['scrollable']:
            print(f"  容器: class='{s['className'][:60]}', scrollH={s['scrollHeight']}, clientH={s['clientHeight']}, children={s['childCount']}")

        # 滚动加载全部用户
        print("4. 开始滚动加载...")
        prev_count = 0
        no_change_count = 0

        for i in range(60):  # 最多滚动60次，足够加载118人
            # 滚动弹窗内的列表容器
            page.evaluate("""() => {
                const allDivs = document.querySelectorAll('div');
                for (const el of allDivs) {
                    if (el.scrollHeight > el.clientHeight + 50 && el.clientHeight > 100 && el.clientHeight < 800) {
                        el.scrollTop = el.scrollHeight;
                    }
                }
            }""")
            time.sleep(1)

            users = extract_users(page)
            current_count = len(users)

            if current_count > prev_count:
                print(f"  滚动 {i+1}: {current_count} 个用户")
                prev_count = current_count
                no_change_count = 0
            else:
                no_change_count += 1
                if no_change_count >= 5:
                    print(f"  连续 {no_change_count} 次无新增，停止")
                    break

        # 最终提取
        print("5. 提取最终用户列表...")
        final_users = extract_users(page)
        print(f"  总计: {len(final_users)} 个用户")

        # 保存
        user_list = [{"href": href, "name": name} for href, name in final_users.items()]
        with open(f"{PROJECT_DIR}/user_list.json", "w") as f:
            json.dump(user_list, f, ensure_ascii=False, indent=2)
        print(f"  已保存: user_list.json")

        # 打印前10个
        for u in user_list[:10]:
            print(f"    - {u['name']}: {u['href']}")

        print("\n浏览器 10 秒后关闭...")
        time.sleep(10)
        context.close()


if __name__ == "__main__":
    run()
