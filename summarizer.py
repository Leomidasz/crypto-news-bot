"""ส่งโพสต์/ข้อความทั้งหมดให้ Claude สรุปเป็นภาษาไทย

Claude ตอบกลับเป็นข้อมูลโครงสร้าง (ผ่าน tool) → ใช้ได้ทั้ง
  - เว็บแอป (บันทึกเป็น JSON)
  - Telegram (แปลงเป็นข้อความด้วย render_text)
"""
import re
from datetime import datetime, timedelta, timezone

from anthropic import AsyncAnthropic

import config

BKK = timezone(timedelta(hours=7))
MAX_ITEM_CHARS = 1200      # ตัดข้อความยาวเกินต่อชิ้น
MAX_CORPUS_CHARS = 150_000  # กันส่งข้อมูลเยอะเกินจนเปลืองเงิน

CATEGORIES = {
    "key": "🔥 ประเด็นสำคัญ",
    "market": "📈 ตลาดและราคา",
    "projects": "🧩 โปรเจกต์ / เหรียญ",
    "regulation": "⚖️ กฎหมาย / Regulation",
    "airdrop": "🎁 Airdrop / โอกาส",
}
MOODS = {"bullish": "🟢 บวก", "bearish": "🔴 ลบ", "neutral": "⚪ ทรงตัว", "mixed": "🟡 ผสม"}

SYSTEM_PROMPT = """คุณคือผู้ช่วยสรุปข่าวคริปโตสำหรับเทรดเดอร์ชาวไทย
คุณจะได้รับโพสต์จาก X และข้อความจาก Discord ในช่วงเวลาหนึ่ง ให้สรุปเป็นภาษาไทยที่อ่านจบใน 2 นาที
แล้วส่งผลผ่านเครื่องมือ publish_digest เท่านั้น

กฎ:
- จัดกลุ่มตามประเด็น ไม่ใช่ตามแหล่ง ข่าวเดียวกันจากหลายแหล่งให้รวมเป็นข้อเดียว และใส่ทุกแหล่งใน sources
- หมวด key = 3-5 ประเด็นที่กระทบตลาดมากที่สุด ประเด็นที่อยู่ใน key แล้วห้ามซ้ำในหมวดอื่น
- เรียงแต่ละหมวดจากสำคัญมากไปน้อย
- sources เขียนสั้นๆ เช่น "@username" หรือ "#ชื่อช่อง"
- links ต้องคัดลอกมาจากบรรทัด "ลิงก์:" ในข้อมูลเท่านั้น ห้ามแต่งลิงก์เอง
- ข่าวลือ/ยังไม่ยืนยัน ให้ unverified = true
- ตัดโพสต์ขยะ โฆษณา มีม และ giveaway ทิ้ง ยกเว้น airdrop/whitelist ที่มีรายละเอียดชัดเจน
- คงชื่อเหรียญ ชื่อโปรเจกต์ ตัวเลข และศัพท์เทคนิคเป็นภาษาอังกฤษตามต้นฉบับ
- ห้ามแต่งข้อมูลที่ไม่มีในต้นฉบับ ห้ามให้คำแนะนำซื้อขาย
- ห้ามใช้ Markdown ในข้อความ (ไม่มี ** หรือ #)"""

DIGEST_TOOL = {
    "name": "publish_digest",
    "description": "ส่งสรุปข่าวคริปโตฉบับสมบูรณ์",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {
                "type": "string",
                "description": "สรุปภาพรวมทั้งหมดใน 1 ประโยค (ไม่เกิน 120 ตัวอักษร)",
            },
            "mood": {
                "type": "string",
                "enum": list(MOODS),
                "description": "บรรยากาศตลาดโดยรวมจากข่าวชุดนี้",
            },
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "enum": list(CATEGORIES)},
                        "title": {"type": "string", "description": "หัวข้อสั้น ไม่เกิน 70 ตัวอักษร"},
                        "summary": {"type": "string", "description": "รายละเอียด 1-3 ประโยค"},
                        "importance": {"type": "string", "enum": ["high", "medium", "low"]},
                        "unverified": {"type": "boolean"},
                        "sources": {"type": "array", "items": {"type": "string"}},
                        "links": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["category", "title", "summary", "importance", "unverified", "sources", "links"],
                },
            },
        },
        "required": ["headline", "mood", "items"],
    },
}


