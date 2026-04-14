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
CHANNEL_NAME = "malaixiyaershouqun"   # 用于生成跳转链接
GROUP_ID     = "@damajiaoliu"
GROUP_LINK   = "https://t.me/damajiaoliu"

# ── 投稿编号（从 1009528 开始）────────────────────────────────────────────────
submission_counter = 1009527

def next_submission_number() -> int:
    global submission_counter
    submission_counter += 1
    return submission_counter

# ── 点赞/点踩存储 ─────────────────────────────────────────────────────────────
vote_data: dict = {}
vote_users: dict = {}

# ── 广告存储 ──────────────────────────────────────────────────────────────────
ads: list = []

# ── FSM ───────────────────────────────────────────────────────────────────────
class SubmitForm(StatesGroup):
    item_name  = State()
    item_desc  = State()
    item_price = State()
    item_area  = State()
    contact    = State()
    media      = State()

class RejectReason(StatesGroup):
    waiting_reason = State()

class AddAd(StatesGroup):
    waiting_input = State()

# ── 临时存储 ──────────────────────────────────────────────────────────────────
pending_submissions: dict = {}
reject_context: dict = {}

router = Router()

# ── 触发词 ────────────────────────────────────────────────────────────────────

def is_submit_trigger(text) -> bool:
    return (text or "").strip() in ["📦 开始投稿", "/submit", "投稿", "开始投稿"]

def is_cancel_trigger(text) -> bool:
    return (text or "").strip() in ["❌ 取消投稿", "/cancel", "取消", "取消投稿"]

def is_done_trigger(text) -> bool:
    return (text or "").strip() in ["✅ 提交投稿", "/done", "提交", "提交投稿"]

def is_addad_trigger(text) -> bool:
    return (text or "").strip().startswith(("加广告", "/addad"))

def is_delad_trigger(text) -> bool:
    return (text or "").strip().startswith(("删广告", "/delad"))

def is_listad_trigger(text) -> bool:
    return (text or "").strip() in ["看广告", "/listad", "广告列表"]

# ── 键盘 ──────────────────────────────────────────────────────────────────────

def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📦 开始投稿"), KeyboardButton(text="❌ 取消投稿")]],
        resize_keyboard=True
    )

def done_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ 提交投稿"), KeyboardButton(text="❌ 取消投稿")]],
        resize_keyboard=True
    )

def admin_review_keyboard(submission_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ 审核通过", callback_data=f"approve:{submission_id}"),
        InlineKeyboardButton(text="❌ 审核不通过", callback_data=f"reject:{submission_id}"),
    ]])

def channel_keyboard(btn_msg_id: int) -> InlineKeyboardMarkup:
    votes = vote_data.get(btn_msg_id, {"up": 0, "down": 0})
    now = time.time()
    active_ads = [ad for ad in ads if ad["expire"] is None or ad["expire"] > now]
    rows = [[
        InlineKeyboardButton(text=f"👍 {votes['up']}", callback_data=f"vote:up:{btn_msg_id}"),
        InlineKeyboardButton(text="💬 讨论一下", url=GROUP_LINK),
        InlineKeyboardButton(text=f"👎 {votes['down']}", callback_data=f"vote:down:{btn_msg_id}"),
    ]]
    for ad in active_ads:
        rows.append([InlineKeyboardButton(text=ad["text"], url=ad["url"])])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def group_notify_keyboard(post_msg_id: int) -> InlineKeyboardMarkup:
    """群组通知消息的跳转按钮"""
    url = f"https://t.me/{CHANNEL_NAME}/{post_msg_id}"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👀 查看商品详情", url=url)
    ]])

# ── 格式化文本 ────────────────────────────────────────────────────────────────

def make_submission_id(user_id: int) -> str:
    return f"{user_id}_{int(time.time())}"

