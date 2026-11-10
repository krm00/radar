#!/usr/bin/env python3
"""
fetch.py — X API'den veriyi çekip data.json'a yazar (GitHub Actions için).

Ortam değişkenleri:
  X_BEARER            (zorunlu)  X Bearer Token
  TELEGRAM_BOT_TOKEN  (opsiyonel) yeni gönderi / takipçi değişimi bildirimi
  TELEGRAM_CHAT_ID    (opsiyonel) bildirimin gideceği sohbet

Çıktı: data.json (statik pano bunu okur)
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
ACCOUNTS = HERE / "accounts.json"
DATA = HERE / "data.json"
API = "https://api.x.com/2"
MAX_HISTORY = 72          # ~9 gün (3 saatlik cron ile)
FOLLOW_DELTA_NOTIFY = 1   # bu kadar değişimde bildirim at


# ------------------------------------------------------------------ HTTP

def get_json(url, token):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "User-Agent": "radar-pages/1.0",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


def telegram(text):
    """Token/chat yoksa sessizce atlar."""
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not tok or not chat:
        return False
    payload = urllib.parse.urlencode({
        "chat_id": chat,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=payload)
        urllib.request.urlopen(req, timeout=20)
        print("telegram: bildirim gönderildi")
        return True
    except Exception as e:
        print(f"telegram hata: {e}")
        return False


# ------------------------------------------------------------------ X API

def fetch_account(handle, token):
    h = handle.lstrip("@")
    u = get_json(f"{API}/users/by/username/{h}"
                 f"?user.fields=public_metrics,name,profile_image_url", token)
    d = u.get("data") or {}
    if not d.get("id"):
        raise RuntimeError(f"@{h} bulunamadı: {u}")
    uid = d["id"]
    followers = (d.get("public_metrics") or {}).get("followers_count", 0)

    t = get_json(f"{API}/users/{uid}/tweets"
                 f"?max_results=5&tweet.fields=public_metrics,created_at", token)
    posts = []
    for p in t.get("data", []) or []:
        m = p.get("public_metrics") or {}
        posts.append({
            "id": p["id"],
            "text": p.get("text", ""),
            "likes": m.get("like_count", 0),
            "comments": m.get("reply_count", 0),
            "reposts": m.get("retweet_count", 0),
            "created_at": p.get("created_at", ""),
            "url": f"https://x.com/{h}/status/{p['id']}",
        })
    return {
        "handle": f"@{h}",
        "name": d.get("name") or h,
        "followers": followers,
        "posts": posts,
    }


# ------------------------------------------------------------------ main

def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main():
    token = os.environ.get("X_BEARER", "").strip()
    if not token:
        raise SystemExit("X_BEARER ortam değişkeni yok")

    handles = json.loads(ACCOUNTS.read_text())["x"]

    prev = {}
    if DATA.exists():
        try:
            raw = json.loads(DATA.read_text())
            prev = {a["handle"]: a for a in raw.get("accounts", [])}
        except Exception:
            prev = {}
    first_run = not prev

    out, errors, events = [], [], []

    for handle in handles:
        try:
            acc = fetch_account(handle, token)
        except Exception as e:
            errors.append(f"{handle}: {e}")
            continue

        old = prev.get(acc["handle"], {})
        hist = old.get("history", [])
        now = int(datetime.now(timezone.utc).timestamp())
        hist = hist + [{"ts": now, "v": acc["followers"]}]
        acc["history"] = hist[-MAX_HISTORY:]
        acc["delta"] = (acc["history"][-1]["v"] - acc["history"][0]["v"]) if len(acc["history"]) > 1 else 0
        out.append(acc)

        if first_run:
            continue  # ilk çalışmada bildirim yok

        # --- yeni gönderiler ---
        old_ids = {p["id"] for p in old.get("posts", [])}
        new_posts = [p for p in acc["posts"] if p["id"] not in old_ids]
        for p in reversed(new_posts[-3:]):     # en fazla 3 bildirim
            events.append(
                f"📡 <b>{esc(acc['handle'])}</b> yeni gönderi\n\n"
                f"{esc(p['text'][:300])}\n\n"
                f"♥ {p['likes']} · 💬 {p['comments']} · 🔁 {p['reposts']}\n"
                f"{p['url']}"
            )

        # --- takipçi değişimi ---
        old_f = old.get("followers")
        if old_f is not None and abs(acc["followers"] - old_f) >= FOLLOW_DELTA_NOTIFY:
            diff = acc["followers"] - old_f
            arrow = "📈" if diff > 0 else "📉"
            events.append(
                f"{arrow} <b>{esc(acc['handle'])}</b> takipçi: "
                f"{old_f} → {acc['followers']} ({diff:+d})"
            )

    DATA.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "accounts": out,
        "errors": errors,
    }, ensure_ascii=False, indent=1))

    print(f"data.json yazıldı — {len(out)} hesap, {len(errors)} hata, {len(events)} bildirim")
    for e in errors:
        print("  !", e)

    for ev in events[:5]:
        telegram(ev)


if __name__ == "__main__":
    main()
