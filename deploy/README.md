# Radar — ücretsiz 7/24 gözcü (Oracle Cloud Always Free)

Amaç: Mac kapalıyken de yeni gönderileri **~1 dakika** içinde Telegram + ntfy'ye düşürmek.
GitHub Actions'ın 5 dakikalık sınırından kurtulmak için küçük bir sunucuda cron çalıştırıyoruz.
**Maliyet: $0** (Oracle Always Free).

## 1. Oracle Cloud hesabı

1. https://www.oracle.com/cloud/free/ → **Start for free**
2. E-posta + ülke (Türkiye) + kimlik doğrulama (kart doğrulaması yapılır, **ücret çekilmez**)
3. Ana bölge (Home Region) seç — **Frankfurt** veya **Amsterdam** (Türkiye'ye en yakın)

> Kart doğrulaması bazen 1-2 saat sürebilir; hesap onaylanınca e-posta gelir.

## 2. Sunucu (instance) oluştur

1. Menü → **Compute → Instances → Create instance**
2. **Image**: Ubuntu 22.04 (veya 24.04)
3. **Shape**: `VM.Standard.A1.Flex` (ARM) → **1 OCPU / 6 GB** yeterli — *Always Free* etiketli olmalı
   - ARM kapasitesi doluysa `VM.Standard.E2.1.Micro` (AMD, Always Free) seç
4. **SSH key**: "Generate a key pair" → **private key'i indir** (`ssh-key-....key`)
5. **Create** → birkaç dakika sonra `Public IP` görünür

## 3. Bağlan

```bash
chmod 600 ~/Downloads/ssh-key-*.key
ssh -i ~/Downloads/ssh-key-*.key ubuntu@<PUBLIC_IP>
```

## 4. Kurulumu çalıştır

```bash
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/krm00/radar/main/deploy/setup.sh)"
```

Sonra anahtarları gir:

```bash
sudo nano /etc/radar.env
```
Doldur:
```
X_BEARER=<X token>
TELEGRAM_BOT_TOKEN=<bot token>
TELEGRAM_CHAT_ID=1635117866
NTFY_TOPIC=radar-krm-db8a2563a232
```

## 5. Test

```bash
set -a; . /etc/radar.env; set +a
cd /opt/radar && python3 notify.py
```

`state.json` yoksa ilk çalışma "tohumlama" yapar (eski gönderileri duyurmaz). İkinci çalışmada
`yeni gönderi yok` yazmalı. Yeni gönderi geldiğinde dakikalar içinde bildirim düşer.

Log: `tail -f /var/log/radar.log`

## Maliyet notu

Her dakika bir `since_id` sorgusu yapılır; **yeni gönderi yoksa 0 post okunur** → aylık maliyet
pratikte **$0** (yalnızca yeni gönderi başına ~$0,005).

## Alternatif: sunucusuz (5 dk → 1 dk)

Sunucu istemiyorsan [cron-job.org](https://cron-job.org) ile GitHub Actions'ı dakikada bir
tetikleyebilirsin:

- URL: `https://api.github.com/repos/krm00/radar/actions/workflows/notify.yml/dispatches`
- Method: `POST`, header `Authorization: Bearer <PAT>`, `Accept: application/vnd.github+json`
- Body: `{"ref":"main"}`
- PAT: fine-grained token, sadece bu repoda **Actions: write**

> PAT'ı üçüncü taraf bir servise verdiğin için bu yol daha az gizlidir; sadece bu repoyla
> sınırlı, istediğinde iptal edilebilir bir token kullan.
