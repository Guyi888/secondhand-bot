import asyncio
import logging
import os
import time
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto, InputMediaVideo, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ── 配置 ──────────────────────────────────────────────────────────────────────
BOT_TOKEN    = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID     = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID   = os.getenv("CHANNEL_ID", "@your_channel")
CHANNEL_NAME = "malaixiyaershouqun"
GROUP_ID     = "@damajiaoliu"
GROUP_LINK   = "https://t.me/damajiaoliu"

# ── 投稿编号 ──────────────────────────────────────────────────────────────────
submission_counter = 1009527

def next_submission_number():
    global submission_counter
    submission_counter += 1
    return submission_counter

# ── 点赞/点踩存储 ─────────────────────────────────────────────────────────────
vote_data = {}
vote_users = {}

# ── 广告存储 ──────────────────────────────────────────────────────────────────
ads = []

# ── 已售出记录 {number: {"btn_msg_id": int, "user_id": int}} ──────────────────
sold_posts = {}

# ── 分类配置 ──────────────────────────────────────────────────────────────────
CATEGORIES = [
    "📱 手机数码",
    "💻 电脑周边",
    "🏠 家居家电",
    "👕 衣物鞋包",
    "🚗 汽车配件",
    "📚 书籍教育",
    "🎮 游戏娱乐",
    "🔧 其他杂物",
]

# 关键词 → 分类（用于智能预判）
CATEGORY_KEYWORDS = {
    "📱 手机数码": [
        "手机", "iphone", "samsung", "三星", "小米", "华为", "oppo", "vivo",
        "realme", "充电器", "充电宝", "耳机", "数码", "平板", "ipad", "watch",
        "airpods", "相机", "camera", "行车记录"
    ],
    "💻 电脑周边": [
        "电脑", "笔记本", "laptop", "键盘", "鼠标", "显示器", "硬盘", "ssd",
        "内存", "显卡", "主机", "台式", "mac", "macbook", "dell", "hp", "asus",
        "lenovo", "联想", "打印机", "路由器"
    ],
    "🏠 家居家电": [
        "家具", "桌子", "椅子", "床", "沙发", "柜", "冰箱", "洗衣机", "空调",
        "电视", "风扇", "热水器", "微波炉", "电饭煲", "灶", "灯", "窗帘",
        "家电", "装修"
    ],
    "👕 衣物鞋包": [
        "衣", "裤", "裙", "鞋", "包", "帽", "服装", "外套", "t恤", "牛仔",
        "运动鞋", "拖鞋", "背包", "手提包", "钱包", "手表", "项链", "饰品"
    ],
    "🚗 汽车配件": [
        "汽车", "摩托", "轮胎", "机油", "car", "motor", "bike", "电动车",
        "脚踏车", "bicycle", "车牌", "车灯", "音响", "坐垫", "行车"
    ],
    "📚 书籍教育": [
        "书", "教材", "课本", "学习", "考试", "book", "课程", "教育",
        "文具", "笔", "本子", "字典", "小说"
    ],
    "🎮 游戏娱乐": [
        "游戏", "ps4", "ps5", "xbox", "switch", "游戏机", "steam", "玩具",
        "积木", "lego", "乐高", "健身", "球", "运动器材", "吉他", "乐器"
    ],
}

def detect_category(text):
    """根据物品名称关键词预判分类，返回建议分类或 None"""
    text_lower = (text or "").lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                return category
    return None

# ── 价格类型 ──────────────────────────────────────────────────────────────────
PRICE_TYPES = {
    "fixed":      "💰 固定价格",
    "negotiate":  "🔪 可以刀价",
    "face":       "💬 价格面议",
}

# ── FSM ───────────────────────────────────────────────────────────────────────
class SubmitForm(StatesGroup):
    item_name       = State()
    item_category   = State()   # 新增：分类选择
    item_desc       = State()
    item_price      = State()
    item_price_type = State()   # 新增：议价类型
    item_area       = State()
    contact         = State()
    media           = State()

class RejectReason(StatesGroup):
    waiting_reason = State()

class AddAd(StatesGroup):
    waiting_input = State()

# ── 临时存储 ──────────────────────────────────────────────────────────────────
pending_submissions = {}
reject_context = {}

router = Router()

# ── 触发词 ────────────────────────────────────────────────────────────────────
def is_submit_trigger(text):
    return (text or "").strip() in ["📦 开始投稿", "/submit", "投稿", "开始投稿"]

