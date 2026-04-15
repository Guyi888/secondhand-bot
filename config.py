# =============================================================================
#  secondhand-bot 配置文件
#  ⚠️  以后只改这个文件，bot.py 不用动
# =============================================================================

# ── Telegram 配置 ─────────────────────────────────────────────────────────────
BOT_TOKEN    = "YOUR_BOT_TOKEN_HERE"       # 填入你的 Bot Token
ADMIN_ID     = 0                           # 填入你的 Telegram 用户 ID（数字）
CHANNEL_ID   = "@your_channel"             # 发布频道，例：@malaixiyaershouqun
CHANNEL_NAME = "your_channel_name"         # 频道用户名（不带@）
GROUP_ID     = "@your_group"               # 讨论群组
GROUP_LINK   = "https://t.me/your_group"   # 群组完整链接

# ── 投稿编号起始值（首次运行用，之后从数据库读取）─────────────────────────────
COUNTER_START = 1000000
