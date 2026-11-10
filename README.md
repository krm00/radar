# Radar — statik pano (GitHub Pages)

X hesabının takipçi sayısını ve son gönderilerinin beğeni/yorum sayılarını gösteren
statik pano. Veri **GitHub Actions** ile saatte bir güncellenir; Mac açık olmak zorunda değil.

## Kurulum (tek sefer)

1. **Repo oluştur** (public — Pages ücretsiz olsun diye):
   ```bash
   gh repo create radar --public --source=. --remote=origin --push
   ```

2. **Token'ı secret olarak ekle** (koda asla yazma):
   ```bash
   gh secret set X_BEARER
   # yapıştır: AAAA... (X Bearer Token)
   ```

3. **Pages'i aç** (main dalı, kök dizin):
   ```bash
   gh api -X POST repos/{owner}/radar/pages \
     -f "source[branch]=main" -f "source[path]=/"
   ```
   ya da web: Settings → Pages → Source: **Deploy from a branch** → `main` / `(root)`

4. **İlk veriyi üret** (Actions'ı elle çalıştır):
   ```bash
   gh workflow run radar.yml
   ```

Birkaç dakika sonra: `https://<kullanıcı>.github.io/radar/`

## Günlük kullanım

- Hesap eklemek/çıkarmak: `accounts.json` düzenle, commit'le
- Güncelleme sıklığı: `.github/workflows/radar.yml` içindeki `cron` satırı
  (şu an **3 saatte bir**: `"17 */3 * * *"`)
- Maliyet: her çalışma ~5 gönderi okuması ≈ **$0,025** → 3 saatlik = ~**$6/ay** üst sınır
  (X aynı gün aynı gönderiyi tekrar faturalamazsa çok daha az)

## Telegram bildirimi (opsiyonel)

Yeni gönderi veya takipçi değişiminde Telegram'dan haber almak için:

1. Telegram'da **@BotFather** → `/newbot` → token al
2. Botuna bir mesaj at, sonra `https://api.telegram.org/bot<TOKEN>/getUpdates`
   adresinden `chat.id` değerini al
3. Secret olarak ekle:
   ```bash
   gh secret set TELEGRAM_BOT_TOKEN
   gh secret set TELEGRAM_CHAT_ID
   ```

Token/chat yoksa bildirim adımı sessizce atlanır — pano normal çalışmaya devam eder.

## iPhone

Safari → `https://<kullanıcı>.github.io/radar/` → Paylaş → **Ana Ekrana Ekle**.
Artık her yerden, Mac kapalıyken de açılır.

## Dosyalar

| Dosya | İş |
|---|---|
| `fetch.py` | X API'den çeker, `data.json` yazar |
| `index.html` | Statik pano (token içermez) |
| `accounts.json` | Takip edilecek hesaplar |
| `.github/workflows/radar.yml` | 3 saatlik cron + Telegram adımı |