def format_admin_text(data: dict, user_id: int, media_list: list) -> str:
    number = data.get("number", "????")
    photo_count = sum(1 for m in media_list if m["type"] == "photo")
    video_count = sum(1 for m in media_list if m["type"] == "video")
    media_info = []
    if photo_count:
        media_info.append(f"🖼 图片 {photo_count} 张")
    if video_count:
        media_info.append(f"🎬 视频 {video_count} 个")
    media_str = "、".join(media_info)
    return (
        f"📬 <b>新投稿待审核 #{number}</b>\n\n"
        f"🛍️ <b>物品名称：</b>{data['item_name']}\n"
        f"📝 <b>描述：</b>{data['item_desc']}\n"
        f"💰 <b>价格：</b>RM {data['item_price']}\n"
        f"📍 <b>地区：</b>{data['item_area']}\n"
        f"📞 <b>联系方式：</b>{data['contact']}\n"
        f"📎 <b>媒体：</b>{media_str}\n"
        f"👤 <b>投稿人 ID：</b><code>{user_id}</code>"
    )

def format_channel_text(data: dict, user_id: int, username: str, full_name: str) -> str:
    number = data.get("number", "????")
    if username:
        user_link = f'<a href="https://t.me/{username}">{full_name}</a>'
    else:
        user_link = f'<a href="tg://user?id={user_id}">{full_name}</a>'
    return (
        f"🏷️ <b>#{number} | {data['item_name']}</b>\n\n"
        f"📝 {data['item_desc']}\n\n"
        f"💰 <b>价格：</b>RM {data['item_price']}\n"
        f"📍 <b>地区：</b>{data['item_area']}\n"
        f"📞 <b>联系：</b>{data['contact']}\n\n"
        f"👤 投稿人：{user_link}"
    )

def build_media_group(media_list: list, caption: str, parse_mode: str = "HTML"):
    result = []
    for i, m in enumerate(media_list):
        cap = caption if i == 0 else None
        pm  = parse_mode if i == 0 else None
        if m["type"] == "photo":
            result.append(InputMediaPhoto(media=m["file_id"], caption=cap, parse_mode=pm))
        else:
            result.append(InputMediaVideo(media=m["file_id"], caption=cap, parse_mode=pm))
    return result

async def post_to_channel_with_buttons(bot: Bot, media_list: list, channel_text: str, number, item_name: str):
    """
    发布到频道，返回 post_msg_id（用于生成跳转链接）
    单媒体：直接带按钮
    多媒体：媒体组 + 按钮消息
    """
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
        btn_msg_id = sent.message_id
        post_msg_id = btn_msg_id  # 单媒体：跳转到这条
        vote_data[btn_msg_id]  = {"up": 0, "down": 0}
        vote_users[btn_msg_id] = set()
        await bot.edit_message_reply_markup(
            chat_id=CHANNEL_ID, message_id=btn_msg_id,
            reply_markup=channel_keyboard(btn_msg_id)
        )
    else:
        media_group = build_media_group(media_list, channel_text)
        msgs = await bot.send_media_group(chat_id=CHANNEL_ID, media=media_group)
        post_msg_id = msgs[0].message_id  # 多媒体：跳转到第一条
        btn_msg = await bot.send_message(
            chat_id=CHANNEL_ID,
            text=f"#{number} | {item_name}",
            reply_markup=channel_keyboard(0)
        )
        btn_msg_id = btn_msg.message_id
        vote_data[btn_msg_id]  = {"up": 0, "down": 0}
        vote_users[btn_msg_id] = set()
        await bot.edit_message_reply_markup(
            chat_id=CHANNEL_ID, message_id=btn_msg_id,
            reply_markup=channel_keyboard(btn_msg_id)
        )

    return post_msg_id

# ─────────────────────────────────────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 欢迎使用<b>大马二手交易投稿机器人</b>！\n\n"
        "点击下方按钮开始投稿物品 👇",
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
        "第 1 步 / 共 6 步\n"
        "请输入<b>物品名称</b>\n"
        "💡 例：iPhone 14 Pro 128GB 深紫色",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

# ─────────────────────────────────────────────────────────────────────────────
# 表单步骤
# ─────────────────────────────────────────────────────────────────────────────

@router.message(SubmitForm.item_name)
async def step_item_name(message: Message, state: FSMContext):
    if is_cancel_trigger(message.text):
        await _do_cancel(message, state); return
    await state.update_data(item_name=(message.text or "").strip())
    await state.set_state(SubmitForm.item_desc)
    await message.answer(
        "第 2 步 / 共 6 步\n请输入<b>物品描述</b>\n💡 例：9成新，无划痕，原装配件齐全",
        parse_mode="HTML"
    )