def _fmt_time(ts: int) -> str:
    return datetime.fromtimestamp(ts, BKK).strftime("%d/%m %H:%M")


def build_corpus(posts: list[dict], msgs: list[dict]) -> str:
    lines = []
    for p in posts:
        text = p["text"][:MAX_ITEM_CHARS]
        lines.append(
            f"[X @{p['username']} | {_fmt_time(p['created_ts'])} | "
            f"❤{p['likes']} 🔁{p['reposts']}] {text}\nลิงก์: {p['url']}"
        )
    for m in msgs:
        text = m["text"][:MAX_ITEM_CHARS]
        lines.append(
            f"[Discord #{m['channel_name']} | {m['author']} | {_fmt_time(m['created_ts'])}] "
            f"{text}\nลิงก์: {m['url']}"
        )

    corpus, total = [], 0
    # ถ้าเยอะเกิน เก็บของใหม่สุดไว้ก่อน
    for line in reversed(lines):
        if total + len(line) > MAX_CORPUS_CHARS:
            break
        corpus.append(line)
        total += len(line)
    return "\n\n".join(reversed(corpus))


def _clean(result: dict, allowed_links: set[str]) -> dict:
    """กันข้อมูลเพี้ยน: ตัดลิงก์ที่ไม่ได้มาจากต้นฉบับ, เรียงตามหมวดและความสำคัญ"""
    rank = {"high": 0, "medium": 1, "low": 2}
    order = list(CATEGORIES)
    items = []
    for it in result.get("items") or []:
        if it.get("category") not in CATEGORIES or not it.get("title"):
            continue
        it["links"] = [l for l in it.get("links") or [] if l in allowed_links][:3]
        it["sources"] = [s for s in it.get("sources") or [] if s][:6]
        it["importance"] = it.get("importance") if it.get("importance") in rank else "medium"
        it["unverified"] = bool(it.get("unverified"))
        items.append(it)
    items.sort(key=lambda i: (order.index(i["category"]), rank[i["importance"]]))
    return {
        "headline": (result.get("headline") or "").strip(),
        "mood": result.get("mood") if result.get("mood") in MOODS else "mixed",
        "items": items,
    }


async def summarize_structured(posts: list[dict], msgs: list[dict], hours: int) -> dict:
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ยังไม่ได้ใส่ ANTHROPIC_API_KEY ใน .env")

    corpus = build_corpus(posts, msgs)
    client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    resp = await client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=6000,
        system=SYSTEM_PROMPT,
        tools=[DIGEST_TOOL],
        tool_choice={"type": "tool", "name": "publish_digest"},
        messages=[{
            "role": "user",
            "content": f"ข้อมูลช่วง {hours} ชั่วโมงล่าสุด "
            f"({len(posts)} โพสต์จาก X, {len(msgs)} ข้อความจาก Discord):\n\n{corpus}",
        }],
    )
    block = next((b for b in resp.content if b.type == "tool_use"), None)
    if block is None:
        raise RuntimeError("Claude ไม่ได้ส่งสรุปกลับมาในรูปแบบที่กำหนด")
    allowed = set(re.findall(r"^ลิงก์: (\S+)$", corpus, re.M))
    return _clean(block.input, allowed)


def render_text(digest: dict) -> str:
    """แปลงสรุปแบบโครงสร้างเป็นข้อความธรรมดาสำหรับ Telegram"""
    out = []
    if digest["headline"]:
        out.append(f"💬 {digest['headline']}")
    out.append(f"บรรยากาศตลาด: {MOODS[digest['mood']]}")
    current = None
    for it in digest["items"]:
        if it["category"] != current:
            current = it["category"]
            out.append(f"\n{CATEGORIES[current]}")
        tag = " [ยังไม่ยืนยัน]" if it["unverified"] else ""
        src = f" ({', '.join(it['sources'])})" if it["sources"] else ""
        out.append(f"• {it['title']}{tag} — {it['summary']}{src}")
    key_links = [l for it in digest["items"] if it["category"] == "key" for l in it["links"][:1]][:3]
    if key_links:
        out.append("\n🔗 ลิงก์ที่ควรเปิดอ่าน:")
        out += key_links
    return "\n".join(out)


async def summarize(posts: list[dict], msgs: list[dict], hours: int) -> str:
    """ใช้กับบอท Telegram (คำสั่ง /news)"""
    return render_text(await summarize_structured(posts, msgs, hours))
