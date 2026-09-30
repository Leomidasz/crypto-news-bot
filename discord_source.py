"""ดึงข้อความจากช่อง Discord ผ่าน Discord REST API (ฟรี)
บอทต้องอยู่ในเซิร์ฟเวอร์ และเปิด MESSAGE CONTENT INTENT ไว้"""
import asyncio
import time
from datetime import datetime

import httpx

import config
import storage
from x_source import SourceError

API = "https://discord.com/api/v10"
DISCORD_EPOCH_MS = 1420070400000


def snowflake_from_ts(ts: int) -> int:
    return (ts * 1000 - DISCORD_EPOCH_MS) << 22


def _message_text(m: dict) -> str:
    """รวมข้อความ + embed + ข้อความที่ถูก forward มา"""
    parts = [m.get("content") or ""]
    for snap in m.get("message_snapshots") or []:
        inner = snap.get("message") or {}
        parts.append(inner.get("content") or "")
        for e in inner.get("embeds") or []:
            parts += [e.get("title") or "", e.get("description") or ""]
    for e in m.get("embeds") or []:
        parts += [e.get("title") or "", e.get("description") or ""]
        for f in e.get("fields") or []:
            parts.append(f"{f.get('name', '')}: {f.get('value', '')}")
    return "\n".join(p.strip() for p in parts if p and p.strip())


async def _get(client: httpx.AsyncClient, url: str, params=None) -> httpx.Response:
    for _ in range(5):
        r = await client.get(url, params=params)
        if r.status_code == 429:  # rate limit → รอตามที่ Discord บอก
            await asyncio.sleep(float(r.json().get("retry_after", 1)) + 0.2)
            continue
        return r
    return r


async def fetch_discord(hours: int) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    if not config.DISCORD_CHANNEL_IDS:
        return [], warnings
    if not config.DISCORD_BOT_TOKEN:
        raise SourceError("ยังไม่ได้ใส่ DISCORD_BOT_TOKEN ใน .env")

    since_ts = int(time.time()) - hours * 3600
    window_start = snowflake_from_ts(since_ts)
    headers = {"Authorization": f"Bot {config.DISCORD_BOT_TOKEN}"}

    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        for ch in config.DISCORD_CHANNEL_IDS:
            info = await _get(client, f"{API}/channels/{ch}")
            if info.status_code == 401:
                raise SourceError("DISCORD_BOT_TOKEN ไม่ถูกต้อง")
            if info.status_code != 200:
                warnings.append(
                    f"Discord ช่อง {ch}: เข้าไม่ได้ ({info.status_code}) — "
                    "เช็คว่าบอทอยู่ในเซิร์ฟเวอร์และมีสิทธิ์ View Channel + Read Message History"
                )
                continue
            ch_info = info.json()
            ch_name = ch_info.get("name", ch)
            guild = ch_info.get("guild_id", "@me")

            last = storage.latest_msg_id(ch)
            after = max(last or 0, window_start)
            fetched, empty = 0, 0

            while fetched < config.DISCORD_MAX_MESSAGES_PER_CHANNEL:
                r = await _get(
                    client, f"{API}/channels/{ch}/messages", {"after": str(after), "limit": 100}
                )
                if r.status_code != 200:
                    warnings.append(f"Discord #{ch_name}: error {r.status_code}")
                    break
                batch = r.json()
                if not batch:
                    break

                msgs = []
                for m in batch:
                    text = _message_text(m)
                    if not text:
                        empty += 1
                        continue
                    author = m.get("author") or {}
                    msgs.append(
                        {
                            "id": int(m["id"]),
                            "channel_id": ch,
                            "channel_name": ch_name,
                            "author": author.get("global_name") or author.get("username", "?"),
                            "created_ts": int(datetime.fromisoformat(m["timestamp"]).timestamp()),
                            "text": text,
                            "url": f"https://discord.com/channels/{guild}/{ch}/{m['id']}",
                        }
                    )
                storage.save_msgs(msgs)
                fetched += len(batch)
                after = max(int(m["id"]) for m in batch)
                if len(batch) < 100:
                    break

            if fetched and empty == fetched:
                warnings.append(
                    f"Discord #{ch_name}: ได้ข้อความแต่เนื้อหาว่างทั้งหมด — "
                    "น่าจะยังไม่ได้เปิด MESSAGE CONTENT INTENT ใน Developer Portal"
                )

    return storage.msgs_since(config.DISCORD_CHANNEL_IDS, since_ts), warnings
