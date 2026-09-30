"""โหลดค่าตั้งค่าทั้งหมดจากไฟล์ .env"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _list(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# chat id ที่อนุญาตให้สั่งบอท (กันคนอื่นมาสั่งแล้วเปลืองเงิน API)
TELEGRAM_ALLOWED_CHAT_IDS = {int(x) for x in _list("TELEGRAM_ALLOWED_CHAT_IDS")}

# --- X (Twitter) ---
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "")
X_ACCOUNTS = [a.lstrip("@") for a in _list("X_ACCOUNTS")]
# จำกัดจำนวนโพสต์ที่ดึงต่อบัญชีต่อครั้ง (คุมค่าใช้จ่าย: 1 โพสต์ ≈ $0.005)
X_MAX_POSTS_PER_ACCOUNT = max(5, min(100, _int("X_MAX_POSTS_PER_ACCOUNT", 20)))
X_INCLUDE_REPLIES = os.getenv("X_INCLUDE_REPLIES", "false").lower() == "true"

# --- Discord ---
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_IDS = _list("DISCORD_CHANNEL_IDS")
DISCORD_MAX_MESSAGES_PER_CHANNEL = _int("DISCORD_MAX_MESSAGES_PER_CHANNEL", 300)

# --- Claude ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

# --- ทั่วไป ---
DEFAULT_HOURS = _int("DEFAULT_HOURS", 12)
MAX_HOURS = 168  # 7 วัน
DB_PATH = Path(os.getenv("NEWSBOT_DB") or BASE_DIR / "newsbot.db")

# --- สรุปอัตโนมัติทุกเช้า (publish.py / GitHub Actions) ---
DIGEST_HOURS = _int("DIGEST_HOURS", 24)
DOCS_DIR = BASE_DIR / "docs"          # โฟลเดอร์เว็บแอป (GitHub Pages)
APP_URL = os.getenv("APP_URL", "")    # ลิงก์เว็บแอป ใส่ในข้อความแจ้งเตือน Telegram
# chat ที่จะส่งแจ้งเตือนตอนเช้า (ถ้าไม่ใส่ ใช้ TELEGRAM_ALLOWED_CHAT_IDS)
TELEGRAM_NOTIFY_CHAT_IDS = [
    int(x) for x in _list("TELEGRAM_NOTIFY_CHAT_IDS")
] or sorted(TELEGRAM_ALLOWED_CHAT_IDS)
