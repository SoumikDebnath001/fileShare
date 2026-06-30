# fileShare — Full Raspberry Pi Setup

Step-by-step guide to run fileShare on a **Raspberry Pi Zero 2 W** so it:

- starts automatically every time the Pi powers on (no manual restarts),
- is reachable through your own domain, and
- lets you upload and download files from anywhere.

Run these commands on the Pi (over SSH or a terminal), top to bottom.

> These steps auto-detect your username and paths, so they work even if your
> Pi user is not `pi`.

---

## 0. Set your two values

Edit the two lines below, then paste the whole block into the terminal:

```bash
# ===== EDIT THESE TWO LINES =====
REPO_URL="https://github.com/<your-username>/fileShare.git"
DOMAIN="files.yourdomain.com"
# ================================
```

---

## 1. Install system packages

```bash
sudo apt update
sudo apt install -y git python3-venv nginx
```

---

## 2. Clone your repo

```bash
cd ~
git clone "$REPO_URL"
cd ~/fileShare
APP_DIR="$PWD"          # remembers the real path for later steps
```

---

## 3. Create the Python environment + install deps

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

---

## 4. Configure your password and secret

```bash
cp .env.example .env
SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
sed -i "s|^FILESHARE_SECRET=.*|FILESHARE_SECRET=$SECRET|" .env
sed -i "s|^FILESHARE_STORAGE=.*|FILESHARE_STORAGE=$APP_DIR/storage|" .env
nano .env     # set FILESHARE_PASSWORD to a strong password, then Ctrl+O Enter Ctrl+X
```

> Tip: to store files on a USB stick instead of the SD card, mount it and set
> `FILESHARE_STORAGE=/mnt/usb` in `.env`.

---

## 5. Auto-start on boot (systemd)

This generates the service file with your **actual** username and paths:

```bash
sudo tee /etc/systemd/system/fileshare.service >/dev/null <<EOF
[Unit]
Description=fileShare self-hosted file storage
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/python app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now fileshare
systemctl status fileshare --no-pager
```

You want to see `active (running)`. It will now start automatically on every
boot and restart itself if it ever crashes.

Quick local test (should print `200`):

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/login
```

---

## 6. Reverse proxy for your domain (nginx)

```bash
sudo tee /etc/nginx/sites-available/fileshare >/dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    client_max_body_size 8G;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_request_buffering off;
        proxy_read_timeout      3600;
        proxy_send_timeout      3600;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/fileshare /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

---

## 7. Point your domain at the Pi

Do this in two places:

- **DNS:** at your domain registrar, create an **A record** for your domain →
  your home's public IP. Find it with `curl -s ifconfig.me` on the Pi. If your
  home IP changes over time, use a Dynamic DNS (DDNS) service.
- **Router:** forward external **ports 80 and 443** to the Pi's local IP.
  Find the local IP with `hostname -I`.

Test from your phone on mobile data (not home WiFi): open
`http://files.yourdomain.com` — you should see the login page.

---

## 8. Add free HTTPS (after DNS resolves)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d "$DOMAIN"
```

Now open `https://files.yourdomain.com`, log in with your password, and
upload/download your files.

---

## Updating later

After you push changes to GitHub:

```bash
cd ~/fileShare && git pull && .venv/bin/pip install -r requirements.txt && sudo systemctl restart fileshare
```

---

## Troubleshooting

```bash
journalctl -u fileshare -f            # live app logs
sudo tail -f /var/log/nginx/error.log # nginx errors
systemctl status fileshare --no-pager # is the app running?
sudo nginx -t                         # is the nginx config valid?
```

| Symptom | Likely fix |
| --- | --- |
| `502 Bad Gateway` from the domain | App isn't running — check `systemctl status fileshare` |
| Domain doesn't load at all | DNS not pointing to your IP, or ports 80/443 not forwarded |
| `413 Request Entity Too Large` | Raise `client_max_body_size` (nginx) and `FILESHARE_MAX_GB` (.env) |
| Login fails | Wrong `FILESHARE_PASSWORD` in `.env`; restart after editing |
| Sessions drop after restart | Set a fixed `FILESHARE_SECRET` in `.env` (step 4 does this) |
