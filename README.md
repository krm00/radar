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
- Maliyet: her çalışma ~5 gönderi okuması ≈ **$0,025** → saatlik = ~$18/ay üst sınır
  (X aynı gün aynı gönderiyi tekrar faturalamazsa çok daha az). Seyreltmek için
  `cron: "17 */3 * * *"` gibi 3 saatte bire al.

## iPhone

Safari → `https://<kullanıcı>.github.io/radar/` → Paylaş → **Ana Ekrana Ekle**.
Artık her yerden, Mac kapalıyken de açılır.

## Dosyalar

| Dosya | İş |
|---|---|
| `fetch.py` | X API'den çeker, `data.json` yazar |
| `index.html` | Statik pano (token içermez) |
| `accounts.json` | Takip edilecek hesaplar |
| `.github/workflows/radar.yml` | Saatlik cron |
