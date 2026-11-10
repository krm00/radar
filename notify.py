#!/usr/bin/env python3
"""
notify.py — hızlı bildirim kontrolü (GitHub Actions, 5 dakikada bir).

Yalnızca `since_id`'den SONRAKİ gönderileri okur; yeni gönderi yoksa hiçbir post
okunmaz → neredeyse sıfır API maliyeti.

Durum dosyası: state.json  ({"last": {"@handle": "tweet_id"}, "uid": {"@handle": "user_id"}})
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from push import send

HERE = Path(__file__).parent
STATE = HERE / "state.json"
DATA = HERE / "data.json"
ACCOUNTS = HERE / "accounts.json"
API = "https://api.x.com/2"

BEARER = os.environ.get("X_BEARER", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def log(*a):
    print(*a, flush=True)


def get(url):
    r = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {BEARER}", "User-Agent": "radar-notify/1.0"})
    with urllib.request.urlopen(r, timeout=25) as x:
        return json.loads(x.read().decode())


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def load_json(p, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def main():
    if not BEARER:
        raise SystemExit("X_BEARER yok")

    handles = json.loads(ACCOUNTS.read_text())["x"]
    state = load_json(STATE, {"last": {}, "uid": {}})
    data = load_json(DATA, {"accounts": []})

    # ilk çalışmada mevcut en yeni gönderiyi referans al (eski gönderileri duyurma)
    seeded = False
    for a in data.get("accounts", []):
        if a.get("handle") and a.get("posts") and not state["last"].get(a["handle"]):
            state["last"][a["handle"]] = a["posts"][0]["id"]
            seeded = True

    changed = seeded
    for handle in handles:
        try:
            if not state["uid"].get(handle):
                u = get(f"{API}/users/by/username/{handle.lstrip('@')}")
                state["uid"][handle] = (u.get("data") or {}).get("id")
                changed = True
        except Exception as e:
            log(f"{handle}: uid alınamadı: {e}")
            continue

        uid = state["uid"].get(handle)
        if not uid:
            continue
        since = state["last"].get(handle)
        if not since:
            continue

        try:
            d = get(f"{API}/users/{uid}/tweets?since_id={since}&max_results=5"
                    f"&tweet.fields=created_at,public_metrics,referenced_tweets")
        except urllib.error.HTTPError as e:
            log(f"{handle}: HTTP {e.code}")
            continue

        tweets = d.get("data") or []
        if not tweets:
            continue

        for t in reversed(tweets):          # eskiden yeniye
            m = t.get("public_metrics") or {}
            refs = t.get("referenced_tweets") or []
            kind = "gönderi"
            if any(x.get("type") == "retweeted" for x in refs):
                kind = "retweet"
            elif any(x.get("type") == "quoted" for x in refs):
                kind = "alıntı"
            elif any(x.get("type") == "replied_to" for x in refs):
                kind = "yanıt"
            log(f"yeni {kind}: {t['id']}")
            send("Radar ⚡", f"⚡ <b>{esc(handle)}</b> yeni {kind}\n\n{esc(t.get('text','')[:400])}\n\n"
                     f"♥ {m.get('like_count',0)} · 💬 {m.get('reply_count',0)} · "
                     f"🔁 {m.get('retweet_count',0)}\n"
                     f"https://x.com/{handle.lstrip('@')}/status/{t['id']}")

        newest = max(tweets, key=lambda t: int(t["id"]))
        state["last"][handle] = newest["id"]
        changed = True

    if changed:
        STATE.write_text(json.dumps(state, indent=1))
        log("state.json güncellendi")
    else:
        log("yeni gönderi yok")


if __name__ == "__main__":
    main()
