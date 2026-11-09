#!/usr/bin/env python3
"""
fetch.py — X API'den veriyi çekip data.json'a yazar (GitHub Actions için).

Token ortam değişkeninden gelir:  X_BEARER
Hesap listesi: accounts.json
Çıktı: data.json  (statik pano bunu okur)
"""
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
ACCOUNTS = HERE / "accounts.json"
DATA = HERE / "data.json"
API = "https://api.x.com/2"
MAX_HISTORY = 72


def get_json(url, token):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "User-Agent": "radar-pages/1.0",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


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


def main():
    token = os.environ.get("X_BEARER", "").strip()
    if not token:
        raise SystemExit("X_BEARER ortam değişkeni yok")

    handles = json.loads(ACCOUNTS.read_text())["x"]
    old = {}
    if DATA.exists():
        try:
            prev = json.loads(DATA.read_text())
            old = {a["handle"]: a for a in prev.get("accounts", [])}
        except Exception:
            old = {}

    out = []
    errors = []
    for handle in handles:
        try:
            acc = fetch_account(handle, token)
        except Exception as e:
            errors.append(f"{handle}: {e}")
            continue
        prev_hist = old.get(acc["handle"], {}).get("history", [])
        now = int(datetime.now(timezone.utc).timestamp())
        hist = prev_hist + [{"ts": now, "v": acc["followers"]}]
        acc["history"] = hist[-MAX_HISTORY:]
        acc["delta"] = (acc["history"][-1]["v"] - acc["history"][0]["v"]) if len(acc["history"]) > 1 else 0
        out.append(acc)

    DATA.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "accounts": out,
        "errors": errors,
    }, ensure_ascii=False, indent=1))
    print(f"data.json yazıldı — {len(out)} hesap, {len(errors)} hata")
    for e in errors:
        print("  !", e)


if __name__ == "__main__":
    main()
