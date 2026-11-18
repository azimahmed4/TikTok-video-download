import asyncio
import os
import re
import httpx
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import CommandStart

# Render-এর Environment Variable থেকে BOT_TOKEN নিবে
BOT_TOKEN = os.getenv("BOT_TOKEN")
DELETE_AFTER_SECONDS = 600  # ১০ মিনিট (৬০০ সেকেন্ড) পর ভিডিও ডিলিট হবে

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

TIKTOK_REGEX = r"(https?://(?:www\.|vm\.|vt\.|m\.)?tiktok\.com/\S+)"

def fix_url(url: str | None) -> str | None:
    if not url:
        return None
    return url if url.startswith("http") else f"https://www.tikwm.com{url}"

async def auto_delete_message(chat_id: int, message_id: int, delay: int):
    """নির্দিষ্ট সময় পর মেসেজ অটো ডিলিট করবে"""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "👋 স্বাগতম!\n\n"
        "যেকোনো **TikTok ভিডিওর লিংক** এখানে পেস্ট করুন, আমি ওয়াটারমার্ক ছাড়া HD ভিডিও পাঠিয়ে দেব।\n"
        "⚠️ কপিরাইট নিরাপত্তার জন্য প্রতিটি ভিডিও ১০ মিনিট পর অটোমেটিক ডিলিট হয়ে যাবে।",
        parse_mode="Markdown"
    )

@dp.message(F.text.regexp(TIKTOK_REGEX))
async def handle_tiktok_link(message: Message):
    match = re.search(TIKTOK_REGEX, message.text)
    tiktok_url = match.group(1)

    status_msg = await message.reply("⏳ ভিডিও প্রসেস হচ্ছে, একটু অপেক্ষা করুন...")

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            res = await client.post(
                "https://www.tikwm.com/api/",
                data={"url": tiktok_url, "hd": 1}
            )
            data = res.json()

        if not data.get("data"):
            await status_msg.edit_text("❌ ভুল লিংক অথবা ভিডিওটি প্রাইভেট/ডিলিট করা হয়েছে।")
            return

        v = data["data"]
        video_url = fix_url(v.get("hdplay") or v.get("play"))
        username = v.get("author", {}).get("unique_id", "unknown")
        views = v.get("play_count", 0)
        likes = v.get("digg_count", 0)

        caption = (
            f"🎬 **Author:** @{username}\n"
            f"👁 **Views:** {views:,} | ❤️ **Likes:** {likes:,}\n\n"
            f"⏳ _নিরাপত্তার স্বার্থে এই ভিডিওটি ১০ মিনিট পর অটোমেটিক ডিলিট হয়ে যাবে।_"
        )

        sent_video = await message.answer_video(
            video=video_url,
            caption=caption,
            parse_mode="Markdown"
        )
        await status_msg.delete()

        # ব্যাকগ্রাউন্ডে ১০ মিনিটের টাইমার চালু
        asyncio.create_task(
            auto_delete_message(sent_video.chat.id, sent_video.message_id, DELETE_AFTER_SECONDS)
        )

    except Exception as e:
        await status_msg.edit_text(f"❌ ভিডিও ডাউনলোড করতে সমস্যা হয়েছে।\nError: `{str(e)}`", parse_mode="Markdown")

# Render-এর পোর্ট সচল রাখার জন্য ডামি ওয়েব সার্ভার
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
