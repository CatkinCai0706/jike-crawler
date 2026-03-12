"""
测试脚本（修正版）：
1. 打开用户主页，提取页面信息
2. 点击"118关注"（div._stat_gw2sk_72），打开关注列表
"""
from playwright.sync_api import sync_playwright
import time
import json

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

        print("1. 打开用户主页...")
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)

        if not check_login(page):
            print("\n========================================")
            print("  请在浏览器中完成登录")
            print("  登录成功后回到终端按回车")
            print("  （登录态会自动保存，下次不用再登）")
            print("========================================\n")
            input("按回车继续...")
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

        # === 测试1：提取用户主页信息 ===
        print("\n=== 测试1：提取用户主页信息 ===")
        time.sleep(3)

        user_info = page.evaluate("""() => {
            const result = {};
            // 用户名
            const nameEl = document.querySelector('._screenName_gw2sk_66 a');
            if (nameEl) result.username = nameEl.innerText.trim();
            // 简介
            const bioEl = document.querySelector('._bio_gw2sk_108');
            if (bioEl) result.bio = bioEl.innerText.trim();
            // 标签
            const tags = document.querySelectorAll('._tagsSection_gw2sk_114 ._root_jshjf_1');
            result.tags = Array.from(tags).map(t => t.innerText.trim());
            // 关注数、被关注数
            const stats = document.querySelectorAll('._stat_gw2sk_72');
            stats.forEach(stat => {
                const count = stat.querySelector('._statCount_gw2sk_82');
                const label = stat.querySelector('._statLabel_gw2sk_88');
                if (count && label) {
                    const labelText = label.innerText.trim();
                    const countText = count.innerText.trim();
                    if (labelText === '关注') result.following = countText;
                    else if (labelText === '被关注') result.followers = countText;
                    else if (labelText === '夸夸') result.likes = countText;
                }
            });
            return result;
        }""")

        print(f"  用户名: {user_info.get('username', '?')}")
        print(f"  简介: {user_info.get('bio', '?')}")
        print(f"  关注: {user_info.get('following', '?')}")
        print(f"  被关注: {user_info.get('followers', '?')}")
        print(f"  夸夸: {user_info.get('likes', '?')}")
        print(f"  标签: {user_info.get('tags', [])}")

        # === 测试2：点击"118关注"打开关注列表 ===
        print("\n=== 测试2：点击关注数，打开关注列表 ===")

        # 找到"关注"那个 stat div（不是"被关注"）
        following_stat = page.evaluate("""() => {
            const stats = document.querySelectorAll('._stat_gw2sk_72');
            for (let i = 0; i < stats.length; i++) {
                const label = stats[i].querySelector('._statLabel_gw2sk_88');
                if (label && label.innerText.trim() === '关注') {
                    return i;
                }
            }
            return -1;
        }""")

        if following_stat >= 0:
            print(f"  找到关注数元素（第 {following_stat} 个 stat）")
            stat_elements = page.query_selector_all('._stat_gw2sk_72')
            stat_elements[following_stat].click()
            print("  已点击，等待弹窗...")
            time.sleep(3)

            page.screenshot(path=f"{PROJECT_DIR}/test_following_list.png")
            print(f"  截图已保存: test_following_list.png")

            # 检查弹窗是否出现
            dialog_title = page.evaluate("""() => {
                // 查找弹窗标题
                const els = document.querySelectorAll('div, h2, h3, span');
                for (const el of els) {
                    if (el.innerText && el.innerText.includes('TA关注的人')) {
                        return el.innerText.trim();
                    }
                }
                return null;
            }""")

            if dialog_title:
                print(f"  弹窗已打开: {dialog_title}")
            else:
                print("  未检测到弹窗标题，看截图确认")

            # 统计可见用户数
            user_items = page.query_selector_all('a[href*="/u/"]')
            target_id = "E04918BA-823C-4284-B2FA-7E00D0849023"
            users = []
            for item in user_items:
                href = item.get_attribute("href") or ""
                if "/u/" in href and target_id not in href and href not in [u['href'] for u in users]:
                    name = item.inner_text().strip().split("\n")[0]
                    users.append({"href": href, "name": name})

            print(f"  当前可见用户数: {len(users)}")
            for u in users[:5]:
                print(f"    - {u['name']}: {u['href']}")
        else:
            print("  未找到关注数元素！")

        print("\n测试完成，浏览器 10 秒后关闭...")
        time.sleep(10)
        context.close()


if __name__ == "__main__":
    run()