@router.message(SubmitForm.item_desc)
async def step_item_desc(message: Message, state: FSMContext):
    if is_cancel_trigger(message.text):
        await _do_cancel(message, state); return
    await state.update_data(item_desc=(message.text or "").strip())
    await state.set_state(SubmitForm.item_price)
    await message.answer(
        "第 3 步 / 共 6 步\n请输入<b>价格</b>（RM）\n💡 例：350 或 面议",
        parse_mode="HTML"
    )

@router.message(SubmitForm.item_price)
async def step_item_price(message: Message, state: FSMContext):
    if is_cancel_trigger(message.text):
        await _do_cancel(message, state); return
    await state.update_data(item_price=(message.text or "").strip())
    await state.set_state(SubmitForm.item_area)
    await message.answer(
        "第 4 步 / 共 6 步\n请输入<b>所在地区</b>\n💡 例：Subang Jaya, Selangor",
        parse_mode="HTML"
    )

@router.message(SubmitForm.item_area)
async def step_item_area(message: Message, state: FSMContext):
    if is_cancel_trigger(message.text):
        await _do_cancel(message, state); return
    await state.update_data(item_area=(message.text or "").strip())
    await state.set_state(SubmitForm.contact)
    await message.answer(
        "第 5 步 / 共 6 步\n请输入<b>联系方式</b>\n💡 例：WA: 601XXXXXXXX 或 @telegram用户名",
        parse_mode="HTML"
    )

@router.message(SubmitForm.contact)
async def step_contact(message: Message, state: FSMContext):
    if is_cancel_trigger(message.text):
        await _do_cancel(message, state); return
    await state.update_data(contact=(message.text or "").strip(), media=[])
    await state.set_state(SubmitForm.media)
    await message.answer(
        "第 6 步 / 共 6 步\n请上传<b>物品图片或视频</b>（最多 10 个）\n\n"
        "⚠️ 请<b>逐个</b>发送，不要用相册合并发送\n"
        "📌 上传完毕后点击下方「✅ 提交投稿」",
        parse_mode="HTML",
        reply_markup=done_keyboard()
    )

@router.message(SubmitForm.media, F.photo)
async def step_media_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    media: list = data.get("media", [])
    if len(media) >= 10:
        await message.answer("⚠️ 最多上传 10 个，请点击「✅ 提交投稿」。")
        return
    media.append({"type": "photo", "file_id": message.photo[-1].file_id})
    await state.update_data(media=media)
    await message.answer(f"✅ 已收到第 {len(media)} 个（图片），继续上传或点击「✅ 提交投稿」。")

@router.message(SubmitForm.media, F.video)
async def step_media_video(message: Message, state: FSMContext):
    data = await state.get_data()
    media: list = data.get("media", [])
    if len(media) >= 10:
        await message.answer("⚠️ 最多上传 10 个，请点击「✅ 提交投稿」。")
        return
    media.append({"type": "video", "file_id": message.video.file_id})
    await state.update_data(media=media)
    await message.answer(f"✅ 已收到第 {len(media)} 个（视频），继续上传或点击「✅ 提交投稿」。")

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
    media: list = data.get("media", [])
    if not media:
        await message.answer("⚠️ 请至少上传 1 张图片或视频。")
        return

    await state.clear()

    user      = message.from_user
    user_id   = user.id
    username  = user.username or ""
    full_name = user.full_name or f"用户{user_id}"

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

    caption = format_admin_text(data, user_id, media) + f"\n\n🆔 <code>{submission_id}</code>"

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
            text=f"⬆️ 以上是投稿 <b>#{number}</b> 的全部媒体，请审核：",
            parse_mode="HTML",
            reply_markup=admin_review_keyboard(submission_id)
        )

    await message.answer(
        f"🎉 投稿 <b>#{number}</b> 已提交！\n管理员审核后会通知你结果，请耐心等待。",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )
    logger.info(f"New submission #{number} ({submission_id}) from user {user_id}, media: {len(media)}")

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
        post_msg_id = await post_to_channel_with_buttons(
            bot, media, channel_text, number, data["item_name"]
        )
    except Exception as e:
        logger.error(f"Failed to post to channel: {e}")
        await callback.answer("❌ 发布到频道失败，请检查机器人权限。", show_alert=True); return

    # ── 通知聊天群组 ──────────────────────────────────────────────────────────
    try:
        await bot.send_message(
            chat_id=GROUP_ID,
            text=(
                f"🆕 <b>新商品上架！</b>\n\n"
                f"🏷️ <b>#{number} | {data['item_name']}</b>\n"
                f"💰 RM {data['item_price']} | 📍 {data['item_area']}\n\n"
                f"👇 点击下方按钮查看详情"
            ),
            parse_mode="HTML",
            reply_markup=group_notify_keyboard(post_msg_id)
        )
    except Exception as e:
        logger.warning(f"Failed to notify group: {e}")

    # ── 通知投稿人 ────────────────────────────────────────────────────────────
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"🎉 <b>你的投稿 #{number} 已通过审核并发布到频道！</b>\n\n感谢使用，欢迎继续投稿～",
            parse_mode="HTML",
            reply_markup=main_keyboard()
        )
    except Exception:
        logger.warning(f"Cannot notify user {user_id}")

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ 投稿 <b>#{number}</b> 已通过并发布到频道。", parse_mode="HTML")
    await callback.answer("✅ 已通过并发布！")
    pending_submissions.pop(submission_id, None)
    logger.info(f"Submission #{number} approved, notified group")

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
        f"📝 请输入投稿 <b>#{number}</b> 的<b>拒绝原因</b>（将发送给用户）\n\n"
        f"可以只发文字，也可以发图片（图片说明文字就是原因）：",
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

