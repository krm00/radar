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
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from push import send

HERE = Path(__file__).parent
ACCOUNTS = HERE / "accounts.json"
DATA = HERE / "data.json"
API = "https://api.x.com/2"

MAX_HISTORY = 72          # takipçi geçmişi kaydı
MAX_POST_HIST = 24        # gönderi başına metrik kaydı
MAX_EVENTS = 40           # aktivite akışı
MAX_ARCHIVE = 400         # analitik için saklanan gönderi
FOLLOW_DELTA_NOTIFY = 1


# ------------------------------------------------------------------ HTTP

def get_json(url, token):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "User-Agent": "radar-pages/2.0",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


def tweet_status(token, tid):
    """True: duruyor, False: silinmiş, None: bilinmiyor (403/limit)."""
    try:
        d = get_json(f"{API}/tweets/{tid}?tweet.fields=public_metrics", token)
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None
    except Exception:
        return None
    if d.get("data"):
        return True
    errs = d.get("errors") or []
    for e in errs:
        blob = f"{e.get('title','')} {e.get('detail','')}".lower()
        if "not found" in blob or "could not find" in blob:
            return False
    return None


def fetch_conversation(token, post_id, limit=30):
    """Bir gönderinin yorumları + hesabın cevapları (tek seferlik)."""
    q = urllib.parse.quote(f"conversation_id:{post_id}")
    d = get_json(f"{API}/tweets/search/recent?query={q}"
                 f"&max_results={max(10, min(100, limit))}"
                 f"&tweet.fields=public_metrics,created_at,referenced_tweets,author_id"
                 f"&expansions=author_id&user.fields=username,name,profile_image_url", token)
    users = {u.get("id"): u for u in ((d.get("includes") or {}).get("users") or [])}
    out = []
    for t in (d.get("data") or []):
        if str(t.get("id")) == str(post_id):
            continue
        refs = t.get("referenced_tweets") or []
        parent = next((r.get("id") for r in refs if r.get("type") == "replied_to"), None)
        u = users.get(t.get("author_id")) or {}
        m = t.get("public_metrics") or {}
        out.append({
            "id": t["id"],
            "parent": parent,
            "author": u.get("username") or "?",
            "name": u.get("name") or "",
            "avatar": (u.get("profile_image_url") or "").replace("_normal", "_200x200"),
            "text": t.get("text", ""),
            "likes": m.get("like_count", 0),
            "created_at": t.get("created_at", ""),
        })
    return out


def fetch_trends(token, woeid="23424969", limit=15):
    """Gündem: tek çağrı, ucuz."""
    try:
        d = get_json(f"{API}/trends/by/woeid/{woeid}", token)
        items = []
        for t in (d.get("data") or [])[:limit]:
            items.append({"name": t.get("trend_name", ""),
                          "count": t.get("trend_metadata", {}).get("post_count") if isinstance(t.get("trend_metadata"), dict) else None})
        return items
    except Exception as e:
        print("trends hata:", e)
        return []


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

    prev, prev_events, prev_raw = {}, [], {}
    if DATA.exists():
        try:
            raw = json.loads(DATA.read_text())
            prev_raw = raw
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

    # --- konuşmalar: her gönderi için yalnızca bir kez ---
    convs = dict(prev_raw.get("conversations") or {})
    conv_budget = int(os.environ.get("CONV_MAX", "1"))
    conv_limit = int(os.environ.get("CONV_LIMIT", "30"))
    fetched_now = 0
    for acc in out:
        for p in acc["posts"]:
            if fetched_now >= conv_budget:
                break
            if p["id"] in convs:
                continue
            try:
                created = int(datetime.fromisoformat(
                    p["created_at"].replace("Z", "+00:00")).timestamp())
                age_s = int(datetime.now(timezone.utc).timestamp()) - created
            except Exception:
                age_s = 10 ** 9
            if age_s > 48 * 3600:      # sadece son 2 günün gönderileri
                continue
            try:
                convs[p["id"]] = {"fetched": int(datetime.now(timezone.utc).timestamp()),
                                  "replies": fetch_conversation(token, p["id"], conv_limit)}
                fetched_now += 1
                print(f"konuşma çekildi: {p['id']} ({len(convs[p['id']]['replies'])} yorum)")
            except Exception as e:
                print(f"konuşma hata {p['id']}: {e}")
    # eski konuşmaları buda
    if len(convs) > 20:
        keep = dict(sorted(convs.items(), key=lambda kv: kv[1].get("fetched", 0), reverse=True)[:20])
        convs = keep

    # --- arşiv: tüm görülen gönderiler (analitik için, ücretsiz) ---
    archive = {x["id"]: x for x in (prev_raw.get("archive") or [])} if prev_raw else {}

    # --- silinen gönderi tespiti: bir önceki listede olup şimdi olmayanlar ---
    deleted_budget = int(os.environ.get("DEL_CHECK_MAX", "8"))
    for acc in out:
        prev_ids = {p["id"] for p in (prev.get(acc["handle"], {}) or {}).get("posts", [])}
        cur_ids = {p["id"] for p in acc["posts"]}
        for mid in (prev_ids - cur_ids):
            if deleted_budget <= 0:
                break
            item = archive.get(mid)
            if item and item.get("deleted"):
                continue
            st = tweet_status(token, mid)
            deleted_budget -= 1
            if st is False:
                if item:
                    item["deleted"] = True
                    item["deleted_at"] = int(datetime.now(timezone.utc).timestamp())
                events.append({"ts": int(datetime.now(timezone.utc).timestamp()),
                               "type": "deleted", "handle": acc["handle"],
                               "text": "gönderi silindi: " + ((item or {}).get("text", "")[:140] or mid)})
                notes.append(f"🗑️ <b>{esc(acc['handle'])}</b> bir gönderi sildi\n\n{esc((item or {}).get('text','')[:250])}")
                print(f"silinmiş: {mid}")
            elif st is True and item:
                item["checked_at"] = int(datetime.now(timezone.utc).timestamp())

    for acc in out:
        for p in acc["posts"]:
            archive[p["id"]] = {
                "id": p["id"], "created_at": p["created_at"], "type": p["type"],
                "likes": p["likes"], "comments": p["comments"], "reposts": p["reposts"],
                "quotes": p["quotes"], "impressions": p["impressions"], "lang": p["lang"],
                "engagement": p.get("engagement", 0), "er": p.get("er"),
                "reply_to": (p.get("reply_to") or {}).get("user") or "",
                "rt_of": p.get("rt_of") or "",
                "handle": acc["handle"],
                "deleted": False,
                "deleted_at": None,
            }
    archive_list = sorted(archive.values(), key=lambda x: x.get("created_at") or "", reverse=True)[:MAX_ARCHIVE]

    trends = fetch_trends(token)
    events = (prev_events + events)[-MAX_EVENTS:]

    DATA.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "accounts": out,
        "events": events,
        "archive": archive_list,
        "trends": trends,
        "conversations": convs,
        "errors": errors,
    }, ensure_ascii=False, indent=1))

    print(f"data.json — {len(out)} hesap, {len(errors)} hata, {len(notes)} bildirim")
    for e in errors:
        print("  !", e)
    for n in notes[:5]:
        send("Radar", n)


def _delta_in(history, hours):
    if len(history) < 2:
        return 0
    cutoff = history[-1]["ts"] - hours * 3600
    base = next((h for h in reversed(history) if h["ts"] <= cutoff), history[0])
    return history[-1]["v"] - base["v"]


if __name__ == "__main__":
    main()
