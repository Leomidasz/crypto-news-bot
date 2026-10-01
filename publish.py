"""สรุปข่าวรอบเช้า → บันทึกเป็นไฟล์ให้เว็บแอป + แจ้งเตือน Telegram

GitHub Actions เรียกไฟล์นี้ทุกเช้าอัตโนมัติ
ทดสอบเองในเครื่อง:  python publish.py          (24 ชม.)
                    python publish.py 12       (12 ชม.)
"""
import asyncio
import json
import sys
from datetime import datetime

import httpx

import config
from digest import collect
from summarizer import BKK, MOODS, summarize_structured

DATA_DIR = config.DOCS_DIR / "data"


def rebuild_index() -> list[dict]:
    """สร้างรายการสรุปทั้งหมด (ใหม่สุดก่อน) ให้หน้าเว็บใช้ทำเมนูย้อนหลัง"""
    entries = []
    for f in sorted(DATA_DIR.glob("20*.json"), reverse=True):
        d = json.loads(f.read_text(encoding="utf-8"))
        entries.append({
            "id": f.stem,
            "generated_at": d["generated_at"],
            "headline": d.get("headline", ""),
            "mood": d.get("mood", "mixed"),
            "count": len(d.get("items", [])),
        })
    (DATA_DIR / "index.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return entries


def save(digest: dict) -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(BKK)
    entry_id = now.strftime("%Y-%m-%d_%H%M")
    (DATA_DIR / f"{entry_id}.json").write_text(
        json.dumps({"generated_at": now.isoformat(timespec="minutes"), **digest},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    rebuild_index()
    return entry_id


async def notify(text: str) -> None:
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_NOTIFY_CHAT_IDS):
        print("(ข้ามการแจ้งเตือน Telegram — ยังไม่ได้ตั้ง token/chat id)")
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=20) as client:
        for chat_id in config.TELEGRAM_NOTIFY_CHAT_IDS:
            try:
                r = await client.post(url, json={
                    "chat_id": chat_id, "text": text[:4000],
                    "link_preview_options": {"is_disabled": True},
                })
            except httpx.HTTPError as e:
                # ไม่พิมพ์ข้อความ error เต็ม เพราะบางแบบมี URL ที่มี token อยู่ข้างใน
                print(f"แจ้งเตือน Telegram ไม่สำเร็จ: เชื่อมต่อไม่ได้ ({type(e).__name__})")
                continue
            if r.status_code != 200:
                hint = {401: "token ไม่ถูกต้อง", 400: "chat id ผิด", 403: "ยังไม่ได้กด Start ที่บอท"}
                print(f"แจ้งเตือน Telegram ไม่สำเร็จ: {r.status_code} {hint.get(r.status_code, '')}")


def notify_text(digest: dict, entry_id: str) -> str:
    lines = [f"☀️ สรุปข่าวคริปโตเช้านี้ — {MOODS[digest['mood']]}"]
    if digest["headline"]:
        lines.append(digest["headline"])
    keys = [i for i in digest["items"] if i["category"] == "key"][:5]
    if keys:
        lines.append("")
        lines += [f"• {i['title']}" + (" [ยังไม่ยืนยัน]" if i["unverified"] else "") for i in keys]
    lines.append(f"\nทั้งหมด {len(digest['items'])} ประเด็น")
    if config.APP_URL:
        lines.append(f"📱 อ่านต่อ: {config.APP_URL.rstrip('/')}/#{entry_id}")
    return "\n".join(lines)


async def main(hours: int) -> int:
    posts, msgs, notes = await collect(hours)
    print(f"ดึงได้: X {len(posts)} โพสต์, Discord {len(msgs)} ข้อความ")
    for n in notes:
        print(n)

    try:
        if posts or msgs:
            digest = await summarize_structured(posts, msgs, hours)
        else:
            digest = {"headline": "ไม่มีโพสต์/ข้อความใหม่ในช่วงเวลานี้", "mood": "neutral", "items": []}
    except Exception as e:  # noqa: BLE001
        await notify(f"❌ สรุปข่าวเช้านี้ไม่สำเร็จ: {type(e).__name__}: {e}")
        raise

    digest.update({
        "hours": hours,
        "counts": {"x": len(posts), "discord": len(msgs)},
        "notes": [n.removeprefix("⚠️ ") for n in notes],
    })
    entry_id = save(digest)
    print(f"บันทึกแล้ว: docs/data/{entry_id}.json ({len(digest['items'])} ประเด็น)")
    await notify(notify_text(digest, entry_id))
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    hrs = int(sys.argv[1]) if len(sys.argv) > 1 else config.DIGEST_HOURS
    sys.exit(asyncio.run(main(hrs)))
