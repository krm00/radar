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
            d = get(f"{API}/users/{uid}/tweets?since_id={since}&max_results=100"
                    f"&tweet.fields=created_at,public_metrics,referenced_tweets,in_reply_to_user_id"
                    f"&expansions=referenced_tweets.id,referenced_tweets.id.author_id,in_reply_to_user_id"
                    f"&user.fields=username,name")
        except urllib.error.HTTPError as e:
            log(f"{handle}: HTTP {e.code}")
            continue

        tweets = d.get("data") or []
        if not tweets:
            continue

        inc = d.get("includes") or {}
        users = {u.get("id"): u for u in (inc.get("users") or [])}
        ref_tweets = {t.get("id"): t for t in (inc.get("tweets") or [])}

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
            # kime ait / kimi hedef aldı
            extra = ""
            rep = next((x for x in refs if x.get("type") == "replied_to"), None)
            quo = next((x for x in refs if x.get("type") == "quoted"), None)
            rtt = next((x for x in refs if x.get("type") == "retweeted"), None)
            if kind == "retweet" and rtt:
                au = users.get((ref_tweets.get(rtt.get("id")) or {}).get("author_id")) or {}
                extra = f" · @{au.get('username','?')} retweetledi"
            elif kind == "yanıt":
                au = users.get(t.get("in_reply_to_user_id")) or {}
                extra = f" · @{au.get('username','?')} kullanıcısına"
            elif kind == "alıntı" and quo:
                au = users.get((ref_tweets.get(quo.get("id")) or {}).get("author_id")) or {}
                extra = f" · @{au.get('username','?')} gönderisinden"

            log(f"yeni {kind}{extra}: {t['id']}")
            send("Radar ⚡", f"⚡ <b>{esc(handle)}</b> yeni {kind}{esc(extra)}\n\n"
                     f"{esc(t.get('text','')[:400])}\n\n"
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
