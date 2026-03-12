"""
测试脚本：探索即刻关注列表页面结构
打开浏览器后暂停等待手动登录，登录后继续探索
"""
from playwright.sync_api import sync_playwright
import time
import json

TARGET_URL = "https://web.okjike.com/u/E04918BA-823C-4284-B2FA-7E00D0849023"
PROJECT_DIR = "/Users/xiaokang/my_project/jike-crawler"

def run():
    with sync_playwright() as p:
        # 使用持久化上下文，保存登录态供后续使用
        context = p.chromium.launch_persistent_context(
            user_data_dir=f"{PROJECT_DIR}/browser_data",
            headless=False,
            viewport={"width": 1280, "height": 900}
        )
        page = context.new_page()

        # 监听网络请求，捕获 API 调用
        api_responses = []
        def handle_response(response):
            url = response.url
            if "api.ruguoapp.com" in url:
                try:
                    body = response.json()
                    api_responses.append({"url": url, "data": body})
                except:
                    pass
        page.on("response", handle_response)

        print("1. 打开即刻网页版...")
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)

        # 检查是否需要登录
        if "login" in page.url.lower() or page.query_selector("[class*='login']"):
            print("\n========================================")
            print("  请在浏览器中完成登录（扫码或手机号）")
            print("  登录成功后回到终端按回车继续...")
            print("========================================\n")
            input("按回车继续...")

            # 登录后重新打开目标页面
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

        page.screenshot(path=f"{PROJECT_DIR}/step1_homepage.png")
        print("2. 主页截图已保存")

        # 查找"关注"数字链接
        print("3. 查找关注数链接...")
        # 打印所有 a 标签的文本和 href
        links = page.query_selector_all("a")
        for link in links:
            text = link.inner_text().strip().replace("\n", " ")
            href = link.get_attribute("href") or ""
            if any(c.isdigit() for c in text) and len(text) < 30:
                print(f"   链接: text='{text}', href='{href}'")

        # 尝试找包含 "following" 的链接或包含数字+关注的元素
        following_el = None
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            if "following" in href.lower():
                following_el = link
                print(f"   >>> 命中: text='{text}', href='{href}'")
                break

        if not following_el:
            # 备选：找包含"关注"且有数字的元素
            for link in links:
                text = link.inner_text().strip()
                if "关注" in text and "被关注" not in text and any(c.isdigit() for c in text):
                    following_el = link
                    print(f"   >>> 备选命中: text='{text}'")
                    break

        if following_el:
            print("4. 点击关注数...")
            following_el.click()
            time.sleep(3)
            page.screenshot(path=f"{PROJECT_DIR}/step2_following_list.png")
            print("   关注列表截图已保存")

            # 提取当前可见的用户链接
            print("5. 提取用户列表...")
            user_links = []
            all_links = page.query_selector_all("a[href*='/u/']")
            target_path = "/u/E04918BA-823C-4284-B2FA-7E00D0849023"
            for link in all_links:
                href = link.get_attribute("href") or ""
                if "/u/" in href and target_path not in href and href not in [l["href"] for l in user_links]:
                    name = link.inner_text().strip().split("\n")[0]
                    user_links.append({"href": href, "name": name})

            print(f"   初始可见用户数: {len(user_links)}")
            for u in user_links[:5]:
                print(f"   - {u['name']}: {u['href']}")

            # 尝试滚动加载更多
            print("6. 滚动加载更多...")
            # 找可滚动容器
            scrollable_info = page.evaluate("""() => {
                const elements = document.querySelectorAll('div');
                const results = [];
                for (const el of elements) {
                    if (el.scrollHeight > el.clientHeight + 100 && el.clientHeight > 200) {
                        results.push({
                            tag: el.tagName,
                            className: el.className.substring(0, 100),
                            id: el.id,
                            scrollHeight: el.scrollHeight,
                            clientHeight: el.clientHeight,
                            childCount: el.children.length
                        });
                    }
                }
                return results.sort((a, b) => b.childCount - a.childCount);
            }""")
            print(f"   可滚动容器: {json.dumps(scrollable_info[:3], ensure_ascii=False, indent=2)}")

            prev_count = len(user_links)
            for i in range(20):
                # 滚动所有可能的容器
                page.evaluate("""() => {
                    const elements = document.querySelectorAll('div');
                    for (const el of elements) {
                        if (el.scrollHeight > el.clientHeight + 100 && el.clientHeight > 200) {
                            el.scrollTop = el.scrollHeight;
                        }
                    }
                }""")
                time.sleep(1.5)

                # 重新统计
                all_links = page.query_selector_all("a[href*='/u/']")
                current_links = set()
                for link in all_links:
                    href = link.get_attribute("href") or ""
                    if "/u/" in href and target_path not in href:
                        current_links.add(href)

                current_count = len(current_links)
                if current_count > prev_count:
                    print(f"   滚动 {i+1}: {current_count} 个用户")
                    prev_count = current_count
                else:
                    print(f"   滚动 {i+1}: 无新增 ({current_count})，再试一次...")
                    if i > 2 and current_count == prev_count:
                        print(f"   连续无新增，停止滚动")
                        break

            # 最终提取完整列表
            print("7. 提取最终用户列表...")
            all_links = page.query_selector_all("a[href*='/u/']")
            final_users = {}
            for link in all_links:
                href = link.get_attribute("href") or ""
                if "/u/" in href and target_path not in href:
                    name = link.inner_text().strip().split("\n")[0]
                    if href not in final_users:
                        final_users[href] = name

            print(f"   最终用户数: {len(final_users)}")
            with open(f"{PROJECT_DIR}/user_list.json", "w") as f:
                json.dump([{"href": k, "name": v} for k, v in final_users.items()], f, ensure_ascii=False, indent=2)
            print("   用户列表已保存: user_list.json")

        else:
            print("   未找到关注数链接，保存页面 HTML 供分析...")
            with open(f"{PROJECT_DIR}/page_html.html", "w") as f:
                f.write(page.content())

        # 保存 API 响应
        print(f"\n8. 捕获到 {len(api_responses)} 个 API 响应")
        # 只保存关键的
        interesting = [r for r in api_responses if "follow" in r["url"].lower() or "user" in r["url"].lower()]
        with open(f"{PROJECT_DIR}/api_responses.json", "w") as f:
            json.dump(interesting if interesting else api_responses[:10], f, ensure_ascii=False, indent=2)
        print("   API 响应已保存")

        print("\n浏览器将在 10 秒后关闭...")
        time.sleep(10)
        context.close()

if __name__ == "__main__":
    run()
