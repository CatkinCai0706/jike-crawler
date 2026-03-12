"""
调试：保存弹窗打开后的完整 HTML，分析滚动容器结构
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

        # 点击关注数
        following_idx = page.evaluate("""() => {
            const stats = document.querySelectorAll('._stat_gw2sk_72');
            for (let i = 0; i < stats.length; i++) {
                const label = stats[i].querySelector('._statLabel_gw2sk_88');
                if (label && label.innerText.trim() === '关注') return i;
            }
            return -1;
        }""")
        stat_elements = page.query_selector_all('._stat_gw2sk_72')
        stat_elements[following_idx].click()
        time.sleep(3)

        # 找弹窗相关的所有可滚动元素，包括大的
        scroll_info = page.evaluate("""() => {
            const results = [];
            const allDivs = document.querySelectorAll('*');
            for (const el of allDivs) {
                const style = window.getComputedStyle(el);
                const overflowY = style.overflowY;
                if (el.scrollHeight > el.clientHeight + 20 && el.clientHeight > 50) {
                    results.push({
                        tag: el.tagName,
                        className: el.className.substring(0, 150),
                        id: el.id,
                        scrollHeight: el.scrollHeight,
                        clientHeight: el.clientHeight,
                        overflowY: overflowY,
                        role: el.getAttribute('role') || '',
                        childCount: el.children.length
                    });
                }
            }
            return results;
        }""")

        print(f"所有可滚动元素 ({len(scroll_info)}):")
        for s in scroll_info:
            print(f"  tag={s['tag']}, class='{s['className'][:80]}', role='{s['role']}', overflow={s['overflowY']}, scrollH={s['scrollHeight']}, clientH={s['clientHeight']}, children={s['childCount']}")

        # 找弹窗/modal 相关元素
        modal_info = page.evaluate("""() => {
            const results = [];
            // 找 mantine Modal/Drawer 相关
            const modals = document.querySelectorAll('[class*="Modal"], [class*="modal"], [class*="Drawer"], [class*="drawer"], [class*="Overlay"], [role="dialog"]');
            for (const el of modals) {
                results.push({
                    tag: el.tagName,
                    className: el.className.substring(0, 150),
                    role: el.getAttribute('role') || '',
                    childCount: el.children.length,
                    innerHTML: el.innerHTML.substring(0, 300)
                });
            }
            return results;
        }""")

        print(f"\n弹窗相关元素 ({len(modal_info)}):")
        for m in modal_info:
            print(f"  tag={m['tag']}, class='{m['className'][:80]}', role='{m['role']}', children={m['childCount']}")
            print(f"    html preview: {m['innerHTML'][:200]}")

        # 保存弹窗区域的 HTML
        dialog_html = page.evaluate("""() => {
            // 找包含"TA关注的人"的最近父容器
            const allEls = document.querySelectorAll('*');
            for (const el of allEls) {
                const text = el.innerText || '';
                if (text.includes('TA关注的人') && el.children.length > 2 && el.innerHTML.length > 500 && el.innerHTML.length < 100000) {
                    return {
                        tag: el.tagName,
                        className: el.className,
                        html: el.innerHTML.substring(0, 5000)
                    };
                }
            }
            return null;
        }""")

        if dialog_html:
            print(f"\n弹窗容器: tag={dialog_html['tag']}, class={dialog_html['className'][:80]}")
            with open(f"{PROJECT_DIR}/dialog_html.html", "w") as f:
                f.write(dialog_html['html'])
            print("弹窗 HTML 已保存: dialog_html.html")
        else:
            print("\n未找到包含'TA关注的人'的容器")

        time.sleep(5)
        context.close()


if __name__ == "__main__":
    run()
