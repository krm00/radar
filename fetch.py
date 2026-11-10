#!/usr/bin/env python3
"""
fetch.py — X API'den veriyi çekip data.json'a yazar (GitHub Actions için).

Ortam değişkenleri:
  X_BEARER            (zorunlu)  X Bearer Token
  POST_LIMIT          (opsiyonel) okunacak gönderi sayısı, varsayılan 10
  TELEGRAM_BOT_TOKEN  (opsiyonel) bildirim
  TELEGRAM_CHAT_ID    (opsiyonel) bildirim

Çıktı: data.json (statik pano bunu okur)
"""
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
ACCOUNTS = HERE / "accounts.json"
DATA = HERE / "data.json"
API = "https://api.x.com/2"

MAX_HISTORY = 72          # takipçi geçmişi kaydı
MAX_POST_HIST = 24        # gönderi başına metrik kaydı
MAX_EVENTS = 40           # aktivite akışı
FOLLOW_DELTA_NOTIFY = 1


# ------------------------------------------------------------------ HTTP

def get_json(url, token):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "User-Agent": "radar-pages/2.0",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


def telegram(text):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not tok or not chat:
        return False
    payload = urllib.parse.urlencode({
        "chat_id": chat, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=payload)
        urllib.request.urlopen(req, timeout=20)
        print("telegram: gönderildi")
        return True
    except Exception as e:
        print(f"telegram hata: {e}")
        return False


# ------------------------------------------------------------------ X API

def fetch_account(handle, token, limit):
    h = handle.lstrip("@")
    u = get_json(f"{API}/users/by/username/{h}"
                 f"?user.fields=public_metrics,name,profile_image_url,verified,"
                 f"description,created_at,pinned_tweet_id", token)
    d = u.get("data") or {}
    if not d.get("id"):
        raise RuntimeError(f"@{h} bulunamadı: {u}")
    uid = d["id"]
    stats = d.get("public_metrics") or {}
    pinned = d.get("pinned_tweet_id")

    t = get_json(
        f"{API}/users/{uid}/tweets?max_results={max(5, min(100, limit))}"
        f"&tweet.fields=public_metrics,created_at,attachments,lang,entities,"
        f"referenced_tweets,conversation_id,note_tweet"
        f"&expansions=attachments.media_keys"
        f"&media.fields=url,preview_image_url,type,width,height,alt_text", token)

    media = {m.get("media_key"): m for m in (t.get("includes", {}) or {}).get("media", [])}

    posts = []
    for p in t.get("data", []) or []:
        m = p.get("public_metrics") or {}
        ent = p.get("entities") or {}
        refs = p.get("referenced_tweets") or []
        ref_types = {r.get("type") for r in refs}

        text = ((p.get("note_tweet") or {}).get("text")) or p.get("text", "")

        imgs = []
        for k in ((p.get("attachments") or {}).get("media_keys") or []):
            mm = media.get(k) or {}
            if mm.get("type") in ("photo", "video", "animated_gif"):
                imgs.append({
                    "type": mm.get("type"),
                    "url": mm.get("url") or "",
                    "preview": mm.get("preview_image_url") or mm.get("url") or "",
                    "w": mm.get("width") or 0,
                    "h": mm.get("height") or 0,
                    "alt": mm.get("alt_text") or "",
                })

        if "retweeted" in ref_types or text.startswith("RT @"):
            ptype = "retweet"
        elif "quoted" in ref_types:
            ptype = "quote"
        elif "replied_to" in ref_types:
            ptype = "reply"
        else:
            ptype = "original"

        posts.append({
            "id": p["id"],
            "text": text,
            "type": ptype,
            "likes": m.get("like_count", 0),
            "comments": m.get("reply_count", 0),
            "reposts": m.get("retweet_count", 0),
            "quotes": m.get("quote_count", 0),
            "bookmarks": m.get("bookmark_count", 0),
            "impressions": m.get("impression_count", 0),
            "lang": p.get("lang", ""),
            "created_at": p.get("created_at", ""),
            "hashtags": [x.get("tag") for x in (ent.get("hashtags") or [])][:8],
            "mentions": [x.get("username") for x in (ent.get("mentions") or [])][:8],
            "pinned": bool(pinned and str(p.get("id")) == str(pinned)),
            "media": imgs,
            "url": f"https://x.com/{h}/status/{p['id']}",
        })

    return {
        "handle": f"@{h}",
        "name": d.get("name") or h,
        "avatar": d.get("profile_image_url", "").replace("_normal", "_200x200"),
        "verified": bool(d.get("verified")),
        "bio": d.get("description", "") or "",
        "joined": d.get("created_at", "") or "",
        "followers": stats.get("followers_count", 0),
        "following": stats.get("following_count", 0),
        "tweets_total": stats.get("tweet_count", 0),
        "posts": posts,
    }


# ------------------------------------------------------------------ yardımcı

def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def engagement(p):
    return p["likes"] + p["comments"] + p["reposts"] + p["quotes"]


def enrich(acc, prev_posts):
    """Türetilmiş metrikler + gönderi başına geçmiş."""
    now = int(datetime.now(timezone.utc).timestamp())
    prev_map = {p["id"]: p for p in prev_posts}

    for p in acc["posts"]:
        e = engagement(p)
        p["engagement"] = e
        # ER yalnızca kendi gönderileri için anlamlı; RT'lerde metrikler asıl
        # gönderiden miras kaldığı için oranı çarpıtıyor, hesaplanmıyor.
        if p["type"] == "retweet" or (p["impressions"] or 0) < 10:
            p["er"] = None
        else:
            p["er"] = round(e / p["impressions"] * 100, 2)

        hist = (prev_map.get(p["id"], {}) or {}).get("hist", [])
        hist = hist + [{"ts": now, "l": p["likes"], "c": p["comments"], "r": p["reposts"]}]
        p["hist"] = hist[-MAX_POST_HIST:]

    posts = acc["posts"]
    if posts:
        total_e = sum(p["engagement"] for p in posts)
        acc["engagement"] = total_e
        ers = [p["er"] for p in posts if p.get("er") is not None]
        acc["avg_er"] = round(sum(ers) / len(ers), 2) if ers else 0
        own = [p for p in posts if p["type"] != "retweet"] or posts
        acc["top_post"] = max(own, key=lambda p: p["engagement"])["id"]
        acc["original_count"] = sum(1 for p in posts if p["type"] == "original")
    else:
        acc["engagement"], acc["avg_er"], acc["top_post"] = 0, 0, None
    return acc


# ------------------------------------------------------------------ main

def main():
    token = os.environ.get("X_BEARER", "").strip()
    if not token:
        raise SystemExit("X_BEARER ortam değişkeni yok")

    limit = int(os.environ.get("POST_LIMIT", "10"))
    handles = json.loads(ACCOUNTS.read_text())["x"]

    prev, prev_events = {}, []
    if DATA.exists():
        try:
            raw = json.loads(DATA.read_text())
            prev = {a["handle"]: a for a in raw.get("accounts", [])}
            prev_events = raw.get("events", [])
        except Exception:
            pass
    first_run = not prev

    out, errors, events, notes = [], [], [], []

    for handle in handles:
        try:
            acc = fetch_account(handle, token, limit)
        except Exception as e:
            errors.append(f"{handle}: {e}")
            continue

        old = prev.get(acc["handle"], {})
        now = int(datetime.now(timezone.utc).timestamp())

        # takipçi geçmişi
        hist = old.get("history", []) + [{"ts": now, "v": acc["followers"]}]
        acc["history"] = hist[-MAX_HISTORY:]
        acc["delta"] = acc["history"][-1]["v"] - acc["history"][0]["v"] if len(acc["history"]) > 1 else 0
        acc["delta_24h"] = _delta_in(acc["history"], 24)
        acc["delta_7d"] = _delta_in(acc["history"], 24 * 7)

        enrich(acc, old.get("posts", []))
        out.append(acc)

        if first_run:
            continue

        # yeni gönderiler
        old_ids = {p["id"] for p in old.get("posts", [])}
        for p in reversed([p for p in acc["posts"] if p["id"] not in old_ids][-3:]):
            label = {"reply": "yanıt", "quote": "alıntı", "retweet": "RT"}.get(p["type"], "gönderi")
            events.append({"ts": now, "type": "post", "handle": acc["handle"],
                           "text": f"yeni {label}: {p['text'][:140]}"})
            notes.append(f"📡 <b>{esc(acc['handle'])}</b> yeni {label}\n\n"
                         f"{esc(p['text'][:300])}\n\n"
                         f"♥ {p['likes']} · 💬 {p['comments']} · 🔁 {p['reposts']}\n{p['url']}")

        # takipçi değişimi
        old_f = old.get("followers")
        if old_f is not None and abs(acc["followers"] - old_f) >= FOLLOW_DELTA_NOTIFY:
            diff = acc["followers"] - old_f
            arrow = "📈" if diff > 0 else "📉"
            events.append({"ts": now, "type": "followers", "handle": acc["handle"],
                           "text": f"takipçi {old_f} → {acc['followers']} ({diff:+d})"})
            notes.append(f"{arrow} <b>{esc(acc['handle'])}</b> takipçi: "
                         f"{old_f} → {acc['followers']} ({diff:+d})")

        # profil değişimi
        changes = []
        if old and old.get("name") and old["name"] != acc["name"]:
            changes.append(f"ad: “{old['name']}” → “{acc['name']}”")
        if old and old.get("bio") is not None and old["bio"] != acc["bio"]:
            changes.append("biyografi değişti")
        if old and old.get("verified") is not None and old["verified"] != acc["verified"]:
            changes.append("doğrulama rozeti " + ("alındı" if old["verified"] else "verildi"))
        if old and old.get("avatar") and old["avatar"] != acc["avatar"]:
            changes.append("profil fotoğrafı değişti")
        for c in changes:
            events.append({"ts": now, "type": "profile", "handle": acc["handle"], "text": c})
            notes.append(f"👤 <b>{esc(acc['handle'])}</b> profil: {esc(c)}")

    events = (prev_events + events)[-MAX_EVENTS:]

    DATA.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "accounts": out,
        "events": events,
        "errors": errors,
    }, ensure_ascii=False, indent=1))

    print(f"data.json — {len(out)} hesap, {len(errors)} hata, {len(notes)} bildirim")
    for e in errors:
        print("  !", e)
    for n in notes[:5]:
        telegram(n)


def _delta_in(history, hours):
    if len(history) < 2:
        return 0
    cutoff = history[-1]["ts"] - hours * 3600
    base = next((h for h in reversed(history) if h["ts"] <= cutoff), history[0])
    return history[-1]["v"] - base["v"]


if __name__ == "__main__":
    main()
