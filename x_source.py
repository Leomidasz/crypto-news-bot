"""ดึงโพสต์จากบัญชี X ที่กำหนด ผ่าน X API v2 (คิดเงินแบบ pay-per-use)"""
import time
from datetime import datetime, timezone

import httpx

import config
import storage

API = "https://api.x.com/2"


class SourceError(Exception):
    pass


def _ts(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def _explain(r: httpx.Response) -> str:
    hints = {
        401: "X_BEARER_TOKEN ไม่ถูกต้อง",
        402: "เครดิต X API หมด — เติมเครดิตใน developer console",
        403: "แอป X ไม่มีสิทธิ์อ่านข้อมูลนี้",
        429: "ยิง X API ถี่เกินไป (rate limit) — รอสักครู่แล้วลองใหม่",
    }
    return f"X API error {r.status_code}: {hints.get(r.status_code, r.text[:200])}"


async def _resolve_user_ids(client: httpx.AsyncClient, warnings: list[str]) -> dict[str, str]:
    """แปลง username → user id (เก็บ cache ไว้ จะได้เสียเงินครั้งเดียว)"""
    ids: dict[str, str] = {}
    missing = []
    for u in config.X_ACCOUNTS:
        uid = storage.get_user_id(u)
        if uid:
            ids[u] = uid
        else:
            missing.append(u)

    for i in range(0, len(missing), 100):
        chunk = missing[i : i + 100]
        r = await client.get(f"{API}/users/by", params={"usernames": ",".join(chunk)})
        if r.status_code != 200:
            raise SourceError(_explain(r))
        body = r.json()
        for user in body.get("data", []):
            storage.save_user(user["username"], user["id"])
            # ใช้ชื่อตามที่พิมพ์ใน .env เป็น key
            for u in chunk:
                if u.lower() == user["username"].lower():
                    ids[u] = user["id"]
        for err in body.get("errors", []):
            warnings.append(f"X: ไม่พบบัญชี @{err.get('value', '?')}")
    return ids


async def fetch_x(hours: int) -> tuple[list[dict], list[str]]:
    """คืน (โพสต์ในช่วง N ชั่วโมงล่าสุด, รายการคำเตือน)"""
    warnings: list[str] = []
    if not config.X_ACCOUNTS:
        return [], warnings
    if not config.X_BEARER_TOKEN:
        raise SourceError("ยังไม่ได้ใส่ X_BEARER_TOKEN ใน .env")

    since_ts = int(time.time()) - hours * 3600
    headers = {"Authorization": f"Bearer {config.X_BEARER_TOKEN}"}

    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        ids = await _resolve_user_ids(client, warnings)

        for username, uid in ids.items():
            params = {
                "max_results": config.X_MAX_POSTS_PER_ACCOUNT,
                "tweet.fields": "created_at,public_metrics,note_tweet",
                "exclude": "retweets" if config.X_INCLUDE_REPLIES else "retweets,replies",
            }
            latest = storage.latest_post(uid)
            if latest and latest[1] >= since_ts:
                # เคยดึงแล้ว → ขอเฉพาะโพสต์ที่ใหม่กว่า (ไม่จ่ายซ้ำ)
                params["since_id"] = str(latest[0])
            else:
                params["start_time"] = datetime.fromtimestamp(since_ts, timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )

            r = await client.get(f"{API}/users/{uid}/tweets", params=params)
            if r.status_code in (401, 402):
                raise SourceError(_explain(r))  # ปัญหาทั้งระบบ หยุดเลย
            if r.status_code != 200:
                warnings.append(f"@{username}: {_explain(r)}")
                continue

            posts = []
            for t in r.json().get("data", []):
                text = (t.get("note_tweet") or {}).get("text") or t.get("text", "")
                m = t.get("public_metrics") or {}
                posts.append(
                    {
                        "id": int(t["id"]),
                        "user_id": uid,
                        "username": username,
                        "created_ts": _ts(t["created_at"]),
                        "text": text,
                        "url": f"https://x.com/{username}/status/{t['id']}",
                        "likes": m.get("like_count", 0),
                        "reposts": m.get("retweet_count", 0),
                    }
                )
            storage.save_posts(posts)

    return storage.posts_since(list(ids.values()), since_ts), warnings
