#!/usr/bin/env python3
"""
digest.py — günlük Telegram özeti (ek API maliyeti yok, data.json'u okur).

İçerik: son 24 saatteki gönderi sayısı, takipçi değişimi, toplam etkileşim,
en çok etkileşim alan gönderi ve gündemden birkaç başlık.
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from push import send

HERE = Path(__file__).parent
DATA = HERE / "data.json"

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main():
    try:
        d = json.loads(DATA.read_text())
    except Exception as e:
        print("data.json okunamadı:", e)
        return

    now = datetime.now(timezone.utc).timestamp()
    parts = [f"📊 <b>Radar günlük özet</b> · {datetime.now(timezone.utc).strftime('%d.%m.%Y')}"]

    for a in d.get("accounts", []):
        posts = a.get("posts", [])
        day = [p for p in posts if p.get("created_at") and
               (now - datetime.fromisoformat(p["created_at"].replace("Z", "+00:00")).timestamp()) < 86400]

        delta24 = a.get("delta_24h")
        arrow = "📈" if (delta24 or 0) > 0 else ("📉" if (delta24 or 0) < 0 else "➖")
        eng = sum(p.get("engagement", 0) or 0 for p in day)

        parts.append(
            f"\n<b>{esc(a.get('name') or a.get('handle'))}</b> ({esc(a.get('handle',''))})\n"
            f"👥 {a.get('followers', 0):,} takipçi · {arrow} {delta24 or 0:+d} (24s)\n"
            f"📝 son 24s: {len(day)} gönderi · ⚡ {eng} etkileşim"
        )

        if posts:
            top = max(posts, key=lambda p: p.get("engagement", 0) or 0)
            parts.append(
                f"\n🔥 <b>En iyi gönderi</b> (♥{top.get('likes',0)} · 💬{top.get('comments',0)})\n"
                f"{esc((top.get('text') or '')[:180])}\n{top.get('url','')}"
            )

    trends = [t.get("name") for t in (d.get("trends") or [])[:3] if t.get("name")]
    if trends:
        parts.append("\n🇹🇷 Gündem: " + " · ".join(esc(t) for t in trends))

    parts.append("\nhttps://krm00.github.io/radar/")
    ok = send("Radar günlük özet", "\n".join(parts))
    print("özet gönderildi" if ok else "özet gönderilemedi")


if __name__ == "__main__":
    main()