def is_cancel_trigger(text):
    return (text or "").strip() in ["❌ 取消投稿", "/cancel", "取消", "取消投稿"]

def is_done_trigger(text):
    return (text or "").strip() in ["✅ 提交投稿", "/done", "提交", "提交投稿"]

def is_addad_trigger(text):
    return (text or "").strip().startswith(("加广告", "/addad"))

def is_delad_trigger(text):
    return (text or "").strip().startswith(("删广告", "/delad"))

def is_listad_trigger(text):
    return (text or "").strip() in ["看广告", "/listad", "广告列表"]

# ── 键盘 ──────────────────────────────────────────────────────────────────────
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📦 开始投稿"), KeyboardButton(text="❌ 取消投稿")]],
        resize_keyboard=True
    )

def done_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ 提交投稿"), KeyboardButton(text="❌ 取消投稿")]],
        resize_keyboard=True
    )

def admin_review_keyboard(submission_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ 审核通过", callback_data="approve:" + submission_id),
        InlineKeyboardButton(text="❌ 审核不通过", callback_data="reject:" + submission_id),
    ]])

def category_keyboard(suggested=None):
    """分类选择键盘，suggested 分类高亮显示在第一行"""
    rows = []
    remaining = [c for c in CATEGORIES if c != suggested]

    if suggested:
        rows.append([
            InlineKeyboardButton(
                text="✅ " + suggested + "（推荐）",
                callback_data="cat:" + suggested
            )
        ])

    # 其余分类两列排列
    row = []
    for cat in remaining:
        row.append(InlineKeyboardButton(text=cat, callback_data="cat:" + cat))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    return InlineKeyboardMarkup(inline_keyboard=rows)

