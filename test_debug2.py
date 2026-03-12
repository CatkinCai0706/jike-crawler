"""
调试：点击关注数后，检查 URL 变化和页面实际内容
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
        print(f"点击前 URL: {page.url}")

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
        time.sleep(4)

        print(f"点击后 URL: {page.url}")
        page.screenshot(path=f"{PROJECT_DIR}/debug_after_click.png")

        # 看看页面上有哪些文本包含"关注"
        texts = page.evaluate("""() => {
            const results = [];
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            while (walker.nextNode()) {
                const text = walker.currentNode.textContent.trim();
                if (text.includes('关注') && text.length < 100) {
                    const parent = walker.currentNode.parentElement;
                    results.push({
                        text: text,
                        parentTag: parent.tagName,
                        parentClass: parent.className.substring(0, 80)
                    });
                }
            }
            return results;
        }""")
        print(f"\n包含'关注'的文本节点:")
        for t in texts:
            print(f"  '{t['text']}' -> {t['parentTag']}.{t['parentClass'][:50]}")

        # 看看 item_dcsra_15 这个 class 是否存在（图5里看到的用户列表项）
        items = page.query_selector_all('[class*="item_dcsra"]')
        print(f"\nitem_dcsra 元素数: {len(items)}")

        # 看看 dcsra 相关的所有 class
        dcsra = page.evaluate("""() => {
            const els = document.querySelectorAll('[class*="dcsra"]');
            return Array.from(els).map(el => ({
                tag: el.tagName,
                class: el.className.substring(0, 100),
                text: el.innerText.substring(0, 80).replace(/\\n/g, ' ')
            }));
        }""")
        print(f"\ndcsra 相关元素 ({len(dcsra)}):")
        for d in dcsra:
            print(f"  {d['tag']}.{d['class'][:60]} -> '{d['text'][:60]}'")

        # 保存完整页面 HTML 的关键部分
        page_html = page.content()
        with open(f"{PROJECT_DIR}/debug_full_page.html", "w") as f:
            f.write(page_html)
        print(f"\n完整 HTML 已保存: debug_full_page.html ({len(page_html)} bytes)")

        time.sleep(5)
        context.close()


if __name__ == "__main__":
    run()
