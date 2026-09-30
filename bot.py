"""บอท Telegram: พิมพ์ /news เพื่อรับสรุปข่าว

คำสั่ง:
  /news [ชม.]     สรุปจาก X + Discord (ค่าเริ่มต้น 12 ชม.) เช่น /news 24
  /news_x [ชม.]   สรุปจาก X อย่างเดียว
  /news_dc [ชม.]  สรุปจาก Discord อย่างเดียว
  /sources        ดูรายชื่อบัญชี X และช่อง Discord ที่ติดตาม
  /start          แสดง chat id ของคุณ (ใช้ตั้งค่า TELEGRAM_ALLOWED_CHAT_IDS)
"""
import logging
import time

from telegram import LinkPreviewOptions, Update
from telegram.error import Conflict
from telegram.ext import Application, CommandHandler, ContextTypes

import config
from digest import build_digest

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # กัน token โผล่ใน log
log = logging.getLogger("newsbot")

TG_LIMIT = 4000


def split_message(text: str, limit: int = TG_LIMIT) -> list[str]:
    """Telegram รับได้ไม่เกิน 4096 ตัวอักษรต่อข้อความ → ตัดแบ่งตามบรรทัด"""
    chunks, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:  # บรรทัดเดียวยาวเกิน
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(cur) + len(line) + 1 > limit:
            chunks.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        chunks.append(cur)
    return chunks


def _allowed(update: Update) -> bool:
    return update.effective_chat.id in config.TELEGRAM_ALLOWED_CHAT_IDS


def _hours(args: list[str]) -> int:
    try:
        h = int(args[0]) if args else config.DEFAULT_HOURS
    except ValueError:
        h = config.DEFAULT_HOURS
    return max(1, min(config.MAX_HOURS, h))


async def _run(update: Update, context: ContextTypes.DEFAULT_TYPE, use_x: bool, use_dc: bool):
    if not _allowed(update):
        await update.message.reply_text("⛔ chat นี้ยังไม่ได้รับอนุญาต พิมพ์ /start เพื่อดู chat id")
        return
    hours = _hours(context.args)
    wait = await update.message.reply_text(f"⏳ กำลังดึงข่าว {hours} ชม.ล่าสุด...")
    try:
        text = await build_digest(hours, use_x=use_x, use_discord=use_dc)
    except Exception as e:  # noqa: BLE001
        log.exception("digest failed")
        text = f"❌ สรุปไม่สำเร็จ: {type(e).__name__}: {e}"
    await wait.delete()
    for chunk in split_message(text):
        await update.message.reply_text(chunk, link_preview_options=NO_PREVIEW)


async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run(update, context, True, True)


async def news_x(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run(update, context, True, False)


async def news_dc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run(update, context, False, True)


async def sources(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    xs = ", ".join(f"@{a}" for a in config.X_ACCOUNTS) or "(ยังไม่ได้ตั้ง)"
    dcs = ", ".join(config.DISCORD_CHANNEL_IDS) or "(ยังไม่ได้ตั้ง)"
    await update.message.reply_text(f"บัญชี X: {xs}\n\nช่อง Discord: {dcs}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    status = "✅ ได้รับอนุญาตแล้ว" if _allowed(update) else "⛔ ยังไม่ได้รับอนุญาต"
    await update.message.reply_text(
        f"chat id ของคุณคือ: {chat_id}\nสถานะ: {status}\n\n"
        "ใส่เลขนี้ใน TELEGRAM_ALLOWED_CHAT_IDS ในไฟล์ .env แล้วรันบอทใหม่\n\n"
        "คำสั่ง: /news [ชม.] · /news_x · /news_dc · /sources"
    )


def register_handlers(app: Application) -> None:
    """เรียกฟังก์ชันนี้ได้จากบอทตัวอื่น (เช่น Hongthong Bot) เพื่อเพิ่มคำสั่งข่าวเข้าไป"""
    app.add_handler(CommandHandler("news", news))
    app.add_handler(CommandHandler("news_x", news_x))
    app.add_handler(CommandHandler("news_dc", news_dc))
    app.add_handler(CommandHandler("sources", sources))


_last_conflict_log = 0.0


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    global _last_conflict_log
    if isinstance(context.error, Conflict):
        # token เดียวกันถูกเปิดอยู่อีกเครื่อง (เช่น คอมบ้าน + คอมที่ทำงาน)
        if time.time() - _last_conflict_log > 60:
            _last_conflict_log = time.time()
            log.error(
                "⚠️ บอทตัวนี้กำลังเปิดอยู่ที่เครื่องอื่น! "
                "ให้ปิดที่เครื่องนั้นก่อน (Ctrl+C) — เปิดพร้อมกันได้ทีละเครื่องเท่านั้น"
            )
        return
    log.error("เกิดข้อผิดพลาด: %s", context.error)


def main():
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit("ยังไม่ได้ใส่ TELEGRAM_BOT_TOKEN ใน .env")
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    register_handlers(app)
    app.add_error_handler(on_error)
    log.info("บอทพร้อมแล้ว — เปิด Telegram แล้วพิมพ์ /start")
    # ทิ้งคำสั่งที่ค้างไว้ตอนบอทปิด กันเปิดเครื่องมาแล้วรัน /news รัวๆ จนเสียเงิน
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
