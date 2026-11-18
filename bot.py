import asyncio
import html
import os
import re
import httpx
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart

BOT_TOKEN = os.getenv("BOT_TOKEN")
DELETE_AFTER_SECONDS = 600  # 10 minutes

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

TIKTOK_REGEX = r"(https?://(?:www\.|vm\.|vt\.|m\.)?tiktok\.com/\S+)"

def fix_url(url: str | None) -> str | None:
    if not url:
        return None
    return url if url.startswith("http") else f"https://www.tikwm.com{url}"

def format_number(num: int) -> str:
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    if num >= 1_000:
        return f"{num / 1_000:.1f}K"
    return str(num)

async def auto_delete_message(chat_id: int, message_id: int, delay: int):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_name = html.escape(message.from_user.first_name or "there")
    welcome_text = (
        f"👋 <b>Hello, {user_name}!</b>\n\n"
        "Welcome to the <b>TikTok HD Video Downloader</b>.\n\n"
        "📥 <b>How to use:</b>\n"
        "Simply paste and send any TikTok video link here. I will automatically fetch and send the <b>No-Watermark HD video</b>.\n\n"
        "⏳ <i>Note: For copyright safety, downloaded videos are automatically deleted after 10 minutes.</i>"
    )
    await message.answer(welcome_text, parse_mode=ParseMode.HTML)

@dp.message(F.text.regexp(TIKTOK_REGEX))
async def handle_tiktok_link(message: Message):
    match = re.search(TIKTOK_REGEX, message.text)
    tiktok_url = match.group(1)

    status_msg = await message.reply("⏳ <b>Processing your TikTok link...</b>", parse_mode=ParseMode.HTML)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                "https://www.tikwm.com/api/",
                data={"url": tiktok_url, "hd": 1}
            )
            data = res.json()

        if not data.get("data"):
            await status_msg.edit_text(
                "❌ <b>Video not found!</b>\nPlease check if the link is valid or if the video is private.",
                parse_mode=ParseMode.HTML
            )
            return

        v = data["data"]
        # Prioritize HD video, fallback to standard no-watermark play
        video_url = fix_url(v.get("hdplay") or v.get("play"))
        music_url = fix_url(v.get("music"))

        username = html.escape(v.get("author", {}).get("unique_id", "unknown"))
        title = html.escape(v.get("title", "").strip())
        if len(title) > 120:
            title = title[:120] + "..."

        views = format_number(v.get("play_count", 0))
        likes = format_number(v.get("digg_count", 0))
        comments = format_number(v.get("comment_count", 0))

        title_line = f"📝 <b>Caption:</b> {title}\n" if title else ""
        caption = (
            f"🎬 <b>Author:</b> @{username}\n"
            f"{title_line}"
            f"👁 <b>Views:</b> {views}  |  ❤️ <b>Likes:</b> {likes}  |  💬 <b>Comments:</b> {comments}\n\n"
            f"⏳ <i>This video will be auto-deleted in 10 minutes.</i>"
        )

        # Inline button for Audio & Original Link
        buttons = []
        if music_url:
            buttons.append([InlineKeyboardButton(text="🎵 Download Audio (MP3)", url=music_url)])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

        await status_msg.edit_text("📤 <b>Uploading HD video...</b>", parse_mode=ParseMode.HTML)

        sent_video = await message.answer_video(
            video=video_url,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            supports_streaming=True
        )
        await status_msg.delete()

        # Schedule auto-delete
        asyncio.create_task(
            auto_delete_message(sent_video.chat.id, sent_video.message_id, DELETE_AFTER_SECONDS)
        )

    except Exception as e:
        err_text = html.escape(str(e))
        await status_msg.edit_text(
            f"❌ <b>Failed to download video.</b>\n<code>{err_text}</code>",
            parse_mode=ParseMode.HTML
        )

# Dummy web server to keep Render alive
async def health_check(request):
    return web.Response(text="TikTok Bot is Running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    await start_web_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
