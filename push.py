#!/usr/bin/env python3
"""
push.py — bildirimleri birden çok kanala gönderir.

Kanallar (hangisi yapılandırılmışsa):
  Telegram : TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
  ntfy.sh  : NTFY_TOPIC  (iOS/Android uygulaması kilit ekranına düşürür)

Kullanım:
  from push import send
  send("Radar", "yeni gönderi ...")
"""
import html
import os
import re
import urllib.parse
import urllib.request


def _plain(text):
    """HTML etiketlerini ntfy için düz metne çevir."""
    t = re.sub(r"<br\s*/?>", "\n", text)
    t = re.sub(r"</p>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t).strip()


def telegram(text):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not tok or not chat:
        return False
    payload = urllib.parse.urlencode({
        "chat_id": chat, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage",
                                   data=payload), timeout=20)
        return True
    except Exception as e:
        print("telegram hata:", e)
        return False


def ntfy(title, text, priority="default"):
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        return False
    body = _plain(text).encode("utf-8")
    req = urllib.request.Request(
        f"https://ntfy.sh/{urllib.parse.quote(topic)}",
        data=body,
        headers={
            "Title": title.encode("utf-8").decode("latin-1", "ignore") or "Radar",
            "Priority": priority,
            "Tags": "bell",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=20)
        return True
    except Exception as e:
        print("ntfy hata:", e)
        return False


def send(title, text, priority="default"):
    """Hem Telegram hem ntfy'ye gönderir (hangisi varsa)."""
    ok_tg = telegram(text)
    ok_nt = ntfy(title, text, priority)
    return ok_tg or ok_nt
