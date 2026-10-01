"""โหลดค่าตั้งค่าทั้งหมดจากไฟล์ .env"""
import os
import re
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _clean(value: str) -> str:
    """ตัดช่องว่าง/เครื่องหมายที่ติดมาตอนคัดลอก เช่น ` ' " """
    return value.strip().strip("`'\"").strip()


def _list(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [_clean(x) for x in raw.replace("\n", ",").split(",") if _clean(x)]


def _ids(name: str) -> list[int]:
    """อ่านเลข chat id ทนต่อการคัดลอกมาแบบมีอะไรติดมา เช่น `123`, ID: 123"""
    out = []
    for x in _list(name):
        m = re.search(r"-?\d+", x)
        if m:
            out.append(int(m.group()))
    return out


def _int(name: str, default: int) -> int:
    try:
        return int(_clean(os.getenv(name, str(default))))
    except ValueError:
        return default


# --- Telegram ---
TELEGRAM_BOT_TOKEN = _clean(os.getenv("TELEGRAM_BOT_TOKEN", ""))
# chat id ที่อนุญาตให้สั่งบอท (กันคนอื่นมาสั่งแล้วเปลืองเงิน API)
TELEGRAM_ALLOWED_CHAT_IDS = set(_ids("TELEGRAM_ALLOWED_CHAT_IDS"))

# --- X (Twitter) ---
X_BEARER_TOKEN = _clean(os.getenv("X_BEARER_TOKEN", ""))
X_ACCOUNTS = [a.lstrip("@") for a in _list("X_ACCOUNTS")]
# จำกัดจำนวนโพสต์ที่ดึงต่อบัญชีต่อครั้ง (คุมค่าใช้จ่าย: 1 โพสต์ ≈ $0.005)
X_MAX_POSTS_PER_ACCOUNT = max(5, min(100, _int("X_MAX_POSTS_PER_ACCOUNT", 20)))
X_INCLUDE_REPLIES = os.getenv("X_INCLUDE_REPLIES", "false").lower() == "true"

# --- Discord ---
DISCORD_BOT_TOKEN = _clean(os.getenv("DISCORD_BOT_TOKEN", ""))
DISCORD_CHANNEL_IDS = _list("DISCORD_CHANNEL_IDS")
DISCORD_MAX_MESSAGES_PER_CHANNEL = _int("DISCORD_MAX_MESSAGES_PER_CHANNEL", 300)

# --- Claude ---
ANTHROPIC_API_KEY = _clean(os.getenv("ANTHROPIC_API_KEY", ""))
CLAUDE_MODEL = _clean(os.getenv("CLAUDE_MODEL", "")) or "claude-sonnet-5-5"

# --- ทั่วไป ---
DEFAULT_HOURS = _int("DEFAULT_HOURS", 12)
MAX_HOURS = 168  # 7 วัน
DB_PATH = Path(os.getenv("NEWSBOT_DB") or BASE_DIR / "newsbot.db")

# --- สรุปอัตโนมัติทุกเช้า (publish.py / GitHub Actions) ---
DIGEST_HOURS = _int("DIGEST_HOURS", 24)
DOCS_DIR = BASE_DIR / "docs"          # โฟลเดอร์เว็บแอป (GitHub Pages)
APP_URL = _clean(os.getenv("APP_URL", ""))    # ลิงก์เว็บแอป ใส่ในข้อความแจ้งเตือน Telegram
# chat ที่จะส่งแจ้งเตือนตอนเช้า (ถ้าไม่ใส่ ใช้ TELEGRAM_ALLOWED_CHAT_IDS)
TELEGRAM_NOTIFY_CHAT_IDS = _ids("TELEGRAM_NOTIFY_CHAT_IDS") or sorted(TELEGRAM_ALLOWED_CHAT_IDS)


def _mask_secrets_in_github_logs() -> None:
    """บน GitHub Actions: สั่งให้ซ่อนกุญแจทุกตัวใน log เป็น ***

    GitHub ซ่อนค่า Secrets ตามที่กรอกไว้เป๊ะๆ อยู่แล้ว แต่ถ้าค่าที่กรอกมีเครื่องหมาย ` หรือช่องว่างติดมา
    แล้วโค้ดตัดออก ค่าหลังตัดจะไม่ถูกซ่อน → สั่งซ่อนซ้ำอีกชั้นตรงนี้
    """
    if os.getenv("GITHUB_ACTIONS") != "true":
        return
    values = [TELEGRAM_BOT_TOKEN, X_BEARER_TOKEN, DISCORD_BOT_TOKEN, ANTHROPIC_API_KEY]
    values += [str(i) for i in TELEGRAM_NOTIFY_CHAT_IDS]
    for v in values:
        if v and len(v) >= 6:
            print(f"::add-mask::{v}", flush=True)


_mask_secrets_in_github_logs()
