"""ทดสอบดึง + สรุปข่าว แล้วพิมพ์ออกหน้าจอ (ไม่ต้องใช้ Telegram)

ใช้:  python run_once.py          → 12 ชม.
      python run_once.py 24       → 24 ชม.
      python run_once.py 6 x      → X อย่างเดียว
      python run_once.py 6 dc     → Discord อย่างเดียว
"""
import asyncio
import sys

from digest import build_digest

if __name__ == "__main__":
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    only = sys.argv[2].lower() if len(sys.argv) > 2 else ""
    use_x = only in ("", "x")
    use_dc = only in ("", "dc")
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")  # ให้ภาษาไทยแสดงถูกใน PowerShell
    print(asyncio.run(build_digest(hours, use_x=use_x, use_discord=use_dc)))
