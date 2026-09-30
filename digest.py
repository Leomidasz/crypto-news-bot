"""รวมขั้นตอน: ดึง X + Discord พร้อมกัน → ให้ Claude สรุป"""
import asyncio

from discord_source import fetch_discord
from summarizer import summarize
from x_source import SourceError, fetch_x


async def collect(hours: int, use_x: bool = True, use_discord: bool = True):
    """ดึงข้อมูลทั้งสองแหล่งพร้อมกัน คืน (posts, msgs, notes)"""
    async def _none():
        return [], []

    results = await asyncio.gather(
        fetch_x(hours) if use_x else _none(),
        fetch_discord(hours) if use_discord else _none(),
        return_exceptions=True,
    )

    notes: list[str] = []
    data = []
    for name, res in zip(("X", "Discord"), results):
        if isinstance(res, SourceError):
            notes.append(f"⚠️ {name}: {res}")
            data.append([])
        elif isinstance(res, Exception):
            notes.append(f"⚠️ {name}: เกิดข้อผิดพลาด ({type(res).__name__}: {res})")
            data.append([])
        else:
            items, warns = res
            notes += [f"⚠️ {w}" for w in warns]
            data.append(items)

    posts, msgs = data
    return posts, msgs, notes


async def build_digest(hours: int, use_x: bool = True, use_discord: bool = True) -> str:
    """ข้อความสรุปสำหรับ Telegram (/news) และ run_once.py"""
    posts, msgs, notes = await collect(hours, use_x, use_discord)
    header = f"🗞 สรุปข่าวคริปโต {hours} ชม.ล่าสุด — X {len(posts)} โพสต์ · Discord {len(msgs)} ข้อความ"

    if not posts and not msgs:
        body = "ไม่มีโพสต์/ข้อความใหม่ในช่วงเวลานี้"
    else:
        body = await summarize(posts, msgs, hours)

    parts = [header, body]
    if notes:
        parts.append("\n".join(notes))
    return "\n\n".join(parts)
