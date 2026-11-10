#!/usr/bin/env python3
"""
stream.py — X filtered stream ile ANLIK Telegram bildirimi.

GitHub Actions'ta çalışmaz (kalıcı bağlantı gerekir). Mac'te, Raspberry Pi'de
veya küçük bir VPS'te 7/24 çalıştırılır.

Gerekli ortam değişkenleri:
  X_BEARER             X Bearer Token
  TELEGRAM_BOT_TOKEN   Telegram bot token
  TELEGRAM_CHAT_ID     hedef sohbet

Kullanım:
  X_BEARER=... TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python3 stream.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.x.com/2"
BEARER = os.environ.get("X_BEARER", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
HANDLE = os.environ.get("WATCH_HANDLE", "erkekdoven62").lstrip("@")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def req(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {BEARER}",
        "Content-Type": "application/json",
        "User-Agent": "radar-stream/1.0",
    })
    return urllib.request.urlopen(r, timeout=90)


def telegram(text):
    if not TG_TOKEN or not TG_CHAT:
        return
    payload = urllib.parse.urlencode({
        "chat_id": TG_CHAT, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=payload),
            timeout=20)
    except Exception as e:
        log("telegram hata:", e)


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def ensure_rule():
    rule = f"from:{HANDLE}"
    try:
        with req(f"{API}/tweets/search/stream/rules") as r:
            meta = json.loads(r.read().decode())
        existing = {x["value"] for x in (meta.get("data") or [])}
        if rule in existing:
            log("kural hazır:", rule)
            return
        ids = [x["id"] for x in (meta.get("data") or [])]
        if ids:
            req(f"{API}/tweets/search/stream/rules", "POST", {"delete": {"ids": ids}}).read()
        req(f"{API}/tweets/search/stream/rules", "POST", {"add": [{"value": rule}]}).read()
        log("kural eklendi:", rule)
    except urllib.error.HTTPError as e:
        log("kural hatası:", e.code, e.read(200).decode(errors="replace")[:200])
        raise


def listen():
    params = ("?tweet.fields=created_at,public_metrics,referenced_tweets"
              "&expansions=author_id,referenced_tweets.id&user.fields=username,name")
    backoff = 5
    while True:
        try:
            log("stream bağlanıyor…")
            with req(f"{API}/tweets/search/stream{params}") as resp:
                log("bağlı — yeni gönderiler anında bildirilecek")
                backoff = 5
                for raw in resp:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        ev = json.loads(raw.decode())
                    except Exception:
                        continue
                    d = ev.get("data") or {}
                    if not d.get("id"):
                        continue
                    m = d.get("public_metrics") or {}
                    refs = d.get("referenced_tweets") or []
                    kind = "gönderi"
                    if any(x.get("type") == "retweeted" for x in refs):
                        kind = "retweet"
                    elif any(x.get("type") == "quoted" for x in refs):
                        kind = "alıntı"
                    elif any(x.get("type") == "replied_to" for x in refs):
                        kind = "yanıt"
                    text = d.get("text", "")
                    log(f"yeni {kind}: {text[:60]}")
                    telegram(
                        f"📡 <b>@{HANDLE}</b> yeni {kind}\n\n{esc(text[:400])}\n\n"
                        f"♥ {m.get('like_count',0)} · 💬 {m.get('reply_count',0)} · "
                        f"🔁 {m.get('retweet_count',0)}\n"
                        f"https://x.com/{HANDLE}/status/{d['id']}"
                    )
        except urllib.error.HTTPError as e:
            body = e.read(300).decode(errors="replace")
            log("stream hata:", e.code, body)
            if e.code == 429:
                time.sleep(60)
        except Exception as e:
            log("bağlantı koptu:", type(e).__name__, e)
        log(f"{backoff} sn sonra yeniden denenecek")
        time.sleep(backoff)
        backoff = min(backoff * 2, 300)


if __name__ == "__main__":
    if not BEARER:
        sys.exit("X_BEARER yok")
    ensure_rule()
    listen()