def price_type_keyboard():
    """议价类型选择"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💰 固定价格", callback_data="pt:fixed"),
        InlineKeyboardButton(text="🔪 可以刀价", callback_data="pt:negotiate"),
        InlineKeyboardButton(text="💬 价格面议", callback_data="pt:face"),
    ]])

def channel_keyboard(btn_msg_id, sold=False):
    now = time.time()
    active_ads = [ad for ad in ads if ad["expire"] is None or ad["expire"] > now]

    if sold:
        rows = [[InlineKeyboardButton(text="🔴 此商品已售出", callback_data="sold_notice")]]
    else:
        votes = vote_data.get(btn_msg_id, {"up": 0, "down": 0})
        rows = [[
            InlineKeyboardButton(text="👍 " + str(votes["up"]),  callback_data="vote:up:"   + str(btn_msg_id)),
            InlineKeyboardButton(text="💬 讨论一下", url=GROUP_LINK),
            InlineKeyboardButton(text="👎 " + str(votes["down"]), callback_data="vote:down:" + str(btn_msg_id)),
        ]]

    for ad in active_ads:
        rows.append([InlineKeyboardButton(text=ad["text"], url=ad["url"])])

    return InlineKeyboardMarkup(inline_keyboard=rows)

def group_notify_keyboard(post_msg_id):
    url = "https://t.me/" + CHANNEL_NAME + "/" + str(post_msg_id)
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👀 查看商品详情", url=url)
    ]])

# ── 格式化文本 ────────────────────────────────────────────────────────────────
def make_submission_id(user_id):
    return str(user_id) + "_" + str(int(time.time()))

def format_admin_text(data, user_id, media_list):
    number     = data.get("number", "????")
    category   = data.get("item_category", "未分类")
    price_type = PRICE_TYPES.get(data.get("item_price_type", "fixed"), "")
    photo_count = sum(1 for m in media_list if m["type"] == "photo")
    video_count = sum(1 for m in media_list if m["type"] == "video")
    media_info = []
    if photo_count:
        media_info.append("🖼 图片 " + str(photo_count) + " 张")
    if video_count:
        media_info.append("🎬 视频 " + str(video_count) + " 个")
    media_str = "、".join(media_info)
    return (
        "📬 <b>新投稿待审核 #" + str(number) + "</b>\n\n"
        "🏷️ <b>分类：</b>" + category + "\n"
        "🛍️ <b>物品名称：</b>" + data["item_name"] + "\n"
        "📝 <b>描述：</b>" + data["item_desc"] + "\n"
        "💰 <b>价格：</b>RM " + data["item_price"] + "　" + price_type + "\n"
        "📍 <b>地区：</b>" + data["item_area"] + "\n"
        "📞 <b>联系方式：</b>" + data["contact"] + "\n"
        "📎 <b>媒体：</b>" + media_str + "\n"
        "👤 <b>投稿人 ID：</b><code>" + str(user_id) + "</code>"
    )

def format_channel_text(data, user_id, username, full_name):
    number     = data.get("number", "????")
    category   = data.get("item_category", "")
    price_type = PRICE_TYPES.get(data.get("item_price_type", "fixed"), "")
    if username:
        user_link = '<a href="https://t.me/' + username + '">' + full_name + "</a>"
    else:
        user_link = '<a href="tg://user?id=' + str(user_id) + '">' + full_name + "</a>"
    return (
        "🏷️ <b>#" + str(number) + " | " + data["item_name"] + "</b>　" + category + "\n\n"
        "📝 " + data["item_desc"] + "\n\n"
        "💰 <b>价格：</b>RM " + data["item_price"] + "　" + price_type + "\n"
        "📍 <b>地区：</b>" + data["item_area"] + "\n"
        "📞 <b>联系：</b>" + data["contact"] + "\n\n"
        "👤 投稿人：" + user_link
    )

def build_media_group(media_list, caption, parse_mode="HTML"):
    result = []
    for i, m in enumerate(media_list):
        cap = caption if i == 0 else None
        pm  = parse_mode if i == 0 else None
        if m["type"] == "photo":
            result.append(InputMediaPhoto(media=m["file_id"], caption=cap, parse_mode=pm))
        else:
            result.append(InputMediaVideo(media=m["file_id"], caption=cap, parse_mode=pm))
    return result

async def post_to_channel_with_buttons(bot, media_list, channel_text, number, item_name):
    if len(media_list) == 1:
        m = media_list[0]
        if m["type"] == "photo":
            sent = await bot.send_photo(
                chat_id=CHANNEL_ID, photo=m["file_id"],
                caption=channel_text, parse_mode="HTML",
                reply_markup=channel_keyboard(0)
            )
        else:
            sent = await bot.send_video(
                chat_id=CHANNEL_ID, video=m["file_id"],
                caption=channel_text, parse_mode="HTML",
                reply_markup=channel_keyboard(0)
            )
        btn_msg_id  = sent.message_id
        post_msg_id = btn_msg_id
        vote_data[btn_msg_id]  = {"up": 0, "down": 0}
        vote_users[btn_msg_id] = set()
        await bot.edit_message_reply_markup(
            chat_id=CHANNEL_ID, message_id=btn_msg_id,
            reply_markup=channel_keyboard(btn_msg_id)
        )
    else:
        media_group = build_media_group(media_list, channel_text)
        msgs = await bot.send_media_group(chat_id=CHANNEL_ID, media=media_group)
        post_msg_id = msgs[0].message_id
        btn_msg = await bot.send_message(
            chat_id=CHANNEL_ID,
            text="#" + str(number) + " | " + item_name,
            reply_markup=channel_keyboard(0)
        )
        btn_msg_id = btn_msg.message_id
        vote_data[btn_msg_id]  = {"up": 0, "down": 0}
        vote_users[btn_msg_id] = set()
        await bot.edit_message_reply_markup(
            chat_id=CHANNEL_ID, message_id=btn_msg_id,
            reply_markup=channel_keyboard(btn_msg_id)
        )

    return post_msg_id, btn_msg_id


# ─────────────────────────────────────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 欢迎使用<b>大马二手交易投稿机器人</b>！\n\n"
        "点击下方按钮开始投稿物品 👇\n\n"
        "💡 标记已售：发送 <code>/sold 编号</code>",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )

# ─────────────────────────────────────────────────────────────────────────────
# 取消
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await _do_cancel(message, state)

@router.message(F.text.func(is_cancel_trigger))
async def btn_cancel(message: Message, state: FSMContext):
    await _do_cancel(message, state)

async def _do_cancel(message: Message, state: FSMContext):
    if await state.get_state() is None:
        await message.answer("❌ 目前没有进行中的投稿。", reply_markup=main_keyboard())
        return
    await state.clear()
    await message.answer("✅ 已取消本次投稿。", reply_markup=main_keyboard())

# ─────────────────────────────────────────────────────────────────────────────
# 开始投稿
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("submit"))
async def cmd_submit(message: Message, state: FSMContext):
    await _do_submit(message, state)

@router.message(F.text.func(is_submit_trigger))
async def btn_submit(message: Message, state: FSMContext):
    await _do_submit(message, state)

async def _do_submit(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(SubmitForm.item_name)
    await message.answer(
        "📦 <b>开始投稿</b>\n\n"
        "第 1 步 / 共 7 步\n"
        "请输入<b>物品名称</b>\n"
        "💡 例：iPhone 14 Pro 128GB 深紫色",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

# ─────────────────────────────────────────────────────────────────────────────
# 步骤 1：物品名称 → 触发分类预判
# ─────────────────────────────────────────────────────────────────────────────

@router.message(SubmitForm.item_name)
async def step_item_name(message: Message, state: FSMContext):
    if is_cancel_trigger(message.text):
        await _do_cancel(message, state); return

    item_name = (message.text or "").strip()
    await state.update_data(item_name=item_name)
    await state.set_state(SubmitForm.item_category)

    suggested = detect_category(item_name)

    if suggested:
        hint = "🤖 根据物品名称，为你推荐分类 <b>" + suggested + "</b>\n点击确认或选择其他分类："
    else:
        hint = "📂 请选择商品分类："

    await message.answer(hint, parse_mode="HTML", reply_markup=category_keyboard(suggested))

# ─────────────────────────────────────────────────────────────────────────────
# 步骤 2：分类选择（callback）
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cat:"))
async def step_category_selected(callback: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if current != SubmitForm.item_category:
        await callback.answer()
        return

    category = callback.data[4:]  # 去掉 "cat:" 前缀
    await state.update_data(item_category=category)
    await state.set_state(SubmitForm.item_desc)

    await callback.message.edit_text(
        "✅ 已选择分类：<b>" + category + "</b>",
        parse_mode="HTML"
    )
    await callback.message.answer(
        "第 3 步 / 共 7 步\n请输入<b>物品描述</b>\n"
        "💡 例：9成新，无划痕，原装配件齐全",
        parse_mode="HTML"
    )
    await callback.answer()

# ─────────────────────────────────────────────────────────────────────────────
# 步骤 3：物品描述
# ─────────────────────────────────────────────────────────────────────────────

@router.message(SubmitForm.item_desc)
async def step_item_desc(message: Message, state: FSMContext):
    if is_cancel_trigger(message.text):
        await _do_cancel(message, state); return
    await state.update_data(item_desc=(message.text or "").strip())
    await state.set_state(SubmitForm.item_price)
    await message.answer(
        "第 4 步 / 共 7 步\n请输入<b>价格</b>（RM）\n"
        "💡 例：350　或　面议",
        parse_mode="HTML"
    )

# ─────────────────────────────────────────────────────────────────────────────
# 步骤 4：价格输入 → 触发议价类型选择
# ─────────────────────────────────────────────────────────────────────────────

@router.message(SubmitForm.item_price)
async def step_item_price(message: Message, state: FSMContext):
    if is_cancel_trigger(message.text):
        await _do_cancel(message, state); return
    await state.update_data(item_price=(message.text or "").strip())
    await state.set_state(SubmitForm.item_price_type)
    await message.answer(
        "第 5 步 / 共 7 步\n请选择<b>议价类型</b>：",
        parse_mode="HTML",
        reply_markup=price_type_keyboard()
    )

# ─────────────────────────────────────────────────────────────────────────────
# 步骤 5：议价类型（callback）
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("pt:"))
async def step_price_type_selected(callback: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if current != SubmitForm.item_price_type:
        await callback.answer()
        return

    pt_key = callback.data[3:]  # 去掉 "pt:" 前缀
    pt_label = PRICE_TYPES.get(pt_key, "")
    await state.update_data(item_price_type=pt_key)
    await state.set_state(SubmitForm.item_area)

    await callback.message.edit_text(
        "✅ 已选择：<b>" + pt_label + "</b>",
        parse_mode="HTML"
    )
    await callback.message.answer(
        "第 6 步 / 共 7 步\n请输入<b>所在地区</b>\n"
        "💡 例：Subang Jaya, Selangor",
        parse_mode="HTML"
    )
    await callback.answer()

# ─────────────────────────────────────────────────────────────────────────────
# 步骤 6：地区
# ─────────────────────────────────────────────────────────────────────────────

@router.message(SubmitForm.item_area)
async def step_item_area(message: Message, state: FSMContext):
    if is_cancel_trigger(message.text):
        await _do_cancel(message, state); return
    await state.update_data(item_area=(message.text or "").strip())
    await state.set_state(SubmitForm.contact)
    await message.answer(
        "第 7 步（最后）/ 共 7 步\n请输入<b>联系方式</b>\n"
        "💡 例：WA: 601XXXXXXXX 或 @telegram用户名",
        parse_mode="HTML"
    )

# ─────────────────────────────────────────────────────────────────────────────
# 步骤 7：联系方式
# ─────────────────────────────────────────────────────────────────────────────

@router.message(SubmitForm.contact)
async def step_contact(message: Message, state: FSMContext):
    if is_cancel_trigger(message.text):
        await _do_cancel(message, state); return
    await state.update_data(contact=(message.text or "").strip(), media=[])
    await state.set_state(SubmitForm.media)
    await message.answer(
        "📸 <b>最后一步：上传图片或视频</b>（最多 10 个）\n\n"
        "⚠️ 请<b>逐个</b>发送，不要用相册合并发送\n"
        "📌 上传完毕后点击「✅ 提交投稿」",
        parse_mode="HTML",
        reply_markup=done_keyboard()
    )

# ─────────────────────────────────────────────────────────────────────────────
# 上传媒体
# ─────────────────────────────────────────────────────────────────────────────

@router.message(SubmitForm.media, F.photo)
async def step_media_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    media = data.get("media", [])
    if len(media) >= 10:
        await message.answer("⚠️ 最多上传 10 个，请点击「✅ 提交投稿」。")
        return
    media.append({"type": "photo", "file_id": message.photo[-1].file_id})
    await state.update_data(media=media)
    await message.answer("✅ 已收到第 " + str(len(media)) + " 个（图片），继续上传或点击「✅ 提交投稿」。")

@router.message(SubmitForm.media, F.video)
async def step_media_video(message: Message, state: FSMContext):
    data = await state.get_data()
    media = data.get("media", [])
    if len(media) >= 10:
        await message.answer("⚠️ 最多上传 10 个，请点击「✅ 提交投稿」。")
        return
    media.append({"type": "video", "file_id": message.video.file_id})
    await state.update_data(media=media)
    await message.answer("✅ 已收到第 " + str(len(media)) + " 个（视频），继续上传或点击「✅ 提交投稿」。")

@router.message(SubmitForm.media, Command("done"))
async def cmd_done(message: Message, state: FSMContext, bot: Bot):
    await _do_done(message, state, bot)

@router.message(SubmitForm.media, F.text.func(is_done_trigger))
async def btn_done(message: Message, state: FSMContext, bot: Bot):
    await _do_done(message, state, bot)

@router.message(SubmitForm.media, F.text)
async def step_media_invalid(message: Message):
    if is_cancel_trigger(message.text) or is_done_trigger(message.text):
        return
    await message.answer(
        "⚠️ 请发送<b>图片或视频</b>，或点击「✅ 提交投稿」提交。",
        parse_mode="HTML"
    )

async def _do_done(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    media = data.get("media", [])
    if not media:
        await message.answer("⚠️ 请至少上传 1 张图片或视频。")
        return

    await state.clear()

    user      = message.from_user
    user_id   = user.id
    username  = user.username or ""
    full_name = user.full_name or ("用户" + str(user_id))

    submission_id = make_submission_id(user_id)
    number = next_submission_number()
    data["number"]    = number
    data["user_id"]   = user_id
    data["username"]  = username
    data["full_name"] = full_name

    pending_submissions[submission_id] = {
        "user_id":   user_id,
        "username":  username,
        "full_name": full_name,
        "data":      data,
        "media":     media,
    }

    caption = format_admin_text(data, user_id, media) + "\n\n🆔 <code>" + submission_id + "</code>"

    first = True
    for m in media:
        if m["type"] == "photo":
            await bot.send_photo(
                chat_id=ADMIN_ID, photo=m["file_id"],
                caption=caption if first else None,
                parse_mode="HTML" if first else None,
                reply_markup=admin_review_keyboard(submission_id) if first else None
            )
        else:
            await bot.send_video(
                chat_id=ADMIN_ID, video=m["file_id"],
                caption=caption if first else None,
                parse_mode="HTML" if first else None,
                reply_markup=admin_review_keyboard(submission_id) if first else None
            )
        first = False

    if len(media) > 1:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text="⬆️ 以上是投稿 <b>#" + str(number) + "</b> 的全部媒体，请审核：",
            parse_mode="HTML",
            reply_markup=admin_review_keyboard(submission_id)
        )

    await message.answer(
        "🎉 投稿 <b>#" + str(number) + "</b> 已提交！\n"
        "管理员审核后会通知你结果，请耐心等待。\n\n"
        "💡 审核通过后，如商品已售出，发送 <code>/sold " + str(number) + "</code> 标记已售。",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )
    logger.info("New submission #%s (%s) from user %s, media: %s", number, submission_id, user_id, len(media))

# ─────────────────────────────────────────────────────────────────────────────
# 审核通过
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("approve:"))
async def admin_approve(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ 你没有权限操作。", show_alert=True); return

    submission_id = callback.data.split(":", 1)[1]
    submission = pending_submissions.get(submission_id)
    if not submission:
        await callback.answer("⚠️ 该投稿已处理或已过期。", show_alert=True); return

    data      = submission["data"]
    media     = submission["media"]
    user_id   = submission["user_id"]
    username  = submission["username"]
    full_name = submission["full_name"]
    number    = data.get("number", "????")

    channel_text = format_channel_text(data, user_id, username, full_name)

    try:
        post_msg_id, btn_msg_id = await post_to_channel_with_buttons(
            bot, media, channel_text, number, data["item_name"]
        )
    except Exception as e:
        logger.error("Failed to post to channel: %s", e)
        await callback.answer("❌ 发布到频道失败，请检查机器人权限。", show_alert=True); return

    # 记录已售信息（用于 /sold 命令）
    sold_posts[number] = {
        "btn_msg_id": btn_msg_id,
        "user_id":    user_id,
    }

    # 通知群组
    try:
        await bot.send_message(
            chat_id=GROUP_ID,
            text=(
                "🆕 <b>新商品上架！</b>\n\n"
                "🏷️ <b>#" + str(number) + " | " + data["item_name"] + "</b>\n"
                "💰 RM " + data["item_price"] + " | 📍 " + data["item_area"] + "\n\n"
                "👇 点击下方按钮查看详情"
            ),
            parse_mode="HTML",
            reply_markup=group_notify_keyboard(post_msg_id)
        )
    except Exception as e:
        logger.warning("Failed to notify group: %s", e)

    # 通知投稿人
    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                "🎉 <b>你的投稿 #" + str(number) + " 已通过审核并发布！</b>\n\n"
                "商品已售出后，发送 <code>/sold " + str(number) + "</code> 标记已售出。"
            ),
            parse_mode="HTML",
            reply_markup=main_keyboard()
        )
    except Exception:
        logger.warning("Cannot notify user %s", user_id)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "✅ 投稿 <b>#" + str(number) + "</b> 已通过并发布到频道。",
        parse_mode="HTML"
    )
    await callback.answer("✅ 已通过并发布！")
    pending_submissions.pop(submission_id, None)
    logger.info("Submission #%s approved", number)

# ─────────────────────────────────────────────────────────────────────────────
# 审核不通过
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("reject:"))
async def admin_reject_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ 你没有权限操作。", show_alert=True); return

    submission_id = callback.data.split(":", 1)[1]
    submission = pending_submissions.get(submission_id)
    if not submission:
        await callback.answer("⚠️ 该投稿已处理或已过期。", show_alert=True); return

    number = submission["data"].get("number", "????")
    reject_context[ADMIN_ID] = submission_id
    await state.set_state(RejectReason.waiting_reason)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "📝 请输入投稿 <b>#" + str(number) + "</b> 的<b>拒绝原因</b>（将发送给用户）：",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(RejectReason.waiting_reason, F.from_user.id == ADMIN_ID, F.text)
async def admin_reject_text(message: Message, state: FSMContext, bot: Bot):
    await _send_reject(message, state, bot, reason_text=(message.text or "").strip(), photo_id=None)

@router.message(RejectReason.waiting_reason, F.from_user.id == ADMIN_ID, F.photo)
async def admin_reject_photo(message: Message, state: FSMContext, bot: Bot):
    reason_text = (message.caption or "（管理员附上了图片说明）").strip()
    await _send_reject(message, state, bot, reason_text=reason_text, photo_id=message.photo[-1].file_id)

async def _send_reject(message: Message, state: FSMContext, bot: Bot, reason_text, photo_id):
    submission_id = reject_context.get(ADMIN_ID)
    if not submission_id:
        await state.clear(); return

    submission = pending_submissions.get(submission_id)
    if not submission:
        await state.clear()
        await message.answer("⚠️ 该投稿已不存在。"); return

    user_id = submission["user_id"]
    number  = submission["data"].get("number", "????")
    item    = submission["data"].get("item_name", "")

    reject_msg = (
        "❌ <b>你的投稿 #" + str(number) + " 未通过审核</b>\n\n"
        "📦 物品：" + item + "\n\n"
        "💬 <b>原因：</b>" + reason_text + "\n\n"
        "请修改后重新点击「📦 开始投稿」重新投稿。"
    )

    try:
        if photo_id:
            await bot.send_photo(
                chat_id=user_id, photo=photo_id,
                caption=reject_msg, parse_mode="HTML",
                reply_markup=main_keyboard()
            )
        else:
            await bot.send_message(
                chat_id=user_id, text=reject_msg,
                parse_mode="HTML", reply_markup=main_keyboard()
            )
    except Exception:
        logger.warning("Cannot notify user %s", user_id)

    await message.answer(
        "✅ 已将拒绝原因发送给用户，投稿 <b>#" + str(number) + "</b> 已移除。",
        parse_mode="HTML"
    )
    pending_submissions.pop(submission_id, None)
    reject_context.pop(ADMIN_ID, None)
    await state.clear()
    logger.info("Submission #%s rejected. Reason: %s", number, reason_text)

# ─────────────────────────────────────────────────────────────────────────────
# ⑤ 自助标记已售出 /sold <编号>
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("sold"))
async def cmd_sold(message: Message, bot: Bot):
    args = message.text.split()[1:] if message.text else []
    if not args or not args[0].isdigit():
        await message.answer(
            "❓ 用法：<code>/sold 编号</code>\n"
            "💡 例：<code>/sold 1009528</code>",
            parse_mode="HTML"
        )
        return

    number = int(args[0])
    post_info = sold_posts.get(number)

    if not post_info:
        await message.answer(
            "⚠️ 未找到编号 #" + str(number) + " 的记录。\n"
            "请确认编号正确，或者机器人重启后记录已丢失。"
        )
        return

    # 只允许原投稿人或管理员操作
    if message.from_user.id != post_info["user_id"] and message.from_user.id != ADMIN_ID:
        await message.answer("⛔ 只有原投稿人才能标记自己的商品已售出。")
        return

    btn_msg_id = post_info["btn_msg_id"]

    try:
        await bot.edit_message_reply_markup(
            chat_id=CHANNEL_ID,
            message_id=btn_msg_id,
            reply_markup=channel_keyboard(btn_msg_id, sold=True)
        )
        sold_posts.pop(number, None)
        await message.answer(
            "✅ <b>#" + str(number) + " 已标记为售出！</b>\n"
            "频道帖子已更新，感谢使用～",
            parse_mode="HTML",
            reply_markup=main_keyboard()
        )
        logger.info("Submission #%s marked as sold by user %s", number, message.from_user.id)
    except Exception as e:
        await message.answer("❌ 操作失败：" + str(e))
        logger.error("Failed to mark #%s as sold: %s", number, e)

# ─────────────────────────────────────────────────────────────────────────────
# 点赞 / 点踩
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("vote:"))
async def handle_vote(callback: CallbackQuery, bot: Bot):
    parts      = callback.data.split(":")
    vote_type  = parts[1]
    btn_msg_id = int(parts[2])
    user_id    = callback.from_user.id

    if btn_msg_id not in vote_data:
        vote_data[btn_msg_id]  = {"up": 0, "down": 0}
        vote_users[btn_msg_id] = set()

    if user_id in vote_users[btn_msg_id]:
        await callback.answer("你已经投过票了！", show_alert=False); return

    vote_users[btn_msg_id].add(user_id)
    vote_data[btn_msg_id][vote_type] += 1

    try:
        await bot.edit_message_reply_markup(
            chat_id=CHANNEL_ID, message_id=btn_msg_id,
            reply_markup=channel_keyboard(btn_msg_id)
        )
    except Exception as e:
        logger.warning("Vote update failed: %s", e)

    emoji = "👍" if vote_type == "up" else "👎"
    await callback.answer(emoji + " 已记录！")

@router.callback_query(F.data == "sold_notice")
async def sold_notice(callback: CallbackQuery):
    await callback.answer("此商品已售出，感谢关注！", show_alert=True)

# ─────────────────────────────────────────────────────────────────────────────
# 广告管理
# ─────────────────────────────────────────────────────────────────────────────

@router.message(F.from_user.id == ADMIN_ID, F.text.func(is_addad_trigger))
async def cmd_addad(message: Message, state: FSMContext):
    await state.set_state(AddAd.waiting_input)
    await message.answer(
        "📢 请按以下格式发送广告信息：\n\n"
        "<code>广告文字 | 链接 | 小时数</code>\n\n"
        "💡 例：\n<code>🔥 点击领取优惠券 | https://example.com | 24</code>\n\n"
        "小时数填 <b>0</b> 表示永久，发送「取消」退出。",
        parse_mode="HTML"
    )

@router.message(AddAd.waiting_input, F.from_user.id == ADMIN_ID)
async def addad_input(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text in ["取消", "/cancel"]:
        await state.clear()
        await message.answer("✅ 已取消。"); return

    parts = [p.strip() for p in text.split("|")]
    if len(parts) != 3:
        await message.answer("⚠️ 格式错误，请按「广告文字 | 链接 | 小时数」发送。"); return

    ad_text, ad_url, hours_str = parts
    try:
        hours = float(hours_str)
    except ValueError:
        await message.answer("⚠️ 小时数必须是数字，例如 24 或 0。"); return

    expire = None if hours == 0 else time.time() + hours * 3600
    ads.append({"text": ad_text, "url": ad_url, "expire": expire})
    await state.clear()

    expire_info = "永久" if expire is None else str(int(hours)) + " 小时后过期"
    await message.answer(
        "✅ 广告已添加！\n\n"
        "📌 文字：" + ad_text + "\n"
        "🔗 链接：" + ad_url + "\n"
        "⏰ 有效期：" + expire_info + "\n\n"
        "当前共 " + str(len(ads)) + " 条广告。"
    )
    logger.info("Ad added: %s | %s | expire=%s", ad_text, ad_url, expire)

@router.message(F.from_user.id == ADMIN_ID, F.text.func(is_listad_trigger))
async def cmd_listad(message: Message):
    if not ads:
        await message.answer("📭 目前没有广告。"); return
    now = time.time()
    lines = []
    for i, ad in enumerate(ads, 1):
        if ad["expire"] is None:
            status = "♾️ 永久"
        elif ad["expire"] > now:
            remain = int((ad["expire"] - now) / 3600)
            status = "⏰ 剩余约 " + str(remain) + " 小时"
        else:
            status = "❌ 已过期"
        lines.append(str(i) + ". " + ad["text"] + "\n   🔗 " + ad["url"] + "\n   " + status)
    await message.answer("📢 <b>广告列表：</b>\n\n" + "\n\n".join(lines), parse_mode="HTML")

@router.message(F.from_user.id == ADMIN_ID, F.text.func(is_delad_trigger))
async def cmd_delad(message: Message):
    now     = time.time()
    expired = [ad for ad in ads if ad["expire"] is not None and ad["expire"] <= now]
    for ad in expired:
        ads.remove(ad)

    text  = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) == 2 and parts[1].isdigit():
        idx = int(parts[1]) - 1
        if 0 <= idx < len(ads):
            removed = ads.pop(idx)
            await message.answer("✅ 已删除广告：" + removed["text"] + "\n当前剩余 " + str(len(ads)) + " 条。")
        else:
            await message.answer("⚠️ 编号不存在，当前共 " + str(len(ads)) + " 条，用「看广告」查看列表。")
        return

    cleaned = len(expired)
    if cleaned > 0:
        await message.answer(
            "✅ 已清理 " + str(cleaned) + " 条过期广告，剩余 " + str(len(ads)) + " 条。\n\n"
            "💡 删除指定广告：「删广告 编号」，例如「删广告 2」"
        )
    else:
        await message.answer(
            "ℹ️ 没有过期广告，当前共 " + str(len(ads)) + " 条。\n\n"
            "💡 删除指定广告：「删广告 编号」，例如「删广告 2」"
        )

# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    logger.info("Bot starting...")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    asyncio.run(main())
