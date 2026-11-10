#!/usr/bin/env python3
"""
watch.py — 7/24 cihazda (Mac / Raspberry Pi / VPS) çalışan hızlı gözcü.

45 saniyede bir `notify.py` mantığını çalıştırır: yeni gönderi varsa anında
Telegram + ntfy'ye gönderir, yoksa hiçbir okuma yapmaz (maliyet ~0).

Kullanım:
  X_BEARER=... TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... NTFY_TOPIC=... python3 watch.py
"""
import os
import sys
import time

import notify

INTERVAL = int(os.environ.get("WATCH_INTERVAL", "45"))

if __name__ == "__main__":
    if not os.environ.get("X_BEARER"):
        sys.exit("X_BEARER yok")
    print(f"gözcü başladı — her {INTERVAL} sn kontrol", flush=True)
    while True:
        try:
            notify.main()
        except Exception as e:
            print("hata:", type(e).__name__, e, flush=True)
        time.sleep(INTERVAL)
