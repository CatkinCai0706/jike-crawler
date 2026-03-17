# auto_config.py — 即刻自动关注/私信/评论 配置
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

# ========== Appium 配置 ==========
APPIUM_SERVER = "http://127.0.0.1:4723"
DESIRED_CAPS = {
    "platformName": "Android",
    "automationName": "UiAutomator2",
    "deviceName": "CLB7N20114002953",
    "platformVersion": "10",
    "appPackage": "com.ruguoapp.jike",
    "appActivity": "",      # 留空，使用 deeplink 启动
    "noReset": True,
    "autoGrantPermissions": True,
    "newCommandTimeout": 300,
}

# ========== 防封策略 ==========
# 每次操作间隔（秒）
ACTION_DELAY_MIN = 20
ACTION_DELAY_MAX = 40

# 每处理 N 人后休息
BATCH_SIZE = 50
BATCH_REST_MIN = 300   # 5 分钟
BATCH_REST_MAX = 600   # 10 分钟

# 每日上限
DAILY_LIMIT = 30

# ========== 私信模板 ==========
# 支持 {username} 变量替换
MESSAGE_TEMPLATES = [
    "同学你好，看到你主页也在做AI相关创业，我目前正在做招聘相关的AI Agent创业，想和有过创业经历的朋友交流一下实践经验。想问下你方便加个微信进一步交流嘛？我的vx是：15150660883，方便的话也可以留下你的联系方式～",
    "你好呀，看到你也在做AI方向的创业，我这边在做招聘领域的AI Agent，想跟有创业经验的朋友聊聊。方便加个微信交流一下吗？我vx：15150660883，也欢迎留下你的联系方式～",
    "hi，关注到你在做AI相关的创业，我目前也在创业做招聘方向的AI Agent，很想和同路人交流下经验。方便加微信聊聊吗？我的vx：15150660883，期待认识你～",
    "你好，看到你主页分享的创业内容很有共鸣，我也在做AI Agent创业（招聘方向），想找有经验的朋友交流。方便的话加个微信？我vx是15150660883，也可以留下你的联系方式～",
]

# ========== 文件路径 ==========
# pipeline 爬完后自动生成的待处理用户列表
AUTO_TARGETS_FILE = str(PROJECT_DIR / "auto_targets.json")
# 自动操作进度文件
AUTO_PROGRESS_FILE = str(PROJECT_DIR / "auto_progress.json")