async def _send_reject(message: Message, state: FSMContext, bot: Bot, reason_text: str, photo_id):
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
        f"❌ <b>你的投稿 #{number} 未通过审核</b>\n\n"
        f"📦 物品：{item}\n\n"
        f"💬 <b>原因：</b>{reason_text}\n\n"
        f"请修改后重新点击「📦 开始投稿」重新投稿。"
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
        logger.warning(f"Cannot notify user {user_id}")

    await message.answer(
        f"✅ 已将拒绝原因发送给用户，投稿 <b>#{number}</b> 已移除。",
        parse_mode="HTML"
    )
    pending_submissions.pop(submission_id, None)
    reject_context.pop(ADMIN_ID, None)
    await state.clear()
    logger.info(f"Submission #{number} rejected. Reason: {reason_text}")

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
        logger.warning(f"Vote update failed: {e}")

    emoji = "👍" if vote_type == "up" else "👎"
    await callback.answer(f"{emoji} 已记录！")

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

    expire_info = "永久" if expire is None else f"{int(hours)} 小时后过期"
    await message.answer(
        f"✅ 广告已添加！\n\n"
        f"📌 文字：{ad_text}\n🔗 链接：{ad_url}\n⏰ 有效期：{expire_info}\n\n"
        f"当前共 {len(ads)} 条广告。"
    )
    logger.info(f"Ad added: {ad_text} | {ad_url} | expire={expire}")

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
            status = f"⏰ 剩余约 {remain} 小时"
        else:
            status = "❌ 已过期"
        lines.append(f"{i}. {ad['text']}\n   🔗 {ad['url']}\n   {status}")
    await message.answer("📢 <b>广告列表：</b>\n\n" + "\n\n".join(lines), parse_mode="HTML")

@router.message(F.from_user.id == ADMIN_ID, F.text.func(is_delad_trigger))
async def cmd_delad(message: Message):
    now = time.time()
    expired = [ad for ad in ads if ad["expire"] is not None and ad["expire"] <= now]
    for ad in expired:
        ads.remove(ad)

    text  = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) == 2 and parts[1].isdigit():
        idx = int(parts[1]) - 1
        if 0 <= idx < len(ads):
            removed = ads.pop(idx)
            await message.answer(f"✅ 已删除广告：{removed['text']}\n当前剩余 {len(ads)} 条。")
        else:
            await message.answer(f"⚠️ 编号不存在，当前共 {len(ads)} 条，用「看广告」查看列表。")
        return

    cleaned = len(expired)
    if cleaned > 0:
        await message.answer(
            f"✅ 已清理 {cleaned} 条过期广告，剩余 {len(ads)} 条。\n\n"
            f"💡 删除指定广告：「删广告 编号」，例如「删广告 2」"
        )
    else:
        await message.answer(
            f"ℹ️ 没有过期广告，当前共 {len(ads)} 条。\n\n"
            f"💡 删除指定广告：「删广告 编号」，例如「删广告 2」"
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